import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Session(Base):
    """The actual teaching unit inside a cohort — not just a calendar date.
    A single-day workshop is a cohort with exactly one Session; a multi-week
    course has one row per meeting. Each Session can carry its own title,
    instructor(s) (via SessionInstructor below), attendance, and — since
    pricing can be per-session instead of per-program — its own price
    override (falls back to Program.price when NULL). `material_url` is
    reserved for the future LMS/teacher-side link; nothing reads it yet."""

    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("cohort_id", "meeting_date", "starts_at", name="uq_session_slot"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False)
    meeting_date = Column(Date, nullable=False)
    starts_at = Column(Time, nullable=True)
    title = Column(String(256), nullable=True)
    material_url = Column(Text, nullable=True)
    price = Column(Numeric(10, 2), nullable=True)
    # unstaffed|open_call|staffed — the staffing marketplace pipeline (W4).
    # Lives on Session, not Cohort (moved 2026-07-24): assignment is per-
    # session, so the open-call/interest/select state has to be too, or a
    # cohort with 9 sessions couldn't tell "3 staffed, 6 still open" apart.
    staffing_status = Column(String(16), nullable=False, default="unstaffed")
    # Instructor delivery (W5 S5-1) — NULL until the assigned instructor taps
    # "start"/"mark done" on the day. Two nullable timestamps rather than a
    # status string: they double as the actual start/finish record, not just
    # a flag, which the calendar/dashboard work (W6) will want to read.
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SessionInstructor(Base):
    """Instructor assigned to one specific Session — not the whole cohort.
    A cohort with several sessions can have a different instructor per
    session; "assign to the whole cohort" is just a bulk action in the UI
    that writes one of these per session, not a separate data concept.
    Replaces the earlier cohort-level CohortInstructor, which was never
    wired into any router (staffing marketplace lands week 4)."""

    __tablename__ = "session_instructors"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_session_instructor"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(16), nullable=False, default="lead")  # lead|co
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SessionCallTarget(Base):
    """Restricts an open call to specific instructors (operator, 2026-07-26).

    Semantics are deliberately "absent means unrestricted": a session with no
    rows here is open to every instructor/facilitator, which is what every
    existing open call is and what the plain "open call" button still does.
    Rows here make it a real gate — targeted users are the only ones who see
    the session on Available Sessions and the only ones who may register
    interest.

    Before this table, the instructor picker on the open-call dialog only
    filtered who got *notified*; the session itself was visible to everyone,
    so "targeted" was a mailing list rather than a restriction.
    """

    __tablename__ = "session_call_targets"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_session_call_target"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
