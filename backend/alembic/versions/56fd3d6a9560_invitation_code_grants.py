"""invitation code grants (2026-08-21)

New `invitation_code_grants` table — a standing "this invite-code batch gets
these courses/paths free" rule, applied immediately to everyone who's ever
used the code and to every future signup on it. `product_type` discriminator
mirrors `Purchase.product_type`; no DB-level uniqueness (duplicate checks are
service-layer, same posture as `LmsProgramItem`).

Revision ID: 56fd3d6a9560
Revises: b11f25397036
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "56fd3d6a9560"
down_revision = "b11f25397036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invitation_code_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invitation_code_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invitation_codes.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("product_type", sa.String(16), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "learning_path_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_invitation_code_grants_invitation_code_id", "invitation_code_grants", ["invitation_code_id"])


def downgrade() -> None:
    op.drop_index("ix_invitation_code_grants_invitation_code_id", table_name="invitation_code_grants")
    op.drop_table("invitation_code_grants")
