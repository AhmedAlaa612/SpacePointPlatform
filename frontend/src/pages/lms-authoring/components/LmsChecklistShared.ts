import { isAxiosError } from "axios"
import { BookOpen, Rocket, Link2, Upload, FileText, ClipboardCheck, Calendar, HelpCircle, Users, Flag } from "lucide-react"
import { MISSION_STEP_KEYS, type LmsProgramItem, type LmsProgramItemInput, type LmsProgramItemType } from "@/api/lms_admin"

export function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

/** Stored deadline is a UTC ISO string — render it into a `datetime-local`
 * input's local-time value, same conversion direction TeacherPortal's own
 * `datetime-local` field uses in reverse (`new Date(value).toISOString()`
 * going back out on save). */
export function toDatetimeLocalValue(iso: string | null | undefined): string {
  if (!iso) return ""
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ""
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Roadmap-board-safe round-trip of an existing item back into the PATCH
 * shape — the endpoint replaces every field from `model_dump()`, so a
 * partial `{ gated: true }` body would blow away the rest of the row
 * (course_id, guideline fields, etc.) back to their schema defaults. Used
 * by the "Gate everything in order" bulk action, which only means to
 * flip one field per item. */
export function itemToInput(item: LmsProgramItem): LmsProgramItemInput {
  return {
    item_type: item.item_type, title: item.title, description: item.description,
    optional: item.optional, requires_confirmation: item.requires_confirmation, scope: item.scope,
    course_id: item.course_id, mission_id: item.mission_id, variant_id: item.variant_id,
    external_url: item.external_url, submission_prompt: item.submission_prompt,
    submission_multi_link: item.submission_multi_link,
    submission_link_labels: item.submission_link_labels,
    deadline_at: item.deadline_at, session_date: item.session_date, session_starts_at: item.session_starts_at,
    session_location: item.session_location, session_meeting_url: item.session_meeting_url,
    cohort_quiz_template_id: item.cohort_quiz_template_id,
    mission_step_key: item.mission_step_key, gated: item.gated, guideline_kind: item.guideline_kind,
    guideline_url: item.guideline_url, checkpoint_label: item.checkpoint_label,
  }
}

export const ITEM_TYPES: { value: LmsProgramItemType; label: string; icon: typeof BookOpen }[] = [
  { value: "course", label: "Course", icon: BookOpen },
  { value: "mission_run", label: "Mission run", icon: Rocket },
  { value: "external_link", label: "Link", icon: Link2 },
  { value: "submission", label: "Submission", icon: Upload },
  { value: "pdf", label: "PDF", icon: FileText },
  { value: "manual", label: "Manual check-off", icon: ClipboardCheck },
  { value: "session", label: "Session", icon: Calendar },
  { value: "quiz", label: "Quiz", icon: HelpCircle },
  { value: "team_setup", label: "Team setup", icon: Users },
  { value: "checkpoint", label: "Checkpoint", icon: Flag },
]

// Mirrors the server-side rule in services/lms/program.py: a link-only
// deliverable can be shared as one team-wide submission, and (Phase 2,
// 2026-09) a mission_run can be a team run sharing one MissionAttempt —
// course/pdf/session stay individual on purpose (see that rule's own
// comment for why).
export const TEAM_SCOPABLE_TYPES = new Set<LmsProgramItemType>(["submission", "external_link", "manual", "mission_run"])

export const ITEM_TYPE_META: Record<LmsProgramItemType, { label: string; icon: typeof BookOpen }> = Object.fromEntries(
  ITEM_TYPES.map((t) => [t.value, { label: t.label, icon: t.icon }]),
) as Record<LmsProgramItemType, { label: string; icon: typeof BookOpen }>

// The Roadmap board tile a design mission's phase picker offers — the
// client's own instruction: "data, link, and cost will not be used for
// this competition." MISSION_STEP_KEYS (api/lms_admin.ts) keeps the full
// backend vocabulary; this is just what the picker shows.
export const PHASE_PICKER_KEYS = MISSION_STEP_KEYS.filter((s) => !["data_budget", "link_budget", "cost_budget"].includes(s.value))
