"""purchases and course pricing (Stripe Checkout, August Build Brief Branch 4)

`courses.price_cents`/`currency` — integer minor units, NULL when not paid.
New `purchases` table — one row per Stripe Checkout attempt, `product_type`
discriminator for Phase 2 reuse (Programs/registration). The partial unique
index on `(user_id, course_id)` where `status='pending'` is the server-side
double-payment backstop; scoped to pending so a legitimate repurchase after
a failed/completed attempt is never blocked.

Revision ID: 9a46ca83d607
Revises: 6dea285545b7
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "9a46ca83d607"
down_revision = "6dea285545b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("price_cents", sa.Integer(), nullable=True))
    op.add_column(
        "courses",
        sa.Column("currency", sa.String(3), nullable=False, server_default="usd"),
    )

    op.create_table(
        "purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_type", sa.String(32), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=True),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enrollments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("stripe_session_id", sa.String(255), nullable=True),
        sa.Column("stripe_payment_intent_id", sa.String(255), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_purchases_stripe_session_id", "purchases", ["stripe_session_id"])
    op.create_index("ix_purchases_stripe_payment_intent_id", "purchases", ["stripe_payment_intent_id"])
    op.create_index(
        "uq_purchases_pending_per_course", "purchases", ["user_id", "course_id"],
        unique=True, postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_table("purchases")
    op.drop_column("courses", "currency")
    op.drop_column("courses", "price_cents")
