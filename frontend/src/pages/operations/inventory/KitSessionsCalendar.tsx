import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { ChevronLeft, ChevronRight, Clock } from "lucide-react"
import { getKitSessionsApi, type KitSession } from "@/api/inventory"
import { cn } from "@/lib/utils"

const WEEKDAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]

function dateKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

const RETURN_LABEL: Record<string, string> = {
  returned: "Returned",
  return_later: "Coming back later",
}

/**
 * Where this kit has been, and where it's booked next — every session it's
 * been earmarked for, laid out as a month grid instead of a flat list, since
 * "what does next month look like for this kit" is a date question, not a
 * search question.
 */
export function KitSessionsCalendar({ kitId, compact = false }: { kitId: string; compact?: boolean }) {
  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["inv-kit-sessions", kitId],
    queryFn: () => getKitSessionsApi(kitId),
  })
  const [cursor, setCursor] = useState(() => { const d = new Date(); d.setDate(1); return d })
  const [selected, setSelected] = useState<string | null>(null)

  const byDay = useMemo(() => {
    const map = new Map<string, KitSession[]>()
    for (const s of sessions) {
      const list = map.get(s.meeting_date)
      if (list) list.push(s)
      else map.set(s.meeting_date, [s])
    }
    return map
  }, [sessions])

  const today = dateKey(new Date())
  const year = cursor.getFullYear()
  const month = cursor.getMonth()
  const firstWeekday = (new Date(year, month, 1).getDay() + 6) % 7 // Monday-first
  const daysInMonth = new Date(year, month + 1, 0).getDate()

  const cells: (Date | null)[] = [
    ...Array.from({ length: firstWeekday }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => new Date(year, month, i + 1)),
  ]
  while (cells.length % 7 !== 0) cells.push(null)

  const upcoming = sessions.filter((s) => s.meeting_date >= today)
  const past = sessions.filter((s) => s.meeting_date < today)
  const selectedSessions = selected ? byDay.get(selected) ?? [] : []

  if (isLoading) {
    return <p className="text-xs text-muted-foreground">Loading…</p>
  }

  if (sessions.length === 0) {
    return <p className="text-xs text-muted-foreground">This kit hasn't been assigned to a session yet.</p>
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setCursor(new Date(year, month - 1, 1))}
          className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
        >
          <ChevronLeft size={14} />
        </button>
        <p className="text-xs font-semibold text-foreground">
          {cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
        </p>
        <button
          type="button"
          onClick={() => setCursor(new Date(year, month + 1, 1))}
          className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
        >
          <ChevronRight size={14} />
        </button>
      </div>

      <div>
        <div className="grid grid-cols-7 gap-0.5 mb-0.5">
          {WEEKDAYS.map((d) => (
            <span key={d} className="text-center text-[9px] font-medium text-muted-foreground">{d}</span>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-0.5">
          {cells.map((date, i) => {
            if (!date) return <div key={i} className={compact ? "aspect-square" : "aspect-square"} />
            const key = dateKey(date)
            const daySessions = byDay.get(key) ?? []
            const has = daySessions.length > 0
            return (
              <button
                type="button"
                key={i}
                disabled={!has}
                onClick={() => setSelected(selected === key ? null : key)}
                title={daySessions.map((s) => s.title).join(", ")}
                className={cn(
                  "aspect-square rounded-md text-[10px] flex flex-col items-center justify-center gap-0.5 transition-colors",
                  has
                    ? "bg-primary/10 text-primary font-semibold hover:bg-primary/20 cursor-pointer"
                    : "text-muted-foreground/70",
                  selected === key && "ring-2 ring-primary",
                  key === today && "ring-1 ring-foreground/40",
                )}
              >
                <span>{date.getDate()}</span>
                {has && <span className="w-1 h-1 rounded-full bg-primary" />}
              </button>
            )
          })}
        </div>
      </div>

      {selectedSessions.length > 0 && (
        <div className="flex flex-col gap-1.5 rounded-xl border border-border bg-background/50 p-2">
          {selectedSessions.map((s) => (
            <SessionLine key={s.session_id} session={s} />
          ))}
        </div>
      )}

      {!compact && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Upcoming ({upcoming.length})
            </p>
            <div className="flex flex-col gap-1 max-h-40 overflow-y-auto">
              {upcoming.length === 0
                ? <p className="text-xs text-muted-foreground">Nothing booked yet.</p>
                : upcoming.map((s) => <SessionLine key={s.session_id} session={s} />)}
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Past ({past.length})
            </p>
            <div className="flex flex-col gap-1 max-h-40 overflow-y-auto">
              {past.length === 0
                ? <p className="text-xs text-muted-foreground">No history yet.</p>
                : [...past].reverse().map((s) => <SessionLine key={s.session_id} session={s} />)}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function SessionLine({ session }: { session: KitSession }) {
  return (
    <Link
      to="/operations/cohorts/$cohortId/sessions/$sessionId"
      params={{ cohortId: session.cohort_id, sessionId: session.session_id }}
      className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg text-xs hover:bg-muted/60 transition-colors"
    >
      <span className="min-w-0">
        <span className="font-medium text-foreground">{session.title}</span>
        <span className="text-muted-foreground"> · {session.cohort_name}</span>
      </span>
      <span className="flex items-center gap-1 shrink-0 text-muted-foreground">
        <Clock size={10} />
        {new Date(session.meeting_date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
        {session.return_status && ` · ${RETURN_LABEL[session.return_status] ?? session.return_status}`}
      </span>
    </Link>
  )
}
