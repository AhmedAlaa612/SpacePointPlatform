"""design schema, re-rooted on mission_attempts.id (P7-4, LMS Phase 2
Stage 7, 2026-08-11).

designs / design_modes / design_components / design_component_mode_states
/ design_{data,power,mass,cost,link}_budget_entries — the CubeSat
mission-design workbench ported from Madar, one Design per MissionAttempt
instead of per user (buys teams, variants, retries and auditable grading
at once). No mission_constraints table: pass/fail thresholds live in
MissionVariant.config (P7-6), never a student-editable row (F4 fix).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b6de791de443"
down_revision = "6d519dc6c5ea"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "designs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mission_attempts.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("design_name", sa.String(128), nullable=False),
        sa.Column("design_objective", sa.Text(), nullable=True),
        sa.Column("orbit_type", sa.String(20), nullable=True),
        sa.Column("orbit_duration_min", sa.Float(), nullable=True),
        sa.Column("orbits_per_day", sa.Float(), nullable=True),
        sa.Column("selected_cubesat_size", sa.String(4), nullable=False, server_default="1U"),
        sa.Column("selected_solar_cells", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_designs_cohort_id", "designs", ["cohort_id"])

    op.create_table(
        "design_modes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("designs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode_name", sa.String(60), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_min", sa.Float(), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_design_modes_design_id", "design_modes", ["design_id"])

    op.create_table(
        "design_components",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("designs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("library_component_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("design_component_library.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("component_name", sa.String(128), nullable=False),
        sa.Column("subsystem", sa.String(40), nullable=False),
        sa.Column("image_bucket", sa.String(64), nullable=True),
        sa.Column("image_path", sa.String(512), nullable=True),
        sa.Column("mass_per_unit_g", sa.Float(), nullable=True),
        sa.Column("length_mm", sa.Float(), nullable=True),
        sa.Column("width_mm", sa.Float(), nullable=True),
        sa.Column("height_mm", sa.Float(), nullable=True),
        sa.Column("voltage_v", sa.Float(), nullable=True),
        sa.Column("current_ma", sa.Float(), nullable=True),
        sa.Column("cost_per_unit_aed", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_design_components_design_id", "design_components", ["design_id"])
    op.create_index("ix_design_components_library_component_id", "design_components", ["library_component_id"])

    op.create_table(
        "design_component_mode_states",
        sa.Column("design_component_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("design_components.id", ondelete="CASCADE"), nullable=False),
        sa.Column("design_mode_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("design_modes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_on", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("design_component_id", "design_mode_id", name="pk_design_component_mode_states"),
    )

    op.create_table(
        "design_data_budget_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("design_component_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("design_components.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("data_type", sa.String(60), nullable=True),
        sa.Column("data_size_per_measurement_kb", sa.Float(), nullable=False, server_default="0"),
        sa.Column("measurements_per_minute", sa.Float(), nullable=False, server_default="0"),
        sa.Column("priority", sa.String(12), nullable=False, server_default="Medium"),
        sa.Column("storage_mode", sa.String(8), nullable=False, server_default="Stored"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "design_power_budget_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("design_component_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("design_components.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("voltage_v", sa.Float(), nullable=True),
        sa.Column("current_ma", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "design_mass_budget_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("design_component_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("design_components.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("mass_per_unit_g", sa.Float(), nullable=True),
        sa.Column("length_mm", sa.Float(), nullable=True),
        sa.Column("width_mm", sa.Float(), nullable=True),
        sa.Column("height_mm", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "design_cost_budget_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("design_component_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("design_components.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("cost_per_unit_aed", sa.Float(), nullable=True),
        sa.Column("vendor", sa.String(80), nullable=True),
        sa.Column("priority", sa.String(12), nullable=True),
        sa.Column("purchase_link", sa.String(512), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "design_link_budget_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("designs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("band_profile", sa.String(12), nullable=False, server_default="UHF"),
        sa.Column("downlink_frequency_mhz", sa.Float(), nullable=False, server_default="437.5"),
        sa.Column("uplink_frequency_mhz", sa.Float(), nullable=False, server_default="145.8"),
        sa.Column("satellite_antenna_gain_dbi", sa.Float(), nullable=False, server_default="2.0"),
        sa.Column("data_rate_kbps", sa.Float(), nullable=False, server_default="9.6"),
        sa.Column("required_signal_quality_db", sa.Float(), nullable=False, server_default="9.6"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_saved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("design_link_budget_entries")
    op.drop_table("design_cost_budget_entries")
    op.drop_table("design_mass_budget_entries")
    op.drop_table("design_power_budget_entries")
    op.drop_table("design_data_budget_entries")
    op.drop_table("design_component_mode_states")
    op.drop_index("ix_design_components_library_component_id", table_name="design_components")
    op.drop_index("ix_design_components_design_id", table_name="design_components")
    op.drop_table("design_components")
    op.drop_index("ix_design_modes_design_id", table_name="design_modes")
    op.drop_table("design_modes")
    op.drop_index("ix_designs_cohort_id", table_name="designs")
    op.drop_table("designs")
