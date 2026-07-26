import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class MergeReview(Base):
    """A pending human decision on two contacts that might be the same person —
    created whenever identity matching (R1-3) can't decide on its own. Never
    auto-resolved; an admin merges, keeps separate, or links as household."""

    __tablename__ = "merge_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_a = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    candidate_b = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    reason = Column(String(64), nullable=False)  # phone_match|import_ambiguous — no name-based reasons; name isn't used in matching
    status = Column(String(16), nullable=False, default="pending")  # pending|merged|kept_separate|linked_household
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    detail = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
