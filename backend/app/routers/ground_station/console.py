"""User-facing Ground Station surface — any logged-in user (no per-mission
gating, this is a tool, not a graded activity)."""

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
from app.schemas.ground_station import CommandIn, CommandQueuedOut, DeviceOut, PhotoOut
from app.services import storage
from app.services.games.realtime import get_realtime_redis_dep
from app.services.ground_station.commands import is_allowed
from app.services.ground_station.devices import queue_command
from app.services.ground_station.realtime import safe_publish_to_device

router = APIRouter(prefix="/ground-station", tags=["ground-station"])


@router.get("/devices", response_model=list[DeviceOut])
async def list_devices(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    devices = (await db.execute(select(GroundStationDevice))).scalars().all()
    return devices


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
):
    files = await storage.list_files("ground-station", str(device_id))
    out: list[PhotoOut] = []
    for f in files:
        if f.get("metadata") is None:  # a folder entry, not a file
            continue
        path = f"{device_id}/{f['name']}"
        url = await storage.get_signed_url("ground-station", path)
        captured_at = f.get("metadata", {}).get("lastModified") or f.get("created_at")
        out.append(PhotoOut(path=path, url=url, captured_at=captured_at))
    return out
