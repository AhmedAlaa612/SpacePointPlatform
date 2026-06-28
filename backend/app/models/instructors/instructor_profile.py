from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class InstructorProfile(Base):
    """Only linkedin/photo/contract fields — the ID card itself (front/back/pdf
    URLs + card_id) lives solely in the shared `id_cards` table (PLAN §4.5),
    not duplicated here, to avoid two places storing the same URLs."""

    __tablename__ = "instructor_profiles"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    contract_url = Column(String, nullable=True)
    signed_contract_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
