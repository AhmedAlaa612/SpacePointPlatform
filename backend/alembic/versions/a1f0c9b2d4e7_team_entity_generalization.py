"""team entity generalization (2026-08-17)

Lifts `MissionTeam` into a top-level, domain-agnostic `Team` — the opening
move of the Competition domain per the August Build Brief (Competition
needs teams too; building its logic against a missions-only table would
mean redoing it later). Production has zero rows in `mission_teams` as of
this migration, confirmed live — this is a pure rename pass, no data-
preserving statements needed.

`mission_teams` -> `learner_teams` (not `teams` — `models/interns/team.py`
already owns that table name, a fully separate internship-program concept).
`mission_team_members` -> `learner_team_members`. `mission_attempts.
mission_team_id` -> `team_id`.

Column renames (`ALTER TABLE ... RENAME COLUMN`) automatically update every
dependent object's definition (CHECK constraint expressions, FK column
references) since Postgres tracks these by attnum internally, not by name
text — so the CHECK/FK constraints don't need to be dropped and recreated,
only renamed for cosmetic consistency with the new model code.

Every current name below was verified against the live dev DB
(`pg_constraint`/`pg_indexes`), not guessed from the model source.

Revision ID: a1f0c9b2d4e7
Revises: f4c8b1e6a923
"""

from alembic import op

revision = "a1f0c9b2d4e7"
down_revision = "f4c8b1e6a923"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # tables
    op.rename_table("mission_teams", "learner_teams")
    op.rename_table("mission_team_members", "learner_team_members")

    # columns (auto-propagates to dependent CHECK/FK definitions)
    op.alter_column("learner_team_members", "mission_team_id", new_column_name="team_id")
    op.alter_column("mission_attempts", "mission_team_id", new_column_name="team_id")

    # constraint renames, cosmetic (functionally already correct post-rename)
    op.execute("ALTER TABLE learner_teams RENAME CONSTRAINT mission_teams_pkey TO learner_teams_pkey")
    op.execute("ALTER TABLE learner_teams RENAME CONSTRAINT mission_teams_cohort_id_fkey TO learner_teams_cohort_id_fkey")
    op.execute("ALTER TABLE learner_teams RENAME CONSTRAINT mission_teams_created_by_fkey TO learner_teams_created_by_fkey")
    op.execute("ALTER TABLE learner_teams RENAME CONSTRAINT uq_mission_teams_cohort_name TO uq_learner_teams_cohort_name")

    op.execute("ALTER TABLE learner_team_members RENAME CONSTRAINT mission_team_members_mission_team_id_fkey TO learner_team_members_team_id_fkey")
    op.execute("ALTER TABLE learner_team_members RENAME CONSTRAINT mission_team_members_user_id_fkey TO learner_team_members_user_id_fkey")
    op.execute("ALTER TABLE learner_team_members RENAME CONSTRAINT pk_mission_team_members TO pk_learner_team_members")

    op.execute("ALTER TABLE mission_attempts RENAME CONSTRAINT mission_attempts_mission_team_id_fkey TO mission_attempts_team_id_fkey")

    # index renames
    op.execute("ALTER INDEX ix_mission_teams_cohort_id RENAME TO ix_learner_teams_cohort_id")
    op.execute("ALTER INDEX ix_mission_team_members_user_id RENAME TO ix_learner_team_members_user_id")
    op.execute("ALTER INDEX ix_mission_attempts_mission_team_id RENAME TO ix_mission_attempts_team_id")


def downgrade() -> None:
    op.execute("ALTER INDEX ix_mission_attempts_team_id RENAME TO ix_mission_attempts_mission_team_id")
    op.execute("ALTER INDEX ix_learner_team_members_user_id RENAME TO ix_mission_team_members_user_id")
    op.execute("ALTER INDEX ix_learner_teams_cohort_id RENAME TO ix_mission_teams_cohort_id")

    op.execute("ALTER TABLE mission_attempts RENAME CONSTRAINT mission_attempts_team_id_fkey TO mission_attempts_mission_team_id_fkey")

    op.execute("ALTER TABLE learner_team_members RENAME CONSTRAINT pk_learner_team_members TO pk_mission_team_members")
    op.execute("ALTER TABLE learner_team_members RENAME CONSTRAINT learner_team_members_user_id_fkey TO mission_team_members_user_id_fkey")
    op.execute("ALTER TABLE learner_team_members RENAME CONSTRAINT learner_team_members_team_id_fkey TO mission_team_members_mission_team_id_fkey")

    op.execute("ALTER TABLE learner_teams RENAME CONSTRAINT uq_learner_teams_cohort_name TO uq_mission_teams_cohort_name")
    op.execute("ALTER TABLE learner_teams RENAME CONSTRAINT learner_teams_created_by_fkey TO mission_teams_created_by_fkey")
    op.execute("ALTER TABLE learner_teams RENAME CONSTRAINT learner_teams_cohort_id_fkey TO mission_teams_cohort_id_fkey")
    op.execute("ALTER TABLE learner_teams RENAME CONSTRAINT learner_teams_pkey TO mission_teams_pkey")

    op.alter_column("mission_attempts", "team_id", new_column_name="mission_team_id")
    op.alter_column("learner_team_members", "team_id", new_column_name="mission_team_id")

    op.rename_table("learner_team_members", "mission_team_members")
    op.rename_table("learner_teams", "mission_teams")
