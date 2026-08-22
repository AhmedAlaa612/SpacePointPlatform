"""Stripe Checkout purchases (Stage S, August Build Brief Branch 4) — one-time
payments for paid LMS courses. Hosted Checkout, webhook-driven fulfilment via
`services/lms/checkout.py::fulfill`.

`product_type` is a flat string discriminator, matching this repo's existing
pattern (`Course.access_mode`, `Enrollment.source`) rather than a polymorphic
or joined-table setup — one column, and it's what lets a Phase 2 Programs/
registration purchase reuse this table instead of a rebuild. `course_id` is
never renamed for that reuse; a sibling nullable FK (e.g. `program_id`) gets
added alongside it instead.

`product_type` is "lms_course" or "learning_path" (2026-08-21, path-bundle
pricing) — `learning_path_id` is the sibling nullable FK the docstring above
predicted. A bundle purchase still isn't a line-item cart: it grants every
step's course in one `fulfill()` pass, and which enrollments it actually
created (as opposed to ones the student already had independently) is
tracked on `Enrollment.purchase_id`, not here — `enrollment_id` below stays
single-row and is only ever set for a `lms_course` purchase.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Purchase(Base):
    """`status`: pending|paid|refunded|disputed|failed.

    The partial unique index is the server-side double-payment backstop —
    scoped to `status='pending'` so a legitimate repurchase after a failed or
    completed attempt is never blocked. It's cheap here specifically because
    the row is always inserted before the Stripe session is created (see the
    checkout router): the losing insert fails before Stripe is ever
    contacted, so there is no orphaned session to clean up.

    No `stripe_charge_id` column — refunds and disputes are both matched via
    `stripe_payment_intent_id`; the one branch that needs a charge-based
    fallback (a dispute with a null `payment_intent`) derives it on demand
    via a single `Charge.retrieve_async` call instead.
    """

    __tablename__ = "purchases"
    __table_args__ = (
        Index(
            "uq_purchases_pending_per_course",
            "user_id", "course_id",
            unique=True, postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "uq_purchases_pending_per_path",
            "user_id", "learning_path_id",
            unique=True, postgresql_where=text("status = 'pending'"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    product_type = Column(String(32), nullable=False)  # "lms_course" | "learning_path"
    # Phase 2 adds program_id/registration_id as sibling nullable FKs
    # matching product_type — never rename this one.
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=True)
    learning_path_id = Column(
        UUID(as_uuid=True), ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=True
    )

    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="SET NULL"), nullable=True)

    stripe_session_id = Column(String(255), unique=True, nullable=True)  # set right after session creation
    stripe_payment_intent_id = Column(String(255), index=True, nullable=True)  # refund/dispute matching key

    amount_cents = Column(Integer, nullable=False)  # snapshotted at checkout time
    currency = Column(String(3), nullable=False)

    status = Column(String(16), nullable=False, default="pending", server_default="pending")

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    paid_at = Column(DateTime(timezone=True), nullable=True)
    refunded_at = Column(DateTime(timezone=True), nullable=True)
