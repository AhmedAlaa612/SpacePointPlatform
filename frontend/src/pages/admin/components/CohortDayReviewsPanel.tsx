/** Ops review queue for instructor reports (operations process doc
 *  §11-§12, built 2026-08-24).
 *
 *  Each submitted report is one card: did the instructor check in, how much
 *  of the checklist is done, what they wrote, and the proof they attached.
 *  Approve locks it in — **and that approval is what later counts as a paid
 *  session**, which is why the button says so and why approving the last
 *  report in a cohort reports back that the cohort completed.
 *
 *  Three places render this: standalone on This Week and inside a cohort's
 *  own detail page (both the "panel" look, with its own header, submitted
 *  reports only — that's the actionable queue), embedded in the Reviews
 *  kanban's Need Review column (`embedded` — the column already has a
 *  title; shows every non-approved report, submitted or still in progress,
 *  so ops sees the whole review picture from one kanban instead of having
 *  to open a session's own Report tab to check on incomplete work), and
 *  scoped to one session on that session's own Report tab (`sessionId` —
 *  every assigned instructor's report, whatever state it's in, including
 *  already-approved ones).
 */
import { useState } from "react"
import { Link } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowRight, CalendarCheck, ChevronRight, CircleAlert, ImageIcon } from "lucide-react"
import { approveDayApi, getDayApi, listDayReviewsApi, returnDayApi } from "@/api/sessions/day"
import type { Cohort, DayReview } from "@/types/sessions"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/pages/admin/components/common"
import { cn, getErrorMessage } from "@/lib/utils"

function DayCard({ d, onDone, linkToSession, defaultOpen }: {
  d: DayReview
  onDone: (msg: string) => void
  /** Suppressed when already rendered on that exact session's own page. */
  linkToSession: boolean
  defaultOpen: boolean
}) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(defaultOpen)
  const [comment, setComment] = useState("")
  const [returning, setReturning] = useState(false)
  const [error, setError] = useState("")

  // Only fetched when ops actually opens the card — the queue can be long and
  // each detail call resolves signed URLs for every proof photo.
  const detail = useQuery({
    queryKey: ["day-detail", d.session_id, d.user_id],
    queryFn: () => getDayApi(d.session_id, d.user_id),
    enabled: open,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["day-reviews"] })
    qc.invalidateQueries({ queryKey: ["day-detail", d.session_id, d.user_id] })
  }

  const approve = useMutation({
    mutationFn: () => approveDayApi(d.day_id),
    onSuccess: (res) => {
      invalidate()
      onDone(
        res.cohort_completed
          ? `Approved — that was the last report, so ${d.cohort_name} is now complete. Certificates have gone out; it's now on the payments to-do list whenever you're ready to bill it.`
          : "Report approved.",
      )
    },
    onError: (e) => setError(getErrorMessage(e, "Could not approve that report")),
  })

  const sendBack = useMutation({
    mutationFn: () => returnDayApi(d.day_id, comment),
    onSuccess: () => { setReturning(false); setComment(""); invalidate(); onDone("Sent back to the instructor.") },
    onError: (e) => setError(getErrorMessage(e, "Could not return that report")),
  })

  const absent = d.att_status === "absent"
  const canReview = d.status === "submitted"
  const canApprove = d.status !== "approved"

  return (
    <div className="border border-border rounded-xl p-3 shrink-0">
      <div
        role="button"
        tabIndex={0}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen((v) => !v) } }}
        className="w-full flex flex-wrap items-start justify-between gap-2 text-left cursor-pointer"
      >
        <div className="flex items-start gap-2 min-w-0">
          <ChevronRight
            size={14}
            className={cn("text-muted-foreground shrink-0 mt-0.5 transition-transform", open && "rotate-90")}
          />
          <div className="min-w-0">
            <p className="font-medium text-sm">
              {d.full_name} — {d.session_title ? `${d.session_title} · ` : ""}{d.cohort_name}
              <span className="text-muted-foreground font-normal">
                {" "}· {new Date(d.meeting_date).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
              </span>
            </p>
            <p className="text-[11px] text-muted-foreground">
              {absent ? (
                <span className="text-amber-600 dark:text-amber-400">
                  Declared absent{d.absence_reason ? ` — ${d.absence_reason}` : ""}
                </span>
              ) : (
                <>
                  {d.checked_in_at
                    ? `Checked in ${new Date(d.checked_in_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}`
                    : "No check-in"}
                  {" · "}Checklist {d.checklist_done}/{d.checklist_total}
                  {!canReview && d.status !== "approved" && " · in progress"}
                </>
              )}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0" onClick={(e) => e.stopPropagation()}>
          {canReview && (
            <Button size="sm" variant="outline" onClick={() => setReturning((v) => !v)}>
              Return
            </Button>
          )}
          {canApprove && (
            <Button size="sm" disabled={approve.isPending} onClick={() => { setError(""); approve.mutate() }}>
              {approve.isPending ? "Approving…" : canReview ? "Approve" : "Approve anyway"}
            </Button>
          )}
        </div>
      </div>

      {returning && (
        <div className="mt-3 flex flex-col sm:flex-row gap-2">
          <input
            className="input flex-1 h-9 text-sm"
            placeholder="What needs changing? e.g. 'Checklist item 6 needs evidence'"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <Button
            size="sm" variant="outline"
            disabled={!comment.trim() || sendBack.isPending}
            onClick={() => { setError(""); sendBack.mutate() }}
          >
            {sendBack.isPending ? "Sending…" : "Send back"}
          </Button>
        </div>
      )}

      {open && (
        <div className="mt-3 border-t border-border pt-3">
          {!canReview && !absent && (
            <p className="text-xs text-muted-foreground italic mb-2">
              Still working through their checklist and hasn't submitted — "Approve anyway" if you already know they delivered.
            </p>
          )}
          {detail.isLoading ? <Spinner /> : (
            <>
              {detail.data?.instructor_notes && (
                <p className="text-xs text-muted-foreground whitespace-pre-line mb-3">
                  <span className="font-semibold text-foreground">Notes: </span>
                  {detail.data.instructor_notes}
                </p>
              )}
              <ul className="space-y-1.5">
                {(detail.data?.checklist ?? []).map((line) => (
                  <li key={line.item_id} className="flex items-start gap-2 text-xs">
                    <span className={line.is_done ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"}>
                      {line.is_done ? "✔" : "☐"}
                    </span>
                    <span className="min-w-0 flex-1">
                      {line.title}
                      {line.requires_proof && !line.proof_url && (
                        <span className="text-amber-600 dark:text-amber-400"> · no photo</span>
                      )}
                      {line.note && <span className="text-muted-foreground italic"> — {line.note}</span>}
                    </span>
                    {line.proof_url && (
                      <a
                        href={line.proof_url} target="_blank" rel="noreferrer"
                        className="inline-flex items-center gap-1 text-primary hover:underline shrink-0"
                      >
                        <ImageIcon size={11} /> photo
                      </a>
                    )}
                  </li>
                ))}
                {(detail.data?.checklist ?? []).length === 0 && (
                  <li className="text-xs text-muted-foreground">No checklist configured for this session.</li>
                )}
              </ul>
            </>
          )}
        </div>
      )}
      {error && <p className="text-xs text-red-600 dark:text-red-400 mt-2">{error}</p>}
      {linkToSession && (
        <div className="flex justify-end border-t border-border mt-3 pt-2">
          <Link
            to="/operations/cohorts/$cohortId/sessions/$sessionId"
            params={{ cohortId: d.cohort_id, sessionId: d.session_id }}
            className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline"
          >
            Open session <ArrowRight size={11} />
          </Link>
        </div>
      )}
    </div>
  )
}

export default function CohortDayReviewsPanel({ cohort, sessionId, embedded = false }: {
  cohort?: Cohort
  /** Scopes to one session's own Report tab — every assigned instructor's
   *  report, whatever state it's in, not just submitted ones. */
  sessionId?: string
  /** Hides the internal header — used inside the Reviews kanban's Need
   *  Review column, which already carries its own title. */
  embedded?: boolean
}) {
  const [flash, setFlash] = useState("")
  const reviews = useQuery({
    queryKey: ["day-reviews", sessionId ?? cohort?.id ?? "all"],
    queryFn: () => listDayReviewsApi(
      sessionId ? { sessionId, statusFilter: "" }
        : cohort ? { cohortId: cohort.id }
        : embedded ? { statusFilter: "" }
        : {},
    ),
  })

  // The kanban column shows the whole review picture — submitted and still
  // in-progress reports alike — minus anything already approved, which has
  // nothing left to review.
  const rows = embedded ? (reviews.data ?? []).filter((d) => d.status !== "approved") : reviews.data ?? []

  const showHeader = !embedded && !sessionId

  return (
    <div className={showHeader ? "py-4" : ""}>
      {showHeader && (
        <div className="mb-3">
          <h3 className="font-semibold text-sm flex items-center gap-1.5">
            <CalendarCheck size={14} /> Needs review
          </h3>
          <p className="text-xs text-muted-foreground">
            Approving a report is what makes that session count on the instructor's payment letter.
          </p>
        </div>
      )}

      {flash && (
        <p className="text-xs text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/50 rounded-lg px-3 py-2 mb-3">
          {flash}
        </p>
      )}

      {reviews.isLoading ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <CircleAlert size={12} />{" "}
          {sessionId
            ? "No instructor has started a report yet."
            : embedded
              ? "Nothing here — no session days awaiting review."
              : "Nothing waiting for review."}
        </p>
      ) : (
        <div className="space-y-2">
          {rows.map((d) => (
            <DayCard
              key={d.day_id} d={d} onDone={setFlash}
              linkToSession={!sessionId}
              defaultOpen={d.status === "submitted"}
            />
          ))}
        </div>
      )}
    </div>
  )
}
