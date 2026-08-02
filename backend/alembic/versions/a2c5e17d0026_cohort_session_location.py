"""Cohort/session location as a real entity, not free text

Operator ask (2026-08-01): a cohort's location was a free-text string plus a
never-wired `location_map_url` column — no link to the `locations` table
that kits and stock already use as their warehouse. Ops had no dashboard for
"where is this cohort" the way they already have one for "where is this kit."

This links Cohort (and, for the rare session that meets somewhere else, a
Session-level override) to that same `locations` table via `location_id`.
`locations.address` / `maps_url` move onto the entity itself — the address
and map link belong to the place, not to whichever cohort happens to be
running there this month.

The old `cohorts.location` / `location_map_url` free-text columns are left in
place (nullable, unused by the UI going forward) rather than dropped — they
are cheap to keep and dropping them would erase whatever ops already typed
into existing cohorts with no way to recover it.

Revision ID: a2c5e17d0026
Revises: e1f4a92c0025
Create Date: 2026-08-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "a2c5e17d0026"
down_revision = "e1f4a92c0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("locations", sa.Column("address", sa.Text(), nullable=True))
    op.add_column("locations", sa.Column("maps_url", sa.Text(), nullable=True))

    op.add_column(
        "cohorts",
        sa.Column(
            "location_id", UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index("ix_cohorts_location_id", "cohorts", ["location_id"])

    # Session-level override — absent means "use the cohort's location",
    # same absent-means-inherit pattern as Session.price vs Program.price.
    op.add_column(
        "sessions",
        sa.Column(
            "location_id", UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index("ix_sessions_location_id", "sessions", ["location_id"])


def downgrade() -> None:
    op.drop_index("ix_sessions_location_id", table_name="sessions")
    op.drop_column("sessions", "location_id")
    op.drop_index("ix_cohorts_location_id", table_name="cohorts")
    op.drop_column("cohorts", "location_id")
    op.drop_column("locations", "maps_url")
    op.drop_column("locations", "address")
