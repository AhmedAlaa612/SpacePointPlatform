import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class CohortCall(Base):
    """A standing grouping over a set of per-session `SessionCall` rows
    (operator ask, 2026-08-01): "open a call across a chosen subset of a
    cohort's sessions, not necessarily all, and manage/close it as one
    thing." `open_call_for_cohort` already existed and bulk-opens an
    independent `SessionCall` on every unstaffed session in a cohort, but
    it's a fire-and-forget loop — nothing records that those N calls were
    "the same ask", so there was no way to view or close them together
    afterwards, or to restrict the bulk-open to a chosen subset of sessions
    in the first place. This row is that missing record.

    This is pure grouping — it does NOT introduce a cohort-level staffing
    state. `Cohort` (see its own docstring) and `Session.staffing_status`
    keep meaning exactly what they meant before "moved to Session, 2026-07-
    24, W4" — a cohort with several sessions can still be partly staffed,
    and a session's own staffing pipeline is untouched by any cohort call
    that happens to be grouping one of its `SessionCall` rows. A session can
    also still run a fully independent call of its own (via the existing
    single-session `open_call`) at the same time a cohort call is live on
    it — the two don't interact.

    `status` is a DERIVED summary, same pattern as `Session.staffing_status`:
    "open" while at least one linked `SessionCall` (via
    `SessionCall.cohort_call_id == this.id`) is still open, "closed" once
    none are. It is never set directly by a caller — the service layer
    (`_sync_cohort_call_status`) recomputes it after every mutation that
    could have changed it (closing a session's call, one of the grouped
    sessions reaching fully staffed, etc).
    """

    __tablename__ = "cohort_calls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, index=True)
    # open|closed — derived, see class docstring. Defaults open: a cohort
    # call is only ever created already-open (there's no draft state).
    status = Column(String(16), nullable=False, default="open")
    # Ops-facing name, e.g. "September intake — public call" — optional,
    # same purpose as SessionCall.label: telling calls apart in a list.
    label = Column(String(64), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    closed_at = Column(DateTime(timezone=True), nullable=True)


class CohortCallTarget(Base):
    """Restricts one `CohortCall` to specific users — same "absent means
    unrestricted" contract as `SessionCallTarget` (see its docstring): a
    cohort call with no rows here is public across every session it opened.

    This is deliberately a separate target list from `SessionCallTarget`,
    not a join through it: the cohort call's targeting is the *intent*
    ("these three people, across whichever sessions get opened"), applied
    to each underlying `SessionCall` at creation time by the service layer.
    `cohort_id` is denormalised from `CohortCall.cohort_id` purely so
    lookups don't need a join, same reasoning `SessionCallTarget.session_id`
    already uses relative to `SessionCall.session_id`.
    """

    __tablename__ = "cohort_call_targets"
    __table_args__ = (
        UniqueConstraint("cohort_call_id", "user_id", name="uq_cohort_call_target"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_call_id = Column(UUID(as_uuid=True), ForeignKey("cohort_calls.id", ondelete="CASCADE"), nullable=False, index=True)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
