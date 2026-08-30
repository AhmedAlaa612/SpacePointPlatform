/** Staffing marketplace endpoints (V2 W4 S4-2), mirroring
 * backend/app/routers/sessions/staffing.py. Session-scoped throughout. */

import { api } from "@/api/client"
import type {
  Session,
  InstructorInterest,
  EligibleInstructor,
  SelectInstructorsResult,
  AvailableSession,
  AvailableWork,
  CohortAssignment,
  CohortCallApplicant,
  MySession,
  RegisterCohortInterestBody,
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

/** Re-posting replaces the previous answer — same "changing your answer is
 *  normal, not an error" contract `registerCohortInterestApi` uses below. */
export const registerInterestApi = (sessionId: string, body: {
  note?: string | null
  role_id?: string | null
  needs_transport?: boolean
  needs_ops_support?: boolean
  travelling_from_other_city?: boolean
  concerns?: string | null
}) =>
  api.post<InstructorInterest>(`/sessions/${sessionId}/staffing/interest`, body).then((r) => r.data)

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

/* ── Cohort-level staffing (2026-08-24) ──────────────────────────────────────
 * The cohort layer over the session-scoped marketplace above: ops opens one
 * call across a set of sessions, the instructor answers it once, and ops picks
 * from one table instead of N. Mirrors the routes added in
 * backend/app/routers/sessions/staffing.py. */

/** Everything this instructor can apply for: cohort cards plus any session
 *  opened on its own. A session never appears in both lists.
 *  `listAvailableSessionsApi` above still works and is unchanged — this is
 *  additive, so nothing breaks mid-release. */
export const listAvailableWorkApi = () =>
  api.get<AvailableWork>("/sessions/available-work").then((r) => r.data)

/** One answer to a cohort call. Re-posting replaces the previous answer —
 *  changing which days you can do is the normal case, not an error. */
export const registerCohortInterestApi = (
  cohortId: string, cohortCallId: string, body: RegisterCohortInterestBody,
) =>
  api.post<CohortCallApplicant>(
    `/sessions/cohorts/${cohortId}/staffing/calls/${cohortCallId}/interest`, body,
  ).then((r) => r.data)

export const withdrawCohortInterestApi = (cohortId: string, cohortCallId: string) =>
  api.delete(
    `/sessions/cohorts/${cohortId}/staffing/calls/${cohortCallId}/interest`,
  ).then((r) => r.data)

/** The ops applicant table — one row per instructor, with the days they
 *  ticked and their support requirements. */
export const listCohortApplicantsApi = (cohortId: string, cohortCallId: string) =>
  api.get<CohortCallApplicant[]>(
    `/sessions/cohorts/${cohortId}/staffing/calls/${cohortCallId}/interest`,
  ).then((r) => r.data)

/** Assign people to a cohort in one action. Omit `role_id` to use whichever
 *  role each applicant asked for; omit `session_ids` to give each of them
 *  exactly the days they ticked. 409s (naming the clash) if somebody already
 *  holds a different role in this cohort. */
export const selectForCohortApi = (cohortId: string, body: {
  user_ids: string[]
  role_id?: string | null
  session_ids?: string[] | null
  cohort_call_id?: string | null
  close_call?: boolean
  rate_basis?: "per_session" | "flat"
  flat_amount_aed?: number | null
}) => api.post<{
  user_id: string; role_id: string; session_ids: string[]
  rate_aed: number | null; rate_basis: string; flat_amount_aed: number | null
}[]>(`/sessions/cohorts/${cohortId}/staffing/select`, body).then((r) => r.data)

export const listCohortAssignmentsApi = (cohortId: string) =>
  api.get<CohortAssignment[]>(
    `/sessions/cohorts/${cohortId}/staffing/assignments`,
  ).then((r) => r.data)

/** Marks the assignment withdrawn (never deletes it — that they were staffed
 *  is part of the record) and drops their session rows. */
export const removeCohortAssignmentApi = (cohortId: string, userId: string) =>
  api.delete(
    `/sessions/cohorts/${cohortId}/staffing/assignments/${userId}`,
  ).then((r) => r.data)
