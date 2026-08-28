import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import {
  Calendar, MapPin, ExternalLink, CheckCircle2, AlertTriangle, Clock, CircleAlert, CircleCheck,
} from "lucide-react"
import { listMySessionsApi } from "@/api/sessions/staffing"
import { checkInApi } from "@/api/sessions/day"
import type { MySession } from "@/types/sessions"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"
import { SessionsSubNav } from "@/components/layout/SessionsSubNav"
import { getErrorMessage } from "@/lib/utils"

const ROLE_LABEL: Record<string, string> = { lead: "Lead instructor", co: "Co-instructor" }

function todayIso() {
  return new Date().toISOString().slice(0, 10)
}

function fmtDate(d: string) {
  return new Date(d).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })
}

/** What's worth telling the instructor at a glance, in priority order — the
 *  most consequential thing that's happened to this day so far. */
function DayStatusPill({ s }: { s: MySession }) {
  if (s.day_status === "approved") {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 border border-emerald-500/20">
        <CircleCheck size={12} /> Approved
      </span>
    )
  }
  if (s.day_status === "changes_required") {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400 border border-amber-500/20">
        <CircleAlert size={12} /> Changes requested
      </span>
    )
  }
  if (s.day_status === "submitted") {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400 border border-blue-500/20">
        <Clock size={12} /> Submitted
      </span>
    )
  }
  if (s.att_status === "absent") {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-muted text-muted-foreground border border-border">
        Excused
      </span>
    )
  }
  if (s.checked_in_at) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400 border border-blue-500/20">
        <CheckCircle2 size={12} /> Checked in
      </span>
    )
  }
  return null
}

function LocationLine({ s }: { s: MySession }) {
  if (!s.location) return null
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      <span className="flex items-center gap-1.5 font-medium"><MapPin size={13} /> {s.location}</span>
      {s.location_address && <span>{s.location_address}</span>}
      {s.location_maps_url && (
        <a href={s.location_maps_url} target="_blank" rel="noreferrer"
          className="flex items-center gap-1 font-medium text-primary hover:underline">
          Open in maps <ExternalLink size={11} />
        </a>
      )}
    </div>
  )
}

/** The one card shape, three ways to use it: a "today" hero (check-in +
 *  excuse + portal), a compact upcoming row (excuse + portal), or a compact
 *  past row (status only, no actions — the day is over). */
function SessionCard({
  s, variant, onCheckIn, onExcuse, checkingIn,
}: {
  s: MySession
  variant: "today" | "upcoming" | "past"
  onCheckIn: (s: MySession) => void
  onExcuse: (s: MySession) => void
  checkingIn: boolean
}) {
  const isToday = variant === "today"
  return (
    <Card className={isToday
      ? "border-primary/40 bg-primary/[0.03] transition-colors"
      : "transition-colors hover:border-primary/40 hover:bg-foreground/5"}
    >
      <CardContent className="p-5 flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0 flex-1">
            {isToday && (
              <p className="text-[11px] font-semibold uppercase tracking-wide text-primary mb-1">Today</p>
            )}
            <Link to="/instructors/sessions/$sessionId" params={{ sessionId: s.session_id }}
              className="font-semibold text-foreground hover:text-primary transition-colors text-base break-words">
              {s.title || s.program_name}
            </Link>
            <p className="text-xs text-muted-foreground break-words mt-0.5">
              {s.title ? `${s.program_name} · ${s.cohort_name}` : s.cohort_name}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="inline-flex items-center text-[11px] font-semibold px-2.5 py-1 rounded-full border bg-primary/10 text-primary border-primary/20">
              {ROLE_LABEL[s.my_role] ?? s.my_role}
            </span>
            <DayStatusPill s={s} />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5 font-medium">
            <Calendar size={13} />
            {fmtDate(s.meeting_date)}{s.starts_at ? ` · ${s.starts_at.slice(0, 5)}` : ""}
          </span>
          <LocationLine s={s} />
        </div>

        <div className="flex items-center gap-2 pt-2 border-t border-border/50 flex-wrap">
          {isToday && !s.checked_in_at && s.att_status !== "absent" && (
            <Button size="sm" disabled={checkingIn} onClick={() => onCheckIn(s)}>
              {checkingIn ? "Checking in…" : "Check in"}
            </Button>
          )}
          {variant !== "past" && s.att_status !== "absent" && s.day_status !== "submitted" && s.day_status !== "approved" && (
            <button
              type="button"
              onClick={() => onExcuse(s)}
              className="text-xs font-medium text-muted-foreground hover:text-red-500 px-2.5 py-1.5 rounded-lg hover:bg-red-500/10 transition-colors"
            >
              Submit excuse
            </button>
          )}
          <Link
            to="/instructors/sessions/$sessionId"
            params={{ sessionId: s.session_id }}
            className="text-xs font-semibold text-primary hover:underline flex items-center gap-1 ml-auto"
          >
            Go to session portal →
          </Link>
        </div>
      </CardContent>
    </Card>
  )
}

type SubTab = "upcoming" | "past"

export default function MySessions() {
  const qc = useQueryClient()
  const [subTab, setSubTab] = useState<SubTab>("upcoming")
  const [excuseTarget, setExcuseTarget] = useState<MySession | null>(null)
  const [excuseReason, setExcuseReason] = useState("")
  const [error, setError] = useState("")

  const sessions = useQuery({ queryKey: ["staffing-my-sessions"], queryFn: listMySessionsApi })
  const rawList = sessions.data ?? []

  const { todaysSessions, upcoming, past } = useMemo(() => {
    const today = todayIso()
    return {
      todaysSessions: rawList.filter((s) => s.meeting_date === today),
      upcoming: rawList.filter((s) => s.meeting_date > today),
      past: rawList.filter((s) => s.meeting_date < today).reverse(),
    }
  }, [rawList])

  const invalidate = () => qc.invalidateQueries({ queryKey: ["staffing-my-sessions"] })

  const checkIn = useMutation({
    mutationFn: (sessionId: string) => checkInApi(sessionId, "present"),
    onSuccess: invalidate,
    onError: (e: any) => setError(getErrorMessage(e, "Could not check in")),
  })

  const excuse = useMutation({
    mutationFn: () => checkInApi(excuseTarget!.session_id, "absent", excuseReason.trim() || undefined),
    onSuccess: () => {
      invalidate()
      setExcuseTarget(null)
      setExcuseReason("")
    },
    onError: (e: any) => setError(getErrorMessage(e, "Could not submit the excuse")),
  })

  if (sessions.isLoading) return <Spinner />

  const list = subTab === "upcoming" ? upcoming : past

  return (
    <div className="space-y-4">
      <SessionsSubNav activeTab="my" />
      <PageHeader title="My Sessions" subtitle="Sessions you're assigned to teach." />

      {error && (
        <div className="p-3 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl text-xs text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Today: one hero card per session that day — most instructors have
          zero or one, but a handful genuinely teach two in a day, and that
          must never collapse into a single card. Absent entirely when
          nothing's on today, rather than an empty "Today" section. */}
      {todaysSessions.length > 0 && (
        <div className="space-y-3">
          {todaysSessions.map((s) => (
            <SessionCard
              key={s.session_id} s={s} variant="today"
              onCheckIn={(s) => { setError(""); checkIn.mutate(s.session_id) }}
              onExcuse={(s) => { setError(""); setExcuseTarget(s) }}
              checkingIn={checkIn.isPending}
            />
          ))}
        </div>
      )}

      <div className="flex items-center gap-1 border-b border-border">
        {(["upcoming", "past"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setSubTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              subTab === t
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t === "upcoming" ? `Upcoming${upcoming.length ? ` (${upcoming.length})` : ""}` : "Past"}
          </button>
        ))}
      </div>

      {list.length === 0 ? (
        <EmptyState
          title={rawList.length === 0
            ? "No sessions assigned yet"
            : subTab === "upcoming" ? "Nothing upcoming" : "No past sessions yet"}
          hint={rawList.length === 0 ? "Register interest on the Available Sessions page to get picked up by ops." : undefined}
        />
      ) : (
        <div className="space-y-3">
          {list.map((s) => (
            <SessionCard
              key={s.session_id} s={s} variant={subTab}
              onCheckIn={(s) => { setError(""); checkIn.mutate(s.session_id) }}
              onExcuse={(s) => { setError(""); setExcuseTarget(s) }}
              checkingIn={checkIn.isPending}
            />
          ))}
        </div>
      )}

      <Dialog open={!!excuseTarget} onOpenChange={(o) => !o && setExcuseTarget(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-500">
              <AlertTriangle size={18} /> Submit an excuse
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-xs text-muted-foreground">
              Marks you absent for <strong>{excuseTarget?.program_name}</strong> on{" "}
              <strong>{excuseTarget && fmtDate(excuseTarget.meeting_date)}</strong>. Operations will see the reason.
            </p>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Reason (optional)</label>
              <textarea
                value={excuseReason}
                onChange={(e) => setExcuseReason(e.target.value)}
                placeholder="e.g. Driving exam, medical appointment…"
                className="w-full h-20 p-2.5 bg-background border border-border rounded-xl text-xs focus:outline-none focus:border-primary"
              />
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setExcuseTarget(null)}>Cancel</Button>
            <Button variant="destructive" disabled={excuse.isPending} onClick={() => excuse.mutate()}>
              {excuse.isPending ? "Submitting…" : "Submit excuse"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
