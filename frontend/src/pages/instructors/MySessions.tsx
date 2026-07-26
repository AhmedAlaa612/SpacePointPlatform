import { useState, useMemo } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { Calendar, MapPin, Search, Filter, CheckCircle2, PlayCircle, Clock, AlertTriangle } from "lucide-react"
import { listMySessionsApi, declineAssignmentApi } from "@/api/sessions/staffing"
import type { MySession } from "@/types/sessions"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"

const ROLE_LABEL: Record<string, string> = { lead: "Lead instructor", co: "Co-instructor" }

type SessionState = "all" | "completed" | "in_progress" | "scheduled"

import { SessionsSubNav } from "@/components/layout/SessionsSubNav"

function getSessionState(s: MySession): "completed" | "in_progress" | "scheduled" {
  if (s.completed_at) return "completed"
  if (s.started_at) return "in_progress"
  return "scheduled"
}

export default function MySessions() {
  const qc = useQueryClient()
  const [search, setSearch] = useState("")
  const [stateFilter, setStateFilter] = useState<SessionState>("all")
  const [dateFilter, setDateFilter] = useState("")
  const [declineTarget, setDeclineTarget] = useState<MySession | null>(null)
  const [declineReason, setDeclineReason] = useState("")

  const sessions = useQuery({ queryKey: ["staffing-my-sessions"], queryFn: listMySessionsApi })

  const declineMutation = useMutation({
    mutationFn: () => declineAssignmentApi(declineTarget!.session_id, declineReason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["staffing-my-sessions"] })
      setDeclineTarget(null)
      setDeclineReason("")
    },
  })

  const rawList = sessions.data ?? []

  const filteredSessions = useMemo(() => {
    return rawList.filter((s) => {
      const state = getSessionState(s)
      if (stateFilter !== "all" && state !== stateFilter) return false
      if (dateFilter && s.meeting_date !== dateFilter) return false

      if (search.trim()) {
        const q = search.toLowerCase()
        const text = `${s.program_name} ${s.cohort_name} ${s.location ?? ""}`.toLowerCase()
        if (!text.includes(q)) return false
      }
      return true
    })
  }, [rawList, search, stateFilter, dateFilter])

  if (sessions.isLoading) return <Spinner />

  return (
    <div className="space-y-4">
      <SessionsSubNav activeTab="my" />
      <PageHeader title="My Sessions" subtitle="Sessions you're assigned to teach." />

      {/* Filter Bar */}
      <div className="p-4 bg-card border border-border rounded-2xl flex flex-wrap items-center gap-3 shadow-xs">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search by program, cohort, location..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 h-9 bg-background border border-border rounded-xl text-xs focus:outline-none focus:border-primary transition-colors"
          />
        </div>

        <div className="flex items-center gap-2">
          <Filter size={14} className="text-muted-foreground" />
          <select
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value as SessionState)}
            className="h-9 px-3 bg-background border border-border rounded-xl text-xs focus:outline-none focus:border-primary cursor-pointer"
          >
            <option value="all">All States</option>
            <option value="scheduled">Scheduled</option>
            <option value="in_progress">In Progress</option>
            <option value="completed">Completed / Done</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <Calendar size={14} className="text-muted-foreground" />
          <input
            type="date"
            value={dateFilter}
            onChange={(e) => setDateFilter(e.target.value)}
            className="h-9 px-3 bg-background border border-border rounded-xl text-xs focus:outline-none focus:border-primary cursor-pointer"
          />
          {dateFilter && (
            <button
              onClick={() => setDateFilter("")}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors underline"
            >
              Clear date
            </button>
          )}
        </div>
      </div>

      {filteredSessions.length === 0 ? (
        <EmptyState
          title={rawList.length === 0 ? "No sessions assigned yet" : "No sessions match your filters"}
          hint={rawList.length === 0 ? "Register interest on the Available Sessions page to get picked up by ops." : "Try adjusting your search criteria or clearing filters."}
        />
      ) : (
        <div className="space-y-3">
          {filteredSessions.map((s) => {
            const st = getSessionState(s)
            return (
              <Card key={s.session_id} className="transition-colors hover:border-primary/40 hover:bg-foreground/5 relative group">
                <CardContent className="p-5">
                  <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Link to="/instructors/sessions/$sessionId" params={{ sessionId: s.session_id }} className="font-semibold text-foreground hover:text-primary transition-colors text-base break-words w-full sm:w-auto">
                          {s.program_name}
                        </Link>

                        {st === "completed" && (
                          <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 border border-emerald-500/20">
                            <CheckCircle2 size={12} /> Completed
                          </span>
                        )}
                        {st === "in_progress" && (
                          <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400 border border-blue-500/20">
                            <PlayCircle size={12} /> In Progress
                          </span>
                        )}
                        {st === "scheduled" && (
                          <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2.5 py-0.5 rounded-full bg-muted text-muted-foreground border border-border">
                            <Clock size={12} /> Scheduled
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground break-words mt-0.5">{s.cohort_name}</p>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <span className="inline-flex items-center text-[11px] font-semibold px-2.5 py-1 rounded-full border bg-primary/10 text-primary border-primary/20">
                        {ROLE_LABEL[s.my_role] ?? s.my_role}
                      </span>
                      {st === "scheduled" && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            setDeclineTarget(s)
                          }}
                          className="text-xs font-medium text-muted-foreground hover:text-red-500 px-2 py-1 rounded-lg hover:bg-red-500/10 transition-colors"
                          title="Submit excuse / decline assignment"
                        >
                          Request Excuse
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-4 text-sm text-muted-foreground pt-2 border-t border-border/50">
                    <div className="flex flex-wrap gap-4">
                      <span className="flex items-center gap-1.5 text-xs font-medium">
                        <Calendar size={14} />
                        {new Date(s.meeting_date).toLocaleDateString(undefined, { weekday: "short", year: "numeric", month: "short", day: "numeric" })}
                        {s.starts_at ? ` · ${s.starts_at.slice(0, 5)}` : ""}
                      </span>
                      {s.location && (
                        <span className="flex items-center gap-1.5 text-xs font-medium"><MapPin size={14} /> {s.location}</span>
                      )}
                    </div>

                    <Link
                      to="/instructors/sessions/$sessionId"
                      params={{ sessionId: s.session_id }}
                      className="text-xs font-semibold text-primary hover:underline flex items-center gap-1 ml-auto"
                    >
                      Open session portal →
                    </Link>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {/* Decline Excuse Modal */}
      <Dialog open={!!declineTarget} onOpenChange={(o) => !o && setDeclineTarget(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-500">
              <AlertTriangle size={18} /> Request Excuse / Decline Session
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-xs text-muted-foreground">
              Are you sure you cannot teach <strong>{declineTarget?.program_name}</strong> on <strong>{declineTarget?.meeting_date}</strong>? Operations will be notified.
            </p>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Reason / Excuse Note (Optional):</label>
              <textarea
                value={declineReason}
                onChange={(e) => setDeclineReason(e.target.value)}
                placeholder="e.g. Flight delay, emergency conflict..."
                className="w-full h-20 p-2.5 bg-background border border-border rounded-xl text-xs focus:outline-none focus:border-primary"
              />
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setDeclineTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={declineMutation.isPending}
              onClick={() => declineMutation.mutate()}
            >
              {declineMutation.isPending ? "Submitting…" : "Decline Assignment"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
