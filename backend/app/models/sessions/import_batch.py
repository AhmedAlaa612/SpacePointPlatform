import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class ImportBatch(Base):
    """One upload of a bulk student sheet — a B2B client's registered-students
    sheet, or a historical backfill import. Always dry-run first (counts
    populated, nothing committed), then committed on operator confirmation
    (see services/sessions/importer.py, R2-2)."""

    __tablename__ = "import_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source = Column(String(16), nullable=False)  # b2b_sheet|backfill
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True)
    filename = Column(String(255), nullable=False)
    status = Column(String(12), nullable=False, default="dry_run")  # dry_run|committed|failed
    # {rows, created, linked, review_queued, errors: [{row, reason}]}
    counts = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
