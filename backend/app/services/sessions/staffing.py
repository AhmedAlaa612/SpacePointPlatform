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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sessions.cohort import Cohort
from app.models.sessions.instructor_interest import InstructorInterest
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
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


async def open_call(db: AsyncSession, session_id: UUID) -> Session:
    session = await _get_session(db, session_id)
    if session.staffing_status != "unstaffed":
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"Session is already {session.staffing_status}, not unstaffed",
        )
    session.staffing_status = "open_call"
    await db.flush()
    return session


async def open_call_for_cohort(db: AsyncSession, cohort_id: UUID) -> list[Session]:
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
    await db.flush()
    return list(sessions)


async def close_call(db: AsyncSession, session_id: UUID, clear_interest: bool = False) -> Session:
    """open_call -> unstaffed. Closes an open call.
    If clear_interest=True (Abort), deletes all submitted InstructorInterest rows for this session.
    If clear_interest=False (Pause), preserves existing interest history.
    """
    session = await _get_session(db, session_id)
    if session.staffing_status != "open_call":
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"Session is {session.staffing_status}, not open_call",
        )

    if clear_interest:
        await db.execute(
            delete(InstructorInterest).where(InstructorInterest.session_id == session_id)
        )

    session.staffing_status = "unstaffed"
    await db.flush()
    return session


async def reopen(db: AsyncSession, session_id: UUID) -> Session:
    """staffed -> open_call. Explicit and separate from removing an
    instructor — reopening never removes anyone already assigned; that's
    remove_instructor's job, called on its own."""
    session = await _get_session(db, session_id)
    if session.staffing_status != "staffed":
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Session is {session.staffing_status}, not staffed")
    session.staffing_status = "open_call"
    await db.flush()
    return session


async def list_available_sessions(
    db: AsyncSession, user: User,
) -> list[tuple[Session, Cohort, Program, int, InstructorInterest | None]]:
    """Every open-call session, cohort/program joined in for display, plus
    an interest count and this user's own interest row (if any) — the S4-3
    "Available sessions" instructor page."""
    rows = (await db.execute(
        select(Session, Cohort, Program)
        .join(Cohort, Cohort.id == Session.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
        .where(Session.staffing_status == "open_call")
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
        select(Session, Cohort, Program, SessionInstructor.role)
        .join(Cohort, Cohort.id == Session.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
        .join(SessionInstructor, SessionInstructor.session_id == Session.id)
        .where(SessionInstructor.user_id == user.id)
        .order_by(Session.meeting_date.asc())
    )).all()
    return [(s, c, p, role) for s, c, p, role in rows]


async def register_interest(db: AsyncSession, session_id: UUID, user: User, note: str | None = None) -> InstructorInterest:
    session = await _get_session(db, session_id)
    if session.staffing_status != "open_call":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This session isn't open for interest right now")
    if not any(r in user.role_values for r in ("instructor", "facilitator")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only instructors or facilitators can register interest")

    existing = (await db.execute(
        select(InstructorInterest).where(
            InstructorInterest.session_id == session_id, InstructorInterest.user_id == user.id,
        )
    )).scalars().first()
    if existing is not None:
        if note is not None:
            existing.note = note
        await db.flush()
        return existing

    interest = InstructorInterest(id=uuid4(), session_id=session_id, user_id=user.id, note=note)
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


async def list_eligible_instructors(db: AsyncSession, session_id: UUID) -> list[tuple[User, InstructorInterest | None]]:
    """Every instructor|facilitator user, paired with their interest row (if
    any) — the full pickable roster for the ops select screen (operator
    requirement 2026-07-24: "ops can pick from the instructors list ...
    multiple ... select all", not just whoever registered interest).
    list_interest above stays interest-only; this is the superset."""
    await _get_session(db, session_id)  # 404 if the session doesn't exist
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
    return [(u, interests.get(u.id)) for u in users]


async def select_instructors(
    db: AsyncSession, session_id: UUID, user_ids: list[UUID], role: Literal["lead", "co"],
    close_call: bool = True,
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
            existing.role = role
            assignments.append(existing)
        else:
            assignment = SessionInstructor(id=uuid4(), session_id=session_id, user_id=user_id, role=role)
            db.add(assignment)
            assignments.append(assignment)
            await _write_touchpoint(db, selected_user, f"session_assigned:{session_id}")

    if close_call:
        session.staffing_status = "staffed"
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
