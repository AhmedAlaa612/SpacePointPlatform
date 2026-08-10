"""team-scoped attempts (P6-2, LMS Phase 2 Stage 6, 2026-08-11).

mission_attempts.mission_team_id + CHECK(user_id XOR mission_team_id).
mission_attempt_members freezes who was on the team for one specific
attempt — team membership can change after that; grading history must not.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "35229e5bc00b"
down_revision = "8dd8994b9a4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mission_attempts",
        sa.Column("mission_team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mission_teams.id", ondelete="RESTRICT"), nullable=True),
    )
    op.create_index("ix_mission_attempts_mission_team_id", "mission_attempts", ["mission_team_id"])
    op.create_unique_constraint(
        "uq_mission_attempts_mission_team_no", "mission_attempts", ["mission_id", "mission_team_id", "attempt_no"],
    )
    op.create_check_constraint(
        "ck_mission_attempts_user_xor_team",
        "mission_attempts",
        "(user_id IS NOT NULL AND mission_team_id IS NULL) OR (user_id IS NULL AND mission_team_id IS NOT NULL)",
    )

    op.create_table(
        "mission_attempt_members",
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mission_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("attempt_id", "user_id", name="pk_mission_attempt_members"),
    )
    op.create_index("ix_mission_attempt_members_user_id", "mission_attempt_members", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_mission_attempt_members_user_id", table_name="mission_attempt_members")
    op.drop_table("mission_attempt_members")
    op.drop_constraint("ck_mission_attempts_user_xor_team", "mission_attempts", type_="check")
    op.drop_constraint("uq_mission_attempts_mission_team_no", "mission_attempts", type_="unique")
    op.drop_index("ix_mission_attempts_mission_team_id", table_name="mission_attempts")
    op.drop_column("mission_attempts", "mission_team_id")
