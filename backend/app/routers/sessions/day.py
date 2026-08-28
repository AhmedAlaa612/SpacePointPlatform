"""Instructor daily loop routes (operations process doc §4-§12).

    POST   /sessions/{id}/delivery/check-in                 instructor or ops
    GET    /sessions/{id}/delivery/day                      instructor or ops
    PUT    /sessions/{id}/delivery/checklist/{item_id}      instructor or ops
    POST   /sessions/{id}/delivery/day/submit               instructor or ops
    GET    /sessions/day-reviews                            ops
    POST   /sessions/day-reviews/{day_id}/approve           ops
    POST   /sessions/day-reviews/{day_id}/return            ops
    GET/PUT /sessions/{scope}/{id}/checklist-items          ops

The instructor-side routes use `require_session_delivery` (instructor,
facilitator or operations) and the service enforces assignment itself through
`_get_deliverable_session` — 404 rather than 403 for someone unassigned, the
same don't-leak-existence convention as `delivery.py` and `checkin.py`.

Approving a day is also where cohort auto-completion is checked, because an
approval is the only event that can make a cohort fully reviewed.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations, require_session_delivery
from app.db.session import get_db
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.user import User
from app.schemas.sessions.day import (
    ChecklistItemOut,
    CheckInIn,
    ChecklistProgressIn,
    DayActionOut,
    DayDetailOut,
    DayReviewOut,
    ReturnDayIn,
    SessionBoardOut,
    SetChecklistItemsIn,
    SubmitDayIn,
)
from app.services.notification import create_notification
from app.services.sessions import day as svc

router = APIRouter(prefix="/sessions", tags=["sessions-day"])


# ── ops: checklist templates ────────────────────────────────────────────────

_SCOPES = {"programs": "program_id", "cohorts": "cohort_id", "sessions": "session_id"}


def _scope_kwarg(scope: str, owner_id: uuid.UUID) -> dict:
    if scope not in _SCOPES:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="A checklist belongs to a program, a cohort or a session",
        )
    return {_SCOPES[scope]: owner_id}


@router.get("/{scope}/{owner_id}/checklist-items", response_model=list[ChecklistItemOut])
async def list_checklist_items(
    scope: str,
    owner_id: uuid.UUID,
    role_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    """One (level, role) bucket — the management view, no inheritance applied.
    Omit `role_id` for the general bucket; pass a role to edit that role's own
    list. Use the instructor's day endpoint to see what actually resolves."""
    return await svc.list_checklist_items(db, role_id=role_id, **_scope_kwarg(scope, owner_id))


@router.put("/{scope}/{owner_id}/checklist-items", response_model=list[ChecklistItemOut])
async def set_checklist_items(
    scope: str,
    owner_id: uuid.UUID,
    body: SetChecklistItemsIn,
    role_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Replace one (level, role) bucket. Saving an empty list clears it, which
    makes the next fallback apply again — general at this level if a role's
    list is cleared, or the next level up if the general one is cleared. That
    is how you go back to inheriting rather than overriding."""
    items = await svc.set_checklist_items(
        db, lines=[i.model_dump() for i in body.items], actor_user_id=current_user.id, role_id=role_id,
        **_scope_kwarg(scope, owner_id),
    )
    await db.commit()
    return items


# ── instructor: the day ─────────────────────────────────────────────────────

@router.get("/{session_id}/delivery/day", response_model=DayDetailOut)
async def get_day(
    session_id: uuid.UUID,
    for_user_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """This instructor's day on this session, with the resolved checklist.

    `for_user_id` lets ops open somebody else's day from the review queue; an
    instructor passing it for another user gets their own day back unless they
    are ops, because `_get_deliverable_session` has already established what
    they may see.
    """
    is_ops = "operations" in current_user.role_values or "admin" in current_user.role_values
    return await svc.get_day_detail(
        db, session_id, current_user, for_user_id=for_user_id if is_ops else None
    )


@router.post("/{session_id}/delivery/check-in", response_model=DayDetailOut)
async def check_in(
    session_id: uuid.UUID,
    body: CheckInIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """"I'm here" / "I can't attend today" (§4) — recorded day by day, never
    inferred from the cohort assignment."""
    await svc.check_in(db, session_id, current_user, att_status=body.att_status, reason=body.reason)
    await db.commit()
    return await svc.get_day_detail(db, session_id, current_user)


@router.put("/{session_id}/delivery/checklist/{item_id}", response_model=DayDetailOut)
async def set_checklist_progress(
    session_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ChecklistProgressIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Tick an item, attach proof, or both. Proof is a `session_reports` row
    id — upload through the existing report endpoint first, then point here."""
    await svc.set_checklist_progress(
        db, session_id, current_user, checklist_item_id=item_id,
        is_done=body.is_done, proof_report_id=body.proof_report_id, note=body.note,
    )
    await db.commit()
    return await svc.get_day_detail(db, session_id, current_user)


@router.post("/{session_id}/delivery/day/submit", response_model=DayDetailOut)
async def submit_day(
    session_id: uuid.UUID,
    body: SubmitDayIn | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Send the day for ops review (§11). 409s listing everything outstanding
    if a required item isn't ticked or a proof-required one has no file."""
    await svc.submit_day(db, session_id, current_user, notes=body.notes if body else None)

    session = await db.get(Session, session_id)
    cohort = await db.get(Cohort, session.cohort_id) if session else None
    ops_users = await _ops_users(db)
    for ops in ops_users:
        await create_notification(
            db, ops.id, "A workshop day is ready for review",
            body=f"{current_user.full_name} submitted "
                 f"{session.meeting_date if session else 'a day'}"
                 f"{f' — {cohort.name}' if cohort else ''}.",
            type="session_day_review",
        )
    await db.commit()
    return await svc.get_day_detail(db, session_id, current_user)


async def _ops_users(db: AsyncSession) -> list[User]:
    from sqlalchemy import select
    return list((await db.execute(
        select(User).where(User.roles.any("operations") | User.roles.any("admin"))
    )).scalars().all())


# ── ops: the review queue ───────────────────────────────────────────────────

@router.get("/day-reviews", response_model=list[DayReviewOut])
async def list_day_reviews(
    status_filter: str | None = "submitted",
    cohort_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    """The queue. Defaults to what needs attention now; pass
    `status_filter=` (empty) for everything, or a cohort to scope it."""
    return await svc.list_day_reviews(db, status_filter=status_filter or None, cohort_id=cohort_id)


@router.post("/day-reviews/{day_id}/approve", response_model=DayActionOut)
async def approve_day(
    day_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Sign a day off — and this is what makes it a *paid* day (§18/§19).

    An approval is the only event that can make a cohort fully reviewed, so
    this is also where auto-completion is checked. When it fires,
    `complete_cohort()` runs unchanged: student statuses, the LMS certificate
    gate and student certificates all behave exactly as they do today.
    """
    day = await svc.approve_day(db, day_id, current_user.id)
    session = await db.get(Session, day.session_id)
    completed = False
    if session is not None:
        completed = await svc.maybe_complete_cohort(db, session.cohort_id, current_user.id)

    await create_notification(
        db, day.user_id, "Your workshop day was approved",
        body=f"Ops approved {session.meeting_date if session else 'your day'}.",
        type="session_day_review",
    )
    await db.commit()
    return DayActionOut(day_id=day.id, status=day.status, cohort_completed=completed)


@router.post("/day-reviews/{day_id}/return", response_model=DayActionOut)
async def return_day(
    day_id: uuid.UUID,
    body: ReturnDayIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Send it back with something to fix (§12). The comment is mandatory."""
    day = await svc.return_day(db, day_id, current_user.id, comment=body.comment)
    session = await db.get(Session, day.session_id)
    await create_notification(
        db, day.user_id, "A workshop day needs changes",
        body=f"{body.comment}"[:200],
        type="session_day_review",
    )
    await db.commit()
    return DayActionOut(day_id=day.id, status=day.status, review_comment=day.review_comment)


# ── ops: the session board ───────────────────────────────────────────────────

@router.get("/board", response_model=SessionBoardOut)
async def get_session_board(
    done_offset: int = 0,
    done_limit: int = 5,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    """Running / Upcoming / Done across every cohort, no date window.

    Needs Review isn't here — it's `GET /sessions/day-reviews`, already its
    own endpoint; the board page calls both rather than this one repeating it.
    """
    return await svc.session_board(db, done_offset=done_offset, done_limit=done_limit)
