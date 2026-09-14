"""Device-authenticated ingest — what the on-site agent (`ops/ground-station/agent/`)
calls. Never touched by a browser directly."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.ground_station.device import GroundStationDevice
from app.routers.ground_station.deps import get_authenticated_device
from app.schemas.ground_station import PhotoOut, TelemetryFrameIn
from app.services import storage
from app.services.games.realtime import get_realtime_redis_dep
import redis.asyncio as redis
from app.services.ground_station.devices import pop_pending_commands, touch_last_seen
from app.services.ground_station.realtime import safe_publish_to_device

router = APIRouter(prefix="/ground-station/devices/{device_id}", tags=["ground-station-ingest"])


@router.post("/telemetry", status_code=202)
async def ingest_telemetry(
    device_id: uuid.UUID,
    frame: TelemetryFrameIn,
    device: GroundStationDevice = Depends(get_authenticated_device),
    db: AsyncSession = Depends(get_db),
    realtime: redis.Redis | None = Depends(get_realtime_redis_dep),
):
    await touch_last_seen(db, device)
    await safe_publish_to_device(realtime, str(device_id), "telemetry_frame", {
        "data": frame.data,
        "recorded_at": (frame.recorded_at or datetime.now(timezone.utc)).isoformat(),
    })
    return {"status": "accepted"}


@router.get("/commands/pending")
async def pending_commands(
    device_id: uuid.UUID,
    device: GroundStationDevice = Depends(get_authenticated_device),
    db: AsyncSession = Depends(get_db),
    realtime: redis.Redis | None = Depends(get_realtime_redis_dep),
):
    await touch_last_seen(db, device)
    if realtime is None:
        return {"commands": []}
    return {"commands": await pop_pending_commands(realtime, str(device_id))}


@router.post("/commands/{command_id}/ack")
async def ack_command(
    device_id: uuid.UUID,
    command_id: str,
    ack: dict,
    device: GroundStationDevice = Depends(get_authenticated_device),
    realtime: redis.Redis | None = Depends(get_realtime_redis_dep),
):
    await safe_publish_to_device(realtime, str(device_id), "command_ack", {
        "command_id": command_id, **ack,
    })
    return {"status": "ok"}


@router.post("/photos", response_model=PhotoOut)
async def ingest_photo(
    device_id: uuid.UUID,
    file: UploadFile = File(...),
    device: GroundStationDevice = Depends(get_authenticated_device),
    realtime: redis.Redis | None = Depends(get_realtime_redis_dep),
):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are accepted")
    data = await file.read()
    captured_at = datetime.now(timezone.utc)
    path = f"{device_id}/{captured_at.strftime('%Y%m%dT%H%M%S')}_{file.filename or 'photo.jpg'}"
    url = await storage.upload_file("ground-station", path, data, file.content_type)
    photo = PhotoOut(path=path, url=url, captured_at=captured_at)
    await safe_publish_to_device(realtime, str(device_id), "photo_added", photo.model_dump(mode="json"))
    return photo
