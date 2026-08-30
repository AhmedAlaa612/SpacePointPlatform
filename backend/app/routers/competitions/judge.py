"""Judge scoring surface (2026-08-24) — `/competitions/judge/*`, gated by
`require_judge`. Every route is cohort-scoped via
`services/competitions/judges.py::require_judge_cohort_access` on top of
the role gate, same split `/missions/instructor` uses for instructors —
a judge with no `CompetitionJudge` row for a cohort 404s on it rather than
403ing, so a judge can't tell a real cohort they're not assigned to apart
from one that doesn't exist.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_judge
from app.db.session import get_db
from app.models.sessions.cohort import Cohort
from app.models.team import Team
from app.models.user import User
from app.schemas.competitions import (
    CompetitionJudgeCohortOut, CompetitionJudgeTeamOut, CompetitionScoreIn, CompetitionScoreOut,
    CompetitionSubmissionItemOut, CompetitionTeamDetailOut,
)
from app.schemas.teams import TeamOut
from app.services.competitions.judges import assigned_cohorts, require_judge_cohort_access
from app.services.competitions.judging import get_own_score, get_rubric, scored_team_ids, submit_score
from app.services.lms.program import team_submission_items
from app.services.teams import team_member_ids, teams_for_cohort

router = APIRouter(
    prefix="/competitions/judge", tags=["competitions-judge"],
    dependencies=[Depends(require_judge)],
)


async def _team_out(db: AsyncSession, team: Team) -> TeamOut:
    member_ids = await team_member_ids(db, team_id=team.id)
    members = [await db.get(User, uid) for uid in member_ids]
    return TeamOut(
        id=team.id, name=team.name, cohort_id=team.cohort_id, member_ids=member_ids,
        member_names=[m.full_name for m in members if m is not None],
    )


async def _team_or_404(db: AsyncSession, team_id: uuid.UUID, *, current: User) -> Team:
    team = await db.get(Team, team_id)
    if team is None or team.cohort_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found")
    await require_judge_cohort_access(db, cohort_id=team.cohort_id, user=current)
    return team


@router.get("/cohorts", response_model=list[CompetitionJudgeCohortOut])
async def list_my_cohorts(db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user)):
    rows = await assigned_cohorts(db, user=current)
    return [
        CompetitionJudgeCohortOut(id=cohort.id, name=cohort.name, program_name=program_name)
        for cohort, program_name in rows
    ]


@router.get("/teams", response_model=list[CompetitionJudgeTeamOut])
async def list_my_teams(
    cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await require_judge_cohort_access(db, cohort_id=cohort_id, user=current)
    if await db.get(Cohort, cohort_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    teams = await teams_for_cohort(db, cohort_id=cohort_id)
    scored = await scored_team_ids(db, judge_user_id=current.id, cohort_id=cohort_id)
    out = []
    for team in teams:
        base = await _team_out(db, team)
        out.append(CompetitionJudgeTeamOut(**base.model_dump(), already_scored=team.id in scored))
    return out


@router.get("/teams/{team_id}", response_model=CompetitionTeamDetailOut)
async def get_my_team(
    team_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    team = await _team_or_404(db, team_id, current=current)
    cohort = await db.get(Cohort, team.cohort_id)
    rubric_result = await get_rubric(db, program_id=cohort.program_id) if cohort else None
    submissions = await team_submission_items(db, team_id=team.id)

    rubric_out = None
    own_score_out = None
    if rubric_result is not None:
        rubric, criteria = rubric_result
        rubric_out = {
            "id": rubric.id, "program_id": rubric.program_id, "name": rubric.name,
            "criteria": [
                {"key": c.key, "label": c.label, "max_points": c.max_points, "position": c.position}
                for c in criteria
            ],
        }
        own_score = await get_own_score(
            db, rubric_id=rubric.id, team_id=team.id, judge_user_id=current.id, cohort_id=team.cohort_id,
        )
        if own_score is not None:
            own_score_out = CompetitionScoreOut.model_validate(own_score, from_attributes=True)

    return CompetitionTeamDetailOut(
        team=await _team_out(db, team),
        submissions=[CompetitionSubmissionItemOut(**s) for s in submissions],
        rubric=rubric_out,
        own_score=own_score_out,
    )


@router.put("/teams/{team_id}/score", response_model=CompetitionScoreOut)
async def put_my_team_score(
    team_id: uuid.UUID, body: CompetitionScoreIn, db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    team = await _team_or_404(db, team_id, current=current)
    cohort = await db.get(Cohort, team.cohort_id)
    rubric_result = await get_rubric(db, program_id=cohort.program_id) if cohort else None
    if rubric_result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No rubric configured for this competition yet")
    rubric, criteria = rubric_result

    score = await submit_score(
        db, rubric=rubric, criteria=criteria, team_id=team.id, judge_user_id=current.id, cohort_id=team.cohort_id,
        criterion_scores=body.criterion_scores, bonus_points=body.bonus_points, submitted=body.submitted,
    )
    await db.commit()
    return CompetitionScoreOut.model_validate(score, from_attributes=True)
