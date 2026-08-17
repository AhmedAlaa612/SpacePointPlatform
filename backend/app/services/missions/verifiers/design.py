"""The `design` mission kind (P7) — CubeSat mission design, ported from
Madar. Unlike `submission`/`quiz`, this kind is iterative: a student saves
components/CONOPS/budgets freely while `in_progress`, any number of times,
in any order, over hours or weeks (MISSIONS_REPORT.md §1.1 — Madar's own
"mission" is "hours to weeks", not "minutes to days"). There is no
resubmit-is-terminal shape here: `mark_design_complete` only ever
transitions `in_progress -> passed`, never to `failed` — an incomplete or
invalid design just stays `in_progress` with a clear reason why, so a
student never loses work by checking too early (contrast with quiz/
submission, where a discrete wrong answer or artifact genuinely is a
terminal outcome for that attempt).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.missions.design import report as design_report
from app.models.missions.design import Design
from app.models.missions.mission import MissionAttempt, MissionVariant
from app.services.missions.attempts import decide_attempt
from app.services.missions.design.service import compute_dashboard


async def ensure_design(db: AsyncSession, *, attempt: MissionAttempt, design_name: str = "My CubeSat") -> Design:
    """Get-or-create the 1:1 Design row for this attempt — mirrors the
    idempotent-create pattern Madar's own `_ensure_constraint`/
    `_ensure_entry` used, just keyed on attempt_id instead of mission_id.
    `cohort_id` mirrors `attempt.cohort_id` (2026-08-17) — already resolved
    eagerly at `start_attempt()` time for both solo and team attempts, so
    the two columns can never disagree. `Design.cohort_id` used to resolve
    this independently and lazily, solo-only; that's gone."""
    design = (await db.execute(select(Design).where(Design.attempt_id == attempt.id))).scalars().first()
    if design is not None:
        return design
    design = Design(id=uuid.uuid4(), attempt_id=attempt.id, design_name=design_name, cohort_id=attempt.cohort_id)
    db.add(design)
    await db.flush()
    return design


async def mark_design_complete(db: AsyncSession, *, attempt: MissionAttempt) -> tuple[MissionAttempt, dict]:
    """Checks the full dashboard; only decides the attempt (passed) if
    every step is valid. An invalid or incomplete design raises 400 with
    the dashboard attached so the caller can show exactly what's missing —
    it never flips the attempt to `failed` or consumes an attempt_no."""
    if attempt.status != "in_progress":
        raise HTTPException(409, detail=f"Attempt is '{attempt.status}', not 'in_progress'")

    design = (await db.execute(select(Design).where(Design.attempt_id == attempt.id))).scalars().first()
    if design is None:
        raise HTTPException(400, detail="No design started yet")

    variant = await db.get(MissionVariant, attempt.variant_id)
    dashboard = await compute_dashboard(db, design=design, variant_config=variant.config or {}, attempt=attempt)

    if not dashboard["all_valid"]:
        raise HTTPException(400, detail={"message": "Design is not ready yet", "steps": {
            k: {"has_data": v["has_data"], "is_valid": v["is_valid"]} for k, v in dashboard["steps"].items()
        }})

    # Design v2 (7D-6) — freeze the review into the attempt. A design that
    # is opened next week must show the numbers it was actually graded on,
    # even if the variant's thresholds or the component library have been
    # edited since. Same discipline the operate mission's debrief uses, and
    # the same F2 lesson this port already learned once for component specs.
    thresholds = dashboard["thresholds"]
    limits = dashboard["cubesat_limits"]
    margins = design_report.build_margins(dashboard, thresholds, limits)
    alerts, recommendations = design_report.build_advice(dashboard, margins)
    attempt.payload = {
        **(attempt.payload or {}),
        "review": {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "variant_label": variant.label if variant else None,
            "design_name": design.design_name,
            "overall": design_report.overall_status(dashboard, margins),
            "margins": margins,
            "alerts": alerts,
            "recommendations": recommendations,
            "thresholds": thresholds,
            "limits": limits,
        },
    }
    await db.flush()

    decided = await decide_attempt(db, attempt=attempt, passed=True, score=100)
    return decided, dashboard
