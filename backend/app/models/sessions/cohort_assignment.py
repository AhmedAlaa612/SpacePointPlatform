import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class CohortInstructorAssignment(Base):
    """The record of the *deal* struck with one instructor for one cohort:
    which role they hold across the whole run, and what was agreed they'd be
    paid for it.

    **This deliberately reopens a boundary that was closed on 2026-07-24**,
    when `cohort_instructors` was dropped in `e5a2c93f0005` as "never wired
    to any endpoint". Go in with eyes open — it comes back for three reasons
    the old table never had:

    1. **The one-role-per-cohort rule needs somewhere to live.** The operator
       confirmed (2026-08-24) that an instructor can be Assistant in Cohort A
       and Instructor in Cohort B, but never both within one cohort. Deriving
       that by scanning `session_instructors` on every write is a race; a row
       here is the fact.
    2. **The rate has to be snapshotted at selection time.** `rate_aed` is
       copied from the resolved opening when ops picks someone, so editing
       `cohort_openings.amount_aed` next month cannot retroactively change
       what somebody already agreed to deliver for.
    3. **Withdrawal needs a record.** An instructor removed from every
       individual session would otherwise leave no trace that they were ever
       staffed.

    **It is NOT a second source of truth for staffing state.**
    `Session.staffing_status`, `services/sessions/openings.py::fully_staffed`
    and `SessionInstructor` remain the sole authority on who teaches which
    day — this row says *what the arrangement is*, they say *what is
    scheduled*. A session-only call that never involved a cohort assignment
    keeps working exactly as it does today, with no row here at all.

    Named `cohort_instructor_assignments` rather than reusing the old
    `cohort_instructors` specifically so `e5a2c93f0005`'s `downgrade()` —
    which recreates that table — can never collide with this one.

    `UNIQUE(cohort_id, user_id, role_id)` rather than `(cohort_id, user_id)`:
    production may already hold an instructor who genuinely took two roles
    across one cohort's sessions, and the backfill has to represent that
    honestly (as two rows, which then pay out as two correct lines) instead
    of failing or silently collapsing. The one-role rule is enforced in
    `services/sessions/cohort_staffing.py` for *new* selections, where it can
    return a readable 409 instead of an integrity error.
    """

    __tablename__ = "cohort_instructor_assignments"
    __table_args__ = (
        UniqueConstraint("cohort_id", "user_id", "role_id", name="uq_cohort_instructor_assignment"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # RESTRICT, matching SessionInstructor.role_id — a role that has ever been
    # assigned is referenced by history and is deactivated, never deleted.
    role_id = Column(UUID(as_uuid=True), ForeignKey("delivery_roles.id", ondelete="RESTRICT"), nullable=False)

    # per_session|flat. "per_session" multiplies `rate_aed` by the number of
    # ops-confirmed delivered days; "flat" pays `flat_amount_aed` outright
    # regardless of the count — the "if you attend all of them this is the
    # amount" arrangement the operator uses for the big camps.
    rate_basis = Column(String(16), nullable=False, default="per_session", server_default="per_session")
    # Snapshot of the resolved per-session rate at selection time (see the
    # class docstring). NULL for rows backfilled from pre-existing
    # SessionInstructor data, where no rate was ever recorded — the payment
    # line then falls back to resolving one live, same as it does today.
    rate_aed = Column(Numeric(10, 2), nullable=True)
    flat_amount_aed = Column(Numeric(10, 2), nullable=True)

    # active|withdrawn. Withdrawing keeps the row so the history stays
    # readable, the same reasoning DeliveryRole.is_active uses.
    status = Column(String(16), nullable=False, default="active", server_default="active")
    # call|direct — whether this came out of the marketplace or ops assigning
    # somebody straight onto sessions (the pre-existing direct-assign path in
    # routers/sessions/cohorts.py, which is untouched).
    source = Column(String(16), nullable=False, default="call", server_default="call")
    # Which call produced it, when one did. SET NULL: deleting a spent
    # grouping row must not erase the assignment it produced.
    cohort_call_id = Column(
        UUID(as_uuid=True), ForeignKey("cohort_calls.id", ondelete="SET NULL"), nullable=True
    )

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
