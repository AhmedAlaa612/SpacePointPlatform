"""website sponsors

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-10-09

Step 3 — Partners, Clients & Industry Leaders Showcase: creates the
`sponsors` table and seeds the six key partners/clients when empty.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'sponsors',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('logo_url', sa.String(length=512), nullable=False),
        sa.Column('website_url', sa.String(length=512), nullable=True),
        sa.Column('tier', sa.String(length=32), nullable=False, server_default='partner'),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )

    conn = op.get_bind()
    conn.execute(sa.text(
        """
        INSERT INTO sponsors
            (id, name, logo_url, website_url, tier, display_order, is_active)
        SELECT * FROM (VALUES
            ('10000000-0000-4000-8000-000000000001'::uuid, 'AGF', '/assets/img/Case studies/Logos/AGF white.png', NULL, 'client', 1, true),
            ('10000000-0000-4000-8000-000000000002'::uuid, 'Edge', '/assets/img/clients/Edge.png', NULL, 'client', 2, true),
            ('10000000-0000-4000-8000-000000000003'::uuid, 'Etlaq', '/assets/img/clients/Etlaq.png', NULL, 'client', 3, true),
            ('10000000-0000-4000-8000-000000000004'::uuid, 'Fada', '/assets/img/clients/Fada.png', NULL, 'client', 4, true),
            ('10000000-0000-4000-8000-000000000005'::uuid, 'Gems', '/assets/img/clients/Gems.png', NULL, 'client', 5, true),
            ('10000000-0000-4000-8000-000000000006'::uuid, 'HCT', '/assets/img/Case studies/Logos/HCT white.png', NULL, 'client', 6, true),
            ('10000000-0000-4000-8000-000000000007'::uuid, 'KU', '/assets/img/clients/KU.png', NULL, 'client', 7, true),
            ('10000000-0000-4000-8000-000000000008'::uuid, 'Kaust', '/assets/img/clients/Kaust.png', NULL, 'client', 8, true),
            ('10000000-0000-4000-8000-000000000009'::uuid, 'MBZUAI', '/assets/img/clients/MBZUAI.png', NULL, 'client', 9, true),
            ('10000000-0000-4000-8000-000000000010'::uuid, 'MUD', '/assets/img/clients/MUD.png', NULL, 'client', 10, true),
            ('10000000-0000-4000-8000-000000000011'::uuid, 'Museum of the Future', '/assets/img/clients/Museum of the future.png', NULL, 'client', 11, true),
            ('10000000-0000-4000-8000-000000000012'::uuid, 'Nasa Dubai', '/assets/img/clients/Nasa Dubai.png', NULL, 'client', 12, true),
            ('10000000-0000-4000-8000-000000000013'::uuid, 'UAESA', '/assets/img/Case studies/Logos/UAE Space Agency white.png', NULL, 'client', 13, true),
            ('10000000-0000-4000-8000-000000000014'::uuid, 'UAEU', '/assets/img/clients/UAEU.png', NULL, 'client', 14, true),
            ('10000000-0000-4000-8000-000000000015'::uuid, 'Maker Fair', '/assets/img/clients/maker fair.png', NULL, 'client', 15, true),
            ('10000000-0000-4000-8000-000000000016'::uuid, 'Space42', '/assets/img/clients/space42.png', NULL, 'client', 16, true),
            ('10000000-0000-4000-8000-000000000017'::uuid, 'ART', '/assets/img/partners/ART.png', NULL, 'partner', 17, true),
            ('10000000-0000-4000-8000-000000000018'::uuid, 'Aeroo', '/assets/img/partners/Aeroo.png', NULL, 'partner', 18, true),
            ('10000000-0000-4000-8000-000000000019'::uuid, 'AirQ', '/assets/img/partners/AirQ.png', NULL, 'partner', 19, true),
            ('10000000-0000-4000-8000-000000000020'::uuid, 'Coursetopia', '/assets/img/partners/Coursetopia.png', NULL, 'partner', 20, true),
            ('10000000-0000-4000-8000-000000000021'::uuid, 'Global Innovation', '/assets/img/partners/Global Innovation.png', NULL, 'partner', 21, true),
            ('10000000-0000-4000-8000-000000000022'::uuid, 'KL . Space', '/assets/img/partners/KL . Space.png', NULL, 'partner', 22, true),
            ('10000000-0000-4000-8000-000000000023'::uuid, 'Kush Digital', '/assets/img/partners/Kush Digital.png', NULL, 'partner', 23, true),
            ('10000000-0000-4000-8000-000000000024'::uuid, 'LyraSense', '/assets/img/partners/LyraSense.png', NULL, 'partner', 24, true),
            ('10000000-0000-4000-8000-000000000025'::uuid, 'Nasa space Alex', '/assets/img/partners/Nasa space Alex.png', NULL, 'partner', 25, true),
            ('10000000-0000-4000-8000-000000000026'::uuid, 'Nasa space Dami', '/assets/img/partners/Nasa space Dami.png', NULL, 'partner', 26, true),
            ('10000000-0000-4000-8000-000000000027'::uuid, 'Nasa space Dubai', '/assets/img/partners/Nasa space Dubai.png', NULL, 'partner', 27, true),
            ('10000000-0000-4000-8000-000000000028'::uuid, 'PL', '/assets/img/partners/PL.png', NULL, 'partner', 28, true),
            ('10000000-0000-4000-8000-000000000029'::uuid, 'Quantum', '/assets/img/partners/Quantum.png', NULL, 'partner', 29, true),
            ('10000000-0000-4000-8000-000000000030'::uuid, 'Raise Me', '/assets/img/partners/Raise Me.png', NULL, 'partner', 30, true),
            ('10000000-0000-4000-8000-000000000031'::uuid, 'Sal7lyy', '/assets/img/partners/Sal7lyy.png', NULL, 'partner', 31, true),
            ('10000000-0000-4000-8000-000000000032'::uuid, 'SatEx', '/assets/img/partners/SatEx.png', NULL, 'partner', 32, true),
            ('10000000-0000-4000-8000-000000000033'::uuid, 'School Try', '/assets/img/partners/School Try.png', NULL, 'partner', 33, true),
            ('10000000-0000-4000-8000-000000000034'::uuid, 'SpaceKids India', '/assets/img/partners/SpaceKids India.png', NULL, 'partner', 34, true),
            ('10000000-0000-4000-8000-000000000035'::uuid, 'UniTors', '/assets/img/partners/UniTors.png', NULL, 'partner', 35, true),
            ('10000000-0000-4000-8000-000000000036'::uuid, 'Changemakers', '/assets/img/supporters/Changemakers.png', NULL, 'supporter', 36, true),
            ('10000000-0000-4000-8000-000000000037'::uuid, 'Heriot', '/assets/img/supporters/Heriot.png', NULL, 'supporter', 37, true),
            ('10000000-0000-4000-8000-000000000038'::uuid, 'ITUSEED', '/assets/img/supporters/ITUSEED.png', NULL, 'supporter', 38, true),
            ('10000000-0000-4000-8000-000000000039'::uuid, 'MBRIF', '/assets/img/supporters/MBRIF.png', NULL, 'supporter', 39, true),
            ('10000000-0000-4000-8000-000000000040'::uuid, 'MZN', '/assets/img/supporters/MZN.png', NULL, 'supporter', 40, true),
            ('10000000-0000-4000-8000-000000000041'::uuid, 'SEA', '/assets/img/supporters/SEA.png', NULL, 'supporter', 41, true),
            ('10000000-0000-4000-8000-000000000042'::uuid, 'Supercharger', '/assets/img/supporters/Supercharger.png', NULL, 'supporter', 42, true),
            ('10000000-0000-4000-8000-000000000043'::uuid, 'Sharjah Startup', '/assets/img/supporters/sharjah startup.png', NULL, 'supporter', 43, true)
        ) AS seed(id, name, logo_url, website_url, tier, display_order, is_active)
        WHERE NOT EXISTS (SELECT 1 FROM sponsors)
        """
    ))


def downgrade() -> None:
    op.drop_table('sponsors')
