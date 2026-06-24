from pydantic import BaseModel, model_validator
from typing import Optional, Any
from decimal import Decimal
from datetime import datetime
from uuid import UUID
from app.models.enums import SubmissionStatus


class TaskSubmissionBase(BaseModel):
    link: str
    note: Optional[str] = None


class TaskSubmissionCreate(TaskSubmissionBase):
    actual_time: Optional[Decimal] = None   # intern logs time spent on submission


class TaskSubmissionReview(BaseModel):
    score: int
    review_comment: str


class TaskSubmissionOut(TaskSubmissionBase):
    id: UUID
    task_id: UUID
    submitted_by: UUID
    submitter_name: Optional[str] = None
    status: SubmissionStatus
    score: Optional[int] = None
    review_comment: Optional[str] = None
    submitted_at: datetime
    reviewed_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def populate_submitter_name(cls, data: Any) -> Any:
        if not hasattr(data, "_sa_instance_state"):
            return data
        loaded = data._sa_instance_state.dict
        submitter = loaded.get("submitter")
        obj = {k: v for k, v in data.__dict__.items() if not k.startswith("_")}
        obj["submitter_name"] = submitter.full_name if submitter is not None else None
        return obj

    class Config:
        from_attributes = True
