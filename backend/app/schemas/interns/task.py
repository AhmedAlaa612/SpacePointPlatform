from pydantic import BaseModel, model_validator
from typing import Optional, List, Any
from decimal import Decimal
from datetime import datetime
from uuid import UUID
from app.models.enums import WorkStatus
from app.schemas.user import UserOut
from app.schemas.interns.submission import TaskSubmissionOut


class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    expected_time: Optional[Decimal] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    status: Optional[WorkStatus] = None
    expected_time: Optional[Decimal] = None
    actual_time: Optional[Decimal] = None


class TaskStatusUpdate(BaseModel):
    status: WorkStatus


class TaskAssign(BaseModel):
    user_ids: List[UUID]


class TaskOut(TaskBase):
    id: UUID
    module_id: UUID
    status: WorkStatus
    actual_time: Optional[Decimal] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    assignees: List[UserOut] = []
    submissions: List[TaskSubmissionOut] = []
    # derived from module â†’ epic chain
    module_title: Optional[str] = None
    module_description: Optional[str] = None
    epic_id: Optional[UUID] = None
    epic_title: Optional[str] = None
    epic_description: Optional[str] = None
    project_id: Optional[UUID] = None

    @model_validator(mode="before")
    @classmethod
    def populate_derived(cls, data: Any) -> Any:
        if not hasattr(data, "_sa_instance_state"):
            return data
        loaded = data._sa_instance_state.dict
        module = loaded.get("module")
        obj = {k: v for k, v in data.__dict__.items() if not k.startswith("_")}
        if module is not None:
            obj["module_title"] = module.title
            obj["module_description"] = module.description
            obj["epic_id"] = module.epic_id
            module_loaded = module._sa_instance_state.dict
            epic = module_loaded.get("epic")
            if epic is not None:
                obj["epic_title"] = epic.title
                obj["epic_description"] = epic.description
                obj["project_id"] = epic.project_id
        return obj

    class Config:
        from_attributes = True
