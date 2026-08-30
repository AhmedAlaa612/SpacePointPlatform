"""Competition domain, judging: rubrics, scores, publish gate, judge role (2026-08-24)

Second stage of the boss-approved plan. Four new tables plus one enum value,
nothing existing changes shape:

- `competition_rubrics` / `competition_rubric_criteria` — a competition's
  scoring rubric, program-scoped (Ru'ya's is the PDF's 8 criteria + a bonus,
  105 pts total; authored by ops, not hardcoded).
- `competition_scores` — one row per (rubric, team, judge, cohort) — a judge
  revises their own row freely via upsert until publish; unique on all four
  so a judge can score the same team again in a later stage (Finalists) as a
  genuinely separate row.
- `competition_result_publications` — the blind-until-published gate. Row
  exists for a cohort = published; delete to unpublish. No judge, including
  the one who scored, sees another judge's numbers before this exists —
  enforced in services/competitions/judging.py, not by this table alone.
- `judge` — new `user_role` enum value. `ALTER TYPE ... ADD VALUE` outside a
  transaction block, same pattern as b2d8a91c0002/c4f9b25e0015/c7e2b41a0039.
- `competition_judges` — a judge's cohort assignment, exact shape of
  `session_instructors` (one row per cohort a judge can see; a Qualifier
  judge has no row for Finalists and vice versa).

Revision ID: c0ecdcecc91c
Revises: 18143df669a7
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c0ecdcecc91c"
down_revision = "18143df669a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "competition_rubrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_competition_rubrics_program_id", "competition_rubrics", ["program_id"])

    op.create_table(
        "competition_rubric_criteria",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rubric_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("competition_rubrics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("max_points", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("rubric_id", "key", name="uq_competition_rubric_criteria_rubric_key"),
    )
    op.create_index("ix_competition_rubric_criteria_rubric_id", "competition_rubric_criteria", ["rubric_id"])

    op.create_table(
        "competition_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rubric_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("competition_rubrics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learner_teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("judge_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("criterion_scores", postgresql.JSONB(), nullable=False),
        sa.Column("bonus_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_points", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "rubric_id", "team_id", "judge_user_id", "cohort_id",
            name="uq_competition_scores_rubric_team_judge_cohort",
        ),
    )
    op.create_index("ix_competition_scores_team_id", "competition_scores", ["team_id"])
    op.create_index("ix_competition_scores_cohort_id", "competition_scores", ["cohort_id"])

    op.create_table(
        "competition_result_publications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("published_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block. Same
    # pattern as b2d8a91c0002 ('operations'), c4f9b25e0015 ('coo'/
    # 'storekeeper'), c7e2b41a0039 ('student').
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'judge'")

    op.create_table(
        "competition_judges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("cohort_id", "user_id", name="uq_competition_judges_cohort_user"),
    )
    op.create_index("ix_competition_judges_cohort_id", "competition_judges", ["cohort_id"])
    op.create_index("ix_competition_judges_user_id", "competition_judges", ["user_id"])


def downgrade() -> None:
    op.drop_table("competition_judges")
    # Postgres cannot drop a value from an enum type — no-op by design,
    # same as c7e2b41a0039.
    op.drop_table("competition_result_publications")
    op.drop_index("ix_competition_scores_cohort_id", table_name="competition_scores")
    op.drop_index("ix_competition_scores_team_id", table_name="competition_scores")
    op.drop_table("competition_scores")
    op.drop_index("ix_competition_rubric_criteria_rubric_id", table_name="competition_rubric_criteria")
    op.drop_table("competition_rubric_criteria")
    op.drop_index("ix_competition_rubrics_program_id", table_name="competition_rubrics")
    op.drop_table("competition_rubrics")
