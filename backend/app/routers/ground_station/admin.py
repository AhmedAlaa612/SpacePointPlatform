"""Staff-only: register a shared/orphan rig, and the ops monitoring list
— every team/solo Ground Station mission run with its device status."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations
from app.db.session import get_db
from app.schemas.ground_station import DeviceOut, DeviceRegisterIn, GroundStationAttemptSummary
from app.services.ground_station.devices import list_ground_station_attempts, register_device

router = APIRouter(prefix="/ground-station/admin", tags=["ground-station-admin"])


@router.post("/devices", response_model=DeviceOut)
async def create_device(
    body: DeviceRegisterIn,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_operations),
):
    device = await register_device(db, label=body.label)
    await db.commit()
    return device


@router.get("/attempts", response_model=list[GroundStationAttemptSummary])
async def list_attempts(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_operations),
):
    rows = await list_ground_station_attempts(db)
    return [
        GroundStationAttemptSummary(
            attempt_id=r.attempt_id, owner_label=r.owner_label, team_id=r.team_id, user_id=r.user_id,
            status=r.status, started_at=r.started_at, device_id=r.device_id,
            device_status=r.device_status, device_last_seen_at=r.device_last_seen_at,
        )
        for r in rows
    ]
