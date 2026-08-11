"""Design mission schema (P7-3/P7-4, Phase 2 Stage 7, 2026-08-11) — the
CubeSat mission-design workbench ported from Madar (MISSIONS_REPORT.md
Ch.1), re-rooted on `mission_attempts.id` instead of `users.id`.

`Design` replaces Madar's own `missions` table (one row per student's
satellite) — that naming collided with the platform's `missions` table
(one row per challenge template) and had to change (Ch.1 §1.1, "mission"
means two different things; Ch.3's "naming trap"). One `Design` belongs to
exactly one `MissionAttempt` (`UNIQUE(attempt_id)`), never to a user
directly — that one change buys teams, variants, retries and auditable
grading for free (PHASE2_EXECUTION_PLAN.md Stage 7 note, P7-4).

`DesignComponentLibrary` replaces Madar's `components` table. Two audit
findings fixed here structurally:
- **F1** (deleting a library component CASCADEs away every student's
  selection and their budgets) — `DesignComponent.library_component_id` is
  RESTRICT, not CASCADE. Retiring a component is `is_active=false`
  (already the intended-but-unenforced mechanism in Madar); there is no
  hard-delete path once a component has ever been used.
- **F2/F3** (no spec snapshotting, so editing the library retroactively
  changes graded work; dimensions were a free-text string parsed with a
  bug that made every seeded component's volume zero) — `DesignComponent`
  freezes the library row's values (name, subsystem, mass, three numeric
  dimensions, voltage/current, cost) at the moment a student adds it.
  Every budget calculator reads this snapshot, never the live library row.
  A later library edit changes nothing about a design already in progress
  or already graded.

Constraints (Madar's `mission_constraints`) do not exist as a table here
at all — that's P7-6's fix for **F4** (a student could `PUT` their own
`max_allowed_mass_kg` until a failing design passed). Pass/fail thresholds
live in `MissionVariant.config` (read-only to the student, instructor-
authored); `Design.selected_cubesat_size` is a genuine student *choice*
from a hardcoded preset table (`services/missions/design/calculators.py
::CUBESAT_PRESETS`) that determines a limit, never a field that sets one.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class DesignComponentLibrary(Base):
    """The shared component catalog students pick from — was Madar's
    `components`. `is_active=False` retires a component from the picker
    without touching any design that already used it (their
    `DesignComponent` snapshot is unaffected either way)."""

    __tablename__ = "design_component_library"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    component_name = Column(String(128), nullable=False)
    subsystem = Column(String(40), nullable=False)  # ADCS|CDHS|EPS|COMMS|Payload|Structure|Thermal
    tag = Column(String(40), nullable=True)
    example_role = Column(Text, nullable=True)
    scaled_description = Column(Text, nullable=True)
    # Numeric from the start (F3) — never a "50x50x30" string to parse.
    length_mm = Column(Float, nullable=True)
    width_mm = Column(Float, nullable=True)
    height_mm = Column(Float, nullable=True)
    scaled_mass_g = Column(Float, nullable=True)
    voltage_v = Column(Float, nullable=True)
    current_ma = Column(Float, nullable=True)
    data_size = Column(String(80), nullable=True)  # informational display string, e.g. "12 KB/s"
    assumed_cost_usd = Column(Float, nullable=True)
    temperature_range = Column(String(40), nullable=True)
    key_specs = Column(Text, nullable=True)
    image_bucket = Column(String(64), nullable=True)
    image_path = Column(String(512), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    notes = Column(Text, nullable=True)
    component_code = Column(String(40), nullable=True)
    datasheet_url = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True)


class Design(Base):
    """One student's (or team's) satellite design — one per
    `MissionAttempt`. `cohort_id` is the P7-7 step-gating scope: NULL means
    this design was started outside a gated cohort context and every step
    is always open (a standalone attempt, mirroring how a standalone
    mission attempt needs no cohort at all)."""

    __tablename__ = "designs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(
        UUID(as_uuid=True), ForeignKey("mission_attempts.id", ondelete="CASCADE"), nullable=False, unique=True,
    )
    design_name = Column(String(128), nullable=False)
    design_objective = Column(Text, nullable=True)
    orbit_type = Column(String(20), nullable=True)  # LEO|MEO|GEO|SSO|Custom
    orbit_duration_min = Column(Float, nullable=True)
    orbits_per_day = Column(Float, nullable=True)
    selected_cubesat_size = Column(String(4), nullable=False, default="1U", server_default="1U")
    selected_solar_cells = Column(Integer, nullable=False, default=0, server_default="0")
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DesignMode(Base):
    """A CONOPS phase (Sun Pointing / Nadir Pointing / Ground Station /
    Safe-Eclipse) — was Madar's `mission_modes`."""

    __tablename__ = "design_modes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_id = Column(UUID(as_uuid=True), ForeignKey("designs.id", ondelete="CASCADE"), nullable=False)
    mode_name = Column(String(60), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    duration_min = Column(Float, nullable=False, default=0.0)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True)


class DesignComponent(Base):
    """A component added to a design — was Madar's `mission_components`,
    now carrying a frozen snapshot of the library row's specs at add time
    (F2/F3 fix, see module docstring). `library_component_id` is RESTRICT
    (F1 fix): a component that has ever been added to a design cannot be
    hard-deleted from the library, only retired via `is_active`.
    """

    __tablename__ = "design_components"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_id = Column(UUID(as_uuid=True), ForeignKey("designs.id", ondelete="CASCADE"), nullable=False)
    library_component_id = Column(
        UUID(as_uuid=True), ForeignKey("design_component_library.id", ondelete="RESTRICT"), nullable=False,
    )
    quantity = Column(Integer, nullable=False, default=1)
    # ── frozen snapshot, taken from the library row at add time ──────────
    component_name = Column(String(128), nullable=False)
    subsystem = Column(String(40), nullable=False)
    image_bucket = Column(String(64), nullable=True)
    image_path = Column(String(512), nullable=True)
    mass_per_unit_g = Column(Float, nullable=True)
    length_mm = Column(Float, nullable=True)
    width_mm = Column(Float, nullable=True)
    height_mm = Column(Float, nullable=True)
    voltage_v = Column(Float, nullable=True)
    current_ma = Column(Float, nullable=True)
    cost_per_unit_aed = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DesignComponentModeState(Base):
    """One cell of the CONOPS component x mode matrix — was Madar's
    `component_mode_states`. Composite PK, no surrogate id: the pair is
    the identity."""

    __tablename__ = "design_component_mode_states"
    __table_args__ = (
        PrimaryKeyConstraint("design_component_id", "design_mode_id", name="pk_design_component_mode_states"),
    )

    design_component_id = Column(
        UUID(as_uuid=True), ForeignKey("design_components.id", ondelete="CASCADE"), nullable=False,
    )
    design_mode_id = Column(UUID(as_uuid=True), ForeignKey("design_modes.id", ondelete="CASCADE"), nullable=False)
    is_on = Column(Boolean, nullable=False, default=False)


class DesignDataBudgetEntry(Base):
    """A student's override of a component's data-generation profile —
    absent means "use the component's use-case defaults" (there are none
    in the library, so an absent entry means simply no data contribution).
    Was Madar's `data_budget_entries`."""

    __tablename__ = "design_data_budget_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_component_id = Column(
        UUID(as_uuid=True), ForeignKey("design_components.id", ondelete="CASCADE"), nullable=False, unique=True,
    )
    data_type = Column(String(60), nullable=True)
    data_size_per_measurement_kb = Column(Float, nullable=False, default=0.0)
    measurements_per_minute = Column(Float, nullable=False, default=0.0)
    priority = Column(String(12), nullable=False, default="Medium", server_default="Medium")
    storage_mode = Column(String(8), nullable=False, default="Stored", server_default="Stored")  # Stored|Sent|Both
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True)


class DesignPowerBudgetEntry(Base):
    """A student's override of a component's voltage/current — falls back
    to the `DesignComponent` snapshot when absent (never the live library
    row). Was Madar's `power_budget_entries`."""

    __tablename__ = "design_power_budget_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_component_id = Column(
        UUID(as_uuid=True), ForeignKey("design_components.id", ondelete="CASCADE"), nullable=False, unique=True,
    )
    voltage_v = Column(Float, nullable=True)
    current_ma = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True)


class DesignMassBudgetEntry(Base):
    """A student's override of a component's quantity/mass/dimensions.
    Was Madar's `mass_budget_entries`."""

    __tablename__ = "design_mass_budget_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_component_id = Column(
        UUID(as_uuid=True), ForeignKey("design_components.id", ondelete="CASCADE"), nullable=False, unique=True,
    )
    quantity = Column(Integer, nullable=True)
    mass_per_unit_g = Column(Float, nullable=True)
    length_mm = Column(Float, nullable=True)
    width_mm = Column(Float, nullable=True)
    height_mm = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True)


class DesignCostBudgetEntry(Base):
    """A student's override of a component's cost. Was Madar's
    `cost_budget_entries`."""

    __tablename__ = "design_cost_budget_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_component_id = Column(
        UUID(as_uuid=True), ForeignKey("design_components.id", ondelete="CASCADE"), nullable=False, unique=True,
    )
    quantity = Column(Integer, nullable=True)
    cost_per_unit_aed = Column(Float, nullable=True)
    vendor = Column(String(80), nullable=True)
    priority = Column(String(12), nullable=True)
    purchase_link = Column(String(512), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True)


class DesignLinkBudgetEntry(Base):
    """The mission-level RF link configuration — one per design, not per
    component (RF is a spacecraft-level property). `is_saved` is the F6
    fix: a real recorded fact the save endpoint sets, replacing Madar's
    `updated_at <= created_at` heuristic for "has the student touched
    this" (corruptible by any other writer or a no-op save). Was Madar's
    `link_budget_entries`."""

    __tablename__ = "design_link_budget_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_id = Column(UUID(as_uuid=True), ForeignKey("designs.id", ondelete="CASCADE"), nullable=False, unique=True)
    band_profile = Column(String(12), nullable=False, default="UHF", server_default="UHF")
    downlink_frequency_mhz = Column(Float, nullable=False, default=437.5)
    uplink_frequency_mhz = Column(Float, nullable=False, default=145.8)
    satellite_antenna_gain_dbi = Column(Float, nullable=False, default=2.0)
    data_rate_kbps = Column(Float, nullable=False, default=9.6)
    required_signal_quality_db = Column(Float, nullable=False, default=9.6)
    notes = Column(Text, nullable=True)
    is_saved = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True)


class DesignStepGate(Base):
    """Server-side step gating, per cohort (P7-7) — replaces Madar's
    `page_access`, which was enforced only in the browser (S1: the budget
    API endpoints had no page-access dependency at all; a student who knew
    the URL bypassed the entire instructor-paced release mechanism). A
    missing row for `(cohort_id, step_key)` means locked, matching Madar's
    own "defaults to locked" behavior for the five budget steps —
    Mission Setup / Components / CONOPS are never gated at all."""

    __tablename__ = "design_step_gates"
    __table_args__ = (
        PrimaryKeyConstraint("cohort_id", "step_key", name="pk_design_step_gates"),
    )

    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False)
    # data_budget|power_budget|link_budget|mass_budget|cost_budget
    step_key = Column(String(20), nullable=False)
    is_unlocked = Column(Boolean, nullable=False, default=False, server_default="false")
    updated_at = Column(DateTime(timezone=True), nullable=True)
