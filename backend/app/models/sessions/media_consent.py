"""Cohort Media Consent domain model (2026-09-27).

Tracks parental/guardian consent for photography, videography, interviews,
and promotional usage for students in a cohort.

Supports:
- Webhook ingestion from external Google Forms via Google Apps Script.
- Email-first, phone-second matching against cohort registrations.
- Updating/replacing student guardian data upon match.
- Unmatched submission logging with 1-click manual ops linking.
- Manual consent state override (paper forms, WhatsApp agreements).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class CohortMediaConsent(Base):
    """A media consent submission or manual record for a cohort.

    Can be linked to a Registration (if matched or manually assigned), or left
    unmatched (registration_id=None, match_status='unmatched') for staff to review.
    """

    __tablename__ = "cohort_media_consents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id = Column(
        UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    registration_id = Column(
        UUID(as_uuid=True), ForeignKey("registrations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    matched_contact_id = Column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Raw form inputs (for display and legal audit)
    student_name_raw = Column(String(255), nullable=True)
    student_email_raw = Column(String(255), nullable=True)
    school_name_raw = Column(String(255), nullable=True)

    # Parent/Guardian details
    parent_name = Column(String(255), nullable=False)
    relationship = Column(String(64), nullable=True)  # Mother, Father, Legal Guardian, Other
    parent_phone = Column(String(64), nullable=True)
    parent_email = Column(String(255), nullable=True)

    # Consent decision & grants
    consent_choice = Column(String(32), nullable=False, default="consented")  # consented | declined
    permission_grants = Column(JSONB, nullable=False, default=list)  # list of strings
    declaration_agreed = Column(Boolean, nullable=False, default=True)
    date_of_signing = Column(Date, nullable=True)

    # Processing metadata
    source = Column(String(32), nullable=False, default="google_form")  # google_form | manual_override | desk
    match_status = Column(String(32), nullable=False, default="unmatched")  # matched | unmatched | manual
    match_method = Column(String(32), nullable=True)  # email | phone | manual

    notes = Column(Text, nullable=True)
    raw_payload = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
