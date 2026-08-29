/** One cohort card on the instructor's Available Sessions page (2026-08-24).
 *
 * Replaces five near-identical session cards with a single decision: pick one
 * role for the whole cohort, tick the days you can do, answer the support
 * questions from the operations process doc §2, and apply once.
 *
 * The single-role rule (an instructor is Assistant in Cohort A and Instructor
 * in Cohort B, but never both inside one cohort) is the operator's, and it is
 * why the role control is a radio group rather than a per-day dropdown — the
 * UI makes the invalid state unrepresentable rather than validating it after
 * the fact. The backend enforces it too, with a 409 naming the clash.
 */
import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Calendar, Clock, ExternalLink, MapPin, Users } from "lucide-react"
import {
  registerCohortInterestApi,
  withdrawCohortInterestApi,
} from "@/api/sessions/staffing"
import { getResponsibilitiesApi } from "@/api/sessions/openings"
import type { AvailableCohortCall } from "@/types/sessions"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { getErrorMessage } from "@/lib/utils"

function formatDay(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric",
  })
}

function formatRange(from: string, to: string) {
  const opts: Intl.DateTimeFormatOptions = { year: "numeric", month: "short", day: "numeric" }
  if (from === to) return new Date(from).toLocaleDateString(undefined, opts)
  return `${new Date(from).toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${new Date(to).toLocaleDateString(undefined, opts)}`
}

export default function CohortCallCard({ c }: { c: AvailableCohortCall }) {
  const qc = useQueryClient()
  const [roleId, setRoleId] = useState<string | null>(
    c.my_role_id ?? c.openings.find((o) => o.remaining > 0)?.role_id ?? c.openings[0]?.role_id ?? null,
  )
  // Every day pre-ticked: taking the whole run is the common case, and
  // unticking the one you can't do is less work than ticking four you can.
  const [picked, setPicked] = useState<Set<string>>(
    () => new Set(
      c.my_interest
        ? c.sessions.filter((s) => s.selected).map((s) => s.session_id)
        : c.sessions.map((s) => s.session_id),
    ),
  )
  const [note, setNote] = useState(c.my_note ?? "")
  const [concerns, setConcerns] = useState(c.my_concerns ?? "")
  const [needsTransport, setNeedsTransport] = useState(c.my_needs_transport)
  const [travelling, setTravelling] = useState(c.my_travelling_from_other_city)
  const [respOpen, setRespOpen] = useState(false)
  const [agreed, setAgreed] = useState(false)
  const [error, setError] = useState("")

  const responsibilities = useQuery({
    queryKey: ["responsibilities", roleId ?? "general", c.cohort_id],
    queryFn: () => getResponsibilitiesApi(roleId, c.cohort_id),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ["available-work"] })

  const register = useMutation({
    mutationFn: () =>
      registerCohortInterestApi(c.cohort_id, c.cohort_call_id, {
        session_ids: [...picked],
        role_id: roleId,
        note: note || null,
        needs_transport: needsTransport,
        needs_ops_support: false,
        travelling_from_other_city: travelling,
        concerns: concerns || null,
        responsibilities_version: responsibilities.data?.text
          ? responsibilities.data.version
          : null,
      }),
    onSuccess: () => { setError(""); invalidate() },
    onError: (e) => setError(getErrorMessage(e, "Could not register your interest")),
  })

  const withdraw = useMutation({
    mutationFn: () => withdrawCohortInterestApi(c.cohort_id, c.cohort_call_id),
    onSuccess: invalidate,
    onError: (e) => setError(getErrorMessage(e, "Could not withdraw")),
  })

  const pending = register.isPending || withdraw.isPending
  const toggleDay = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const handleApply = () => {
    setError("")
    if (c.openings.length > 0 && !roleId) {
      setError("Please pick a role above before applying.")
      return
    }
    if (picked.size === 0) {
      setError("Please pick at least one session date.")
      return
    }
    if (responsibilities.data?.text && !agreed) {
      setError("Please view and agree to the Responsibilities to apply.")
      setRespOpen(true)
      return
    }
    register.mutate()
  }

  useEffect(() => {
    if (c.my_interest || !roleId) return
    const openForRole = c.sessions
      .filter((s) => !s.open_role_ids || s.open_role_ids.length === 0 || s.open_role_ids.includes(roleId))
      .map((s) => s.session_id)
    setPicked(new Set(openForRole))
  }, [roleId])

  const isReady =
    picked.size > 0 &&
    (!c.openings.length || !!roleId) &&
    (!responsibilities.data?.text || agreed)

  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="min-w-0">
            <p className="font-semibold break-words">{c.cohort_name}</p>
            <p className="text-xs text-muted-foreground break-words">
              {c.program_name}{c.label ? ` · ${c.label}` : ""}
            </p>
          </div>
          <span className="shrink-0 inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-0.5 rounded-full border bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-900/50">
            <Users size={12} /> {c.interested_count} interested
          </span>
        </div>

        <div className="flex flex-wrap gap-4 text-sm text-muted-foreground mb-3">
          <span className="flex items-center gap-1.5">
            <Calendar size={14} /> {formatRange(c.starts_on, c.ends_on)}
          </span>
          <span className="flex items-center gap-1.5">
            <Clock size={14} /> {c.session_count} session{c.session_count === 1 ? "" : "s"}
          </span>
          {c.location && (
            <span className="flex items-center gap-1.5">
              <MapPin size={14} /> {c.location}{c.location_city ? `, ${c.location_city}` : ""}
              {c.location_map_url && (
                <a href={c.location_map_url} target="_blank" rel="noreferrer"
                   className="inline-flex items-center gap-0.5 text-primary hover:underline">
                  map <ExternalLink size={11} />
                </a>
              )}
            </span>
          )}
          {c.location_address && <span>{c.location_address}</span>}
        </div>

        {c.description && (
          <p className="text-sm text-muted-foreground mb-3 whitespace-pre-line">{c.description}</p>
        )}

        {/* One role for the whole cohort — the operator's rule, made
            structural rather than validated after the fact. */}
        {c.openings.length > 0 && (
          <div className="mb-3 flex flex-col gap-1.5">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Role</p>
            {c.openings.map((o) => {
              const full = o.remaining <= 0
              return (
                <label
                  key={o.role_id}
                  className={`flex items-start justify-between gap-3 text-sm rounded-lg px-2 py-1.5 -mx-2 transition-colors ${
                    !c.my_interest && !full ? "cursor-pointer hover:bg-muted" : ""
                  } ${!c.my_interest && roleId === o.role_id ? "bg-primary/5 ring-1 ring-primary/20" : ""}`}
                >
                  <div className="flex items-start gap-2 min-w-0">
                    {!c.my_interest && (
                      <input
                        type="radio" name={`role-${c.cohort_call_id}`} className="mt-1 shrink-0"
                        checked={roleId === o.role_id} disabled={full}
                        onChange={() => setRoleId(o.role_id)}
                      />
                    )}
                    <div className="min-w-0">
                      <span className="text-foreground">
                        {o.role_name}
                        <span className="text-xs text-muted-foreground">
                          {" "}&middot; {o.remaining > 0 ? `${o.remaining} of ${o.slots} left` : "full — waitlist"}
                        </span>
                      </span>
                      {o.notes && <p className="text-xs text-muted-foreground italic">{o.notes}</p>}
                    </div>
                  </div>
                  {o.amount_aed != null && (
                    <span className="text-sm font-semibold tabular-nums shrink-0">
                      AED {o.amount_aed.toLocaleString()}<span className="text-xs font-normal text-muted-foreground">/session</span>
                    </span>
                  )}
                </label>
              )
            })}
          </div>
        )}

        <div className="mb-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Program Sessions &mdash; Uncheck a session if you can't attend it
          </p>
          <div className="flex flex-wrap gap-2">
            {c.sessions.map((s) => {
              const on = c.my_interest ? s.selected : picked.has(s.session_id)
              const isFullForRole =
                !c.my_interest &&
                !!roleId &&
                !!s.open_role_ids &&
                s.open_role_ids.length > 0 &&
                !s.open_role_ids.includes(roleId)

              return (
                <button
                  key={s.session_id}
                  type="button"
                  disabled={c.my_interest || isFullForRole}
                  onClick={() => toggleDay(s.session_id)}
                  title={isFullForRole ? "This session is already fully staffed for this role" : (s.title ?? undefined)}
                  className={`px-3.5 py-2 rounded-xl text-xs sm:text-sm font-medium border transition-colors flex items-center gap-1.5 ${
                    isFullForRole
                      ? "bg-muted/40 text-muted-foreground/60 border-border/40 cursor-not-allowed opacity-75"
                      : on
                      ? "bg-primary/10 text-primary border-primary/30 font-semibold cursor-pointer"
                      : "bg-transparent text-muted-foreground border-border hover:bg-muted cursor-pointer"
                  }`}
                >
                  {isFullForRole ? "🔒" : on ? "☑" : "☐"} {formatDay(s.meeting_date)}
                  {s.starts_at ? ` · ${s.starts_at.slice(0, 5)}` : ""}
                  {isFullForRole && <span className="text-[10px] text-amber-600 dark:text-amber-400 font-semibold">(Full)</span>}
                </button>
              )
            })}
          </div>
          {!c.my_interest && picked.size === 0 && (
            <p className="text-xs text-muted-foreground mt-1.5">Pick at least one day.</p>
          )}
        </div>

        {c.my_interest ? (
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
              You've registered for {c.sessions.filter((s) => s.selected).length} of {c.session_count} days
              {c.my_note ? `: "${c.my_note}"` : ""}
            </span>
            <Button size="sm" variant="outline" disabled={pending} onClick={() => withdraw.mutate()}>
              Withdraw
            </Button>
            {error && <p className="text-xs text-red-600 dark:text-red-400 w-full">{error}</p>}
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {/* Operations process doc §2 — ops needs these before the workshop,
                not on the morning somebody turns out to need a taxi. */}
            <div className="rounded-xl border border-border bg-background/50 p-3 flex flex-col gap-2">
              <p className="text-xs font-semibold text-foreground">Anything we should know?</p>
              <div className="flex flex-col gap-1.5">
                {([
                  ["I need transport", needsTransport, setNeedsTransport],
                  ["I'm travelling from another city", travelling, setTravelling],
                ] as const).map(([label, value, set]) => (
                  <label key={label} className="flex items-center gap-2 text-xs cursor-pointer select-none">
                    <input
                      type="checkbox" checked={value}
                      onChange={(e) => set(e.target.checked)}
                      className="rounded text-primary focus:ring-primary border-border bg-background"
                    />
                    {label}
                  </label>
                ))}
              </div>
              <textarea
                className="input min-h-[3rem] resize-y text-xs"
                placeholder="Clarify any constraints or support needed…"
                value={concerns}
                onChange={(e) => setConcerns(e.target.value)}
              />
            </div>

            {responsibilities.data?.text && (
              <details
                open={respOpen}
                onToggle={(e) => setRespOpen(e.currentTarget.open)}
                className={`rounded-xl border transition-colors group ${
                  error && !agreed ? "border-amber-500/50 bg-amber-500/5" : "border-border bg-background/50"
                }`}
              >
                <summary className="px-3 py-2.5 flex items-center justify-between text-xs font-semibold text-foreground cursor-pointer select-none list-none">
                  <span>Responsibilities{responsibilities.data.role_name ? ` — ${responsibilities.data.role_name}` : ""}</span>
                  <span className="text-[10px] text-primary group-open:hidden">View responsibilities ▾</span>
                  <span className="text-[10px] text-muted-foreground hidden group-open:inline">Hide ▴</span>
                </summary>
                <div className="px-3 pb-3 pt-1 border-t border-border flex flex-col gap-2">
                  <p className="text-xs text-muted-foreground whitespace-pre-line max-h-40 overflow-y-auto">
                    {responsibilities.data.text}
                  </p>
                  <label className="flex items-center gap-2 text-xs text-foreground font-medium cursor-pointer select-none pt-1">
                    <input
                      type="checkbox" checked={agreed}
                      onChange={(e) => { setAgreed(e.target.checked); if (e.target.checked) setError("") }}
                      className="rounded text-primary focus:ring-primary border-border bg-background"
                    />
                    I agree to the Responsibilities
                  </label>
                </div>
              </details>
            )}

            <div className="flex flex-col sm:flex-row gap-3 items-center">
              <textarea
                className="input flex-1 min-h-[4.5rem] resize-y text-xs sm:text-sm"
                placeholder="Optional cover letter (why you'd like this one)…"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <Button
                className={`h-11 px-6 rounded-xl text-sm font-semibold shrink-0 transition-all ${
                  isReady
                    ? "bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm"
                    : "bg-muted/80 text-muted-foreground border border-border/80 hover:bg-muted hover:text-foreground"
                }`}
                disabled={pending}
                onClick={handleApply}
              >
                {register.isPending ? "Registering…" : "Register interest"}
              </Button>
            </div>
            {c.openings.length > 0 && !roleId && (
              <p className="text-xs text-muted-foreground">Pick a role above before applying.</p>
            )}
            {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
