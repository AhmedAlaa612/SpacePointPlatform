"""Device-secret auth — deliberately NOT `get_current_active_user`. The
on-site agent authenticates as a piece of hardware, not a platform user, so
it carries a per-device secret (header) instead of a JWT."""

import uuid

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.ground_station.device import GroundStationDevice
from app.services.ground_station.devices import get_device, verify_device_secret


async def get_authenticated_device(
    device_id: uuid.UUID,
    x_device_secret: str = Header(..., alias="X-Device-Secret"),
    db: AsyncSession = Depends(get_db),
) -> GroundStationDevice:
    device = await get_device(db, device_id)
    if device is None or not verify_device_secret(device, x_device_secret):
        raise HTTPException(status_code=401, detail="Invalid device credentials")
    return device
