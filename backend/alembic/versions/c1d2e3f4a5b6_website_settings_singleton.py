"""website settings singleton

Revision ID: c1d2e3f4a5b6
Revises: f5a6b7c8d9e0
Create Date: 2026-10-09

Step 1 — SpacePoint Website Global Config & Live Counters: creates the
`website_settings` singleton table (single row id=1) and seeds it with
the agreed defaults when empty.
"""

from alembic import op
import sqlalchemy as sa


revision = 'c1d2e3f4a5b6'
down_revision = 'f5a6b7c8d9e0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'website_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('students_count', sa.String(length=64), nullable=False, server_default='2,700+'),
        sa.Column('workshops_count', sa.String(length=64), nullable=False, server_default='40+'),
        sa.Column('partners_count', sa.String(length=64), nullable=False, server_default='25'),
        sa.Column('satellites_flown_count', sa.String(length=64), nullable=False, server_default='50+'),
        sa.Column('instructor_invite_code', sa.String(length=64), nullable=True, server_default='UOWD26'),
        sa.Column('intern_invite_code', sa.String(length=64), nullable=True, server_default='UOWD26'),
        sa.Column('contact_email', sa.String(length=255), nullable=False, server_default='info@spacepoint.ae'),
        sa.Column('contact_phone', sa.String(length=64), nullable=False, server_default='+971 56 298 7005'),
        sa.Column('contact_whatsapp', sa.String(length=64), nullable=True, server_default='+971 56 298 7005'),
        sa.Column('office_address', sa.String(length=255), nullable=False, server_default='Sharjah Research, Technology and Innovation Park (SRTIP), Block B – Office B22-120, Sharjah, United Arab Emirates'),
        sa.Column('social_linkedin', sa.String(length=255), nullable=True, server_default='https://www.linkedin.com/company/spacepointae/posts/?feedView=all'),
        sa.Column('social_x', sa.String(length=255), nullable=True, server_default='https://www.tiktok.com/@spacepoint.ae'),
        sa.Column('social_instagram', sa.String(length=255), nullable=True, server_default='https://www.instagram.com/spacepoint.ae'),
        sa.Column('social_youtube', sa.String(length=255), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    conn = op.get_bind()
    conn.execute(sa.text(
        """
        INSERT INTO website_settings (
            id, students_count, workshops_count, partners_count,
            satellites_flown_count, instructor_invite_code, intern_invite_code,
            contact_email, contact_phone, contact_whatsapp, office_address,
            social_linkedin, social_x, social_instagram, social_youtube
        )
        SELECT 1, '2,700+', '40+', '25', '50+', 'UOWD26', 'UOWD26',
               'info@spacepoint.ae', '+971 56 298 7005', '+971 56 298 7005',
               'Sharjah Research, Technology and Innovation Park (SRTIP), Block B – Office B22-120, Sharjah, United Arab Emirates',
               'https://www.linkedin.com/company/spacepointae/posts/?feedView=all',
               'https://www.tiktok.com/@spacepoint.ae',
               'https://www.instagram.com/spacepoint.ae',
               ''
        WHERE NOT EXISTS (SELECT 1 FROM website_settings WHERE id = 1)
        """
    ))


def downgrade() -> None:
    op.drop_table('website_settings')
