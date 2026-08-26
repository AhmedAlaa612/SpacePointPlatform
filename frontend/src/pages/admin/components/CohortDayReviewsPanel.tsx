/** Ops Day Reviews queue (operations process doc §11-§12, built 2026-08-24).
 *
 *  Each submitted day is one card: did the instructor check in, how much of
 *  the checklist is done, what they wrote, and the proof they attached.
 *  Approve locks it in — **and that approval is what later counts as a paid
 *  day**, which is why the button says so and why approving the last day of a
 *  cohort reports back that the cohort completed.
 *
 *  Rendered inside a cohort (scoped to it) and standalone on This Week (the
 *  whole queue). `cohort` omitted means the latter.
 */
import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CalendarCheck, CircleAlert, ImageIcon } from "lucide-react"
import { approveDayApi, getDayApi, listDayReviewsApi, returnDayApi } from "@/api/sessions/day"
import type { Cohort, DayReview } from "@/types/sessions"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/pages/admin/components/common"
import { getErrorMessage } from "@/lib/utils"

function DayCard({ d, onDone }: { d: DayReview; onDone: (msg: string) => void }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
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
          ? `Approved — that was the last day, so ${d.cohort_name} is now complete. Certificates and draft payment lines have gone out.`
          : "Day approved.",
      )
    },
    onError: (e) => setError(getErrorMessage(e, "Could not approve that day")),
  })

  const sendBack = useMutation({
    mutationFn: () => returnDayApi(d.day_id, comment),
    onSuccess: () => { setReturning(false); setComment(""); invalidate(); onDone("Sent back to the instructor.") },
    onError: (e) => setError(getErrorMessage(e, "Could not return that day")),
  })

  const absent = d.att_status === "absent"

  return (
    <div className="border border-border rounded-xl p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium text-sm">
            {d.full_name} — {d.cohort_name}
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
              </>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button size="sm" variant="outline" onClick={() => setOpen((v) => !v)}>
            {open ? "Hide" : "View"}
          </Button>
          <Button size="sm" variant="outline" onClick={() => setReturning((v) => !v)}>
            Return
          </Button>
          <Button size="sm" disabled={approve.isPending} onClick={() => { setError(""); approve.mutate() }}>
            {approve.isPending ? "Approving…" : absent ? "Acknowledge" : "Approve"}
          </Button>
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
    </div>
  )
}

export default function CohortDayReviewsPanel({ cohort }: { cohort?: Cohort }) {
  const [flash, setFlash] = useState("")
  const reviews = useQuery({
    queryKey: ["day-reviews", cohort?.id ?? "all"],
    queryFn: () => listDayReviewsApi(cohort ? { cohortId: cohort.id } : {}),
  })

  const rows = reviews.data ?? []

  return (
    <div className="py-4">
      <div className="mb-3">
        <h3 className="font-semibold text-sm flex items-center gap-1.5">
          <CalendarCheck size={14} /> Day reviews
        </h3>
        <p className="text-xs text-muted-foreground">
          Approving a day is what makes it count on the instructor's payment letter.
        </p>
      </div>

      {flash && (
        <p className="text-xs text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/50 rounded-lg px-3 py-2 mb-3">
          {flash}
        </p>
      )}

      {reviews.isLoading ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <CircleAlert size={12} /> Nothing waiting for review.
        </p>
      ) : (
        <div className="space-y-2">
          {rows.map((d) => <DayCard key={d.day_id} d={d} onDone={setFlash} />)}
        </div>
      )}
    </div>
  )
}
