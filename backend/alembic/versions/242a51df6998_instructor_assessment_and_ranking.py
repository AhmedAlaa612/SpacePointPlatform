"""Instructor assessment and performance ranking domain (2026-09)

A per-opportunity, randomized scenario MCQ instructors complete when
applying for a role on the existing staffing marketplace
(`cohort_calls`/`cohort_call_id` — see `app/models/instructor_assessment/
__init__.py`), plus the post-program performance rating and the
configurable ranking-weight blend that build on top of it.

Additive only — every table here is new, and nothing in the existing
marketplace changes shape. A cohort with no `assessment_cohort_assignments`
row behaves exactly as it did before this migration.

Revision ID: 242a51df6998
Revises: 4230948f677b
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = '242a51df6998'
down_revision: Union[str, None] = '4230948f677b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assessment_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "assessment_questions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("config_id", UUID(as_uuid=True), sa.ForeignKey("assessment_configs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(128), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", JSONB(), nullable=False),
        sa.Column("critical", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_assessment_questions_config_id", "assessment_questions", ["config_id"])
    op.create_index("ix_assessment_questions_category", "assessment_questions", ["category"])

    op.create_table(
        "assessment_cohort_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cohort_id", UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("config_id", UUID(as_uuid=True), sa.ForeignKey("assessment_configs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assigned_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "assessment_attempts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("config_id", UUID(as_uuid=True), sa.ForeignKey("assessment_configs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("cohort_call_id", UUID(as_uuid=True), sa.ForeignKey("cohort_calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_order", JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="in_progress"),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("total", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("critical_correct", sa.Integer(), nullable=True),
        sa.Column("critical_total", sa.Integer(), nullable=True),
        sa.Column("category_breakdown", JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("cohort_call_id", "user_id", name="uq_assessment_attempt_call_user"),
    )
    op.create_index("ix_assessment_attempts_cohort_call_id", "assessment_attempts", ["cohort_call_id"])
    op.create_index("ix_assessment_attempts_user_id", "assessment_attempts", ["user_id"])

    op.create_table(
        "assessment_answers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("attempt_id", UUID(as_uuid=True), sa.ForeignKey("assessment_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", UUID(as_uuid=True), sa.ForeignKey("assessment_questions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("selected_option_index", sa.Integer(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("attempt_id", "question_id", name="uq_assessment_answer_attempt_question"),
    )
    op.create_index("ix_assessment_answers_attempt_id", "assessment_answers", ["attempt_id"])

    op.create_table(
        "instructor_program_ratings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cohort_id", UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instructor_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rater_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("dimension_scores", JSONB(), nullable=False),
        sa.Column("strengths", sa.Text(), nullable=True),
        sa.Column("areas_for_improvement", sa.Text(), nullable=True),
        sa.Column("recommended", sa.Boolean(), nullable=True),
        sa.Column("flag", sa.String(16), nullable=False, server_default="none"),
        sa.Column("submitted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "cohort_id", "instructor_user_id", "rater_user_id",
            name="uq_instructor_program_rating_cohort_instructor_rater",
        ),
    )
    op.create_index("ix_instructor_program_ratings_cohort_id", "instructor_program_ratings", ["cohort_id"])
    op.create_index("ix_instructor_program_ratings_instructor_user_id", "instructor_program_ratings", ["instructor_user_id"])

    op.create_table(
        "instructor_certification_tags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_instructor_certification_tags_user_id", "instructor_certification_tags", ["user_id"])

    op.create_table(
        "ranking_weight_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("factor_weights", JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Seed the default weighting the boss's brief gave as an example, active
    # from day one — Phase 3 ships with a real, adjustable blend rather than
    # an empty config table.
    op.execute(
        """
        INSERT INTO ranking_weight_profiles (id, name, factor_weights, is_active, created_at, updated_at)
        VALUES (
            gen_random_uuid(),
            'Default',
            '{"assessment_score": 30, "previous_rating": 25, "relevant_experience": 15,
              "sessions_hours": 10, "reliability": 10, "recent_performance": 10}',
            true, now(), now()
        )
        """
    )


def downgrade() -> None:
    op.drop_table("ranking_weight_profiles")
    op.drop_index("ix_instructor_certification_tags_user_id", table_name="instructor_certification_tags")
    op.drop_table("instructor_certification_tags")
    op.drop_index("ix_instructor_program_ratings_instructor_user_id", table_name="instructor_program_ratings")
    op.drop_index("ix_instructor_program_ratings_cohort_id", table_name="instructor_program_ratings")
    op.drop_table("instructor_program_ratings")
    op.drop_index("ix_assessment_answers_attempt_id", table_name="assessment_answers")
    op.drop_table("assessment_answers")
    op.drop_index("ix_assessment_attempts_user_id", table_name="assessment_attempts")
    op.drop_index("ix_assessment_attempts_cohort_call_id", table_name="assessment_attempts")
    op.drop_table("assessment_attempts")
    op.drop_table("assessment_cohort_assignments")
    op.drop_index("ix_assessment_questions_category", table_name="assessment_questions")
    op.drop_index("ix_assessment_questions_config_id", table_name="assessment_questions")
    op.drop_table("assessment_questions")
    op.drop_table("assessment_configs")
