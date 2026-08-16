"""mission_attempts.cohort_id + mission_step_gates (2026-08-17)

Reverses the Design v2 D1 call ("instructors stay out of the mission
entirely") on the operator's explicit instruction — the boss's own request,
delivered 2026-08-16, is cohort-scoped instructor progress/gating/review
for the Design mission. `mission_step_gates` revives the shape of the
dropped `design_step_gates` (94eaeb5ddbde -> d4a1c07e5b32), with `mission_id`
added to the key since a cohort can run more than one gated mission, and an
`updated_by` audit column since a non-staff role can now flip these.

`mission_attempts.cohort_id` is new — before this, cohort attribution only
existed transitively via `designs.cohort_id` (solo, and only for the design
mission) or `mission_teams.cohort_id` (team). Every attempt now carries its
own, resolved eagerly at `start_attempt()` time, for every mission kind.

Backfill is exact for the two existing attribution sources (designs, mission
teams) and best-effort for anything else (a solo attempt on a non-design
mission, which never had a cohort_id anywhere before this) — approximated
from the student's most recent active registration today, which is not
necessarily what cohort they were actually in when that old attempt
started. Affects historical rows only; every new attempt is exact going
forward.

Revision ID: d92f7a5c1e34
Revises: c7a2e5f1d093
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d92f7a5c1e34"
down_revision = "c7a2e5f1d093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mission_attempts", sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_mission_attempts_cohort_id", "mission_attempts", "cohorts",
        ["cohort_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_mission_attempts_cohort_id", "mission_attempts", ["cohort_id"])

    # 1. Solo attempts with a Design row — exact, already resolved once.
    op.execute("""
        UPDATE mission_attempts ma SET cohort_id = d.cohort_id
        FROM designs d WHERE d.attempt_id = ma.id AND d.cohort_id IS NOT NULL
    """)
    # 2. Team attempts — exact, from the team's own cohort attribution.
    op.execute("""
        UPDATE mission_attempts ma SET cohort_id = mt.cohort_id
        FROM mission_teams mt WHERE mt.id = ma.mission_team_id AND mt.cohort_id IS NOT NULL
    """)
    # 3. Remaining solo attempts (non-design mission kinds never had a
    #    cohort_id anywhere before this) — best-effort, via the same "most
    #    recent active registration" rule resolve_student_cohort() uses.
    op.execute("""
        UPDATE mission_attempts ma SET cohort_id = latest_reg.cohort_id
        FROM (
            SELECT DISTINCT ON (u.id) u.id AS user_id, r.cohort_id
            FROM users u
            JOIN registrations r ON r.contact_id = u.contact_id
            WHERE r.status IN ('registered', 'attended')
            ORDER BY u.id, r.created_at DESC
        ) latest_reg
        WHERE ma.user_id = latest_reg.user_id AND ma.cohort_id IS NULL
    """)

    op.create_table(
        "mission_step_gates",
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("missions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_key", sa.String(20), nullable=False),
        sa.Column("is_unlocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.PrimaryKeyConstraint("cohort_id", "mission_id", "step_key", name="pk_mission_step_gates"),
    )


def downgrade() -> None:
    op.drop_table("mission_step_gates")
    op.drop_index("ix_mission_attempts_cohort_id", table_name="mission_attempts")
    op.drop_constraint("fk_mission_attempts_cohort_id", "mission_attempts", type_="foreignkey")
    op.drop_column("mission_attempts", "cohort_id")
