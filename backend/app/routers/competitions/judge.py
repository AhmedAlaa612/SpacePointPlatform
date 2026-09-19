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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_judge
from app.db.session import get_db
from app.models.missions.design import Design
from app.models.missions.mission import MissionAttempt
from app.models.sessions.cohort import Cohort
from app.models.team import Team
from app.models.user import User
from app.routers.missions.design import design_state_out
from app.schemas.competitions import (
    CompetitionJudgeCohortOut, CompetitionJudgeTeamOut, CompetitionMissionRunOut, CompetitionScoreIn,
    CompetitionScoreOut, CompetitionSubmissionItemOut, CompetitionTeamDetailOut,
)
from app.schemas.missions_design import DesignStateOut
from app.schemas.teams import TeamOut
from app.services.competitions.judges import assigned_cohorts, require_judge_cohort_access
from app.services.competitions.judging import get_own_score, get_rubric, scored_team_ids, submit_score
from app.services.lms.program import team_mission_run_items, team_submission_items
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
        out.append(CompetitionJudgeTeamOut(
            **base.model_dump(),
            already_scored=team.id in scored,
            locked=team.final_locked_at is not None,
            locked_at=team.final_locked_at,
        ))
    return out


@router.get("/teams/{team_id}", response_model=CompetitionTeamDetailOut)
async def get_my_team(
    team_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    team = await _team_or_404(db, team_id, current=current)
    cohort = await db.get(Cohort, team.cohort_id)
    rubric_result = await get_rubric(db, program_id=cohort.program_id) if cohort else None
    submissions = await team_submission_items(db, team_id=team.id)
    mission_runs = await team_mission_run_items(db, team_id=team.id)

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
        mission_runs=[CompetitionMissionRunOut(**m) for m in mission_runs],
        rubric=rubric_out,
        own_score=own_score_out,
        locked=team.final_locked_at is not None,
        locked_at=team.final_locked_at,
    )


@router.get("/teams/{team_id}/mission-runs/{attempt_id}/design-detail", response_model=DesignStateOut)
async def get_my_team_mission_run_design_detail(
    team_id: uuid.UUID, attempt_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Read-only design dashboard for one of this team's mission runs
    (Phase 3, 2026-09) — the same full wizard state ops already sees via
    `/missions/instructor/attempts/{id}/design-detail` (`design_state_out`,
    reused here rather than duplicated), but reached only through a team
    this judge is actually assigned to: `_team_or_404` enforces the
    CompetitionJudge cohort check first, then the attempt itself must
    belong to `team_id` — a judge is never handed a bare "any attempt id"
    route, only ever one confirmed to belong to a team they can see."""
    team = await _team_or_404(db, team_id, current=current)
    attempt = await db.get(MissionAttempt, attempt_id)
    if attempt is None or attempt.team_id != team.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission run not found")
    design = (await db.execute(select(Design).where(Design.attempt_id == attempt.id))).scalars().first()
    if design is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This team hasn't started their design yet")
    return await design_state_out(db, attempt=attempt, design=design)


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
