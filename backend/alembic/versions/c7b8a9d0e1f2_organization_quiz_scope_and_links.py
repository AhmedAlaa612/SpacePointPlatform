"""organization quiz scope and links

Revision ID: c7b8a9d0e1f2
Revises: 9a8b7c6d5e4f
Create Date: 2026-10-26 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c7b8a9d0e1f2'
down_revision = '9a8b7c6d5e4f'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Organizations quiz scope and allowed template IDs
    op.add_column('organizations', sa.Column('quiz_scope', sa.String(length=32), nullable=False, server_default=sa.text("'own'")))
    op.add_column('organizations', sa.Column('allowed_quiz_template_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))

    # 2. Cohort Quiz questions & templates organization links
    op.add_column('cohort_quiz_questions', sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_cohort_quiz_questions_organization_id', 'cohort_quiz_questions', ['organization_id'])

    op.add_column('cohort_quiz_templates', sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_cohort_quiz_templates_organization_id', 'cohort_quiz_templates', ['organization_id'])

    # 3. Set organizations is_approved server default to false
    op.alter_column('organizations', 'is_approved', server_default=sa.text('false'))


def downgrade():
    op.alter_column('organizations', 'is_approved', server_default=sa.text('true'))
    op.drop_index('ix_cohort_quiz_templates_organization_id', table_name='cohort_quiz_templates')
    op.drop_column('cohort_quiz_templates', 'organization_id')
    op.drop_index('ix_cohort_quiz_questions_organization_id', table_name='cohort_quiz_questions')
    op.drop_column('cohort_quiz_questions', 'organization_id')
    op.drop_column('organizations', 'allowed_quiz_template_ids')
    op.drop_column('organizations', 'quiz_scope')
