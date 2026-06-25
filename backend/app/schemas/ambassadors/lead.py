from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime


class LeadBase(BaseModel):
    contact_name: str
    company: Optional[str] = None
    type: str
    notes: Optional[str] = None


class LeadCreate(LeadBase):
    pass


class LeadOut(LeadBase):
    id: UUID
    ambassador_id: UUID
    status: str
    created_at: datetime
    ambassador_name: Optional[str] = None
    ambassador_email: Optional[str] = None

    class Config:
        from_attributes = True


class LeadStatusUpdate(BaseModel):
    # "submitted", "in review", "converted", "closed"
    status: str


class LeadUpdate(BaseModel):
    contact_name: Optional[str] = None
    company: Optional[str] = None
    type: Optional[str] = None
    notes: Optional[str] = None


class LeadCommentCreate(BaseModel):
    body: str


class LeadCommentOut(BaseModel):
    id: UUID
    lead_id: UUID
    author_id: Optional[UUID] = None
    body: str
    created_at: datetime
    author_name: Optional[str] = None
    author_role: Optional[str] = None

    class Config:
        from_attributes = True
