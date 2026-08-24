/** Ops-side cohort staffing (2026-08-24): the applicant table and who ended
 *  up staffed.
 *
 *  The point of this panel is that it is **one row per instructor**, not one
 *  per session. Previously ops picked people session by session, so staffing a
 *  five-day camp meant working the same roster five times and there was no one
 *  place showing who had asked for the whole run. Here an applicant states one
 *  role and the days they can do, and "Assign" writes both their cohort
 *  assignment and exactly the session rows they ticked.
 */
import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Bus, Check, LifeBuoy, MapPin, Plane, Trash2 } from "lucide-react"
import {
  listCohortApplicantsApi,
  listCohortAssignmentsApi,
  listCohortCallsApi,
  removeCohortAssignmentApi,
  selectForCohortApi,
} from "@/api/sessions/staffing"
import type { Cohort } from "@/types/sessions"
import { Button } from "@/components/ui/button"
import { ConfirmDialog, Spinner } from "@/pages/admin/components/common"
import { getErrorMessage } from "@/lib/utils"

function Badge({ icon: Icon, label, tone = "muted" }: {
  icon: typeof Bus; label: string; tone?: "muted" | "good"
}) {
  const tones = {
    muted: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-400 dark:border-amber-900/50",
    good: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-900/50",
  }
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded border ${tones[tone]}`}>
      <Icon size={10} /> {label}
    </span>
  )
}

export default function CohortStaffingPanel({ cohort }: { cohort: Cohort }) {
  const qc = useQueryClient()
  const [callId, setCallId] = useState<string | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [error, setError] = useState("")
  const [removing, setRemoving] = useState<{ userId: string; name: string } | null>(null)

  const calls = useQuery({
    queryKey: ["cohort-calls", cohort.id],
    queryFn: () => listCohortCallsApi(cohort.id),
  })
  const activeCallId = callId ?? calls.data?.find((c) => c.status === "open")?.id ?? calls.data?.[0]?.id ?? null

  const applicants = useQuery({
    queryKey: ["cohort-applicants", cohort.id, activeCallId],
    queryFn: () => listCohortApplicantsApi(cohort.id, activeCallId!),
    enabled: !!activeCallId,
  })
  const assignments = useQuery({
    queryKey: ["cohort-assignments", cohort.id],
    queryFn: () => listCohortAssignmentsApi(cohort.id),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["cohort-applicants", cohort.id] })
    qc.invalidateQueries({ queryKey: ["cohort-assignments", cohort.id] })
    qc.invalidateQueries({ queryKey: ["cohort-calls", cohort.id] })
    qc.invalidateQueries({ queryKey: ["cohort-sessions", cohort.id] })
  }

  const assign = useMutation({
    mutationFn: () =>
      selectForCohortApi(cohort.id, {
        user_ids: selected,
        cohort_call_id: activeCallId,
      }),
    onSuccess: () => { setError(""); setSelected([]); invalidate() },
    // A 409 here is the one-role-per-cohort rule, and its message names who
    // clashes with what — surface it verbatim rather than a generic failure.
    onError: (e) => setError(getErrorMessage(e, "Could not assign those instructors")),
  })

  const remove = useMutation({
    mutationFn: (userId: string) => removeCohortAssignmentApi(cohort.id, userId),
    onSuccess: () => { setRemoving(null); invalidate() },
    onError: (e) => setError(getErrorMessage(e, "Could not remove that assignment")),
  })

  const rows = applicants.data ?? []
  const pickable = rows.filter((r) => !r.already_assigned)
  const staffed = (assignments.data ?? []).filter((a) => a.status === "active")

  const toggle = (id: string) =>
    setSelected((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])

  return (
    <div className="py-4 space-y-6">
      <div>
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <div>
            <h3 className="font-semibold text-sm">Applicants</h3>
            <p className="text-xs text-muted-foreground">
              One row per instructor — the role they asked for and the days they can do.
            </p>
          </div>
          {(calls.data ?? []).length > 1 && (
            <select
              className="input h-8 text-xs w-auto"
              value={activeCallId ?? ""}
              onChange={(e) => { setCallId(e.target.value); setSelected([]) }}
            >
              {calls.data!.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label || "Call"} · {c.status} · {c.sessions.length} sessions
                </option>
              ))}
            </select>
          )}
        </div>

        {calls.isLoading || applicants.isLoading ? (
          <Spinner />
        ) : !activeCallId ? (
          <p className="text-xs text-muted-foreground">
            No cohort call yet — open one below and applicants will appear here.
          </p>
        ) : rows.length === 0 ? (
          <p className="text-xs text-muted-foreground">Nobody has registered interest yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground border-b border-border">
                  <th className="py-2 pr-2 w-8"></th>
                  <th className="py-2 pr-3">Instructor</th>
                  <th className="py-2 pr-3">Role</th>
                  <th className="py-2 pr-3">Days</th>
                  <th className="py-2 pr-3">Notes</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.user_id} className="border-b border-border/60 align-top">
                    <td className="py-2 pr-2">
                      <input
                        type="checkbox"
                        disabled={r.already_assigned}
                        checked={selected.includes(r.user_id)}
                        onChange={() => toggle(r.user_id)}
                        className="rounded text-primary focus:ring-primary border-border bg-background"
                      />
                    </td>
                    <td className="py-2 pr-3">
                      <p className="font-medium">{r.full_name}</p>
                      <p className="text-[11px] text-muted-foreground">{r.email}</p>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {r.available_in_city && <Badge icon={MapPin} label="works in this city" tone="good" />}
                        {r.needs_transport && <Badge icon={Bus} label="needs transport" />}
                        {r.travelling_from_other_city && <Badge icon={Plane} label="another city" />}
                        {r.needs_ops_support && <Badge icon={LifeBuoy} label="needs ops support" />}
                        {r.already_assigned && <Badge icon={Check} label="assigned" tone="good" />}
                      </div>
                    </td>
                    <td className="py-2 pr-3 whitespace-nowrap">{r.role_name ?? "—"}</td>
                    <td className="py-2 pr-3 whitespace-nowrap tabular-nums">{r.session_count}</td>
                    <td className="py-2 pr-3 text-xs text-muted-foreground max-w-xs">
                      {r.note && <p className="whitespace-pre-line">{r.note}</p>}
                      {r.concerns && <p className="whitespace-pre-line italic mt-1">{r.concerns}</p>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="flex flex-wrap items-center gap-3 mt-3">
              <Button
                size="sm"
                disabled={selected.length === 0 || assign.isPending}
                onClick={() => { setError(""); assign.mutate() }}
              >
                {assign.isPending ? "Assigning…" : `Assign selected (${selected.length})`}
              </Button>
              {pickable.length > 0 && (
                <button
                  type="button"
                  className="text-xs text-primary hover:underline"
                  onClick={() => setSelected(
                    selected.length === pickable.length ? [] : pickable.map((r) => r.user_id),
                  )}
                >
                  {selected.length === pickable.length ? "Clear" : "Select all"}
                </button>
              )}
              <p className="text-xs text-muted-foreground">
                Each person gets exactly the days they ticked, in the role they applied for.
              </p>
            </div>
          </div>
        )}
        {error && <p className="text-xs text-red-600 dark:text-red-400 mt-2">{error}</p>}
      </div>

      <div>
        <h3 className="font-semibold text-sm mb-1">Staffed</h3>
        <p className="text-xs text-muted-foreground mb-3">
          The agreed rate is snapshotted here — editing a cohort rate later won't reprice anyone
          already assigned.
        </p>
        {assignments.isLoading ? (
          <Spinner />
        ) : staffed.length === 0 ? (
          <p className="text-xs text-muted-foreground">Nobody assigned yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground border-b border-border">
                  <th className="py-2 pr-3">Instructor</th>
                  <th className="py-2 pr-3">Role</th>
                  <th className="py-2 pr-3">Sessions</th>
                  <th className="py-2 pr-3">Rate</th>
                  <th className="py-2 pr-3"></th>
                </tr>
              </thead>
              <tbody>
                {staffed.map((a) => (
                  <tr key={a.id} className="border-b border-border/60">
                    <td className="py-2 pr-3">
                      <p className="font-medium">{a.full_name}</p>
                      <p className="text-[11px] text-muted-foreground">{a.email}</p>
                    </td>
                    <td className="py-2 pr-3 whitespace-nowrap">{a.role_name}</td>
                    <td className="py-2 pr-3 tabular-nums">{a.session_count}</td>
                    <td className="py-2 pr-3 tabular-nums whitespace-nowrap">
                      {a.rate_basis === "flat"
                        ? a.flat_amount_aed != null ? `AED ${a.flat_amount_aed.toLocaleString()} flat` : "flat —"
                        : a.rate_aed != null ? `AED ${a.rate_aed.toLocaleString()}/session` : "—"}
                    </td>
                    <td className="py-2 pr-3 text-right">
                      <button
                        type="button"
                        className="text-muted-foreground hover:text-red-600 transition-colors"
                        title="Remove from this cohort"
                        onClick={() => setRemoving({ userId: a.user_id, name: a.full_name })}
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {removing && (
        <ConfirmDialog
          title={`Remove ${removing.name}?`}
          description="They'll be taken off every session in this cohort. The assignment is kept as withdrawn, so the record that they were staffed survives."
          confirmLabel="Remove"
          destructive
          pending={remove.isPending}
          onConfirm={() => remove.mutate(removing.userId)}
          onCancel={() => setRemoving(null)}
        />
      )}
    </div>
  )
}
