/** Mission-manager scoped surface (7B-7) — thin wrapper over
 * `/missions/manager/*`. Types mirror `schemas/missions_manager.py` and
 * the shared `MissionAttemptAdminOut` shape from `schemas/missions_admin.py`. */
import { api } from "@/api/client";

export interface ManagedMission {
  mission_id: string;
  title: string;
}

export interface MissionStatsRow {
  user_id: string;
  full_name: string;
  status: "in_progress" | "submitted" | "passed" | "failed" | "abandoned";
  score: number | null;
  attempt_no: number;
}

export interface MissionStats {
  mission_id: string;
  total_attempts: number;
  total_students: number;
  passed_students: number;
  pass_rate: number;
  rows: MissionStatsRow[];
}

export interface ManagedAttempt {
  id: string;
  mission_id: string;
  mission_title: string;
  variant_id: string;
  variant_label: string;
  user_id: string | null;
  student_name: string | null;
  team_id: string | null;
  team_name: string | null;
  attempt_no: number;
  status: string;
  score: number | null;
  payload: Record<string, unknown>;
  started_at: string | null;
  submitted_at: string | null;
  decided_at: string | null;
}

export const myManagedMissionsApi = () =>
  api.get<ManagedMission[]>("/missions/manager/mine").then((r) => r.data);

export const managedMissionStatsApi = (missionId: string) =>
  api.get<MissionStats>(`/missions/manager/${missionId}/stats`).then((r) => r.data);

export const managedMissionQueueApi = (missionId: string) =>
  api.get<ManagedAttempt[]>(`/missions/manager/${missionId}/queue`).then((r) => r.data);

export const reviewManagedAttemptApi = (
  attemptId: string, data: { passed: boolean; score?: number | null; review_comment?: string | null },
) => api.post<ManagedAttempt>(`/missions/manager/attempts/${attemptId}/review`, data).then((r) => r.data);
