"""W5 S5-3: widen the shared certificates table to also cover student
completion certs. Every existing row is a staff cert (user_id set); this
only loosens the constraint and adds the two new nullable columns + enum
value — nothing to backfill.

Operator decision (2026-07-24): widen the existing table with a type
discriminator, rather than a separate student-certificate mechanism, per
the model's own original "unified... one place" intent.

Revision ID: d1a4f8c0010
Revises: c9a5e17b0009
Create Date: 2026-07-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "d1a4f8c0010"
down_revision = "c9a5e17b0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("certificates", "user_id", nullable=True)
    op.add_column(
        "certificates",
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True),
    )
    op.add_column(
        "certificates",
        sa.Column("registration_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("registrations.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_check_constraint(
        "ck_certificate_exactly_one_owner", "certificates", "(user_id IS NOT NULL) != (contact_id IS NOT NULL)",
    )
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE certificate_type ADD VALUE IF NOT EXISTS 'student_completion'")


def downgrade() -> None:
    op.drop_constraint("ck_certificate_exactly_one_owner", "certificates", type_="check")
    op.drop_column("certificates", "registration_id")
    op.drop_column("certificates", "contact_id")
    op.alter_column("certificates", "user_id", nullable=False)
    # Postgres cannot drop a value from an enum type — no-op by design
    # (matches b2d8a91c0002's precedent for the same reason).
