"""User-facing Ground Station surface — any logged-in user (no per-mission
gating, this is a tool, not a graded activity). Matches the legacy app's own
access model: everything past login was open to any authenticated viewer,
including thresholds config and alert acknowledgement — there was no
finer-grained RBAC on these specific actions there either."""

import uuid
from datetime import datetime, timezone

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.ground_station.device import GroundStationDevice
from app.models.user import User
from app.schemas.ground_station import (
    AlertOut,
    CommandIn,
    CommandQueuedOut,
    DeviceOut,
    DeviceStatsOut,
    HistoryOut,
    PhotoOut,
    ThresholdsIn,
    ThresholdsOut,
)
from app.services import storage
from app.services.games.realtime import get_realtime_redis_dep
from app.services.ground_station.commands import is_allowed
from app.services.ground_station.devices import queue_command
from app.services.ground_station.realtime import active_connection_count, safe_publish_to_device
from app.services.ground_station.telemetry import (
    acknowledge_alert,
    device_stats,
    get_history,
    get_latest,
    get_thresholds,
    list_alerts,
    list_images,
    set_thresholds,
)

router = APIRouter(prefix="/ground-station", tags=["ground-station"])


@router.get("/devices", response_model=list[DeviceOut])
async def list_devices(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    devices = (await db.execute(select(GroundStationDevice))).scalars().all()
    return devices


@router.get("/devices/{device_id}", response_model=DeviceOut)
async def get_device_details(
    device_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    device = await db.get(GroundStationDevice, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.get("/devices/{device_id}/stats", response_model=DeviceStatsOut)
async def get_device_stats(
    device_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    realtime: redis.Redis | None = Depends(get_realtime_redis_dep),
):
    stats = await device_stats(db, device_id)
    connections = await active_connection_count(realtime, str(device_id))
    return DeviceStatsOut(device_id=device_id, active_connections=connections, **stats)


@router.get("/devices/{device_id}/telemetry/latest")
async def get_telemetry_latest(
    device_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    latest = await get_latest(db, device_id)
    if latest is None:
        raise HTTPException(status_code=404, detail="No telemetry data available")
    return latest.data | {"recorded_at": latest.recorded_at.isoformat()}


@router.get("/devices/{device_id}/history", response_model=HistoryOut)
async def get_telemetry_history(
    device_id: uuid.UUID,
    minutes: int = 15,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await get_history(db, device_id, minutes)
    return HistoryOut(device_id=device_id, minutes=minutes, count=len(rows), data=rows)


@router.get("/devices/{device_id}/thresholds", response_model=ThresholdsOut)
async def get_device_thresholds(
    device_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    row = await get_thresholds(db, device_id)
    await db.commit()
    return row


@router.put("/devices/{device_id}/thresholds", response_model=ThresholdsOut)
async def put_device_thresholds(
    device_id: uuid.UUID,
    body: ThresholdsIn,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    row = await set_thresholds(db, device_id, body.model_dump(exclude_none=True))
    await db.commit()
    return row


@router.get("/devices/{device_id}/alerts", response_model=list[AlertOut])
async def get_device_alerts(
    device_id: uuid.UUID,
    active: bool = False,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_alerts(db, device_id, active_only=active)


@router.post("/devices/{device_id}/alerts/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge_device_alert(
    device_id: uuid.UUID,
    alert_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    alert = await acknowledge_alert(db, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.commit()
    return alert


@router.post("/devices/{device_id}/commands", response_model=CommandQueuedOut)
async def send_command(
    device_id: uuid.UUID,
    body: CommandIn,
    user: User = Depends(get_current_active_user),
    realtime: redis.Redis | None = Depends(get_realtime_redis_dep),
):
    name = body.name.strip().upper()
    if not is_allowed(name):
        raise HTTPException(status_code=400, detail=f"Unknown or disallowed command: {body.name!r}")
    if realtime is None:
        raise HTTPException(status_code=503, detail="Real-time link unavailable — command not sent")

    command_id = str(uuid.uuid4())
    queued_at = datetime.now(timezone.utc)
    await queue_command(realtime, str(device_id), command_id=command_id, name=name, arg=body.arg)
    await safe_publish_to_device(realtime, str(device_id), "command_queued", {
        "id": command_id, "name": name, "arg": body.arg,
        "sent_by": str(user.id), "queued_at": queued_at.isoformat(),
    })
    return CommandQueuedOut(id=command_id, name=name, arg=body.arg, queued_at=queued_at)


@router.get("/devices/{device_id}/photos", response_model=list[PhotoOut])
async def list_photos(
    device_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    images = await list_images(db, device_id)
    out: list[PhotoOut] = []
    for img in images:
        url = await storage.get_signed_url(img.bucket, img.path)
        out.append(PhotoOut(path=img.path, url=url, captured_at=img.captured_at, lat=img.lat, lon=img.lon, alt=img.alt))
    return out
