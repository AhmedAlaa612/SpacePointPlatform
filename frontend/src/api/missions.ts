/** Missions student API (P5-4) — thin wrappers over `/missions/*`. Types
 * mirror `schemas/missions.py` field for field.
 */
import { api } from "./client";

export interface MissionVariantSummary {
  id: string;
  label: string;
  position: number;
  points: number;
}

export type MissionTeamPolicy = "solo" | "team" | "either";

export interface MissionCatalogItem {
  id: string;
  title: string;
  slug: string;
  summary: string | null;
  kind: "design" | "submission" | "quiz" | "checklist" | "operate" | "external";
  track: string | null;
  image_url: string | null;
  variants: MissionVariantSummary[];
  locked: boolean;
  team_policy: MissionTeamPolicy;
}

export interface MissionTeam {
  id: string;
  name: string;
  cohort_id: string | null;
  member_ids: string[];
  member_names: string[];
}

export interface MissionPrerequisite {
  item_type: "course" | "mission";
  item_id: string;
  title: string;
  satisfied: boolean;
}

export interface MissionGraphNode {
  id: string;
  title: string;
  kind: MissionCatalogItem["kind"];
  track: string | null;
  locked: boolean;
  requires: string[];
}

export interface MissionQuizQuestion {
  prompt: string;
  options: { text: string }[];
}

export type MissionVariantConfig =
  | Record<string, never>
  | { pass_threshold: number; questions: MissionQuizQuestion[] };

export interface MissionVariant {
  id: string;
  label: string;
  position: number;
  points: number;
  config: MissionVariantConfig;
}

export interface MissionAttempt {
  id: string;
  mission_id: string;
  variant_id: string;
  variant_label: string;
  attempt_no: number;
  status: "in_progress" | "submitted" | "passed" | "failed" | "abandoned";
  score: number | null;
  payload: Record<string, unknown>;
  started_at: string | null;
  submitted_at: string | null;
  decided_at: string | null;
  team_id: string | null;
  team_name: string | null;
}

export interface MissionDetail {
  id: string;
  title: string;
  slug: string;
  summary: string | null;
  description: string | null;
  kind: MissionCatalogItem["kind"];
  track: string | null;
  image_url: string | null;
  variants: MissionVariant[];
  attempts: MissionAttempt[];
  prerequisites: MissionPrerequisite[];
  locked: boolean;
  team_policy: MissionTeamPolicy;
  my_teams: MissionTeam[];
}

export interface MissionQuizReviewQuestion {
  prompt: string | null;
  selected: number;
  correct: boolean;
  explanation: string | null;
  correct_text: string | null;
}

export interface MissionQuizReview {
  score: number;
  passed: boolean;
  questions: MissionQuizReviewQuestion[];
}

export interface MissionAttemptSubmitResult {
  attempt: MissionAttempt;
  review: MissionQuizReview | null;
}

export async function fetchMissionCatalog(): Promise<MissionCatalogItem[]> {
  const { data } = await api.get<MissionCatalogItem[]>("/missions");
  return data;
}

export async function fetchMissionGraph(): Promise<MissionGraphNode[]> {
  const { data } = await api.get<MissionGraphNode[]>("/missions/graph");
  return data;
}

export async function fetchMission(missionId: string): Promise<MissionDetail> {
  const { data } = await api.get<MissionDetail>(`/missions/${missionId}`);
  return data;
}

export async function startMissionAttempt(
  missionId: string, variantId: string, teamId?: string,
): Promise<MissionAttempt> {
  const { data } = await api.post<MissionAttempt>(`/missions/${missionId}/attempts`, {
    variant_id: variantId, team_id: teamId || null,
  });
  return data;
}

export async function fetchMyTeams(): Promise<MissionTeam[]> {
  const { data } = await api.get<MissionTeam[]>("/missions/teams/mine");
  return data;
}

export async function createTeam(name: string, memberIds: string[] = []): Promise<MissionTeam> {
  const { data } = await api.post<MissionTeam>("/missions/teams", { name, member_ids: memberIds });
  return data;
}

export async function fetchMissionAttempt(attemptId: string): Promise<MissionAttempt> {
  const { data } = await api.get<MissionAttempt>(`/missions/attempts/${attemptId}`);
  return data;
}

export async function submitQuizAttempt(attemptId: string, answers: number[]): Promise<MissionAttemptSubmitResult> {
  const { data } = await api.post<MissionAttemptSubmitResult>(`/missions/attempts/${attemptId}/submit`, { answers });
  return data;
}

export async function submitSubmissionAttempt(
  attemptId: string, artifactUrl: string, notes?: string,
): Promise<MissionAttemptSubmitResult> {
  const { data } = await api.post<MissionAttemptSubmitResult>(`/missions/attempts/${attemptId}/submit`, {
    artifact_url: artifactUrl, notes: notes || null,
  });
  return data;
}
