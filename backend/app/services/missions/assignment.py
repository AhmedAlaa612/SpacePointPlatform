"""Mission assignment service (2026-08-12) — mirrors `services/lms/enrollment.py::enroll`
for the mission side. See `models/missions/assignment.py` for the design note.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.assignment import MissionAssignment
from app.models.missions.mission import Mission


async def assign(
    db: AsyncSession, *, user_id: UUID, mission_id: UUID, granted_by: UUID | None = None,
) -> MissionAssignment:
    """Grant (or re-grant) a person access to a mission. Idempotent: an
    existing active row is returned unchanged; an inactive one is
    reactivated in place. Always source='ops' — unlike enrollments there is
    no self-service path onto a mission assignment."""
    mission = await db.get(Mission, mission_id)
    if mission is None:
        raise HTTPException(404, detail="Mission not found")

    existing = (await db.execute(
        select(MissionAssignment).where(
            MissionAssignment.user_id == user_id, MissionAssignment.mission_id == mission_id,
        )
    )).scalars().first()

    if existing is not None:
        if existing.status == "inactive":
            existing.status = "active"
            if granted_by is not None:
                existing.granted_by = granted_by
            await db.flush()
        return existing

    assignment = MissionAssignment(
        id=uuid4(), user_id=user_id, mission_id=mission_id, source="ops",
        granted_by=granted_by, status="active",
    )
    db.add(assignment)
    await db.flush()
    return assignment
