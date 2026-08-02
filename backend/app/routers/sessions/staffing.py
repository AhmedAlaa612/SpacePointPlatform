"""Staffing marketplace routers (V2 W4 S4-2). Session-scoped — see
services/sessions/staffing.py's module docstring for why. Layered on top of
the pre-existing direct-assign endpoints in cohorts.py (assign_instructor/
unassign_instructor), which stay untouched and fully working.

Notifications per the S4-2 spec: on open_call -> notify every instructor|
facilitator user; on selection -> assignment email (transactional, no
consent gate) + in-app notification; on removal -> notify (handled in
cohorts.py's unassign_instructor, the only place instructors are removed).
"""

from __future__ import annotations

import uuid

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_instructor_or_facilitator, require_operations
from app.db.session import get_db
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.cohort import Cohort
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.schemas.sessions.cohorts import BulkActionError, SessionInstructorOut, SessionOut
from app.services.sessions import openings as openings_svc
from app.schemas.sessions.staffing import (
    AddonSummary,
    OpeningSummary,
    AvailableSessionOut,
    CloseCohortCallRequest,
    CohortCallOut,
    EligibleInstructorOut,
    InterestOut,
    MySessionOut,
    OpenCohortCallRequest,
    OpenCohortCallResponse,
    RegisterInterestRequest,
    SelectInstructorsRequest,
    SelectInstructorsResponse,
    SessionCallOut,
)
from app.services.notification import create_notification
from app.services.sessions import staffing
from app.workers.settings import get_arq_redis, safe_enqueue

router = APIRouter(prefix="/sessions", tags=["sessions-staffing"])


async def _session_out(db: AsyncSession, session: Session) -> SessionOut:
    rows = (await db.execute(
        select(SessionInstructor, User.full_name, DeliveryRole.name)
        .join(User, User.id == SessionInstructor.user_id)
        .join(DeliveryRole, DeliveryRole.id == SessionInstructor.role_id)
        .where(SessionInstructor.session_id == session.id)
    )).all()
    out = SessionOut.model_validate(session)
    out.instructors = [
        SessionInstructorOut(user_id=si.user_id, full_name=name, role=role_name)
        for si, name, role_name in rows
    ]
    out.target_user_ids = await staffing.call_target_ids(db, session.id)
    return out


# ── Ops: open call / reopen ─────────────────────────────────────────────────

class OpenCallRequest(BaseModel):
    user_ids: list[uuid.UUID] | None = None
    # B2: which roles are on offer. None opens every configured opening —
    # today's exact behaviour.
    role_ids: list[uuid.UUID] | None = None
    # Optional ops-facing name for this call, e.g. "Backup facilitators" —
    # only useful once a session has more than one call open (2026-08-01).
    label: str | None = None


@router.post("/{session_id}/staffing/open-call", response_model=SessionOut)
async def open_call(
    session_id: uuid.UUID,
    body: OpenCallRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Opens a new call on this session (2026-08-01: a session can run
    several calls at once — call this again while already open_call to add
    another, e.g. a targeted call for one missing role alongside a public
    one). The picked instructors are the call's audience in the real
    sense — only they can see the session or register interest because of
    it. No selection means a call open to everyone."""
    target_ids = list(body.user_ids) if body and body.user_ids else []
    role_ids = list(body.role_ids) if body and body.role_ids else None
    label = body.label if body else None
    session = await staffing.open_call(
        db, session_id, target_user_ids=target_ids, role_ids=role_ids,
        actor_user_id=current_user.id, label=label,
    )

    query = select(User).where(User.roles.any("instructor") | User.roles.any("facilitator"))
    if target_ids:
        query = query.where(User.id.in_(target_ids))

    eligible = (await db.execute(query)).scalars().all()
    for user in eligible:
        await create_notification(
            db, user.id, "New session open for interest",
            body=f"A session on {session.meeting_date} is open for interest — register if you'd like it.",
            type="staffing_open_call",
        )

    await db.commit()
    await db.refresh(session)
    return await _session_out(db, session)


# ── Ops: cohort-level standing calls (2026-08-01) ───────────────────────────
# Groups a chosen subset of a cohort's sessions' own calls into one standing
# CohortCall so ops can view/close them together.
#
# 2026-08-02: the ungrouped `POST /cohorts/{id}/staffing/open-call` that used
# to sit here is gone. It opened calls that this grouped model couldn't see,
# so anything created through it could never be closed as a group — two
# coexisting call models, one of which the management UI didn't know about.
# The `staffing.open_call_for_cohort` SERVICE it called is still very much
# alive: it's what `open_cohort_call` below falls back to when `session_ids`
# is omitted. Only the parallel HTTP entry point is retired.

@router.post("/cohorts/{cohort_id}/staffing/calls", response_model=OpenCohortCallResponse)
async def open_cohort_call(
    cohort_id: uuid.UUID,
    body: OpenCohortCallRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Opens one standing call across a chosen subset of this cohort's
    sessions (omit `session_ids` for every currently-unstaffed session in
    the cohort — the same default `open_call_for_cohort` already uses).
    Partial failure (e.g. a listed session that's already staffed, or one
    that isn't actually in this cohort) is reported in `failed` rather than
    rolling back the rest of the batch."""
    session_ids = list(body.session_ids) if body and body.session_ids is not None else None
    target_ids = list(body.user_ids) if body and body.user_ids else []
    role_ids = list(body.role_ids) if body and body.role_ids else None
    label = body.label if body else None

    call, succeeded, failed = await staffing.open_cohort_call(
        db, cohort_id, session_ids=session_ids, target_user_ids=target_ids,
        role_ids=role_ids, actor_user_id=current_user.id, label=label,
    )

    if succeeded:
        query = select(User).where(User.roles.any("instructor") | User.roles.any("facilitator"))
        if target_ids:
            query = query.where(User.id.in_(target_ids))

        eligible = (await db.execute(query)).scalars().all()
        for user in eligible:
            await create_notification(
                db, user.id, "New sessions open for interest",
                body=f"{len(succeeded)} session(s) are open for interest — register if you'd like one.",
                type="staffing_open_call",
            )

    await db.commit()
    calls = await staffing.list_cohort_calls(db, cohort_id)
    call_row = next(c for c in calls if c["id"] == call.id)
    return OpenCohortCallResponse(
        call=CohortCallOut(**call_row),
        failed=[BulkActionError(session_id=f["session_id"], detail=f["detail"]) for f in failed],
    )


@router.get("/cohorts/{cohort_id}/staffing/calls", response_model=list[CohortCallOut])
async def list_cohort_calls(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Every standing cohort call, most recent first, each with its target
    users and the grouped sessions' own call/staffing status — the "manage
    it as one cohesive thing" view."""
    return [CohortCallOut(**row) for row in await staffing.list_cohort_calls(db, cohort_id)]


@router.post("/cohorts/{cohort_id}/staffing/calls/{cohort_call_id}/close", response_model=CohortCallOut)
async def close_cohort_call(
    cohort_id: uuid.UUID,
    cohort_call_id: uuid.UUID,
    body: CloseCohortCallRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Closes this cohort call for a chosen subset of its grouped sessions
    (omit `session_ids` to close all of them still open) — the rest, if
    any, keep running. Delegates per-session to the existing single-call
    close, so `clear_interest` and staffing_status resync behave exactly as
    they do for a session-level close."""
    session_ids = list(body.session_ids) if body and body.session_ids else None
    clear_interest = body.clear_interest if body else False
    await staffing.close_cohort_call(
        db, cohort_id, cohort_call_id, session_ids=session_ids, clear_interest=clear_interest,
    )
    await db.commit()
    calls = await staffing.list_cohort_calls(db, cohort_id)
    call_row = next(c for c in calls if c["id"] == cohort_call_id)
    return CohortCallOut(**call_row)


@router.delete("/cohorts/{cohort_id}/staffing/calls/{cohort_call_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cohort_call(
    cohort_id: uuid.UUID,
    cohort_call_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Tidy up a closed cohort call — refused (409) while it's still open."""
    await staffing.delete_cohort_call(db, cohort_id, cohort_call_id)
    await db.commit()


@router.post("/{session_id}/staffing/reopen", response_model=SessionOut)
async def reopen(
    session_id: uuid.UUID,
    body: OpenCallRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Targeting carries over — reopening a call aimed at three instructors
    keeps it aimed at them rather than quietly going public. Send user_ids to
    change the audience, or an empty list to open it to everyone. Same for
    role_ids (B2) — the common case is reopening for just the roles still
    needed."""
    session = await staffing.reopen(
        db, session_id,
        target_user_ids=list(body.user_ids) if body and body.user_ids is not None else None,
        role_ids=list(body.role_ids) if body and body.role_ids else None,
        actor_user_id=current_user.id,
    )
    await db.commit()
    await db.refresh(session)
    return await _session_out(db, session)


class CloseCallRequest(BaseModel):
    clear_interest: bool = False


@router.post("/{session_id}/staffing/close-call", response_model=SessionOut)
async def close_call(
    session_id: uuid.UUID,
    body: CloseCallRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Closes every call currently open on this session at once — the
    original one-button behaviour, kept for the common case. To close just
    one call while leaving others running, use the per-call endpoint below."""
    clear_interest = body.clear_interest if body else False
    session = await staffing.close_all_calls(db, session_id, clear_interest=clear_interest)
    await db.commit()
    await db.refresh(session)
    return await _session_out(db, session)


# ── Ops: individual calls (2026-08-01) ──────────────────────────────────────

@router.get("/{session_id}/staffing/calls", response_model=list[SessionCallOut])
async def list_calls(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Every call on this session, open or closed, most recent first — "view
    open calls public or targeted, edit them or close them" (operator,
    2026-08-01). A session can have several open at once."""
    return [SessionCallOut(**row) for row in await staffing.list_calls(db, session_id)]


@router.post("/{session_id}/staffing/calls/{call_id}/close", response_model=SessionOut)
async def close_one_call(
    session_id: uuid.UUID,
    call_id: uuid.UUID,
    body: CloseCallRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Closes just this one call, leaving any other open calls on the same
    session running. `clear_interest` only actually clears interest once
    this was the last open call — interest gathered under a call still open
    elsewhere on the session isn't touched."""
    clear_interest = body.clear_interest if body else False
    session = await staffing.close_call(db, session_id, call_id, clear_interest=clear_interest)
    await db.commit()
    await db.refresh(session)
    return await _session_out(db, session)


# ── Instructor: available sessions / my sessions ────────────────────────────

@router.get("/available", response_model=list[AvailableSessionOut])
async def list_available_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor_or_facilitator),
):
    rows = await staffing.list_available_sessions(db, current_user)
    out = []
    for s, c, p, count, interest in rows:
        # I5-5: the invite carries the offer, not just the date and place.
        # open_only (B2): a role ops isn't soliciting for right now doesn't
        # appear here, even if the opening row exists.
        openings = await openings_svc.openings_for_session(db, s.id, open_only=True)
        addons = [
            a for a in await openings_svc.addons_for_session(db, s.id)
            if a["user_id"] is None and a["status"] == "agreed"
        ]
        out.append(AvailableSessionOut(
            session_id=s.id, cohort_id=c.id, cohort_name=c.name, program_name=p.name,
            title=s.title,
            location=c.location, meeting_date=s.meeting_date, starts_at=s.starts_at,
            interested_count=count, my_interest=interest is not None,
            my_note=interest.note if interest else None,
            program_type=p.program_type,
            description=p.description,
            location_map_url=c.location_map_url,
            duration_hours=float(await openings_svc.resolve_duration(db, s) or 0) or None,
            openings=[
                OpeningSummary(
                    role_id=o["role_id"], role_name=o["role_name"],
                    role_description=o["role_description"],
                    slots=o["slots"], remaining=o["remaining"],
                    amount_aed=float(o["amount_aed"]) if o["amount_aed"] is not None else None,
                    notes=o["notes"],
                )
                for o in openings
            ],
            addons=[
                AddonSummary(
                    description=a["description"], amount_aed=float(a["amount_aed"]), notes=a["notes"]
                )
                for a in addons
            ],
            responsibilities_accepted=bool(
                interest and interest.responsibilities_accepted_at is not None
            ),
        ))
    return out


@router.get("/mine", response_model=list[MySessionOut])
async def list_my_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor_or_facilitator),
):
    rows = await staffing.list_my_sessions(db, current_user)
    return [
        MySessionOut(
            session_id=s.id, cohort_id=c.id, cohort_name=c.name, program_name=p.name,
            title=s.title,
            location=c.location, meeting_date=s.meeting_date, starts_at=s.starts_at,
            my_role=role, staffing_status=s.staffing_status,
            started_at=s.started_at, completed_at=s.completed_at,
        )
        for s, c, p, role in rows
    ]


# ── Instructor: register / withdraw interest ────────────────────────────────

@router.post("/{session_id}/staffing/interest", response_model=InterestOut, status_code=status.HTTP_201_CREATED)
async def register_interest(
    session_id: uuid.UUID,
    body: RegisterInterestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor_or_facilitator),
):
    interest = await staffing.register_interest(
        db, session_id, current_user, note=body.note, role_id=body.role_id,
    )
    await db.commit()
    role_name = None
    if interest.role_id is not None:
        role_name = await db.scalar(select(DeliveryRole.name).where(DeliveryRole.id == interest.role_id))
    return InterestOut(
        user_id=current_user.id, full_name=current_user.full_name, email=current_user.email,
        note=interest.note, role_id=interest.role_id, role_name=role_name,
        created_at=interest.created_at,
    )


class DeclineAssignmentRequest(BaseModel):
    reason: str | None = None


@router.post("/{session_id}/staffing/decline")
async def decline_assignment(
    session_id: uuid.UUID,
    body: DeclineAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor_or_facilitator),
):
    """Instructor declines an assigned session with an optional excuse reason."""
    si = await db.scalar(
        select(SessionInstructor).where(
            SessionInstructor.session_id == session_id,
            SessionInstructor.user_id == current_user.id,
        )
    )
    if si is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    await db.delete(si)

    session = await db.get(Session, session_id)
    ops_users = (await db.execute(
        select(User).where(User.roles.any("operations") | User.roles.any("admin"))
    )).scalars().all()

    for ops in ops_users:
        await create_notification(
            db, ops.id, "Instructor requested excuse",
            body=f"{current_user.full_name} declined assignment for session on {session.meeting_date if session else 'session'}."
                 + (f" Reason: {body.reason}" if body.reason else ""),
            type="staffing_open_call",
        )

    await db.commit()
    return {"status": "declined"}


@router.delete("/{session_id}/staffing/interest", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw_interest(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor_or_facilitator),
):
    await staffing.withdraw_interest(db, session_id, current_user)
    await db.commit()


# ── Ops: interest list, full eligible roster, select ────────────────────────

@router.get("/{session_id}/staffing/interest", response_model=list[InterestOut])
async def list_interest(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    rows = await staffing.list_interest(db, session_id)
    role_names = dict((await db.execute(select(DeliveryRole.id, DeliveryRole.name))).all())
    return [
        InterestOut(
            user_id=u.id, full_name=u.full_name, email=u.email, note=i.note,
            role_id=i.role_id, role_name=role_names.get(i.role_id) if i.role_id else None,
            created_at=i.created_at,
        )
        for i, u in rows
    ]


@router.get("/{session_id}/staffing/eligible-instructors", response_model=list[EligibleInstructorOut])
async def list_eligible_instructors(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Full instructor|facilitator roster for the ops select screen — not
    interest-only (operator requirement 2026-07-24)."""
    rows = await staffing.list_eligible_instructors(db, session_id)
    return [
        EligibleInstructorOut(
            user_id=u.id, full_name=u.full_name or u.email, email=u.email, photo_url=u.photo_url,
            interested=interest is not None, note=interest.note if interest else None,
            interest_role_id=interest.role_id if interest else None,
            interest_role_name=role_name,
        )
        for u, interest, role_name in rows
    ]


@router.post("/{session_id}/staffing/select", response_model=SelectInstructorsResponse)
async def select_instructors(
    session_id: uuid.UUID,
    body: SelectInstructorsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    assignments, without_interest = await staffing.select_instructors(
        db, session_id, body.user_ids, body.role_id, close_call=body.close_call,
        actor_user_id=current_user.id,
    )

    session = await db.get(Session, session_id)
    cohort = await db.get(Cohort, session.cohort_id) if session else None
    role_names = dict((await db.execute(select(DeliveryRole.id, DeliveryRole.name))).all())
    for assignment in assignments:
        await create_notification(
            db, assignment.user_id, "You've been assigned to a session",
            body=f"You're assigned ({role_names.get(assignment.role_id, 'instructor')}) "
                 f"to a session on {session.meeting_date}"
                 + (f" at {cohort.location}." if cohort and cohort.location else "."),
            type="staffing_assigned",
        )
        await safe_enqueue(arq_redis, "send_assignment_email", str(session_id), str(assignment.user_id))

    await db.commit()
    return SelectInstructorsResponse(assigned=[a.user_id for a in assignments], without_interest=without_interest)
