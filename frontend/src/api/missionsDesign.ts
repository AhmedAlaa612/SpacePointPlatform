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
  link: { margin_db: number; status: string };
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
  created_at: string | null;
  components: DesignComponent[];
  modes: DesignMode[];
  link_entry: LinkEntry | null;
  cubesat_presets: CubeSatPreset[];
  band_presets: Record<string, BandPreset>;
  dashboard: Dashboard;
  locked_steps: string[];
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
