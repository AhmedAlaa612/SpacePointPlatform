"""Schemas for the operations "registration desk" (V2 R2-3) — manual
registration, the registrations list, and the payment/ticket actions that go
with it. Kept in its own module rather than folded into cohorts.py, mirroring
how the public flow's request schema lives in its own
schemas/sessions/public_registration.py rather than in cohorts.py or
registration.py.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr

PaymentStatus = Literal["unpaid", "partial", "paid", "waived", "refunded"]
RegistrationStatus = Literal["registered", "attended", "completed", "cancelled", "no_show"]


class DeskRegistrationRequest(BaseModel):
    """Manual, in-person/by-phone registration taken by an operations staff
    member. No age/minor detection or enforcement — parent details are always
    optional; if given, that contact is linked as guardian/payer."""

    student_name: str
    email: EmailStr
    phone: str
    city: str | None = None

    # Purely informational (2026-07-24, CEO request) — no age/minor
    # enforcement anywhere. organization_name resolves or creates a school
    # Organization by name.
    date_of_birth: date | None = None
    grade: str | None = None
    organization_name: str | None = None

    parent_name: str | None = None
    parent_phone: str | None = None
    parent_email: EmailStr | None = None

    # Which of the cohort's sessions this registration covers. None means
    # "every session in the cohort" — see PublicRegistrationRequest.
    session_ids: list[UUID] | None = None

    # Desk-only: staff can choose not to send the ticket email at all (e.g.
    # they're printing it directly, or sending it manually later).
    send_ticket_email: bool = True


class RegistrationAttendanceOut(BaseModel):
    session_id: UUID
    meeting_date: date
    session_title: str | None = None
    att_status: str
    recorded_at: datetime | None = None


class RegistrationOut(BaseModel):
    """One registration row — a Registration joined with its Contact (and,
    when payer_contact_id is set, the guardian's contact too)."""

    id: UUID
    contact_id: UUID
    student_name: str
    student_phone: str | None = None
    student_email: str | None = None
    student_date_of_birth: date | None = None
    student_grade: str | None = None
    student_organization_name: str | None = None
    payer_contact_id: UUID | None = None
    guardian_name: str | None = None
    guardian_phone: str | None = None
    payment_status: PaymentStatus
    price_charged: Decimal | None = None
    status: RegistrationStatus
    registered_via: str
    is_repeat: bool
    ticket_sent: bool
    checked_in: bool
    # Whether a certificate exists at all. certificate_url below is only ever
    # set for certs that were stored as a file — student completion certs are
    # emailed as a PDF attachment and never uploaded, so they have a row and
    # no URL. Keying "has a certificate" off the URL made every student
    # certificate invisible in the ops list.
    certificate_issued: bool = False
    certificate_url: str | None = None
    attended_sessions_count: int = 0
    total_cohort_sessions_count: int = 0
    attendance_records: list[RegistrationAttendanceOut] = []
    created_at: datetime


class ConfirmPaymentRequest(BaseModel):
    amount: Decimal
    # "paid" is the primary case; "partial" is supported for the desk to
    # record a deposit without needing a separate endpoint.
    status: Literal["paid", "partial"] = "paid"
