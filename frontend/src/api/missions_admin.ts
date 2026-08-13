/** Missions admin API (P5-4) — thin wrapper over `/missions/admin`. */
import { api } from "@/api/client";

export interface MissionAdminOption {
  id: string;
  title: string;
}

export const listMissionsAdminApi = () =>
  api.get<MissionAdminOption[]>("/missions/admin").then((r) => r.data);

export type MissionKind = "design" | "submission" | "quiz" | "checklist" | "operate" | "external";
export type MissionTeamPolicy = "solo" | "team" | "either";
export type MissionStatus = "draft" | "in_review" | "published" | "archived";
export type MissionAccessMode = "open" | "invite";

export interface MissionVariantAdmin {
  id: string;
  label: string;
  position: number;
  points: number;
  config: Record<string, unknown>;
}

export interface MissionAdmin {
  id: string;
  title: string;
  slug: string;
  summary: string | null;
  description: string | null;
  kind: MissionKind;
  team_policy: MissionTeamPolicy;
  status: MissionStatus;
  access_mode: MissionAccessMode;
  track: string | null;
  image_url: string | null;
  authored_by: string;
  authored_by_name: string | null;
  reviewed_by: string | null;
  created_at: string | null;
  variants: MissionVariantAdmin[];
}

export interface MissionUpdateIn {
  status?: MissionStatus;
  title?: string;
  summary?: string;
  description?: string;
  access_mode?: MissionAccessMode;
  team_policy?: MissionTeamPolicy;
  track?: string;
}

/** Full rows (status, kind, variants, ...) for the ops mission list —
 * same endpoint `listMissionsAdminApi` uses, kept separate so the
 * prerequisites picker's narrow type doesn't have to change shape. */
export const listMissionsAdminFullApi = () =>
  api.get<MissionAdmin[]>("/missions/admin").then((r) => r.data);

export const getMissionAdminApi = (id: string) =>
  api.get<MissionAdmin>(`/missions/admin/${id}`).then((r) => r.data);

export const updateMissionAdminApi = (id: string, data: MissionUpdateIn) =>
  api.patch<MissionAdmin>(`/missions/admin/${id}`, data).then((r) => r.data);

export const deleteMissionAdminApi = (id: string) =>
  api.delete<void>(`/missions/admin/${id}`).then((r) => r.data);

// ── mission assignment (2026-08-12) ─────────────────────────────────────────

export interface MissionAssignment {
  id: string;
  user_id: string;
  user_name: string;
  user_email: string;
  mission_id: string;
  source: string;
  status: string;
  granted_by: string | null;
  created_at: string | null;
}

export interface MissionBulkAssignResult {
  granted: number;
  already_assigned: number;
}

export const listMissionRosterApi = (missionId: string) =>
  api.get<MissionAssignment[]>(`/missions/admin/${missionId}/roster`).then((r) => r.data);

export const grantMissionAssignmentApi = (missionId: string, userId: string) =>
  api.post<MissionAssignment>(`/missions/admin/${missionId}/assignments`, { user_id: userId }).then((r) => r.data);

export const bulkGrantMissionAssignmentApi = (missionId: string, role: string) =>
  api.post<MissionBulkAssignResult>(`/missions/admin/${missionId}/assignments/bulk`, { role }).then((r) => r.data);

export const revokeMissionAssignmentApi = (assignmentId: string) =>
  api.post<MissionAssignment>(`/missions/admin/assignments/${assignmentId}/revoke`).then((r) => r.data);
