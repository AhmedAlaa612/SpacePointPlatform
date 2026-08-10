"""mission core schema (P5-1, LMS Phase 2 Stage 5, 2026-08-11).

Four tables: missions (template) / mission_variants (difficulty) /
mission_prerequisites (DAG edge) / mission_attempts (one run, verifier-
graded). Solo only this stage — mission_attempts.user_id is nullable ahead
of Stage 6 (team attempts), but mission_teams doesn't exist yet so its FK
is not forward-referenced here.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "4011c4274501"
down_revision = "2be404a89eae"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "missions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("team_policy", sa.String(8), nullable=False, server_default="solo"),
        sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
        sa.Column("access_mode", sa.String(12), nullable=False, server_default="open"),
        sa.Column("authored_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("image_bucket", sa.String(64), nullable=True),
        sa.Column("image_path", sa.String(512), nullable=True),
        sa.Column("track", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("slug", name="uq_missions_slug"),
    )

    op.create_table(
        "mission_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("missions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(24), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("mission_id", "position", name="uq_mission_variants_mission_position"),
    )
    op.create_index("ix_mission_variants_mission_id", "mission_variants", ["mission_id"])

    op.create_table(
        "mission_prerequisites",
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("missions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requires_mission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("missions.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("mission_id", "requires_mission_id", name="pk_mission_prerequisites"),
        sa.CheckConstraint("mission_id != requires_mission_id", name="ck_mission_prereq_not_self"),
    )

    op.create_table(
        "mission_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("missions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mission_variants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="in_progress"),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("mission_id", "user_id", "attempt_no", name="uq_mission_attempts_mission_user_no"),
    )
    op.create_index("ix_mission_attempts_mission_id", "mission_attempts", ["mission_id"])
    op.create_index("ix_mission_attempts_user_id", "mission_attempts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_mission_attempts_user_id", table_name="mission_attempts")
    op.drop_index("ix_mission_attempts_mission_id", table_name="mission_attempts")
    op.drop_table("mission_attempts")
    op.drop_table("mission_prerequisites")
    op.drop_index("ix_mission_variants_mission_id", table_name="mission_variants")
    op.drop_table("mission_variants")
    op.drop_table("missions")
