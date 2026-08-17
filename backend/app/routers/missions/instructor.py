"""Cohort-scoped instructor Missions surface (2026-08-17) —
`/missions/instructor/*`.

The boss's own ask (delivered 2026-08-16, alongside the August Build
Brief): instructors track and control their own cohort's Design mission
runs — progress, step-gating, review — without becoming ops/facilitator
generally. A deliberate reversal of Design v2 D1's "instructors stay out
of the mission entirely" call, this time shipped with the UI in the same
change so it can't go inert the way `design_step_gates` did the first time
(see `models/missions/gate.py`).

`instructor` gets a brand-new access path here — not an extension of
`/missions/admin`, which stays gated to operations/facilitator/admin
exactly as before. Cohort scoping is per-route, via
`services/missions/cohort_access.py::require_cohort_access` — staff bypass
it entirely (any cohort), an instructor is restricted to cohorts where
they hold a `SessionInstructor` row on one of that cohort's sessions.

Registered before `student_router` in `routers/missions/__init__.py` — the
same static-path-before-dynamic-`/missions/{mission_id}` reasoning
`/missions/manager` etc. already follow.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_instructor_missions
from app.db.session import get_db
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.missions.step_selection import MissionStepSelection
from app.models.missions.team import MissionTeam
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.user import User
from app.schemas.lms_progress_grid import ProgressGridOut
from app.schemas.missions_admin import MissionAttemptAdminOut, MissionAttemptReviewIn
from app.schemas.missions_instructor import (
    DesignStepSelectionOut, DesignStepSelectionsOut, DesignStepSelectionUpdateIn,
    InstructorCohortOut, MissionStepGateOut, MissionStepGateUpdateIn,
)
from app.services.lms.admin_progress import DESIGN_STEP_LABELS, DESIGN_STEP_PREREQS, DOWNLINK_STEP_DEPS, cohort_progress_grid
from app.services.missions.cohort_access import instructor_cohort_ids, require_cohort_access
from app.services.missions.gating import set_step_gate, step_gates_for_mission
from app.services.missions.step_selection import clear_selected_steps, selected_steps_for_cohort_mission, set_selected_steps
from app.services.missions.verifiers.submission import review_submission_attempt

router = APIRouter(
    prefix="/missions/instructor", tags=["missions-instructor"],
    dependencies=[Depends(require_instructor_missions)],
)


@router.get("/cohorts", response_model=list[InstructorCohortOut])
async def my_cohorts(db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user)):
    """Cohorts this instructor may act on — every cohort, for staff."""
    allowed = await instructor_cohort_ids(db, user=current)
    query = select(Cohort).join(Program, Program.id == Cohort.program_id).order_by(Cohort.name)
    if allowed is not None:
        if not allowed:
            return []
        query = query.where(Cohort.id.in_(allowed))
    rows = (await db.execute(query.add_columns(Program.name))).all()
    return [
        InstructorCohortOut(id=cohort.id, name=cohort.name, program_name=program_name, status=cohort.status)
        for cohort, program_name in rows
    ]


@router.get("/cohorts/{cohort_id}/progress", response_model=ProgressGridOut)
async def cohort_progress(
    cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    grid = await cohort_progress_grid(db, cohort_id=cohort_id)
    if grid is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    return grid


@router.get("/cohorts/{cohort_id}/missions/{mission_id}/gates", response_model=list[MissionStepGateOut])
async def get_step_gates(
    cohort_id: uuid.UUID, mission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    if await db.get(Mission, mission_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")
    gates = await step_gates_for_mission(db, cohort_id=cohort_id, mission_id=mission_id)
    out = []
    for key, label in DESIGN_STEP_LABELS:
        gate = gates.get(key)
        updated_by_name = None
        if gate is not None and gate.updated_by is not None:
            editor = await db.get(User, gate.updated_by)
            updated_by_name = editor.full_name if editor else None
        out.append(MissionStepGateOut(
            step_key=key, label=label,
            is_unlocked=gate.is_unlocked if gate is not None else False,
            updated_at=gate.updated_at if gate is not None else None,
            updated_by_name=updated_by_name,
        ))
    return out


@router.put("/cohorts/{cohort_id}/missions/{mission_id}/gates/{step_key}", response_model=MissionStepGateOut)
async def put_step_gate(
    cohort_id: uuid.UUID, mission_id: uuid.UUID, step_key: str, body: MissionStepGateUpdateIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    if await db.get(Mission, mission_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")
    if step_key not in dict(DESIGN_STEP_LABELS):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown step")
    gate = await set_step_gate(
        db, cohort_id=cohort_id, mission_id=mission_id, step_key=step_key,
        is_unlocked=body.is_unlocked, updated_by=current.id,
    )
    await db.commit()
    label = dict(DESIGN_STEP_LABELS)[step_key]
    return MissionStepGateOut(
        step_key=step_key, label=label, is_unlocked=gate.is_unlocked,
        updated_at=gate.updated_at, updated_by_name=current.full_name,
    )


def _step_selections_out(included: set[str], *, is_default: bool) -> DesignStepSelectionsOut:
    steps = [
        DesignStepSelectionOut(
            step_key=key, label=label, included=(key in included),
            prereqs=list(DESIGN_STEP_PREREQS.get(key, ())),
        )
        for key, label in DESIGN_STEP_LABELS if key != "downlink"
    ]
    return DesignStepSelectionsOut(
        is_default=is_default, steps=steps,
        downlink_deps=sorted(DOWNLINK_STEP_DEPS), downlink_included=DOWNLINK_STEP_DEPS <= included,
    )


@router.get("/cohorts/{cohort_id}/missions/{mission_id}/steps", response_model=DesignStepSelectionsOut)
async def get_step_selection(
    cohort_id: uuid.UUID, mission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    if await db.get(Mission, mission_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")
    has_rows = (await db.execute(
        select(MissionStepSelection.step_key).where(
            MissionStepSelection.cohort_id == cohort_id, MissionStepSelection.mission_id == mission_id,
        ).limit(1)
    )).scalar_one_or_none() is not None
    included = await selected_steps_for_cohort_mission(db, cohort_id=cohort_id, mission_id=mission_id)
    return _step_selections_out(included, is_default=not has_rows)


@router.put("/cohorts/{cohort_id}/missions/{mission_id}/steps", response_model=DesignStepSelectionsOut)
async def put_step_selection(
    cohort_id: uuid.UUID, mission_id: uuid.UUID, body: DesignStepSelectionUpdateIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    if await db.get(Mission, mission_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")
    included = await set_selected_steps(
        db, cohort_id=cohort_id, mission_id=mission_id, step_keys=body.step_keys, created_by=current.id,
    )
    await db.commit()
    return _step_selections_out(included, is_default=False)


@router.delete("/cohorts/{cohort_id}/missions/{mission_id}/steps", response_model=DesignStepSelectionsOut)
async def delete_step_selection(
    cohort_id: uuid.UUID, mission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    if await db.get(Mission, mission_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")
    await clear_selected_steps(db, cohort_id=cohort_id, mission_id=mission_id)
    await db.commit()
    included = await selected_steps_for_cohort_mission(db, cohort_id=cohort_id, mission_id=mission_id)
    return _step_selections_out(included, is_default=True)


async def _attempt_admin_out(db: AsyncSession, attempt: MissionAttempt) -> MissionAttemptAdminOut:
    mission = await db.get(Mission, attempt.mission_id)
    variant = await db.get(MissionVariant, attempt.variant_id)
    student = await db.get(User, attempt.user_id) if attempt.user_id else None
    team = await db.get(MissionTeam, attempt.mission_team_id) if attempt.mission_team_id else None
    return MissionAttemptAdminOut(
        id=attempt.id, mission_id=attempt.mission_id, mission_title=mission.title if mission else "",
        variant_id=attempt.variant_id, variant_label=variant.label if variant else "",
        user_id=attempt.user_id, student_name=student.full_name if student else None,
        team_id=attempt.mission_team_id, team_name=team.name if team else None,
        attempt_no=attempt.attempt_no, status=attempt.status,
        score=float(attempt.score) if attempt.score is not None else None, payload=attempt.payload or {},
        started_at=attempt.started_at, submitted_at=attempt.submitted_at, decided_at=attempt.decided_at,
    )


@router.get("/cohorts/{cohort_id}/missions/{mission_id}/queue", response_model=list[MissionAttemptAdminOut])
async def cohort_review_queue(
    cohort_id: uuid.UUID, mission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    if await db.get(Mission, mission_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")
    attempts = (await db.execute(
        select(MissionAttempt).where(
            MissionAttempt.mission_id == mission_id, MissionAttempt.cohort_id == cohort_id,
            MissionAttempt.status == "submitted",
        ).order_by(MissionAttempt.submitted_at)
    )).scalars().all()
    return [await _attempt_admin_out(db, a) for a in attempts]


@router.post("/attempts/{attempt_id}/review", response_model=MissionAttemptAdminOut)
async def instructor_review_attempt(
    attempt_id: uuid.UUID, body: MissionAttemptReviewIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await db.get(MissionAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    if attempt.cohort_id is None:
        # No instructor can act on an unattributed attempt — only staff,
        # which require_cohort_access already lets through unconditionally
        # below via its own staff bypass... except there's no cohort_id to
        # pass. Resolve that directly: staff always may, nobody else can.
        roles = current.role_values
        if "admin" not in roles and not ({"operations", "facilitator"} & set(roles)):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    else:
        await require_cohort_access(db, cohort_id=attempt.cohort_id, user=current)
    reviewed = await review_submission_attempt(
        db, attempt=attempt, reviewer_id=current.id, passed=body.passed,
        score=body.score, review_comment=body.review_comment,
    )
    await db.commit()
    await db.refresh(reviewed)
    return await _attempt_admin_out(db, reviewed)
