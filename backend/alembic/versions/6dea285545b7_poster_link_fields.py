"""Poster/Canva link fields (August Build Brief, Branch 3).

Two plain nullable columns, no new table — the poster feature is scoped
down to "two link fields on the mission attempt." `cohorts.poster_template_url`
is the master template link ops sets once per cohort; `designs.poster_url`
is the team's own working-copy link, pasted back in. Both start NULL for
every existing row (no template set, no poster pasted yet), which is the
correct default state — no backfill needed.

Revision ID: 6dea285545b7
Revises: f4c8b1e6a923
"""

import sqlalchemy as sa
from alembic import op

revision = "6dea285545b7"
down_revision = "f4c8b1e6a923"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cohorts", sa.Column("poster_template_url", sa.String(512), nullable=True))
    op.add_column("designs", sa.Column("poster_url", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("designs", "poster_url")
    op.drop_column("cohorts", "poster_template_url")
