from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

MAX_STUDENTS = 100_000


class StatusUpdate(BaseModel):
    status: str


class SessionCreate(BaseModel):
    title: str
    description: Optional[str] = None
    date: datetime
    planned_students: int = Field(default=0, ge=0, le=MAX_STUDENTS)


class SessionDone(BaseModel):
    attended_students: int = Field(ge=0, le=MAX_STUDENTS)


class MaterialSent(BaseModel):
    material_link: Optional[str] = None


class SessionCancel(BaseModel):
    reason: Optional[str] = None


class SessionReject(BaseModel):
    reason: Optional[str] = None


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    date: Optional[datetime] = None
    planned_students: Optional[int] = Field(default=None, ge=0, le=MAX_STUDENTS)


class TeacherOut(BaseModel):
    id: UUID
    full_name: str
    email: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class InstructorOut(BaseModel):
    """Instructors are now unified Users with 'instructor' in their roles array."""
    id: UUID
    invited_by_id: UUID
    full_name: str
    email: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class SessionOut(BaseModel):
    id: UUID
    teacher_id: UUID
    title: str
    description: Optional[str] = None
    date: datetime
    status: str
    status_note: Optional[str] = None
    material_sent: bool
    material_link: Optional[str] = None
    planned_students: int
    attended_students: int
    created_at: datetime
    teacher_name: Optional[str] = None
    teacher_email: Optional[str] = None
    ambassador_name: Optional[str] = None

    class Config:
        from_attributes = True
