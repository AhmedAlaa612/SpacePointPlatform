"""organization hosting grants and quotas

Revision ID: f5e6d7c8b9a0
Revises: e4d5c6b7a8f9
Create Date: 2026-10-25 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f5e6d7c8b9a0'
down_revision = 'e4d5c6b7a8f9'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Organizations grants and quotas
    op.add_column('organizations', sa.Column('is_approved', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('organizations', sa.Column('can_publish_events', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('organizations', sa.Column('can_author_courses', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('organizations', sa.Column('can_publish_courses', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('organizations', sa.Column('course_scope_all', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('organizations', sa.Column('allowed_course_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column('organizations', sa.Column('max_events', sa.Integer(), nullable=True))
    op.add_column('organizations', sa.Column('max_programs', sa.Integer(), nullable=True))
    op.add_column('organizations', sa.Column('max_cohorts', sa.Integer(), nullable=True))
    op.add_column('organizations', sa.Column('max_students_per_cohort', sa.Integer(), nullable=True))
    op.add_column('organizations', sa.Column('max_observers_per_cohort', sa.Integer(), nullable=True))

    # 2. Multi-member user link to organization
    op.add_column('users', sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_users_organization_id', 'users', ['organization_id'])

    # Backfill users.organization_id from organizations.owner_user_id
    op.execute("""
        UPDATE users u
        SET organization_id = o.id
        FROM organizations o
        WHERE o.owner_user_id = u.id AND u.organization_id IS NULL
    """)

    # 3. Programs organization link
    op.add_column('programs', sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_programs_organization_id', 'programs', ['organization_id'])

    # 4. Courses organization link and review timestamp
    op.add_column('courses', sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_courses_organization_id', 'courses', ['organization_id'])
    op.add_column('courses', sa.Column('submitted_for_review_at', sa.DateTime(timezone=True), nullable=True))

    # 5. WebsiteEvent cohort link
    op.add_column('website_events', sa.Column('cohort_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cohorts.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_website_events_cohort_id', 'website_events', ['cohort_id'])


def downgrade():
    op.drop_index('ix_website_events_cohort_id', table_name='website_events')
    op.drop_column('website_events', 'cohort_id')

    op.drop_column('courses', 'submitted_for_review_at')
    op.drop_index('ix_courses_organization_id', table_name='courses')
    op.drop_column('courses', 'organization_id')

    op.drop_index('ix_programs_organization_id', table_name='programs')
    op.drop_column('programs', 'organization_id')

    op.drop_index('ix_users_organization_id', table_name='users')
    op.drop_column('users', 'organization_id')

    op.drop_column('organizations', 'max_observers_per_cohort')
    op.drop_column('organizations', 'max_students_per_cohort')
    op.drop_column('organizations', 'max_cohorts')
    op.drop_column('organizations', 'max_programs')
    op.drop_column('organizations', 'max_events')
    op.drop_column('organizations', 'allowed_course_ids')
    op.drop_column('organizations', 'course_scope_all')
    op.drop_column('organizations', 'can_publish_courses')
    op.drop_column('organizations', 'can_author_courses')
    op.drop_column('organizations', 'can_publish_events')
    op.drop_column('organizations', 'is_approved')
