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
  StaffingStatus,
} from "@/types/sessions"
import type { BulkActionResult } from "@/api/sessions/cohorts"

// ── Instructor: available sessions / my sessions ────────────────────────────

export const listAvailableSessionsApi = () =>
  api.get<AvailableSession[]>("/sessions/available").then((r) => r.data)

export const listMySessionsApi = () =>
  api.get<MySession[]>("/sessions/mine").then((r) => r.data)

// ── Ops: open call / reopen ─────────────────────────────────────────────────

/** Opens a new call on this session (2026-08-01: safe to call again while
 *  already open_call — a session can run several calls at once, e.g. a
 *  targeted call for one missing role alongside a public one). */
export const openCallApi = (sessionId: string, userIds?: string[], roleIds?: string[], label?: string) =>
  api.post<Session>(`/sessions/${sessionId}/staffing/open-call`, {
    user_ids: userIds, role_ids: roleIds, label,
  }).then((r) => r.data)

/* ── cohort-level "grouped" calls (2026-08-01) ───────────────────────────
 * A single call spanning several sessions at once, manageable and closeable
 * as one entity. As of 2026-08-02 this is the ONLY way to open a call across
 * several sessions: `openCallForCohortApi` (and the endpoint behind it) is
 * gone, because calls it opened never showed up in the panel that manages
 * them. Per-session calls still go through `openCallApi` above — a
 * session-level call is just a call whose session set is one. */

export interface CohortCallSession {
  session_id: string
  meeting_date: string
  starts_at: string | null
  status: "open" | "closed"
  staffing_status: StaffingStatus
}

export interface CohortCall {
  id: string
  cohort_id: string
  status: "open" | "closed"
  label: string | null
  target_user_ids: string[]
  sessions: CohortCallSession[]
  created_at: string | null
  closed_at: string | null
}

export const openCohortCallApi = (cohortId: string, body: {
  session_ids?: string[]; user_ids?: string[]; role_ids?: string[]; label?: string
}) => api.post<{ call: CohortCall; failed: BulkActionResult["failed"] }>(
  `/sessions/cohorts/${cohortId}/staffing/calls`, body,
).then((r) => r.data)

export const listCohortCallsApi = (cohortId: string) =>
  api.get<CohortCall[]>(`/sessions/cohorts/${cohortId}/staffing/calls`).then((r) => r.data)

export const closeCohortCallApi = (cohortId: string, callId: string, body: {
  session_ids?: string[]; clear_interest?: boolean
} = {}) => api.post<CohortCall>(
  `/sessions/cohorts/${cohortId}/staffing/calls/${callId}/close`, body,
).then((r) => r.data)

/** Tidy up a closed cohort call — refused (409) while it's still open. */
export const deleteCohortCallApi = (cohortId: string, callId: string) =>
  api.delete(`/sessions/cohorts/${cohortId}/staffing/calls/${callId}`).then((r) => r.data)

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

/** Closes every call currently open on this session at once — the original
 *  one-button behaviour. To close just one call while others stay open, use
 *  closeOneCallApi below. */
export const closeCallApi = (sessionId: string, clearInterest: boolean = false) =>
  api.post<Session>(`/sessions/${sessionId}/staffing/close-call`, { clear_interest: clearInterest }).then((r) => r.data)

/* ── individual calls (2026-08-01) — a session can have several open ────── */

export interface SessionCall {
  id: string
  session_id: string
  status: "open" | "closed"
  label: string | null
  target_user_ids: string[]
  created_at: string | null
  closed_at: string | null
}

export const listSessionCallsApi = (sessionId: string) =>
  api.get<SessionCall[]>(`/sessions/${sessionId}/staffing/calls`).then((r) => r.data)

export const closeOneCallApi = (sessionId: string, callId: string, clearInterest: boolean = false) =>
  api.post<Session>(`/sessions/${sessionId}/staffing/calls/${callId}/close`, { clear_interest: clearInterest }).then((r) => r.data)

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
