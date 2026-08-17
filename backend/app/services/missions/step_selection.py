"""Per-cohort Design-mission step *selection* (2026-08-17) — which of the 9
build steps even apply to a cohort's run, distinct from `gating.py`'s
temporal lock/unlock. Real-world driver: the TDRA Summer Camp cohort, which
only needs Components/Power/Mass, skipping Data Budget and Communication
(Link + Downlink) entirely — see `DESIGN_STEP_PREREQS` in
`app/services/lms/admin_progress.py` for the verified real math dependency
graph this module expands against.

A missing row set for a `(cohort_id, mission_id)` pair means "no selection
configured, all 8 steps included" — every cohort that never touches this
feature keeps behaving exactly as before this module existed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.mission import MissionAttempt
from app.models.missions.step_selection import MissionStepSelection


def expand_with_prereqs(selected: set[str]) -> set[str]:
    """Closure of `selected` over `DESIGN_STEP_PREREQS` — pulls in every
    real prerequisite, transitively. Raises on an unknown or non-selectable
    key (including `"downlink"`, which is a derived check, not a step)."""
    from app.services.lms.admin_progress import DESIGN_STEP_PREREQS, SELECTABLE_STEP_KEYS

    unknown = selected - SELECTABLE_STEP_KEYS
    if unknown:
        raise HTTPException(400, detail=f"Unknown step(s): {sorted(unknown)}")

    result: set[str] = set()
    stack = list(selected)
    while stack:
        key = stack.pop()
        if key in result:
            continue
        result.add(key)
        stack.extend(DESIGN_STEP_PREREQS[key])
    return result


async def selected_steps_for_cohort_mission(
    db: AsyncSession, *, cohort_id: uuid.UUID, mission_id: uuid.UUID,
) -> set[str]:
    """The resolved included-step set. No rows -> every selectable step —
    the single place this default lives; everything else consumes it."""
    from app.services.lms.admin_progress import SELECTABLE_STEP_KEYS

    rows = (await db.execute(
        select(MissionStepSelection.step_key).where(
            MissionStepSelection.cohort_id == cohort_id, MissionStepSelection.mission_id == mission_id,
        )
    )).scalars().all()
    if not rows:
        return set(SELECTABLE_STEP_KEYS)
    return set(rows)


async def set_selected_steps(
    db: AsyncSession, *, cohort_id: uuid.UUID, mission_id: uuid.UUID,
    step_keys: list[str], created_by: uuid.UUID,
) -> set[str]:
    """Replace-the-whole-set write. `step_keys` is the desired *direct*
    selection — this always re-expands prerequisites server-side, so a
    client can never persist a dependency-incomplete set regardless of
    what it pre-computed for its own UI."""
    if not step_keys:
        raise HTTPException(400, detail="Select at least one step")
    expanded = expand_with_prereqs(set(step_keys))

    await db.execute(
        delete(MissionStepSelection).where(
            MissionStepSelection.cohort_id == cohort_id, MissionStepSelection.mission_id == mission_id,
        )
    )
    now = datetime.now(timezone.utc)
    for key in expanded:
        db.add(MissionStepSelection(
            cohort_id=cohort_id, mission_id=mission_id, step_key=key,
            created_at=now, created_by=created_by,
        ))
    await db.flush()
    return expanded


async def clear_selected_steps(db: AsyncSession, *, cohort_id: uuid.UUID, mission_id: uuid.UUID) -> None:
    """Reset to the default (all steps included) by removing every row."""
    await db.execute(
        delete(MissionStepSelection).where(
            MissionStepSelection.cohort_id == cohort_id, MissionStepSelection.mission_id == mission_id,
        )
    )
    await db.flush()


async def selected_steps_for_attempt(db: AsyncSession, *, attempt: MissionAttempt) -> set[str]:
    """The included-step set for one attempt's wizard/completion check. An
    attempt with no cohort (self-service, outside any workshop) is never
    scoped — every step is included, mirroring `gate_map_for_attempt`."""
    from app.services.lms.admin_progress import SELECTABLE_STEP_KEYS

    if attempt.cohort_id is None:
        return set(SELECTABLE_STEP_KEYS)
    return await selected_steps_for_cohort_mission(db, cohort_id=attempt.cohort_id, mission_id=attempt.mission_id)
