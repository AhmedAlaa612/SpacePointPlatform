/** Competition judging (2026-08-24) — mirrors backend/app/schemas/competitions.py
 * and the `/competitions/admin/*` + `/competitions/judge/*` routers. */
import { api } from "@/api/client"

export interface CompetitionRubricCriterion {
  key: string
  label: string
  max_points: number
  position: number
}

export interface CompetitionRubric {
  id: string
  program_id: string
  name: string
  criteria: CompetitionRubricCriterion[]
}

export interface CompetitionScore {
  id: string
  team_id: string
  judge_user_id: string
  criterion_scores: Record<string, number>
  bonus_points: number
  total_points: number
  submitted_at: string | null
}

export interface CompetitionLeaderboardRow {
  rank: number
  team_id: string
  team_name: string
  score: number | null
  judges_scored: number
  status: "scored" | "unscored"
}

export interface CompetitionJudge {
  user_id: string
  full_name: string
  email: string
}

export interface CompetitionJudgeProgress extends CompetitionJudge {
  scored_count: number
  team_count: number
}

export interface CompetitionPublication {
  published: boolean
  published_at: string | null
}

export interface CompetitionSubmissionItem {
  item_id: string
  title: string
  item_type: string
  status: string
  submitted_url: string | null
}

export interface CompetitionJudgeCohort {
  id: string
  name: string
  program_name: string
}

export interface CompetitionJudgeTeam {
  id: string
  name: string
  cohort_id: string | null
  member_ids: string[]
  member_names: string[]
  already_scored: boolean
}

export interface CompetitionTeamDetail {
  team: { id: string; name: string; cohort_id: string | null; member_ids: string[]; member_names: string[] }
  submissions: CompetitionSubmissionItem[]
  rubric: CompetitionRubric | null
  own_score: CompetitionScore | null
}

// ── Ops admin ────────────────────────────────────────────────────────────

export const getProgramRubricApi = (programId: string) =>
  api.get<CompetitionRubric>(`/competitions/admin/programs/${programId}/rubric`).then((r) => r.data)

export const putProgramRubricApi = (
  programId: string,
  data: { name: string; criteria: { key: string; label: string; max_points: number }[] },
) => api.put<CompetitionRubric>(`/competitions/admin/programs/${programId}/rubric`, data).then((r) => r.data)

export const getCohortJudgesApi = (cohortId: string) =>
  api.get<CompetitionJudgeProgress[]>(`/competitions/admin/cohorts/${cohortId}/judges`).then((r) => r.data)

export const inviteCohortJudgeApi = (cohortId: string, data: { name: string; email: string }) =>
  api.post<CompetitionJudge>(`/competitions/admin/cohorts/${cohortId}/judges`, data).then((r) => r.data)

export const revokeCohortJudgeApi = (cohortId: string, userId: string) =>
  api.delete<void>(`/competitions/admin/cohorts/${cohortId}/judges/${userId}`).then((r) => r.data)

export const getCohortLeaderboardApi = (cohortId: string) =>
  api.get<CompetitionLeaderboardRow[]>(`/competitions/admin/cohorts/${cohortId}/leaderboard`).then((r) => r.data)

export const getCohortExportTop20Api = (cohortId: string) =>
  api.get<CompetitionLeaderboardRow[]>(`/competitions/admin/cohorts/${cohortId}/export-top20`).then((r) => r.data)

export const publishCohortResultsApi = (cohortId: string) =>
  api.post<CompetitionPublication>(`/competitions/admin/cohorts/${cohortId}/publish`).then((r) => r.data)

export const unpublishCohortResultsApi = (cohortId: string) =>
  api.post<void>(`/competitions/admin/cohorts/${cohortId}/unpublish`).then((r) => r.data)

// ── Judge surface ────────────────────────────────────────────────────────

export const getMyJudgeCohortsApi = () =>
  api.get<CompetitionJudgeCohort[]>("/competitions/judge/cohorts").then((r) => r.data)

export const getMyJudgeTeamsApi = (cohortId: string) =>
  api.get<CompetitionJudgeTeam[]>("/competitions/judge/teams", { params: { cohort_id: cohortId } }).then((r) => r.data)

export const getMyJudgeTeamApi = (teamId: string) =>
  api.get<CompetitionTeamDetail>(`/competitions/judge/teams/${teamId}`).then((r) => r.data)

export const submitMyJudgeScoreApi = (
  teamId: string, data: { criterion_scores: Record<string, number>; bonus_points?: number },
) => api.put<CompetitionScore>(`/competitions/judge/teams/${teamId}/score`, data).then((r) => r.data)
