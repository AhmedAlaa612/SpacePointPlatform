import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { ArrowRight, Calendar, CheckCircle2, CircleAlert, MapPin, PlayCircle } from "lucide-react"
import { getSessionBoardApi, listDayReviewsApi } from "@/api/sessions/day"
import type { BoardInstructor, BoardSession } from "@/types/sessions"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner } from "@/pages/instructors/components/common"
import CohortDayReviewsPanel from "@/pages/admin/components/CohortDayReviewsPanel"
import { cn } from "@/lib/utils"

/**
 * "What needs review, what's running, what's done" — everything, every
 * cohort, one page (2026-08-28; simplified to 3 columns 2026-08-30 — an
 * "Upcoming" column used to sit here too, but a session that hasn't started
 * needs nothing from ops, so it never earned its keep). Unbounded on
 * purpose: This Week already answers the 7-day staffing-gap question, and
 * stays as it is — this is the lifecycle question instead, with no date
 * window.
 */

function fmtDate(d: string) {
  return new Date(d).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })
}

function fmtTime(d: string) {
  return new Date(d).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/)
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase()
}

/** One assigned instructor's row on a Running card — checked in or not,
 *  checklist progress, and whether they've submitted, at a glance. */
function InstructorRow({ i }: { i: BoardInstructor }) {
  const notCheckedIn = i.day_status === null && i.att_status === null
  const absent = i.att_status === "absent"
  const doneWorking = i.day_status === "submitted" || i.day_status === "approved"

  return (
    <div className="flex items-center gap-2">
      <div className="w-5 h-5 rounded-full bg-primary/20 text-primary flex items-center justify-center text-[9px] font-bold shrink-0">
        {initials(i.full_name)}
      </div>
      <span className="text-xs flex-1 min-w-0 truncate">{i.full_name}</span>
      {!notCheckedIn && !absent && i.checklist_total > 0 && (
        <span className="flex gap-0.5 shrink-0">
          {Array.from({ length: i.checklist_total }).map((_, idx) => (
            <span
              key={idx}
              className={cn(
                "w-1.5 h-1.5 rounded-full",
                idx < i.checklist_done
                  ? doneWorking ? "bg-emerald-500" : "bg-amber-500"
                  : "bg-border",
              )}
            />
          ))}
        </span>
      )}
      <span
        className={cn(
          "text-[10px] font-semibold px-1.5 py-0.5 rounded-full shrink-0",
          notCheckedIn || absent
            ? "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400"
            : doneWorking
              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400"
              : "bg-muted text-muted-foreground",
        )}
      >
        {notCheckedIn ? "Not checked in" : absent ? "Absent" : doneWorking ? "Submitted" : `${i.checklist_done}/${i.checklist_total} · working`}
      </span>
    </div>
  )
}

function OpenSessionLink({ s }: { s: BoardSession }) {
  return (
    <Link
      to="/operations/cohorts/$cohortId/sessions/$sessionId"
      params={{ cohortId: s.cohort_id, sessionId: s.session_id }}
      className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline"
    >
      Open session <ArrowRight size={11} />
    </Link>
  )
}

function RunningCard({ s }: { s: BoardSession }) {
  const flagged = s.instructors.some((i) => (i.day_status === null && i.att_status === null) || i.att_status === "absent")
  return (
    <Card className={cn("shrink-0 py-0", flagged && "border-amber-500/40")}>
      <CardContent className="p-3 flex flex-col gap-2.5">
        <div>
          <p className="text-sm font-semibold text-foreground truncate">{s.title || s.program_name}</p>
          <p className="text-xs text-muted-foreground truncate">
            {s.cohort_name}{s.started_at ? ` · started ${fmtTime(s.started_at)}` : ""}
          </p>
        </div>
        {s.instructors.length > 0 && (
          <div className="flex flex-col gap-1.5 border-t border-border pt-2">
            {s.instructors.map((i) => <InstructorRow key={i.user_id} i={i} />)}
          </div>
        )}
        <div className="flex justify-end border-t border-border pt-2">
          <OpenSessionLink s={s} />
        </div>
      </CardContent>
    </Card>
  )
}

/** A session can be marked done while an instructor's own report is still
 *  unfinished — session completion and report completion are tracked
 *  separately. Flagging that here is the only place it would otherwise be
 *  visible at all: Need Review only lists submitted reports, so a report
 *  nobody ever submitted has nowhere else to surface once its session
 *  leaves Running. */
function unfinishedInstructors(s: BoardSession) {
  return s.instructors.filter((i) => i.day_status !== "submitted" && i.day_status !== "approved")
}

function DoneCard({ s }: { s: BoardSession }) {
  const unfinished = unfinishedInstructors(s)
  return (
    <Card className={cn("shrink-0 py-0", unfinished.length > 0 && "border-amber-500/40")}>
      <CardContent className="p-3 flex flex-col gap-1.5">
        <Link
          to="/operations/cohorts/$cohortId/sessions/$sessionId"
          params={{ cohortId: s.cohort_id, sessionId: s.session_id }}
          className="hover:text-primary transition-colors"
        >
          <p className="text-sm font-semibold text-foreground truncate">{s.title || s.program_name}</p>
        </Link>
        <p className="text-xs text-muted-foreground truncate">{s.cohort_name}</p>
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground pt-1">
          <span className="flex items-center gap-1"><Calendar size={11} /> {fmtDate(s.meeting_date)}</span>
          {s.location && <span className="flex items-center gap-1"><MapPin size={11} /> {s.location}</span>}
        </div>
        {unfinished.length > 0 && (
          <div className="flex flex-col gap-1 border-t border-border pt-2 mt-1">
            {unfinished.map((i) => (
              <div key={i.user_id} className="flex flex-wrap items-center gap-1 text-[11px] text-amber-700 dark:text-amber-400">
                <span className="flex items-center gap-1 shrink-0 font-semibold">
                  <CircleAlert size={11} className="shrink-0" />
                  Not submitted:
                </span>
                <span className="break-words min-w-0 flex-1" title={i.full_name}>{i.full_name}</span>
              </div>
            ))}
          </div>
        )}
        <div className="flex justify-end pt-1">
          <OpenSessionLink s={s} />
        </div>
      </CardContent>
    </Card>
  )
}

function Column({
  title, icon, tone, count, children,
}: { title: string; icon: React.ReactNode; tone: string; count: number; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2.5 w-[85vw] max-w-[320px] shrink-0 snap-start sm:w-auto sm:max-w-none sm:flex-1 sm:min-w-[280px]">
      <div className="flex items-center justify-between px-1">
        <span className={`flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide ${tone}`}>
          {icon} {title}
        </span>
        <span className="text-xs font-semibold text-muted-foreground tabular-nums">{count}</span>
      </div>
      <div className="flex flex-col gap-2 max-h-[65vh] sm:max-h-[calc(100vh-220px)] overflow-y-auto pr-0.5">
        {children}
      </div>
    </div>
  )
}

export default function Reviews() {
  const [doneLimit, setDoneLimit] = useState(5)

  const board = useQuery({
    queryKey: ["session-board", doneLimit],
    queryFn: () => getSessionBoardApi({ doneOffset: 0, doneLimit }),
  })
  // Shares its cache with the embedded CohortDayReviewsPanel below (same
  // query key) — this fetch is just for the column's count.
  const needsReview = useQuery({
    queryKey: ["day-reviews", "all"],
    queryFn: () => listDayReviewsApi(),
  })

  if (board.isLoading || needsReview.isLoading) return <Spinner />

  const b = board.data

  return (
    <div className="space-y-4">
      <PageHeader title="Reviews" subtitle="Every cohort, one page — what needs review, what's running, what's done." />

      <div className="flex gap-4 overflow-x-auto pb-2 snap-x snap-mandatory sm:snap-none">
        <Column
          title="Need Review" count={needsReview.data?.length ?? 0}
          icon={<CircleAlert size={14} />} tone="text-red-600 dark:text-red-400"
        >
          {(needsReview.data?.length ?? 0) === 0 ? (
            <p className="text-xs text-muted-foreground px-1 py-4">Nothing waiting on you.</p>
          ) : (
            <CohortDayReviewsPanel embedded />
          )}
        </Column>

        <Column
          title="Running" count={b?.running.length ?? 0}
          icon={<PlayCircle size={14} />} tone="text-blue-600 dark:text-blue-400"
        >
          {(b?.running.length ?? 0) === 0 ? (
            <p className="text-xs text-muted-foreground px-1 py-4">Nothing running right now.</p>
          ) : (
            b!.running.map((s) => <RunningCard key={s.session_id} s={s} />)
          )}
        </Column>

        <Column
          title="Done" count={b?.done_total ?? 0}
          icon={<CheckCircle2 size={14} />} tone="text-emerald-600 dark:text-emerald-400"
        >
          {(b?.done.length ?? 0) === 0 ? (
            <p className="text-xs text-muted-foreground px-1 py-4">Nothing done yet.</p>
          ) : (
            <>
              {b!.done.map((s) => <DoneCard key={s.session_id} s={s} />)}
              {b!.done.length < b!.done_total && (
                <button
                  type="button"
                  onClick={() => setDoneLimit((n) => n + 5)}
                  className="text-xs font-medium text-primary hover:underline py-2"
                >
                  Load more ({b!.done_total - b!.done.length} more)
                </button>
              )}
            </>
          )}
        </Column>
      </div>
    </div>
  )
}
