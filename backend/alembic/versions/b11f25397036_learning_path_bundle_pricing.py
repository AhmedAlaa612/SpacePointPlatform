"""learning path bundle pricing (Stripe Checkout, 2026-08-21)

`learning_paths.price_cents`/`currency` — integer minor units, NULL when not
purchasable as a bundle (existing free `/start` self-enrol is unaffected
either way). `purchases.learning_path_id` — sibling nullable FK to
`course_id`, `product_type` discriminator gains a `"learning_path"` value.
Partial unique index on `(user_id, learning_path_id)` where `status='pending'`
mirrors the existing course one — same double-payment backstop.
`enrollments.purchase_id` — which Purchase actually granted a given
enrollment row, so a bundle refund/dispute can revoke every enrollment it
created without touching a course the student already owned independently.

Revision ID: b11f25397036
Revises: c3e5a19d7f42
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b11f25397036"
down_revision = "c3e5a19d7f42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("learning_paths", sa.Column("price_cents", sa.Integer(), nullable=True))
    op.add_column(
        "learning_paths",
        sa.Column("currency", sa.String(3), nullable=False, server_default="usd"),
    )

    op.add_column(
        "purchases",
        sa.Column(
            "learning_path_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=True,
        ),
    )
    op.create_index(
        "uq_purchases_pending_per_path", "purchases", ["user_id", "learning_path_id"],
        unique=True, postgresql_where=sa.text("status = 'pending'"),
    )

    op.add_column(
        "enrollments",
        sa.Column(
            "purchase_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchases.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index("ix_enrollments_purchase_id", "enrollments", ["purchase_id"])


def downgrade() -> None:
    op.drop_index("ix_enrollments_purchase_id", table_name="enrollments")
    op.drop_column("enrollments", "purchase_id")
    op.drop_index("uq_purchases_pending_per_path", table_name="purchases")
    op.drop_column("purchases", "learning_path_id")
    op.drop_column("learning_paths", "currency")
    op.drop_column("learning_paths", "price_cents")
