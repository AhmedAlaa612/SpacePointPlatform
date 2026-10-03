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
  /** Only set when there's no uploaded file — an external link (Google
   *  Drive, a manufacturer's site) with nothing to do about its
   *  download-ability. When `has_datasheet_file` is true, this is null and
   *  `getComponentDatasheetUrlApi` resolves the actual URL on demand. */
  datasheet_url: string | null;
  has_datasheet_file: boolean;
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
  /** Null for student custom parts (is_custom) — exactly one of the two IDs is set. */
  library_component_id: string | null;
  custom_component_id: string | null;
  is_custom: boolean;
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
  /** Custom-spec snapshot — only set when is_custom is true. */
  purpose_function: string | null;
  pins_used: string | null;
  measurement_output: string | null;
  measurement_range: string | null;
  /** Server-computed at snapshot time (voltage_v * current_ma). */
  power_computed_mw: number | null;
  datasheet_reference: string | null;
  on_mode_ids: string[];
  data_entry: DesignDataEntry | null;
  power_entry: DesignPowerEntry | null;
  mass_entry: DesignMassEntry | null;
  cost_entry: DesignCostEntry | null;
}

/** A student-defined custom part — visible only to its own attempt (+ ops).
 * Power is derived read-only (voltage_v * current_ma); cost is AED direct. */
export interface DesignCustomComponent {
  id: string;
  attempt_id: string;
  component_name: string;
  subsystem: string;
  purpose_function: string;
  voltage_v: number;
  current_ma: number;
  power_computed_mw: number;
  pins_used: string;
  measurement_output: string;
  measurement_range: string | null;
  datasheet_reference: string | null;
  mass_g: number;
  length_mm: number;
  width_mm: number;
  height_mm: number;
  cost_aed: number;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface DesignCustomComponentCreate {
  component_name: string;
  subsystem: string;
  purpose_function: string;
  voltage_v: number;
  current_ma: number;
  pins_used: string;
  measurement_output: string;
  measurement_range?: string | null;
  datasheet_reference?: string | null;
  mass_g: number;
  length_mm: number;
  width_mm: number;
  height_mm: number;
  cost_aed: number;
  quantity?: number;
}

export const CUSTOM_SUBSYSTEMS = ["ADCS", "CDHS", "EPS", "COMMS", "Payload", "Structure", "Thermal"];

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
  /** 2026-08-17 — whether the hidden Downlink cross-check currently counts
   * toward all_valid (true when data_budget/link_budget/conops are all
   * in the cohort's selected subset). */
  downlink_included: boolean;
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
  /** 2026-08-17 — step_key -> included, the 8 selectable steps (never
   * "downlink"). Compositional scope, distinct from step_gates' temporal
   * pacing — an attempt outside any cohort (or an unconfigured cohort)
   * reads all true. Drives which tabs even appear, not just whether
   * they're blocked. */
  included_steps: Record<string, boolean>;
  /** 2026-09 — step keys the student has explicitly confirmed via "Complete
   * this step" (`confirmDesignStep`). Never includes "report" — that step
   * stays purely validity-driven. Persisted server-side, replacing the
   * old client-only localStorage flag. */
  confirmed_steps: string[];
  /** Ops-set once per cohort — null outside any cohort (or when unset). */
  poster_template_url: string | null;
  /** The team's own working-copy link — editable until the cohort ends. */
  poster_url: string | null;
}

/** The 4-prompt guided objective, concatenated into one `design_objective`
 * string — matching legacy Madar's "Requirement Form" (mission.html), which
 * consistently got better answers than a single blank textarea. Shared
 * between `DesignBriefingPage` (pre-attempt) and `DesignMissionPage`'s Setup
 * tab (2026-08-24 — program-linked mission runs skip the briefing page
 * entirely, since their attempt is created eagerly at assignment time, so
 * Setup has to be able to collect the same questions on its own). */
export const OBJECTIVE_PROMPTS: { key: string; label: string; placeholder: string }[] = [
  { key: "primary", label: "The satellite shall achieve the primary mission objective of:", placeholder: "e.g. capturing daily imagery of the UAE coastline" },
  { key: "success", label: "The mission is successful if the satellite is able to:", placeholder: "e.g. downlink at least one usable image per day for 30 days" },
  { key: "lifetime", label: "The satellite shall operate for a minimum duration of:", placeholder: "e.g. 6 months" },
  { key: "conops", label: "The satellite shall perform its mission tasks by:", placeholder: "e.g. imaging in sunlight, downlinking over the ground station pass" },
];

export function joinObjectivePrompts(values: Record<string, string>): string {
  return OBJECTIVE_PROMPTS.map((p) => `${p.label} ${(values[p.key] ?? "").trim()}`).join("\n\n");
}

/** Splits a `design_objective` string back into its 4 prompts for editing.
 * Falls back to putting the whole thing in `primary` when it doesn't match
 * the guided format (legacy freeform text, or a program run's blank
 * server-set default) so nothing already saved is silently dropped. */
export function parseObjectivePrompts(objective: string | null): Record<string, string> {
  const values: Record<string, string> = {};
  if (!objective) return values;
  for (const chunk of objective.split("\n\n")) {
    const match = OBJECTIVE_PROMPTS.find((p) => chunk.startsWith(p.label));
    if (match) values[match.key] = chunk.slice(match.label.length).trim();
  }
  if (Object.keys(values).length === 0 && objective.trim()) {
    values.primary = objective.trim();
  }
  return values;
}

export async function fetchDesignState(attemptId: string): Promise<DesignState> {
  const { data } = await api.get<DesignState>(`/missions/design/attempts/${attemptId}`);
  return data;
}

export async function fetchDesignLibrary(params?: { subsystem?: string; search?: string; attemptId?: string }): Promise<DesignLibraryComponent[]> {
  const queryParams: Record<string, string> = {};
  if (params?.subsystem) queryParams.subsystem = params.subsystem;
  if (params?.search) queryParams.search = params.search;
  if (params?.attemptId) queryParams.attempt_id = params.attemptId;
  const { data } = await api.get<DesignLibraryComponent[]>("/missions/design/library", { params: queryParams });
  return data;
}

/** Resolved fresh per view, same posture as the LMS attachment viewer and
 *  the instructor library's own datasheet fix — never embedded in the list
 *  above for a hosted PDF. */
export async function fetchComponentDatasheetUrl(componentId: string): Promise<string> {
  const { data } = await api.get<{ url: string }>(`/missions/design/library/${componentId}/datasheet-url`);
  return data.url;
}

export async function updateDesign(attemptId: string, body: Partial<{
  design_name: string; design_objective: string; orbit_type: string;
  orbit_duration_min: number; orbits_per_day: number;
  selected_cubesat_size: string; selected_solar_cells: number;
  battery_capacity_wh: number; poster_url: string;
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

/** Re-add an already-defined custom part to the cart (e.g. after removing
 * it) — same endpoint as library picks, with the custom id instead. */
export async function addCustomComponentToDesign(attemptId: string, customComponentId: string, quantity = 1): Promise<DesignState> {
  const { data } = await api.post<DesignState>(`/missions/design/attempts/${attemptId}/components`, {
    custom_component_id: customComponentId, quantity,
  });
  return data;
}

export async function fetchCustomComponents(attemptId: string): Promise<DesignCustomComponent[]> {
  const { data } = await api.get<DesignCustomComponent[]>(`/missions/design/attempts/${attemptId}/custom-components`);
  return data;
}

/** Define a custom part and place it in the design in one step. */
export async function createCustomComponent(attemptId: string, body: DesignCustomComponentCreate): Promise<DesignState> {
  const { data } = await api.post<DesignState>(`/missions/design/attempts/${attemptId}/custom-components`, body);
  return data;
}

export async function updateCustomComponent(
  attemptId: string, customComponentId: string, body: Partial<DesignCustomComponentCreate>,
): Promise<DesignCustomComponent> {
  const { data } = await api.patch<DesignCustomComponent>(
    `/missions/design/attempts/${attemptId}/custom-components/${customComponentId}`, body,
  );
  return data;
}

export async function deleteCustomComponent(attemptId: string, customComponentId: string): Promise<void> {
  await api.delete(`/missions/design/attempts/${attemptId}/custom-components/${customComponentId}`);
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

/** Self-check for one design-phase step (2026-09) — "Complete this step" in
 * DesignMissionPage.tsx. The backend re-validates the step's own
 * requirements and 400s if they aren't met yet, matching the disabled
 * Complete button here — this is the enforcement, not just a UI nicety. */
export async function confirmDesignStep(attemptId: string, stepKey: string): Promise<DesignState> {
  const { data } = await api.post<DesignState>(`/missions/design/attempts/${attemptId}/steps/${stepKey}/confirm`);
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
