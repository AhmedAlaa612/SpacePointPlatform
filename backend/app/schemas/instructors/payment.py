from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import PaymentLetterStatus


class PaymentSessionOut(BaseModel):
    id: UUID
    # I5-8: set when this line came from a real delivered session. Its
    # presence is what stops that session being billed twice.
    session_id: Optional[UUID] = None
    session_date: Optional[str] = None
    workshop_description: str
    # I5-3: the role *name* as a plain string, snapshotted on the document.
    # Not an FK and not an enum — a signed letter keeps saying what it said,
    # and a role ops adds tomorrow prints without a migration.
    role: str
    location: Optional[str] = None
    duration_hours: Optional[float] = None
    compensation_aed: float
    # Cohort rows (2026-08-24). `session_date` holds the cohort's date range
    # rather than one date, and these two print as "n x rate" in the
    # document's units column. Null on a single-session or manual row, which
    # still prints hours.
    cohort_id: Optional[UUID] = None
    session_count: Optional[int] = None
    rate_aed: Optional[float] = None
    # I5-1: exposed so the editable table can render rows in the order the
    # document prints them, and reorder without inventing its own.
    sort_order: int = 1

    class Config:
        from_attributes = True


class PaymentAddonOut(BaseModel):
    id: UUID
    description: str
    amount_aed: float
    notes: Optional[str] = None
    sort_order: int = 1

    class Config:
        from_attributes = True


class PaymentLetterOut(BaseModel):
    id: UUID
    instructor_user_id: Optional[UUID] = None
    instructor_name: Optional[str] = None
    batch_id: Optional[UUID] = None
    batch_name: Optional[str] = None
    letter_date: Optional[str] = None
    reference: str
    status: PaymentLetterStatus
    is_published: bool
    # I5-7: whether signing generates workshop-delivery certificates.
    issue_certificates: bool = True
    pdf_url: Optional[str] = None
    signed_pdf_url: Optional[str] = None
    signed_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
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


class PaymentLetterUpdate(BaseModel):
    """I5-7 — the certificate checkbox at payment prep."""

    issue_certificates: Optional[bool] = None
    admin_notes: Optional[str] = None
    batch_id: Optional[UUID] = None


class PaymentLetterCreate(BaseModel):
    instructor_user_id: UUID
    batch_id: Optional[UUID] = None
    letter_date: Optional[str] = None
    reference: str = "Facilitator Agreement"


class PaymentSessionCreate(BaseModel):
    session_date: Optional[str] = None
    workshop_description: str
    # I5-3: the role *name* as a plain string, snapshotted on the document.
    # Not an FK and not an enum — a signed letter keeps saying what it said,
    # and a role ops adds tomorrow prints without a migration.
    role: str
    location: Optional[str] = None
    duration_hours: Optional[float] = None
    compensation_aed: float = 0
    sort_order: int = 1


class PaymentAddonCreate(BaseModel):
    description: str
    amount_aed: float = 0
    notes: Optional[str] = None
    sort_order: int = 1


# I5-1. The model always carried every column the document prints; only the
# *add* form ever set three of them, and existing rows were read-only — which
# is why the finished letter was being hand-fixed in Word every time. These
# are partial: every field optional, unset fields left alone, so the table can
# save one cell without resubmitting the row.


class PaymentSessionUpdate(BaseModel):
    session_date: Optional[str] = None
    workshop_description: Optional[str] = None
    role: Optional[str] = None
    location: Optional[str] = None
    duration_hours: Optional[float] = None
    compensation_aed: Optional[float] = None
    # Cohort rows (2026-08-24): the number of ops-approved days and the
    # per-session rate behind the total. Editable like every other cell —
    # the computed figures are a draft, not a verdict.
    session_count: Optional[int] = None
    rate_aed: Optional[float] = None
    sort_order: Optional[int] = None


class PaymentAddonUpdate(BaseModel):
    description: Optional[str] = None
    amount_aed: Optional[float] = None
    notes: Optional[str] = None
    sort_order: Optional[int] = None


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
    instructor_email: Optional[str] = None
    type: str
    workshop_name: Optional[str] = None
    workshop_date: Optional[str] = None
    location: Optional[str] = None
    file_url: str


class CertificateCreate(BaseModel):
    instructor_user_id: UUID
    workshop_name: str
    workshop_date: str
    location: str
    send_email: bool = False


class BulkImportPreviewOut(BaseModel):
    instructor_count: int
    session_count: int
    addon_count: int
    unmatched_emails: list[str]
    errors: list[str]


class CohortInstructorPaymentOut(BaseModel):
    instructor_user_id: UUID
    full_name: str
    email: str
    role_name: str
    sessions_count: int
    assigned_sessions_count: int
    hours: float
    rate_aed: Optional[float] = None
    rate_basis: str = "per_session"
    total_aed: float = 0.0
    attendance_status: str = "no_checkin"
    attendance_tag: str = "No check-in"
    outcome: Literal["pending", "added", "ignored"] = "pending"
    has_active_draft: bool = False
    active_draft_letter_id: Optional[UUID] = None
    letter_id: Optional[UUID] = None
    letter_reference: Optional[str] = None
    letter_status: Optional[PaymentLetterStatus] = None
    payment_session_id: Optional[UUID] = None
    decided_at: Optional[datetime] = None


class CompletedCohortPaymentOut(BaseModel):
    cohort_id: UUID
    name: str
    program_name: str
    date_range: str
    completed_date: Optional[str] = None
    location: Optional[str] = None
    status: Literal["pending", "settled"]
    settled_outcome: Optional[Literal["added", "ignored", "partial"]] = None
    settled_at: Optional[datetime] = None
    instructors: list[CohortInstructorPaymentOut] = []


class SettleCohortInstructorIn(BaseModel):
    instructor_user_id: UUID
    action: Literal["add", "ignore"]
    role: str
    sessions_count: int = 1
    hours: Optional[float] = None
    rate_aed: Optional[float] = None
    compensation_aed: float = 0.0


class SettleCohortPaymentIn(BaseModel):
    batch_id: Optional[UUID] = None
    items: list[SettleCohortInstructorIn]


class SettleCohortPaymentOut(BaseModel):
    cohort: CompletedCohortPaymentOut
    created_drafts: int = 0
    appended_drafts: int = 0
    ignored_count: int = 0
    touched_letter_ids: list[UUID] = []


class CohortInstructorActionIn(BaseModel):
    instructor_user_id: Optional[UUID] = None


class MonthlyPaidPointOut(BaseModel):
    month_key: str
    month_label: str
    amount_aed: float
    letters_count: int


class PaymentsAnalyticsOut(BaseModel):
    total_paid_aed: float
    paid_letters_count: int
    paid_sessions_count: int
    paid_hours_count: float
    paid_instructors_count: int
    monthly_paid: list[MonthlyPaidPointOut] = []


class InstructorPaymentHistoryOut(BaseModel):
    instructor_user_id: UUID
    full_name: str
    email: str
    bank_details_complete: bool
    bank_name: Optional[str] = None
    total_paid_aed: float
    paid_letters_count: int
    paid_sessions_count: int
    paid_hours_count: float
    avg_aed_per_session: float
    monthly_paid: list[MonthlyPaidPointOut] = []
    draft_letters_count: int
    published_letters_count: int
    signed_letters_count: int
    pending_payout_aed: float
    letters: list[PaymentLetterOut] = []
