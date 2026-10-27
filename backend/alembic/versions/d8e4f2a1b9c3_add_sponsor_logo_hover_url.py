"""add sponsor logo hover url

Revision ID: d8e4f2a1b9c3
Revises: c7d3e1f9a2b5
Create Date: 2026-10-27

Adds `logo_hover_url` to the `sponsors` table to support separate white and
colored hover versions of partner/client/supporter logos.
"""

from alembic import op
import sqlalchemy as sa


revision = 'd8e4f2a1b9c3'
down_revision = 'c7d3e1f9a2b5'
branch_labels = None
depends_on = None


# Initial mapping for seeded sponsors where an original colored version exists on disk
SEED_HOVER_LOGOS = [
    ('AGF', '/assets/img/clients/AGF original.png'),
    ('Edge', '/assets/img/clients/Edge Original.png'),
    ('Etlaq', '/assets/img/clients/Etlaq original.png'),
    ('Fada', '/assets/img/clients/Fada original.png'),
    ('Gems', '/assets/img/clients/Gems original.png'),
    ('HCT', '/assets/img/clients/HCT original.png'),
    ('KU', '/assets/img/clients/KU original.png'),
    ('Kaust', '/assets/img/clients/Kaust original.png'),
    ('MBZUAI', '/assets/img/clients/MBZUAI original.png'),
    ('MUD', '/assets/img/clients/MUD original.png'),
    ('Museum of the Future', '/assets/img/clients/Museum of the future original.png'),
    ('Nasa Dubai', '/assets/img/clients/Nasa Dubai original.png'),
    ('UAESA', '/assets/img/clients/UAESA original.png'),
    ('UAEU', '/assets/img/clients/UAEU original.png'),
    ('Maker Fair', '/assets/img/clients/maker fair original.png'),
    ('Space42', '/assets/img/clients/space42 original.png'),
    ('Changemakers', '/assets/img/supporters/changemakers original.png'),
    ('Heriot', '/assets/img/supporters/Heriot original.png'),
    ('ITUSEED', '/assets/img/supporters/ITUSEED original.png'),
    ('MBRIF', '/assets/img/supporters/MBRIF original.png'),
    ('MZN', '/assets/img/supporters/MZN original.png'),
    ('SEA', '/assets/img/supporters/SEA original.png'),
    ('Supercharger', '/assets/img/supporters/Supercharger original.png'),
    ('Sharjah Startup', '/assets/img/supporters/sharjah startup original.png'),
]


def upgrade() -> None:
    op.add_column('sponsors', sa.Column('logo_hover_url', sa.String(length=512), nullable=True))

    conn = op.get_bind()
    for name, hover_url in SEED_HOVER_LOGOS:
        conn.execute(
            sa.text("UPDATE sponsors SET logo_hover_url = :hover_url WHERE name = :name AND logo_hover_url IS NULL"),
            {"name": name, "hover_url": hover_url},
        )


def downgrade() -> None:
    op.drop_column('sponsors', 'logo_hover_url')
