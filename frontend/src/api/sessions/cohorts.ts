import { api } from "@/api/client"
import type {
  Cohort,
  CohortStatus,
  CohortVisibility,
  GenerateSessionsResult,
  Session,
  SessionInstructor,
  Registration,
  DeskRegistrationInput,
} from "@/types/sessions"

export const getCohortsApi = (programId?: string) =>
  api.get<Cohort[]>("/sessions/cohorts", { params: programId ? { program_id: programId } : undefined })
    .then((r) => r.data)

export const getCohortApi = (id: string) =>
  api.get<Cohort>(`/sessions/cohorts/${id}`).then((r) => r.data)

export const createCohortApi = (data: {
  program_id: string
  name: string
  starts_on?: string
  ends_on?: string
  location?: string
  location_id?: string | null
  warehouse_id?: string | null
  capacity?: number
  status?: CohortStatus
  visibility?: CohortVisibility
  notes?: string
  poster_template_url?: string
}) => api.post<Cohort>("/sessions/cohorts", data).then((r) => r.data)

export const updateCohortApi = (
  id: string,
  data: Partial<{
    name: string
    starts_on: string | null
    ends_on: string | null
    location: string | null
    location_id: string | null
    warehouse_id: string | null
    capacity: number | null
    status: CohortStatus
    visibility: CohortVisibility
    notes: string | null
    poster_template_url: string | null
  }>
) => api.patch<Cohort>(`/sessions/cohorts/${id}`, data).then((r) => r.data)

export const generateSessionsApi = (
  cohortId: string,
  data: { weekdays: number[]; count: number; starts_at?: string | null }
) => api.post<GenerateSessionsResult>(`/sessions/cohorts/${cohortId}/sessions:generate`, data).then((r) => r.data)

export const getSessionsApi = (cohortId: string) =>
  api.get<Session[]>(`/sessions/cohorts/${cohortId}/sessions`).then((r) => r.data)

export const addSessionApi = (
  cohortId: string,
  data: { meeting_date: string; starts_at?: string | null; title?: string | null; material_url?: string | null; price?: number | null }
) => api.post<Session>(`/sessions/cohorts/${cohortId}/sessions`, data).then((r) => r.data)

export const updateSessionApi = (
  cohortId: string,
  sessionId: string,
  data: Partial<{
    meeting_date: string; starts_at: string | null; title: string | null
    material_url: string | null; price: number | null
    /** null clears the override back to "inherit the cohort's location". */
    location_id: string | null
    /** null clears the override back to "inherit the cohort's warehouse". */
    warehouse_id: string | null
  }>
) => api.patch<Session>(`/sessions/cohorts/${cohortId}/sessions/${sessionId}`, data).then((r) => r.data)

export const assignInstructorApi = (
  cohortId: string, sessionId: string, data: { user_id: string; role_id?: string }
) => api.post<SessionInstructor>(`/sessions/cohorts/${cohortId}/sessions/${sessionId}/instructors`, data).then((r) => r.data)

export const unassignInstructorApi = (cohortId: string, sessionId: string, userId: string) =>
  api.delete(`/sessions/cohorts/${cohortId}/sessions/${sessionId}/instructors/${userId}`).then((r) => r.data)

export interface BulkActionResult {
  succeeded: string[]
  failed: { session_id: string; detail: string }[]
}

/** Same instructor/role onto every listed session — a cohort with 100
 *  sessions shouldn't mean 100 taps. Partial failure doesn't roll back the
 *  rest; check `failed` for anything that didn't go through. */
export const bulkAssignInstructorApi = (
  cohortId: string, data: { session_ids: string[]; user_id: string; role_id?: string }
) => api.post<BulkActionResult>(`/sessions/cohorts/${cohortId}/sessions/bulk-assign-instructor`, data).then((r) => r.data)

export const bulkOpenCallApi = (
  cohortId: string, data: { session_ids: string[]; target_user_ids?: string[]; role_ids?: string[] }
) => api.post<BulkActionResult>(`/sessions/cohorts/${cohortId}/sessions/bulk-open-call`, data).then((r) => r.data)

export const getRegistrationsApi = (cohortId: string) =>
  api.get<Registration[]>(`/sessions/cohorts/${cohortId}/registrations`).then((r) => r.data)

export const deskRegisterApi = (cohortId: string, data: DeskRegistrationInput) =>
  api.post(`/sessions/cohorts/${cohortId}/registrations`, data).then((r) => r.data)

export const resendTicketApi = (registrationId: string) =>
  api.post(`/sessions/registrations/${registrationId}/resend-ticket`).then((r) => r.data)

export const cancelRegistrationApi = (registrationId: string) =>
  api.post(`/sessions/registrations/${registrationId}/cancel`).then((r) => r.data)

export const confirmPaymentApi = (
  registrationId: string,
  data: { amount: number; status?: "paid" | "partial" }
) => api.post(`/sessions/registrations/${registrationId}/confirm-payment`, data).then((r) => r.data)

// Manual override (operator request 2026-07-25) — issues a certificate to a
// registration regardless of whether it met the program's completion rule.
export const giveCertificateApi = (registrationId: string) =>
  api.post<{ id: string; status: string; certificate_url: string }>(`/sessions/registrations/${registrationId}/certificate`).then((r) => r.data)

// One merged PDF, one page per registered student in this cohort.
export const downloadCohortCertificatesApi = async (cohortId: string, cohortName: string, theme: "dark" | "light") => {
  const res = await api.get(`/sessions/cohorts/${cohortId}/certificates/download`, {
    responseType: "blob", params: { theme },
  })
  const url = URL.createObjectURL(res.data as Blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `certificates_${cohortName.replace(/[^a-z0-9]+/gi, "_")}.pdf`
  a.click()
  URL.revokeObjectURL(url)
}

/** 409 if anyone has registered — cancel the cohort instead to keep history. */
export const deleteCohortApi = (id: string) =>
  api.delete<void>(`/sessions/cohorts/${id}`).then((r) => r.data)

/** 409 if attendance has been recorded for the session. */
export const deleteSessionApi = (cohortId: string, sessionId: string) =>
  api.delete<void>(`/sessions/cohorts/${cohortId}/sessions/${sessionId}`).then((r) => r.data)

/** Erases a sign-up along with its attendance and certificate — the
 *  destructive counterpart to cancel, for rows that shouldn't exist.
 *  deleteContact also removes the person from Contacts; that 409s if they hold
 *  a staff account or are registered in other cohorts. */
export const deleteRegistrationApi = (registrationId: string, deleteContact = false) =>
  api
    .delete<void>(`/sessions/registrations/${registrationId}`, { params: { delete_contact: deleteContact } })
    .then((r) => r.data)

export interface SessionHistoryMovement {
  id: string
  reason: string
  subject: string
  is_kit: boolean
  qty: number | null
  from_warehouse_name?: string | null
  to_warehouse_name?: string | null
  from_location_name?: string | null
  to_location_name?: string | null
  actor_name: string
  actor_role: string
  created_at?: string | null
  due_back_on?: string | null
  note?: string | null
}

export interface SessionHistoryKitCheck {
  id: string
  kit_id: string
  kit_label: string
  phase: string
  skipped: boolean
  actor_name: string
  actor_role: string
  counts: Record<string, number>
  missing: Record<string, number>
  note?: string | null
  created_at?: string | null
}

export interface SessionHistoryResponse {
  session_id: string
  started_at?: string | null
  completed_at?: string | null
  notes?: string | null
  pre_session: {
    movements: SessionHistoryMovement[]
    kit_checks: SessionHistoryKitCheck[]
  }
  during_session: {
    attendance: {
      present: number
      absent: number
      late: number
      excused: number
      total: number
      records: { registration_id: string; student_name: string; status: string; marked_at?: string | null }[]
    }
  }
  post_session: {
    movements: SessionHistoryMovement[]
    kit_checks: SessionHistoryKitCheck[]
    reports: { id: string; file_url: string; notes?: string | null; actor_name: string; actor_role: string; created_at?: string | null }[]
    addons: any[]
  }
}

export const getSessionHistoryApi = (sessionId: string) =>
  api.get<SessionHistoryResponse>(`/sessions/${sessionId}/history`).then((r) => r.data)
