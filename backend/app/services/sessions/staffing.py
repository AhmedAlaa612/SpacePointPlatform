"""Staffing marketplace (V2 W4, S4-1).

Session-scoped, not cohort-scoped (operator decision 2026-07-24, see
MASTER_EXECUTION_PLAN_V2.md's W4 discoveries entry) — the CEO's own
description was "a session is made available... instructors register
interest... someone selects among them", and assignment itself (via
SessionInstructor) is already per-session, not per-cohort. A cohort with
several sessions can be partly staffed; there is no cohort-level staffing
state to track.

This is layered on top of the direct-assign path that already existed
before W4 (routers/sessions/cohorts.py's assign_instructor/unassign_instructor,
built in R2-3) — that path is untouched and still works exactly as it did,
for ops who just want to assign someone without running an open call.
select_instructors below is the marketplace's "confirm" step; it writes to
the same SessionInstructor table.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.inventory.city import City
from app.models.inventory.location import Location
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_call import CohortCall, CohortCallTarget
from app.models.sessions.cohort_opening import CohortOpening
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.instructor_interest import InstructorInterest
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionCallTarget, SessionInstructor
from app.models.sessions.session_call import SessionCall
from app.models.sessions.opening import SessionOpening
from app.services.sessions.openings import fully_staffed, lead_role_id, set_openings_open
from app.models.spine.touchpoint import Touchpoint
from app.models.user import User

# D-open-1 default (V2 §C, unanswered by the CEO — this is the fallback the
# plan says to use until it is): who can open a call / select instructors.
STAFFING_SELECTOR_ROLES = ["admin", "operations"]


async def _write_touchpoint(db: AsyncSession, user: User, raw_platform_id: str) -> None:
    """Best-effort — a user only has a linked contact once they've been
    through ensure_user_contact (see services/spine/identity.py), which
    every user eventually is, but this must never block a staffing action
    on that timing."""
    if user.contact_id is None:
        return
    db.add(Touchpoint(
        id=uuid4(), contact_id=user.contact_id, channel="system",
        touchpoint_type="staffing", occurred_at=datetime.now(timezone.utc),
        raw_platform_id=raw_platform_id,
    ))
    await db.flush()


async def _get_session(db: AsyncSession, session_id: UUID) -> Session:
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


async def call_target_ids(db: AsyncSession, session_id: UUID) -> list[UUID]:
    """The session's *effective* restriction right now (2026-08-01): if any
    currently-open call has no targets, the session is public regardless of
    what other open calls target — same "absent means unrestricted" contract
    every existing caller (register_interest's gate, `_session_out`'s
    "Targeted" badge) already relies on, now resolved across possibly several
    open calls instead of one flat list."""
    open_calls = (await db.execute(
        select(SessionCall.id).where(SessionCall.session_id == session_id, SessionCall.status == "open")
    )).scalars().all()
    if not open_calls:
        return []

    targeted_call_ids = set((await db.execute(
        select(SessionCallTarget.call_id).where(SessionCallTarget.call_id.in_(open_calls)).distinct()
    )).scalars().all())
    if any(cid not in targeted_call_ids for cid in open_calls):
        return []  # at least one open call is public — the session is public

    return list((await db.execute(
        select(SessionCallTarget.user_id.distinct()).where(SessionCallTarget.call_id.in_(open_calls))
    )).scalars().all())


async def list_calls(db: AsyncSession, session_id: UUID) -> list[dict]:
    """Every call ever opened on this session, most recent first — the "view
    open calls, public or targeted, edit them or close them" ask (2026-08-01).
    Ops manages each independently rather than the session having exactly one
    call state."""
    calls = (await db.execute(
        select(SessionCall).where(SessionCall.session_id == session_id).order_by(SessionCall.created_at.desc())
    )).scalars().all()
    if not calls:
        return []
    targets = (await db.execute(
        select(SessionCallTarget.call_id, SessionCallTarget.user_id)
        .where(SessionCallTarget.call_id.in_([c.id for c in calls]))
    )).all()
    by_call: dict[UUID, list[UUID]] = {}
    for call_id, user_id in targets:
        by_call.setdefault(call_id, []).append(user_id)
    return [
        {
            "id": c.id, "session_id": c.session_id, "status": c.status, "label": c.label,
            "target_user_ids": by_call.get(c.id, []),
            "created_at": c.created_at, "closed_at": c.closed_at,
        }
        for c in calls
    ]


async def _create_call(
    db: AsyncSession, *, session_id: UUID, target_user_ids: list[UUID] | None,
    actor_user_id: UUID | None, label: str | None = None,
    cohort_call_id: UUID | None = None,
) -> SessionCall:
    """One call — public if `target_user_ids` is empty/None, targeted
    otherwise. Never touches any other call already open on this session;
    that's the whole point (2026-08-01) — a public call and a targeted call
    can run side by side, each closed independently.

    `cohort_call_id` (2026-08-01) is purely a grouping label for a standing
    `CohortCall` this session's call happens to belong to — omit it (the
    default) for a call opened directly on the session, independent of any
    cohort call."""
    call = SessionCall(
        id=uuid4(), session_id=session_id, status="open", label=label, created_by=actor_user_id,
        cohort_call_id=cohort_call_id,
    )
    db.add(call)
    await db.flush()
    for user_id in dict.fromkeys(target_user_ids or []):  # de-dupe, keep order
        db.add(SessionCallTarget(id=uuid4(), call_id=call.id, session_id=session_id, user_id=user_id))
    await db.flush()
    return call


async def set_call_targets(db: AsyncSession, session_id: UUID, target_user_ids: list[UUID]) -> Session:
    """Sets or replaces call targets for open calls on a session."""
    open_calls = (await db.execute(
        select(SessionCall).where(SessionCall.session_id == session_id, SessionCall.status == "open")
    )).scalars().all()
    if not open_calls:
        await _create_call(db, session_id=session_id, target_user_ids=target_user_ids, actor_user_id=None)
    else:
        for call in open_calls:
            await db.execute(delete(SessionCallTarget).where(SessionCallTarget.call_id == call.id))
            for uid in dict.fromkeys(target_user_ids or []):
                db.add(SessionCallTarget(id=uuid4(), call_id=call.id, session_id=session_id, user_id=uid))
    await db.flush()
    return await _get_session(db, session_id)


async def open_call(
    db: AsyncSession, session_id: UUID, target_user_ids: list[UUID] | None = None,
    role_ids: list[UUID] | None = None, actor_user_id: UUID | None = None, label: str | None = None,
    cohort_call_id: UUID | None = None,
) -> Session:
    """Opens a new call on this session (2026-08-01: session can carry
    several at once — a public one and a targeted one, or several targeted
    ones for different missing roles, all live together). `target_user_ids`
    restricts *this* call to those instructors; omit it (or pass an empty
    list) for a call open to every instructor/facilitator. Refused only once
    the session is `staffed` — every opening already filled is when
    `reopen()` is the right call instead, since that's explicitly "we need
    more after all."

    `role_ids` (B2) restricts which of the session's openings are on offer —
    "we still need 2 Assistants" without touching who can see it. Omit it to
    open every configured opening, today's exact behaviour.

    `cohort_call_id` (2026-08-01) tags the new call as belonging to a
    standing `CohortCall` — used internally by `open_cohort_call`. Every
    existing caller omits it, unaffected."""
    session = await _get_session(db, session_id)
    if session.staffing_status == "staffed":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Session is already staffed — use reopen instead")
    session.staffing_status = "open_call"
    await _create_call(
        db, session_id=session_id, target_user_ids=target_user_ids, actor_user_id=actor_user_id, label=label,
        cohort_call_id=cohort_call_id,
    )
    await set_openings_open(db, session_id=session_id, role_ids=role_ids)
    await db.flush()
    return session


async def open_call_for_cohort(
    db: AsyncSession, cohort_id: UUID, target_user_ids: list[UUID] | None = None,
    actor_user_id: UUID | None = None,
) -> list[Session]:
    """Bulk convenience for a multi-session cohort — opens every session
    that's still unstaffed. Sessions already open_call or staffed are left
    exactly as they are, not treated as an error."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    sessions = (await db.execute(
        select(Session).where(Session.cohort_id == cohort_id, Session.staffing_status == "unstaffed")
    )).scalars().all()
    for session in sessions:
        session.staffing_status = "open_call"
        await _create_call(db, session_id=session.id, target_user_ids=target_user_ids, actor_user_id=actor_user_id)
    await db.flush()
    return list(sessions)


# ── Cohort-level calls (2026-08-01) ─────────────────────────────────────────
# A standing grouping over a chosen subset of a cohort's sessions' own
# SessionCall rows — see CohortCall's docstring. Distinct from
# open_call_for_cohort above, which stays exactly as it is (an ungrouped bulk
# convenience with no way to view/close what it opened as one thing).

async def _sync_cohort_call_status(db: AsyncSession, call: CohortCall) -> None:
    """Recompute the cohort call's summary from its grouped SessionCall rows
    — "open" while at least one is still open, else "closed" — the same
    derived-from-children pattern as `_sync_staffing_status` above. Called
    after anything that might have closed one of them."""
    still_open = await db.scalar(
        select(func.count()).select_from(SessionCall)
        .where(SessionCall.cohort_call_id == call.id, SessionCall.status == "open")
    )
    if still_open:
        call.status = "open"
        call.closed_at = None
    else:
        call.status = "closed"
        call.closed_at = datetime.now(timezone.utc)


async def open_cohort_call(
    db: AsyncSession, cohort_id: UUID, *,
    session_ids: list[UUID] | None = None,
    target_user_ids: list[UUID] | None = None,
    role_ids: list[UUID] | None = None,
    actor_user_id: UUID | None = None,
    label: str | None = None,
) -> tuple[CohortCall, list[UUID], list[dict]]:
    """Opens one standing call across a *chosen subset* of a cohort's
    sessions (operator ask, 2026-08-01) — `session_ids` omitted falls back
    to `open_call_for_cohort`'s existing default (every currently-unstaffed
    session in the cohort), so "open call for the whole cohort" still means
    the same thing it always did. Given explicit `session_ids`, anything not
    actually belonging to this cohort is reported failed rather than
    silently skipped or erroring the whole batch.

    Each resolved session gets its own independent `open_call`, tagged with
    this new `CohortCall`'s id — partial failure (e.g. a listed session
    that's already staffed) doesn't roll back the rest, same
    tolerate-and-report contract `bulk_open_call` (routers/sessions/
    cohorts.py) already established for the ungrouped bulk path."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    call = CohortCall(id=uuid4(), cohort_id=cohort_id, status="open", label=label, created_by=actor_user_id)
    db.add(call)
    await db.flush()
    for user_id in dict.fromkeys(target_user_ids or []):  # de-dupe, keep order
        db.add(CohortCallTarget(id=uuid4(), cohort_call_id=call.id, cohort_id=cohort_id, user_id=user_id))
    await db.flush()

    failed: list[dict] = []
    if session_ids is not None:
        wanted = list(dict.fromkeys(session_ids))  # de-dupe, keep order
        found = {
            s.id: s for s in (await db.execute(
                select(Session).where(Session.cohort_id == cohort_id, Session.id.in_(wanted))
            )).scalars().all()
        }
        sessions = []
        for sid in wanted:
            if sid in found:
                sessions.append(found[sid])
            else:
                failed.append({"session_id": sid, "detail": "Session not found in this cohort"})
    else:
        sessions = list((await db.execute(
            select(Session).where(Session.cohort_id == cohort_id, Session.staffing_status == "unstaffed")
        )).scalars().all())

    succeeded: list[UUID] = []
    for session in sessions:
        try:
            await open_call(
                db, session.id, target_user_ids=target_user_ids, role_ids=role_ids,
                actor_user_id=actor_user_id, cohort_call_id=call.id,
            )
            succeeded.append(session.id)
        except HTTPException as exc:
            failed.append({"session_id": session.id, "detail": str(exc.detail)})

    await db.flush()
    return call, succeeded, failed


async def list_cohort_calls(db: AsyncSession, cohort_id: UUID) -> list[dict]:
    """Every CohortCall opened on this cohort, most recent first, each with
    its target users and the grouped sessions' own call status/staffing
    status — the "view it and manage it as one thing" half of the ask."""
    calls = (await db.execute(
        select(CohortCall).where(CohortCall.cohort_id == cohort_id).order_by(CohortCall.created_at.desc())
    )).scalars().all()
    if not calls:
        return []
    call_ids = [c.id for c in calls]

    targets = (await db.execute(
        select(CohortCallTarget.cohort_call_id, CohortCallTarget.user_id)
        .where(CohortCallTarget.cohort_call_id.in_(call_ids))
    )).all()
    targets_by_call: dict[UUID, list[UUID]] = {}
    for call_id, user_id in targets:
        targets_by_call.setdefault(call_id, []).append(user_id)

    rows = (await db.execute(
        select(SessionCall, Session)
        .join(Session, Session.id == SessionCall.session_id)
        .where(SessionCall.cohort_call_id.in_(call_ids))
        .order_by(Session.meeting_date.asc())
    )).all()
    sessions_by_call: dict[UUID, list[dict]] = {}
    for sc, session in rows:
        sessions_by_call.setdefault(sc.cohort_call_id, []).append({
            "session_id": session.id,
            "meeting_date": session.meeting_date,
            "starts_at": session.starts_at,
            "status": sc.status,
            "staffing_status": session.staffing_status,
        })

    return [
        {
            "id": c.id, "cohort_id": c.cohort_id, "status": c.status, "label": c.label,
            "target_user_ids": targets_by_call.get(c.id, []),
            "sessions": sessions_by_call.get(c.id, []),
            "created_at": c.created_at, "closed_at": c.closed_at,
        }
        for c in calls
    ]


async def close_cohort_call(
    db: AsyncSession, cohort_id: UUID, cohort_call_id: UUID, *,
    session_ids: list[UUID] | None = None, clear_interest: bool = False,
) -> CohortCall:
    """Closes this cohort call for a chosen subset of its grouped sessions
    (omit `session_ids` to close all of them) — the other half of the ask:
    close it for some sessions while the rest stay open. Delegates to the
    existing `close_call` per session rather than duplicating its close
    logic (interest-clearing, staffing_status resync), then recomputes this
    CohortCall's own derived status from what's left open."""
    call = await db.get(CohortCall, cohort_call_id)
    if call is None or call.cohort_id != cohort_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort call not found")

    query = select(SessionCall).where(SessionCall.cohort_call_id == cohort_call_id, SessionCall.status == "open")
    if session_ids:
        query = query.where(SessionCall.session_id.in_(session_ids))
    open_calls = (await db.execute(query)).scalars().all()

    for sc in open_calls:
        await close_call(db, sc.session_id, sc.id, clear_interest=clear_interest)

    await _sync_cohort_call_status(db, call)
    await db.flush()
    return call


async def delete_cohort_call(db: AsyncSession, cohort_id: UUID, cohort_call_id: UUID) -> None:
    """Removes a closed CohortCall entirely — the grouping record only, not
    the sessions or their staffing history. `SessionCall.cohort_call_id` is
    ON DELETE SET NULL (see the model), so the underlying per-session calls
    just lose their grouping label; `CohortCallTarget` rows cascade-delete.
    Refused while still open — closing is the well-defined way to end a live
    call, deleting is only for tidying up ones that are already done."""
    call = await db.get(CohortCall, cohort_call_id)
    if call is None or call.cohort_id != cohort_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort call not found")
    if call.status != "closed":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Close this call before deleting it")

    await db.delete(call)
    await db.flush()


async def _sync_staffing_status(db: AsyncSession, session: Session) -> None:
    """Recompute the session-wide summary from its calls/openings — "staffed"
    if every opening is filled, else "open_call" if any call is still open,
    else "unstaffed". Called after anything that might have changed either."""
    if await fully_staffed(db, session.id):
        session.staffing_status = "staffed"
    else:
        still_open = await db.scalar(
            select(func.count()).select_from(SessionCall)
            .where(SessionCall.session_id == session.id, SessionCall.status == "open")
        )
        session.staffing_status = "open_call" if still_open else "unstaffed"


async def close_call(
    db: AsyncSession, session_id: UUID, call_id: UUID, clear_interest: bool = False,
) -> Session:
    """Closes one specific call (2026-08-01) — a session with several calls
    open keeps the others running. `clear_interest` (Abort) only actually
    clears the session's interest once this was the *last* open call: interest
    gathered under a call that's still open elsewhere on the same session is
    real and shouldn't vanish because a different call closed."""
    session = await _get_session(db, session_id)
    call = await db.get(SessionCall, call_id)
    if call is None or call.session_id != session_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Call not found")
    if call.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="That call is already closed")

    call.status = "closed"
    call.closed_at = datetime.now(timezone.utc)
    await db.flush()

    other_open = await db.scalar(
        select(func.count()).select_from(SessionCall)
        .where(SessionCall.session_id == session_id, SessionCall.status == "open")
    )
    if clear_interest and not other_open:
        await db.execute(
            delete(InstructorInterest).where(InstructorInterest.session_id == session_id)
        )

    await _sync_staffing_status(db, session)
    await db.flush()
    return session


async def close_all_calls(db: AsyncSession, session_id: UUID, clear_interest: bool = False) -> Session:
    """The single "Close Call" button's behaviour from before multiple calls
    existed — closes everything currently open on this session at once."""
    session = await _get_session(db, session_id)
    open_calls = (await db.execute(
        select(SessionCall).where(SessionCall.session_id == session_id, SessionCall.status == "open")
    )).scalars().all()

    now = datetime.now(timezone.utc)
    for call in open_calls:
        call.status = "closed"
        call.closed_at = now
    if clear_interest:
        await db.execute(
            delete(InstructorInterest).where(InstructorInterest.session_id == session_id)
        )
    await _sync_staffing_status(db, session)
    await db.flush()
    return session


async def reopen(
    db: AsyncSession, session_id: UUID, target_user_ids: list[UUID] | None = None,
    role_ids: list[UUID] | None = None, actor_user_id: UUID | None = None,
) -> Session:
    """staffed -> open_call: opens a fresh call once every opening was
    filled and ops decides more are needed after all (someone dropped out,
    a new role was added). Explicit and separate from removing an
    instructor — reopening never removes anyone already assigned; that's
    remove_instructor's job, called on its own.

    Targeting carries over by default: reopening after a call that was aimed
    at three specific instructors targets the same three again, rather than
    silently going public. Pass `target_user_ids` to change it, or `[]` to
    open it to everyone. Since `staffed` means every call closed, "the
    previous call" is unambiguous — the most recently closed one.

    `role_ids` (B2) is the main real-world use of role-scoping: reopening
    for "just the 2 Assistants still needed" is how that actually happens in
    practice. Omit it to reopen every configured opening."""
    session = await _get_session(db, session_id)
    if session.staffing_status != "staffed":
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Session is {session.staffing_status}, not staffed")

    if target_user_ids is None:
        last_call_id = await db.scalar(
            select(SessionCall.id).where(SessionCall.session_id == session_id, SessionCall.status == "closed")
            .order_by(SessionCall.closed_at.desc()).limit(1)
        )
        target_user_ids = list((await db.execute(
            select(SessionCallTarget.user_id).where(SessionCallTarget.call_id == last_call_id)
        )).scalars().all()) if last_call_id else []

    session.staffing_status = "open_call"
    await _create_call(db, session_id=session_id, target_user_ids=target_user_ids, actor_user_id=actor_user_id)
    await set_openings_open(db, session_id=session_id, role_ids=role_ids)
    await db.flush()
    return session


async def list_available_sessions(
    db: AsyncSession, user: User,
) -> list[tuple[Session, Cohort, Program, int, InstructorInterest | None]]:
    """Every open-call session, cohort/program joined in for display, plus
    an interest count and this user's own interest row (if any) — the S4-3
    "Available sessions" instructor page."""
    # A session can have several calls open at once (2026-08-01) — it's
    # visible if ANY open call has no targets (public), or if the user is
    # specifically targeted by ANY open call. A targeted call running
    # alongside a public one doesn't take the public one's reach away.
    open_public_call = (
        select(SessionCall.id)
        .outerjoin(SessionCallTarget, SessionCallTarget.call_id == SessionCall.id)
        .where(
            SessionCall.session_id == Session.id, SessionCall.status == "open",
            SessionCallTarget.id.is_(None),
        )
    ).exists()
    i_am_targeted = (
        select(SessionCallTarget.id)
        .join(SessionCall, SessionCall.id == SessionCallTarget.call_id)
        .where(
            SessionCall.session_id == Session.id, SessionCall.status == "open",
            SessionCallTarget.user_id == user.id,
        )
    ).exists()

    has_no_calls = ~(
        select(SessionCall.id)
        .where(SessionCall.session_id == Session.id)
    ).exists()

    rows = (await db.execute(
        select(Session, Cohort, Program)
        .join(Cohort, Cohort.id == Session.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
        .where(Session.staffing_status == "open_call", or_(open_public_call, i_am_targeted, has_no_calls))
        .order_by(Session.meeting_date.asc())
    )).all()
    session_ids = [s.id for s, _, _ in rows]
    if not session_ids:
        return []

    counts = dict((await db.execute(
        select(InstructorInterest.session_id, func.count())
        .where(InstructorInterest.session_id.in_(session_ids))
        .group_by(InstructorInterest.session_id)
    )).all())
    my_interests = {
        i.session_id: i for i in (await db.execute(
            select(InstructorInterest).where(
                InstructorInterest.session_id.in_(session_ids), InstructorInterest.user_id == user.id,
            )
        )).scalars().all()
    }
    return [(s, c, p, counts.get(s.id, 0), my_interests.get(s.id)) for s, c, p in rows]


async def list_my_sessions(db: AsyncSession, user: User) -> list[tuple[Session, Cohort, Program, str]]:
    """Every session this user is assigned to (via either the marketplace's
    select_instructors or the pre-existing direct-assign path — both write
    the same SessionInstructor row) — the S4-3 "My sessions" instructor page."""
    rows = (await db.execute(
        select(Session, Cohort, Program, DeliveryRole.name)
        .join(Cohort, Cohort.id == Session.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
        .join(SessionInstructor, SessionInstructor.session_id == Session.id)
        .join(DeliveryRole, DeliveryRole.id == SessionInstructor.role_id)
        .where(SessionInstructor.user_id == user.id)
        .order_by(Session.meeting_date.asc())
    )).all()
    return [(s, c, p, role) for s, c, p, role in rows]


async def register_interest(
    db: AsyncSession, session_id: UUID, user: User, note: str | None = None,
    role_id: UUID | None = None,
) -> InstructorInterest:
    session = await _get_session(db, session_id)
    if session.staffing_status != "open_call":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This session isn't open for interest right now")
    if not any(r in user.role_values for r in ("instructor", "facilitator")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only instructors or facilitators can register interest")

    # A targeted call is a real restriction, not just a narrower notification
    # list (operator, 2026-07-26). 404 rather than 403 so an untargeted
    # instructor can't probe which sessions exist — the same don't-leak-existence
    # convention the delivery routes follow.
    targets = await call_target_ids(db, session_id)
    if targets and user.id not in targets:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    # B1: applying for a specific role. It has to be one this session is
    # actually soliciting for right now — an opening that exists but is
    # closed (B2), or that never existed, isn't a valid choice.
    if role_id is not None:
        session_openings = (await db.execute(
            select(SessionOpening).where(SessionOpening.session_id == session_id)
        )).scalars().all()
        if session_openings:
            opening = next((o for o in session_openings if o.role_id == role_id), None)
            if opening is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="That role isn't offered on this session")
            if not opening.is_open:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="That role isn't currently open for interest")
        else:
            cohort_opening = (await db.execute(
                select(CohortOpening).where(
                    CohortOpening.cohort_id == session.cohort_id,
                    CohortOpening.role_id == role_id,
                )
            )).scalars().first()
            if cohort_opening is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="That role isn't offered on this session")

    existing = (await db.execute(
        select(InstructorInterest).where(
            InstructorInterest.session_id == session_id, InstructorInterest.user_id == user.id,
        )
    )).scalars().first()
    if existing is not None:
        if note is not None:
            existing.note = note
        if role_id is not None:
            existing.role_id = role_id
        await db.flush()
        return existing

    interest = InstructorInterest(id=uuid4(), session_id=session_id, user_id=user.id, note=note, role_id=role_id)
    db.add(interest)
    await db.flush()
    return interest


async def withdraw_interest(db: AsyncSession, session_id: UUID, user: User) -> None:
    interest = (await db.execute(
        select(InstructorInterest).where(
            InstructorInterest.session_id == session_id, InstructorInterest.user_id == user.id,
        )
    )).scalars().first()
    if interest is not None:
        await db.delete(interest)
        await db.flush()


async def list_interest(db: AsyncSession, session_id: UUID) -> list[tuple[InstructorInterest, User]]:
    rows = (await db.execute(
        select(InstructorInterest, User)
        .join(User, User.id == InstructorInterest.user_id)
        .where(InstructorInterest.session_id == session_id)
        .order_by(InstructorInterest.created_at.asc())
    )).all()
    return [(interest, u) for interest, u in rows]


async def _resolve_session_city_id(db: AsyncSession, session: Session) -> UUID | None:
    """Same nullable-override pattern as `_resolve_effective_warehouse`
    (routers/sessions/cohorts.py) — a session's own `location_id` wins,
    else fall back to its cohort's. Simpler here: no multiplicity to
    disambiguate, a location has at most one city."""
    location_id = session.location_id
    if location_id is None:
        cohort = await db.get(Cohort, session.cohort_id)
        location_id = cohort.location_id if cohort else None
    if location_id is None:
        return None
    location = await db.get(Location, location_id)
    return location.city_id if location else None


async def resolve_session_location_display(
    db: AsyncSession, session: Session | None = None, cohort: Cohort | None = None,
) -> dict[str, str | None]:
    """Full resolved "where is this" for a session (or a cohort alone —
    tickets have no session row), for every instructor- and student-facing
    surface: name, address, city, country, and the maps link.

    Same nullable-override pattern as `_resolve_session_city_id`: the
    session's own `location_id` wins, else the cohort's, resolved against
    the canonical `Location` row — the legacy free-text
    `cohort.location`/`cohort.location_map_url` fields are the *last-
    resort* fallback for pre-migration cohorts that never got a
    `location_id`.

    **This is the only place in the codebase allowed to read those two
    legacy columns.** Every display/email/notification call site calls this
    instead of touching `cohort.location` itself — see Phase 2 of the
    location-model cleanup. The one deliberate exception is
    `public_catalog` (routers/sessions/public.py), which batch-fetches
    `Location` rows across many cohorts to avoid an N+1; it reimplements
    the same resolution inline and must not be "fixed" into a per-row loop.
    """
    location_id = (session.location_id if session else None) or (cohort.location_id if cohort else None)
    location = await db.get(Location, location_id) if location_id else None
    city = await db.get(City, location.city_id) if location and location.city_id else None
    return {
        "name": (location.name if location else None) or (cohort.location if cohort else None),
        "address": location.address if location else None,
        "city_name": city.name if city else None,
        "country": city.country if city else None,
        "maps_url": (location.maps_url if location else None) or (cohort.location_map_url if cohort else None),
    }


async def list_eligible_instructors(
    db: AsyncSession, session_id: UUID,
) -> list[tuple[User, InstructorInterest | None, str | None, bool]]:
    """Every instructor|facilitator user, paired with their interest row (if
    any), the name of the role they applied for (B1), and whether they
    marked the session's city as somewhere they're open to work
    (2026-08-08) — the full pickable roster for the ops select screen
    (operator requirement 2026-07-24: "ops can pick from the instructors
    list ... multiple ... select all", not just whoever registered
    interest). list_interest above stays interest-only; this is the
    superset."""
    session = await _get_session(db, session_id)  # 404 if the session doesn't exist
    session_city_id = await _resolve_session_city_id(db, session)

    users = (await db.execute(
        select(User)
        .where(User.roles.any("instructor") | User.roles.any("facilitator"))
        .order_by(User.full_name.asc())
    )).scalars().all()
    interests = {
        i.user_id: i for i in (await db.execute(
            select(InstructorInterest).where(InstructorInterest.session_id == session_id)
        )).scalars().all()
    }
    role_names = dict((await db.execute(select(DeliveryRole.id, DeliveryRole.name))).all())

    deliver_city_ids_by_user: dict[UUID, list[UUID]] = {}
    if session_city_id is not None:
        profiles = (await db.execute(
            select(ApplicantProfile.user_id, ApplicantProfile.deliver_city_ids)
            .where(ApplicantProfile.deliver_city_ids.isnot(None))
        )).all()
        deliver_city_ids_by_user = {user_id: city_ids for user_id, city_ids in profiles}

    return [
        (
            u,
            interests.get(u.id),
            role_names.get(interests[u.id].role_id) if u.id in interests and interests[u.id].role_id else None,
            session_city_id is not None and session_city_id in deliver_city_ids_by_user.get(u.id, []),
        )
        for u in users
    ]


async def select_instructors(
    db: AsyncSession, session_id: UUID, user_ids: list[UUID], role_id: UUID | None = None,
    close_call: bool = True, actor_user_id: UUID | None = None,
) -> tuple[list[SessionInstructor], list[UUID]]:
    """The marketplace's confirm step — writes SessionInstructor (same table
    the pre-existing direct-assign path uses). Returns (assignments,
    user_ids_without_interest) so the caller can surface an ops override
    rather than block it — mandatory per S4-1's spec: selecting someone who
    never registered interest is allowed, just flagged in the response.

    `close_call=False` keeps staffing_status at open_call so ops can pick
    people out of the interest list incrementally — assigning one instructor
    used to close the call unconditionally, which stopped everyone else from
    registering interest even when more were still wanted (operator, 2026-07-26).
    Assignments themselves are unaffected either way: this only controls
    whether the session stays open to new interest."""
    session = await _get_session(db, session_id)
    if not user_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Select at least one instructor")

    # I5-3: roles are data. Omitted means the most senior one, which is what
    # the old `role="lead"` default meant before roles were configurable.
    if role_id is None:
        role_id = await lead_role_id(db)
        if role_id is None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="No delivery roles are configured")
    elif await db.get(DeliveryRole, role_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Delivery role not found")

    interested_ids = set((await db.execute(
        select(InstructorInterest.user_id).where(InstructorInterest.session_id == session_id)
    )).scalars().all())
    without_interest = [uid for uid in user_ids if uid not in interested_ids]

    assignments: list[SessionInstructor] = []
    for user_id in user_ids:
        selected_user = await db.get(User, user_id)
        if selected_user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"User {user_id} not found")

        existing = (await db.execute(
            select(SessionInstructor).where(
                SessionInstructor.session_id == session_id, SessionInstructor.user_id == user_id,
            )
        )).scalars().first()
        if existing is not None:
            existing.role_id = role_id
            assignments.append(existing)
        else:
            assignment = SessionInstructor(id=uuid4(), session_id=session_id, user_id=user_id, role_id=role_id)
            db.add(assignment)
            assignments.append(assignment)
            await _write_touchpoint(db, selected_user, f"session_assigned:{session_id}:{user_id}")

    await db.flush()
    if close_call:
        # I5-4: "staffed" now means every opening is filled. A session with no
        # openings falls back to "somebody is assigned", so everything created
        # before openings existed behaves exactly as it did. Reaching "staffed"
        # closes every call still open on this session — there's nothing left
        # for any of them to solicit (2026-08-01).
        if await fully_staffed(db, session_id):
            session.staffing_status = "staffed"
            await db.execute(
                SessionCall.__table__.update()
                .where(SessionCall.session_id == session_id, SessionCall.status == "open")
                .values(status="closed", closed_at=datetime.now(timezone.utc))
            )
        else:
            session.staffing_status = "open_call"
    await db.flush()
    return assignments, without_interest


async def remove_instructor(db: AsyncSession, session_id: UUID, user_id: UUID) -> None:
    assignment = (await db.execute(
        select(SessionInstructor).where(
            SessionInstructor.session_id == session_id, SessionInstructor.user_id == user_id,
        )
    )).scalars().first()
    if assignment is not None:
        await db.delete(assignment)
        await db.flush()
