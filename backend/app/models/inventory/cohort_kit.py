import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class CohortKit(Base):
    """A kit ops has put on a cohort's *default* list — what every one of
    that cohort's sessions starts with, before any session-specific kit
    activity happens (Phase 3 follow-up to the session kit loop, I2-1/I2-2).

    This is deliberately a thinner table than `SessionKit`: no
    `received_at`/`return_status`/`ops_confirmed_at`. Those columns exist on
    `SessionKit` because a session is a real teaching unit on a real date,
    with an instructor who can physically hold a kit and hand it back. A
    cohort is not a day — it is a plan for many days — so there is nothing to
    receive and nothing to return here. The instructor-facing receive/return
    workflow only ever happens once a cohort default has been materialized
    onto an actual session (see `materialize_session_kits`); this row never
    itself represents custody of anything.

    It is also not a reservation. A `Kit` is one physical, serialised box
    (see `Kit`'s own docstring) — the same box cannot usefully be "held" by
    two different cohort defaults, and this table doesn't try to arbitrate
    that. `cohort_kits` just labels which kits a cohort's sessions should
    default to; the only place a kit is ever actually claimed for a specific
    date is `SessionKit`, created at materialization time. Two cohorts can
    list the same kit as a default with no conflict, exactly as two sessions
    in the same cohort could (in principle) both materialize it — this table
    does not know or care whether the box is free.

    `created_by` is RESTRICT, matching `SessionKit.created_by`: whoever set a
    cohort's default kit list is attribution, not a resource to garbage
    collect on staff departure.
    """

    __tablename__ = "cohort_kits"
    __table_args__ = (
        UniqueConstraint("cohort_id", "kit_id", name="uq_cohort_kit"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id = Column(
        UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kit_id = Column(
        UUID(as_uuid=True), ForeignKey("kits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
