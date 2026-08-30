import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY

from app.db.base import Base


class EmailTemplate(Base):
    """Every system email the platform sends, one row per code-wired trigger
    (see `app/db/email_template_defaults.py` for the fixed set of 25 keys).

    Unlike `DocumentTemplate`, this table is never a create/delete surface —
    each `key` is referenced directly by a specific call site in the code, so
    an admin can only edit `subject`/`body_html` and toggle `is_paused`.
    `placeholders`/`attachment_labels` are informational, generated from the
    same defaults that seed the row, not admin-editable.
    """

    __tablename__ = "email_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(64), nullable=False)
    description = Column(Text, nullable=False)  # admin-facing "when this is sent" copy
    subject = Column(Text, nullable=False)
    body_html = Column(Text, nullable=False)
    placeholders = Column(ARRAY(String), nullable=False, default=list)
    attachment_labels = Column(ARRAY(String), nullable=False, default=list)
    is_paused = Column(Boolean, nullable=False, default=False)
    is_internal = Column(Boolean, nullable=False, default=False)  # admin-notification ping, not a user lifecycle email
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
