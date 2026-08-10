"""mission_teams + mission_team_members (P6-1, LMS Phase 2 Stage 6, 2026-08-11).

Deliberately not models/interns/team.py's teams table — that one's name is
globally UNIQUE, epics.team_id is NOT NULL, and project_teams joins it to
projects. mission_teams is cohort-scoped (UNIQUE(cohort_id, name)), NULL
cohort_id for a self-formed team from the public catalog.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "8dd8994b9a4b"
down_revision = "4011c4274501"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mission_teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("cohort_id", "name", name="uq_mission_teams_cohort_name"),
    )
    op.create_index("ix_mission_teams_cohort_id", "mission_teams", ["cohort_id"])

    op.create_table(
        "mission_team_members",
        sa.Column("mission_team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mission_teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("mission_team_id", "user_id", name="pk_mission_team_members"),
    )
    op.create_index("ix_mission_team_members_user_id", "mission_team_members", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_mission_team_members_user_id", table_name="mission_team_members")
    op.drop_table("mission_team_members")
    op.drop_index("ix_mission_teams_cohort_id", table_name="mission_teams")
    op.drop_table("mission_teams")
