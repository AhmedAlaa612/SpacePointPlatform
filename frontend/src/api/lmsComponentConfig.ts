import { api } from "@/api/client";

export interface ComponentItemSummary {
  id: string;
  component_name: string;
  subsystem: string;
  tag: string | null;
  component_code: string | null;
  example_role: string | null;
  scaled_mass_g: number | null;
  voltage_v: number | null;
  current_ma: number | null;
  assumed_cost_usd: number | null;
  image_url: string | null;
  is_active: boolean;
  is_enabled: boolean;
}

export interface ComponentConfigOut {
  owner_type: "program" | "cohort";
  owner_id: string;
  is_inherited: boolean;
  has_override: boolean;
  disabled_subsystems: string[];
  disabled_tags: string[];
  disabled_component_ids: string[];
  available_subsystems: string[];
  available_tags: string[];
  total_components: number;
  enabled_components: number;
  components: ComponentItemSummary[];
  updated_at: string | null;
  updated_by: string | null;
}

export interface ComponentConfigIn {
  disabled_subsystems: string[];
  disabled_tags: string[];
  disabled_component_ids: string[];
}

export async function getProgramComponentsApi(lmsProgramId: string): Promise<ComponentConfigOut> {
  const { data } = await api.get<ComponentConfigOut>(`/lms/admin/programs/${lmsProgramId}/components`);
  return data;
}

export async function updateProgramComponentsApi(
  lmsProgramId: string,
  body: ComponentConfigIn
): Promise<ComponentConfigOut> {
  const { data } = await api.put<ComponentConfigOut>(`/lms/admin/programs/${lmsProgramId}/components`, body);
  return data;
}

export async function resetProgramComponentsApi(lmsProgramId: string): Promise<ComponentConfigOut> {
  const { data } = await api.delete<ComponentConfigOut>(`/lms/admin/programs/${lmsProgramId}/components`);
  return data;
}

export async function getCohortComponentsApi(
  cohortId: string,
  isInstructor = false
): Promise<ComponentConfigOut> {
  const prefix = isInstructor ? "/lms/instructor" : "/lms/admin";
  const { data } = await api.get<ComponentConfigOut>(`${prefix}/cohorts/${cohortId}/components`);
  return data;
}

export async function updateCohortComponentsApi(
  cohortId: string,
  body: ComponentConfigIn,
  isInstructor = false
): Promise<ComponentConfigOut> {
  const prefix = isInstructor ? "/lms/instructor" : "/lms/admin";
  const { data } = await api.put<ComponentConfigOut>(`${prefix}/cohorts/${cohortId}/components`, body);
  return data;
}

export async function resetCohortComponentsApi(
  cohortId: string,
  isInstructor = false
): Promise<ComponentConfigOut> {
  const prefix = isInstructor ? "/lms/instructor" : "/lms/admin";
  const { data } = await api.delete<ComponentConfigOut>(`${prefix}/cohorts/${cohortId}/components`);
  return data;
}
