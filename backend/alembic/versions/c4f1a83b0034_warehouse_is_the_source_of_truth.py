"""Warehouse becomes the source of truth for stock/kit location; sessions and
cohorts get an explicit warehouse override.

Location and warehouse were being treated as interchangeable: `stock_levels`
was still keyed and constrained on `location_id` (`warehouse_id` was a
decorative nullable side column), `kits.current_location_id` was still
authoritative, and nothing on `sessions`/`cohorts` referenced a warehouse at
all even though a location can — and in this data, already does — have more
than one. This migration tightens the schema to match the actual model:
stock and kits live in a warehouse; a location is the union of its
warehouses; a session/cohort may pin a specific warehouse the same way it
already pins a specific location override.

Revision ID: c4f1a83b0034
Revises: f8d9e21a0033
Create Date: 2026-08-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "c4f1a83b0034"
down_revision = "f8d9e21a0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    # Defensive backfill — f8d9e21a0033 already gave every location a default
    # warehouse and backfilled existing rows, but a row created between that
    # migration landing and this one (or in a differently-seeded DB) could
    # still be null. Same "pick a location's first/only warehouse" logic.
    connection.execute(sa.text(
        "UPDATE stock_levels s SET warehouse_id = ("
        "  SELECT w.id FROM warehouses w WHERE w.location_id = s.location_id ORDER BY w.created_at LIMIT 1"
        ") WHERE s.warehouse_id IS NULL"
    ))
    connection.execute(sa.text(
        "UPDATE kits k SET current_warehouse_id = ("
        "  SELECT w.id FROM warehouses w WHERE w.location_id = k.current_location_id ORDER BY w.created_at LIMIT 1"
        ") WHERE k.current_warehouse_id IS NULL"
    ))

    # Anything still null (a location with zero warehouses) blocks the NOT
    # NULL below — surface it instead of failing on a bare constraint error.
    orphan_stock = connection.execute(sa.text(
        "SELECT count(*) FROM stock_levels WHERE warehouse_id IS NULL"
    )).scalar()
    orphan_kits = connection.execute(sa.text(
        "SELECT count(*) FROM kits WHERE current_warehouse_id IS NULL"
    )).scalar()
    if orphan_stock or orphan_kits:
        raise RuntimeError(
            f"{orphan_stock} stock_levels and {orphan_kits} kits have no resolvable "
            "warehouse (their location has none) — create a warehouse for that "
            "location before running this migration."
        )

    # ── stock_levels: warehouse becomes the key, location_id goes away ──────
    op.drop_constraint("uq_stock_item_location", "stock_levels", type_="unique")
    op.drop_constraint("stock_levels_location_id_fkey", "stock_levels", type_="foreignkey")
    op.drop_column("stock_levels", "location_id")
    op.alter_column("stock_levels", "warehouse_id", existing_type=UUID(as_uuid=True), nullable=False)
    op.create_unique_constraint("uq_stock_item_warehouse", "stock_levels", ["item_id", "warehouse_id"])

    # ── kits: warehouse becomes authoritative; location_id stays as a
    # denormalized column derived from it (never set independently) ────────
    op.alter_column("kits", "current_warehouse_id", existing_type=UUID(as_uuid=True), nullable=False)

    # ── cohorts / sessions: explicit warehouse override, same shape as the
    # existing location_id override ─────────────────────────────────────────
    op.add_column(
        "cohorts",
        sa.Column(
            "warehouse_id", UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "warehouse_id", UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "warehouse_id")
    op.drop_column("cohorts", "warehouse_id")

    op.alter_column("kits", "current_warehouse_id", existing_type=UUID(as_uuid=True), nullable=True)

    op.drop_constraint("uq_stock_item_warehouse", "stock_levels", type_="unique")
    op.add_column(
        "stock_levels",
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=True),
    )
    connection = op.get_bind()
    connection.execute(sa.text(
        "UPDATE stock_levels s SET location_id = ("
        "  SELECT w.location_id FROM warehouses w WHERE w.id = s.warehouse_id"
        ")"
    ))
    op.alter_column("stock_levels", "location_id", existing_type=UUID(as_uuid=True), nullable=False)
    op.alter_column("stock_levels", "warehouse_id", existing_type=UUID(as_uuid=True), nullable=True)
    op.create_unique_constraint("uq_stock_item_location", "stock_levels", ["item_id", "location_id"])
