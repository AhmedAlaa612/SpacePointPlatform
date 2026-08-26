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
} from "@/types/sessions"

// ── ops: checklist templates ────────────────────────────────────────────────

export type ChecklistScope = "programs" | "cohorts" | "sessions"

/** Items attached at this level only — the management view, no inheritance
 *  applied. What actually resolves for a session comes back on the day. */
export const listChecklistItemsApi = (scope: ChecklistScope, ownerId: string) =>
  api.get<ChecklistItem[]>(`/sessions/${scope}/${ownerId}/checklist-items`).then((r) => r.data)

/** Whole-set replace, like openings. Saving an empty list clears this level,
 *  which makes the level above apply again — that is how you go back to
 *  inheriting rather than overriding. */
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
) =>
  api.put<ChecklistItem[]>(`/sessions/${scope}/${ownerId}/checklist-items`, { items })
    .then((r) => r.data)

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
 *  everything, or a cohort id to scope it. */
export const listDayReviewsApi = (opts: { statusFilter?: string; cohortId?: string } = {}) =>
  api.get<DayReview[]>("/sessions/day-reviews", {
    params: {
      status_filter: opts.statusFilter ?? "submitted",
      ...(opts.cohortId ? { cohort_id: opts.cohortId } : {}),
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
