/** Instructor daily loop (operations process doc §4-§12), mirroring
 * backend/app/routers/sessions/day.py.
 *
 * The flow: check in (or declare an absence), work the resolved checklist
 * uploading proof where an item demands it, submit the day, then ops approves
 * it or returns it with a comment. That approval is what makes a day a *paid*
 * day, which is why it also triggers cohort completion server-side. */

import { api } from "@/api/client"
import type {
  ChecklistItem,
  DayDetail,
  DayReview,
  InstructorAttendance,
  SessionBoard,
  SessionGameRun,
} from "@/types/sessions"

// ── ops: checklist templates ────────────────────────────────────────────────

export type ChecklistScope = "programs" | "cohorts" | "sessions"

/** One (level, role) bucket — the management view, no inheritance applied.
 *  Omit `roleId` for the general bucket; pass a role to see that role's own
 *  list. What actually resolves for an instructor comes back on the day. */
export const listChecklistItemsApi = (scope: ChecklistScope, ownerId: string, roleId?: string | null) =>
  api.get<ChecklistItem[]>(`/sessions/${scope}/${ownerId}/checklist-items`, {
    params: roleId ? { role_id: roleId } : {},
  }).then((r) => r.data)

/** Whole-bucket replace, like openings. Saving an empty list clears this
 *  (level, role) bucket, which makes the fallback apply again — general at
 *  this level if a role's list is cleared, or the level above if the general
 *  one is cleared. That is how you go back to inheriting rather than
 *  overriding. */
export const setChecklistItemsApi = (
  scope: ChecklistScope,
  ownerId: string,
  items: {
    title: string
    description?: string | null
    requires_proof?: boolean
    is_required?: boolean
    sort_order?: number | null
  }[],
  roleId?: string | null,
) =>
  api.put<ChecklistItem[]>(`/sessions/${scope}/${ownerId}/checklist-items`, { items }, {
    params: roleId ? { role_id: roleId } : {},
  }).then((r) => r.data)

// ── instructor: the day ─────────────────────────────────────────────────────

/** `forUserId` is ops-only — it opens somebody else's day from the review
 *  queue. An instructor passing it gets their own day back regardless. */
export const getDayApi = (sessionId: string, forUserId?: string) =>
  api.get<DayDetail>(`/sessions/${sessionId}/delivery/day`, {
    params: forUserId ? { for_user_id: forUserId } : undefined,
  }).then((r) => r.data)

export const checkInApi = (sessionId: string, attStatus: InstructorAttendance, reason?: string) =>
  api.post<DayDetail>(`/sessions/${sessionId}/delivery/check-in`, {
    att_status: attStatus, reason: reason ?? null,
  }).then((r) => r.data)

/** Tick an item, attach proof, or both. `proof_report_id` is a session-report
 *  row id — upload through the existing report endpoint first, then point
 *  here, rather than a second upload path. */
export const setChecklistProgressApi = (sessionId: string, itemId: string, body: {
  is_done?: boolean
  proof_report_id?: string | null
  note?: string | null
}) =>
  api.put<DayDetail>(`/sessions/${sessionId}/delivery/checklist/${itemId}`, body)
    .then((r) => r.data)

/** 409s listing everything outstanding if a required item isn't ticked or a
 *  proof-required one has no file. */
export const submitDayApi = (sessionId: string, notes?: string) =>
  api.post<DayDetail>(`/sessions/${sessionId}/delivery/day/submit`, { notes: notes ?? null })
    .then((r) => r.data)

// ── ops: the review queue ───────────────────────────────────────────────────

/** Defaults to what needs attention now. Pass `statusFilter: ""` for
 *  everything, and a cohort id or a session id to scope it — the latter is
 *  a session's own Report tab, every assigned instructor's report whatever
 *  state it's in. */
export const listDayReviewsApi = (opts: { statusFilter?: string; cohortId?: string; sessionId?: string } = {}) =>
  api.get<DayReview[]>("/sessions/day-reviews", {
    params: {
      status_filter: opts.statusFilter ?? "submitted",
      ...(opts.cohortId ? { cohort_id: opts.cohortId } : {}),
      ...(opts.sessionId ? { session_id: opts.sessionId } : {}),
    },
  }).then((r) => r.data)

/** Signing a day off is what makes it a paid day. `cohort_completed` tells you
 *  whether this approval was the one that completed the cohort — which also
 *  issued its certificates and drafted its payment lines. */
export const approveDayApi = (dayId: string) =>
  api.post<{ day_id: string; status: string; cohort_completed: boolean }>(
    `/sessions/day-reviews/${dayId}/approve`,
  ).then((r) => r.data)

export const returnDayApi = (dayId: string, comment: string) =>
  api.post<{ day_id: string; status: string; review_comment: string | null }>(
    `/sessions/day-reviews/${dayId}/return`, { comment },
  ).then((r) => r.data)

// ── ops: the session board ──────────────────────────────────────────────────

/** Running/Done across every cohort. Needs Review is `listDayReviewsApi` —
 *  the board page calls both. */
export const getSessionBoardApi = (opts: { doneOffset?: number; doneLimit?: number } = {}) =>
  api.get<SessionBoard>("/sessions/board", {
    params: { done_offset: opts.doneOffset ?? 0, done_limit: opts.doneLimit ?? 5 },
  }).then((r) => r.data)

/** Live-quiz runs on this session, most recent first — part of the Report
 *  tab's "warehouse & session activity" strip. */
export const listSessionGameRunsApi = (sessionId: string) =>
  api.get<SessionGameRun[]>(`/sessions/${sessionId}/game-runs`).then((r) => r.data)
