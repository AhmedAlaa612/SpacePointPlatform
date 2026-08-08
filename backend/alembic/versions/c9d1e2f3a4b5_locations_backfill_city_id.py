"""Locations → City backfill (2026-08-08, chained after a1b2c3d4e5f6).

`locations.city_id` was added nullable in the cities migration and left
unset on existing rows — the plan explicitly refused to guess a city from
`Location.name`. This is the guarded exception: a location whose free-text
`name` exactly matches a seeded city's name *in the same country* (both
case- and whitespace-insensitive) is unambiguous — "Abu Dhabi" can only be
the Abu Dhabi city. Verified against the live dev DB: this auto-resolves
"Abu Dhabi", "Al Ain" and "Dubai" (3 of 5 currently-null rows). "Egypt" and
"Main Warehouse" are not city names and stay NULL by design — ops fixes
those by hand through the now-required City field on the location forms.

Downgrade is a no-op: this is a best-effort data repair, and reversing it
would destroy real data.
"""

import sqlalchemy as sa
from alembic import op

revision = "c9d1e2f3a4b5"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text(
        "UPDATE locations l SET city_id = c.id FROM cities c "
        "WHERE l.city_id IS NULL AND l.country = c.country "
        "  AND lower(trim(c.name)) = lower(trim(l.name))"
    ))


def downgrade() -> None:
    pass
