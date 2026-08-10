"""LMS leaderboard (P2-4, Phase 2 Stage 2, 2026-08-10).

Derived, never cached — every read is a `SUM(points) GROUP BY user_id`
straight off `point_events`; if this ever needs to be faster, the
escalation is a materialised view, never a stored total column (§6).

⚠️ D6 (leaderboard scope + display names) is still an open operator
decision (PHASE2_EXECUTION_PLAN.md §2) — this ships the backend the rest
of Phase 2 needs to build against, but is NOT wired into any
student-facing page. The plan's own stated default is "cohort-scoped,
chosen display name" — "chosen" implies a handle-picking feature that
doesn't exist yet and is out of this stage's scope to invent unprompted.
`_display_name` below is a safe, private-by-default stand-in (first name +
last-initial, no new schema) so the query itself can be built and tested
now; swap it for whatever D6 actually decides once it's answered. The user
base skews toward minors — full legal names are not an acceptable default
in the meantime.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.points import PointEvent
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES


def _display_name(full_name: str) -> str:
    parts = (full_name or "").strip().split()
    if not parts:
        return "Student"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0]}."


async def leaderboard(
    db: AsyncSession, *, cohort_id: uuid.UUID | None = None, limit: int = 50,
) -> list[dict]:
    """Top `limit` users by total points. `cohort_id` scopes to users linked
    (via `users.contact_id`) to an active registration in that cohort;
    omitted, it's global. Only users with at least one point_events row
    appear — no zero-point padding."""
    total_col = func.sum(PointEvent.points).label("total")
    stmt = (
        select(User.id, User.full_name, total_col)
        .join(PointEvent, PointEvent.user_id == User.id)
        .group_by(User.id, User.full_name)
        .order_by(total_col.desc())
        .limit(limit)
    )
    if cohort_id is not None:
        stmt = (
            stmt.join(Contact, Contact.id == User.contact_id)
            .join(Registration, Registration.contact_id == Contact.id)
            .where(
                Registration.cohort_id == cohort_id,
                Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
            )
        )

    rows = (await db.execute(stmt)).all()
    return [
        {
            "rank": i + 1,
            "user_id": row.id,
            "display_name": _display_name(row.full_name),
            "points": int(row.total),
        }
        for i, row in enumerate(rows)
    ]
