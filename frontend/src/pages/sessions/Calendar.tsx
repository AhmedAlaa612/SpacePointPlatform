import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { CalendarDays, ChevronLeft, ChevronRight, Clock, MapPin, Users } from "lucide-react"
import { getCalendarApi } from "@/api/sessions/calendar"
import type { CalendarEvent, ProgramType } from "@/types/sessions"
import { Card, CardContent } from "@/components/ui/card"
import { useAuth } from "@/context/AuthContext"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"

const DAY = 86_400_000
const programColors: Record<ProgramType, string> = {
  workshop: "border-violet-400/50 bg-violet-500/10 text-violet-700 dark:text-violet-300",
  course: "border-sky-400/50 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  info_session: "border-amber-400/50 bg-amber-500/10 text-amber-700 dark:text-amber-300",
}

function iso(d: Date) { return d.toISOString().slice(0, 10) }
function monday(d: Date) { const x = new Date(d); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x }
function fmtDate(value: string) { return new Date(`${value}T12:00:00`).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }) }
function fmtTime(value: string) { return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) }

function EventCard({ event, opsView }: { event: CalendarEvent; opsView?: boolean }) {
  const tone = event.source === "teacher_session"
    ? "border-rose-400/50 bg-rose-500/10 text-rose-700 dark:text-rose-300"
    : programColors[event.program_type ?? "workshop"]
  const body = (
    <Card className={`transition-colors hover:border-primary/50 ${event.session_id ? "cursor-pointer" : ""}`}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-semibold text-foreground truncate">{event.title}</p>
            <p className="mt-0.5 text-xs text-muted-foreground truncate">{event.source === "teacher_session" ? `Teacher session · ${event.teacher_name ?? ""}` : `${event.program_name} · ${event.cohort_name}`}</p>
          </div>
          <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${tone}`}>
            {event.source === "teacher_session" ? "Teacher" : event.program_type?.replace("_", " ")}
          </span>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="flex items-center gap-1"><Clock size={13} />{fmtTime(event.starts_at)}</span>
          {event.location && <span className="flex items-center gap-1"><MapPin size={13} />{event.location}</span>}
          {event.instructors.length > 0 && <span className="flex items-center gap-1"><Users size={13} />{event.instructors.map((x) => x.full_name).join(", ")}</span>}
        </div>
      </CardContent>
    </Card>
  )
  if (!event.session_id) return body
  if (opsView) {
    // Ops/admin lands on the specific session, not the bare cohort list —
    // falls back to the cohort page (or the list) if either id is somehow
    // missing, rather than a dead link.
    if (event.cohort_id) {
      return (
        <Link
          to="/operations/cohorts/$cohortId/sessions/$sessionId"
          params={{ cohortId: event.cohort_id, sessionId: event.session_id }}
        >
          {body}
        </Link>
      )
    }
    return <Link to="/operations/cohorts">{body}</Link>
  }
  return <Link to="/instructors/sessions/$sessionId" params={{ sessionId: event.session_id }}>{body}</Link>
}

import { SessionsSubNav } from "@/components/layout/SessionsSubNav"

export default function SessionsCalendar() {
  const { activeRole } = useAuth()
  const canSeeOps = activeRole === "admin" || activeRole === "operations"
  const isInstructorRole = activeRole === "instructor" || activeRole === "facilitator"
  const [scope, setScope] = useState<"ops" | "instructor">(canSeeOps ? "ops" : "instructor")
  const [weekStart, setWeekStart] = useState(() => monday(new Date()))
  const from = iso(weekStart)
  const to = iso(new Date(weekStart.getTime() + 6 * DAY))
  const calendar = useQuery({ queryKey: ["sessions-calendar", from, to, scope], queryFn: () => getCalendarApi(from, to, scope) })
  const byDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>()
    calendar.data?.events.forEach((event) => { const key = event.starts_at.slice(0, 10); map.set(key, [...(map.get(key) ?? []), event]) })
    return map
  }, [calendar.data])
  const days = Array.from({ length: 7 }, (_, i) => new Date(weekStart.getTime() + i * DAY))
  const upcoming = (calendar.data?.events ?? []).filter((event) => new Date(event.starts_at).getTime() >= Date.now()).slice(0, 7)

  return (
    <div>
      {isInstructorRole && <SessionsSubNav activeTab="calendar" />}
      <div className="flex flex-wrap items-end justify-between gap-4">
      <PageHeader title="Sessions Calendar" subtitle="Your scheduled delivery sessions and the operations calendar." />
      {canSeeOps && <div className="flex rounded-lg border border-border p-1 text-sm"><button onClick={() => setScope("ops")} className={`rounded-md px-3 py-1.5 ${scope === "ops" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}>Operations</button><button onClick={() => setScope("instructor")} className={`rounded-md px-3 py-1.5 ${scope === "instructor" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}>My sessions</button></div>}
    </div>
    <Card className="mt-6"><CardContent className="p-4"><div className="flex items-center justify-between"><button aria-label="Previous week" onClick={() => setWeekStart((d) => new Date(d.getTime() - 7 * DAY))} className="rounded-lg p-2 hover:bg-muted"><ChevronLeft size={18}/></button><p className="font-semibold">{fmtDate(from)} – {fmtDate(to)}</p><button aria-label="Next week" onClick={() => setWeekStart((d) => new Date(d.getTime() + 7 * DAY))} className="rounded-lg p-2 hover:bg-muted"><ChevronRight size={18}/></button></div></CardContent></Card>
    {calendar.isLoading ? <Spinner /> : calendar.isError ? <p className="mt-6 text-sm text-destructive">Could not load the calendar.</p> : <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_300px]"><div className="space-y-3">{days.map((day) => { const key = iso(day); const events = byDay.get(key) ?? []; return <section key={key} className="rounded-xl border border-border bg-card/50"><div className="border-b border-border px-4 py-3 font-medium">{fmtDate(key)}</div><div className="space-y-2 p-3">              {events.length ? events.map((event) => <EventCard key={event.id} event={event} opsView={scope === "ops"} />) : <p className="py-3 text-center text-sm text-muted-foreground">No sessions</p>}</div></section> })}</div><aside><Card><CardContent className="p-4"><div className="mb-3 flex items-center gap-2 font-semibold"><CalendarDays size={17}/>Upcoming 7 days</div>{upcoming.length ? <div className="space-y-3">{upcoming.map((event) => <div key={event.id} className="border-l-2 border-primary pl-3"><p className="text-xs text-muted-foreground">{fmtDate(event.starts_at.slice(0, 10))} · {fmtTime(event.starts_at)}</p><p className="text-sm font-medium">{event.title}</p></div>)}</div> : <EmptyState title="Nothing upcoming" hint="New sessions will appear here." />}</CardContent></Card></aside></div>}
    </div>
  )
}
