"""mission proposals (7B-6, Missions Phase 2B, 2026-08-12)

The front door onto missions.status's draft/in_review/published pipeline —
see models/missions/proposal.py for the full design note. One table,
nothing else touches it yet.

Revision ID: b7305bf56b57
Revises: ee33eb03e57d
Create Date: 2026-08-11 15:53:32.959713

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b7305bf56b57'
down_revision: Union[str, None] = 'ee33eb03e57d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mission_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("repo_url", sa.String(512), nullable=True),
        sa.Column("zip_bucket", sa.String(64), nullable=True),
        sa.Column("zip_path", sa.String(512), nullable=True),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="submitted"),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("missions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mission_proposals_submitted_by", "mission_proposals", ["submitted_by"])
    op.create_index("ix_mission_proposals_status", "mission_proposals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_mission_proposals_status", table_name="mission_proposals")
    op.drop_index("ix_mission_proposals_submitted_by", table_name="mission_proposals")
    op.drop_table("mission_proposals")
