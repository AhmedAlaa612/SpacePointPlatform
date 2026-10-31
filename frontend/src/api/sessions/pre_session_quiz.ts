import { api } from "@/api/client"

export interface PinoutCell {
  text: string
  is_correct: boolean
}

export interface PinoutRow {
  label: string
  cells: PinoutCell[]
}

export interface PinoutTableConfig {
  connector_name: string
  header_subtitle: string
  columns: string[]
  rows: PinoutRow[]
}

export interface McqOption {
  text: string
  is_correct: boolean
}

export interface PreSessionQuizQuestion {
  id: string
  topic: string
  question_type: "pinout_table" | "mcq" | "written" | "subsystem_matching"
  title: string
  prompt: string
  image_url?: string | null
  options: McqOption[]
  table_config?: PinoutTableConfig | null
  allow_other: boolean
  is_other_correct: boolean
  explanation?: string | null
  explanation_image_url?: string | null
  explanation_table?: PinoutTableConfig | null
  is_active: boolean
  created_at?: string | null
}

export interface PreSessionQuizQuestionIn {
  topic: string
  question_type: "pinout_table" | "mcq" | "written" | "subsystem_matching"
  title: string
  prompt: string
  image_url?: string | null
  options: McqOption[]
  table_config?: PinoutTableConfig | null
  allow_other: boolean
  is_other_correct: boolean
  explanation?: string | null
  explanation_image_url?: string | null
  explanation_table?: PinoutTableConfig | null
  is_active?: boolean
}

export interface ReferenceAttachment {
  id?: string
  title: string
  url: string
  doc_type?: "datasheet" | "user_guide"
  subsystem_tag?: string | null
  image_url?: string | null
  is_file: boolean
}

export interface MatchingBucket {
  id: string
  label: string
  subtitle?: string
  color: "purple" | "emerald" | "blue" | "amber" | "rose" | "cyan"
}

export interface MatchingItemRule {
  datasheet_id: string
  correct_bucket_id: string
  explanation?: string | null
}

export interface MatchingPhaseConfig {
  buckets: MatchingBucket[]
  items: MatchingItemRule[]
}

export interface QuizPipelinePhase {
  id: string
  phase_type: "explore_datasheets" | "subsystem_matching" | "quiz"
  title: string
  subtitle?: string
  instructions?: string[]
  pass_percentage: number
  cooldown_seconds: number
  show_correct_on_fail: boolean
  show_explanation_on_fail: boolean
  show_bucket_target_counts: boolean
  allow_datasheet_lookup: boolean
  question_ids: string[]
  matching_config?: MatchingPhaseConfig | null
}

export interface PreSessionQuizPreset {
  id: string
  name: string
  description?: string | null
  question_ids: string[]
  reference_attachments: ReferenceAttachment[]
  phases?: QuizPipelinePhase[]
  questions: PreSessionQuizQuestion[]
  is_active: boolean
  created_at?: string | null
}

export interface PreSessionQuizPresetIn {
  name: string
  description?: string | null
  question_ids?: string[]
  reference_attachments?: ReferenceAttachment[]
  phases?: QuizPipelinePhase[]
  is_active?: boolean
}

export interface PreSessionQuizAssignment {
  level: "session" | "cohort" | "program" | "none"
  preset_id: string | null
  preset_name: string | null
  inherited: boolean
}

export interface PreSessionQuizAnswerIn {
  question_id: string
  selected_option_index?: number | null
  selected_cells?: number[][] | null
  chose_other?: boolean
  other_text?: string | null
  written_text?: string | null
}

export interface PreSessionQuizAnswerRecord {
  question_id: string
  selected_option_index?: number | null
  selected_cells?: number[][] | null
  chose_other: boolean
  other_text?: string | null
  written_text?: string | null
  status: "correct" | "incorrect" | "pending_review"
  needs_ops_inspection?: boolean
  reviewed_by?: string | null
  reviewed_at?: string | null
  review_comment?: string | null
}

export interface PhaseTrial {
  id: string
  attempt_id: string
  phase_id: string
  phase_index: number
  phase_type: string
  trial_number: number
  started_at: string
  submitted_at: string
  duration_seconds: number
  score: number
  total: number
  score_pct: number
  pass_percentage_required: number
  passed: boolean
  cooldown_until?: string | null
  cooldown_seconds_remaining?: number | null
  payload: Record<string, any>
}

export interface PreSessionQuizAttempt {
  id: string
  cohort_id?: string | null
  session_id?: string | null
  preset_id?: string | null
  user_id: string
  user_name?: string | null
  status?: "in_progress" | "cooldown_locked" | "completed"
  current_phase_index?: number
  phase_started_at?: string | null
  locked_until?: string | null
  cooldown_seconds_remaining?: number | null
  started_at?: string | null
  submitted_at?: string | null
  total_duration_seconds?: number
  answers: PreSessionQuizAnswerRecord[]
  phase_states?: Record<string, any>
  auto_score: number
  final_score: number
  total_questions: number
  pending_review_count: number
}

export interface CohortPreQuizStatus {
  has_quiz: boolean
  assignment_level?: string
  preset?: PreSessionQuizPreset | null
  my_attempt?: PreSessionQuizAttempt | null
  trials?: PhaseTrial[]
  all_attempts: PreSessionQuizAttempt[]
}

export type SessionPreQuizStatus = CohortPreQuizStatus

export interface PhaseTrialSubmitIn {
  client_duration_seconds?: number
  matching_placements?: Record<string, string>
  answers?: PreSessionQuizAnswerIn[]
}

export type PreQuizScope = "programs" | "cohorts" | "sessions"

/* ── Question Bank API ─────────────────────────────────────────────────────── */

export const listPreQuizQuestionsApi = (params?: { topic?: string; active_only?: boolean }) =>
  api.get<PreSessionQuizQuestion[]>("/sessions/pre-quiz/questions", { params }).then((r) => r.data)

export const createPreQuizQuestionApi = (body: PreSessionQuizQuestionIn) =>
  api.post<PreSessionQuizQuestion>("/sessions/pre-quiz/questions", body).then((r) => r.data)

export const updatePreQuizQuestionApi = (questionId: string, body: PreSessionQuizQuestionIn) =>
  api.put<PreSessionQuizQuestion>(`/sessions/pre-quiz/questions/${questionId}`, body).then((r) => r.data)

export const deletePreQuizQuestionApi = (questionId: string) =>
  api.delete(`/sessions/pre-quiz/questions/${questionId}`).then((r) => r.data)

export const uploadPreQuizImageApi = (file: File) => {
  const form = new FormData()
  form.append("file", file)
  return api.post<{ url: string; path: string }>("/sessions/pre-quiz/images", form).then((r) => r.data)
}

export const uploadPreQuizDatasheetApi = (file: File) => {
  const form = new FormData()
  form.append("file", file)
  return api.post<{ url: string; path: string }>("/sessions/pre-quiz/datasheets", form).then((r) => r.data)
}

/* ── Presets API ───────────────────────────────────────────────────────────── */

export const listPreQuizPresetsApi = (activeOnly = true) =>
  api
    .get<PreSessionQuizPreset[]>("/sessions/pre-quiz/presets", { params: { active_only: activeOnly } })
    .then((r) => r.data)

export const createPreQuizPresetApi = (body: PreSessionQuizPresetIn) =>
  api.post<PreSessionQuizPreset>("/sessions/pre-quiz/presets", body).then((r) => r.data)

export const updatePreQuizPresetApi = (presetId: string, body: PreSessionQuizPresetIn) =>
  api.put<PreSessionQuizPreset>(`/sessions/pre-quiz/presets/${presetId}`, body).then((r) => r.data)

export const deletePreQuizPresetApi = (presetId: string) =>
  api.delete(`/sessions/pre-quiz/presets/${presetId}`).then((r) => r.data)

/* ── Assignments API (Program -> Cohort -> Session) ────────────────────────── */

export const getPreQuizAssignmentApi = (scope: PreQuizScope, ownerId: string) =>
  api
    .get<PreSessionQuizAssignment>(`/sessions/pre-quiz/assignments/${scope}/${ownerId}`)
    .then((r) => r.data)

export const setPreQuizAssignmentApi = (
  scope: PreQuizScope,
  ownerId: string,
  presetId: string | null,
  clearOverride = false
) =>
  api
    .put<PreSessionQuizAssignment>(
      `/sessions/pre-quiz/assignments/${scope}/${ownerId}`,
      { preset_id: presetId },
      { params: { clear_override: clearOverride } }
    )
    .then((r) => r.data)

/* ── Cohort Readiness Pipeline API ─────────────────────────────────────────── */

export const getCohortPreQuizStatusApi = (cohortId: string) =>
  api.get<CohortPreQuizStatus>(`/sessions/cohorts/${cohortId}/pre-quiz`).then((r) => r.data)

export const startCohortPhaseApi = (cohortId: string, phaseId: string) =>
  api.post<PreSessionQuizAttempt>(`/sessions/cohorts/${cohortId}/pre-quiz/phases/${phaseId}/start`).then((r) => r.data)

export const submitCohortPhaseApi = (cohortId: string, phaseId: string, body: PhaseTrialSubmitIn) =>
  api
    .post<{ trial: PhaseTrial; attempt: PreSessionQuizAttempt }>(
      `/sessions/cohorts/${cohortId}/pre-quiz/phases/${phaseId}/submit`,
      body
    )
    .then((r) => r.data)

export const unlockCohortCooldownApi = (attemptId: string) =>
  api.post<PreSessionQuizAttempt>(`/sessions/pre-quiz/attempts/${attemptId}/unlock-cooldown`).then((r) => r.data)

/* ── Legacy Session Pre-Quiz & Ops Review API ──────────────────────────────── */

export const getSessionPreQuizStatusApi = (sessionId: string) =>
  api.get<SessionPreQuizStatus>(`/sessions/${sessionId}/pre-quiz`).then((r) => r.data)

export const submitSessionPreQuizApi = (sessionId: string, answers: PreSessionQuizAnswerIn[]) =>
  api
    .post<PreSessionQuizAttempt>(`/sessions/${sessionId}/pre-quiz/submit`, { answers })
    .then((r) => r.data)

export const reviewPreQuizAttemptQuestionApi = (
  attemptId: string,
  body: { question_id: string; is_correct: boolean; review_comment?: string | null }
) =>
  api
    .patch<PreSessionQuizAttempt>(`/sessions/pre-quiz/attempts/${attemptId}/review`, body)
    .then((r) => r.data)
