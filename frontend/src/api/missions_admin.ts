/** Missions admin API (P5-4) — thin wrapper over `/missions/admin`. Only
 * the fields the prerequisites picker (7B-2) needs; the full authoring
 * surface for missions is still seed-script only, no admin UI yet. */
import { api } from "@/api/client";

export interface MissionAdminOption {
  id: string;
  title: string;
}

export const listMissionsAdminApi = () =>
  api.get<MissionAdminOption[]>("/missions/admin").then((r) => r.data);
