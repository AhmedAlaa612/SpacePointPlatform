"""add_cms_and_website_leads_tables

Revision ID: 2a26344b41c6
Revises: f8a1c2d3e4b5
Create Date: 2026-09-26 16:51:47.988360

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2a26344b41c6'
down_revision: Union[str, None] = 'f8a1c2d3e4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Media Clippings
    op.create_table(
        'media_clippings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('publisher_name', sa.String(length=255), nullable=False),
        sa.Column('article_title', sa.String(length=512), nullable=False),
        sa.Column('article_url', sa.String(length=1024), nullable=False),
        sa.Column('published_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('logo_url', sa.String(length=512), nullable=True),
        sa.Column('is_arabic', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('snippet', sa.Text(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # 2. Sponsors
    op.create_table(
        'sponsors',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('logo_url', sa.String(length=512), nullable=False),
        sa.Column('website_url', sa.String(length=512), nullable=True),
        sa.Column('tier', sa.String(length=64), nullable=False, server_default='partner'),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sponsors_tier'), 'sponsors', ['tier'], unique=False)

    # 3. Student Missions
    op.create_table(
        'student_missions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('student_name', sa.String(length=255), nullable=False),
        sa.Column('project_title', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=128), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('docx_url', sa.String(length=512), nullable=True),
        sa.Column('photo_url', sa.String(length=512), nullable=True),
        sa.Column('metrics_json', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # 4. Website Leads
    op.create_table(
        'website_leads',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('lead_type', sa.String(length=64), nullable=False),
        sa.Column('contact_name', sa.String(length=255), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=64), nullable=True),
        sa.Column('organization_name', sa.String(length=255), nullable=True),
        sa.Column('program_interest', sa.String(length=255), nullable=True),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='new'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_website_leads_email'), 'website_leads', ['email'], unique=False)
    op.create_index(op.f('ix_website_leads_lead_type'), 'website_leads', ['lead_type'], unique=False)
    op.create_index(op.f('ix_website_leads_status'), 'website_leads', ['status'], unique=False)

    # 5. Articles
    op.create_table(
        'articles',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('slug', sa.String(length=160), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('content_markdown', sa.Text(), nullable=False),
        sa.Column('content_html', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=False, server_default='TECHNOLOGY'),
        sa.Column('author_id', sa.UUID(), nullable=True),
        sa.Column('author_display_name', sa.String(length=128), nullable=False),
        sa.Column('author_role', sa.String(length=128), nullable=True),
        sa.Column('author_initials', sa.String(length=8), nullable=True),
        sa.Column('cover_image_url', sa.String(length=512), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='draft'),
        sa.Column('reviewer_feedback', sa.Text(), nullable=True),
        sa.Column('reviewed_by_id', sa.UUID(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('featured_order', sa.Integer(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_articles_author_id'), 'articles', ['author_id'], unique=False)
    op.create_index(op.f('ix_articles_category'), 'articles', ['category'], unique=False)
    op.create_index(op.f('ix_articles_slug'), 'articles', ['slug'], unique=True)
    op.create_index(op.f('ix_articles_status'), 'articles', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_articles_status'), table_name='articles')
    op.drop_index(op.f('ix_articles_slug'), table_name='articles')
    op.drop_index(op.f('ix_articles_category'), table_name='articles')
    op.drop_index(op.f('ix_articles_author_id'), table_name='articles')
    op.drop_table('articles')

    op.drop_index(op.f('ix_website_leads_status'), table_name='website_leads')
    op.drop_index(op.f('ix_website_leads_lead_type'), table_name='website_leads')
    op.drop_index(op.f('ix_website_leads_email'), table_name='website_leads')
    op.drop_table('website_leads')

    op.drop_table('student_missions')

    op.drop_index(op.f('ix_sponsors_tier'), table_name='sponsors')
    op.drop_table('sponsors')

    op.drop_table('media_clippings')
