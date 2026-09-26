import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class Article(Base):
    """Clean CMS Article model replacing legacy blogs_registry.json.

    Supports collaborative multi-role authoring (interns, facilitators, instructors)
    with admin review workflows and safe markdown-to-sanitized-HTML compilation.
    """

    __tablename__ = "articles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(160), unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    content_markdown = Column(Text, nullable=False)
    content_html = Column(Text, nullable=False)
    category = Column(String(64), nullable=False, default="TECHNOLOGY", index=True)

    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    author_display_name = Column(String(128), nullable=False)
    author_role = Column(String(128), nullable=True)
    author_initials = Column(String(8), nullable=True)
    cover_image_url = Column(String(512), nullable=True)

    # Lifecycle: draft | in_review | changes_requested | published | archived
    status = Column(String(32), nullable=False, default="draft", index=True)
    reviewer_feedback = Column(Text, nullable=True)
    reviewed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # Optional integer for pinning articles to top of blog list / homepage
    featured_order = Column(Integer, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    author = relationship("User", foreign_keys=[author_id], lazy="selectin")
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id], lazy="selectin")
