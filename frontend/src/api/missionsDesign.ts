/** Design mission API (P7-5) — thin wrappers over `/missions/design/*`.
 * Types mirror `schemas/missions_design.py` field for field.
 */
import { api } from "./client";

export interface DesignLibraryComponent {
  id: string;
  component_name: string;
  subsystem: string;
  tag: string | null;
  example_role: string | null;
  scaled_description: string | null;
  length_mm: number | null;
  width_mm: number | null;
  height_mm: number | null;
  scaled_mass_g: number | null;
  voltage_v: number | null;
  current_ma: number | null;
  data_size: string | null;
  assumed_cost_usd: number | null;
  temperature_range: string | null;
  key_specs: string | null;
  image_url: string | null;
  component_code: string | null;
  datasheet_url: string | null;
}

export interface DesignDataEntry {
  data_type: string | null;
  data_size_per_measurement_kb: number;
  measurements_per_minute: number;
  priority: string;
  storage_mode: "Stored" | "Sent" | "Both";
  notes: string | null;
}

export interface DesignPowerEntry {
  voltage_v: number | null;
  current_ma: number | null;
  notes: string | null;
}

export interface DesignMassEntry {
  quantity: number | null;
  mass_per_unit_g: number | null;
  length_mm: number | null;
  width_mm: number | null;
  height_mm: number | null;
  notes: string | null;
}

export interface DesignCostEntry {
  quantity: number | null;
  cost_per_unit_aed: number | null;
  vendor: string | null;
  priority: string | null;
  purchase_link: string | null;
  notes: string | null;
}

export interface DesignComponent {
  id: string;
  library_component_id: string;
  component_name: string;
  subsystem: string;
  image_url: string | null;
  quantity: number;
  mass_per_unit_g: number | null;
  length_mm: number | null;
  width_mm: number | null;
  height_mm: number | null;
  voltage_v: number | null;
  current_ma: number | null;
  cost_per_unit_aed: number | null;
  on_mode_ids: string[];
  data_entry: DesignDataEntry | null;
  power_entry: DesignPowerEntry | null;
  mass_entry: DesignMassEntry | null;
  cost_entry: DesignCostEntry | null;
}

export interface DesignMode {
  id: string;
  mode_name: string;
  position: number;
  duration_min: number;
  description: string | null;
}

export interface LinkEntry {
  band_profile: string;
  downlink_frequency_mhz: number;
  uplink_frequency_mhz: number;
  satellite_antenna_gain_dbi: number;
  data_rate_kbps: number;
  required_signal_quality_db: number;
  notes: string | null;
  is_saved: boolean;
}

export interface CubeSatPreset {
  size: string;
  available_volume_cm3: number;
  max_mass_kg: number;
}

export interface BandPreset {
  downlink_frequency_mhz: number;
  uplink_frequency_mhz: number;
  satellite_antenna_gain_dbi: number;
  data_rate_kbps: number;
  required_signal_quality_db: number;
}

export interface StepStatus {
  has_data: boolean;
  is_valid: boolean;
}

export interface Dashboard {
  all_valid: boolean;
  steps: Record<string, StepStatus>;
  conops: { total_mode_duration_min: number; duration_difference_min: number };
  data: {
    total_per_orbit_kb: number; total_per_day_kb: number; total_stored_per_day_kb: number;
    total_sent_per_day_kb: number; storage_remaining_kb: number; max_storage_kb: number;
    required_storage_margin_kb: number;
  };
  power: {
    total_power_mw: number; total_energy_per_orbit_mwh: number; total_energy_per_day_mwh: number;
    power_margin_mw: number; required_solar_cells: number; generated_power_mw: number;
    selected_solar_cells: number; power_per_solar_cell_w: number;
  };
  mass: {
    total_mass_kg: number; mass_margin_kg: number; total_volume_cm3: number;
    volume_margin_cm3: number; max_allowed_mass_kg: number; available_internal_volume_cm3: number;
  };
  cost: { total_cost_aed: number; cost_margin_aed: number; maximum_budget_aed: number };
  link: {
    margin_db: number; status: string;
    good_threshold_db: number; weak_threshold_db: number;
    assumed_distance_km: number; transmit_power_dbm: number;
  };
  /** Design v2 (7D-2, F8/D4) — energy over a whole orbit, and the battery. */
  energy: {
    sunlit_minutes: number; eclipse_minutes: number;
    generated_per_orbit_mwh: number; consumed_per_orbit_mwh: number;
    energy_margin_mwh: number; energy_balance_ok: boolean;
    eclipse_draw_mwh: number; battery_capacity_mwh: number;
    depth_of_discharge_pct: number; max_depth_of_discharge_pct: number; depth_of_discharge_ok: boolean;
  };
  /** Design v2 (7D-2, F7) — can you actually get the data down? */
  downlink: {
    data_to_downlink_per_orbit_kb: number; downlink_capacity_per_orbit_kb: number;
    downlink_margin_kb: number; contact_minutes: number; utilisation_pct: number;
  };
  /** Design v2 (7D-3) — the payoff screen Madar had and the port dropped. */
  overall: { label: string; all_valid: boolean; errors: number; warnings: number; incomplete: number };
  kpis: Record<string, number>;
  margins: MarginRow[];
  module_cards: ModuleCard[];
  charts: DesignCharts;
  alerts: DesignAlert[];
  recommendations: Recommendation[];
}

export type MarginStatus = "good" | "tight" | "fail" | "incomplete";

export interface MarginRow {
  key: string;
  label: string;
  value: number;
  unit: string;
  status: MarginStatus;
  interpretation: string;
}

export interface ModuleCard {
  key: string;
  title: string;
  status: MarginStatus;
  kpi1_label: string;
  kpi1_value: string;
  kpi2_label: string;
  kpi2_value: string;
  tab: string;
}

export interface DesignAlert {
  severity: "error" | "warning" | "info" | "success";
  step: string | null;
  message: string;
}

export interface Recommendation {
  key: string;
  title: string;
  message: string;
  why: string;
}

export interface DesignCharts {
  power_by_subsystem: { subsystem: string; value: number }[];
  mass_by_subsystem: { subsystem: string; value: number }[];
  cost_by_subsystem: { subsystem: string; value: number }[];
  mode_distribution: { mode_name: string; duration_min: number }[];
}

export interface DesignState {
  id: string;
  attempt_id: string;
  mission_id: string;
  variant_id: string;
  variant_label: string;
  attempt_status: "in_progress" | "submitted" | "passed" | "failed" | "abandoned";
  design_name: string;
  design_objective: string | null;
  orbit_type: string | null;
  orbit_duration_min: number | null;
  orbits_per_day: number | null;
  selected_cubesat_size: string;
  selected_solar_cells: number;
  battery_capacity_wh: number | null;
  created_at: string | null;
  components: DesignComponent[];
  modes: DesignMode[];
  link_entry: LinkEntry | null;
  cubesat_presets: CubeSatPreset[];
  band_presets: Record<string, BandPreset>;
  dashboard: Dashboard;
  /** F9 — what this teaching model simplifies, stated rather than hidden. */
  assumptions: string[];
  /** 2026-08-17 — step_key -> is_unlocked, all 9 steps. An attempt outside
   * any cohort (or a cohort with no gates set) reads all true. */
  step_gates: Record<string, boolean>;
}

export async function fetchDesignState(attemptId: string): Promise<DesignState> {
  const { data } = await api.get<DesignState>(`/missions/design/attempts/${attemptId}`);
  return data;
}

export async function fetchDesignLibrary(params?: { subsystem?: string; search?: string }): Promise<DesignLibraryComponent[]> {
  const { data } = await api.get<DesignLibraryComponent[]>("/missions/design/library", { params });
  return data;
}

export async function updateDesign(attemptId: string, body: Partial<{
  design_name: string; design_objective: string; orbit_type: string;
  orbit_duration_min: number; orbits_per_day: number;
  selected_cubesat_size: string; selected_solar_cells: number;
  battery_capacity_wh: number;
}>): Promise<DesignState> {
  const { data } = await api.patch<DesignState>(`/missions/design/attempts/${attemptId}`, body);
  return data;
}

export async function addDesignComponent(attemptId: string, libraryComponentId: string, quantity = 1): Promise<DesignState> {
  const { data } = await api.post<DesignState>(`/missions/design/attempts/${attemptId}/components`, {
    library_component_id: libraryComponentId, quantity,
  });
  return data;
}

export async function removeDesignComponent(attemptId: string, designComponentId: string): Promise<DesignState> {
  const { data } = await api.delete<DesignState>(`/missions/design/attempts/${attemptId}/components/${designComponentId}`);
  return data;
}

export async function saveConops(
  attemptId: string, modeDurations: Record<string, number>, cellStates: Record<string, Record<string, boolean>>,
): Promise<DesignState> {
  const { data } = await api.post<DesignState>(`/missions/design/attempts/${attemptId}/conops`, {
    mode_durations: modeDurations, cell_states: cellStates,
  });
  return data;
}

export async function saveDataBudget(attemptId: string, componentId: string, body: Partial<DesignDataEntry>): Promise<DesignState> {
  const { data } = await api.post<DesignState>(`/missions/design/attempts/${attemptId}/components/${componentId}/data-budget`, body);
  return data;
}

export async function savePowerBudget(attemptId: string, componentId: string, body: Partial<DesignPowerEntry>): Promise<DesignState> {
  const { data } = await api.post<DesignState>(`/missions/design/attempts/${attemptId}/components/${componentId}/power-budget`, body);
  return data;
}

export async function saveMassBudget(attemptId: string, componentId: string, body: Partial<DesignMassEntry>): Promise<DesignState> {
  const { data } = await api.post<DesignState>(`/missions/design/attempts/${attemptId}/components/${componentId}/mass-budget`, body);
  return data;
}

export async function saveCostBudget(attemptId: string, componentId: string, body: Partial<DesignCostEntry>): Promise<DesignState> {
  const { data } = await api.post<DesignState>(`/missions/design/attempts/${attemptId}/components/${componentId}/cost-budget`, body);
  return data;
}

export async function saveLinkBudget(attemptId: string, body: Omit<LinkEntry, "is_saved">): Promise<DesignState> {
  const { data } = await api.post<DesignState>(`/missions/design/attempts/${attemptId}/link-budget`, body);
  return data;
}

export async function completeDesign(attemptId: string): Promise<DesignState> {
  const { data } = await api.post<DesignState>(`/missions/design/attempts/${attemptId}/complete`);
  return data;
}

// ── Teaching surfaces (Design v2, 7D-4 / 7D-5) ──────────────────────────

export interface DesignBriefing {
  mission_id: string;
  mission_title: string;
  mission_summary: string | null;
  variant_id: string;
  variant_label: string;
  points: number;
  what_is_a_budget: string;
  step_order: { key: string; label: string; detail: string; depends_on: string[] }[];
  limits: { key: string; label: string; value: string; detail: string }[];
  cubesat_sizes: { size: string; max_mass_kg: number; available_volume_cm3: number }[];
  budgets: { key: string; title: string; checks: string; why_it_matters: string }[];
  assumptions: string[];
}

export interface HandbookBudget {
  key: string;
  title: string;
  checks: string;
  formula: string;
  means?: string;
  fails_when?: string;
  why_it_matters?: string;
  fix?: string;
}

export interface HandbookMistake {
  key: string;
  title: string;
  symptom: string;
  steps: string[];
  meaning?: string;
  fix?: string;
}

export interface DesignHandbook {
  disclosure: "full" | "symptoms" | "reference";
  what_is_a_budget: string;
  step_order: { key: string; label: string; detail: string; depends_on: string[] }[];
  budgets: HandbookBudget[];
  data_types: { name: string; detail: string }[];
  mistakes: HandbookMistake[];
  assumptions: string[];
}

export async function fetchDesignBriefing(missionId: string, variantId?: string): Promise<DesignBriefing> {
  const { data } = await api.get<DesignBriefing>(`/missions/design/briefing/${missionId}`, {
    params: variantId ? { variant_id: variantId } : undefined,
  });
  return data;
}

export async function fetchDesignHandbook(attemptId: string): Promise<DesignHandbook> {
  const { data } = await api.get<DesignHandbook>(`/missions/design/attempts/${attemptId}/handbook`);
  return data;
}
