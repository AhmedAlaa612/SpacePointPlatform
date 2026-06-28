from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class DocumentRequestCreate(BaseModel):
    type: str  # 'recommendation_letter', 'confirmation_letter', 'completion_letter', 'certificate'
    requested_role: Optional[str] = None  # role the user was acting as (e.g. 'instructor')
    notes: Optional[str] = None


class DocumentRequestOut(BaseModel):
    id: UUID
    user_id: UUID
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    type: str
    status: str
    requested_role: Optional[str] = None
    notes: Optional[str] = None
    admin_notes: Optional[str] = None
    file_url: Optional[str] = None
    user_created_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentRequestReview(BaseModel):
    status: str  # 'approved', 'rejected'
    admin_notes: Optional[str] = None


class DocumentRequestApprove(BaseModel):
    signatory_name: Optional[str] = None
    signatory_title: Optional[str] = None
    recommendation_text: Optional[str] = None
    date: Optional[str] = None
    title: Optional[str] = None
