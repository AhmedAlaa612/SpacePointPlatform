from pydantic import BaseModel, model_validator
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID
from app.models.enums import WorkStatus
from app.schemas.user import UserOut


# ── forward-declared to avoid circular imports ────────────────────────────────
class TaskBriefOut(BaseModel):
    id: UUID
    title: str
    status: WorkStatus
    due_date: Optional[datetime] = None
    expected_time: Optional[float] = None
    actual_time: Optional[float] = None
    assignee_count: int = 0
    assignees: List[UserOut] = []

    @model_validator(mode="before")
    @classmethod
    def populate_assignee_count(cls, data: Any) -> Any:
        if not hasattr(data, "_sa_instance_state"):
            return data
        loaded = data._sa_instance_state.dict
        assignees = loaded.get("assignees") or []
        obj = {k: v for k, v in data.__dict__.items() if not k.startswith("_")}
        obj["assignee_count"] = len(assignees)
        obj["assignees"] = assignees
        return obj

    class Config:
        from_attributes = True


class ModuleBriefOut(BaseModel):
    id: UUID
    epic_id: UUID
    title: str
    description: Optional[str] = None
    created_at: datetime
    tasks: List[TaskBriefOut] = []

    @model_validator(mode="before")
    @classmethod
    def populate_tasks(cls, data: Any) -> Any:
        if not hasattr(data, "_sa_instance_state"):
            return data
        loaded = data._sa_instance_state.dict
        tasks = loaded.get("tasks") or []
        obj = {k: v for k, v in data.__dict__.items() if not k.startswith("_")}
        obj["tasks"] = tasks
        return obj

    class Config:
        from_attributes = True


# ── Epic schemas ──────────────────────────────────────────────────────────────

class EpicBase(BaseModel):
    title: str
    description: Optional[str] = None


class EpicCreate(EpicBase):
    team_id: UUID


class EpicUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[WorkStatus] = None


class EpicOut(EpicBase):
    id: UUID
    project_id: UUID
    team_id: UUID
    status: WorkStatus
    created_by: Optional[UUID] = None
    created_at: datetime
    modules: List[ModuleBriefOut] = []
    team_name: Optional[str] = None
    leader_name: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def populate_modules(cls, data: Any) -> Any:
        if not hasattr(data, "_sa_instance_state"):
            return data
        loaded = data._sa_instance_state.dict
        modules = loaded.get("modules") or []
        obj = {k: v for k, v in data.__dict__.items() if not k.startswith("_")}
        obj["modules"] = modules
        team = loaded.get("team")
        if team is not None:
            obj["team_name"] = team.name
            team_loaded = team._sa_instance_state.dict
            leader = team_loaded.get("leader")
            if leader is not None:
                obj["leader_name"] = leader.full_name
        return obj

    class Config:
        from_attributes = True
