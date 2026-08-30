import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Calendar, Clock, ExternalLink, MapPin, Users } from "lucide-react"
import { listAvailableWorkApi, registerInterestApi, withdrawInterestApi } from "@/api/sessions/staffing"
import { acceptResponsibilitiesApi, getResponsibilitiesApi } from "@/api/sessions/openings"
import type { AvailableSession } from "@/types/sessions"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"
import { SessionsSubNav } from "@/components/layout/SessionsSubNav"
import { getErrorMessage } from "@/lib/utils"
import CohortCallCard from "@/pages/instructors/components/CohortCallCard"
import {
  ApplyFooter,
  ResponsibilitiesDetails,
  RoleOpeningsPicker,
  SupportQuestionsPanel,
} from "@/pages/instructors/components/CallFormParts"

/**
 * Two groups, not one flat list (2026-08-24). A cohort call is a single
 * decision about a run of days — one role, the days you can do — so it gets a
 * card of its own. A session opened on its own is still a standalone offer and
 * keeps the original card. The server guarantees a session appears in exactly
 * one of the two lists, so nothing is offered twice.
 */
export default function AvailableSessions() {
  const work = useQuery({ queryKey: ["available-work"], queryFn: listAvailableWorkApi })

  if (work.isLoading) return <Spinner />

  const cohortCalls = work.data?.cohort_calls ?? []
  const singles = work.data?.single_sessions ?? []
  const nothing = cohortCalls.length === 0 && singles.length === 0

  return (
    <div>
      <SessionsSubNav activeTab="available" />
      <PageHeader
        title="Available Work"
        subtitle="Open calls you can register for — pick a role and the days you can deliver."
      />

      {nothing ? (
        <EmptyState title="Nothing open right now" hint="Check back once ops opens a call." />
      ) : (
        <div className="space-y-6">
          {cohortCalls.length > 0 && (
            <div className="space-y-3">
              {cohortCalls.map((c) => <CohortCallCard key={c.cohort_call_id} c={c} />)}
            </div>
          )}

          {singles.length > 0 && (
            <div className="space-y-3">
              {cohortCalls.length > 0 && (
                <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Single sessions
                </h2>
              )}
              {singles.map((s) => <SessionCard key={s.session_id} s={s} />)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** One session's offer, own its own role selection and responsibilities —
 *  each pulls the combined text for whichever role is currently picked
 *  (general text + that role's own description), not one generic block
 *  shared across every role a session offers.
 *
 *  Shares its form parts with CohortCallCard (2026-08-30) — this used to be
 *  a lighter, older design that never got the operations process doc §2
 *  support questions or the collapsible responsibilities block the cohort
 *  form gained on 2026-08-24. */
function SessionCard({ s }: { s: AvailableSession }) {
  const qc = useQueryClient()
  const [note, setNote] = useState(s.my_note ?? "")
  const [concerns, setConcerns] = useState(s.my_concerns ?? "")
  const [needsTransport, setNeedsTransport] = useState(s.my_needs_transport ?? false)
  const [travelling, setTravelling] = useState(s.my_travelling_from_other_city ?? false)
  const [respOpen, setRespOpen] = useState(false)
  const [agreed, setAgreed] = useState(false)
  const [error, setError] = useState("")
  // B1: which opening they're applying for. Defaults to the first role a
  // session is soliciting for once its openings load.
  const [roleId, setRoleId] = useState<string | null>(s.openings[0]?.role_id ?? null)

  const responsibilities = useQuery({
    queryKey: ["responsibilities", roleId ?? "general"],
    queryFn: () => getResponsibilitiesApi(roleId),
  })

  const accept = useMutation({ mutationFn: acceptResponsibilitiesApi })

  const register = useMutation({
    mutationFn: async () => {
      await registerInterestApi(s.session_id, {
        note: note || null, role_id: roleId,
        needs_transport: needsTransport, needs_ops_support: false,
        travelling_from_other_city: travelling, concerns: concerns || null,
      })
      // Recorded against the version that was on screen — the server refuses
      // a stale one rather than accepting agreement to unread wording.
      if (responsibilities.data?.text) {
        await accept.mutateAsync({ sessionId: s.session_id, version: responsibilities.data.version })
      }
    },
    onSuccess: () => {
      setError("")
      qc.invalidateQueries({ queryKey: ["available-work"] })
    },
    onError: (e) => setError(getErrorMessage(e, "Could not register your interest")),
  })
  const withdraw = useMutation({
    mutationFn: () => withdrawInterestApi(s.session_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["available-work"] }),
  })

  const pending = register.isPending || withdraw.isPending

  const handleApply = () => {
    setError("")
    if (s.openings.length > 0 && !roleId) {
      setError("Please pick a role above before applying.")
      return
    }
    if (responsibilities.data?.text && !agreed) {
      setError("Please view and agree to the Responsibilities to apply.")
      setRespOpen(true)
      return
    }
    register.mutate()
  }

  const isReady = (!s.openings.length || !!roleId) && (!responsibilities.data?.text || agreed)

  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="min-w-0">
            {/* The session title is what an instructor is actually deciding
                about — program + cohort alone don't say what they'd teach. */}
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
          {s.location_address && (
            <span className="flex items-center gap-1.5">{s.location_address}</span>
          )}
          {s.duration_hours != null && (
            <span className="flex items-center gap-1.5"><Clock size={14} /> {s.duration_hours}h</span>
          )}
        </div>

        {s.description && (
          <p className="text-sm text-muted-foreground mb-3 whitespace-pre-line">{s.description}</p>
        )}

        {/* I5-5 / B1: the offer itself — per role, with what is left. Before
            they've applied, it doubles as the role picker: what they're
            applying for, not something ops guesses afterward from a
            hardcoded Lead/Co-instructor split. */}
        <RoleOpeningsPicker
          openings={s.openings} myInterest={s.my_interest} roleId={roleId}
          onSelect={setRoleId} groupName={`role-${s.session_id}`}
        />
        {s.addons.length > 0 && (
          <div className="mb-3 flex flex-col gap-1.5">
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
            <Button size="sm" variant="outline" disabled={pending} onClick={() => withdraw.mutate()}>
              Withdraw
            </Button>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {/* Operations process doc §2 — same questions a cohort call's
                form asks, brought here 2026-08-30. */}
            <SupportQuestionsPanel
              needsTransport={needsTransport} onNeedsTransportChange={setNeedsTransport}
              travelling={travelling} onTravellingChange={setTravelling}
              concerns={concerns} onConcernsChange={setConcerns}
            />

            {/* B1: scoped to the role picked above — a role's own wording
                (e.g. "carry the kit") is part of what's being agreed to, not
                a separate blurb next to a generic agreement that ignores it. */}
            {responsibilities.data?.text && (
              <ResponsibilitiesDetails
                text={responsibilities.data.text} roleName={responsibilities.data.role_name}
                agreed={agreed}
                onAgreedChange={(v) => { setAgreed(v); if (v) setError("") }}
                open={respOpen} onOpenChange={setRespOpen}
                hasError={!!error && !agreed}
              />
            )}

            <ApplyFooter
              note={note} onNoteChange={setNote}
              ready={isReady} pending={pending} pendingLabel="Registering…"
              onApply={handleApply}
              extra={<>
                {s.openings.length > 0 && !roleId && (
                  <p className="text-xs text-muted-foreground">Pick a role above before applying.</p>
                )}
                {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
              </>}
            />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
