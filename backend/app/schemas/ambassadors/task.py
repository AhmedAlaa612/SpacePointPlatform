from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

MAX_TASK_POINTS = 100_000


class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    deadline: Optional[datetime] = None
    points_reward: int = Field(default=0, ge=0, le=MAX_TASK_POINTS)


class TaskCreate(TaskBase):
    assigned_to: UUID


class TaskOut(TaskBase):
    id: UUID
    assigned_to: UUID
    created_by: Optional[UUID] = None
    status: str
    edit_notes: Optional[str] = None
    submission: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    deadline: Optional[datetime] = None
    points_reward: Optional[int] = Field(default=None, ge=0, le=MAX_TASK_POINTS)


class TaskStatusUpdate(BaseModel):
    # accepted, submitted, approved, rejected, edit_requested
    status: str
    edit_notes: Optional[str] = None
    submission: Optional[str] = None


class AssignableUser(BaseModel):
    id: UUID
    full_name: str
    email: str
    roles: list[str]
    country: Optional[str] = None

    class Config:
        from_attributes = True
