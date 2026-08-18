"""Mission-manager scoped surface (7B-7, D7) — `/missions/manager/*`.

D7's payoff for an approved intern proposal: whoever staff assigned as a
mission's manager (`POST /missions/admin/{mission_id}/managers`) can see
that mission's stats and review its submission-kind attempts, without
becoming ops/facilitator generally. Staff can reach every mission through
this surface too (`require_mission_manager_or_staff`), same "layered on
top of, not instead of" posture the rest of this codebase's authorization
uses.

Deliberately thin: no route here edits a mission's own fields, variants, or
thresholds — that stays `/missions/admin/*` only, frozen once published
(D9). A manager's power is read + review, nothing that could retroactively
change what an already-graded attempt meant.

Registered before `student_router` in `routers/missions/__init__.py`:
`/missions/manager` is a static path that would otherwise be swallowed by
`/missions/{mission_id}` (same routing-order lesson as `/teams`/`/graph`/
`/proposals`).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.missions.manager import MissionManager
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.team import Team
from app.models.missions.mission import Mission
from app.models.user import User
from app.services.missions.design import content as design_content
from app.schemas.missions_admin import MissionAttemptAdminOut, MissionAttemptReviewIn
from app.schemas.missions_manager import (
    MissionContentOut,
    MissionContentUpdateIn,
    MissionStatsOut,
    MyManagedMissionOut,
)
from app.services.missions.authorization import require_mission_manager_or_staff
from app.services.missions.stats import mission_stats
from app.services.missions.verifiers.submission import review_submission_attempt

router = APIRouter(prefix="/missions/manager", tags=["missions-manager"])


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


@router.get("/mine", response_model=list[MyManagedMissionOut])
async def my_managed_missions(db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user)):
    rows = (await db.execute(
        select(Mission)
        .join(MissionManager, MissionManager.mission_id == Mission.id)
        .where(MissionManager.user_id == current.id)
        .order_by(Mission.title)
    )).scalars().all()
    return [MyManagedMissionOut(mission_id=m.id, title=m.title) for m in rows]


@router.get("/{mission_id}/stats", response_model=MissionStatsOut)
async def manager_mission_stats(
    mission_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    if await db.get(Mission, mission_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")
    await require_mission_manager_or_staff(db, mission_id=mission_id, user=current)
    return await mission_stats(db, mission_id=mission_id)


@router.get("/{mission_id}/queue", response_model=list[MissionAttemptAdminOut])
async def manager_review_queue(
    mission_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    if await db.get(Mission, mission_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")
    await require_mission_manager_or_staff(db, mission_id=mission_id, user=current)
    attempts = (await db.execute(
        select(MissionAttempt).where(
            MissionAttempt.mission_id == mission_id, MissionAttempt.status == "submitted",
        ).order_by(MissionAttempt.submitted_at)
    )).scalars().all()
    return [await _attempt_admin_out(db, a) for a in attempts]


@router.post("/attempts/{attempt_id}/review", response_model=MissionAttemptAdminOut)
async def manager_review_attempt(
    attempt_id: uuid.UUID, body: MissionAttemptReviewIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await db.get(MissionAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    await require_mission_manager_or_staff(db, mission_id=attempt.mission_id, user=current)
    reviewed = await review_submission_attempt(
        db, attempt=attempt, reviewer_id=current.id, passed=body.passed,
        score=body.score, review_comment=body.review_comment,
    )
    await db.commit()
    await db.refresh(reviewed)
    return await _attempt_admin_out(db, reviewed)


# ── Authored content (Design v2, 7D-8 / D8) ─────────────────────────────

@router.get("/{mission_id}/content", response_model=MissionContentOut)
async def get_mission_content(
    mission_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """The explanatory copy for this mission, with every field showing both
    its current value and the authored default.

    Editable while published, unlike `mission_variants.config` — that is
    the D8 split, and the reason a mission manager is a useful role rather
    than a read-only one. Changing how a budget is explained cannot change
    anybody's grade.
    """
    await require_mission_manager_or_staff(db, mission_id=mission_id, user=current)
    mission = await db.get(Mission, mission_id)
    if mission is None:
        raise HTTPException(404, detail="Mission not found")
    return MissionContentOut(
        mission_id=mission.id, mission_kind=mission.kind, mission_status=mission.status,
        editable=design_content.editable_content(mission.content or {}) if mission.kind == "design" else {},
    )


@router.put("/{mission_id}/content", response_model=MissionContentOut)
async def update_mission_content(
    mission_id: uuid.UUID, body: MissionContentUpdateIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Overrides only. An empty string clears an override and restores the
    default, so nothing is ever permanently lost to a bad edit."""
    await require_mission_manager_or_staff(db, mission_id=mission_id, user=current)
    mission = await db.get(Mission, mission_id)
    if mission is None:
        raise HTTPException(404, detail="Mission not found")
    mission.content = _prune(body.content)
    await db.commit()
    return MissionContentOut(
        mission_id=mission.id, mission_kind=mission.kind, mission_status=mission.status,
        editable=design_content.editable_content(mission.content or {}) if mission.kind == "design" else {},
    )


def _prune(raw: dict) -> dict:
    """Drop blanks so "cleared" means "back to the default" rather than
    "overridden with nothing"."""
    out: dict = {}
    for key, value in (raw or {}).items():
        if isinstance(value, str):
            if value.strip():
                out[key] = value
        elif isinstance(value, list):
            items = [str(v) for v in value if str(v).strip()]
            if items:
                out[key] = items
        elif isinstance(value, dict):
            nested = {k: {kk: vv for kk, vv in (v or {}).items() if isinstance(vv, str) and vv.strip()}
                      for k, v in value.items()}
            nested = {k: v for k, v in nested.items() if v}
            if nested:
                out[key] = nested
    return out
