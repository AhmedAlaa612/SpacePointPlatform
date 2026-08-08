"""Soft-deprecate `locations.country` (2026-08-08, chained after the
locations→city backfill).

`Location.country` is now derived from `city_id → cities.country`, so the
NOT NULL constraint goes (it would otherwise force every legacy row — and
every future location — to keep a second, potentially-disagreeing copy of
the country). The column itself is kept, unused, exactly the way this
codebase already treats `Cohort.location`: nothing outside the inventory
CRUD router reads it today (full-backend grep verified), and dropping it
outright is the Phase-3 follow-up once nothing reads it at all.

Downgrade re-adds the constraint, backfilling NULLs from the city first —
same discipline as a1b2c3d4e5f6's downgrade.
"""

import sqlalchemy as sa
from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "c9d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("locations", "country", nullable=True)


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text(
        "UPDATE locations l SET country = c.country "
        "FROM cities c WHERE l.city_id = c.id AND l.country IS NULL"
    ))
    op.alter_column("locations", "country", nullable=False)
