"""Staff-only device management — register a rig, rotate its secret."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations
from app.db.session import get_db
from app.schemas.ground_station import DeviceOut, DeviceRegisterIn, DeviceRegisterOut
from app.services.ground_station.devices import get_device, register_device, rotate_secret

router = APIRouter(prefix="/ground-station/admin", tags=["ground-station-admin"])


@router.post("/devices", response_model=DeviceRegisterOut)
async def create_device(
    body: DeviceRegisterIn,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_operations),
):
    device, secret = await register_device(db, label=body.label)
    await db.commit()
    return DeviceRegisterOut(device=DeviceOut.model_validate(device), secret=secret)


@router.post("/devices/{device_id}/rotate-secret", response_model=DeviceRegisterOut)
async def rotate_device_secret(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_operations),
):
    device = await get_device(db, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    secret = await rotate_secret(db, device)
    await db.commit()
    return DeviceRegisterOut(device=DeviceOut.model_validate(device), secret=secret)
