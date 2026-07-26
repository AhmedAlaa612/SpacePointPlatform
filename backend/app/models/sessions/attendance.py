import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class AttendanceRecord(Base):
    """One student's attendance status for one session. method distinguishes a
    door QR scan from a manually-recorded entry — both write the same row shape."""

    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("registration_id", "session_id", name="uq_attendance_registration_session"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    registration_id = Column(UUID(as_uuid=True), ForeignKey("registrations.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    att_status = Column(String(12), nullable=False)  # present|absent
    method = Column(String(8), nullable=False, default="manual")  # manual|qr
    recorded_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
