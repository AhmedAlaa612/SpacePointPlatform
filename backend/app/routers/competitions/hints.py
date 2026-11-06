"""Competition judging endpoints for Interactive Card Hint Station."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.competitions.hint_station import (
    CohortHintCard,
    CohortHintChallenge,
    CohortTeamHintReveal,
)
from app.models.team import Team
from app.models.user import User
from app.schemas.hint_station import (
    CohortHintJudgingSummaryOut,
    HintRevealAuditOut,
    TeamHintJudgingSummaryOut,
)
from app.services.competitions.hint_station import (
    get_cohort_hint_judging_summary,
    reset_team_hint_reveals,
    reset_user_hint_reveals,
)

router = APIRouter(prefix="/competitions", tags=["competitions-hints"])


@router.get(
    "/cohorts/{cohort_id}/hints/judging-summary",
    response_model=CohortHintJudgingSummaryOut,
)
async def cohort_hint_judging_summary(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Returns hint assistance summary and chronological reveals for all teams in a cohort."""
    # Staff-only: the cohort-wide audit must never be reachable by students.
    if not any(r in current.role_values for r in ("admin", "operations", "instructor", "judge")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Staff privileges required")
    return await get_cohort_hint_judging_summary(db, cohort_id=cohort_id)


@router.get(
    "/teams/{team_id}/hints",
    response_model=TeamHintJudgingSummaryOut,
)
async def team_hint_summary(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Returns hint assistance summary and reveal audit for a single team (for JudgeTeamDetail)."""
    # Staff-only: a team's hint audit is judge/ops context, never student-facing.
    if not any(r in current.role_values for r in ("admin", "operations", "instructor", "judge")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Staff privileges required")
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found")

    reveals = (
        await db.execute(
            select(CohortTeamHintReveal)
            .where(CohortTeamHintReveal.team_id == team_id)
            .order_by(CohortTeamHintReveal.revealed_at.desc())
        )
    ).scalars().all()

    # Preload challenges and cards
    challenge_ids = {r.challenge_id for r in reveals}
    challenges = {}
    if challenge_ids:
        ch_res = (
            await db.execute(
                select(CohortHintChallenge).where(CohortHintChallenge.id.in_(challenge_ids))
            )
        ).scalars().all()
        challenges = {c.id: c.title for c in ch_res}

    card_ids = {r.hint_card_id for r in reveals}
    cards = {}
    if card_ids:
        card_res = (
            await db.execute(
                select(CohortHintCard).where(CohortHintCard.id.in_(card_ids))
            )
        ).scalars().all()
        cards = {c.id: c for c in card_res}

    user_ids = {r.revealed_by_user_id for r in reveals if r.revealed_by_user_id}
    user_names = {}
    if user_ids:
        u_res = (
            await db.execute(select(User).where(User.id.in_(user_ids)))
        ).scalars().all()
        for u in u_res:
            name = u.full_name or u.email
            user_names[u.id] = name

    audit_entries: list[HintRevealAuditOut] = []
    total_deductions = 0
    for r in reveals:
        c = cards.get(r.hint_card_id)
        total_deductions += r.points_deducted
        audit_entries.append(
            HintRevealAuditOut(
                id=r.id,
                challenge_id=r.challenge_id,
                challenge_title=challenges.get(r.challenge_id, "Challenge"),
                hint_card_id=r.hint_card_id,
                level=c.level if c else 1,
                level_label=c.level_label if c else "Hint",
                card_title=c.title if c else "Hint",
                points_deducted=r.points_deducted,
                revealed_at=r.revealed_at,
                revealed_by_name=user_names.get(r.revealed_by_user_id) if r.revealed_by_user_id else None,
            )
        )

    return TeamHintJudgingSummaryOut(
        team_id=team.id,
        team_name=team.name,
        team_code=team.join_code,
        hints_used=len(audit_entries),
        total_points_deducted=total_deductions,
        reveals=audit_entries,
    )


@router.post(
    "/cohorts/{cohort_id}/hints/teams/{team_id}/reset",
)
async def reset_team_reveals(
    cohort_id: uuid.UUID,
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Resets a team's hint reveal history for demo or rehearsal runs."""
    # User is multi-role — check role_values, not a nonexistent .role.
    is_ops = any(r in current.role_values for r in ("admin", "operations", "instructor"))
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found")

    # If not ops, allow if observer team
    if not is_ops and not team.is_observer:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only ops can reset official team reveals")

    deleted = await reset_team_hint_reveals(db, cohort_id=cohort_id, team_id=team_id)
    return {"team_id": str(team_id), "deleted_reveals_count": deleted}


@router.post(
    "/cohorts/{cohort_id}/hints/users/{user_id}/reset",
)
async def reset_user_reveals(
    cohort_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Resets an individual student's hint reveal history for demo or rehearsal runs."""
    is_ops = any(r in current.role_values for r in ("admin", "operations", "instructor"))
    if not is_ops:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only ops can reset individual student reveals")

    deleted = await reset_user_hint_reveals(db, cohort_id=cohort_id, user_id=user_id)
    return {"user_id": str(user_id), "deleted_reveals_count": deleted}
