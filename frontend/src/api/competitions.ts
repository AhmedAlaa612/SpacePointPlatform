/** Competition judging (2026-08-24) — mirrors backend/app/schemas/competitions.py
 * and the `/competitions/admin/*` + `/competitions/judge/*` routers. */
import { api } from "@/api/client"
import type { DesignState } from "@/api/missionsDesign"

export interface CompetitionRubricSubCriterion {
  key: string
  label: string
  max_points: number
  position: number
}

export interface CompetitionRubricCriterion {
  key: string
  label: string
  max_points: number
  position: number
  /** Who grades it — "judge" or "operations". Sub-criteria always inherit this. */
  scored_by?: string
  /** Empty/missing = flat criterion scored directly; otherwise scored via these leaves. */
  sub_criteria?: CompetitionRubricSubCriterion[]
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
  criterion_comments?: Record<string, string>
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
  is_observer?: boolean
  score: number | null
  score_percent?: number | null
  qualification?: string | null
  judges_scored: number
  status: "scored" | "unscored"
  judge_scores: CompetitionJudgeScore[]
  /** Sibling cohort(s) under the same program with a same-named team —
   * inferred, not stored; null means not advanced (yet). */
  advanced_to: string | null
  timing_adjustment?: number | null
  timing_badge?: string | null
  timing_tier_name?: string | null
  is_timing_override?: boolean
  timing_override_notes?: string | null
  final_locked_at?: string | null
  first_locked_at?: string | null
  raw_judge_score?: number | null
  /** Operations-graded total for this team (null until operations scores it). */
  ops_score?: number | null
  ops_max_points?: number | null
  ops_criterion_scores?: Record<string, number>
  ops_criterion_notes?: string | null
}

export interface CompetitionVisibilitySettings {
  show_score: boolean
  show_rank: boolean
  show_breakdown: boolean
  show_ops_criteria: boolean
  show_ops_comments: boolean
  show_judge_comments: boolean
}

export interface StudentCriterionScoreBreakdown {
  key: string
  label: string
  max_points: number
  average_points?: number | null
  subs?: CriterionSubScoreItem[]
}

export interface StudentJudgeCriteriaComment {
  criterion: string
  comment: string
}

export interface CompetitionStudentResult {
  team_id: string
  team_name: string
  status: string
  locked: boolean
  locked_at: string | null
  published: boolean
  qualification: string | null
  timing_adjustment?: number | null
  timing_badge?: string | null

  final_score?: number | null
  score_percent?: number | null
  raw_judge_score?: number | null
  rank?: number | null
  total_teams?: number | null

  criteria_breakdown?: StudentCriterionScoreBreakdown[] | null
  ops_score?: number | null
  ops_max_points?: number | null
  ops_breakdown?: CriterionScoreItem[] | null

  ops_comments?: string | null
  judge_comments?: string[] | null
  judge_criteria_comments?: StudentJudgeCriteriaComment[] | null

  visibility_settings?: CompetitionVisibilitySettings | null
}

export interface SubmissionWindowItem {
  id: string
  name: string
  cutoff_at: string
  points: number
  badge?: string | null
  color?: string | null
  description?: string | null
  is_deadline?: boolean
}

export interface TeamTimingAdjustmentUpdate {
  override_points: number | null
  notes?: string | null
}

export interface CriterionScoreItem {
  key: string
  label: string
  max_points: number
  awarded_points?: number | null
  comment?: string | null
  subs?: CriterionSubScoreItem[]
}

export interface CriterionSubScoreItem {
  key: string
  label: string
  max_points: number
  awarded_points?: number | null
}

export interface JudgeEvaluationDetail {
  judge_user_id: string
  judge_name: string
  judge_email: string
  submitted_at?: string | null
  total_points: number
  bonus_points: number
  timing_adjustment: number
  notes?: string | null
  criteria: CriterionScoreItem[]
}

export interface TeamScoreBreakdown {
  team_id: string
  team_name: string
  cohort_id: string
  status: string
  qualification?: string | null
  final_score?: number | null
  score_percent?: number | null
  raw_judge_score?: number | null
  timing_adjustment?: number | null
  timing_badge?: string | null
  is_timing_override: boolean
  timing_override_notes?: string | null
  final_locked_at?: string | null
  first_locked_at?: string | null
  judges: JudgeEvaluationDetail[]
  ops_score?: number | null
  ops_max_points?: number | null
  ops_criterion_scores?: Record<string, number>
  ops_criterion_notes?: string | null
  ops_breakdown?: CriterionScoreItem[]
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
  visibility_settings?: CompetitionVisibilitySettings
}

export interface CompetitionSubmissionItem {
  item_id: string
  title: string
  item_type: string
  status: string
  submitted_url: string | null
  // The plain (non-multi) submission's own type — link (default) or text.
  submission_field_type: "text" | "link"
  submitted_text: string | null
  // 2026-09-14 — set (alongside submitted_url mirroring the first link)
  // only for a submission_multi_link item; render these grouped under the
  // one submission instead of a bare link.
  submission_multi_link: boolean
  submitted_links: { label: string | null; url: string | null; text: string | null }[] | null
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
 * set — "In program" reads this, not `lms_access`), and `card_id` is the
 * printable ID-card string. `roles` carries the account's actual roles
 * (drives the Staff toggle + role filter). Backs the `registered_only`/
 * `team_status`/`login_status` filters. */
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
  /** Set the moment a login actually succeeds — null means this account
   * has never once been logged into. */
  last_login_at: string | null
  team_id: string | null
  team_name: string | null
  team_uuid: string | null
  registered: boolean
  lms_access: boolean
  is_observer?: boolean
  card_number: number | null
  card_id: string | null
  roles: string[]
}

export interface CompetitionAssignableStudentsPage {
  items: CompetitionAssignableStudent[]
  total: number
  page: number
  page_size: number
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
  // Team hit "Final Submit" — its checklist is frozen, only ops can reopen it.
  locked: boolean
  locked_at?: string | null
  roster_team_id?: string | null
  member_count?: number
  items_done?: number
  items_total?: number
  pct?: number
  is_observer?: boolean
}

export interface CompetitionTeam {
  id: string
  name: string
  cohort_id: string | null
  member_ids: string[]
  member_names: string[]
  member_emails: string[]
  is_observer?: boolean
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
  locked?: boolean
  locked_at?: string | null
  /** Operations-graded scores (leaves + parent totals) — read-only for judges. */
  ops_criterion_scores?: Record<string, number>
  ops_max_points?: number | null
}

// ── Ops admin ────────────────────────────────────────────────────────────

export const getCohortRubricApi = (cohortId: string) =>
  api.get<CompetitionRubric>(`/competitions/admin/cohorts/${cohortId}/rubric`).then((r) => r.data)

export const putCohortRubricApi = (
  cohortId: string,
  data: {
    name: string
    criteria: {
      key: string; label: string; max_points: number
      scored_by?: "judge" | "operations"
      sub_criteria?: { key: string; label: string; max_points: number }[]
    }[]
  },
) => api.put<CompetitionRubric>(`/competitions/admin/cohorts/${cohortId}/rubric`, data).then((r) => r.data)

export const getProgramRubricApi = (programId: string) =>
  api.get<CompetitionRubric>(`/competitions/admin/programs/${programId}/rubric`).then((r) => r.data)

export const putProgramRubricApi = (
  programId: string,
  data: {
    name: string
    criteria: {
      key: string; label: string; max_points: number
      scored_by?: "judge" | "operations"
      sub_criteria?: { key: string; label: string; max_points: number }[]
    }[]
  },
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

export const getCohortLeaderboardApi = (cohortId: string, mode?: "participant" | "observer" | "all") =>
  api.get<CompetitionLeaderboardRow[]>(`/competitions/admin/cohorts/${cohortId}/leaderboard`, { params: mode ? { mode } : {} }).then((r) => r.data)

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

/** One .xlsx: a 'Quiz Summary' sheet and a 'Quiz Answers' sheet (per-question
 * answers grouped by Team and Quiz) — for reviewing cohort quiz diagnostic results. */
export const downloadCohortQuizAnswersWorkbookApi = async (cohortId: string, cohortName: string) => {
  const res = await api.get(`/competitions/admin/cohorts/${cohortId}/quiz-answers.xlsx`, { responseType: "blob" })
  const url = URL.createObjectURL(res.data as Blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `${cohortName.replace(/[^a-z0-9]+/gi, "_")}_quiz_answers.xlsx`
  a.click()
  URL.revokeObjectURL(url)
}

export const getCohortPublicationApi = (cohortId: string) =>
  api.get<CompetitionPublication>(`/competitions/admin/cohorts/${cohortId}/publication`).then((r) => r.data)

export const publishCohortResultsApi = (cohortId: string, settings?: CompetitionVisibilitySettings) =>
  api.post<CompetitionPublication>(`/competitions/admin/cohorts/${cohortId}/publish`, settings ? { visibility_settings: settings } : {}).then((r) => r.data)

export const updateCohortPublicationSettingsApi = (cohortId: string, settings: CompetitionVisibilitySettings) =>
  api.put<CompetitionPublication>(`/competitions/admin/cohorts/${cohortId}/publication/settings`, { visibility_settings: settings }).then((r) => r.data)

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

/** Assign tab's own cohort-scoped search — same name/email +
 * invite-code filters as `searchStudentsApi`, plus `registered_only`
 * (restrict to accounts who actually have a Registration in this cohort,
 * vs. the default platform-wide search), `team_status`/`login_status`
 * filters, `mode` (`student` | `staff` = literally not a student |
 * `observer` = has observer role), an optional `role` narrowing the
 * staff toggle, and server-side pagination + sorting. */
export const searchAssignableStudentsApi = (
  cohortId: string,
  params: {
    q?: string; invite_code?: string; registered_only?: boolean
    team_status?: "all" | "has_team" | "no_team"
    lms_status?: "all" | "has_access" | "no_access"
    login_status?: "all" | "never" | "has_logged_in"
    mode?: "all" | "student" | "observer" | "staff"
    role?: string
    page?: number; page_size?: number
    sort?: "full_name" | "card_number" | "created_at" | "email"
    direction?: "asc" | "desc"
  } = {},
) =>
  api.get<CompetitionAssignableStudentsPage>(
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

/** Assign tab add-to-program (2026-10): registers accounts into the
 * cohort without putting them on a team. Staff accounts gain the
 * observer role + a mode="observer" assignment. */
export const registerUsersToCohortApi = (
  cohortId: string,
  userIds: string[],
  options?: { send_welcome_email?: boolean; send_ticket_email?: boolean },
) =>
  api.post<CompetitionAssignStudentsResult>(
    `/competitions/admin/cohorts/${cohortId}/register-users`, { user_ids: userIds, ...options },
  ).then((r) => r.data)

export const advanceCohortTeamsApi = (
  cohortId: string,
  data: { team_ids: string[]; to_cohort_id: string; send_ticket_email?: boolean; send_welcome_email?: boolean },
) =>
  api.post<CompetitionAdvanceResult[]>(`/competitions/admin/cohorts/${cohortId}/advance-teams`, data).then((r) => r.data)

// ── Teams (manual management) ───────────────────────────────────────────

export const getCohortTeamsApi = (cohortId: string) =>
  api.get<CompetitionTeam[]>(`/competitions/admin/cohorts/${cohortId}/teams`).then((r) => r.data)

export const createCohortTeamApi = (cohortId: string, name: string, is_observer?: boolean) =>
  api.post<CompetitionTeam>(`/competitions/admin/cohorts/${cohortId}/teams`, { name, is_observer: !!is_observer }).then((r) => r.data)

export const renameTeamApi = (teamId: string, name: string) =>
  api.patch<CompetitionTeam>(`/competitions/admin/teams/${teamId}`, { name }).then((r) => r.data)

export const deleteTeamApi = (teamId: string) =>
  api.delete<void>(`/competitions/admin/teams/${teamId}`).then((r) => r.data)

/** Reopens a team's checklist after "Final Submit" — see
 * routers/competitions/admin.py::unlock_team. The only way that lock
 * ever clears; a team can never re-open its own submission. */
export const unlockTeamApi = (teamId: string) =>
  api.post<CompetitionTeam>(`/competitions/admin/teams/${teamId}/unlock`).then((r) => r.data)

export const resetObserverTeamApi = (teamId: string) =>
  api.post<CompetitionTeam>(`/competitions/admin/teams/${teamId}/observer-reset`).then((r) => r.data)

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

export const getMyJudgeTeamsApi = (cohortId: string, mode?: "participant" | "observer" | "all") =>
  api.get<CompetitionJudgeTeam[]>("/competitions/judge/teams", { params: { cohort_id: cohortId, ...(mode ? { mode } : {}) } }).then((r) => r.data)

export const getMyJudgeTeamApi = (teamId: string) =>
  api.get<CompetitionTeamDetail>(`/competitions/judge/teams/${teamId}`).then((r) => r.data)

// Phase 3 — read-only design dashboard for one of this team's mission
// runs, scoped through the judge's own team access (never a bare "any
// attempt id" fetch). Returns the same DesignState shape the ops-facing
// `attemptDesignDetailApi` does, so `DesignRunDetail` can render either.
export const getMyJudgeTeamMissionRunDetailApi = (teamId: string, attemptId: string) =>
  api.get<DesignState>(`/competitions/judge/teams/${teamId}/mission-runs/${attemptId}/design-detail`).then((r) => r.data)

export const submitMyJudgeScoreApi = (
  teamId: string,
  data: {
    criterion_scores: Record<string, number>
    criterion_comments?: Record<string, string>
    bonus_points?: number
    submitted?: boolean
  },
) => api.put<CompetitionScore>(`/competitions/judge/teams/${teamId}/score`, data).then((r) => r.data)

// ── Team analytics (2026-09-16) ─────────────────────────────────────────
// Backs the Judging page's Analysis tab — one payload, mirroring
// `CompetitionAnalyticsOut` in backend/app/schemas/competitions.py. See
// `services/competitions/analytics.py` for where each number comes from
// (in particular: `mission_run` items are reported under `missions`, not
// as `items` rows, because their real completion is per-design-step).

export interface CompetitionAnalyticsItem {
  item_id: string
  title: string
  item_type: string
  scope: "team" | "individual"
  position: number
  optional: boolean
  deadline_at: string | null
  /** What `total` counts — so the UI never infers it from `scope`. */
  denominator: "teams" | "students"
  total: number
  done: number
  awaiting: number
  pending: number
  pct: number
}

export interface CompetitionAnalyticsMission {
  mission_id: string
  title: string
  scope: "team" | "individual"
  total: number
  passed: number
  in_progress: number
  not_started: number
}

export interface CompetitionAnalyticsDeliverable {
  item_id: string
  title: string
  status: string
  optional?: boolean
  submitted_url: string | null
  submitted_text: string | null
  submitted_links: { label: string | null; url: string | null; text: string | null }[] | null
}

export interface CompetitionAnalyticsTeamMember {
  user_id?: string
  name: string
  last_login_at: string | null
}

export interface CompetitionTeamQuizSubmission {
  user_id: string
  student_name: string
  assignment_id: string | null
  item_id: string
  quiz_title: string
  status: "submitted" | "in_progress" | "not_started"
  score: number | null
  total: number | null
  submitted_at: string | null
}

export interface CompetitionAnalyticsTeam {
  team_id: string
  team_name: string
  roster_team_id: string | null
  is_observer?: boolean
  member_count: number
  members: CompetitionAnalyticsTeamMember[]
  never_logged_in: number
  items_total: number
  items_done: number
  awaiting: number
  pct: number
  /** Every required team deliverable — awaiting_confirmation counts as not
   * done, since ops confirming it is the outstanding work, but a done or
   * awaiting item still carries whatever the team actually submitted. */
  deliverables: CompetitionAnalyticsDeliverable[]
  /** Team-scoped Design mission runs on this team's checklist, if any. */
  mission_runs: CompetitionMissionRun[]
  /** Cohort quiz submissions for members of this team. */
  quiz_submissions?: CompetitionTeamQuizSubmission[]
  last_activity_at: string | null
  stalled: boolean
  /** Team hit "Final Submit" — its checklist is frozen, only ops can reopen it. */
  locked: boolean
  locked_at?: string | null
  locked_by_name?: string | null
  locked_by_email?: string | null
  locked_by_id?: string | null
}

export interface CompetitionAnalyticsActivity {
  date: string
  updates: number
}

export interface CompetitionAnalyticsTotals {
  teams: number
  students_on_teams: number
  avg_team_size: number
  empty_teams: number
  registered_students: number
  students_without_team: number
  assigned_students: number
  never_logged_in: number
  deliverables_per_team: number
  deliverables_done: number
  deliverables_awaiting: number
  teams_complete: number
  teams_not_started: number
  teams_stalled: number
  avg_team_pct: number
}

export interface CompetitionAnalytics {
  cohort_id: string
  cohort_name: string
  totals: CompetitionAnalyticsTotals
  items: CompetitionAnalyticsItem[]
  missions: CompetitionAnalyticsMission[]
  teams: CompetitionAnalyticsTeam[]
  activity: CompetitionAnalyticsActivity[]
  stalled_after_days: number
}

export const getCohortTeamAnalyticsApi = (cohortId: string, mode?: "participant" | "observer" | "all") =>
  api.get<CompetitionAnalytics>(`/competitions/admin/cohorts/${cohortId}/team-analytics`, { params: mode ? { mode } : {} }).then((r) => r.data)

// ── Certificate issuance (2026-09) ──────────────────────────────────────────

export interface CompetitionCertificateRecipient {
  registration_id: string
  user_id?: string | null
  contact_id: string
  student_name: string
  email?: string | null
  team_id?: string | null
  team_name?: string | null
  submissions_done: number
  submissions_total: number
  required_submissions_total: number
  /** Required submissions done — the eligibility-driving count. */
  required_submissions_done?: number
  /** Optional (bonus-only) submissions done — never drives eligibility. */
  optional_submissions_done?: number
  optional_submissions_total?: number
  team_locked: boolean
  meets_locked_only: boolean
  meets_participation: boolean
  meets_at_least_one: boolean
  meets_all_completed: boolean
  certificate_type_earned?: "completion" | "participation" | null
  certificate_issued: boolean
  certificate_id?: string | null
  certificate_generated_at?: string | null
}

export interface CompetitionCertificateRecipientsSummary {
  program_name?: string
  cohort_name?: string
  dates?: string
  total_registered: number
  submission_items_total: number
  required_submissions_total: number
  locked_only_count: number
  participation_count: number
  at_least_one_count: number
  all_completed_count: number
  recipients: CompetitionCertificateRecipient[]
  templates?: Array<{
    id: string
    name: string
    is_default: boolean
    background_type?: string
    email_subject?: string | null
    email_body?: string | null
  }> | null
  default_template_id?: string | null
}

export type CertificateFilterMode = "locked_only" | "participation" | "all_completed" | "at_least_one" | "all"

export interface CompetitionCertificateSendIn {
  filter: CertificateFilterMode | "custom"
  registration_ids?: string[] | null
  theme?: "dark" | "light" | string
  template_id?: string | null
  skip_already_issued?: boolean
  custom_email_subject?: string | null
  custom_email_body?: string | null
  save_email_to_template?: boolean
  /** Bulk override: issue every targeted recipient as this type. Omit for earned types. */
  force_certificate_type?: "completion" | "participation" | null
}

export interface CompetitionCertificateSendResult {
  status?: string
  sent_count: number
  skipped_count: number
  total_targeted: number
  recipient_names: string[]
  errors: string[]
}

export const getCohortCertificateRecipientsApi = (
  cohortId: string,
  filter: CertificateFilterMode = "all",
) =>
  api
    .get<CompetitionCertificateRecipientsSummary>(
      `/competitions/admin/cohorts/${cohortId}/certificates/recipients`,
      { params: { filter } },
    )
    .then((r) => r.data)

export const sendCohortCertificatesApi = (
  cohortId: string,
  payload: CompetitionCertificateSendIn,
) =>
  api
    .post<CompetitionCertificateSendResult>(
      `/competitions/admin/cohorts/${cohortId}/certificates/send`,
      payload,
    )
    .then((r) => r.data)

export interface CompetitionCertificateTestEmailIn {
  to_email: string
  recipient_name?: string
  theme?: string
  template_id?: string | null
  certificate_type?: "completion" | "participation"
  custom_email_subject?: string | null
  custom_email_body?: string | null
}

export const sendTestCertificateEmailApi = (
  cohortId: string,
  payload: CompetitionCertificateTestEmailIn,
) =>
  api
    .post<{ sent: boolean; to: string; subject: string }>(
      `/competitions/admin/cohorts/${cohortId}/certificates/test-email`,
      payload,
    )
    .then((r) => r.data)


export const downloadCompetitionCertificatesApi = async (
  cohortId: string,
  cohortName: string,
  filter: CertificateFilterMode | "custom",
  theme: "dark" | "light" | string = "dark",
  registrationIds?: string[] | null,
  templateId?: string | null,
  forceCertificateType?: "completion" | "participation" | null,
) => {
  let res
  if (registrationIds && registrationIds.length > 0) {
    res = await api.post(
      `/competitions/admin/cohorts/${cohortId}/certificates/download`,
      {
        filter, theme, template_id: templateId, registration_ids: registrationIds,
        force_certificate_type: forceCertificateType ?? undefined,
      },
      { responseType: "blob" },
    )
  } else {
    res = await api.get(`/competitions/admin/cohorts/${cohortId}/certificates/download`, {
      params: { filter, theme, template_id: templateId, force_certificate_type: forceCertificateType ?? undefined },
      responseType: "blob",
    })
  }
  const url = URL.createObjectURL(res.data as Blob)
  const a = document.createElement("a")
  a.href = url
  const safeName = cohortName.replace(/[^a-z0-9]+/gi, "_")
  const suffix = registrationIds && registrationIds.length > 0 ? `_${registrationIds.length}_selected` : ""
  a.download = `certificates_${filter}_${safeName}_${theme}${suffix}.pdf`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export const getStudentCompetitionResultApi = (cohortId: string) =>
  api.get<CompetitionStudentResult>(`/competitions/student/cohorts/${cohortId}/my-result`).then((r) => r.data)

export const getCohortSubmissionWindowsApi = (cohortId: string) =>
  api.get<SubmissionWindowItem[]>(`/competitions/admin/cohorts/${cohortId}/submission-windows`).then((r) => r.data)

export const updateCohortSubmissionWindowsApi = (cohortId: string, windows: SubmissionWindowItem[]) =>
  api.put<SubmissionWindowItem[]>(`/competitions/admin/cohorts/${cohortId}/submission-windows`, { windows }).then((r) => r.data)

export const updateTeamTimingAdjustmentApi = (cohortId: string, teamId: string, body: TeamTimingAdjustmentUpdate) =>
  api.patch<TeamScoreBreakdown>(`/competitions/admin/cohorts/${cohortId}/teams/${teamId}/timing-adjustment`, body).then((r) => r.data)

export const getTeamScoreBreakdownApi = (cohortId: string, teamId: string) =>
  api.get<TeamScoreBreakdown>(`/competitions/admin/cohorts/${cohortId}/teams/${teamId}/score-breakdown`).then((r) => r.data)

export interface OperationsScoreUpdate {
  criterion_scores: Record<string, number>
  notes?: string | null
}

export interface OperationsScoreResult {
  team_id: string
  ops_criterion_scores: Record<string, number>
  ops_criterion_notes: string | null
  ops_scored_at: string | null
  ops_scored_by_name: string | null
}

/** Operations grades its own criteria for a team — judge averages are untouched. */
export const putTeamOperationsScoreApi = (cohortId: string, teamId: string, body: OperationsScoreUpdate) =>
  api.put<OperationsScoreResult>(`/competitions/admin/cohorts/${cohortId}/teams/${teamId}/ops-score`, body).then((r) => r.data)

export interface CohortTimingWindowResponse {
  windows: SubmissionWindowItem[]
  active_window: (SubmissionWindowItem & { seconds_remaining: number; is_active: boolean }) | null
  is_deadline_passed?: boolean
  deadline_cutoff_at?: string | null
}

export const getCohortTimingWindowStudentApi = (cohortId: string) =>
  api.get<CohortTimingWindowResponse>(`/competitions/student/cohorts/${cohortId}/timing-window`).then((r) => r.data)



