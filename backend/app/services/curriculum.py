"""Unified prerequisites (7B-2, Missions Phase 2B, 2026-08-12) — courses and
missions as interchangeable "items" in one DAG (D2), superseding the
mission-only `mission_prerequisites`. `models/curriculum.py::Prerequisite`
stores edges only; this module evaluates and authors them.

Readiness ("has this student earned the right to attempt/enroll in X") is a
computed rule, kept separate from a grant (`missions.access_mode` /
`courses.access_mode` — "can this student see X at all") — the same split
P5-6 established for missions alone, now applying across both item kinds.
"Satisfied" means: for a mission, a passing attempt (solo, or as a member of
a team attempt's frozen roster); for a course, every mandatory item across
every module completed (`course_completion`, itself derived, never stored).
An item with no incoming edges has an empty prerequisite set and is always
available — vacuously satisfied.

No cycle detection beyond blocking direct self-reference (the CHECK
constraint) — the mission-only DAG this replaces never had it either, and a
human-authored two-node cycle is a mistake to catch by review, not a case
worth a graph-traversal check that nothing before this asked for.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.curriculum import Prerequisite
from app.models.lms.course import Course
from app.models.missions.mission import Mission, MissionAttempt, MissionAttemptMember
from app.services.lms.progress import course_completion

ItemType = Literal["course", "mission"]


async def item_exists(db: AsyncSession, *, item_type: ItemType, item_id: uuid.UUID) -> bool:
    if item_type == "mission":
        return await db.get(Mission, item_id) is not None
    return await db.get(Course, item_id) is not None


async def item_title(db: AsyncSession, *, item_type: ItemType, item_id: uuid.UUID) -> str:
    if item_type == "mission":
        mission = await db.get(Mission, item_id)
        return mission.title if mission else "(deleted mission)"
    course = await db.get(Course, item_id)
    return course.title if course else "(deleted course)"


async def _passed_mission(db: AsyncSession, *, mission_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    solo = (await db.execute(
        select(MissionAttempt.id).where(
            MissionAttempt.mission_id == mission_id, MissionAttempt.user_id == user_id,
            MissionAttempt.status == "passed",
        ).limit(1)
    )).first()
    if solo is not None:
        return True
    # a passing team attempt counts for every member on its frozen roster,
    # not just whoever's user_id happens to be on the attempt row itself
    # (there isn't one — team attempts key on team_id instead).
    team = (await db.execute(
        select(MissionAttempt.id)
        .join(MissionAttemptMember, MissionAttemptMember.attempt_id == MissionAttempt.id)
        .where(
            MissionAttempt.mission_id == mission_id, MissionAttempt.status == "passed",
            MissionAttemptMember.user_id == user_id,
        ).limit(1)
    )).first()
    return team is not None


async def _is_satisfied(db: AsyncSession, *, item_type: ItemType, item_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    if item_type == "mission":
        return await _passed_mission(db, mission_id=item_id, user_id=user_id)
    completion = await course_completion(db, user_id=user_id, course_id=item_id)
    return completion["completed"]


async def prerequisites_of(db: AsyncSession, *, item_type: ItemType, item_id: uuid.UUID) -> list[Prerequisite]:
    return list((await db.execute(
        select(Prerequisite).where(Prerequisite.item_type == item_type, Prerequisite.item_id == item_id)
    )).scalars().all())


async def prerequisite_status(
    db: AsyncSession, *, item_type: ItemType, item_id: uuid.UUID, user_id: uuid.UUID,
) -> list[dict]:
    """Every prerequisite of `(item_type, item_id)`, each flagged with
    whether this student has satisfied it. Empty list = no prerequisites."""
    edges = await prerequisites_of(db, item_type=item_type, item_id=item_id)
    result = []
    for edge in edges:
        satisfied = await _is_satisfied(
            db, item_type=edge.requires_type, item_id=edge.requires_id, user_id=user_id,
        )
        title = await item_title(db, item_type=edge.requires_type, item_id=edge.requires_id)
        result.append({
            "item_type": edge.requires_type, "item_id": edge.requires_id,
            "title": title, "satisfied": satisfied,
        })
    return result


async def is_unlocked(db: AsyncSession, *, item_type: ItemType, item_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    status = await prerequisite_status(db, item_type=item_type, item_id=item_id, user_id=user_id)
    return all(row["satisfied"] for row in status)


# ── authoring (7B-2) — no admin surface existed for mission_prerequisites
# either; this is the first CRUD path for prerequisite edges of any kind. ──

async def add_prerequisite(
    db: AsyncSession, *,
    item_type: ItemType, item_id: uuid.UUID, requires_type: ItemType, requires_id: uuid.UUID,
) -> Prerequisite:
    if item_type == requires_type and item_id == requires_id:
        raise HTTPException(400, detail="An item cannot require itself")
    if not await item_exists(db, item_type=item_type, item_id=item_id):
        raise HTTPException(404, detail=f"{item_type.capitalize()} not found")
    if not await item_exists(db, item_type=requires_type, item_id=requires_id):
        raise HTTPException(404, detail=f"{requires_type.capitalize()} not found")
    existing = await db.get(Prerequisite, (item_type, item_id, requires_type, requires_id))
    if existing is not None:
        raise HTTPException(409, detail="This prerequisite already exists")
    edge = Prerequisite(item_type=item_type, item_id=item_id, requires_type=requires_type, requires_id=requires_id)
    db.add(edge)
    await db.flush()
    return edge


async def remove_prerequisite(
    db: AsyncSession, *,
    item_type: ItemType, item_id: uuid.UUID, requires_type: ItemType, requires_id: uuid.UUID,
) -> None:
    edge = await db.get(Prerequisite, (item_type, item_id, requires_type, requires_id))
    if edge is None:
        raise HTTPException(404, detail="Prerequisite not found")
    await db.delete(edge)
