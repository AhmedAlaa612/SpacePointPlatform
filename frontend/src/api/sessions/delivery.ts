/** Instructor session delivery endpoints (V2 W5 S5-1), mirroring
 * backend/app/routers/sessions/delivery.py. Session-scoped throughout. */

import { api } from "@/api/client"
import type { AttendanceResult, AttendanceStatus, CompleteCohortResult, SessionDelivery, SessionReport } from "@/types/sessions"

export const getSessionDeliveryApi = (sessionId: string) =>
  api.get<SessionDelivery>(`/sessions/${sessionId}/delivery`).then((r) => r.data)

export const startSessionApi = (sessionId: string) =>
  api.post<SessionDelivery>(`/sessions/${sessionId}/delivery/start`).then((r) => r.data)

export const markSessionDoneApi = (sessionId: string) =>
  api.post<SessionDelivery>(`/sessions/${sessionId}/delivery/done`).then((r) => r.data)

/** The session's comment box. Sends the whole text — it is one text area,
 *  not a log. An empty string clears it. */
export const updateSessionNotesApi = (sessionId: string, notes: string) =>
  api.put<SessionDelivery>(`/sessions/${sessionId}/delivery/notes`, { notes }).then((r) => r.data)

export const markAttendanceApi = (sessionId: string, registrationId: string, attStatus: AttendanceStatus) =>
  api.put<AttendanceResult>(`/sessions/${sessionId}/delivery/attendance/${registrationId}`, { att_status: attStatus }).then((r) => r.data)

export const scanAttendanceApi = (sessionId: string, token: string) =>
  api.post<AttendanceResult>(`/sessions/${sessionId}/delivery/scan`, { token }).then((r) => r.data)

// ── Session reports (W5 S5-2) ────────────────────────────────────────────────

export const uploadSessionReportApi = (cohortId: string, data: { file: File; sessionId?: string; notes?: string }) => {
  const form = new FormData()
  form.append("file", data.file)
  if (data.sessionId) form.append("session_id", data.sessionId)
  if (data.notes) form.append("notes", data.notes)
  // No explicit Content-Type — axios sets the multipart boundary itself.
  return api.post<SessionReport>(`/sessions/cohorts/${cohortId}/reports`, form).then((r) => r.data)
}

export const listCohortReportsApi = (cohortId: string) =>
  api.get<SessionReport[]>(`/sessions/cohorts/${cohortId}/reports`).then((r) => r.data)

export const completeCohortApi = (cohortId: string) =>
  api.post<CompleteCohortResult>(`/sessions/cohorts/${cohortId}/complete`).then((r) => r.data)
