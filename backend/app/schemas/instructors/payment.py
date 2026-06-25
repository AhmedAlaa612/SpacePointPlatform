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
    instructor_user_id: Optional[UUID] = None
    instructor_name: Optional[str] = None
    batch_id: Optional[UUID] = None
    letter_date: Optional[str] = None
    reference: str
    status: PaymentLetterStatus
    is_published: bool
    pdf_url: Optional[str] = None
    signed_pdf_url: Optional[str] = None
    admin_notes: Optional[str] = None
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


class PaymentAddonCreate(BaseModel):
    description: str
    amount_aed: float = 0
    notes: Optional[str] = None


class PaymentBatchCreate(BaseModel):
    name: str
    description: Optional[str] = None


class PaymentBatchOut(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    letter_count: int = 0

    class Config:
        from_attributes = True


class CertificateOut(BaseModel):
    id: UUID
    user_id: UUID
    instructor_name: Optional[str] = None
    type: str
    workshop_name: Optional[str] = None
    workshop_date: Optional[str] = None
    location: Optional[str] = None
    file_url: str


class BulkImportPreviewOut(BaseModel):
    instructor_count: int
    session_count: int
    addon_count: int
    unmatched_emails: list[str]
    errors: list[str]
