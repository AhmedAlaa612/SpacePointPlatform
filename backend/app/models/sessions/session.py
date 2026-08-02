import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Numeric, String, Text, Time, UniqueConstraint
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
    # I5-2. NULL = inherit from the cohort, then the program.
    duration_hours = Column(Numeric(5, 2), nullable=True)
    # Free-text comments from whoever delivered the session (I2-7, operator
    # 2026-07-30). Deliberately one editable blob rather than a comment log:
    # the ask was "a simple comments text area", and the job it has to do is
    # give an instructor somewhere to put a fact the system can't model yet —
    # "took a speaker that isn't in the list" — instead of silently dropping
    # it. Ops reads it on the session; nothing notifies them (operator's call).
    notes = Column(Text, nullable=True)
    # NULL = inherit the cohort's location (2026-08-01) — same absent-means-
    # inherit pattern as duration_hours/price above. Only set when a specific
    # session genuinely meets somewhere other than the cohort's usual place.
    location_id = Column(UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    # NULL = inherit the cohort's warehouse, same pattern as location_id —
    # see Cohort.warehouse_id for why this is a separate field from location.
    warehouse_id = Column(UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True)
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
    # Cohort-level kit defaults (Phase 3 follow-up to I2-1/I2-2): a session
    # with no kit activity of its own inherits its cohort's default kit list.
    # The first time this specific session's kits are touched — ops assigns/
    # removes one directly, or an instructor receives/returns one — the
    # cohort's current default is copied into real `SessionKit` rows here and
    # this flips to True for good. It has to be a separate flag rather than
    # inferred from `SessionKit` row count: a session ops deliberately clears
    # down to zero kits is legitimately zero rows, and without this flag that
    # is indistinguishable from a session nobody has touched yet — the first
    # would silently revert to inheriting the cohort default on the next
    # read, which is exactly the bug this column exists to prevent.
    kits_overridden = Column(Boolean, nullable=False, default=False)
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
    # I5-3: roles are data now (`delivery_roles`), not a `lead|co` string.
    # The old column is remapped by migration `c2a7b49e0022`, not dropped
    # blind — production holds real rows.
    role_id = Column(
        UUID(as_uuid=True), ForeignKey("delivery_roles.id", ondelete="RESTRICT"), nullable=False
    )
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SessionCallTarget(Base):
    """Restricts one specific call to specific instructors (operator,
    2026-07-26; scoped per-call 2026-08-01).

    Semantics are deliberately "absent means unrestricted": a *call* with no
    rows here is open to every instructor/facilitator. Since a session can
    run several calls at once (`SessionCall`), a session overall is public
    the moment any one of its open calls has no target rows — a targeted call
    running alongside it doesn't take that away. Rows here make one call a
    real gate — targeted users are the only ones who see the session on
    Available Sessions *because of that call* (another open call may still
    grant them, or anyone, visibility).

    Before `call_id` existed, every row was tagged only with `session_id` —
    one flat target list per session, so a public call and a targeted call
    could never coexist. `session_id` stays alongside `call_id` (denormalised
    from `SessionCall.session_id`) purely so lookups don't need a join.
    """

    __tablename__ = "session_call_targets"
    __table_args__ = (
        UniqueConstraint("call_id", "user_id", name="uq_session_call_target"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_id = Column(UUID(as_uuid=True), ForeignKey("session_calls.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
