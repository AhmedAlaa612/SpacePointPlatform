"""Instructor cohort-scoped Missions access (2026-08-17) — the boss's ask
for instructors to track/gate/review their own cohort's Design runs,
without becoming ops/facilitator generally.

Reuses `SessionInstructor` exactly as `services/sessions/delivery.py::
_get_deliverable_session` already does for session delivery/roster, rather
than inventing a second "instructor owns cohort X" concept. A dedicated
cohort-level grant table (`CohortInstructor`) existed once for this same
purpose and was removed 2026-08-01 because it drifted from the real
staffing source of truth (`SessionInstructor`) — reintroducing that drift
risk here would undo that fix.

Same "staff OR a row here" composition as `authorization.py::
require_mission_manager_or_staff`, and the same plain-async-helper shape
(not a `Depends` factory) — this codebase's stated convention for
per-resource checks.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User

_STAFF_ROLES = {"operations", "facilitator"}


async def instructor_cohort_ids(db: AsyncSession, *, user: User) -> set[uuid.UUID] | None:
    """`None` means no restriction (staff — operations/facilitator/admin).
    Otherwise the set of cohort_ids this instructor is assigned to via
    `SessionInstructor`, derived from `Session.cohort_id` — may be empty."""
    roles = user.role_values
    if "admin" in roles or _STAFF_ROLES & set(roles):
        return None
    rows = (await db.execute(
        select(Session.cohort_id)
        .join(SessionInstructor, SessionInstructor.session_id == Session.id)
        .where(SessionInstructor.user_id == user.id)
        .distinct()
    )).scalars().all()
    return set(rows)


async def require_cohort_access(db: AsyncSession, *, cohort_id: uuid.UUID, user: User) -> None:
    """Instructor OR staff, cohort-scoped — the check every cohort-scoped
    Missions endpoint shares. 404s, not 403s, on a cohort the instructor
    isn't assigned to (matches `_get_deliverable_session`'s "don't leak
    existence" convention)."""
    allowed = await instructor_cohort_ids(db, user=user)
    if allowed is not None and cohort_id not in allowed:
        raise HTTPException(404, detail="Cohort not found")
