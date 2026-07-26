import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Calendar, MapPin, Users } from "lucide-react"
import { listAvailableSessionsApi, registerInterestApi, withdrawInterestApi } from "@/api/sessions/staffing"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"
import { SessionsSubNav } from "@/components/layout/SessionsSubNav"

export default function AvailableSessions() {
  const qc = useQueryClient()
  const [notes, setNotes] = useState<Record<string, string>>({})

  const sessions = useQuery({ queryKey: ["staffing-available-sessions"], queryFn: listAvailableSessionsApi })

  const register = useMutation({
    mutationFn: (sessionId: string) => registerInterestApi(sessionId, notes[sessionId]),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["staffing-available-sessions"] }),
  })
  const withdraw = useMutation({
    mutationFn: (sessionId: string) => withdrawInterestApi(sessionId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["staffing-available-sessions"] }),
  })

  if (sessions.isLoading) return <Spinner />

  return (
    <div>
      <SessionsSubNav activeTab="available" />
      <PageHeader title="Available Sessions" subtitle="Sessions open for interest — register for the ones you'd like to teach." />

      {(sessions.data ?? []).length === 0 ? (
        <EmptyState title="No sessions open right now" hint="Check back once ops opens a call for a session." />
      ) : (
        <div className="space-y-3">
          {sessions.data!.map((s) => {
            const pending = (register.isPending && register.variables === s.session_id) || (withdraw.isPending && withdraw.variables === s.session_id)
            return (
              <Card key={s.session_id}>
                <CardContent className="p-5">
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="min-w-0">
                      <p className="font-semibold break-words">{s.program_name}</p>
                      <p className="text-xs text-muted-foreground break-words">{s.cohort_name}</p>
                    </div>
                    <span className="shrink-0 inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-0.5 rounded-full border bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-900/50">
                      <Users size={12} /> {s.interested_count} interested
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-4 text-sm text-muted-foreground mb-3">
                    <span className="flex items-center gap-1.5">
                      <Calendar size={14} />
                      {new Date(s.meeting_date).toLocaleDateString(undefined, { weekday: "short", year: "numeric", month: "short", day: "numeric" })}
                      {s.starts_at ? ` · ${s.starts_at.slice(0, 5)}` : ""}
                    </span>
                    {s.location && (
                      <span className="flex items-center gap-1.5"><MapPin size={14} /> {s.location}</span>
                    )}
                  </div>

                  {s.my_interest ? (
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">You've registered interest{s.my_note ? `: "${s.my_note}"` : ""}</span>
                      <Button size="sm" variant="outline" disabled={pending} onClick={() => withdraw.mutate(s.session_id)}>
                        Withdraw
                      </Button>
                    </div>
                  ) : (
                    <div className="flex flex-col sm:flex-row gap-2">
                      <input
                        className="input flex-1"
                        placeholder="Optional note to ops (why you'd like this one)…"
                        value={notes[s.session_id] ?? ""}
                        onChange={(e) => setNotes({ ...notes, [s.session_id]: e.target.value })}
                      />
                      <Button size="sm" disabled={pending} onClick={() => register.mutate(s.session_id)}>
                        {pending ? "Registering…" : "Register interest"}
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
