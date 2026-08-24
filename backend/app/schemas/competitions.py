"""Competition judging schemas (2026-08-24) — rubric authoring, blind
per-judge scoring, the leaderboard, and judge-roster management. See
`services/competitions/judging.py` and `services/competitions/judges.py`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.teams import TeamOut


class CompetitionRubricCriterionIn(BaseModel):
    key: str
    label: str
    max_points: int


class CompetitionRubricCriterionOut(BaseModel):
    key: str
    label: str
    max_points: int
    position: int


class CompetitionRubricIn(BaseModel):
    name: str
    criteria: list[CompetitionRubricCriterionIn]


class CompetitionRubricOut(BaseModel):
    id: UUID
    program_id: UUID
    name: str
    criteria: list[CompetitionRubricCriterionOut]


class CompetitionScoreIn(BaseModel):
    criterion_scores: dict[str, int]
    bonus_points: int = 0


class CompetitionScoreOut(BaseModel):
    id: UUID
    team_id: UUID
    judge_user_id: UUID
    criterion_scores: dict[str, int]
    bonus_points: int
    total_points: int
    submitted_at: datetime | None = None


class CompetitionLeaderboardRowOut(BaseModel):
    rank: int
    team_id: UUID
    team_name: str
    score: float | None = None
    judges_scored: int
    status: str  # scored|unscored


class CompetitionJudgeOut(BaseModel):
    user_id: UUID
    full_name: str
    email: str


class CompetitionJudgeProgressOut(CompetitionJudgeOut):
    scored_count: int
    team_count: int


class CompetitionJudgeInviteIn(BaseModel):
    name: str
    email: str


class CompetitionPublicationOut(BaseModel):
    published: bool
    published_at: datetime | None = None


class CompetitionSubmissionItemOut(BaseModel):
    item_id: UUID
    title: str
    item_type: str
    status: str
    submitted_url: str | None = None


class CompetitionJudgeCohortOut(BaseModel):
    id: UUID
    name: str
    program_name: str


class CompetitionJudgeTeamOut(TeamOut):
    """A team as seen on the judge's roster — `TeamOut` plus whether this
    judge (specifically, not any judge) has already scored it, so the judge
    UI can show a done/pending mark without a second round trip."""

    already_scored: bool = False


class CompetitionTeamDetailOut(BaseModel):
    team: TeamOut
    submissions: list[CompetitionSubmissionItemOut]
    rubric: CompetitionRubricOut | None = None
    own_score: CompetitionScoreOut | None = None
