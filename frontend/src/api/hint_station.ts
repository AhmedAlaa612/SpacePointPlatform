import { api } from "@/api/client";

export interface CohortHintCard {
  id: string;
  challenge_id: string;
  level: number;
  level_label: string;
  badge_label?: string | null;
  title: string;
  teaser?: string | null;
  revealed_content?: string | null;
  point_deduction: number;
  unlock_order: number;
  position: number;
  created_at?: string | null;
  is_revealed: boolean;
  is_locked: boolean;
  revealed_at?: string | null;
  revealed_by_name?: string | null;
}

export interface CohortHintChallenge {
  id: string;
  owner_type: "program" | "cohort";
  owner_id: string;
  title: string;
  challenge_code?: string | null;
  topic?: string | null;
  description: string;
  mission_statement?: string | null;
  max_points: number;
  position: number;
  is_active: boolean;
  created_at?: string | null;
  cards: CohortHintCard[];
  points_deducted: number;
  max_remaining_points: number;
}

export interface StudentHintStationData {
  cohort_id?: string | null;
  cohort_name?: string | null;
  program_id?: string | null;
  program_name?: string | null;
  team_id?: string | null;
  team_name?: string | null;
  is_active: boolean;
  challenges: CohortHintChallenge[];
  total_hints_revealed: number;
  total_points_deducted: number;
  can_switch_to_judge_view: boolean;
}

export interface HintRevealAudit {
  id: string;
  challenge_id: string;
  challenge_title: string;
  hint_card_id: string;
  level: number;
  level_label: string;
  card_title: string;
  points_deducted: number;
  revealed_at: string;
  revealed_by_name?: string | null;
}

export interface TeamHintJudgingSummary {
  team_id: string;
  team_name: string;
  team_code?: string | null;
  hints_used: number;
  total_points_deducted: number;
  reveals: HintRevealAudit[];
}

export interface IndividualHintJudgingSummary {
  user_id: string;
  user_name: string;
  user_email?: string | null;
  hints_used: number;
  total_points_deducted: number;
  reveals: HintRevealAudit[];
}

export interface CohortHintJudgingSummary {
  cohort_id: string;
  cohort_name?: string | null;
  total_hints_revealed: number;
  total_points_deducted: number;
  teams: TeamHintJudgingSummary[];
  individuals: IndividualHintJudgingSummary[];
}

// ── Student Surface ─────────────────────────────────────────────────────────

export const getProgramHintsApi = (assignmentId: string) =>
  api.get<StudentHintStationData>(`/lms/programs/${assignmentId}/hints`).then((r) => r.data);

export const revealHintCardApi = (assignmentId: string, cardId: string) =>
  api.post<CohortHintCard>(`/lms/programs/${assignmentId}/hints/${cardId}/reveal`).then((r) => r.data);

// ── Ops & Authoring Surface ────────────────────────────────────────────────

export const listProgramChallengesAdminApi = (programId: string) =>
  api.get<CohortHintChallenge[]>(`/lms/admin/hints/program/${programId}`).then((r) => r.data);

export const listCohortChallengesAdminApi = (cohortId: string) =>
  api.get<CohortHintChallenge[]>(`/lms/admin/hints/cohort/${cohortId}`).then((r) => r.data);

export const forkCohortChallengesAdminApi = (cohortId: string) =>
  api.post<CohortHintChallenge[]>(`/lms/admin/hints/cohort/${cohortId}/fork`).then((r) => r.data);

export const createHintChallengeApi = (data: {
  owner_type: "program" | "cohort";
  owner_id: string;
  title: string;
  challenge_code?: string | null;
  topic?: string | null;
  description: string;
  mission_statement?: string | null;
  max_points?: number;
  position?: number;
  is_active?: boolean;
}) => api.post<CohortHintChallenge>("/lms/admin/hints/challenges", data).then((r) => r.data);

export const updateHintChallengeApi = (
  challengeId: string,
  data: Partial<CohortHintChallenge>,
) => api.put<CohortHintChallenge>(`/lms/admin/hints/challenges/${challengeId}`, data).then((r) => r.data);

export const deleteHintChallengeApi = (challengeId: string) =>
  api.delete<{ id: string; deleted: boolean }>(`/lms/admin/hints/challenges/${challengeId}`).then((r) => r.data);

export const createHintCardApi = (
  challengeId: string,
  data: {
    level: number;
    level_label: string;
    badge_label?: string | null;
    title: string;
    teaser?: string | null;
    revealed_content: string;
    point_deduction?: number;
    unlock_order?: number;
    position?: number;
  },
) => api.post<CohortHintCard>(`/lms/admin/hints/challenges/${challengeId}/cards`, data).then((r) => r.data);

export const updateHintCardApi = (
  cardId: string,
  data: Partial<CohortHintCard>,
) => api.put<CohortHintCard>(`/lms/admin/hints/cards/${cardId}`, data).then((r) => r.data);

export const deleteHintCardApi = (cardId: string) =>
  api.delete<{ id: string; deleted: boolean }>(`/lms/admin/hints/cards/${cardId}`).then((r) => r.data);

export const importCohortHintsAdminApi = (
  cohortId: string,
  data: {
    source_type: "program" | "cohort";
    source_id: string;
    challenge_ids?: string[];
    replace_existing?: boolean;
  },
) => api.post<{ cloned_count: number }>(`/lms/admin/hints/cohort/${cohortId}/import`, data).then((r) => r.data);

export const importProgramHintsAdminApi = (
  programId: string,
  data: {
    source_type: "program" | "cohort";
    source_id: string;
    challenge_ids?: string[];
    replace_existing?: boolean;
  },
) => api.post<{ cloned_count: number }>(`/lms/admin/hints/program/${programId}/import`, data).then((r) => r.data);

// ── Judging & Operations Surface ───────────────────────────────────────────

export const getCohortHintJudgingSummaryApi = (cohortId: string) =>
  api.get<CohortHintJudgingSummary>(`/competitions/cohorts/${cohortId}/hints/judging-summary`).then((r) => r.data);

export const getTeamHintSummaryApi = (teamId: string) =>
  api.get<TeamHintJudgingSummary>(`/competitions/teams/${teamId}/hints`).then((r) => r.data);

export const resetTeamHintRevealsApi = (cohortId: string, teamId: string) =>
  api.post<{ team_id: string; deleted_reveals_count: number }>(
    `/competitions/cohorts/${cohortId}/hints/teams/${teamId}/reset`,
  ).then((r) => r.data);

export const resetUserHintRevealsApi = (cohortId: string, userId: string) =>
  api.post<{ user_id: string; deleted_reveals_count: number }>(
    `/competitions/cohorts/${cohortId}/hints/users/${userId}/reset`,
  ).then((r) => r.data);
