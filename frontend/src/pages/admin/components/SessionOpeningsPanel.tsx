import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Trash2 } from "lucide-react"
import {
  getDeliveryRolesApi,
  getOpeningsApi,
  setOpeningsApi,
} from "@/api/sessions/openings"
import { useToast } from "@/components/ui/toast"
import { InheritedBadge } from "@/pages/admin/components/InheritedFrom"
import { cn } from "@/lib/utils"

const OUTFIT = "'Outfit', ui-sans-serif, system-ui, sans-serif"

/** Compact (default, unchanged) vs. the Cohort Wizard's bigger scale */
function sizes(large: boolean) {
  return {
    wrap: large ? "rounded-2xl border border-border bg-card p-6 flex flex-col gap-5" : "rounded-2xl border border-border bg-card p-4 flex flex-col gap-3",
    title: large ? "text-lg font-semibold text-foreground" : "text-sm font-semibold text-foreground",
    desc: large ? "text-[15px] text-muted-foreground mt-1" : "text-xs text-muted-foreground mt-0.5",
    roleName: large ? "text-base text-foreground min-w-[10rem] h-12 flex items-center" : "text-sm text-foreground min-w-[9rem] h-9 flex items-center",
    fieldLabel: large ? "text-xs text-muted-foreground leading-none" : "text-[10px] text-muted-foreground leading-none",
    slotsInput: large ? "!w-20 h-12 px-3 border border-border bg-background text-foreground rounded-xl text-base text-right tabular-nums" : "!w-16 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right tabular-nums",
    notesInput: large ? "w-full h-12 px-3 border border-border bg-background text-foreground rounded-xl text-base" : "w-full h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm",
    liveInfo: large ? "text-sm text-muted-foreground tabular-nums h-12 flex items-center gap-3" : "text-xs text-muted-foreground tabular-nums h-9 flex items-center gap-2",
    emptyNote: large ? "text-base text-muted-foreground" : "text-sm text-muted-foreground",
    select: large ? "h-12 px-3 border border-border bg-background text-foreground rounded-xl text-base" : "h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm",
    primaryBtn: large ? "h-12 px-6 bg-primary text-primary-foreground rounded-xl font-semibold hover:opacity-90 disabled:opacity-40 transition-opacity" : "h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:opacity-90 disabled:opacity-40",
    cancelBtn: large ? "h-12 px-4 text-base text-muted-foreground hover:text-foreground" : "h-9 px-3 text-sm text-muted-foreground hover:text-foreground",
  }
}

export function SessionOpeningsPanel({ sessionId, large = false }: { sessionId: string; large?: boolean }) {
  const t = sizes(large)
  const qc = useQueryClient()
  const toast = useToast()
  const [error, setError] = useState("")
  const [draft, setDraft] = useState<
    { role_id: string; slots: number; notes: string }[] | null
  >(null)

  const { data: roles = [] } = useQuery({
    queryKey: ["delivery-roles"], queryFn: () => getDeliveryRolesApi(),
  })
  const { data: openings = [] } = useQuery({
    queryKey: ["session-openings", sessionId], queryFn: () => getOpeningsApi(sessionId),
  })

  useEffect(() => {
    if (draft === null && openings.length) {
      setDraft(openings.map((o) => ({
        role_id: o.role_id,
        slots: o.slots,
        notes: o.notes ?? "",
      })))
    }
  }, [openings, draft])

  const rows = draft ?? []
  const unusedRoles = roles.filter((r) => !rows.some((d) => d.role_id === r.id))

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["session-openings", sessionId] })
    qc.invalidateQueries({ queryKey: ["admin-cohorts"] })
  }
  const onError = (e: any) => setError(e?.response?.data?.detail ?? "Could not save that")

  const save = useMutation({
    mutationFn: () => setOpeningsApi({
      sessionId,
      openings: rows.map((d) => ({
        role_id: d.role_id,
        slots: d.slots,
        amount_aed: null,
        notes: d.notes || null,
      })),
    }),
    onSuccess: (data) => {
      toast.success("Openings saved")
      setError("")
      qc.setQueryData(["session-openings", sessionId], data)
      setDraft(null)
      invalidate()
    },
    onError,
  })

  const inherited = openings.some((o) => o.inherited)

  return (
    <div className={t.wrap}>
      <div>
        <div className="flex items-center gap-2 flex-wrap">
          <p className={t.title} style={large ? { fontFamily: OUTFIT } : undefined}>What this session is offering</p>
          <InheritedBadge overridden={!inherited && openings.length > 0} />
        </div>
        <p className={t.desc}>
          Which roles this session needs and how many slots — pay follows the cohort's Roles tab, not set
          here. Slots left is worked out from who&apos;s assigned.
          {inherited && " Saving customizes just this session — the cohort default stays as-is for the others."}
        </p>
      </div>

      <div className={cn("flex flex-col", large ? "gap-4" : "gap-2")}>
        {rows.map((d, i) => {
          const live = openings.find((o) => o.role_id === d.role_id)
          const role = roles.find((r) => r.id === d.role_id)
          return (
            <div key={d.role_id} className="flex items-end gap-3 flex-wrap">
              <span className={t.roleName}>{role?.name ?? "Role"}</span>
              <label className="flex flex-col gap-1">
                <span className={t.fieldLabel}>Slots</span>
                <input
                  type="number" min={1} value={d.slots}
                  onChange={(e) => setDraft(rows.map((x, j) =>
                    j === i ? { ...x, slots: Math.max(1, Number(e.target.value) || 1) } : x))}
                  className={t.slotsInput}
                />
              </label>
              <label className="flex-1 min-w-[8rem] flex flex-col gap-1">
                <span className={t.fieldLabel}>Notes</span>
                <input
                  placeholder="Optional" value={d.notes}
                  onChange={(e) => setDraft(rows.map((x, j) =>
                    j === i ? { ...x, notes: e.target.value } : x))}
                  className={t.notesInput}
                />
              </label>
              {live && (
                <span className={t.liveInfo}>
                  {live.amount_aed != null && <span>AED {Number(live.amount_aed).toLocaleString()}</span>}
                  <span>{live.filled}/{live.slots} filled</span>
                </span>
              )}
              <button
                onClick={() => setDraft(rows.filter((_, j) => j !== i))}
                className={cn("text-muted-foreground hover:text-red-600 transition-colors", large ? "p-2 h-12" : "p-1 h-9")}
                aria-label="Remove opening"
              ><Trash2 size={large ? 18 : 14} /></button>
            </div>
          )
        })}
        {rows.length === 0 && (
          <p className={t.emptyNote}>
            No openings yet — this session behaves as it always did until you add one.
          </p>
        )}
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        {unusedRoles.length > 0 && (
          <select
            value="" onChange={(e) => e.target.value && setDraft([
              ...rows, { role_id: e.target.value, slots: 1, notes: "" },
            ])}
            className={t.select}
          >
            <option value="">+ Add a role…</option>
            {unusedRoles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        )}
        <button
          onClick={() => { setError(""); save.mutate() }}
          disabled={draft === null || save.isPending}
          className={t.primaryBtn}
        >
          {save.isPending ? "Saving…" : "Save openings"}
        </button>
        {draft !== null && (
          <button
            onClick={() => { setDraft(null); setError("") }}
            className={t.cancelBtn}
          >
            Cancel
          </button>
        )}
      </div>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}
