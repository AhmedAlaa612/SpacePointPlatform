"""Live games — student play schemas (Live Games Phase 2C, 8-8)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.services.games.avatars import AVATAR_PRESETS


def _validate_avatar(v: str | None) -> str | None:
    if v is not None and v not in AVATAR_PRESETS:
        raise ValueError(f"'{v}' is not a valid avatar — choose one of {sorted(AVATAR_PRESETS)}")
    return v


class JoinRunIn(BaseModel):
    avatar: str | None = None  # None = initials fallback (world-class rework: icon presets only, no photo)

    _validate_avatar = field_validator("avatar")(_validate_avatar)


class UpdateParticipantProfileIn(BaseModel):
    """Lobby-only nickname/avatar override for one game — distinct from the
    profile-level nickname reroll (D2, weekly-cooldown-limited): this is a
    lighter-weight, uncapped, per-game display override, per D18."""
    nickname: str = Field(min_length=1, max_length=64)
    avatar: str | None = None

    _validate_avatar = field_validator("avatar")(_validate_avatar)

    @field_validator("nickname")
    @classmethod
    def _strip_nickname(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("nickname can't be blank")
        return v


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
