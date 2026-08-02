import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Boxes, Trash2 } from "lucide-react"
import { getCohortKitsApi, setCohortKitsApi, removeCohortKitApi, getKitsApi } from "@/api/inventory"
import { Modal, ModalActions } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { cn } from "@/lib/utils"
import type { Cohort } from "@/types/sessions"

/**
 * Cohort-level kit defaults (2026-08-01) — what a session in this cohort is
 * equipped with until it picks its own, same "set it once, override
 * per-session" pattern already established by MaterialsPanel. No
 * received/returned/confirm-return UI here: none of that custody-report
 * flow applies at the cohort level, only at the session's own Kits panel.
 */
export function CohortKitsPanel({ cohort }: { cohort: Cohort }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [picking, setPicking] = useState(false)
  const [error, setError] = useState("")

  const { data } = useQuery({
    queryKey: ["cohort-kits", cohort.id],
    queryFn: () => getCohortKitsApi(cohort.id),
  })
  const kits = data?.kits ?? []

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["cohort-kits", cohort.id] })
    // Sessions inherit these — the session-level Kits panel needs a nudge too.
    qc.invalidateQueries({ queryKey: ["session-kits"] })
  }

  const remove = useMutation({
    mutationFn: (kitId: string) => removeCohortKitApi({ cohortId: cohort.id, kitId }),
    onSuccess: () => { toast.success("Kit removed from defaults"); setError(""); invalidate() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not remove that kit"),
  })

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Boxes size={14} /> Default kits
        </p>
        <button onClick={() => setPicking(true)} className="text-xs text-primary hover:underline">
          Choose kits
        </button>
      </div>
      <p className="text-xs text-muted-foreground -mt-1">
        What a session in this cohort is equipped with until it picks its own — set it once here,
        override it for one session in that session's own Kits panel.
      </p>

      {kits.length === 0 ? (
        <p className="text-sm text-muted-foreground">No default kits set for this cohort.</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {kits.map((k) => (
            <div
              key={k.kit_id}
              className="flex items-center justify-between gap-2 px-3 py-2 bg-background border border-border rounded-xl text-sm"
            >
              <span className="min-w-0">
                <span className="font-mono text-foreground">{k.label}</span>
                <span className="text-xs text-muted-foreground"> · {k.template_name} · {k.location_name}</span>
              </span>
              <button
                onClick={() => remove.mutate(k.kit_id)}
                className="text-muted-foreground hover:text-red-600 shrink-0"
                title="Remove from cohort defaults"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      )}
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      {picking && (
        <CohortKitPicker
          cohortId={cohort.id}
          effectiveWarehouseId={cohort.effective_warehouse_id ?? null}
          effectiveWarehouseName={cohort.effective_warehouse_name ?? null}
          selected={kits.map((k) => k.kit_id)}
          onClose={() => setPicking(false)}
          onDone={() => { setPicking(false); invalidate() }}
        />
      )}
    </div>
  )
}

/** Standalone multi-select kit picker — deliberately not shared with
 *  SessionKitAssignment's KitPicker: that one is entangled with the
 *  received/returned custody report, which has no cohort-level analogue. */
function CohortKitPicker({ cohortId, selected, effectiveWarehouseId, effectiveWarehouseName, onClose, onDone }: {
  cohortId: string
  selected: string[]
  effectiveWarehouseId?: string | null
  effectiveWarehouseName?: string | null
  onClose: () => void
  onDone: () => void
}) {
  const toast = useToast()
  const [chosen, setChosen] = useState<string[]>(selected)
  const { data: kits = [] } = useQuery({ queryKey: ["inv-kits", "", "", false], queryFn: () => getKitsApi() })

  // Kits already at the cohort's assigned warehouse first — the common
  // pick — without hiding kits sitting elsewhere.
  const sortedKits = effectiveWarehouseId
    ? [...kits].sort((a, b) =>
        Number(b.current_warehouse_id === effectiveWarehouseId) - Number(a.current_warehouse_id === effectiveWarehouseId))
    : kits

  // Full resubmit — the API takes the whole set and is idempotent.
  const save = useMutation({
    mutationFn: () => setCohortKitsApi({ cohortId, kitIds: chosen }),
    onSuccess: () => { toast.success("Default kits saved"); onDone() },
  })

  return (
    <Modal title="Default kits for this cohort" onClose={onClose} maxWidth="max-w-md">
      {effectiveWarehouseName && (
        <p className="text-xs text-muted-foreground -mt-1">
          This cohort's warehouse is {effectiveWarehouseName} — kits there are listed first.
        </p>
      )}
      <div className="flex flex-col gap-1 max-h-[50vh] overflow-y-auto">
        {sortedKits.map((k) => {
          const on = chosen.includes(k.id)
          return (
            <label
              key={k.id}
              className={cn(
                "flex items-center justify-between gap-2 px-3 py-2 rounded-xl border cursor-pointer transition-colors",
                on ? "border-primary/30 bg-primary/5" : "border-border hover:bg-muted",
              )}
            >
              <span className="min-w-0">
                <span className="font-mono text-sm text-foreground">{k.label}</span>
                <span className="block text-xs text-muted-foreground truncate">
                  {k.location_name}
                  {k.holder_name && ` · with ${k.holder_name}`}
                  {k.shortage_count > 0 && ` · ${k.shortage_count} missing`}
                </span>
              </span>
              <input
                type="checkbox" checked={on}
                onChange={() => setChosen(on ? chosen.filter((id) => id !== k.id) : [...chosen, k.id])}
              />
            </label>
          )
        })}
        {kits.length === 0 && (
          <p className="text-sm text-muted-foreground py-4 text-center">No kits exist yet.</p>
        )}
      </div>
      <ModalActions
        onCancel={onClose}
        onConfirm={() => save.mutate()}
        loading={save.isPending}
        disabled={false}
        label="Save"
      />
    </Modal>
  )
}
