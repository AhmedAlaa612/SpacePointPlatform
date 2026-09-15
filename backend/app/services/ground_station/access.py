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
from app.models.missions.mission import Mission, MissionAttempt, MissionAttemptMember
from app.models.user import User
from app.services.missions.authorization import is_staff

__all__ = ["is_staff", "require_device_access", "require_attempt_access", "require_ground_station_attempt", "visible_device_ids"]


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


async def require_ground_station_attempt(db: AsyncSession, *, attempt: MissionAttempt, user: User) -> None:
    """`require_attempt_access` plus the check every route under
    `/ground-station/attempts/` actually needs: the attempt has to belong
    to a `ground_station` mission. Without this, an owner (or staff acting
    on behalf of one) could point these routes at *any* attempt id they can
    see — including, via `complete_attempt`, self-passing an unrelated
    quiz/design run by flipping its status to `passed`. 404s either way,
    same "don't leak" convention as the rest of this module."""
    await require_attempt_access(db, attempt=attempt, user=user)
    mission = await db.get(Mission, attempt.mission_id)
    if mission is None or mission.kind != "ground_station":
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
