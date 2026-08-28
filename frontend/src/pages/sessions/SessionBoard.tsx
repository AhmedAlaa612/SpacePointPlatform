import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { Calendar, CircleAlert, Clock, MapPin, PlayCircle, CheckCircle2 } from "lucide-react"
import { listDayReviewsApi, getSessionBoardApi } from "@/api/sessions/day"
import type { BoardSession } from "@/types/sessions"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner } from "@/pages/instructors/components/common"
import CohortDayReviewsPanel from "@/pages/admin/components/CohortDayReviewsPanel"

/**
 * "What needs review, what's running, what's upcoming, what's done" —
 * everything, every cohort, one page, so ops doesn't have to open each
 * cohort in turn to answer it (2026-08-28). Unbounded on purpose: This Week
 * already answers the 7-day staffing-gap question, and stays as it is —
 * this is the lifecycle question instead, with no date window.
 */

function fmtDate(d: string) {
  return new Date(d).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })
}

function BoardCard({ s }: { s: BoardSession }) {
  return (
    <Link
      to="/operations/cohorts/$cohortId/sessions/$sessionId"
      params={{ cohortId: s.cohort_id, sessionId: s.session_id }}
    >
      <Card className="transition-colors hover:border-primary/40 hover:bg-foreground/5">
        <CardContent className="p-3 flex flex-col gap-1.5">
          <p className="text-sm font-semibold text-foreground truncate">{s.title || s.program_name}</p>
          <p className="text-xs text-muted-foreground truncate">{s.cohort_name}</p>
          <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground pt-1">
            <span className="flex items-center gap-1"><Calendar size={11} /> {fmtDate(s.meeting_date)}</span>
            {s.location && <span className="flex items-center gap-1"><MapPin size={11} /> {s.location}</span>}
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}

function Column({
  title, icon, tone, count, children,
}: { title: string; icon: React.ReactNode; tone: string; count: number; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2.5 min-w-[300px] w-[300px] shrink-0">
      <div className="flex items-center justify-between px-1">
        <span className={`flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide ${tone}`}>
          {icon} {title}
        </span>
        <span className="text-xs font-semibold text-muted-foreground tabular-nums">{count}</span>
      </div>
      <div className="flex flex-col gap-2 max-h-[70vh] overflow-y-auto pr-0.5">
        {children}
      </div>
    </div>
  )
}

export default function SessionBoard() {
  const [doneLimit, setDoneLimit] = useState(5)

  const needsReview = useQuery({
    queryKey: ["day-reviews", "submitted"],
    queryFn: () => listDayReviewsApi({ statusFilter: "submitted" }),
  })
  const board = useQuery({
    queryKey: ["session-board", doneLimit],
    queryFn: () => getSessionBoardApi({ doneOffset: 0, doneLimit }),
  })

  if (needsReview.isLoading || board.isLoading) return <Spinner />

  const b = board.data
  const reviewCount = needsReview.data?.length ?? 0

  return (
    <div className="space-y-4">
      <PageHeader title="Session Board" subtitle="Every cohort, one page — what needs review, what's running, what's upcoming, what's done." />

      <div className="flex gap-4 overflow-x-auto pb-2">
        <Column
          title="Needs Review" count={reviewCount}
          icon={<CircleAlert size={14} />} tone="text-red-600 dark:text-red-400"
        >
          {reviewCount === 0 ? (
            <p className="text-xs text-muted-foreground px-1 py-4">Nothing waiting on you.</p>
          ) : (
            <CohortDayReviewsPanel />
          )}
        </Column>

        <Column
          title="Running" count={b?.running.length ?? 0}
          icon={<PlayCircle size={14} />} tone="text-blue-600 dark:text-blue-400"
        >
          {(b?.running.length ?? 0) === 0 ? (
            <p className="text-xs text-muted-foreground px-1 py-4">Nothing running right now.</p>
          ) : (
            b!.running.map((s) => <BoardCard key={s.session_id} s={s} />)
          )}
        </Column>

        <Column
          title="Upcoming" count={b?.upcoming.length ?? 0}
          icon={<Clock size={14} />} tone="text-muted-foreground"
        >
          {(b?.upcoming.length ?? 0) === 0 ? (
            <p className="text-xs text-muted-foreground px-1 py-4">Nothing upcoming.</p>
          ) : (
            b!.upcoming.map((s) => <BoardCard key={s.session_id} s={s} />)
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
              {b!.done.map((s) => <BoardCard key={s.session_id} s={s} />)}
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
