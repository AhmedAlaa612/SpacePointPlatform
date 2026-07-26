/** Staffing marketplace endpoints (V2 W4 S4-2), mirroring
 * backend/app/routers/sessions/staffing.py. Session-scoped throughout. */

import { api } from "@/api/client"
import type {
  Session,
  InstructorInterest,
  EligibleInstructor,
  SelectInstructorsResult,
  AvailableSession,
  MySession,
} from "@/types/sessions"

// ── Instructor: available sessions / my sessions ────────────────────────────

export const listAvailableSessionsApi = () =>
  api.get<AvailableSession[]>("/sessions/available").then((r) => r.data)

export const listMySessionsApi = () =>
  api.get<MySession[]>("/sessions/mine").then((r) => r.data)

// ── Ops: open call / reopen ─────────────────────────────────────────────────

export const openCallApi = (sessionId: string, userIds?: string[]) =>
  api.post<Session>(`/sessions/${sessionId}/staffing/open-call`, { user_ids: userIds }).then((r) => r.data)

export const openCallForCohortApi = (cohortId: string, userIds?: string[]) =>
  api.post<Session[]>(`/sessions/cohorts/${cohortId}/staffing/open-call`, { user_ids: userIds }).then((r) => r.data)

export const reopenStaffingApi = (sessionId: string) =>
  api.post<Session>(`/sessions/${sessionId}/staffing/reopen`).then((r) => r.data)

export const closeCallApi = (sessionId: string, clearInterest: boolean = false) =>
  api.post<Session>(`/sessions/${sessionId}/staffing/close-call`, { clear_interest: clearInterest }).then((r) => r.data)

// ── Instructor/facilitator: register / withdraw interest ───────────────────

export const registerInterestApi = (sessionId: string, note?: string) =>
  api.post<InstructorInterest>(`/sessions/${sessionId}/staffing/interest`, { note }).then((r) => r.data)

export const withdrawInterestApi = (sessionId: string) =>
  api.delete(`/sessions/${sessionId}/staffing/interest`).then((r) => r.data)

export const declineAssignmentApi = (sessionId: string, reason?: string) =>
  api.post(`/sessions/${sessionId}/staffing/decline`, { reason }).then((r) => r.data)

// ── Ops: interest list, full eligible roster, select ────────────────────────

export const listInterestApi = (sessionId: string) =>
  api.get<InstructorInterest[]>(`/sessions/${sessionId}/staffing/interest`).then((r) => r.data)

export const listEligibleInstructorsApi = (sessionId: string) =>
  api.get<EligibleInstructor[]>(`/sessions/${sessionId}/staffing/eligible-instructors`).then((r) => r.data)

export const selectInstructorsApi = (sessionId: string, userIds: string[], role: "lead" | "co" = "lead") =>
  api.post<SelectInstructorsResult>(`/sessions/${sessionId}/staffing/select`, { user_ids: userIds, role }).then((r) => r.data)
