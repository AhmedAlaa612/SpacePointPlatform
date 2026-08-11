"""Mission authoring + review routes (P5-4) — `/missions/admin/*`, gated by
`require_lms_content` (same population as course authoring — operations +
facilitator; admin passes automatically).

Simple CRUD lives directly in the router, matching the established
`routers/lms/admin.py` convention. Variant `config` is validated per kind
before it's ever written: `quiz` reuses `AdminContentQuiz` (the same
validator LMS quiz items use, including the exactly-one-correct-option
rule); every other kind accepts free-form JSON for now (design's Stage 7
constraints row, submission's unused config).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_lms_content
from app.db.session import get_db
from app.models.missions.design import DesignStepGate
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.missions.team import MissionTeam
from app.models.user import User
from app.schemas.lms_admin import AdminContentQuiz
from app.schemas.missions_admin import (
    DesignStepGateOut,
    DesignStepGateUpdateIn,
    MissionAdminOut,
    MissionAttemptAdminOut,
    MissionAttemptReviewIn,
    MissionCreate,
    MissionTeamAdminOut,
    MissionTeamCreateAdminIn,
    MissionUpdate,
    MissionVariantAdminOut,
    MissionVariantCreate,
    MissionVariantUpdate,
)
from app.services import storage
from app.services.missions import create_team, team_member_ids
from app.services.missions.design.gating import GATED_STEPS
from app.services.missions.verifiers.submission import review_submission_attempt

_STEP_LABELS = {
    "data_budget": "Data Budget", "power_budget": "Power Budget", "link_budget": "Link Budget",
    "mass_budget": "Mass Budget", "cost_budget": "Cost Budget",
}

router = APIRouter(prefix="/missions/admin", tags=["missions-admin"], dependencies=[Depends(require_lms_content)])


def _validated_variant_config(*, mission_kind: str, config: dict) -> dict:
    if mission_kind != "quiz":
        return config
    try:
        parsed = AdminContentQuiz(**config)
    except ValidationError as exc:
        # include_context=False: the exactly-one-correct-option model_validator's
        # ValueError lands in ctx.error by default, which isn't JSON-serializable
        # (same fix routers/lms/admin.py::_validated_checkpoint_content uses).
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.errors(include_context=False))
    return parsed.model_dump()


async def _mission_admin_out(db: AsyncSession, mission: Mission) -> MissionAdminOut:
    image_url = await storage.resolve_url(mission.image_bucket, mission.image_path)
    author = await db.get(User, mission.authored_by)
    variants = (await db.execute(
        select(MissionVariant).where(MissionVariant.mission_id == mission.id).order_by(MissionVariant.position)
    )).scalars().all()
    return MissionAdminOut(
        id=mission.id, title=mission.title, slug=mission.slug, summary=mission.summary,
        description=mission.description, kind=mission.kind, team_policy=mission.team_policy,
        status=mission.status, access_mode=mission.access_mode, track=mission.track,
        image_url=image_url, authored_by=mission.authored_by,
        authored_by_name=author.full_name if author else None,
        reviewed_by=mission.reviewed_by, created_at=mission.created_at,
        variants=[
            MissionVariantAdminOut(id=v.id, label=v.label, position=v.position, points=v.points, config=v.config)
            for v in variants
        ],
    )


async def _get_mission_or_404(db: AsyncSession, mission_id: uuid.UUID) -> Mission:
    mission = await db.get(Mission, mission_id)
    if mission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")
    return mission


@router.get("", response_model=list[MissionAdminOut])
async def list_missions(db: AsyncSession = Depends(get_db)):
    missions = (await db.execute(select(Mission).order_by(Mission.created_at.desc()))).scalars().all()
    return [await _mission_admin_out(db, m) for m in missions]


@router.post("", response_model=MissionAdminOut, status_code=status.HTTP_201_CREATED)
async def create_mission(
    body: MissionCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_lms_content),
):
    existing = (await db.execute(select(Mission).where(Mission.slug == body.slug))).scalars().first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A mission with this slug already exists")
    mission = Mission(
        id=uuid.uuid4(), title=body.title, slug=body.slug, summary=body.summary, description=body.description,
        kind=body.kind, team_policy=body.team_policy, access_mode=body.access_mode, track=body.track,
        authored_by=current_user.id,
    )
    db.add(mission)
    await db.commit()
    await db.refresh(mission)
    return await _mission_admin_out(db, mission)


# ── team formation: ops-assign (P6-4) ────────────────────────────────────
# Registered before /{mission_id} on purpose: 'teams' is a static path that
# would otherwise be swallowed by the dynamic mission_id segment (same
# lesson as admin_router vs student_router in routers/missions/__init__.py).

async def _team_admin_out(db: AsyncSession, team: MissionTeam) -> MissionTeamAdminOut:
    member_ids = await team_member_ids(db, team_id=team.id)
    members = [await db.get(User, uid) for uid in member_ids]
    return MissionTeamAdminOut(
        id=team.id, name=team.name, cohort_id=team.cohort_id, member_ids=member_ids,
        member_names=[m.full_name for m in members if m is not None],
    )


@router.get("/teams", response_model=list[MissionTeamAdminOut])
async def list_teams(cohort_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)):
    query = select(MissionTeam).order_by(MissionTeam.created_at.desc())
    if cohort_id is not None:
        query = query.where(MissionTeam.cohort_id == cohort_id)
    teams = (await db.execute(query)).scalars().all()
    return [await _team_admin_out(db, t) for t in teams]


@router.post("/teams", response_model=MissionTeamAdminOut, status_code=status.HTTP_201_CREATED)
async def assign_team(
    body: MissionTeamCreateAdminIn, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lms_content),
):
    """Ops assigns a team from a cohort roster — MISSIONS_REPORT.md §Q5.
    Same `create_team` primitive self-form (student router) calls; only the
    caller and the required `cohort_id` differ."""
    team = await create_team(
        db, name=body.name, created_by=current_user.id, cohort_id=body.cohort_id, member_ids=body.member_ids,
    )
    await db.commit()
    await db.refresh(team)
    return await _team_admin_out(db, team)


# ── design step gates: server-side, per cohort (P7-7) ────────────────────
# Registered before /{mission_id} for the same routing-order reason as
# /teams above — 'design' would otherwise parse as a mission_id.

@router.get("/design/step-gates", response_model=list[DesignStepGateOut])
async def list_design_step_gates(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    rows = {
        g.step_key: g for g in (await db.execute(
            select(DesignStepGate).where(DesignStepGate.cohort_id == cohort_id)
        )).scalars().all()
    }
    return [
        DesignStepGateOut(step_key=key, label=_STEP_LABELS[key], is_unlocked=rows[key].is_unlocked if key in rows else False)
        for key in sorted(GATED_STEPS)
    ]


@router.put("/design/step-gates/{cohort_id}/{step_key}", response_model=DesignStepGateOut)
async def update_design_step_gate(
    cohort_id: uuid.UUID, step_key: str, body: DesignStepGateUpdateIn, db: AsyncSession = Depends(get_db),
):
    if step_key not in GATED_STEPS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"'{step_key}' is not a gated step")
    gate = await db.get(DesignStepGate, (cohort_id, step_key))
    if gate is None:
        gate = DesignStepGate(cohort_id=cohort_id, step_key=step_key, is_unlocked=body.is_unlocked)
        db.add(gate)
    else:
        gate.is_unlocked = body.is_unlocked
    await db.commit()
    return DesignStepGateOut(step_key=step_key, label=_STEP_LABELS[step_key], is_unlocked=gate.is_unlocked)


@router.get("/{mission_id}", response_model=MissionAdminOut)
async def get_mission(mission_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    mission = await _get_mission_or_404(db, mission_id)
    return await _mission_admin_out(db, mission)


@router.patch("/{mission_id}", response_model=MissionAdminOut)
async def update_mission(mission_id: uuid.UUID, body: MissionUpdate, db: AsyncSession = Depends(get_db)):
    mission = await _get_mission_or_404(db, mission_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(mission, field, value)
    await db.commit()
    await db.refresh(mission)
    return await _mission_admin_out(db, mission)


@router.post("/{mission_id}/variants", response_model=MissionVariantAdminOut, status_code=status.HTTP_201_CREATED)
async def create_variant(mission_id: uuid.UUID, body: MissionVariantCreate, db: AsyncSession = Depends(get_db)):
    mission = await _get_mission_or_404(db, mission_id)
    config = _validated_variant_config(mission_kind=mission.kind, config=body.config)
    variant = MissionVariant(
        id=uuid.uuid4(), mission_id=mission.id, label=body.label, position=body.position,
        points=body.points, config=config,
    )
    db.add(variant)
    await db.commit()
    await db.refresh(variant)
    return MissionVariantAdminOut(
        id=variant.id, label=variant.label, position=variant.position, points=variant.points, config=variant.config,
    )


@router.patch("/{mission_id}/variants/{variant_id}", response_model=MissionVariantAdminOut)
async def update_variant(
    mission_id: uuid.UUID, variant_id: uuid.UUID, body: MissionVariantUpdate, db: AsyncSession = Depends(get_db),
):
    mission = await _get_mission_or_404(db, mission_id)
    variant = await db.get(MissionVariant, variant_id)
    if variant is None or variant.mission_id != mission.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Variant not found")
    updates = body.model_dump(exclude_unset=True)
    if "config" in updates:
        updates["config"] = _validated_variant_config(mission_kind=mission.kind, config=updates["config"])
    for field, value in updates.items():
        setattr(variant, field, value)
    await db.commit()
    await db.refresh(variant)
    return MissionVariantAdminOut(
        id=variant.id, label=variant.label, position=variant.position, points=variant.points, config=variant.config,
    )


# ── review queue (submission kind) ──────────────────────────────────────

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


@router.get("/attempts/queue", response_model=list[MissionAttemptAdminOut])
async def review_queue(db: AsyncSession = Depends(get_db)):
    """Attempts awaiting a human decision — always `submitted` (a `quiz`
    attempt never lingers there, it self-decides on submit)."""
    attempts = (await db.execute(
        select(MissionAttempt).where(MissionAttempt.status == "submitted").order_by(MissionAttempt.submitted_at)
    )).scalars().all()
    return [await _attempt_admin_out(db, a) for a in attempts]


@router.post("/attempts/{attempt_id}/review", response_model=MissionAttemptAdminOut)
async def review_attempt(
    attempt_id: uuid.UUID, body: MissionAttemptReviewIn,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_lms_content),
):
    attempt = await db.get(MissionAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    reviewed = await review_submission_attempt(
        db, attempt=attempt, reviewer_id=current_user.id, passed=body.passed,
        score=body.score, review_comment=body.review_comment,
    )
    await db.commit()
    await db.refresh(reviewed)
    return await _attempt_admin_out(db, reviewed)
