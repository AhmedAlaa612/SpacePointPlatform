"""designs.battery_capacity_wh (Design v2, 7D-2 / D4)

Closes F8: the power budget checked instantaneous load against generation
and threw the per-orbit energy total away. With a battery the design can be
checked for two things Madar never asked — whether the orbit is
sustainable (energy in over a full lap covers energy out, using the
illumination fraction already in the student's own CONOPS), and whether the
battery survives eclipse within its depth-of-discharge limit.

The capacity is the student's design decision. The DoD limit is not: it
lives in `mission_variants.config.max_depth_of_discharge_pct`, because a
student setting their own pass threshold is exactly the bug (F4) this port
already fixed once.

Nullable on purpose — existing in-progress designs simply show the new
energy step as "not started" rather than being retro-failed.

Revision ID: e7b2f14a9c60
Revises: d4a1c07e5b32
"""

import sqlalchemy as sa
from alembic import op

revision = "e7b2f14a9c60"
down_revision = "d4a1c07e5b32"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("designs", sa.Column("battery_capacity_wh", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("designs", "battery_capacity_wh")
