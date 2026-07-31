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

export const openCallApi = (sessionId: string, userIds?: string[], roleIds?: string[]) =>
  api.post<Session>(`/sessions/${sessionId}/staffing/open-call`, {
    user_ids: userIds, role_ids: roleIds,
  }).then((r) => r.data)

export const openCallForCohortApi = (cohortId: string, userIds?: string[]) =>
  api.post<Session[]>(`/sessions/cohorts/${cohortId}/staffing/open-call`, { user_ids: userIds }).then((r) => r.data)

/** Targeting carries over by default. Pass [] to widen the call to everyone,
 *  or a list of user ids to re-aim it. Same shape for role_ids (B2) — the
 *  common case is reopening for just the roles still needed. */
export const reopenStaffingApi = (sessionId: string, targetUserIds?: string[], roleIds?: string[]) =>
  api
    .post<Session>(
      `/sessions/${sessionId}/staffing/reopen`,
      targetUserIds === undefined && roleIds === undefined
        ? undefined
        : { user_ids: targetUserIds, role_ids: roleIds },
    )
    .then((r) => r.data)

export const closeCallApi = (sessionId: string, clearInterest: boolean = false) =>
  api.post<Session>(`/sessions/${sessionId}/staffing/close-call`, { clear_interest: clearInterest }).then((r) => r.data)

// ── Instructor/facilitator: register / withdraw interest ───────────────────

export const registerInterestApi = (sessionId: string, note?: string, roleId?: string | null) =>
  api.post<InstructorInterest>(`/sessions/${sessionId}/staffing/interest`, { note, role_id: roleId ?? null }).then((r) => r.data)

export const withdrawInterestApi = (sessionId: string) =>
  api.delete(`/sessions/${sessionId}/staffing/interest`).then((r) => r.data)

export const declineAssignmentApi = (sessionId: string, reason?: string) =>
  api.post(`/sessions/${sessionId}/staffing/decline`, { reason }).then((r) => r.data)

// ── Ops: interest list, full eligible roster, select ────────────────────────

export const listInterestApi = (sessionId: string) =>
  api.get<InstructorInterest[]>(`/sessions/${sessionId}/staffing/interest`).then((r) => r.data)

export const listEligibleInstructorsApi = (sessionId: string) =>
  api.get<EligibleInstructor[]>(`/sessions/${sessionId}/staffing/eligible-instructors`).then((r) => r.data)

/** closeCall=false leaves the session at open_call so more instructors can
 *  still register interest while ops assigns people one at a time. */
export const selectInstructorsApi = (sessionId: string, userIds: string[], roleId?: string, closeCall = true) =>
  api.post<SelectInstructorsResult>(`/sessions/${sessionId}/staffing/select`, { user_ids: userIds, role_id: roleId ?? null, close_call: closeCall }).then((r) => r.data)
