import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class Document(Base):
    """A generated document (letter) for a user — an instance of a document_template.

    Replaces the old per-type `recommendation_letters` / `intern_letters` tables; the
    template (or `label`) carries the identity, so there's no hardcoded letter type.
    Certificates keep their own first-class table (cert_type enum + payment_session link
    + auto-triggers).
    """

    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("document_templates.id", ondelete="SET NULL"), nullable=True)
    label = Column(String(255), nullable=False)         # display title (usually the template name)
    file_url = Column(Text, nullable=False)             # legacy fallback only — bucket/file_path are the source of truth (A2)
    bucket = Column(String(100), nullable=True)
    file_path = Column(Text, nullable=True)             # storage path; URLs generated at query time via storage.resolve_url
    generated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    data = Column(JSONB, nullable=False, default=dict)  # per-instance: signatory_name/title, body text, …
    generated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
