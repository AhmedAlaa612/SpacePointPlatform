import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import ENUM, UUID

from app.db.base import Base
from app.models.enums import CertificateType


class Certificate(Base):
    """Shared certificate table (PLAN §4.5), unified with a `type` discriminator
    so workshop-delivery certs (instructors domain, Phase 3) and completion
    certs (interns/instructors, Phase 4) live in one place. `payment_session_id`
    and the workshop_* columns are only populated for type='workshop_delivery'.
    """

    __tablename__ = "certificates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(ENUM(CertificateType, name="certificate_type", create_type=False), nullable=False)
    file_url = Column(String, nullable=False)
    generated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    generated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # workshop_delivery-only fields (nullable for completion-cert rows)
    payment_session_id = Column(
        UUID(as_uuid=True), ForeignKey("payment_sessions.id", ondelete="SET NULL"), nullable=True
    )
    workshop_name = Column(String(255), nullable=True)
    workshop_date = Column(String(50), nullable=True)
    location = Column(String(255), nullable=True)
