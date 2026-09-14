"""Telemetry/command/photo ingest. Two authentication shapes share this
surface: the on-site agent (device secret, `/devices/{id}/*`) and a
student's own browser via Web Serial direct-connect (their normal JWT,
`/devices/{id}/telemetry/browser`) — same processing either way."""

import uuid
from datetime import datetime, timezone

import redis.asyncio as redis
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.ground_station.device import GroundStationDevice
from app.models.user import User
from app.routers.ground_station.deps import get_authenticated_device
from app.schemas.ground_station import BrowserTelemetryIn, PhotoOut, TelemetryFrameIn
from app.services import storage
from app.services.games.realtime import get_realtime_redis_dep
from app.services.ground_station.devices import pop_pending_commands, touch_last_seen
from app.services.ground_station.realtime import safe_publish_to_device
from app.services.ground_station.telemetry import check_thresholds, persist_image, persist_telemetry

router = APIRouter(prefix="/ground-station/devices/{device_id}", tags=["ground-station-ingest"])


async def _ingest_and_broadcast(
    db: AsyncSession, realtime: redis.Redis | None, device_id: uuid.UUID, data: dict, recorded_at: datetime | None,
) -> None:
    ts = recorded_at or datetime.now(timezone.utc)
    await persist_telemetry(db, device_id, data, ts)
    alerts = await check_thresholds(db, device_id, data)
    await db.commit()
    await safe_publish_to_device(realtime, str(device_id), "telemetry_frame", {"data": data, "recorded_at": ts.isoformat()})
    for alert in alerts:
        await safe_publish_to_device(realtime, str(device_id), "alert", {
            "id": str(alert.id), "alert_type": alert.alert_type, "threshold": alert.threshold,
            "current_value": alert.current_value, "severity": alert.severity,
            "occurred_at": alert.occurred_at.isoformat(),
            "message": f"{alert.alert_type.upper()} {alert.severity.upper()}: {alert.current_value} (limit {alert.threshold})",
        })


@router.post("/telemetry", status_code=202)
async def ingest_telemetry(
    device_id: uuid.UUID,
    frame: TelemetryFrameIn,
    device: GroundStationDevice = Depends(get_authenticated_device),
    db: AsyncSession = Depends(get_db),
    realtime: redis.Redis | None = Depends(get_realtime_redis_dep),
):
    await touch_last_seen(db, device)
    await _ingest_and_broadcast(db, realtime, device_id, frame.data, frame.recorded_at)
    return {"status": "accepted"}


@router.post("/telemetry/browser", status_code=202)
async def ingest_telemetry_from_browser(
    device_id: uuid.UUID,
    frame: BrowserTelemetryIn,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    realtime: redis.Redis | None = Depends(get_realtime_redis_dep),
):
    """Web Serial direct-connect (`web_serial.js` in the legacy app) — the
    student's own Chrome/Edge tab read this straight off the hardware, no
    on-site agent involved. Still flows through the same DB+broadcast path
    so every other connected viewer sees it too."""
    await _ingest_and_broadcast(db, realtime, device_id, frame.data, None)
    return {"status": "accepted"}


@router.get("/commands/pending")
async def pending_commands(
    device_id: uuid.UUID,
    device: GroundStationDevice = Depends(get_authenticated_device),
    db: AsyncSession = Depends(get_db),
    realtime: redis.Redis | None = Depends(get_realtime_redis_dep),
):
    await touch_last_seen(db, device)
    await db.commit()
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
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    alt: float | None = Form(None),
    device: GroundStationDevice = Depends(get_authenticated_device),
    db: AsyncSession = Depends(get_db),
    realtime: redis.Redis | None = Depends(get_realtime_redis_dep),
):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are accepted")
    data = await file.read()
    captured_at = datetime.now(timezone.utc)
    path = f"{device_id}/{captured_at.strftime('%Y%m%dT%H%M%S')}_{file.filename or 'photo.jpg'}"
    url = await storage.upload_file("ground-station", path, data, file.content_type)
    await persist_image(db, device_id, bucket="ground-station", path=path, lat=lat, lon=lon, alt=alt, captured_at=captured_at)
    await db.commit()
    photo = PhotoOut(path=path, url=url, captured_at=captured_at, lat=lat, lon=lon, alt=alt)
    await safe_publish_to_device(realtime, str(device_id), "photo_added", photo.model_dump(mode="json"))
    return photo
