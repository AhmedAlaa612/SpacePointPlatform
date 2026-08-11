"""Live game facilitator-authoring schemas (Live Games Phase 2C, 8-3)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class GameQuestionOptionIn(BaseModel):
    text: str
    is_correct: bool = False


class GameQuestionIn(BaseModel):
    prompt: str
    options: list[GameQuestionOptionIn] = Field(min_length=2)
    time_limit_seconds: int | None = None  # None = use the game's default
    points_mode: Literal["normal", "double"] = "normal"
    position: int | None = None  # None = append at the end

    @model_validator(mode="after")
    def _validate_correct_option(self) -> "GameQuestionIn":
        correct = sum(1 for o in self.options if o.is_correct)
        if correct != 1:
            raise ValueError(f"a game question needs exactly one correct option, got {correct}")
        return self


class GameQuestionUpdate(BaseModel):
    prompt: str | None = None
    options: list[GameQuestionOptionIn] | None = None
    time_limit_seconds: int | None = None
    points_mode: Literal["normal", "double"] | None = None
    position: int | None = None

    @model_validator(mode="after")
    def _validate_correct_option(self) -> "GameQuestionUpdate":
        if self.options is not None:
            correct = sum(1 for o in self.options if o.is_correct)
            if correct != 1:
                raise ValueError(f"a game question needs exactly one correct option, got {correct}")
        return self


class GameQuestionOut(BaseModel):
    id: UUID
    position: int
    prompt: str
    options: list[GameQuestionOptionIn]
    time_limit_seconds: int | None
    points_mode: str
    max_points: int  # resolved via services/games/points.py — the frontend never computes this itself


class GameQuestionReorderIn(BaseModel):
    question_ids: list[UUID]


class GameCreate(BaseModel):
    title: str
    description: str | None = None
    default_time_limit_seconds: int = Field(gt=0, default=20)
    default_floor_pct: int = Field(ge=0, le=100, default=25)
    default_blackout_count: int = Field(ge=0, default=3)


class GameUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    default_time_limit_seconds: int | None = Field(gt=0, default=None)
    default_floor_pct: int | None = Field(ge=0, le=100, default=None)
    default_blackout_count: int | None = Field(ge=0, default=None)


class GameOut(BaseModel):
    id: UUID
    title: str
    description: str | None
    created_by: UUID
    default_time_limit_seconds: int
    default_floor_pct: int
    default_blackout_count: int
    created_at: datetime | None
    question_count: int


class GameDetailOut(GameOut):
    questions: list[GameQuestionOut]
