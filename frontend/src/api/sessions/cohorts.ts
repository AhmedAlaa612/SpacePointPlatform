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
  capacity?: number
  status?: CohortStatus
  visibility?: CohortVisibility
  notes?: string
}) => api.post<Cohort>("/sessions/cohorts", data).then((r) => r.data)

export const updateCohortApi = (
  id: string,
  data: Partial<{
    name: string
    starts_on: string | null
    ends_on: string | null
    location: string | null
    capacity: number | null
    status: CohortStatus
    visibility: CohortVisibility
    notes: string | null
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
  data: Partial<{ meeting_date: string; starts_at: string | null; title: string | null; material_url: string | null; price: number | null }>
) => api.patch<Session>(`/sessions/cohorts/${cohortId}/sessions/${sessionId}`, data).then((r) => r.data)

export const assignInstructorApi = (
  cohortId: string, sessionId: string, data: { user_id: string; role?: "lead" | "co" }
) => api.post<SessionInstructor>(`/sessions/cohorts/${cohortId}/sessions/${sessionId}/instructors`, data).then((r) => r.data)

export const unassignInstructorApi = (cohortId: string, sessionId: string, userId: string) =>
  api.delete(`/sessions/cohorts/${cohortId}/sessions/${sessionId}/instructors/${userId}`).then((r) => r.data)

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
