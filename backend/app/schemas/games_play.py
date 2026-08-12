"""Live games — student play schemas (Live Games Phase 2C, 8-8)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class JoinRunIn(BaseModel):
    avatar: str | None = None  # None = use the profile photo (D18's default)


class ParticipantOut(BaseModel):
    id: UUID
    run_id: UUID
    nickname: str
    avatar: str | None
    joined_at: datetime | None


class SubmitAnswerIn(BaseModel):
    selected_option_index: int | None
    elapsed_seconds: float


class AnswerAckOut(BaseModel):
    """Private — sent only in the HTTP response and over the participant's
    own channel, never the shared run channel (D9's leaderboard privacy
    extends to the answer breakdown too, since a wrong-answer 0 next to a
    correct-answer 178 would out who answered what)."""
    is_correct: bool
    points_awarded: int
    base_points: int
    speed_bonus: int
    streak: int


class MyScoreOut(BaseModel):
    score: int
    streak: int


class StudentLeaderboardEntryOut(BaseModel):
    participant_id: UUID
    nickname: str
    avatar: str | None
    score: int
    is_me: bool


class JoinableRunOut(BaseModel):
    run_id: UUID
    assignment_id: UUID
    game_title: str
    status: str
    session_title: str | None
    session_date: str
