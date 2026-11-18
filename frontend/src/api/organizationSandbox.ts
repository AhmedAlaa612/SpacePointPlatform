import { api } from "./client"

/** Organization sandbox staffing — org instructors, judges and readiness.
 *  Backed by `/organization/cohorts/{id}/...` (2026-11-18). */

export interface OrgCohortStaffSession {
  id: string
  title: string
  meeting_date: string | null
  started_at: string | null
  completed_at: string | null
  staffing_status: string
  attendance_present?: number
  attendance_absent?: number
  attendance_total?: number
  instructors?: { user_id: string; full_name: string }[]
}

export interface OrgInstructorReadiness {
  status: string
  final_score: number
  total_questions: number
  submitted_at: string | null
  passed: boolean
}

export interface OrgCohortStaffInstructor {
  user_id: string
  full_name: string
  email: string
  phone: string | null
  status: string
  session_ids: string[]
  sessions_count: number
  completed_sessions: number
  attendance_present: number
  attendance_absent: number
  roles: string[]
  readiness: OrgInstructorReadiness | null
}

export interface OrgCohortStaffJudge {
  user_id: string
  full_name: string
  email: string
  phone: string | null
  status: string
  onboarding_sent_at: string | null
}

export interface OrgCohortStaff {
  cohort_id: string
  sessions: OrgCohortStaffSession[]
  instructors: OrgCohortStaffInstructor[]
  judges: OrgCohortStaffJudge[]
}

export interface OrgReadinessPreset {
  id: string
  name: string
  description: string | null
  preset_type: string | null
  passing_score_percent?: number | null
  question_count: number
  phases_count: number
  is_own?: boolean
}

export interface OrgReadinessQuestionInput {
  prompt: string
  question_type: "mcq" | "written"
  options?: { text: string; is_correct: boolean }[]
  explanation?: string | null
  critical?: boolean
}

export interface OrgReadinessPresetCreateInput {
  name: string
  description?: string | null
  passing_score_percent?: number
  cohort_id?: string
  questions: OrgReadinessQuestionInput[]
}

export interface OrgReadinessInstructor {
  user_id: string
  full_name: string
  email: string
  status: string
  final_score: number
  total_questions: number
  pending_review_count: number
  submitted_at: string | null
  passed: boolean
}

export interface OrgCohortReadiness {
  preset: Pick<OrgReadinessPreset, "id" | "name" | "description" | "question_count"> | null
  instructors: OrgReadinessInstructor[]
}

export const getOrgCohortStaff = (cohortId: string) =>
  api.get<OrgCohortStaff>(`/organization/cohorts/${cohortId}/staff`).then((r) => r.data)

export const assignOrgInstructor = (
  cohortId: string,
  payload: { user_id: string; session_ids?: string[]; role_id?: string },
) =>
  api
    .post<{ assigned: number }>(`/organization/cohorts/${cohortId}/instructors`, payload)
    .then((r) => r.data)

export const unassignOrgInstructor = (cohortId: string, userId: string, sessionId?: string) =>
  api.delete(`/organization/cohorts/${cohortId}/instructors/${userId}`, {
    params: sessionId ? { session_id: sessionId } : undefined,
  })

export const assignOrgJudge = (cohortId: string, userId: string) =>
  api
    .post<{ assigned: boolean }>(`/organization/cohorts/${cohortId}/judges`, { user_id: userId })
    .then((r) => r.data)

export const unassignOrgJudge = (cohortId: string, userId: string) =>
  api.delete(`/organization/cohorts/${cohortId}/judges/${userId}`)

export const getOrgReadinessPresets = (cohortId?: string) =>
  api
    .get<OrgReadinessPreset[]>("/organization/readiness-presets", {
      params: cohortId ? { cohort_id: cohortId } : undefined,
    })
    .then((r) => r.data)

export const createOrgReadinessPreset = (payload: OrgReadinessPresetCreateInput) =>
  api.post<OrgReadinessPreset>("/organization/readiness-presets", payload).then((r) => r.data)

export const deleteOrgReadinessPreset = (presetId: string, cohortId?: string) =>
  api.delete(`/organization/readiness-presets/${presetId}`, {
    params: cohortId ? { cohort_id: cohortId } : undefined,
  })

export const getOrgCohortReadiness = (cohortId: string) =>
  api.get<OrgCohortReadiness>(`/organization/cohorts/${cohortId}/readiness`).then((r) => r.data)

export const setOrgCohortReadiness = (cohortId: string, presetId: string | null) =>
  api
    .put(`/organization/cohorts/${cohortId}/readiness`, { preset_id: presetId })
    .then((r) => r.data)
