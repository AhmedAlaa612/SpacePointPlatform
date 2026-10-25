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
  question_type: "pinout_table" | "mcq"
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
  question_type: "pinout_table" | "mcq"
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
  id?: string | null
  title: string
  url: string
  is_file: boolean
}

export interface PreSessionQuizPreset {
  id: string
  name: string
  description?: string | null
  question_ids: string[]
  reference_attachments: ReferenceAttachment[]
  questions: PreSessionQuizQuestion[]
  is_active: boolean
  created_at?: string | null
}

export interface PreSessionQuizPresetIn {
  name: string
  description?: string | null
  question_ids: string[]
  reference_attachments: ReferenceAttachment[]
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
}

export interface PreSessionQuizAnswerRecord {
  question_id: string
  selected_option_index?: number | null
  selected_cells?: number[][] | null
  chose_other: boolean
  other_text?: string | null
  status: "correct" | "incorrect" | "pending_review"
  reviewed_by?: string | null
  reviewed_at?: string | null
  review_comment?: string | null
}

export interface PreSessionQuizAttempt {
  id: string
  session_id: string
  preset_id?: string | null
  user_id: string
  user_name?: string | null
  answers: PreSessionQuizAnswerRecord[]
  auto_score: number
  final_score: number
  total_questions: number
  pending_review_count: number
  submitted_at?: string | null
}

export interface SessionPreQuizStatus {
  has_quiz: boolean
  preset?: PreSessionQuizPreset | null
  my_attempt?: PreSessionQuizAttempt | null
  all_attempts: PreSessionQuizAttempt[]
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

/* ── Session Delivery & Ops Review API ─────────────────────────────────────── */

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
