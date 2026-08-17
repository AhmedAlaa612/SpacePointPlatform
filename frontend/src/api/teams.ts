/** Domain-agnostic team API (2026-08-17) — thin wrappers over `/teams/*`.
 * Generalized out of the missions-only `MissionTeam` type that used to
 * live in `missions.ts`; mission-context creation/listing
 * (`POST /missions/teams`, `GET /missions/teams/mine`) still lives in
 * `missions.ts` and returns this same shape.
 */
import { api } from "./client";

export interface Team {
  id: string;
  name: string;
  cohort_id: string | null;
  member_ids: string[];
  member_names: string[];
}

export async function joinTeam(teamId: string): Promise<Team> {
  const { data } = await api.post<Team>(`/teams/${teamId}/join`);
  return data;
}

export async function leaveTeam(teamId: string): Promise<void> {
  await api.delete(`/teams/${teamId}/leave`);
}
