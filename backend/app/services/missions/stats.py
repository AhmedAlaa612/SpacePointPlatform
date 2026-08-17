"""Mission-manager scoped stats (7B-7) — every attempt at one mission,
rolled up per student using the same rule the cohort-scoped admin progress
grid uses (7B-1, `services/missions/best_attempt.py`), applied mission-wide
here instead of cohort-scoped: a mission manager cares about their
mission across every cohort and every self-formed team that's touched it,
not one cohort at a time.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.mission import MissionAttempt, MissionAttemptMember
from app.models.user import User
from app.services.missions.best_attempt import best_attempt


async def mission_stats(db: AsyncSession, *, mission_id: uuid.UUID) -> dict:
    attempts = (await db.execute(
        select(MissionAttempt).where(MissionAttempt.mission_id == mission_id)
    )).scalars().all()
    attempts_by_id = {a.id: a for a in attempts}

    by_user: dict[uuid.UUID, list[MissionAttempt]] = {}
    for a in attempts:
        if a.user_id is not None:
            by_user.setdefault(a.user_id, []).append(a)

    team_attempt_ids = [a.id for a in attempts if a.team_id is not None]
    if team_attempt_ids:
        members = (await db.execute(
            select(MissionAttemptMember).where(MissionAttemptMember.attempt_id.in_(team_attempt_ids))
        )).scalars().all()
        for m in members:
            by_user.setdefault(m.user_id, []).append(attempts_by_id[m.attempt_id])

    best_by_user = {uid: best_attempt(user_attempts) for uid, user_attempts in by_user.items()}

    users = (
        (await db.execute(select(User).where(User.id.in_(list(best_by_user))))).scalars().all()
        if best_by_user else []
    )
    users_by_id = {u.id: u for u in users}

    rows = [
        {
            "user_id": uid,
            "full_name": users_by_id[uid].full_name if uid in users_by_id else "(deleted user)",
            "status": attempt.status,
            "score": float(attempt.score) if attempt.score is not None else None,
            "attempt_no": attempt.attempt_no,
        }
        for uid, attempt in best_by_user.items()
    ]
    passed = sum(1 for r in rows if r["status"] == "passed")

    return {
        "mission_id": mission_id,
        "total_attempts": len(attempts),
        "total_students": len(rows),
        "passed_students": passed,
        "pass_rate": round(100 * passed / len(rows)) if rows else 0,
        "rows": rows,
    }
