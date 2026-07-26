import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Touchpoint(Base):
    """Every interaction with a person, across every channel — the raw material
    the CRM timeline and attribution are built from later. campaign_id and
    content_item_id are plain UUIDs (no FK) until the marketing tables land in
    the CRM phase; they're populated from day one so nothing has to be
    backfilled once that FK is added.
    """

    __tablename__ = "touchpoints"
    __table_args__ = (
        Index(
            "uq_touchpoints_channel_raw_platform_id",
            "channel", "raw_platform_id",
            unique=True,
            postgresql_where=text("raw_platform_id IS NOT NULL"),
        ),
        Index("ix_touchpoints_contact_occurred", "contact_id", "occurred_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)

    # whatsapp|instagram|facebook|tiktok|x|linkedin|email|web|phone|offline|ambassador|system
    channel = Column(String(24), nullable=False)
    # message_in|message_out|form_submit|page_visit|post_engagement|session_delivered|
    # registration|payment|import|staffing|other
    touchpoint_type = Column(String(32), nullable=False)
    direction = Column(String(8), nullable=True)  # in|out|n/a

    campaign_id = Column(UUID(as_uuid=True), nullable=True)
    content_item_id = Column(UUID(as_uuid=True), nullable=True)
    utm_source = Column(String(128), nullable=True)
    utm_medium = Column(String(128), nullable=True)
    utm_campaign = Column(String(128), nullable=True)
    utm_content = Column(String(128), nullable=True)
    utm_term = Column(String(128), nullable=True)

    occurred_at = Column(DateTime(timezone=True), nullable=False)
    raw_platform_id = Column(String(256), nullable=True)
    raw_payload_ref = Column(String(512), nullable=True)  # storage path, not inline JSON
    ingested_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime(timezone=True), nullable=True)
