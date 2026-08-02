import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class SessionCall(Base):
    """One open-call "campaign" on a session (2026-08-01) — a session can run
    several of these at once: a public call open to everyone, and a separate
    targeted call aimed at two specific instructors for a role still needed,
    both live at the same time, each independently viewable/editable/closeable.

    Before this, `SessionCallTarget` rows were tagged only with `session_id` —
    one flat target list per session, so "open a public call" and "also
    target these two people" collided into a single restriction rather than
    two coexisting calls. Each `SessionCallTarget` row now also carries
    `call_id`, scoping it to the specific call that created it.

    `session.staffing_status` stays the session-wide summary it always was
    (unstaffed|open_call|staffed) — `open_call` means "at least one call here
    is open", derived by the service layer on every mutation, same as before.

    A call can optionally belong to a standing `CohortCall` (2026-08-01,
    `cohort_call_id`) — pure grouping label for ops managing several sessions'
    calls as one campaign, no change whatsoever to this call's own open/
    close/target mechanics; a session-level call opened directly (no
    cohort_call_id) behaves exactly as it always has.
    """

    __tablename__ = "session_calls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    # open|closed
    status = Column(String(16), nullable=False, default="open")
    # Ops-facing name, e.g. "Backup facilitators" — optional, purely for
    # telling calls apart in the list when there's more than one.
    label = Column(String(64), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    closed_at = Column(DateTime(timezone=True), nullable=True)
    # Optional grouping into a cohort-wide call (2026-08-01) — NULL for a
    # call opened directly on this session, independent of any cohort call.
    cohort_call_id = Column(UUID(as_uuid=True), ForeignKey("cohort_calls.id", ondelete="SET NULL"), nullable=True, index=True)
