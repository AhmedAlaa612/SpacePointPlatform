import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base

#: Editorial lifecycle for website articles (Step 5).
ARTICLE_STATUSES = (
    "draft",
    "submitted",
    "in_review",
    "changes_requested",
    "published",
    "archived",
)


class WebsiteArticle(Base):
    """Contributor-authored article backing spacepoint.ae/insights.

    Step 5 — Articles, Blog & Editorial Review Queue: contributors draft in
    Markdown (`content_markdown`); `content_html` is the sanitized render
    served to the public site. Only `published` rows are publicly visible.
    """

    __tablename__ = "articles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    summary = Column(Text, nullable=True)
    content_markdown = Column(Text, nullable=False)
    content_html = Column(Text, nullable=False)
    category = Column(String(64), nullable=False, default="EDUCATION")
    cover_image_url = Column(String(512), nullable=True)
    status = Column(String(32), nullable=False, default="draft")
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    author_display_name = Column(String(255), nullable=False)
    author_role = Column(String(128), nullable=True)
    author_initials = Column(String(8), nullable=True)
    reviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewer_feedback = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    featured_order = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
