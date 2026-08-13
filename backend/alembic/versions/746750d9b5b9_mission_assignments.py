"""mission assignments (2026-08-12)

`mission_assignments` — the mission-side equivalent of `enrollments`.
Missions had no grant table at all before this; `mission_attempts` is a run
record, not access. Mirrors `enrollments`' shape: soft-revoke via `status`
(active|inactive, never delete), `granted_by` SET NULL so the row survives
the granter's account being removed. See `models/missions/assignment.py`
for the full design note.

Revision ID: 746750d9b5b9
Revises: f3b7a2e91c5d
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '746750d9b5b9'
down_revision: Union[str, None] = 'f3b7a2e91c5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mission_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("missions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(12), nullable=False, server_default="ops"),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "mission_id", name="uq_mission_assignments_user_mission"),
    )


def downgrade() -> None:
    op.drop_table("mission_assignments")
