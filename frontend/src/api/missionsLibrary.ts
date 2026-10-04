/** Component library administration (Design v2, 7D-7) — `/missions/library/*`.
 *
 * The catalog is global: it has no mission_id and every design mission
 * reads it. That is why it lives in its own `/lms-authoring` section rather
 * than inside one mission's page, even though (D7) a design-mission
 * manager may edit it as well as staff.
 */
import { api } from "./client";

export interface LibraryComponentAdmin {
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
  component_code: string | null;
  datasheet_url: string | null;
  notes: string | null;
  is_active: boolean;
  image_url: string | null;
  /** Whether the org's own copy is uploaded (served through the no-download
   *  viewer) — as opposed to `datasheet_url` alone, an external link
   *  (Google Drive, a manufacturer's site) we don't host and can't protect. */
  has_datasheet_file: boolean;
  updated_at: string | null;
  updated_by_name: string | null;
  /** How many designs have ever added this — the blast radius of a spec edit. */
  used_in_designs: number;
}

export type LibraryComponentInput = Partial<Omit<LibraryComponentAdmin,
  "id" | "is_active" | "image_url" | "has_datasheet_file" | "updated_at" | "updated_by_name" | "used_in_designs">> & {
  component_name: string;
  subsystem: string;
};

export const SUBSYSTEMS = ["ADCS", "CDHS", "EPS", "COMMS", "Payload", "Structure", "Thermal"] as const;

export async function listLibrary(params?: { subsystem?: string; search?: string; tag?: string }): Promise<LibraryComponentAdmin[]> {
  const { data } = await api.get<LibraryComponentAdmin[]>("/missions/library", { params });
  return data;
}

export async function createLibraryComponent(body: LibraryComponentInput): Promise<LibraryComponentAdmin> {
  const { data } = await api.post<LibraryComponentAdmin>("/missions/library", body);
  return data;
}

export async function updateLibraryComponent(
  id: string, body: Partial<LibraryComponentInput>,
): Promise<LibraryComponentAdmin> {
  const { data } = await api.patch<LibraryComponentAdmin>(`/missions/library/${id}`, body);
  return data;
}

/** Retire or restore. There is no delete — see the router's module docstring. */
export async function setLibraryRetired(id: string, retired: boolean): Promise<LibraryComponentAdmin> {
  const { data } = await api.post<LibraryComponentAdmin>(`/missions/library/${id}/retire`, null, {
    params: { retired },
  });
  return data;
}

export async function uploadLibraryImage(id: string, file: File): Promise<LibraryComponentAdmin> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<LibraryComponentAdmin>(`/missions/library/${id}/image`, form);
  return data;
}

/** Uploads the org's own PDF — supersedes `datasheet_url` server-side, since
 *  a component only ever shows one "Datasheet" affordance at a time. */
export async function uploadLibraryDatasheet(id: string, file: File): Promise<LibraryComponentAdmin> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<LibraryComponentAdmin>(`/missions/library/${id}/datasheet`, form);
  return data;
}

export async function deleteLibraryDatasheet(id: string): Promise<LibraryComponentAdmin> {
  const { data } = await api.delete<LibraryComponentAdmin>(`/missions/library/${id}/datasheet`);
  return data;
}

export async function bulkImportLibrary(
  components: LibraryComponentInput[],
): Promise<{ created: number; updated: number; errors: string[] }> {
  const { data } = await api.post("/missions/library/bulk", { components });
  return data;
}

/** Student-built custom parts (DesignCustomComponent) for the ops explorer.
 * Unlike the shared catalog above, these are per-attempt — owner + program/cohort
 * attribution comes from the backend so ops can tell who built what and where. */
export interface AdminCustomComponent {
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
  image_url: string | null;
  created_at: string | null;
  updated_at: string | null;
  user_id: string | null;
  student_name: string | null;
  student_email: string | null;
  team_id: string | null;
  team_name: string | null;
  cohort_id: string | null;
  cohort_name: string | null;
  program_id: string | null;
  program_name: string | null;
  program_code: string | null;
  mission_id: string | null;
  mission_title: string | null;
}

export async function listAdminCustomComponents(params?: {
  cohort_id?: string;
  mission_id?: string;
  subsystem?: string;
  search?: string;
  user_id?: string;
  is_active?: boolean;
}): Promise<AdminCustomComponent[]> {
  const { data } = await api.get<AdminCustomComponent[]>("/missions/admin/custom-components", { params });
  return data;
}
