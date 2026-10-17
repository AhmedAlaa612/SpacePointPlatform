from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ArcadeMode = Literal["explorer", "engineer"]
ArcadeProgramMode = Literal["explorer", "engineer", "either"]


class ArcadeDebriefNote(BaseModel):
    ok: bool
    t: str


class ArcadeModeBestOut(BaseModel):
    best_score: int = 0
    passed: bool = False
    attempts_count: int = 0


class ArcadeGameCatalogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    game_key: str
    position: int
    module_key: str
    module_no: str
    module_name: str
    kind: str
    is_3d: bool
    title: str
    blurb: str | None = None
    lesson_explorer: str | None = None
    lesson_engineer: str | None = None
    time_explorer_seconds: int
    time_engineer_seconds: int
    points_explorer: int
    points_engineer: int
    explorer: ArcadeModeBestOut = Field(default_factory=ArcadeModeBestOut)
    engineer: ArcadeModeBestOut = Field(default_factory=ArcadeModeBestOut)


class ArcadeAttemptSubmitIn(BaseModel):
    mode: ArcadeMode
    score: int = Field(ge=0, le=100)
    accuracy: int = Field(ge=0, le=100)
    passed: bool
    elapsed_seconds: int = Field(ge=0)
    notes: list[ArcadeDebriefNote] = Field(default_factory=list)
    assignment_id: UUID | None = None
    program_item_id: UUID | None = None


class ArcadeAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    game_id: UUID
    game_key: str
    game_title: str
    mode: str
    score: int
    accuracy: int
    passed: bool
    elapsed_seconds: int
    attempt_no: int
    points_awarded: int = 0
    notes: list[ArcadeDebriefNote] = []
    completed_at: datetime | None = None
