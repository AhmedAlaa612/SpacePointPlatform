import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class IdentityAlias(Base):
    """Every external identifier that resolves to a contact — email, phone,
    a WhatsApp wa_id, a Madar student id, a social handle. The
    (alias_type, alias_value_hash) unique constraint is what makes identity
    matching a simple lookup instead of a fuzzy search for the exact-match
    cases (see services/spine/identity.py, R1-3)."""

    __tablename__ = "identity_aliases"
    __table_args__ = (
        UniqueConstraint("alias_type", "alias_value_hash", name="uq_identity_alias_type_hash"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)

    # email|phone|wa_id|ig_handle|fb_psid|x_handle|tiktok_handle|linkedin_id|
    # madar_user|legacy_inventory_instructor|lp_cookie
    # NOTE: VARCHAR(32), not (24) — 'legacy_inventory_instructor' itself is 27 chars.
    alias_type = Column(String(32), nullable=False)
    alias_value_hash = Column(String(64), nullable=False)  # sha256 hex of the normalized value — the lookup key
    alias_value_plain = Column(String(256), nullable=True)  # kept for internal ids (madar_user); hash-only otherwise
    matched_by = Column(String(24), nullable=False)  # deterministic_exact|manual_merge|import
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
