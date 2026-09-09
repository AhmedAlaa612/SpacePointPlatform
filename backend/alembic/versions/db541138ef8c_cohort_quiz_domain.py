"""Cohort knowledge-quiz domain (2026-09) — the per-cohort timed diagnostic
quiz: a facilitator-authored question bank, fixed templates assembled from
it, and student attempts/answers. See `app/models/lms/cohort_quiz.py` for
the full domain writeup and why this is a separate table set from the
unrelated in-course module quiz and the instructor-assessment domain.

Revision ID: db541138ef8c
Revises: 8b3d0f61a2c7
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'db541138ef8c'
down_revision: Union[str, None] = '8b3d0f61a2c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cohort_quiz_questions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('topic', sa.String(length=128), nullable=False),
        sa.Column('subtopic', sa.String(length=128), nullable=True),
        sa.Column('difficulty', sa.String(length=16), nullable=False),
        sa.Column('time_limit_seconds', sa.Integer(), nullable=False),
        sa.Column('bloom_level', sa.String(length=32), nullable=True),
        sa.Column('question_type', sa.String(length=32), nullable=True),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('options', postgresql.JSONB(), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('source_url', sa.String(length=512), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_cohort_quiz_questions_topic', 'cohort_quiz_questions', ['topic'])

    op.create_table(
        'cohort_quiz_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'cohort_quiz_template_questions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'template_id', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('cohort_quiz_templates.id', ondelete='CASCADE'), nullable=False,
        ),
        sa.Column(
            'question_id', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('cohort_quiz_questions.id', ondelete='SET NULL'), nullable=True,
        ),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.UniqueConstraint('template_id', 'position', name='uq_cohort_quiz_template_question_position'),
    )
    op.create_index(
        'ix_cohort_quiz_template_questions_template_id', 'cohort_quiz_template_questions', ['template_id'],
    )

    op.create_table(
        'cohort_quiz_attempts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'program_item_id', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('lms_program_items.id', ondelete='CASCADE'), nullable=False,
        ),
        sa.Column(
            'cohort_quiz_template_id', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('cohort_quiz_templates.id', ondelete='RESTRICT'), nullable=False,
        ),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('cohort_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cohorts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('question_order', postgresql.JSONB(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='in_progress'),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('topic_breakdown', postgresql.JSONB(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('program_item_id', 'user_id', name='uq_cohort_quiz_attempt_item_user'),
    )
    op.create_index('ix_cohort_quiz_attempts_program_item_id', 'cohort_quiz_attempts', ['program_item_id'])
    op.create_index('ix_cohort_quiz_attempts_user_id', 'cohort_quiz_attempts', ['user_id'])

    op.create_table(
        'cohort_quiz_answers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'attempt_id', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('cohort_quiz_attempts.id', ondelete='CASCADE'), nullable=False,
        ),
        sa.Column(
            'question_id', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('cohort_quiz_questions.id', ondelete='SET NULL'), nullable=True,
        ),
        sa.Column('topic', sa.String(length=128), nullable=False),
        sa.Column('selected_option_index', sa.Integer(), nullable=True),
        sa.Column('is_correct', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('timed_out', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('time_taken_seconds', sa.Integer(), nullable=True),
        sa.Column('answered_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('attempt_id', 'question_id', name='uq_cohort_quiz_answer_attempt_question'),
    )
    op.create_index('ix_cohort_quiz_answers_attempt_id', 'cohort_quiz_answers', ['attempt_id'])


def downgrade() -> None:
    op.drop_table('cohort_quiz_answers')
    op.drop_table('cohort_quiz_attempts')
    op.drop_table('cohort_quiz_template_questions')
    op.drop_table('cohort_quiz_templates')
    op.drop_table('cohort_quiz_questions')
