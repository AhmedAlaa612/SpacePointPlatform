import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Trash2 } from "lucide-react"
import type { Cohort } from "@/types/sessions"
import { getDeliveryRolesApi, getCohortOpeningsApi, setCohortOpeningsApi } from "@/api/sessions/openings"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

export function CohortOpeningsPanel({ cohort }: { cohort: Cohort }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [error, setError] = useState("")
  const [draft, setDraft] = useState<
    { role_id: string; slots: number; amount_aed: string; notes: string }[] | null
  >(null)

  const { data: roles = [] } = useQuery({
    queryKey: ["delivery-roles"],
    queryFn: () => getDeliveryRolesApi(),
  })

  const { data: defaults = [], isLoading } = useQuery({
    queryKey: ["cohort-openings-defaults", cohort.id],
    queryFn: () => getCohortOpeningsApi(cohort.id),
  })

  useEffect(() => {
    if (defaults) {
      setDraft(defaults.map((o) => ({
        role_id: o.role_id,
        slots: o.slots,
        amount_aed: o.amount_aed != null ? String(o.amount_aed) : "",
        notes: o.notes ?? "",
      })))
    }
  }, [defaults])

  const rows = draft ?? []
  const unusedRoles = roles.filter((r) => !rows.some((d) => d.role_id === r.id))

  const save = useMutation({
    mutationFn: () => setCohortOpeningsApi({
      cohortId: cohort.id,
      openings: rows.map((d) => ({
        role_id: d.role_id,
        slots: d.slots,
        amount_aed: d.amount_aed === "" ? null : Number(d.amount_aed),
        notes: d.notes || null,
      })),
    }),
    onSuccess: () => {
      toast.success("Default openings saved")
      setError("")
      qc.invalidateQueries({ queryKey: ["cohort-openings-defaults", cohort.id] })
    },
    onError: (e: any) => setError(getErrorMessage(e, "Could not save defaults")),
  })

  const handleReset = () => {
    setError("")
    if (defaults) {
      setDraft(defaults.map((o) => ({
        role_id: o.role_id,
        slots: o.slots,
        amount_aed: o.amount_aed != null ? String(o.amount_aed) : "",
        notes: o.notes ?? "",
      })))
    }
  }

  return (
    <div className="flex flex-col gap-3 py-1">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <p className="text-sm font-semibold text-foreground">Default openings</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            What new sessions in this cohort offer until customized individually. Set once here, override per session.
          </p>
        </div>
      </div>

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading default openings…</p>
      ) : (
        <div className="flex flex-col gap-2">
          {rows.map((d, i) => {
            const role = roles.find((r) => r.id === d.role_id)
            return (
              <div key={d.role_id} className="flex items-end gap-2 flex-wrap">
                <span className="text-sm text-foreground min-w-[9rem] h-9 flex items-center font-medium">
                  {role?.name ?? "Role"}
                </span>
                <label className="flex flex-col gap-0.5">
                  <span className="text-[10px] text-muted-foreground leading-none">Slots</span>
                  <input
                    type="number"
                    min={1}
                    value={d.slots}
                    onChange={(e) => setDraft(rows.map((x, j) =>
                      j === i ? { ...x, slots: Math.max(1, Number(e.target.value) || 1) } : x))}
                    className="!w-16 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right tabular-nums focus:outline-none focus:border-primary transition-colors"
                  />
                </label>
                <label className="flex flex-col gap-0.5">
                  <span className="text-[10px] text-muted-foreground leading-none">Amount (AED)</span>
                  <input
                    type="number"
                    min={0}
                    value={d.amount_aed}
                    onChange={(e) => setDraft(rows.map((x, j) =>
                      j === i ? { ...x, amount_aed: e.target.value } : x))}
                    className="!w-28 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right tabular-nums focus:outline-none focus:border-primary transition-colors"
                  />
                </label>
                <label className="flex-1 min-w-[8rem] flex flex-col gap-0.5">
                  <span className="text-[10px] text-muted-foreground leading-none">Notes</span>
                  <input
                    placeholder="Optional"
                    value={d.notes}
                    onChange={(e) => setDraft(rows.map((x, j) =>
                      j === i ? { ...x, notes: e.target.value } : x))}
                    className="w-full h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm focus:outline-none focus:border-primary transition-colors"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => setDraft(rows.filter((_, j) => j !== i))}
                  className="p-2 h-9 text-muted-foreground hover:text-red-600 transition-colors shrink-0"
                  aria-label="Remove default opening"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            )
          })}

          {rows.length === 0 && (
            <p className="text-sm text-muted-foreground py-1">
              No default openings set — new sessions in this cohort will start with nothing offered until you add a role here or customize per session.
            </p>
          )}
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap pt-1">
        {unusedRoles.length > 0 && (
          <select
            value=""
            onChange={(e) => {
              if (e.target.value) {
                setDraft([...rows, { role_id: e.target.value, slots: 1, amount_aed: "", notes: "" }])
              }
            }}
            className="h-9 px-3 border border-border bg-background text-foreground rounded-lg text-sm cursor-pointer focus:outline-none focus:border-primary transition-colors"
          >
            <option value="">+ Add a role…</option>
            {unusedRoles.map((r) => (
              <option key={r.id} value={r.id}>{r.name}</option>
            ))}
          </select>
        )}

        <button
          type="button"
          onClick={() => { setError(""); save.mutate() }}
          disabled={draft === null || save.isPending}
          className="h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:opacity-90 disabled:opacity-40 transition-colors"
        >
          {save.isPending ? "Saving defaults…" : "Save defaults"}
        </button>

        <button
          type="button"
          onClick={handleReset}
          className="h-9 px-3 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          Reset
        </button>
      </div>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}
