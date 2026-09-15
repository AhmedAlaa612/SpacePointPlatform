/** Competition judging (2026-08-24) — mirrors backend/app/schemas/competitions.py
 * and the `/competitions/admin/*` + `/competitions/judge/*` routers. */
import { api } from "@/api/client"
import type { DesignState } from "@/api/missionsDesign"

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
  /** False: only an autosaved draft — doesn't count toward already_scored,
   * judges_scored, or the leaderboard. True: the judge clicked Submit. */
  submitted: boolean
}

export interface CompetitionJudgeScore {
  judge_user_id: string
  judge_name: string
  total_points: number
}

export interface CompetitionLeaderboardRow {
  rank: number
  team_id: string
  team_name: string
  score: number | null
  judges_scored: number
  status: "scored" | "unscored"
  judge_scores: CompetitionJudgeScore[]
  /** Sibling cohort(s) under the same program with a same-named team —
   * inferred, not stored; null means not advanced (yet). */
  advanced_to: string | null
}

export interface CompetitionJudge {
  user_id: string
  full_name: string
  email: string
}

export interface CompetitionJudgeProgress extends CompetitionJudge {
  scored_count: number
  team_count: number
  onboarding_sent: boolean
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
  // 2026-09-14 — set (alongside submitted_url mirroring the first link)
  // only for a submission_multi_link item; render these grouped under the
  // one submission instead of a bare link.
  submission_multi_link: boolean
  submitted_links: { label: string | null; url: string }[] | null
  updated_at: string | null
  updated_by_name: string | null
}

// Phase 3 (2026-09) — a team-scoped design mission run. `attempt_id` is
// null until the team has one (not assigned to the checklist yet), in
// which case `status` is "not_started".
export interface CompetitionMissionRun {
  mission_id: string
  title: string
  attempt_id: string | null
  status: string
}

export interface CompetitionImportRow {
  row_number: number
  team_id: string | null
  team_name: string | null
  email: string | null
  disposition: "created" | "matched" | "error"
  reason: string | null
}

export interface CompetitionImportResult {
  summary: { total: number; created: number; matched: number; error: number }
  rows: CompetitionImportRow[]
}

/** A parsed sheet row, before anything is written — `issues` is empty for a
 * clean row, non-empty means it needs a fix (usually the email) before it
 * can be confirmed. Every field here is editable in the preview table.
 * `team_id` (2026-09-14) is the roster's own grouping key and the one
 * required team field now — `team_name` is optional, a blank one just
 * means that team hasn't named itself yet (see services/competitions/
 * registration_import.py's module docstring). */
export interface CompetitionImportPreviewRow {
  row_number: number
  team_id: string | null
  team_name: string | null
  member_name: string | null
  email: string | null
  phone: string | null
  nationality: string | null
  school: string | null
  issues: string[]
}

export interface CompetitionImportPreview {
  rows: CompetitionImportPreviewRow[]
}

/** Assign tab's search result — the same student row `/lms/admin/students`
 * returns, plus this cohort's own state: `team_id`/`team_name` are set
 * when the student is already on a team in *this* cohort (both null
 * otherwise), `registered` says whether they have an actual Registration
 * here (the search itself is platform-wide unless `registered_only` is
 * set), and `lms_access` says whether they already have this cohort's LMS
 * program checklist. Backs the `registered_only`/`team_status`/
 * `lms_status` filters. */
export interface CompetitionAssignableStudent {
  id: string
  full_name: string
  nickname: string | null
  email: string
  invite_code: string | null
  invite_label: string | null
  school_name: string | null
  grade: string | null
  status: string | null
  created_at: string | null
  team_id: string | null
  team_name: string | null
  registered: boolean
  lms_access: boolean
}

/** Assign tab (2026-09-14): a row of the bulk "assign already
 * self-registered students to teams" action. Same disposition vocabulary
 * as `CompetitionImportRow` — `created` means a new Registration was made
 * for this student, `matched` means they already had one (a re-assign or
 * team move). */
export interface CompetitionAssignStudentRow {
  row_number: number
  user_id: string | null
  team_id: string | null
  team_name: string | null
  disposition: "created" | "matched" | "error"
  reason: string | null
}

export interface CompetitionAssignStudentsResult {
  summary: { total: number; created: number; matched: number; error: number }
  rows: CompetitionAssignStudentRow[]
}

export interface CompetitionAdvanceResult {
  team_id: string
  team_name: string
  to_team_id: string
  members_advanced: number
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

export interface CompetitionTeam {
  id: string
  name: string
  cohort_id: string | null
  member_ids: string[]
  member_names: string[]
  member_emails: string[]
}

export interface CompetitionTeamDetail {
  team: { id: string; name: string; cohort_id: string | null; member_ids: string[]; member_names: string[] }
  submissions: CompetitionSubmissionItem[]
  // Defaults to [] server-side, so a cohort with no team-scoped mission_run
  // items (every cohort until Phase 2/3 items are authored) never carries
  // anything here.
  mission_runs: CompetitionMissionRun[]
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

export const inviteCohortJudgeApi = (
  cohortId: string, data: { name: string; email: string; send_email?: boolean },
) =>
  api.post<CompetitionJudge>(`/competitions/admin/cohorts/${cohortId}/judges`, data).then((r) => r.data)

export const revokeCohortJudgeApi = (cohortId: string, userId: string) =>
  api.delete<void>(`/competitions/admin/cohorts/${cohortId}/judges/${userId}`).then((r) => r.data)

export const resendJudgeOnboardingEmailApi = (cohortId: string, userId: string) =>
  api.post<{ sent: boolean }>(
    `/competitions/admin/cohorts/${cohortId}/judges/${userId}/resend-onboarding-email`,
  ).then((r) => r.data)

export const getCohortLeaderboardApi = (cohortId: string) =>
  api.get<CompetitionLeaderboardRow[]>(`/competitions/admin/cohorts/${cohortId}/leaderboard`).then((r) => r.data)

export const getCohortExportTop20Api = (cohortId: string) =>
  api.get<CompetitionLeaderboardRow[]>(`/competitions/admin/cohorts/${cohortId}/export-top20`).then((r) => r.data)

/** One .xlsx: a Scores sheet (rank, average, every judge's own score) and
 * a Submissions sheet (every team's link deliverables, who sent them,
 * when) — for reviewing a cohort's judging round outside the app. */
export const downloadCohortResultsWorkbookApi = async (cohortId: string, cohortName: string) => {
  const res = await api.get(`/competitions/admin/cohorts/${cohortId}/export.xlsx`, { responseType: "blob" })
  const url = URL.createObjectURL(res.data as Blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `${cohortName.replace(/[^a-z0-9]+/gi, "_")}_results.xlsx`
  a.click()
  URL.revokeObjectURL(url)
}

export const getCohortPublicationApi = (cohortId: string) =>
  api.get<CompetitionPublication>(`/competitions/admin/cohorts/${cohortId}/publication`).then((r) => r.data)

export const publishCohortResultsApi = (cohortId: string) =>
  api.post<CompetitionPublication>(`/competitions/admin/cohorts/${cohortId}/publish`).then((r) => r.data)

export const unpublishCohortResultsApi = (cohortId: string) =>
  api.post<void>(`/competitions/admin/cohorts/${cohortId}/unpublish`).then((r) => r.data)

/** Parses the sheet and flags per-row issues — writes nothing. Safe to call
 * repeatedly while ops is still fixing flagged rows in the browser. */
export const previewCohortRegistrationImportApi = (cohortId: string, file: File) => {
  const form = new FormData()
  form.append("file", file)
  return api.post<CompetitionImportPreview>(
    `/competitions/admin/cohorts/${cohortId}/registration-import/preview`, form,
    { headers: { "Content-Type": "multipart/form-data" } },
  ).then((r) => r.data)
}

/** Actually commits the (possibly hand-edited) preview rows. The server
 * re-validates on the way in — a row still missing a field or still
 * carrying a malformed email comes back as an `error` row, not written. */
export const confirmCohortRegistrationImportApi = (
  cohortId: string,
  rows: Omit<CompetitionImportPreviewRow, "issues">[],
  options?: { send_ticket_email?: boolean; send_welcome_email?: boolean },
) =>
  api.post<CompetitionImportResult>(
    `/competitions/admin/cohorts/${cohortId}/registration-import/confirm`, { rows, ...options },
  ).then((r) => r.data)

/** Assign tab's own cohort-scoped student search — same name/email +
 * invite-code filters as `searchStudentsApi`, plus `registered_only`
 * (restrict to students who actually have a Registration in this cohort,
 * vs. the default platform-wide search) and `team_status`/`lms_status`
 * filters. */
export const searchAssignableStudentsApi = (
  cohortId: string,
  params: {
    q?: string; invite_code?: string; registered_only?: boolean
    team_status?: "all" | "has_team" | "no_team"
    lms_status?: "all" | "has_access" | "no_access"
  } = {},
) =>
  api.get<CompetitionAssignableStudent[]>(
    `/competitions/admin/cohorts/${cohortId}/assignable-students`, { params },
  ).then((r) => r.data)

/** Assign tab: registers each already self-registered student (found via
 * `searchAssignableStudentsApi`) into `cohortId` and adds them to the Team
 * ID ops typed in for their row, creating the team if it's new. Idempotent
 * the same way the roster import is — see `CompetitionAssignStudentRow`. */
export const assignExistingStudentsApi = (
  cohortId: string,
  rows: { user_id: string; team_id: string }[],
  options?: { send_ticket_email?: boolean; send_welcome_email?: boolean },
) =>
  api.post<CompetitionAssignStudentsResult>(
    `/competitions/admin/cohorts/${cohortId}/assign-students`, { rows, ...options },
  ).then((r) => r.data)

export const advanceCohortTeamsApi = (
  cohortId: string,
  data: { team_ids: string[]; to_cohort_id: string; send_ticket_email?: boolean; send_welcome_email?: boolean },
) =>
  api.post<CompetitionAdvanceResult[]>(`/competitions/admin/cohorts/${cohortId}/advance-teams`, data).then((r) => r.data)

// ── Teams (manual management) ───────────────────────────────────────────

export const getCohortTeamsApi = (cohortId: string) =>
  api.get<CompetitionTeam[]>(`/competitions/admin/cohorts/${cohortId}/teams`).then((r) => r.data)

export const createCohortTeamApi = (cohortId: string, name: string) =>
  api.post<CompetitionTeam>(`/competitions/admin/cohorts/${cohortId}/teams`, { name }).then((r) => r.data)

export const renameTeamApi = (teamId: string, name: string) =>
  api.patch<CompetitionTeam>(`/competitions/admin/teams/${teamId}`, { name }).then((r) => r.data)

export const deleteTeamApi = (teamId: string) =>
  api.delete<void>(`/competitions/admin/teams/${teamId}`).then((r) => r.data)

export const addExistingTeamMemberApi = (teamId: string, userId: string) =>
  api.post<CompetitionTeam>(`/competitions/admin/teams/${teamId}/members`, { user_id: userId }).then((r) => r.data)

export const registerAndAddTeamMemberApi = (
  teamId: string,
  data: {
    full_name: string; email: string; phone?: string; school?: string
    send_welcome_email?: boolean; send_ticket_email?: boolean
  },
) => api.post<CompetitionTeam>(`/competitions/admin/teams/${teamId}/members`, data).then((r) => r.data)

export const removeTeamMemberApi = (teamId: string, userId: string) =>
  api.delete<void>(`/competitions/admin/teams/${teamId}/members/${userId}`).then((r) => r.data)

// ── Judge surface ────────────────────────────────────────────────────────

export const getMyJudgeCohortsApi = () =>
  api.get<CompetitionJudgeCohort[]>("/competitions/judge/cohorts").then((r) => r.data)

export const getMyJudgeTeamsApi = (cohortId: string) =>
  api.get<CompetitionJudgeTeam[]>("/competitions/judge/teams", { params: { cohort_id: cohortId } }).then((r) => r.data)

export const getMyJudgeTeamApi = (teamId: string) =>
  api.get<CompetitionTeamDetail>(`/competitions/judge/teams/${teamId}`).then((r) => r.data)

// Phase 3 — read-only design dashboard for one of this team's mission
// runs, scoped through the judge's own team access (never a bare "any
// attempt id" fetch). Returns the same DesignState shape the ops-facing
// `attemptDesignDetailApi` does, so `DesignRunDetail` can render either.
export const getMyJudgeTeamMissionRunDetailApi = (teamId: string, attemptId: string) =>
  api.get<DesignState>(`/competitions/judge/teams/${teamId}/mission-runs/${attemptId}/design-detail`).then((r) => r.data)

export const submitMyJudgeScoreApi = (
  teamId: string, data: { criterion_scores: Record<string, number>; bonus_points?: number; submitted?: boolean },
) => api.put<CompetitionScore>(`/competitions/judge/teams/${teamId}/score`, data).then((r) => r.data)
