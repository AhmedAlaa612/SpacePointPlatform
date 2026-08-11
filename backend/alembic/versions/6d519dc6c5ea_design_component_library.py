"""design_component_library (P7-3, LMS Phase 2 Stage 7, 2026-08-11).

The shared component catalog for design missions — was Madar's
`components`. Dimensions are numeric columns from the start (F3: the old
string parser split on ASCII 'x', but seed data used U+00D7, so every
seeded component's volume was vacuously zero).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "6d519dc6c5ea"
down_revision = "35229e5bc00b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "design_component_library",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("component_name", sa.String(128), nullable=False),
        sa.Column("subsystem", sa.String(40), nullable=False),
        sa.Column("tag", sa.String(40), nullable=True),
        sa.Column("example_role", sa.Text(), nullable=True),
        sa.Column("scaled_description", sa.Text(), nullable=True),
        sa.Column("length_mm", sa.Float(), nullable=True),
        sa.Column("width_mm", sa.Float(), nullable=True),
        sa.Column("height_mm", sa.Float(), nullable=True),
        sa.Column("scaled_mass_g", sa.Float(), nullable=True),
        sa.Column("voltage_v", sa.Float(), nullable=True),
        sa.Column("current_ma", sa.Float(), nullable=True),
        sa.Column("data_size", sa.String(80), nullable=True),
        sa.Column("assumed_cost_usd", sa.Float(), nullable=True),
        sa.Column("temperature_range", sa.String(40), nullable=True),
        sa.Column("key_specs", sa.Text(), nullable=True),
        sa.Column("image_bucket", sa.String(64), nullable=True),
        sa.Column("image_path", sa.String(512), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("component_code", sa.String(40), nullable=True),
        sa.Column("datasheet_url", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_design_component_library_subsystem", "design_component_library", ["subsystem"])
    op.create_index("ix_design_component_library_is_active", "design_component_library", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_design_component_library_is_active", table_name="design_component_library")
    op.drop_index("ix_design_component_library_subsystem", table_name="design_component_library")
    op.drop_table("design_component_library")
