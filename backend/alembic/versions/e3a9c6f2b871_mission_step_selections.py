"""mission_step_selections (2026-08-17)

Compositional per-cohort Design step scoping — which of the 9 build steps
even apply to a cohort's run, distinct from `mission_step_gates`' temporal
lock/unlock (both tables can have rows for the same cohort/mission at once).
Real-world driver: the TDRA Summer Camp case, where a cohort only needs
Components/Power/Mass, skipping Data Budget and Communication entirely.

Green-field table, no drop/revive history to preserve like
`design_step_gates` had. Deliberately does NOT mirror `mission_step_gates`'
boolean `is_unlocked` flag — a step is included purely by its row existing,
since writes always replace the whole selected set at once rather than
toggling one key. Absence of any row for a `(cohort_id, mission_id)` pair
means "no selection configured, all steps included" — the opposite default
polarity from gates ("absence means locked").

Revision ID: e3a9c6f2b871
Revises: d92f7a5c1e34
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e3a9c6f2b871"
down_revision = "d92f7a5c1e34"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mission_step_selections",
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("missions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_key", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.PrimaryKeyConstraint("cohort_id", "mission_id", "step_key", name="pk_mission_step_selections"),
    )


def downgrade() -> None:
    op.drop_table("mission_step_selections")
