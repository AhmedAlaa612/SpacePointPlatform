"""Per-cohort Design-mission step gating (2026-08-17) — a revival of the
dropped `design_step_gates`/`gating.py` (`94eaeb5ddbde` -> `d4a1c07e5b32`,
Design v2 D1). That version shipped inert: `is_step_unlocked` was hardcoded
default-unlocked and no UI was ever built to flip a gate, so it sat
unused and was removed. The operator has now explicitly reversed that
call — this time both layers (this module's server-side enforcement, and
the client-side tab-blocking in `DesignMissionPage.tsx`) ship together.

Design-mission only: it's the only mission kind with a real multi-step
wizard to gate — quiz/submission are single-shot, nothing to lock.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.gate import MissionStepGate
from app.models.missions.mission import MissionAttempt


async def step_gates_for_mission(
    db: AsyncSession, *, cohort_id: uuid.UUID, mission_id: uuid.UUID,
) -> dict[str, MissionStepGate]:
    """step_key -> gate row, for every gate an instructor has explicitly
    set on this cohort/mission. A missing key means locked — same
    "absence is the safe default" rule the dropped table used."""
    rows = (await db.execute(
        select(MissionStepGate).where(
            MissionStepGate.cohort_id == cohort_id, MissionStepGate.mission_id == mission_id,
        )
    )).scalars().all()
    return {g.step_key: g for g in rows}


async def set_step_gate(
    db: AsyncSession, *, cohort_id: uuid.UUID, mission_id: uuid.UUID, step_key: str,
    is_unlocked: bool, updated_by: uuid.UUID,
) -> MissionStepGate:
    gate = await db.get(MissionStepGate, (cohort_id, mission_id, step_key))
    if gate is None:
        gate = MissionStepGate(cohort_id=cohort_id, mission_id=mission_id, step_key=step_key)
        db.add(gate)
    gate.is_unlocked = is_unlocked
    gate.updated_at = datetime.now(timezone.utc)
    gate.updated_by = updated_by
    await db.flush()
    return gate


async def gate_map_for_attempt(db: AsyncSession, *, attempt: MissionAttempt) -> dict[str, bool]:
    """step_key -> is_unlocked, for every step, for the student-facing
    wizard (`DesignStateOut.step_gates`). An attempt with no cohort_id
    (self-service, outside any workshop) is never gated — everything reads
    `True`. Otherwise a missing row also reads `True` — gating is an
    opt-in restriction a cohort's instructor applies, not a default-locked
    system; only an explicit `is_unlocked=False` row locks a step."""
    from app.services.lms.admin_progress import DESIGN_STEP_LABELS

    if attempt.cohort_id is None:
        return {key: True for key, _ in DESIGN_STEP_LABELS}
    gates = await step_gates_for_mission(db, cohort_id=attempt.cohort_id, mission_id=attempt.mission_id)
    return {
        key: (gates[key].is_unlocked if key in gates else True)
        for key, _ in DESIGN_STEP_LABELS
    }


async def require_step_unlocked(db: AsyncSession, *, attempt: MissionAttempt, step_key: str) -> None:
    """Server-side enforcement — call at the top of each design write
    endpoint, right after the existing ownership check. A missing row or
    an attempt with no cohort_id means unlocked; only an explicit
    `is_unlocked=False` row blocks."""
    if attempt.cohort_id is None:
        return
    gate = await db.get(MissionStepGate, (attempt.cohort_id, attempt.mission_id, step_key))
    if gate is not None and not gate.is_unlocked:
        raise HTTPException(403, detail=f"Your instructor hasn't unlocked '{step_key}' yet")
