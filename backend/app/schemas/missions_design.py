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

from pydantic import BaseModel, Field, model_validator


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
    # `datasheet_url` is only ever populated here when there's no uploaded
    # file to protect — an external link with nothing we can do about its
    # download-ability anyway. Once `has_datasheet_file` is true, this stays
    # None; the frontend calls the datasheet-url endpoint on demand instead
    # of holding a downloadable link in this list payload.
    datasheet_url: str | None = None
    has_datasheet_file: bool = False


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
    # Same DB-protecting ceiling as the budget-entry quantity fields above —
    # DesignComponent.quantity is also a 32-bit Integer.
    quantity: int = Field(default=1, ge=0, le=1_000_000)


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
    # Both capped to match DesignDataBudgetEntry's DB columns
    # (String(60)/String(12)) — same unbounded-string-into-fixed-column
    # bug as CostEntrySaveIn.purchase_link below, just on this table.
    data_type: str | None = Field(default=None, max_length=60)
    data_size_per_measurement_kb: float = 0.0
    measurements_per_minute: float = 0.0
    priority: str = Field(default="Medium", max_length=12)
    storage_mode: Literal["Stored", "Sent", "Both"] = "Stored"
    notes: str | None = None


class PowerEntrySaveIn(BaseModel):
    voltage_v: float | None = None
    current_ma: float | None = None
    notes: str | None = None


class MassEntrySaveIn(BaseModel):
    # DB-protecting ceiling, same reasoning as DesignUpdateIn.selected_solar_cells
    # — the column is a 32-bit Integer, no real design touches this range.
    quantity: int | None = Field(default=None, ge=0, le=1_000_000)
    mass_per_unit_g: float | None = None
    length_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    notes: str | None = None


class CostEntrySaveIn(BaseModel):
    quantity: int | None = Field(default=None, ge=0, le=1_000_000)
    cost_per_unit_aed: float | None = None
    # vendor/priority capped to match DesignCostBudgetEntry's DB columns
    # (String(80)/String(12)) — same class of bug as purchase_link below.
    vendor: str | None = Field(default=None, max_length=80)
    priority: str | None = Field(default=None, max_length=12)
    # Matches DesignCostBudgetEntry.purchase_link's DB column (String(512))
    # — a pasted marketplace/tracking URL over that length used to sail
    # past validation and crash the save at the driver layer
    # (StringDataRightTruncationError -> 500) instead of a clean 400.
    purchase_link: str | None = Field(default=None, max_length=512)
    notes: str | None = None


class LinkEntrySaveIn(BaseModel):
    # Matches DesignLinkBudgetEntry.band_profile's DB column (String(12)).
    band_profile: str = Field(default="UHF", max_length=12)
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
    # design_name/orbit_type/poster_url capped to match Design's DB columns
    # (String(128)/String(20)/String(512)) — design_objective is a DB Text
    # column (unbounded), so it's deliberately left uncapped here too.
    design_name: str | None = Field(default=None, max_length=128)
    design_objective: str | None = None
    orbit_type: str | None = Field(default=None, max_length=20)
    orbit_duration_min: float | None = None
    orbits_per_day: float | None = None
    selected_cubesat_size: Literal["1U", "2U", "3U", "6U"] | None = None
    # No real CubeSat design gets anywhere near 100,000 cells — this is a
    # DB-protecting ceiling, not a domain constraint. Without it a huge
    # pasted/typed value sailed past validation and only failed at the
    # driver layer (OverflowError against the Integer column) -> 500.
    selected_solar_cells: int | None = Field(default=None, ge=0, le=100_000)
    battery_capacity_wh: float | None = None
    poster_url: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def _no_explicit_null_on_required_columns(self):
        """design_name/selected_cubesat_size/selected_solar_cells back
        NOT NULL Design columns — Optional here only so a partial PATCH can
        omit them (update_design uses model_dump(exclude_unset=True)).
        Omission is fine; an *explicit* null isn't excluded by that, and
        used to sail through setattr straight into a NOT NULL column,
        crashing at the driver layer (IntegrityError) -> 500."""
        for field in ("design_name", "selected_cubesat_size", "selected_solar_cells"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be set to null")
        return self


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
    # 2026-08-17 — whether "downlink" (a derived, non-selectable check)
    # currently counts toward all_valid for this attempt's cohort scope —
    # true whenever data_budget/link_budget/conops are all included.
    downlink_included: bool = True
    conops: ConopsSummaryOut
    data: DataBudgetSummaryOut
    power: PowerBudgetSummaryOut
    mass: MassBudgetSummaryOut
    cost: CostBudgetSummaryOut
    link: LinkBudgetSummaryOut
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
    # Poster/Canva (August Build Brief, Branch 3). poster_template_url is
    # resolved from the attempt's cohort (None outside any cohort);
    # poster_url is the team's own working-copy link, editable until the
    # cohort's ends_on passes.
    poster_template_url: str | None = None
    poster_url: str | None = None

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
    # 2026-08-17 — step_key -> included, the 8 selectable DESIGN_STEP_LABELS
    # keys (never "downlink" — it's a derived check, not a tab). An attempt
    # outside any cohort (or a cohort with no selection configured) reads
    # all True — compositional scope, distinct from step_gates' temporal
    # pacing. Drives DesignMissionPage.tsx's tab list (steps are removed
    # entirely, not just blocked).
    included_steps: dict[str, bool] = {}
    # 2026-09 — step keys the student has explicitly confirmed via
    # "Complete this step" (POST .../steps/{step_key}/confirm). Never
    # includes "report" — that step stays purely validity-driven. Drives
    # DesignMissionPage.tsx's per-step Complete button/checkmark instead of
    # the old client-only localStorage flag.
    confirmed_steps: list[str] = []


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
    has_datasheet_file: bool = False
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
