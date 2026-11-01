"""Unified question bank and presets (readiness pipeline + pre-assessment)

Revision ID: de56bc78fa02
Revises: cd45ab67ef01
Create Date: 2026-11-01 23:25:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "de56bc78fa02"
down_revision = "cd45ab67ef01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add columns to pre_session_quiz_questions
    op.add_column("pre_session_quiz_questions", sa.Column("code", sa.String(length=64), nullable=True))
    op.add_column("pre_session_quiz_questions", sa.Column("critical", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("pre_session_quiz_questions", sa.Column("points", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.create_index(op.f("ix_pre_session_quiz_questions_code"), "pre_session_quiz_questions", ["code"], unique=False)
    op.create_index(op.f("ix_pre_session_quiz_questions_critical"), "pre_session_quiz_questions", ["critical"], unique=False)

    # 2. Add columns to pre_session_quiz_presets
    op.add_column("pre_session_quiz_presets", sa.Column("preset_type", sa.String(length=32), nullable=False, server_default=sa.text("'readiness_pipeline'")))
    op.add_column("pre_session_quiz_presets", sa.Column("draw_size", sa.Integer(), nullable=True, server_default=sa.text("15")))
    op.add_column("pre_session_quiz_presets", sa.Column("critical_floor", sa.Integer(), nullable=True, server_default=sa.text("3")))
    op.add_column("pre_session_quiz_presets", sa.Column("passing_score_percent", sa.Integer(), nullable=True, server_default=sa.text("80")))
    op.create_index(op.f("ix_pre_session_quiz_presets_preset_type"), "pre_session_quiz_presets", ["preset_type"], unique=False)

    # 3. Data migration: populate unified questions and presets from existing assessment_questions/configs
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if "assessment_questions" in table_names:
        op.execute("""
            INSERT INTO pre_session_quiz_questions (
                id, topic, question_type, title, prompt, options, critical, points, explanation, is_active, created_at
            )
            SELECT 
                aq.id, 
                aq.category, 
                'mcq', 
                SUBSTRING(aq.prompt FROM 1 FOR 60), 
                aq.prompt, 
                aq.options, 
                aq.critical, 
                1, 
                aq.rationale, 
                aq.is_active, 
                aq.created_at
            FROM assessment_questions aq
            WHERE NOT EXISTS (
                SELECT 1 FROM pre_session_quiz_questions psq WHERE psq.id = aq.id
            )
        """)

    if "assessment_configs" in table_names:
        op.execute("""
            INSERT INTO pre_session_quiz_presets (
                id, name, description, preset_type, draw_size, critical_floor, passing_score_percent, is_active, created_at
            )
            SELECT 
                ac.id, 
                ac.name, 
                ac.description, 
                'pre_assessment', 
                ac.draw_size, 
                ac.critical_floor, 
                80, 
                ac.is_active, 
                ac.created_at
            FROM assessment_configs ac
            WHERE NOT EXISTS (
                SELECT 1 FROM pre_session_quiz_presets psp WHERE psp.id = ac.id
            )
        """)


def downgrade() -> None:
    op.drop_index(op.f("ix_pre_session_quiz_presets_preset_type"), table_name="pre_session_quiz_presets")
    op.drop_column("pre_session_quiz_presets", "passing_score_percent")
    op.drop_column("pre_session_quiz_presets", "critical_floor")
    op.drop_column("pre_session_quiz_presets", "draw_size")
    op.drop_column("pre_session_quiz_presets", "preset_type")

    op.drop_index(op.f("ix_pre_session_quiz_questions_critical"), table_name="pre_session_quiz_questions")
    op.drop_index(op.f("ix_pre_session_quiz_questions_code"), table_name="pre_session_quiz_questions")
    op.drop_column("pre_session_quiz_questions", "points")
    op.drop_column("pre_session_quiz_questions", "critical")
    op.drop_column("pre_session_quiz_questions", "code")
