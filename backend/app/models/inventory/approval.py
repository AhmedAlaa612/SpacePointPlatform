import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class InventoryActionPolicy(Base):
    """One row per gateable action type (2026-08-27 approvals/purchasing
    follow-up). `requires_approval` is the whole point: the COO flips it on
    or off per action type, and nothing in the code needs to change when
    they do. Every known action type gets a row (seeded at `False` by the
    migration), so a missing row is never ambiguous — it's only possible for
    a brand-new action type `ACTION_TYPES` hasn't been seeded for yet, and
    `services/inventory/approvals.py::policy_requires_approval` treats an
    absent row the same as `False`, matching the "nothing gates until the
    COO turns it on" deploy guarantee.
    """

    __tablename__ = "inventory_action_policies"

    action_type = Column(String(64), primary_key=True)
    requires_approval = Column(Boolean, nullable=False, default=False, server_default="false")

    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class InventoryApprovalRequest(Base):
    """A queued action, waiting on a COO (or admin) decision.

    `payload` is the exact kwargs the original write needs — captured once,
    at submission time, after every existence/ownership check the direct
    endpoint already runs, so a request only ever reaches the queue for a
    *policy* reason, never a data one. Approving replays it through
    `ACTION_EXECUTORS[action_type]` with `requested_by` (not the reviewer) as
    the actor, because the storekeeper who will actually carry it out is who
    the resulting Movement should say did it — the COO's name lives in
    `reviewed_by`, not `created_by`.

    No `error` column: if the replay fails (the world moved between
    submission and review — the warehouse was deactivated, the count changed
    again), the approve endpoint surfaces that as a 409 and the request
    stays `pending` for the COO to retry or reject. Nothing silently succeeds
    on stale state, and nothing needs a second failure state to express that.
    """

    __tablename__ = "inventory_approval_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    action_type = Column(String(64), nullable=False, index=True)
    status = Column(String(16), nullable=False, default="pending", server_default="pending", index=True)
    summary = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=False)

    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    requested_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_note = Column(Text, nullable=True)
