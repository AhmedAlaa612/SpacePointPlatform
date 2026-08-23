"""LMS leaderboard (P2-4, Phase 2 Stage 2, 2026-08-10; turned on in Live
Games Phase 2C, 8-2).

Derived, never cached — every read is a `SUM(points) GROUP BY user_id`
straight off `point_events`; if this ever needs to be faster, the
escalation is a materialised view, never a stored total column (§6).

D6 (leaderboard scope + display names) was an open operator decision from
Stage 2 that kept this backend built but never linked into the frontend —
showing real names on a leaderboard isn't acceptable given the user base
skews toward minors, and nobody had picked what to show instead.
`services/nicknames.py` (8-1) is that answer: every student already has an
auto-generated public nickname, so `_display_name` uses it directly.

Staff accounts (D2: instructors/ops/etc. can take LMS courses too, and rack
up `point_events` the same way students do) are excluded outright
(operator ask, 2026-08-22) — a leaderboard mixing in staff isn't a fair
ranking for the students it's for. `_display_name`'s non-student fallback
below is now unreachable from `leaderboard()` itself as a result, but it
stays generic (keyed on nickname/full_name, not role) rather than assuming
every caller has already filtered to students.
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


def _display_name(*, nickname: str | None, full_name: str) -> str:
    if nickname:
        return nickname
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
        select(User.id, User.full_name, User.nickname, total_col)
        .join(PointEvent, PointEvent.user_id == User.id)
        .where(User.roles.any("student"))
        .group_by(User.id, User.full_name, User.nickname)
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
            "display_name": _display_name(nickname=row.nickname, full_name=row.full_name),
            "points": int(row.total),
        }
        for i, row in enumerate(rows)
    ]
