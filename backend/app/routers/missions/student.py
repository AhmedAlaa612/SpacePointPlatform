"""Mission student routes (P5-4/P6-4) — `/missions/*`.

Standalone catalog only lists `published` + `access_mode == 'open'`
missions — `invite` missions carry no grant table of their own (unlike
courses' `enrollments`) and are reachable only through course embedding
(P5-5), where the *course's* enrollment already gates who gets there. That
reuses the existing entitlement path instead of building a second one
(mirrors the Stage S note: "avoids a second entitlement path"). Not-found
and not-open-yet both read as a flat 404 — same don't-leak-existence
posture as `routers/lms/student.py`.

Prerequisite gating (P5-6, unified across item kinds by 7B-2): the
`prerequisites` DAG (`models/curriculum.py`) stores edges,
`services/curriculum.py` evaluates them. `access_mode` decides eligibility
(a grant — is this mission visible at all); prerequisites decide readiness
(a computed rule — has this student earned the right to attempt it). Two
different mechanisms, not collapsed (Stage 5 note ②). An unrelated mission
(no edges naming it) has an empty prerequisite set and is always available.

Team formation (P6-4): self-form here is the same `create_team` primitive
ops-assign (`routers/missions/admin.py`) calls, just without a `cohort_id`
— "both write the same rows" (MISSIONS_REPORT.md §Q5). `/teams` and
`/teams/mine` are registered before `/{mission_id}` for the same static-
before-dynamic routing-order reason `/graph` already is.
"""

import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.curriculum import Prerequisite
from app.models.missions.design import Design
from app.models.missions.mission import Mission, MissionAttempt, MissionAttemptMember, MissionVariant
from app.models.team import Team
from app.models.user import User
from app.schemas.curriculum import PrerequisiteItemOut
from app.schemas.missions import (
    MissionAttemptOut,
    MissionAttemptStartIn,
    MissionAttemptSubmitIn,
    MissionAttemptSubmitOut,
    MissionCatalogOut,
    MissionDetailOut,
    MissionGraphNodeOut,
    MissionQuizReviewOut,
    MissionVariantOut,
    MissionVariantSummaryOut,
)
from app.schemas.teams import TeamCreateIn, TeamOut
from app.services import storage
from app.services.curriculum import is_unlocked, prerequisite_status
from app.services.missions import resolve_student_cohort, start_attempt
from app.services.missions.serialize import variant_student_view
from app.services.teams import create_team, team_member_ids, teams_for_user
from app.services.missions.verifiers.quiz import submit_quiz_attempt
from app.services.missions.verifiers.submission import submit_submission_attempt

router = APIRouter(prefix="/missions", tags=["missions"])


async def _open_mission(db: AsyncSession, mission_id: uuid.UUID) -> Mission:
    mission = await db.get(Mission, mission_id)
    if mission is None or mission.status != "published" or mission.access_mode != "open":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")
    return mission


async def _team_out(db: AsyncSession, team: Team) -> TeamOut:
    member_ids = await team_member_ids(db, team_id=team.id)
    members = [await db.get(User, uid) for uid in member_ids]
    return TeamOut(
        id=team.id, name=team.name, cohort_id=team.cohort_id, member_ids=member_ids,
        member_names=[m.full_name for m in members if m is not None],
    )


async def _attempt_out(
    db: AsyncSession, attempt: MissionAttempt, *, variant_label: str, design_name: str | None = None,
) -> MissionAttemptOut:
    team_name = None
    if attempt.team_id is not None:
        team = await db.get(Team, attempt.team_id)
        team_name = team.name if team else None
    return MissionAttemptOut(
        id=attempt.id, mission_id=attempt.mission_id, variant_id=attempt.variant_id,
        variant_label=variant_label, attempt_no=attempt.attempt_no, status=attempt.status,
        score=float(attempt.score) if attempt.score is not None else None, payload=attempt.payload or {},
        started_at=attempt.started_at, submitted_at=attempt.submitted_at, decided_at=attempt.decided_at,
        team_id=attempt.team_id, team_name=team_name, design_name=design_name,
    )


@router.get("", response_model=list[MissionCatalogOut])
async def mission_catalog(db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user)):
    missions = (await db.execute(
        select(Mission).where(Mission.status == "published", Mission.access_mode == "open")
        .order_by(Mission.created_at.desc())
    )).scalars().all()
    out = []
    for mission in missions:
        variants = (await db.execute(
            select(MissionVariant).where(MissionVariant.mission_id == mission.id).order_by(MissionVariant.position)
        )).scalars().all()
        out.append(MissionCatalogOut(
            id=mission.id, title=mission.title, slug=mission.slug, summary=mission.summary,
            kind=mission.kind, track=mission.track,
            image_url=await storage.resolve_url(mission.image_bucket, mission.image_path),
            variants=[
                MissionVariantSummaryOut(id=v.id, label=v.label, position=v.position, points=v.points)
                for v in variants
            ],
            locked=not await is_unlocked(db, item_type="mission", item_id=mission.id, user_id=current.id),
            team_policy=mission.team_policy,
        ))
    return out


@router.get("/graph", response_model=list[MissionGraphNodeOut])
async def mission_graph(db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user)):
    """The constellation view's data — every open mission plus its
    mission-to-mission prerequisite edges and this student's own lock state.
    A mission can require a course too since 7B-2, but that edge has no
    node to draw an arrow to in a mission-only constellation, so this view
    stays scoped to mission->mission edges — `locked` still reflects every
    prerequisite (course or mission), only the drawn graph is narrower than
    the full DAG. Registered before `/{mission_id}` on purpose: 'graph'
    would otherwise parse as a mission_id and 422 (same routing-order lesson
    as admin_router vs student_router in routers/missions/__init__.py)."""
    missions = (await db.execute(
        select(Mission).where(Mission.status == "published", Mission.access_mode == "open")
        .order_by(Mission.created_at.desc())
    )).scalars().all()
    mission_ids = [m.id for m in missions]
    edges = (await db.execute(
        select(Prerequisite).where(
            Prerequisite.item_type == "mission", Prerequisite.item_id.in_(mission_ids),
            Prerequisite.requires_type == "mission",
        )
    )).scalars().all()
    requires_by_mission: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for edge in edges:
        requires_by_mission[edge.item_id].append(edge.requires_id)

    out = []
    for mission in missions:
        out.append(MissionGraphNodeOut(
            id=mission.id, title=mission.title, kind=mission.kind, track=mission.track,
            locked=not await is_unlocked(db, item_type="mission", item_id=mission.id, user_id=current.id),
            requires=requires_by_mission.get(mission.id, []),
        ))
    return out


# ── team formation: self-form (P6-4) ─────────────────────────────────────

@router.post("/teams", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def form_team(
    body: TeamCreateIn, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Self-form from the public catalog — no `cohort_id` (MISSIONS_REPORT.md
    §Q5). Same `create_team` primitive ops-assign calls."""
    team = await create_team(db, name=body.name, created_by=current.id, member_ids=body.member_ids)
    await db.commit()
    await db.refresh(team)
    return await _team_out(db, team)


@router.get("/teams/mine", response_model=list[TeamOut])
async def my_teams(db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user)):
    teams = await teams_for_user(db, user_id=current.id)
    return [await _team_out(db, t) for t in teams]


@router.get("/{mission_id}", response_model=MissionDetailOut)
async def mission_detail(
    mission_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    mission = await _open_mission(db, mission_id)
    variants = (await db.execute(
        select(MissionVariant).where(MissionVariant.mission_id == mission.id).order_by(MissionVariant.position)
    )).scalars().all()
    variant_by_id = {v.id: v for v in variants}
    attempts = (await db.execute(
        select(MissionAttempt).where(
            MissionAttempt.mission_id == mission.id,
            or_(
                MissionAttempt.user_id == current.id,
                MissionAttempt.id.in_(
                    select(MissionAttemptMember.attempt_id).where(MissionAttemptMember.user_id == current.id)
                ),
            ),
        ).order_by(MissionAttempt.attempt_no)
    )).scalars().all()
    prereqs = await prerequisite_status(db, item_type="mission", item_id=mission.id, user_id=current.id)
    my_team_rows = await teams_for_user(db, user_id=current.id) if mission.team_policy != "solo" else []
    # Design-kind only: one query for every attempt's design name rather than
    # N — mission.kind is fixed per mission, so this is empty/skipped for
    # every other kind.
    design_name_by_attempt: dict[uuid.UUID, str] = {}
    if mission.kind == "design" and attempts:
        design_name_by_attempt = dict((await db.execute(
            select(Design.attempt_id, Design.design_name).where(
                Design.attempt_id.in_([a.id for a in attempts])
            )
        )).all())
    return MissionDetailOut(
        id=mission.id, title=mission.title, slug=mission.slug, summary=mission.summary,
        description=mission.description, kind=mission.kind, track=mission.track,
        image_url=await storage.resolve_url(mission.image_bucket, mission.image_path),
        variants=[MissionVariantOut(**variant_student_view(v, kind=mission.kind)) for v in variants],
        attempts=[
            await _attempt_out(
                db, a, variant_label=variant_by_id[a.variant_id].label if a.variant_id in variant_by_id else "",
                design_name=design_name_by_attempt.get(a.id),
            )
            for a in attempts
        ],
        prerequisites=[PrerequisiteItemOut(**p) for p in prereqs],
        locked=not all(p["satisfied"] for p in prereqs),
        team_policy=mission.team_policy,
        my_teams=[await _team_out(db, t) for t in my_team_rows],
    )


@router.post("/{mission_id}/attempts", response_model=MissionAttemptOut, status_code=status.HTTP_201_CREATED)
async def start_mission_attempt(
    mission_id: uuid.UUID, body: MissionAttemptStartIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    mission = await _open_mission(db, mission_id)
    variant = await db.get(MissionVariant, body.variant_id)
    if variant is None or variant.mission_id != mission.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Variant not found")
    if not await is_unlocked(db, item_type="mission", item_id=mission.id, user_id=current.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Complete the required missions first")

    if body.team_id is not None:
        if mission.team_policy == "solo":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This mission is solo only")
        team = await db.get(Team, body.team_id)
        if team is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found")
        if current.id not in await team_member_ids(db, team_id=team.id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You are not a member of this team")
        attempt = await start_attempt(
            db, mission_id=mission.id, variant_id=body.variant_id, team_id=body.team_id,
            force_new=body.force_new, cohort_id=team.cohort_id,
        )
    else:
        if mission.team_policy == "team":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This mission requires a team")
        cohort_id = await resolve_student_cohort(db, user_id=current.id)
        attempt = await start_attempt(
            db, mission_id=mission.id, variant_id=body.variant_id, user_id=current.id,
            force_new=body.force_new, cohort_id=cohort_id,
        )

    await db.commit()
    await db.refresh(attempt)
    active_variant = await db.get(MissionVariant, attempt.variant_id)
    return await _attempt_out(db, attempt, variant_label=active_variant.label if active_variant else "")


async def _own_attempt(db: AsyncSession, attempt_id: uuid.UUID, user: User) -> MissionAttempt:
    """"Own" means the caller is either the solo student, or (P6-2) a
    member of the frozen `mission_attempt_members` snapshot for a team
    attempt — any teammate can view/submit on the team's behalf."""
    attempt = await db.get(MissionAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    if attempt.user_id == user.id:
        return attempt
    if attempt.team_id is not None:
        member = await db.get(MissionAttemptMember, (attempt.id, user.id))
        if member is not None:
            return attempt
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attempt not found")


@router.get("/attempts/{attempt_id}", response_model=MissionAttemptOut)
async def get_mission_attempt(
    attempt_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_attempt(db, attempt_id, current)
    variant = await db.get(MissionVariant, attempt.variant_id)
    return await _attempt_out(db, attempt, variant_label=variant.label if variant else "")


@router.post("/attempts/{attempt_id}/submit", response_model=MissionAttemptSubmitOut)
async def submit_mission_attempt(
    attempt_id: uuid.UUID, body: MissionAttemptSubmitIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_attempt(db, attempt_id, current)
    mission = await db.get(Mission, attempt.mission_id)
    variant = await db.get(MissionVariant, attempt.variant_id)

    if mission.kind == "quiz":
        if body.answers is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="answers is required for a quiz mission")
        decided, graded = await submit_quiz_attempt(db, attempt=attempt, variant=variant, answers=body.answers)
        await db.commit()
        await db.refresh(decided)
        return MissionAttemptSubmitOut(
            attempt=await _attempt_out(db, decided, variant_label=variant.label),
            review=MissionQuizReviewOut(score=graded["score"], passed=graded["passed"], questions=graded["questions"]),
        )

    if mission.kind == "submission":
        if not body.artifact_url:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="artifact_url is required for a submission mission")
        submitted = await submit_submission_attempt(
            db, attempt=attempt, artifact_url=body.artifact_url, notes=body.notes,
        )
        await db.commit()
        await db.refresh(submitted)
        return MissionAttemptSubmitOut(
            attempt=await _attempt_out(db, submitted, variant_label=variant.label), review=None,
        )

    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Mission kind '{mission.kind}' has no submit flow yet")
