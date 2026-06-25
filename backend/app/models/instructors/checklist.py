import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class ChecklistModule(Base):
    """Phase 1 curriculum modules. Named `checklist_modules` (not bare
    `modules`) to avoid colliding with the interns domain's own `modules`
    table in the same schema (PLAN §4.3)."""

    __tablename__ = "checklist_modules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False, default=1)


class ModuleSection(Base):
    __tablename__ = "module_sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_id = Column(UUID(as_uuid=True), ForeignKey("checklist_modules.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False, default=1)


class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_id = Column(UUID(as_uuid=True), ForeignKey("checklist_modules.id", ondelete="CASCADE"), nullable=False)
    section_id = Column(
        UUID(as_uuid=True), ForeignKey("module_sections.id", ondelete="CASCADE"), nullable=True
    )
    item_code = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=1)
    is_required = Column(Boolean, nullable=False, default=True)


class UserChecklistProgress(Base):
    __tablename__ = "user_checklist_progress"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    checklist_item_id = Column(
        UUID(as_uuid=True), ForeignKey("checklist_items.id", ondelete="CASCADE"), nullable=False
    )
    is_completed = Column(Boolean, nullable=False, default=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
