"""Add warehouses entity and link to locations, kits, stock_levels, and movements.

Revision ID: f8d9e21a0033
Revises: a7c9e15f0032
Create Date: 2026-08-01
"""

import uuid
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "f8d9e21a0033"
down_revision = "a7c9e15f0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create warehouses table
    op.create_table(
        "warehouses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "location_id",
            UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("code", sa.String(32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 2. Add warehouse_id columns to kits, stock_levels, and movements
    op.add_column(
        "kits",
        sa.Column(
            "current_warehouse_id",
            UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=True,
            index=True,
        ),
    )

    op.add_column(
        "stock_levels",
        sa.Column(
            "warehouse_id",
            UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )

    op.add_column(
        "movements",
        sa.Column(
            "from_warehouse_id",
            UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )

    op.add_column(
        "movements",
        sa.Column(
            "to_warehouse_id",
            UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )

    # 3. Data Migration: Create default Warehouse for each location and backfill warehouse IDs
    connection = op.get_bind()
    locations = connection.execute(sa.text("SELECT id, name FROM locations")).fetchall()

    for loc_id, loc_name in locations:
        wh_id = str(uuid.uuid4())
        wh_name = f"{loc_name} Warehouse"
        wh_code = f"WH-{loc_name[:3].upper()}"

        connection.execute(
            sa.text(
                "INSERT INTO warehouses (id, location_id, name, code, is_active, created_at) "
                "VALUES (:id, :loc_id, :name, :code, true, NOW())"
            ),
            {"id": wh_id, "loc_id": loc_id, "name": wh_name, "code": wh_code},
        )

        # Backfill kits
        connection.execute(
            sa.text(
                "UPDATE kits SET current_warehouse_id = :wh_id "
                "WHERE current_location_id = :loc_id AND current_warehouse_id IS NULL"
            ),
            {"wh_id": wh_id, "loc_id": loc_id},
        )

        # Backfill stock_levels
        connection.execute(
            sa.text(
                "UPDATE stock_levels SET warehouse_id = :wh_id "
                "WHERE location_id = :loc_id AND warehouse_id IS NULL"
            ),
            {"wh_id": wh_id, "loc_id": loc_id},
        )

        # Backfill movements
        connection.execute(
            sa.text(
                "UPDATE movements SET from_warehouse_id = :wh_id "
                "WHERE from_location_id = :loc_id AND from_warehouse_id IS NULL"
            ),
            {"wh_id": wh_id, "loc_id": loc_id},
        )

        connection.execute(
            sa.text(
                "UPDATE movements SET to_warehouse_id = :wh_id "
                "WHERE to_location_id = :loc_id AND to_warehouse_id IS NULL"
            ),
            {"wh_id": wh_id, "loc_id": loc_id},
        )


def downgrade() -> None:
    op.drop_column("movements", "to_warehouse_id")
    op.drop_column("movements", "from_warehouse_id")
    op.drop_column("stock_levels", "warehouse_id")
    op.drop_column("kits", "current_warehouse_id")
    op.drop_table("warehouses")
