"""Design mission schemas (P7-5) — `/missions/design/*`.

One `GET .../attempts/{attempt_id}` returns everything the nine-step UI
needs in a single fetch (design fields, components with their budget
overrides, CONOPS matrix, link entry, and the computed dashboard) — a
deliberate simplification of Madar's one-fetch-per-page shape, since this
is a single-page wizard, not eleven server-rendered HTML files.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


# ── component library (the picker) ──────────────────────────────────────

class DesignLibraryComponentOut(BaseModel):
    id: UUID
    component_name: str
    subsystem: str
    tag: str | None = None
    example_role: str | None = None
    scaled_description: str | None = None
    length_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    scaled_mass_g: float | None = None
    voltage_v: float | None = None
    current_ma: float | None = None
    data_size: str | None = None
    assumed_cost_usd: float | None = None
    temperature_range: str | None = None
    key_specs: str | None = None
    image_url: str | None = None
    component_code: str | None = None
    datasheet_url: str | None = None


# ── design components (with budget overrides) ────────────────────────────

class DesignDataEntryOut(BaseModel):
    data_type: str | None = None
    data_size_per_measurement_kb: float = 0.0
    measurements_per_minute: float = 0.0
    priority: str = "Medium"
    storage_mode: Literal["Stored", "Sent", "Both"] = "Stored"
    notes: str | None = None


class DesignPowerEntryOut(BaseModel):
    voltage_v: float | None = None
    current_ma: float | None = None
    notes: str | None = None


class DesignMassEntryOut(BaseModel):
    quantity: int | None = None
    mass_per_unit_g: float | None = None
    length_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    notes: str | None = None


class DesignCostEntryOut(BaseModel):
    quantity: int | None = None
    cost_per_unit_aed: float | None = None
    vendor: str | None = None
    priority: str | None = None
    purchase_link: str | None = None
    notes: str | None = None


class DesignComponentOut(BaseModel):
    id: UUID
    library_component_id: UUID
    component_name: str
    subsystem: str
    image_url: str | None = None
    quantity: int
    mass_per_unit_g: float | None = None
    length_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    voltage_v: float | None = None
    current_ma: float | None = None
    cost_per_unit_aed: float | None = None
    on_mode_ids: list[UUID] = []
    data_entry: DesignDataEntryOut | None = None
    power_entry: DesignPowerEntryOut | None = None
    mass_entry: DesignMassEntryOut | None = None
    cost_entry: DesignCostEntryOut | None = None


class DesignComponentAddIn(BaseModel):
    library_component_id: UUID
    quantity: int = 1


# ── CONOPS ────────────────────────────────────────────────────────────────

class DesignModeOut(BaseModel):
    id: UUID
    mode_name: str
    position: int
    duration_min: float
    description: str | None = None


class ConopsSaveIn(BaseModel):
    mode_durations: dict[UUID, float]  # mode_id -> duration_min
    cell_states: dict[UUID, dict[UUID, bool]]  # component_id -> {mode_id: is_on}


# ── budget entry saves ────────────────────────────────────────────────────

class DataEntrySaveIn(BaseModel):
    data_type: str | None = None
    data_size_per_measurement_kb: float = 0.0
    measurements_per_minute: float = 0.0
    priority: str = "Medium"
    storage_mode: Literal["Stored", "Sent", "Both"] = "Stored"
    notes: str | None = None


class PowerEntrySaveIn(BaseModel):
    voltage_v: float | None = None
    current_ma: float | None = None
    notes: str | None = None


class MassEntrySaveIn(BaseModel):
    quantity: int | None = None
    mass_per_unit_g: float | None = None
    length_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    notes: str | None = None


class CostEntrySaveIn(BaseModel):
    quantity: int | None = None
    cost_per_unit_aed: float | None = None
    vendor: str | None = None
    priority: str | None = None
    purchase_link: str | None = None
    notes: str | None = None


class LinkEntrySaveIn(BaseModel):
    band_profile: str = "UHF"
    downlink_frequency_mhz: float
    uplink_frequency_mhz: float
    satellite_antenna_gain_dbi: float
    data_rate_kbps: float
    required_signal_quality_db: float
    notes: str | None = None


class LinkEntryOut(BaseModel):
    band_profile: str
    downlink_frequency_mhz: float
    uplink_frequency_mhz: float
    satellite_antenna_gain_dbi: float
    data_rate_kbps: float
    required_signal_quality_db: float
    notes: str | None = None
    is_saved: bool


# ── design fields ──────────────────────────────────────────────────────

class DesignUpdateIn(BaseModel):
    design_name: str | None = None
    design_objective: str | None = None
    orbit_type: str | None = None
    orbit_duration_min: float | None = None
    orbits_per_day: float | None = None
    selected_cubesat_size: Literal["1U", "2U", "3U", "6U"] | None = None
    selected_solar_cells: int | None = None
    battery_capacity_wh: float | None = None


# ── the dashboard (composed summary) ────────────────────────────────────

class StepStatusOut(BaseModel):
    has_data: bool
    is_valid: bool


class DataBudgetSummaryOut(BaseModel):
    total_per_orbit_kb: float
    total_per_day_kb: float
    total_stored_per_day_kb: float
    total_sent_per_day_kb: float
    storage_remaining_kb: float
    max_storage_kb: float
    required_storage_margin_kb: float


class PowerBudgetSummaryOut(BaseModel):
    total_power_mw: float
    total_energy_per_orbit_mwh: float
    total_energy_per_day_mwh: float
    power_margin_mw: float
    required_solar_cells: int
    generated_power_mw: float
    selected_solar_cells: int
    power_per_solar_cell_w: float


class MassBudgetSummaryOut(BaseModel):
    total_mass_kg: float
    mass_margin_kg: float
    total_volume_cm3: float
    volume_margin_cm3: float
    max_allowed_mass_kg: float
    available_internal_volume_cm3: float


class CostBudgetSummaryOut(BaseModel):
    total_cost_aed: float
    cost_margin_aed: float
    maximum_budget_aed: float


class LinkBudgetSummaryOut(BaseModel):
    margin_db: float
    status: str
    # The bar, not just the score. Showing "Margin: 0.61 dB - Failed Link"
    # without saying 3 dB is required leaves a student guessing which way to
    # move, which is the opposite of a teaching tool.
    good_threshold_db: float
    weak_threshold_db: float
    assumed_distance_km: float
    transmit_power_dbm: float


class EnergyBudgetSummaryOut(BaseModel):
    sunlit_minutes: float
    eclipse_minutes: float
    generated_per_orbit_mwh: float
    consumed_per_orbit_mwh: float
    energy_margin_mwh: float
    energy_balance_ok: bool
    eclipse_draw_mwh: float
    battery_capacity_mwh: float
    depth_of_discharge_pct: float
    max_depth_of_discharge_pct: float
    depth_of_discharge_ok: bool


class DownlinkBudgetSummaryOut(BaseModel):
    data_to_downlink_per_orbit_kb: float
    downlink_capacity_per_orbit_kb: float
    downlink_margin_kb: float
    contact_minutes: float
    utilisation_pct: float


class ConopsSummaryOut(BaseModel):
    total_mode_duration_min: float
    duration_difference_min: float


class MarginRowOut(BaseModel):
    key: str
    label: str
    value: float
    unit: str
    status: str  # good | tight | fail | incomplete
    interpretation: str


class ModuleCardOut(BaseModel):
    key: str
    title: str
    status: str
    kpi1_label: str
    kpi1_value: str
    kpi2_label: str
    kpi2_value: str
    tab: str


class AlertOut(BaseModel):
    severity: str  # error | warning | info | success
    step: str | None = None
    message: str


class RecommendationOut(BaseModel):
    key: str
    title: str
    message: str
    why: str


class OverallStatusOut(BaseModel):
    label: str
    all_valid: bool
    errors: int
    warnings: int
    incomplete: int


class DashboardOut(BaseModel):
    all_valid: bool
    steps: dict[str, StepStatusOut]
    conops: ConopsSummaryOut
    data: DataBudgetSummaryOut
    power: PowerBudgetSummaryOut
    mass: MassBudgetSummaryOut
    cost: CostBudgetSummaryOut
    link: LinkBudgetSummaryOut
    energy: EnergyBudgetSummaryOut
    downlink: DownlinkBudgetSummaryOut

    # Design v2 (7D-3) — the payoff screen. Madar had all of this and the
    # port rendered a boolean; the numbers were already here, the judgement
    # was not.
    overall: OverallStatusOut
    kpis: dict
    margins: list[MarginRowOut] = []
    module_cards: list[ModuleCardOut] = []
    charts: dict = {}
    alerts: list[AlertOut] = []
    recommendations: list[RecommendationOut] = []


# ── the full state fetch ─────────────────────────────────────────────────

class CubeSatPresetOut(BaseModel):
    size: str
    available_volume_cm3: float
    max_mass_kg: float


class DesignStateOut(BaseModel):
    id: UUID
    attempt_id: UUID
    mission_id: UUID
    variant_id: UUID
    variant_label: str
    attempt_status: str
    design_name: str
    design_objective: str | None = None
    orbit_type: str | None = None
    orbit_duration_min: float | None = None
    orbits_per_day: float | None = None
    selected_cubesat_size: str
    selected_solar_cells: int
    battery_capacity_wh: float | None = None
    created_at: datetime | None = None

    components: list[DesignComponentOut] = []
    modes: list[DesignModeOut] = []
    link_entry: LinkEntryOut | None = None

    cubesat_presets: list[CubeSatPresetOut] = []
    band_presets: dict[str, dict] = {}

    dashboard: DashboardOut
    # F9 — what the model simplifies, said out loud rather than hidden.
    assumptions: list[str] = []
    # 2026-08-17 — step_key -> is_unlocked, all 9 DESIGN_STEP_LABELS keys.
    # An attempt outside any cohort (or a cohort with no gates set) reads
    # all True — gating is opt-in per cohort, not a default-locked system.
    # Drives DesignMissionPage.tsx's tab-blocking alongside the existing
    # data-dependency check.
    step_gates: dict[str, bool] = {}


# ── Teaching surfaces (Design v2, 7D-4 / 7D-5) ──────────────────────────

class DesignBriefingOut(BaseModel):
    """Read before designing. Served without an attempt existing, so opening
    it never burns a retry."""

    mission_id: UUID
    mission_title: str
    mission_summary: str | None = None
    variant_id: UUID
    variant_label: str
    points: int
    what_is_a_budget: str
    step_order: list[dict]
    limits: list[dict]
    cubesat_sizes: list[dict]
    budgets: list[dict]
    assumptions: list[str]


class DesignHandbookOut(BaseModel):
    """The Design Handbook — open while designing, disclosure scaled by
    variant exactly as the operate mission's Ops Handbook is."""

    disclosure: str
    what_is_a_budget: str
    step_order: list[dict]
    budgets: list[dict]
    data_types: list[dict]
    mistakes: list[dict]
    assumptions: list[str]


# ── Component library administration (Design v2, 7D-7) ──────────────────

class LibraryComponentBase(BaseModel):
    component_name: str | None = None
    subsystem: str | None = None
    tag: str | None = None
    example_role: str | None = None
    scaled_description: str | None = None
    length_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    scaled_mass_g: float | None = None
    voltage_v: float | None = None
    current_ma: float | None = None
    data_size: str | None = None
    assumed_cost_usd: float | None = None
    temperature_range: str | None = None
    key_specs: str | None = None
    component_code: str | None = None
    datasheet_url: str | None = None
    notes: str | None = None


class LibraryComponentCreateIn(LibraryComponentBase):
    component_name: str
    subsystem: str


class LibraryComponentUpdateIn(LibraryComponentBase):
    is_active: bool | None = None


class LibraryComponentAdminOut(LibraryComponentBase):
    id: UUID
    component_name: str
    subsystem: str
    is_active: bool
    image_url: str | None = None
    updated_at: datetime | None = None
    updated_by_name: str | None = None
    # How many designs have ever added this. Retiring is safe at any count;
    # this is here so an editor can see the blast radius of a *spec change*
    # before making one.
    used_in_designs: int = 0


class LibraryBulkImportIn(BaseModel):
    components: list[LibraryComponentCreateIn]


class LibraryBulkImportOut(BaseModel):
    created: int
    updated: int
    errors: list[str] = []
