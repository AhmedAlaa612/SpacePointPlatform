"""Mission student routes (P5-4) — `/missions/*`.

Standalone catalog only lists `published` + `access_mode == 'open'`
missions — `invite` missions carry no grant table of their own (unlike
courses' `enrollments`) and are reachable only through course embedding
(P5-5), where the *course's* enrollment already gates who gets there. That
reuses the existing entitlement path instead of building a second one
(mirrors the Stage S note: "avoids a second entitlement path"). Not-found
and not-open-yet both read as a flat 404 — same don't-leak-existence
posture as `routers/lms/student.py`.

Prerequisite gating (P5-6): `mission_prerequisites` stores DAG edges (P5-1),
`services/missions/prerequisites.py` evaluates them. `access_mode` decides
eligibility (a grant — is this mission visible at all); prerequisites
decide readiness (a computed rule — has this student earned the right to
attempt it). Two different mechanisms, not collapsed (Stage 5 note ②). An
unrelated mission (no edges naming it) has an empty prerequisite set and is
always available.
"""

import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.models.missions.mission import Mission, MissionAttempt, MissionPrerequisite, MissionVariant
from app.db.session import get_db
from app.models.user import User
from app.schemas.missions import (
    MissionAttemptOut,
    MissionAttemptStartIn,
    MissionAttemptSubmitIn,
    MissionAttemptSubmitOut,
    MissionCatalogOut,
    MissionDetailOut,
    MissionGraphNodeOut,
    MissionPrerequisiteOut,
    MissionQuizReviewOut,
    MissionVariantOut,
    MissionVariantSummaryOut,
)
from app.services import storage
from app.services.missions import is_unlocked, prerequisite_status, start_attempt
from app.services.missions.serialize import variant_student_view
from app.services.missions.verifiers.quiz import submit_quiz_attempt
from app.services.missions.verifiers.submission import submit_submission_attempt

router = APIRouter(prefix="/missions", tags=["missions"])


async def _open_mission(db: AsyncSession, mission_id: uuid.UUID) -> Mission:
    mission = await db.get(Mission, mission_id)
    if mission is None or mission.status != "published" or mission.access_mode != "open":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")
    return mission


def _attempt_out(attempt: MissionAttempt, *, variant_label: str) -> MissionAttemptOut:
    return MissionAttemptOut(
        id=attempt.id, mission_id=attempt.mission_id, variant_id=attempt.variant_id,
        variant_label=variant_label, attempt_no=attempt.attempt_no, status=attempt.status,
        score=float(attempt.score) if attempt.score is not None else None, payload=attempt.payload or {},
        started_at=attempt.started_at, submitted_at=attempt.submitted_at, decided_at=attempt.decided_at,
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
            locked=not await is_unlocked(db, mission_id=mission.id, user_id=current.id),
        ))
    return out


@router.get("/graph", response_model=list[MissionGraphNodeOut])
async def mission_graph(db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user)):
    """The constellation view's data — every open mission plus its
    prerequisite edges and this student's own lock state. Registered before
    `/{mission_id}` on purpose: 'graph' would otherwise parse as a mission_id
    and 422 (same routing-order lesson as admin_router vs student_router in
    routers/missions/__init__.py)."""
    missions = (await db.execute(
        select(Mission).where(Mission.status == "published", Mission.access_mode == "open")
        .order_by(Mission.created_at.desc())
    )).scalars().all()
    mission_ids = [m.id for m in missions]
    edges = (await db.execute(
        select(MissionPrerequisite).where(MissionPrerequisite.mission_id.in_(mission_ids))
    )).scalars().all()
    requires_by_mission: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for edge in edges:
        requires_by_mission[edge.mission_id].append(edge.requires_mission_id)

    out = []
    for mission in missions:
        out.append(MissionGraphNodeOut(
            id=mission.id, title=mission.title, kind=mission.kind, track=mission.track,
            locked=not await is_unlocked(db, mission_id=mission.id, user_id=current.id),
            requires=requires_by_mission.get(mission.id, []),
        ))
    return out


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
            MissionAttempt.mission_id == mission.id, MissionAttempt.user_id == current.id,
        ).order_by(MissionAttempt.attempt_no)
    )).scalars().all()
    prereqs = await prerequisite_status(db, mission_id=mission.id, user_id=current.id)
    return MissionDetailOut(
        id=mission.id, title=mission.title, slug=mission.slug, summary=mission.summary,
        description=mission.description, kind=mission.kind, track=mission.track,
        image_url=await storage.resolve_url(mission.image_bucket, mission.image_path),
        variants=[MissionVariantOut(**variant_student_view(v, kind=mission.kind)) for v in variants],
        attempts=[
            _attempt_out(a, variant_label=variant_by_id[a.variant_id].label if a.variant_id in variant_by_id else "")
            for a in attempts
        ],
        prerequisites=[MissionPrerequisiteOut(**p) for p in prereqs],
        locked=not all(p["satisfied"] for p in prereqs),
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
    if not await is_unlocked(db, mission_id=mission.id, user_id=current.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Complete the required missions first")
    attempt = await start_attempt(db, user_id=current.id, mission_id=mission.id, variant_id=body.variant_id)
    await db.commit()
    await db.refresh(attempt)
    active_variant = await db.get(MissionVariant, attempt.variant_id)
    return _attempt_out(attempt, variant_label=active_variant.label if active_variant else "")


async def _own_attempt(db: AsyncSession, attempt_id: uuid.UUID, user: User) -> MissionAttempt:
    attempt = await db.get(MissionAttempt, attempt_id)
    if attempt is None or attempt.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    return attempt


@router.get("/attempts/{attempt_id}", response_model=MissionAttemptOut)
async def get_mission_attempt(
    attempt_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_attempt(db, attempt_id, current)
    variant = await db.get(MissionVariant, attempt.variant_id)
    return _attempt_out(attempt, variant_label=variant.label if variant else "")


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
            attempt=_attempt_out(decided, variant_label=variant.label),
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
        return MissionAttemptSubmitOut(attempt=_attempt_out(submitted, variant_label=variant.label), review=None)

    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Mission kind '{mission.kind}' has no submit flow yet")
