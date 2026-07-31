import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Calendar, Clock, ExternalLink, MapPin, Users } from "lucide-react"
import { listAvailableSessionsApi, registerInterestApi, withdrawInterestApi } from "@/api/sessions/staffing"
import { acceptResponsibilitiesApi, getResponsibilitiesApi } from "@/api/sessions/openings"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"
import { SessionsSubNav } from "@/components/layout/SessionsSubNav"

export default function AvailableSessions() {
  const qc = useQueryClient()
  const [notes, setNotes] = useState<Record<string, string>>({})
  // B1: which opening they're applying for. Defaults to the first role a
  // session is soliciting for once its openings load.
  const [roleChoice, setRoleChoice] = useState<Record<string, string>>({})

  const sessions = useQuery({ queryKey: ["staffing-available-sessions"], queryFn: listAvailableSessionsApi })
  // I5-5: shown with every invite, ticked before registering interest.
  const { data: responsibilities } = useQuery({
    queryKey: ["responsibilities"], queryFn: getResponsibilitiesApi,
  })
  const [agreed, setAgreed] = useState<Record<string, boolean>>({})
  const [error, setError] = useState("")

  useEffect(() => {
    if (!sessions.data) return
    setRoleChoice((prev) => {
      const next = { ...prev }
      let changed = false
      for (const s of sessions.data!) {
        if (!next[s.session_id] && s.openings.length > 0) {
          next[s.session_id] = s.openings[0].role_id
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [sessions.data])

  const accept = useMutation({ mutationFn: acceptResponsibilitiesApi })

  const register = useMutation({
    mutationFn: async (sessionId: string) => {
      await registerInterestApi(sessionId, notes[sessionId], roleChoice[sessionId] ?? null)
      // Recorded against the version that was on screen — the server refuses
      // a stale one rather than accepting agreement to unread wording.
      if (responsibilities?.text) {
        await accept.mutateAsync({ sessionId, version: responsibilities.version })
      }
    },
    onSuccess: () => {
      setError("")
      qc.invalidateQueries({ queryKey: ["staffing-available-sessions"] })
    },
    onError: (e: any) =>
      setError(e?.response?.data?.detail ?? "Could not register your interest"),
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
                      {/* The session title is what an instructor is actually
                          deciding about — program + cohort alone don't say
                          what they'd be teaching. */}
                      <p className="font-semibold break-words">{s.title || s.program_name}</p>
                      <p className="text-xs text-muted-foreground break-words">
                        {s.title ? `${s.program_name} · ${s.cohort_name}` : s.cohort_name}
                      </p>
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
                      <span className="flex items-center gap-1.5">
                        <MapPin size={14} /> {s.location}
                        {s.location_map_url && (
                          <a href={s.location_map_url} target="_blank" rel="noreferrer"
                             className="inline-flex items-center gap-0.5 text-primary hover:underline">
                            map <ExternalLink size={11} />
                          </a>
                        )}
                      </span>
                    )}
                    {s.duration_hours != null && (
                      <span className="flex items-center gap-1.5"><Clock size={14} /> {s.duration_hours}h</span>
                    )}
                  </div>

                  {s.description && (
                    <p className="text-sm text-muted-foreground mb-3 whitespace-pre-line">{s.description}</p>
                  )}

                  {/* I5-5: the offer itself — per role, with what is left. */}
                  {s.openings.length > 0 && (
                    <div className="mb-3 flex flex-col gap-1.5">
                      {s.openings.map((o) => {
                        const full = o.remaining <= 0
                        return (
                          <label
                            key={o.role_id}
                            className={`flex items-start justify-between gap-3 text-sm rounded-lg px-2 py-1.5 -mx-2 transition-colors ${
                              !s.my_interest && !full ? "cursor-pointer hover:bg-muted" : ""
                            } ${!s.my_interest && roleChoice[s.session_id] === o.role_id ? "bg-primary/5 ring-1 ring-primary/20" : ""}`}
                          >
                            <div className="flex items-start gap-2 min-w-0">
                              {!s.my_interest && (
                                <input
                                  type="radio"
                                  name={`role-${s.session_id}`}
                                  className="mt-1 shrink-0"
                                  checked={roleChoice[s.session_id] === o.role_id}
                                  disabled={full}
                                  onChange={() => setRoleChoice({ ...roleChoice, [s.session_id]: o.role_id })}
                                />
                              )}
                              <div className="min-w-0">
                                <span className="text-foreground">
                                  {o.role_name}
                                  <span className="text-xs text-muted-foreground">
                                    {" "}&middot; {o.remaining > 0 ? `${o.remaining} of ${o.slots} left` : "full \u2014 waitlist"}
                                  </span>
                                </span>
                                {o.role_description && (
                                  <p className="text-xs text-muted-foreground">{o.role_description}</p>
                                )}
                              </div>
                            </div>
                            {o.amount_aed != null && (
                              <span className="text-sm font-semibold tabular-nums shrink-0">
                                AED {o.amount_aed.toLocaleString()}
                              </span>
                            )}
                          </label>
                        )
                      })}
                      {s.addons.map((a, i) => (
                        <div key={i} className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                          <span>+ {a.description}</span>
                          <span className="tabular-nums">AED {a.amount_aed.toLocaleString()}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {s.my_interest ? (
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">You've registered interest{s.my_note ? `: "${s.my_note}"` : ""}</span>
                      <Button size="sm" variant="outline" disabled={pending} onClick={() => withdraw.mutate(s.session_id)}>
                        Withdraw
                      </Button>
                    </div>
                  ) : (
                    <div className="flex flex-col gap-2">
                      {responsibilities?.text && (
                        <div className="rounded-xl border border-border bg-background/50 p-3 flex flex-col gap-2">
                          <p className="text-xs font-semibold text-foreground">Responsibilities</p>
                          <p className="text-xs text-muted-foreground whitespace-pre-line max-h-32 overflow-y-auto">
                            {responsibilities.text}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {responsibilities.payment_terms_note}
                          </p>
                          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer select-none">
                            <input
                              type="checkbox"
                              checked={agreed[s.session_id] ?? false}
                              onChange={(e) => setAgreed({ ...agreed, [s.session_id]: e.target.checked })}
                              className="rounded text-primary focus:ring-primary border-border bg-background"
                            />
                            I have read and agree to these
                          </label>
                        </div>
                      )}
                      <div className="flex flex-col sm:flex-row gap-2">
                        <input
                          className="input flex-1"
                          placeholder="Optional note to ops (why you'd like this one)…"
                          value={notes[s.session_id] ?? ""}
                          onChange={(e) => setNotes({ ...notes, [s.session_id]: e.target.value })}
                        />
                        <Button
                          size="sm"
                          disabled={
                            pending ||
                            (!!responsibilities?.text && !agreed[s.session_id]) ||
                            (s.openings.length > 0 && !roleChoice[s.session_id])
                          }
                          onClick={() => { setError(""); register.mutate(s.session_id) }}
                        >
                          {pending ? "Registering…" : "Register interest"}
                        </Button>
                      </div>
                      {s.openings.length > 0 && !roleChoice[s.session_id] && (
                        <p className="text-xs text-muted-foreground">Pick a role above before applying.</p>
                      )}
                      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
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
