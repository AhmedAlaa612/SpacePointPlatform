"""Prerequisite DAG evaluation (P5-6) — `mission_prerequisites` (P5-1)
stores edges only; this module is where they're actually enforced.

Readiness (has this student earned the right to attempt X) is a computed
rule, separate from `access_mode` (can this student see X at all, a grant)
— Stage 5 note ②, do not collapse the two. "Passed" means any variant of
the prerequisite mission — readiness is per-mission, not per-difficulty.
An unrelated mission (no rows in `mission_prerequisites` naming it) has an
empty prerequisite set and is always available — vacuously satisfied.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.mission import Mission, MissionAttempt, MissionPrerequisite


async def prerequisite_missions(db: AsyncSession, *, mission_id: uuid.UUID) -> list[Mission]:
    return list((await db.execute(
        select(Mission)
        .join(MissionPrerequisite, MissionPrerequisite.requires_mission_id == Mission.id)
        .where(MissionPrerequisite.mission_id == mission_id)
    )).scalars().all())


async def passed_mission_ids(
    db: AsyncSession, *, user_id: uuid.UUID, mission_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    if not mission_ids:
        return set()
    rows = (await db.execute(
        select(MissionAttempt.mission_id).where(
            MissionAttempt.user_id == user_id,
            MissionAttempt.mission_id.in_(mission_ids),
            MissionAttempt.status == "passed",
        ).distinct()
    )).scalars().all()
    return set(rows)


async def prerequisite_status(db: AsyncSession, *, mission_id: uuid.UUID, user_id: uuid.UUID) -> list[dict]:
    """Every prerequisite of `mission_id`, each flagged with whether this
    student has passed it. Empty list = no prerequisites."""
    prereqs = await prerequisite_missions(db, mission_id=mission_id)
    if not prereqs:
        return []
    passed = await passed_mission_ids(db, user_id=user_id, mission_ids=[p.id for p in prereqs])
    return [{"mission_id": p.id, "title": p.title, "satisfied": p.id in passed} for p in prereqs]


async def is_unlocked(db: AsyncSession, *, mission_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    status = await prerequisite_status(db, mission_id=mission_id, user_id=user_id)
    return all(row["satisfied"] for row in status)
