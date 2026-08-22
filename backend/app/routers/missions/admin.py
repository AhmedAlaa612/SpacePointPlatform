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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_lms_content
from app.db.session import get_db
from app.models.missions.assignment import MissionAssignment
from app.models.missions.manager import MissionManager
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.team import Team
from app.models.user import User
from app.schemas.lms_admin import AdminContentQuiz
from app.schemas.missions_admin import (
    MissionAdminOut,
    MissionAssignmentGrantIn,
    MissionAssignmentOut,
    MissionAttemptAdminOut,
    MissionAttemptAssignIn,
    MissionAttemptReviewIn,
    MissionBulkAssignIn,
    MissionBulkAssignOut,
    MissionCreate,
    MissionTeamAdminOut,
    MissionTeamCreateAdminIn,
    MissionUpdate,
    MissionVariantAdminOut,
    MissionVariantCreate,
    MissionVariantUpdate,
)
from app.schemas.missions_manager import MissionManagerAssignIn, MissionManagerOut
from app.services import storage
from app.services.teams import create_team, team_member_ids
from app.services.missions import assign_mission_run
from app.services.missions.assignment import assign as assign_mission
from app.services.missions.verifiers.submission import review_submission_attempt

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

async def _team_admin_out(db: AsyncSession, team: Team) -> MissionTeamAdminOut:
    member_ids = await team_member_ids(db, team_id=team.id)
    members = [await db.get(User, uid) for uid in member_ids]
    return MissionTeamAdminOut(
        id=team.id, name=team.name, cohort_id=team.cohort_id, member_ids=member_ids,
        member_names=[m.full_name for m in members if m is not None],
    )


@router.get("/teams", response_model=list[MissionTeamAdminOut])
async def list_teams(cohort_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)):
    query = select(Team).order_by(Team.created_at.desc())
    if cohort_id is not None:
        query = query.where(Team.cohort_id == cohort_id)
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


@router.delete("/{mission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mission(mission_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Refuses if any attempt has ever been made (mirrors `delete_course`'s
    guard, `routers/lms/admin.py`) — a mission with attempt history has real
    student work behind it; archive it via `status` instead. Nothing else
    references a mission with no attempts, so it cascades cleanly (variants,
    managers, assignments)."""
    mission = await _get_mission_or_404(db, mission_id)

    attempt_count = await db.scalar(
        select(func.count()).select_from(MissionAttempt).where(MissionAttempt.mission_id == mission_id)
    )
    if attempt_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"This mission has {attempt_count} attempt(s) and can't be deleted. Archive it instead.",
        )

    await db.delete(mission)
    await db.commit()


# ── mission managers (7B-7) — resource-scoped permission, staff-assigned ──

async def _manager_out(db: AsyncSession, manager: MissionManager) -> MissionManagerOut:
    user = await db.get(User, manager.user_id)
    return MissionManagerOut(
        user_id=manager.user_id, full_name=user.full_name if user else "(deleted user)",
        granted_by=manager.granted_by, created_at=manager.created_at,
    )


@router.get("/{mission_id}/managers", response_model=list[MissionManagerOut])
async def list_mission_managers(mission_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_mission_or_404(db, mission_id)
    rows = (await db.execute(
        select(MissionManager).where(MissionManager.mission_id == mission_id)
    )).scalars().all()
    return [await _manager_out(db, m) for m in rows]


@router.post("/{mission_id}/managers", response_model=MissionManagerOut, status_code=status.HTTP_201_CREATED)
async def assign_mission_manager(
    mission_id: uuid.UUID, body: MissionManagerAssignIn,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_lms_content),
):
    await _get_mission_or_404(db, mission_id)
    if await db.get(User, body.user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    existing = await db.get(MissionManager, (mission_id, body.user_id))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Already a manager of this mission")
    manager = MissionManager(mission_id=mission_id, user_id=body.user_id, granted_by=current_user.id)
    db.add(manager)
    await db.commit()
    await db.refresh(manager)
    return await _manager_out(db, manager)


@router.delete("/{mission_id}/managers/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_mission_manager(mission_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    manager = await db.get(MissionManager, (mission_id, user_id))
    if manager is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not a manager of this mission")
    await db.delete(manager)
    await db.commit()


# ── mission assignment (2026-08-12) — bookkeeping, not a gate ────────────
# Mirrors the enrollment grant/bulk/revoke/roster shape in
# routers/lms/admin.py. Purely additive to `access_mode`: whether an
# `invite` mission should require a row here before `MissionAttempt`
# creation is an open question, deliberately not decided here — this is
# just the admin-facing "who has this been given to" list.

async def _assignment_out(db: AsyncSession, assignment: MissionAssignment) -> MissionAssignmentOut:
    user = await db.get(User, assignment.user_id)
    return MissionAssignmentOut(
        id=assignment.id, user_id=assignment.user_id,
        user_name=user.full_name if user else "(deleted user)",
        user_email=user.email if user else "",
        mission_id=assignment.mission_id, source=assignment.source, status=assignment.status,
        granted_by=assignment.granted_by, created_at=assignment.created_at,
    )


@router.get("/{mission_id}/roster", response_model=list[MissionAssignmentOut])
async def mission_roster(mission_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_mission_or_404(db, mission_id)
    rows = (await db.execute(
        select(MissionAssignment).where(MissionAssignment.mission_id == mission_id)
        .order_by(MissionAssignment.created_at.desc())
    )).scalars().all()
    return [await _assignment_out(db, a) for a in rows]


@router.post(
    "/{mission_id}/assignments", response_model=MissionAssignmentOut, status_code=status.HTTP_201_CREATED,
)
async def grant_mission_assignment(
    mission_id: uuid.UUID, body: MissionAssignmentGrantIn,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_lms_content),
):
    if await db.get(User, body.user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    assignment = await assign_mission(db, user_id=body.user_id, mission_id=mission_id, granted_by=current_user.id)
    await db.commit()
    return await _assignment_out(db, assignment)


@router.post("/{mission_id}/assignments/bulk", response_model=MissionBulkAssignOut)
async def bulk_grant_mission_assignment(
    mission_id: uuid.UUID, body: MissionBulkAssignIn,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_lms_content),
):
    """Every user holding `body.role` — role-only, missions have no cohort
    curriculum table the way courses do."""
    await _get_mission_or_404(db, mission_id)
    user_ids = list((await db.execute(select(User.id).where(User.roles.any(body.role)))).scalars().all())

    granted = already_assigned = 0
    for user_id in user_ids:
        existing = (await db.execute(
            select(MissionAssignment.id).where(
                MissionAssignment.user_id == user_id, MissionAssignment.mission_id == mission_id,
                MissionAssignment.status == "active",
            )
        )).first()
        if existing is not None:
            already_assigned += 1
            continue
        await assign_mission(db, user_id=user_id, mission_id=mission_id, granted_by=current_user.id)
        granted += 1

    await db.commit()
    return MissionBulkAssignOut(granted=granted, already_assigned=already_assigned)


@router.post("/assignments/{assignment_id}/revoke", response_model=MissionAssignmentOut)
async def revoke_mission_assignment(assignment_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    assignment = await db.get(MissionAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    assignment.status = "inactive"
    await db.commit()
    return await _assignment_out(db, assignment)


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
    # D8 (Design v2) — grading criteria are frozen while a mission is
    # published. Editing a threshold on a live mission retroactively
    # changes what an already-graded attempt was measured against, which is
    # exactly the class of bug this port fixed once already for Madar's
    # component library (F2/F4). Explanatory *content* is a different thing
    # and stays editable — see `/missions/manager/{id}/content`.
    frozen = {"config", "points"} & set(updates)
    if frozen and mission.status == "published":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"{', '.join(sorted(frozen))} cannot change while this mission is published — "
                   f"move it back to draft first. Briefing and handbook content stays editable.",
        )
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
    team = await db.get(Team, attempt.team_id) if attempt.team_id else None
    return MissionAttemptAdminOut(
        id=attempt.id, mission_id=attempt.mission_id, mission_title=mission.title if mission else "",
        variant_id=attempt.variant_id, variant_label=variant.label if variant else "",
        user_id=attempt.user_id, student_name=student.full_name if student else None,
        team_id=attempt.team_id, team_name=team.name if team else None,
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


# ── cohort-scoped run assignment (2026-08-21, LMS Program redesign) ─────────

@router.post("/attempts/assign", response_model=MissionAttemptAdminOut, status_code=status.HTTP_201_CREATED)
async def assign_mission_attempt(
    body: MissionAttemptAssignIn, db: AsyncSession = Depends(get_db),
):
    """The one way a solo attempt gets a `cohort_id` now — student-started
    attempts (`POST /missions/{id}/attempts`) are always independent.
    Used directly for cohort-scoped missions with no full LMS Program
    (e.g. TDRA's reduced step selection), and internally by
    `services/lms/program.py::assign_lms_program` for a checklist's
    `mission_run` items. Idempotent: re-assigning the same student just
    resumes their existing in-progress run unless `force_new=True`."""
    if await db.get(User, body.user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    if await db.get(Mission, body.mission_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")
    if await db.get(Cohort, body.cohort_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    attempt = await assign_mission_run(
        db, mission_id=body.mission_id, user_id=body.user_id, cohort_id=body.cohort_id,
        variant_id=body.variant_id, force_new=body.force_new,
    )
    await db.commit()
    await db.refresh(attempt)
    return await _attempt_admin_out(db, attempt)
