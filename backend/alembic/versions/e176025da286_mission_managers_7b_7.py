"""mission managers (7B-7, Missions Phase 2B, 2026-08-12)

D7's payoff: a resource-scoped permission letting a specific user (usually
the intern whose proposal became this mission) manage just that one
mission — see models/missions/manager.py for the full design note.

Revision ID: e176025da286
Revises: b7305bf56b57
Create Date: 2026-08-11 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e176025da286'
down_revision: Union[str, None] = 'b7305bf56b57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mission_managers",
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("missions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("mission_id", "user_id", name="pk_mission_managers"),
    )
    op.create_index("ix_mission_managers_user_id", "mission_managers", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_mission_managers_user_id", table_name="mission_managers")
    op.drop_table("mission_managers")
