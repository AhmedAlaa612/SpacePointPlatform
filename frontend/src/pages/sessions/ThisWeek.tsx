import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { Clock, ExternalLink, MapPin, Users } from "lucide-react"
import { getCalendarApi } from "@/api/sessions/calendar"
import type { CalendarEvent, StaffingStatus } from "@/types/sessions"
import { Card, CardContent } from "@/components/ui/card"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"
import { cn } from "@/lib/utils"

/**
 * "Which sessions this week still have nobody on them?" — the question ops
 * asks daily, which until now had no page (2026-08-02). It could only be
 * answered by opening every cohort one at a time: the dashboard had the
 * number but nothing to click, and the calendar showed a week without
 * showing staffing at all.
 *
 * Deliberately a read-and-navigate view, not another place to act: every row
 * is a link to the session that owns the problem. Same /sessions/calendar
 * data the calendar already uses — no new endpoint, it just asks for the next
 * seven days and sorts by what needs attention.
 */

const STAFFING_LABEL: Record<StaffingStatus, string> = {
  unstaffed: "Unstaffed",
  open_call: "Open call",
  staffed: "Staffed",
}
const STAFFING_TONE: Record<StaffingStatus, string> = {
  unstaffed: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  open_call: "border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400",
  staffed: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
}
// Unstaffed first — the whole point of the page.
const STAFFING_RANK: Record<StaffingStatus, number> = { unstaffed: 0, open_call: 1, staffed: 2 }

function iso(d: Date) { return d.toISOString().slice(0, 10) }
function fmtDay(value: string) {
  return new Date(value).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })
}
function fmtTime(value: string) {
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

export default function ThisWeek() {
  const [needsAttentionOnly, setNeedsAttentionOnly] = useState(false)

  const { from, to } = useMemo(() => {
    const start = new Date()
    start.setHours(0, 0, 0, 0)
    const end = new Date(start)
    end.setDate(end.getDate() + 7)
    return { from: iso(start), to: iso(end) }
  }, [])

  const { data, isLoading } = useQuery({
    queryKey: ["sessions-calendar", from, to, "ops"],
    queryFn: () => getCalendarApi(from, to, "ops"),
  })

  const rows = useMemo(() => {
    // Teacher sessions aren't ours to staff — they have no staffing_status
    // and no session to open a call on, so they'd only be noise here.
    const sessions = (data?.events ?? []).filter((e) => e.source === "session")
    const filtered = needsAttentionOnly
      ? sessions.filter((e) => (e.staffing_status ?? "unstaffed") !== "staffed")
      : sessions
    return [...filtered].sort((a, b) => {
      const rank = STAFFING_RANK[a.staffing_status ?? "unstaffed"] - STAFFING_RANK[b.staffing_status ?? "unstaffed"]
      return rank !== 0 ? rank : a.starts_at.localeCompare(b.starts_at)
    })
  }, [data, needsAttentionOnly])

  const unstaffed = (data?.events ?? []).filter(
    (e) => e.source === "session" && (e.staffing_status ?? "unstaffed") === "unstaffed",
  ).length

  return (
    <div>
      <PageHeader
        title="This week"
        subtitle="Sessions in the next 7 days, worst staffing first."
        action={
          <button
            onClick={() => setNeedsAttentionOnly((v) => !v)}
            className={cn(
              "h-9 px-3 rounded-xl border text-sm font-medium transition-colors",
              needsAttentionOnly
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-foreground hover:bg-muted",
            )}
          >
            {needsAttentionOnly ? "Showing needs attention" : "Needs attention only"}
          </button>
        }
      />

      {isLoading ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <EmptyState
          title={needsAttentionOnly ? "Nothing needs attention" : "No sessions in the next 7 days"}
          hint={needsAttentionOnly ? "Every session this week has someone on it." : undefined}
        />
      ) : (
        <div className="flex flex-col gap-4">
          {unstaffed > 0 && !needsAttentionOnly && (
            <p className="text-sm text-muted-foreground">
              <span className="font-semibold text-red-600 dark:text-red-400">{unstaffed}</span>
              {" "}session{unstaffed === 1 ? " has" : "s have"} nobody on {unstaffed === 1 ? "it" : "them"} yet.
            </p>
          )}
          <div className="flex flex-col gap-2">
            {rows.map((e) => <SessionRow key={e.id} event={e} />)}
          </div>
        </div>
      )}
    </div>
  )
}

function SessionRow({ event: e }: { event: CalendarEvent }) {
  const status = e.staffing_status ?? "unstaffed"
  const body = (
    <Card className="transition-colors hover:border-primary/50">
      <CardContent className="p-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-foreground truncate">{e.title}</p>
          <p className="mt-0.5 text-xs text-muted-foreground truncate">
            {e.program_name} · {e.cohort_name}
          </p>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <Clock size={13} />{fmtDay(e.starts_at)} · {fmtTime(e.starts_at)}
            </span>
            {e.location && <span className="flex items-center gap-1"><MapPin size={13} />{e.location}</span>}
            {e.location_address && <span>{e.location_address}</span>}
            {e.location_maps_url && (
              <a
                href={e.location_maps_url} target="_blank" rel="noreferrer"
                onClick={(ev) => ev.stopPropagation()}
                className="flex items-center gap-0.5 text-primary hover:underline"
              >
                map <ExternalLink size={11} />
              </a>
            )}
            {e.instructors.length > 0 && (
              <span className="flex items-center gap-1">
                <Users size={13} />{e.instructors.map((x) => x.full_name).join(", ")}
              </span>
            )}
          </div>
        </div>
        <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold", STAFFING_TONE[status])}>
          {STAFFING_LABEL[status]}
        </span>
      </CardContent>
    </Card>
  )

  if (!e.session_id || !e.cohort_id) return body
  return (
    <Link
      to="/operations/cohorts/$cohortId/sessions/$sessionId"
      params={{ cohortId: e.cohort_id, sessionId: e.session_id }}
    >
      {body}
    </Link>
  )
}
