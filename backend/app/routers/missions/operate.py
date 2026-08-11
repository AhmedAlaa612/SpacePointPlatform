"""Operate mission routes (Phase 2B, Stage 7B-3) — `/missions/operate/*`.
Registered before `/missions/{mission_id}` in `routers/missions/__init__.py`
for the same static-before-dynamic reason as `/missions/design`,
`/missions/admin`, `/missions/graph`, and `/missions/teams`.

Authorization reuses `routers/missions/student.py::_own_attempt` — the
solo student, or any member of a team attempt's frozen roster. Same
posture as the design mission: nothing here is operate-specific about
who may act on an attempt.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.user import User
from app.routers.missions.student import _own_attempt
from app.schemas.missions_operate import (
    AnomalyStateOut,
    CommandEventOut,
    FinishOperationOut,
    IssueCommandIn,
    IssueCommandOut,
    OperateStateOut,
    TelemetryOut,
)
from app.services.missions.operate.evaluator import evaluate_operation
from app.services.missions.operate.telemetry import compute_telemetry
from app.services.missions.verifiers.operate import attempt_events, commands_issued, finish_operation, issue_command

router = APIRouter(prefix="/missions/operate", tags=["missions-operate"])


async def _own_operate_attempt(db: AsyncSession, attempt_id: uuid.UUID, user: User) -> MissionAttempt:
    attempt = await _own_attempt(db, attempt_id, user)
    mission = await db.get(Mission, attempt.mission_id)
    if mission is None or mission.kind != "operate":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    return attempt


async def _state_out(db: AsyncSession, attempt: MissionAttempt) -> OperateStateOut:
    mission = await db.get(Mission, attempt.mission_id)
    variant = await db.get(MissionVariant, attempt.variant_id)
    config = variant.config or {}

    started_at = attempt.started_at or datetime.now(timezone.utc)
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    telemetry = compute_telemetry(elapsed)

    events = attempt_events(attempt)
    result = evaluate_operation(
        commands_issued=commands_issued(attempt),
        anomaly_script=config.get("anomalies", []),
        pass_threshold=config.get("pass_threshold", 70),
    )

    return OperateStateOut(
        attempt_id=attempt.id, mission_id=mission.id, variant_id=variant.id, variant_label=variant.label,
        attempt_status=attempt.status, elapsed_seconds=round(elapsed, 1),
        telemetry=TelemetryOut(**telemetry.__dict__),
        events=[CommandEventOut(**e) for e in events],
        anomalies=[
            AnomalyStateOut(index=a.index, subsystem=a.subsystem, triggered=a.triggered, resolved=a.resolved)
            for a in result.anomalies
        ],
        score=result.score, triggered_count=result.triggered_count, resolved_count=result.resolved_count,
        pass_threshold=config.get("pass_threshold", 70),
    )


@router.get("/attempts/{attempt_id}", response_model=OperateStateOut)
async def get_operate_state(
    attempt_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_operate_attempt(db, attempt_id, current)
    return await _state_out(db, attempt)


@router.post("/attempts/{attempt_id}/command", response_model=IssueCommandOut)
async def send_command(
    attempt_id: uuid.UUID, body: IssueCommandIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_operate_attempt(db, attempt_id, current)
    event = await issue_command(db, attempt=attempt, raw_command=body.command, issued_by=current.id)
    await db.commit()
    state = await _state_out(db, attempt)
    return IssueCommandOut(event=CommandEventOut(**event), state=state)


@router.post("/attempts/{attempt_id}/finish", response_model=FinishOperationOut)
async def finish(
    attempt_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_operate_attempt(db, attempt_id, current)
    decided, result = await finish_operation(db, attempt=attempt)
    await db.commit()
    state = await _state_out(db, decided)
    return FinishOperationOut(passed=result.passed, score=result.score, state=state)
