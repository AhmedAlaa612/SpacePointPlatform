from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime


class ApplicationQuestionCreate(BaseModel):
    question_text: str
    question_type: str  # text, number, radio, multiple_choice
    required: bool = True
    options: Optional[List[str]] = None


class ApplicationQuestionUpdate(BaseModel):
    question_text: Optional[str] = None
    question_type: Optional[str] = None
    required: Optional[bool] = None
    order: Optional[int] = None
    options: Optional[List[str]] = None


class ApplicationQuestionOut(BaseModel):
    id: UUID
    question_text: str
    question_type: str
    required: bool
    order: int
    options: Optional[List[str]] = None
    created_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TeacherApplicationCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    invite_code: str
    answers: Optional[Dict[str, Any]] = None


class TeacherApplicationUpdate(BaseModel):
    status: str  # pending, approved, rejected


class TeacherApplicationOut(BaseModel):
    id: UUID
    full_name: str
    email: str
    invite_code: str
    invited_by_id: UUID
    answers: Optional[Dict[str, Any]] = None
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
