import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ENUM, UUID

from app.db.base import Base
from app.models.enums import PaymentLetterStatus


class PaymentBatch(Base):
    __tablename__ = "payment_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_by_admin_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PaymentLetter(Base):
    __tablename__ = "payment_letters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(UUID(as_uuid=True), ForeignKey("payment_batches.id", ondelete="SET NULL"), nullable=True)
    instructor_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    letter_date = Column(String(50), nullable=True)
    reference = Column(String(255), nullable=False, default="Facilitator Agreement")
    status = Column(
        ENUM(PaymentLetterStatus, name="payment_letter_status", create_type=False),
        nullable=False,
        default=PaymentLetterStatus.draft,
    )
    is_published = Column(Boolean, nullable=False, default=False)
    pdf_url = Column(String, nullable=True)         # legacy fallback only — *_path are the source of truth (A2; bucket "payment-letters")
    signed_pdf_url = Column(String, nullable=True)
    pdf_path = Column(String, nullable=True)
    signed_pdf_path = Column(String, nullable=True)
    instructor_signature_data = Column(Text, nullable=True)  # base64 PNG, re-embedded into the PDF on each sign
    signed_at = Column(DateTime(timezone=True), nullable=True)
    admin_notes = Column(Text, nullable=True)
    # I5-7. Certificates already generate on signing, one per payment session.
    # The CEO asked to make that optional — set at letter-prep, honoured at
    # signing. Defaults true so existing behaviour is unchanged.
    issue_certificates = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class PaymentSession(Base):
    __tablename__ = "payment_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_letter_id = Column(
        UUID(as_uuid=True), ForeignKey("payment_letters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # I5-8. Nullable FK — manual lines keep working, and this is what stops a
    # completed session being billed twice. SET NULL rather than CASCADE: a
    # deleted session must not erase a payment record.
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    session_date = Column(String(50), nullable=True)
    workshop_description = Column(String(255), nullable=False)
    # I5-3: a plain String holding the role *name* at the time, no longer the
    # `payment_session_role` enum. **Deliberately a snapshot, not an FK to
    # `delivery_roles`:** a signed letter has to keep saying what it said,
    # even if someone renames a role two years later. Documents freeze; live
    # assignments don't. Widening it to a string also means a role ops adds
    # tomorrow can be printed without an enum migration.
    role = Column(String(64), nullable=False)
    location = Column(String(255), nullable=True)
    duration_hours = Column(Float, nullable=True)
    compensation_aed = Column(Float, nullable=False, default=0)
    sort_order = Column(Integer, nullable=False, default=1)


class PaymentAddon(Base):
    __tablename__ = "payment_addons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_letter_id = Column(
        UUID(as_uuid=True), ForeignKey("payment_letters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description = Column(String(255), nullable=False)
    amount_aed = Column(Float, nullable=False, default=0)
    notes = Column(String(255), nullable=True)
    sort_order = Column(Integer, nullable=False, default=1)


class InstructorBankDetails(Base):
    __tablename__ = "instructor_bank_details"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    account_holder_name = Column(String(255), nullable=True)
    bank_name = Column(String(255), nullable=True)
    iban = Column(String(50), nullable=True)
    swift_bic = Column(String(20), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class PortalSetting(Base):
    """Key/value store — signatory defaults, admin signature image path, etc."""

    __tablename__ = "portal_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
