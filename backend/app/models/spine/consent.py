import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class ConsentRecord(Base):
    """Append-only consent log. Current status for a (contact, consent_type) is
    the latest row by created_at — withdrawal INSERTS a new row, it never
    updates the old one, so the history of every opt-in/opt-out is preserved.
    The full gate (services/spine/consent.py) lands at CRM phase start; this
    table just needs to exist so registration forms can write to it now.
    """

    __tablename__ = "consent_records"
    __table_args__ = (
        Index("ix_consent_records_contact_type", "contact_id", "consent_type"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    consent_type = Column(String(32), nullable=False)  # whatsapp_marketing|email_marketing|data_processing
    status = Column(String(16), nullable=False)  # granted|withdrawn
    granted_at = Column(DateTime(timezone=True), nullable=True)
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    source = Column(String(64), nullable=False)  # form key, import batch, wa_optin, manual
    jurisdiction = Column(String(8), nullable=True)
    guardian_contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
