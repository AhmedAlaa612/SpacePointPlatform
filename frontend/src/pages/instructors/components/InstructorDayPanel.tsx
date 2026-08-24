/** The instructor's day (operations process doc §4-§12, built 2026-08-24).
 *
 *  Two pieces that belong together:
 *    - **Today** — "I'm here" / "I can't attend", recorded day by day rather
 *      than inferred from the cohort assignment. An instructor assigned to
 *      five days may legitimately miss one, and the payment letter should say
 *      four.
 *    - **Daily checklist** — the items ops configured for this programme, with
 *      a photo attached directly to the item that needs one rather than
 *      everything dumped into a single end-of-day upload.
 *
 *  Submitting sends the day for ops review; that approval is what makes the
 *  day count on the payment letter, so the submit button says so.
 *
 *  Proof upload deliberately reuses `uploadSessionReportApi` — the same
 *  bucket, permission check and ops-facing list as every other session file.
 *  The checklist row just points at the report it created.
 */
import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Camera, CheckCircle2, Clock3, ImageIcon, Send, UserX } from "lucide-react"
import {
  checkInApi,
  getDayApi,
  setChecklistProgressApi,
  submitDayApi,
} from "@/api/sessions/day"
import { uploadSessionReportApi } from "@/api/sessions/delivery"
import type { ChecklistLine } from "@/types/sessions"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { getErrorMessage } from "@/lib/utils"

const STATUS_LABEL: Record<string, { text: string; className: string }> = {
  draft: { text: "Not submitted", className: "bg-muted text-muted-foreground border-border" },
  submitted: {
    text: "Awaiting ops review",
    className: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400 border-blue-500/20",
  },
  changes_required: {
    text: "Changes required",
    className: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400 border-amber-500/20",
  },
  approved: {
    text: "Approved",
    className: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 border-emerald-500/20",
  },
}

function ChecklistRow({
  line, sessionId, cohortId, locked, onChanged,
}: {
  line: ChecklistLine; sessionId: string; cohortId: string; locked: boolean
  onChanged: () => void
}) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  const tick = useMutation({
    mutationFn: (isDone: boolean) => setChecklistProgressApi(sessionId, line.item_id, { is_done: isDone }),
    onSuccess: onChanged,
    onError: (e) => setError(getErrorMessage(e, "Couldn't save that")),
  })

  /** Upload through the ordinary session-report path, then point the checklist
   *  row at the row it created. Two steps on purpose — one upload mechanism
   *  for the whole domain. */
  const attach = async (file: File) => {
    setBusy(true)
    setError("")
    try {
      const report = await uploadSessionReportApi(cohortId, { file, sessionId, notes: line.title })
      await setChecklistProgressApi(sessionId, line.item_id, {
        proof_report_id: report.id, is_done: true,
      })
      onChanged()
    } catch (e) {
      setError(getErrorMessage(e, "Couldn't upload that photo"))
    } finally {
      setBusy(false)
    }
  }

  const needsPhoto = line.requires_proof && !line.proof_url

  return (
    <div className="flex items-start gap-2 py-1.5">
      <input
        type="checkbox"
        checked={line.is_done}
        disabled={locked || tick.isPending}
        onChange={(e) => tick.mutate(e.target.checked)}
        className="mt-0.5 shrink-0 rounded text-primary focus:ring-primary border-border bg-background"
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm text-foreground">
          {line.title}
          {!line.is_required && <span className="text-xs text-muted-foreground"> · optional</span>}
        </p>
        {line.description && (
          <p className="text-xs text-muted-foreground">{line.description}</p>
        )}
        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
      </div>
      {line.requires_proof && (
        <div className="shrink-0 flex items-center gap-2">
          {line.proof_url ? (
            <a
              href={line.proof_url} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
            >
              <ImageIcon size={12} /> photo
            </a>
          ) : (
            <span className="text-[10px] font-semibold text-amber-600 dark:text-amber-400">photo needed</span>
          )}
          {!locked && (
            <>
              <input
                ref={fileRef} type="file" accept="image/*" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) void attach(f) }}
              />
              <button
                type="button" disabled={busy}
                onClick={() => fileRef.current?.click()}
                className={`p-1.5 rounded-lg border transition-colors disabled:opacity-50 ${
                  needsPhoto
                    ? "border-amber-500/40 text-amber-600 dark:text-amber-400 hover:bg-amber-500/10"
                    : "border-border text-muted-foreground hover:bg-muted"
                }`}
                aria-label={`Attach a photo for ${line.title}`}
              >
                <Camera size={13} />
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

export default function InstructorDayPanel({
  sessionId, cohortId, onChanged,
}: {
  sessionId: string; cohortId: string; onChanged?: () => void
}) {
  const qc = useQueryClient()
  const [reason, setReason] = useState("")
  const [askingAbsence, setAskingAbsence] = useState(false)
  const [notes, setNotes] = useState("")
  const [error, setError] = useState("")

  const day = useQuery({
    queryKey: ["instructor-day", sessionId],
    queryFn: () => getDayApi(sessionId),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["instructor-day", sessionId] })
    onChanged?.()
  }

  const check = useMutation({
    mutationFn: (v: { att: "present" | "absent"; reason?: string }) =>
      checkInApi(sessionId, v.att, v.reason),
    onSuccess: () => { setError(""); setAskingAbsence(false); invalidate() },
    onError: (e) => setError(getErrorMessage(e, "Couldn't record that")),
  })

  const submit = useMutation({
    mutationFn: () => submitDayApi(sessionId, notes || undefined),
    onSuccess: () => { setError(""); invalidate() },
    // The 409 body lists everything still outstanding — show it verbatim
    // rather than a generic failure.
    onError: (e) => setError(getErrorMessage(e, "Couldn't submit the day")),
  })

  const d = day.data
  if (day.isLoading || !d) return null

  const locked = d.status === "approved" || d.status === "submitted"
  const badge = STATUS_LABEL[d.status] ?? STATUS_LABEL.draft

  return (
    <div className="flex flex-col gap-3">
      <Card>
        <CardContent className="p-4 flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold text-foreground">Today</p>
            <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${badge.className}`}>
              {badge.text}
            </span>
          </div>

          {d.status === "changes_required" && d.review_comment && (
            <p className="text-xs text-amber-700 dark:text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-xl px-3 py-2">
              <span className="font-semibold">Ops asked for a change: </span>{d.review_comment}
            </p>
          )}

          {d.att_status == null ? (
            <>
              <p className="text-xs text-muted-foreground">
                Are you here today? Ops confirms this, and confirmed days are what your payment
                letter counts.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm" disabled={check.isPending}
                  onClick={() => check.mutate({ att: "present" })}
                >
                  <CheckCircle2 size={14} className="mr-1.5" /> I'm here
                </Button>
                <Button
                  size="sm" variant="outline" disabled={check.isPending}
                  onClick={() => setAskingAbsence((v) => !v)}
                >
                  <UserX size={14} className="mr-1.5" /> I can't attend
                </Button>
              </div>
              {askingAbsence && (
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    className="input flex-1 h-9 text-sm"
                    placeholder="Reason (exam, medical appointment…)"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                  <Button
                    size="sm" variant="outline" disabled={check.isPending}
                    onClick={() => check.mutate({ att: "absent", reason: reason || undefined })}
                  >
                    Confirm absence
                  </Button>
                </div>
              )}
            </>
          ) : d.att_status === "absent" ? (
            <p className="text-xs text-amber-700 dark:text-amber-400">
              You've declared an absence{d.absence_reason ? ` — ${d.absence_reason}` : ""}. Ops will
              acknowledge it; this day won't be counted on your payment letter.
            </p>
          ) : (
            <p className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Clock3 size={12} />
              Checked in
              {d.checked_in_at
                ? ` at ${new Date(d.checked_in_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}`
                : ""}
            </p>
          )}
          {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
        </CardContent>
      </Card>

      {d.att_status === "present" && d.checklist.length > 0 && (
        <Card>
          <CardContent className="p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
              <p className="text-sm font-semibold text-foreground">Daily checklist</p>
              <span className="text-xs text-muted-foreground tabular-nums">
                {d.checklist.filter((l) => l.is_done).length}/{d.checklist.length}
              </span>
            </div>
            <div className="divide-y divide-border/60">
              {d.checklist.map((line) => (
                <ChecklistRow
                  key={line.item_id} line={line} sessionId={sessionId} cohortId={cohortId}
                  locked={locked} onChanged={invalidate}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {d.att_status != null && d.status !== "approved" && (
        <Card>
          <CardContent className="p-4 flex flex-col gap-2">
            {d.status === "submitted" ? (
              <p className="text-xs text-muted-foreground">
                Submitted — waiting for ops to review it.
              </p>
            ) : (
              <>
                <textarea
                  className="input min-h-[4rem] resize-y text-sm"
                  placeholder="How did the day go? Anything ops should know for tomorrow…"
                  value={notes || d.instructor_notes || ""}
                  onChange={(e) => setNotes(e.target.value)}
                />
                {d.missing.length > 0 && (
                  <ul className="text-xs text-muted-foreground list-disc pl-4">
                    {d.missing.map((m) => <li key={m}>{m}</li>)}
                  </ul>
                )}
                <Button
                  size="sm" className="w-fit"
                  disabled={!d.can_submit || submit.isPending}
                  onClick={() => { setError(""); submit.mutate() }}
                >
                  <Send size={13} className="mr-1.5" />
                  {submit.isPending ? "Submitting…" : "Submit day for approval"}
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
