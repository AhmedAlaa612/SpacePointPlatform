import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import ENUM, UUID

from app.db.base import Base
from app.models.enums import UserRole


class IdCard(Base):
    """Shared across all roles (PLAN §4.5) — one row per generated card."""

    __tablename__ = "id_cards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(ENUM(UserRole, name="user_role", create_type=False), nullable=False)
    card_id = Column(String(50), nullable=True)  # e.g. SP-INS-0012
    front_url = Column(String, nullable=True)
    back_url = Column(String, nullable=True)
    pdf_url = Column(String, nullable=True)
    generated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
