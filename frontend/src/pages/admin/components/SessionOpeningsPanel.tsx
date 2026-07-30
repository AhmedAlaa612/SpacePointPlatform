import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, Plus, Trash2, X } from "lucide-react"
import {
  createAddonApi,
  decideAddonApi,
  getAddonsApi,
  getDeliveryRolesApi,
  getOpeningsApi,
  setOpeningsApi,
} from "@/api/sessions/openings"

/**
 * The offer, per role (I5-4) and its add-ons (§G-addons) — on the ops session
 * view.
 *
 * An offer is not one number on a session: this session needs 1 Lead
 * Facilitator at 2000 and 2 Assistants at 400. Slots remaining falls out of
 * assignments, so nothing here is stored twice.
 *
 * Add-ons sit underneath because they are the same conversation. Anything ops
 * adds here is `agreed` on arrival; anything an instructor raised shows as
 * `proposed` with approve/decline, because the person asking is never the
 * person approving.
 */
export function SessionOpeningsPanel({ sessionId }: { sessionId: string }) {
  const qc = useQueryClient()
  const [error, setError] = useState("")
  const [draft, setDraft] = useState<
    { role_id: string; slots: number; amount_aed: string; notes: string }[] | null
  >(null)

  const { data: roles = [] } = useQuery({
    queryKey: ["delivery-roles"], queryFn: () => getDeliveryRolesApi(),
  })
  const { data: openings = [] } = useQuery({
    queryKey: ["session-openings", sessionId], queryFn: () => getOpeningsApi(sessionId),
  })
  const { data: addons = [] } = useQuery({
    queryKey: ["session-addons", sessionId], queryFn: () => getAddonsApi(sessionId),
  })

  // Seed the editable draft from the server once it's loaded.
  useEffect(() => {
    if (draft === null && openings.length) {
      setDraft(openings.map((o) => ({
        role_id: o.role_id,
        slots: o.slots,
        amount_aed: o.amount_aed != null ? String(o.amount_aed) : "",
        notes: o.notes ?? "",
      })))
    }
  }, [openings, draft])

  const rows = draft ?? []
  const unusedRoles = roles.filter((r) => !rows.some((d) => d.role_id === r.id))

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["session-openings", sessionId] })
    qc.invalidateQueries({ queryKey: ["session-addons", sessionId] })
    qc.invalidateQueries({ queryKey: ["admin-cohorts"] })
  }
  const onError = (e: any) => setError(e?.response?.data?.detail ?? "Could not save that")

  const save = useMutation({
    mutationFn: () => setOpeningsApi({
      sessionId,
      openings: rows.map((d) => ({
        role_id: d.role_id,
        slots: d.slots,
        amount_aed: d.amount_aed === "" ? null : Number(d.amount_aed),
        notes: d.notes || null,
      })),
    }),
    onSuccess: () => { setError(""); setDraft(null); invalidate() },
    onError,
  })

  const [addonDesc, setAddonDesc] = useState("")
  const [addonAmount, setAddonAmount] = useState("")
  const addAddon = useMutation({
    mutationFn: () => createAddonApi({
      sessionId, description: addonDesc, amount_aed: Number(addonAmount) || 0, source: "offer",
    }),
    onSuccess: () => { setAddonDesc(""); setAddonAmount(""); invalidate() },
    onError,
  })
  const decide = useMutation({ mutationFn: decideAddonApi, onSuccess: invalidate, onError })

  return (
    <div className="rounded-2xl border border-border bg-card p-4 flex flex-col gap-3">
      <div>
        <p className="text-sm font-semibold text-foreground">What this session is offering</p>
        <p className="text-xs text-muted-foreground mt-0.5">
          Per role — slots and the amount. Slots left is worked out from who&apos;s assigned.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        {rows.map((d, i) => {
          const live = openings.find((o) => o.role_id === d.role_id)
          const role = roles.find((r) => r.id === d.role_id)
          return (
            <div key={d.role_id} className="flex items-center gap-2 flex-wrap">
              <span className="text-sm text-foreground min-w-[9rem]">{role?.name ?? "Role"}</span>
              <input
                type="number" min={1} value={d.slots}
                onChange={(e) => setDraft(rows.map((x, j) =>
                  j === i ? { ...x, slots: Math.max(1, Number(e.target.value) || 1) } : x))}
                className="w-16 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right tabular-nums"
              />
              <span className="text-xs text-muted-foreground">slots</span>
              <input
                type="number" min={0} placeholder="AED" value={d.amount_aed}
                onChange={(e) => setDraft(rows.map((x, j) =>
                  j === i ? { ...x, amount_aed: e.target.value } : x))}
                className="w-24 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right tabular-nums"
              />
              <input
                placeholder="Notes" value={d.notes}
                onChange={(e) => setDraft(rows.map((x, j) =>
                  j === i ? { ...x, notes: e.target.value } : x))}
                className="flex-1 min-w-[8rem] h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm"
              />
              {live && (
                <span className="text-xs text-muted-foreground tabular-nums">
                  {live.filled}/{live.slots} filled
                </span>
              )}
              <button
                onClick={() => setDraft(rows.filter((_, j) => j !== i))}
                className="p-1 text-muted-foreground hover:text-red-600"
                aria-label="Remove opening"
              ><Trash2 size={14} /></button>
            </div>
          )
        })}
        {rows.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No openings yet — this session behaves as it always did until you add one.
          </p>
        )}
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {unusedRoles.length > 0 && (
          <select
            value="" onChange={(e) => e.target.value && setDraft([
              ...rows, { role_id: e.target.value, slots: 1, amount_aed: "", notes: "" },
            ])}
            className="h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm"
          >
            <option value="">+ Add a role…</option>
            {unusedRoles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        )}
        <button
          onClick={() => { setError(""); save.mutate() }}
          disabled={draft === null || save.isPending}
          className="h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:opacity-90 disabled:opacity-40"
        >
          {save.isPending ? "Saving…" : "Save openings"}
        </button>
        {draft !== null && (
          <button
            onClick={() => { setDraft(null); setError("") }}
            className="h-9 px-3 text-sm text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
        )}
      </div>

      <div className="border-t border-border pt-3 flex flex-col gap-2">
        <p className="text-xs font-semibold text-muted-foreground">Add-ons</p>
        {addons.map((a) => (
          <div key={a.id} className="flex items-center justify-between gap-3 text-sm">
            <span className="text-foreground truncate">
              {a.description}
              <span className="text-xs text-muted-foreground">
                {" "}· AED {Number(a.amount_aed).toLocaleString()}
                {a.user_name && ` · ${a.user_name}`}
                {a.role_name && !a.user_name && ` · ${a.role_name}`}
              </span>
            </span>
            <span className="flex items-center gap-1.5 shrink-0">
              {a.status === "proposed" ? (
                <>
                  <span className="text-xs text-amber-700 dark:text-amber-400">requested</span>
                  <button
                    onClick={() => decide.mutate({ addonId: a.id, status: "agreed" })}
                    className="p-1 text-emerald-600 hover:opacity-80" aria-label="Agree"
                  ><Check size={15} /></button>
                  <button
                    onClick={() => decide.mutate({ addonId: a.id, status: "declined" })}
                    className="p-1 text-muted-foreground hover:text-red-600" aria-label="Decline"
                  ><X size={15} /></button>
                </>
              ) : (
                <span className={a.status === "agreed"
                  ? "text-xs text-emerald-600 dark:text-emerald-400"
                  : "text-xs text-muted-foreground line-through"}>
                  {a.status}
                </span>
              )}
            </span>
          </div>
        ))}
        {addons.length === 0 && (
          <p className="text-sm text-muted-foreground">Nothing extra on this session.</p>
        )}

        <div className="flex items-center gap-2">
          <input
            placeholder="Poster printing" value={addonDesc}
            onChange={(e) => setAddonDesc(e.target.value)}
            className="flex-1 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm"
          />
          <input
            type="number" min={0} placeholder="AED" value={addonAmount}
            onChange={(e) => setAddonAmount(e.target.value)}
            className="w-24 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right tabular-nums"
          />
          <button
            onClick={() => addAddon.mutate()}
            disabled={!addonDesc || addAddon.isPending}
            className="h-9 px-3 border border-border text-foreground text-sm rounded-lg hover:bg-muted disabled:opacity-40"
          ><Plus size={14} /></button>
        </div>
      </div>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}
