import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowDown, ArrowUp, Plus } from "lucide-react"
import {
  createDeliveryRoleApi,
  getDeliveryRolesApi,
  getResponsibilitiesApi,
  setResponsibilitiesApi,
  updateDeliveryRoleApi,
} from "@/api/sessions/openings"
import { Spinner } from "@/pages/admin/components/common"
import { getActiveRankingWeightsApi, updateRankingWeightsApi } from "@/api/instructor_assessment"
import { RANKING_FACTORS, type RankingFactorKey, type RankingWeightProfile } from "@/types/instructor_assessment"

/**
 * Delivery roles and the responsibilities text (I5-3, I5-5).
 *
 * Roles are data rather than an enum, which is what let staffing and payment
 * letters share one vocabulary. Two rules worth knowing while editing here:
 *
 * - **Order is seniority.** "The lead" is whatever sits at the top, so moving
 *   a role changes who kits are issued to and who is assigned by default.
 * - **Renaming is safe.** Payment letters snapshot the role's name at the time
 *   they were written, so a signed letter keeps saying what it said.
 *
 * There is no delete: a role that has ever been assigned is part of the
 * record. Deactivating stops new assignments and leaves history readable.
 */
export default function DeliverySettings() {
  const qc = useQueryClient()
  const [newRole, setNewRole] = useState("")
  const [text, setText] = useState<string | null>(null)
  const [error, setError] = useState("")

  const { data: roles = [], isLoading } = useQuery({
    queryKey: ["delivery-roles-all"], queryFn: () => getDeliveryRolesApi(true),
  })
  const { data: responsibilities } = useQuery({
    // getResponsibilitiesApi now takes an optional roleId — passed bare like
    // this, react-query's own queryFn context ({queryKey, signal, ...})
    // becomes that argument, which axios then serializes as bracket-notation
    // junk in the query string. Always wrap it.
    queryKey: ["responsibilities"], queryFn: () => getResponsibilitiesApi(),
  })

  useEffect(() => {
    if (text === null && responsibilities) setText(responsibilities.text)
  }, [responsibilities, text])

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["delivery-roles-all"] })
    qc.invalidateQueries({ queryKey: ["delivery-roles"] })
  }
  const onError = (e: any) => setError(e?.response?.data?.detail ?? "Could not save that")

  const create = useMutation({
    mutationFn: () => createDeliveryRoleApi({ name: newRole }),
    onSuccess: () => { setError(""); setNewRole(""); invalidate() },
    onError,
  })
  const update = useMutation({
    mutationFn: updateDeliveryRoleApi, onSuccess: () => { setError(""); invalidate() }, onError,
  })
  const saveText = useMutation({
    mutationFn: () => setResponsibilitiesApi(text ?? ""),
    onSuccess: () => {
      setError("")
      qc.invalidateQueries({ queryKey: ["responsibilities"] })
    },
    onError,
  })

  /** Swap sort_order with the neighbour — seniority is the column, so nothing
   *  else has to know about ordering. */
  const swap = (i: number, j: number) => {
    const a = roles[i], b = roles[j]
    if (!a || !b) return
    update.mutate({ id: a.id, sort_order: b.sort_order })
    update.mutate({ id: b.id, sort_order: a.sort_order })
  }

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold text-foreground tracking-tight">Delivery settings</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          The roles people are assigned in, and what they agree to when accepting a session
        </p>
      </div>

      <section className="rounded-2xl border border-border bg-card p-4 flex flex-col gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">Roles</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Order is seniority — the top one is treated as the lead, including for handing
            out kits. Renaming is safe: signed payment letters keep the wording they were
            written with.
          </p>
        </div>

        <div className="flex flex-col gap-2">
          {roles.map((r, i) => (
            <div key={r.id} className="flex flex-col gap-1.5 p-2.5 border border-border rounded-xl">
              <div className="flex items-center gap-2">
                <input
                  defaultValue={r.name}
                  onBlur={(e) => e.target.value !== r.name &&
                    update.mutate({ id: r.id, name: e.target.value })}
                  className="flex-1 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm"
                />
                <button
                  disabled={i === 0} onClick={() => swap(i, i - 1)}
                  className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"
                  aria-label="Move up"
                ><ArrowUp size={14} /></button>
                <button
                  disabled={i === roles.length - 1} onClick={() => swap(i, i + 1)}
                  className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"
                  aria-label="Move down"
                ><ArrowDown size={14} /></button>
                <button
                  onClick={() => update.mutate({ id: r.id, is_active: !r.is_active })}
                  className={`h-8 px-3 text-xs font-medium rounded-lg border transition-colors ${
                    r.is_active
                      ? "border-border text-muted-foreground hover:bg-muted"
                      : "border-amber-400/40 bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400"
                  }`}
                >
                  {r.is_active ? "Active" : "Inactive"}
                </button>
              </div>
              <textarea
                defaultValue={r.description ?? ""}
                placeholder="What an instructor is agreeing to when they pick this role — shown on the invite."
                rows={2}
                onBlur={(e) => e.target.value !== (r.description ?? "") &&
                  update.mutate({ id: r.id, description: e.target.value || null })}
                className="w-full px-2 py-1.5 border border-border bg-background text-foreground rounded-lg text-xs resize-y"
              />
              {/* The global tier of the rate hierarchy (2026-08-24): a cohort
                  or a single session can still override it, but this is what
                  applies when neither does. Clearing the box sends an explicit
                  clear rather than an omitted field — "" and "untouched" are
                  otherwise indistinguishable to the API. */}
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="shrink-0">Default rate</span>
                <span className="shrink-0 text-[11px]">AED</span>
                <input
                  type="number" min={0} step="1"
                  defaultValue={r.default_rate_aed ?? ""}
                  placeholder="not set"
                  onBlur={(e) => {
                    const raw = e.target.value.trim()
                    const current = r.default_rate_aed ?? null
                    const next = raw === "" ? null : Number(raw)
                    if (next === current) return
                    update.mutate(
                      next === null
                        ? { id: r.id, clear_default_rate: true }
                        : { id: r.id, default_rate_aed: next },
                    )
                  }}
                  className="w-28 h-8 px-2 border border-border bg-background text-foreground rounded-lg text-xs tabular-nums"
                />
                <span className="text-[11px]">per session</span>
              </label>
            </div>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <input
            placeholder="e.g. Observer" value={newRole}
            onChange={(e) => setNewRole(e.target.value)}
            className="flex-1 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm"
          />
          <button
            onClick={() => { setError(""); create.mutate() }}
            disabled={!newRole || create.isPending}
            className="h-9 px-3 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:opacity-90 disabled:opacity-40"
          ><Plus size={14} className="inline mr-1" /> Add role</button>
        </div>
      </section>

      <section className="rounded-2xl border border-border bg-card p-4 flex flex-col gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">General responsibilities</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            One chunk of text, appended <strong>after</strong> whichever role's own
            responsibilities an instructor is agreeing to — things true regardless of role
            (arrive on time, wear the branded shirt, payment terms, anything else). Editing this
            makes a new version: anyone who already agreed stays recorded against the wording
            they actually read.
          </p>
        </div>
        <textarea
          value={text ?? ""} onChange={(e) => setText(e.target.value)} rows={8}
          placeholder="Arrive 30 minutes before the session starts…&#10;&#10;Standard payment is within 30 days of delivery."
          className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-y"
        />

        <button
          onClick={() => { setError(""); saveText.mutate() }}
          disabled={saveText.isPending}
          className="h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:opacity-90 disabled:opacity-40 w-fit"
        >
          {saveText.isPending ? "Saving…" : "Save"}
        </button>
      </section>

      <RankingWeightsSection />

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}

/** The configurable blend behind the instructor Priority Score (2026-09) —
 *  a small settings surface, not a dedicated feature. Weights don't need to
 *  sum to 100; the blend normalizes over whichever factors have data for a
 *  given instructor. Fetches first, then mounts the form seeded from the
 *  active profile — the form's own state is only ever initialized once, at
 *  mount, never synced in from a later-arriving query via an effect. */
function RankingWeightsSection() {
  const { data: profile, isLoading } = useQuery({
    queryKey: ["ranking-weights"], queryFn: getActiveRankingWeightsApi,
  })

  if (isLoading || !profile) return <Spinner />

  return <RankingWeightsForm profile={profile} />
}

function RankingWeightsForm({ profile }: { profile: RankingWeightProfile }) {
  const qc = useQueryClient()
  const [weights, setWeights] = useState<Partial<Record<RankingFactorKey, number>>>(profile.factor_weights)
  const [saved, setSaved] = useState(false)

  const save = useMutation({
    mutationFn: () => updateRankingWeightsApi({
      name: profile.name,
      factor_weights: (weights ?? {}) as Record<string, number>,
    }),
    onSuccess: () => {
      setSaved(true)
      qc.invalidateQueries({ queryKey: ["ranking-weights"] })
    },
  })

  const total = Object.values(weights).reduce((sum, v) => sum + (v ?? 0), 0)

  return (
    <section className="rounded-2xl border border-border bg-card p-4 flex flex-col gap-3">
      <div>
        <p className="text-sm font-semibold text-foreground">Instructor Priority Score weights</p>
        <p className="text-xs text-muted-foreground mt-0.5">
          How much each factor counts toward the Priority Score shown on the instructor selection screen.
          A factor with no data yet for a given instructor (e.g. no rating history) is left out of their
          blend rather than counted as zero — weights don't need to add up to exactly 100.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        {RANKING_FACTORS.map((f) => (
          <label key={f.key} className="flex items-center justify-between gap-3 text-sm">
            <span>{f.label}</span>
            <span className="flex items-center gap-1.5">
              <input
                type="number" min={0} max={100} step="1"
                value={weights[f.key] ?? 0}
                onChange={(e) => { setSaved(false); setWeights((prev) => ({ ...prev, [f.key]: Number(e.target.value) })) }}
                className="w-20 h-8 px-2 border border-border bg-background text-foreground rounded-lg text-sm tabular-nums text-right"
              />
              <span className="text-xs text-muted-foreground">%</span>
            </span>
          </label>
        ))}
      </div>

      <p className="text-xs text-muted-foreground">Total: {total}%</p>

      <button
        onClick={() => save.mutate()}
        disabled={save.isPending}
        className="h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:opacity-90 disabled:opacity-40 w-fit"
      >
        {save.isPending ? "Saving…" : saved ? "Saved" : "Save weights"}
      </button>
    </section>
  )
}
