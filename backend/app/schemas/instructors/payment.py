from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import PaymentLetterStatus, PaymentSessionRole


class PaymentSessionOut(BaseModel):
    id: UUID
    session_date: Optional[str] = None
    workshop_description: str
    role: PaymentSessionRole
    location: Optional[str] = None
    duration_hours: Optional[float] = None
    compensation_aed: float

    class Config:
        from_attributes = True


class PaymentAddonOut(BaseModel):
    id: UUID
    description: str
    amount_aed: float
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class PaymentLetterOut(BaseModel):
    id: UUID
    letter_date: Optional[str] = None
    reference: str
    status: PaymentLetterStatus
    is_published: bool
    pdf_url: Optional[str] = None
    signed_pdf_url: Optional[str] = None
    sessions: list[PaymentSessionOut] = []
    addons: list[PaymentAddonOut] = []


class PaymentSummaryOut(BaseModel):
    total_earned_aed: float
    total_hours: float
    total_sessions: int
    pending_signature: int


class SignLetterRequest(BaseModel):
    signature: str  # data:image/png;base64,...


class PaymentLetterCreate(BaseModel):
    instructor_user_id: UUID
    batch_id: Optional[UUID] = None
    letter_date: Optional[str] = None
    reference: str = "Facilitator Agreement"


class PaymentSessionCreate(BaseModel):
    session_date: Optional[str] = None
    workshop_description: str
    role: PaymentSessionRole
    location: Optional[str] = None
    duration_hours: Optional[float] = None
    compensation_aed: float = 0
