"""The student-facing entry point: resolve (or lazily provision) the one
rig belonging to a ground_station mission attempt, and let its owner mark
it done for checklist tracking (no grade attached — see `complete_attempt`)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.missions.mission import MissionAttempt
from app.models.team import Team
from app.models.user import User
from app.schemas.ground_station import AttemptCompleteOut, AttemptDeviceOut, DeviceOut
from app.services.ground_station.access import require_attempt_access
from app.services.ground_station.devices import get_or_create_device_for_attempt

router = APIRouter(prefix="/ground-station/attempts", tags=["ground-station-attempts"])


@router.get("/{attempt_id}/device", response_model=AttemptDeviceOut)
async def get_attempt_device(
    attempt_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    attempt = await db.get(MissionAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(404, detail="Attempt not found")
    await require_attempt_access(db, attempt=attempt, user=user)

    label = user.full_name
    if attempt.team_id is not None:
        team = await db.get(Team, attempt.team_id)
        label = team.name if team else "Team rig"

    device = await get_or_create_device_for_attempt(db, mission_attempt_id=attempt.id, label=label)
    await db.commit()
    return AttemptDeviceOut(device=DeviceOut.model_validate(device), ingest_base_url=settings.BASE_URL)


@router.post("/{attempt_id}/complete", response_model=AttemptCompleteOut)
async def complete_attempt(
    attempt_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Self-serve "done" for checklist tracking (`mission_run` items check
    `attempt.status == 'passed'`) — no grading involved: `score` stays
    null and nothing runs through `decide_attempt`/`award_points`, so
    marking this never mints points. It just flips the one field the
    checklist's own auto-tracking already reads. Idempotent."""
    attempt = await db.get(MissionAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(404, detail="Attempt not found")
    await require_attempt_access(db, attempt=attempt, user=user)

    if attempt.status not in ("passed",):
        attempt.status = "passed"
        attempt.submitted_at = attempt.submitted_at or datetime.now(timezone.utc)
        attempt.decided_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(attempt)

    return AttemptCompleteOut(attempt_id=attempt.id, status=attempt.status, decided_at=attempt.decided_at)
