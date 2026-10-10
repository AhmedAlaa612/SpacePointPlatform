"""website programs

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-10-09

Step 2 — Core Programs & AED Pricing Management: creates the
`website_programs` table and seeds the four flagship programs when empty.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = 'd2e3f4a5b6c7'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'website_programs',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('slug', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=128), nullable=False),
        sa.Column('tagline', sa.String(length=255), nullable=True),
        sa.Column('category', sa.String(length=64), nullable=False, server_default='Aerospace Engineering'),
        sa.Column('level', sa.String(length=64), nullable=False, server_default='Intermediate'),
        sa.Column('duration', sa.String(length=64), nullable=False, server_default='4 Weeks'),
        sa.Column('price_aed', sa.Integer(), nullable=False),
        sa.Column('compare_at_price_aed', sa.Integer(), nullable=True),
        sa.Column('badge_text', sa.String(length=64), nullable=True),
        sa.Column('features_list', JSONB(), nullable=False, server_default='[]'),
        sa.Column('syllabus_url', sa.String(length=512), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_published', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )
    op.create_index('ix_website_programs_slug', 'website_programs', ['slug'], unique=True)

    conn = op.get_bind()
    conn.execute(sa.text(
        """
        INSERT INTO website_programs
            (id, slug, title, tagline, category, level, duration,
             price_aed, badge_text, features_list, display_order, is_published)
        SELECT * FROM (VALUES
            (
                '00000000-0000-4000-8000-000000000001'::uuid, 'quick-flight', 'Quick Flight',
                'Ignite Curiosity. Spark Future Innovators.', 'Space Education', 'First-time exposure', '2-3 Hours',
                500, 'so valuble',
                '["Give students their first real exposure to space technology", "Transform theory into action with a hands-on CubeSat build experience", "Designed to inspire interest in STEM in just a few hours", "Perfect introduction for schools looking to engage students in a memorable way"]'::jsonb,
                1, true
            ),
            (
                '00000000-0000-4000-8000-000000000002'::uuid, 'shallow-flight', 'Shallow Flight',
                'Turn Curiosity Into Real Skills', 'Space Education', 'Skill-building', '6-10 Hours',
                2500, '2000 - 3000 AED',
                '["Move beyond basics into real satellite subsystems and engineering concepts", "Students don’t just learn — they build, connect, and test", "Combines mechanical, electrical, and software learning in one experience", "Ideal for schools aiming to develop practical STEM capabilities"]'::jsonb,
                2, true
            ),
            (
                '00000000-0000-4000-8000-000000000003'::uuid, 'the-mission', 'The Mission',
                'From Classroom to Space Mission', 'Space Education', 'Advanced programs', '18-24 Hours',
                7500, '~7500 AED',
                '["A complete end-to-end satellite development experience", "Students go through the same journey as real space engineers", "Includes building, integration, testing, and mission simulation", "Covers launch concepts, environmental challenges, and operations", "Creates high-impact learning outcomes schools can proudly showcase"]'::jsonb,
                3, true
            ),
            (
                '00000000-0000-4000-8000-000000000004'::uuid, 'the-journey', 'The Journey',
                'Train Educators. Build Space Programs. Inspire Generations.', 'Space Education', 'Institutions', '6+ Months',
                1000, '1,000 AED / Participant',
                '["A 6-month guided program led by your institution’s instructors.", "SpacePoint trains educators and provides monthly expert follow-up.", "Includes a structured learning path and a dedicated satellite development lab.", "Designed for long-term skill development and sustainable STEM impact."]'::jsonb,
                4, true
            )
        ) AS seed(id, slug, title, tagline, category, level, duration,
                  price_aed, badge_text, features_list, display_order, is_published)
        WHERE NOT EXISTS (SELECT 1 FROM website_programs)
        """
    ))


def downgrade() -> None:
    op.drop_index('ix_website_programs_slug', table_name='website_programs')
    op.drop_table('website_programs')
