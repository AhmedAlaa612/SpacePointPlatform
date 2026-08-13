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
  updated_at: string | null;
  updated_by_name: string | null;
  /** How many designs have ever added this — the blast radius of a spec edit. */
  used_in_designs: number;
}

export type LibraryComponentInput = Partial<Omit<LibraryComponentAdmin,
  "id" | "is_active" | "image_url" | "updated_at" | "updated_by_name" | "used_in_designs">> & {
  component_name: string;
  subsystem: string;
};

export const SUBSYSTEMS = ["ADCS", "CDHS", "EPS", "COMMS", "Payload", "Structure", "Thermal"] as const;

export async function listLibrary(params?: { subsystem?: string; search?: string }): Promise<LibraryComponentAdmin[]> {
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

export async function bulkImportLibrary(
  components: LibraryComponentInput[],
): Promise<{ created: number; updated: number; errors: string[] }> {
  const { data } = await api.post("/missions/library/bulk", { components });
  return data;
}
