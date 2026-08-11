"""Live games — instructor live-play schemas (Live Games Phase 2C, 8-7).

Two shapes for a question on purpose: `LiveQuestionOut` (options carry
`is_correct`) is only ever returned from a staff-gated HTTP GET, never
broadcast — the WS run channel is shared by the instructor *and* every
student, so anything sent there uses `PublicQuestionOut` instead, which
strips `is_correct` entirely. Mixing these up would leak the answer key
to every connected student the instant a question starts.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PublicQuestionOptionOut(BaseModel):
    text: str


class PublicQuestionOut(BaseModel):
    """Broadcast shape — no `is_correct` anywhere. Sent over `question_started`."""
    id: UUID
    position: int
    prompt: str
    options: list[PublicQuestionOptionOut]
    time_limit_seconds: int
    max_points: int


class LiveQuestionOptionOut(BaseModel):
    text: str
    is_correct: bool


class LiveQuestionOut(BaseModel):
    """Staff-only shape — HTTP GET only, never broadcast."""
    id: UUID
    position: int
    prompt: str
    options: list[LiveQuestionOptionOut]
    time_limit_seconds: int
    max_points: int


class GameRunOut(BaseModel):
    id: UUID
    assignment_id: UUID
    run_no: int
    status: str
    current_question_position: int | None
    total_questions: int
    blackout_active: bool
    started_at: datetime | None
    ended_at: datetime | None


class RosterEntryOut(BaseModel):
    participant_id: UUID
    nickname: str
    avatar: str | None
    has_answered_current: bool


class LeaderboardEntryOut(BaseModel):
    participant_id: UUID
    nickname: str
    avatar: str | None
    score: int


class QuestionResultOut(BaseModel):
    index: int
    text: str
    is_correct: bool
    count: int
    pct: int


class RevealNameOut(BaseModel):
    participant_id: UUID
    real_name: str
