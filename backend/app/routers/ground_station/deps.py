"""Ingest auth (2026-09-14 rework): none. Operator directive — the whole
Ground Station surface is already private (attempt-owner + staff only, see
services/ground_station/access.py), so the ESP32 side stays a plain
unauthenticated POST to a hard-to-guess device UUID. No secret to bake
into firmware, no rotation, no header — the tradeoff is explicit and
accepted: anyone who somehow learns a specific device id could inject
fake data for it. Only requirement left: the device id has to be real."""

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.ground_station.device import GroundStationDevice
from app.models.user import User
from app.services.ground_station.access import require_device_access
from app.services.ground_station.devices import get_device


async def get_open_device(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> GroundStationDevice:
    """Ingest path — no auth, see this module's docstring."""
    device = await get_device(db, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Unknown device")
    return device


async def get_authorized_device(
    device_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> GroundStationDevice:
    """The console (viewer) path — logged in AND owns the attempt (or
    staff). 404s rather than 403s on a device that exists but isn't
    theirs, so its existence isn't leaked."""
    device = await get_device(db, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    await require_device_access(db, device=device, user=user)
    return device
