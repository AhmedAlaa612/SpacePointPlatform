"""Who can see a rig's data (2026-09-14 rework): the attempt's own
owner(s) — the solo student, or any member of the team that started it —
plus staff. Same shape as `services/missions/cohort_access.py`'s "staff OR
a row here" composition and the missions router's own `_own_attempt`, just
scoped to a device instead of an attempt directly.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ground_station.device import GroundStationDevice
from app.models.missions.mission import MissionAttempt, MissionAttemptMember
from app.models.user import User

_STAFF_ROLES = {"admin", "operations", "facilitator"}


def is_staff(user: User) -> bool:
    return bool(_STAFF_ROLES & set(user.role_values))


async def _owns_attempt(db: AsyncSession, attempt: MissionAttempt, user: User) -> bool:
    if attempt.user_id == user.id:
        return True
    if attempt.team_id is not None:
        member = await db.get(MissionAttemptMember, (attempt.id, user.id))
        if member is not None:
            return True
    return False


async def require_device_access(db: AsyncSession, *, device: GroundStationDevice, user: User) -> None:
    """404s (not 403 — don't leak that a device exists) unless the caller
    is staff or owns the attempt this device belongs to. A device with no
    owning attempt at all (staff-provisioned, orphan) is staff-only."""
    if is_staff(user):
        return
    if device.mission_attempt_id is None:
        raise HTTPException(404, detail="Device not found")
    attempt = await db.get(MissionAttempt, device.mission_attempt_id)
    if attempt is None or not await _owns_attempt(db, attempt, user):
        raise HTTPException(404, detail="Device not found")


async def require_attempt_access(db: AsyncSession, *, attempt: MissionAttempt, user: User) -> None:
    if is_staff(user):
        return
    if not await _owns_attempt(db, attempt, user):
        raise HTTPException(404, detail="Attempt not found")


async def visible_device_ids(db: AsyncSession, *, user: User) -> set[uuid.UUID] | None:
    """`None` means unrestricted (staff sees every device). Otherwise the
    set of device ids the caller owns via a solo or team mission attempt."""
    if is_staff(user):
        return None
    rows = (await db.execute(
        select(GroundStationDevice.id).join(
            MissionAttempt, MissionAttempt.id == GroundStationDevice.mission_attempt_id,
        ).where(
            (MissionAttempt.user_id == user.id)
            | (MissionAttempt.id.in_(
                select(MissionAttemptMember.attempt_id).where(MissionAttemptMember.user_id == user.id)
            ))
        )
    )).scalars().all()
    return set(rows)
