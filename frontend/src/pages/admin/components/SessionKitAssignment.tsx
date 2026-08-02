import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Boxes, CheckCircle2, Clock, X } from "lucide-react"
import {
  confirmKitReturnsApi,
  getKitsApi,
  getWarehousesApi,
  getSessionKitsApi,
  removeSessionKitApi,
  setSessionKitsApi,
} from "@/api/inventory"
import { Modal, Field, ModalActions } from "@/pages/admin/components/common"
import { InheritedFrom, InheritedBadge } from "@/pages/admin/components/InheritedFrom"
import { useToast } from "@/components/ui/toast"
import { cn } from "@/lib/utils"

/**
 * Kits for a session, on the ops side (I2-1/I2-3).
 *
 * Lives in its own file rather than inside Cohorts.tsx, which is already
 * ~105 KB and has produced three stale-prop bugs of the same class. The
 * modal takes one import and one line.
 *
 * No custody leg (2026-08-01): kits are assigned here, and that's the whole
 * story until the instructor reports back. This panel shows that report —
 * received / returned / return-later — and lets ops confirm it, optionally
 * moving a kit onto a shelf at the same time. That move is a separate,
 * ordinary inventory action, not something the instructor's report triggers.
 */
export function SessionKitAssignment({
  sessionId, hasInstructor, effectiveWarehouseId = null, effectiveWarehouseName = null, onChanged,
}: {
  sessionId: string
  hasInstructor: boolean
  /** The session's assigned warehouse (session override, else the cohort's) —
   *  defaults the restock picker so ops isn't retyping the same warehouse
   *  every time. */
  effectiveWarehouseId?: string | null
  effectiveWarehouseName?: string | null
  onChanged: () => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [picking, setPicking] = useState(false)
  const [confirming, setConfirming] = useState<{ kitIds: string[] } | null>(null)
  const [error, setError] = useState("")

  const { data } = useQuery({
    queryKey: ["session-kits", sessionId],
    queryFn: () => getSessionKitsApi(sessionId),
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["session-kits", sessionId] })
    qc.invalidateQueries({ queryKey: ["inv-kits"] })
    onChanged()
  }

  const remove = useMutation({
    mutationFn: (kitId: string) => removeSessionKitApi({ sessionId, kitId }),
    onSuccess: () => { toast.success("Kit removed"); setError(""); refresh() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not remove that kit"),
  })

  const kits = data?.kits ?? []
  const awaitingReview = kits.filter((k) => k.return_status && !k.ops_confirmed)
  // 2026-08-01 cohort kit defaults: this session hasn't picked its own yet,
  // it's showing whatever the cohort defaults to.
  const usingCohortDefaults = data?.level === "cohort"

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Boxes size={14} /> Kits
        </p>
        <button onClick={() => setPicking(true)} className="text-xs text-primary hover:underline">
          Choose kits
        </button>
      </div>

      {/* Same inheritance treatment as location/warehouse, rather than this
          panel's old bespoke grey info box (2026-08-02). */}
      <InheritedFrom
        overridden={!usingCohortDefaults && kits.length > 0}
        hint={usingCohortDefaults
          ? "Using the cohort's default kits — assign or remove one to make this session's own."
          : undefined}
      />

      {kits.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No kits for this session. Sessions without kits are unaffected by any of this.
        </p>
      ) : (
        <>
          <div className="flex flex-col gap-1.5">
            {kits.map((k) => (
              <div key={k.kit_id} className="flex items-center justify-between gap-2 text-sm">
                <span className="min-w-0">
                  <span className="font-mono text-foreground">{k.label}</span>
                  <span className="text-xs text-muted-foreground">
                    {" · "}{k.location_name}
                    {!k.received && " · not yet received"}
                    {k.return_status === "returned" && !k.ops_confirmed && " · reported returned"}
                    {k.return_status === "return_later" && !k.ops_confirmed && " · returning later"}
                    {k.ops_confirmed && " · confirmed back"}
                  </span>
                  {k.inherited && <InheritedBadge overridden={false} className="ml-1.5 align-middle" />}
                </span>
                <span className="flex items-center gap-2 shrink-0">
                  {k.return_status && !k.ops_confirmed && (
                    <button
                      onClick={() => setConfirming({ kitIds: [k.kit_id] })}
                      className="text-xs text-primary hover:underline"
                    >
                      Confirm
                    </button>
                  )}
                  {k.ops_confirmed ? (
                    <CheckCircle2 size={13} className="text-emerald-600 dark:text-emerald-400" />
                  ) : k.return_status === "return_later" ? (
                    <Clock size={13} className="text-amber-600 dark:text-amber-400" />
                  ) : (
                    <AlertTriangle size={13} className="text-amber-600 dark:text-amber-400" />
                  )}
                  <button
                    onClick={() => remove.mutate(k.kit_id)}
                    className="text-muted-foreground hover:text-red-600"
                    title="Remove from this session"
                  >
                    <X size={13} />
                  </button>
                </span>
              </div>
            ))}
          </div>

          {awaitingReview.length > 1 && (
            <div className="flex flex-wrap gap-2 mt-1">
              <button
                onClick={() => setConfirming({ kitIds: awaitingReview.map((k) => k.kit_id) })}
                className="h-8 px-3 border border-border rounded-lg text-xs font-medium text-muted-foreground hover:bg-muted"
              >
                Confirm all reported ({awaitingReview.length})
              </button>
            </div>
          )}

          {!hasInstructor && kits.some((k) => !k.received) && (
            <p className="text-xs text-muted-foreground">
              Assign an instructor so they can confirm they have these.
            </p>
          )}
          {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
        </>
      )}

      {picking && (
        <KitPicker
          sessionId={sessionId}
          selected={kits.map((k) => k.kit_id)}
          effectiveWarehouseId={effectiveWarehouseId}
          effectiveWarehouseName={effectiveWarehouseName}
          onClose={() => setPicking(false)}
          onDone={() => { setPicking(false); refresh() }}
        />
      )}
      {confirming && (
        <ConfirmReturnModal
          sessionId={sessionId}
          kitIds={confirming.kitIds}
          defaultWarehouseName={effectiveWarehouseName}
          onClose={() => setConfirming(null)}
          onDone={() => { setConfirming(null); refresh() }}
        />
      )}
    </div>
  )
}

function KitPicker({ sessionId, selected, effectiveWarehouseId, effectiveWarehouseName, onClose, onDone }: {
  sessionId: string
  selected: string[]
  effectiveWarehouseId?: string | null
  effectiveWarehouseName?: string | null
  onClose: () => void
  onDone: () => void
}) {
  const toast = useToast()
  const [chosen, setChosen] = useState<string[]>(selected)
  const { data: kits = [] } = useQuery({ queryKey: ["inv-kits", "", "", false], queryFn: () => getKitsApi() })

  // Kits already at the session's assigned warehouse first — that's the
  // common pick — without hiding kits sitting elsewhere (ops can still
  // choose one and transfer it in).
  const sortedKits = effectiveWarehouseId
    ? [...kits].sort((a, b) =>
        Number(b.current_warehouse_id === effectiveWarehouseId) - Number(a.current_warehouse_id === effectiveWarehouseId))
    : kits

  // The API takes the whole set and is idempotent, so the picker resubmits
  // everything rather than diffing.
  const save = useMutation({
    mutationFn: () => setSessionKitsApi({ sessionId, kitIds: chosen }),
    onSuccess: () => { toast.success("Session kits saved"); onDone() },
  })

  return (
    <Modal title="Kits for this session" onClose={onClose} maxWidth="max-w-md">
      {effectiveWarehouseName && (
        <p className="text-xs text-muted-foreground -mt-1">
          This session's warehouse is {effectiveWarehouseName} — kits there are listed first.
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

/** Confirming the instructor's report. Restocking is a separate, optional
 *  choice on the same screen — a kit that never physically left has nothing
 *  to move, and forcing a location on every confirmation would be wrong for
 *  exactly that case. */
function ConfirmReturnModal({ sessionId, kitIds, defaultWarehouseName, onClose, onDone }: {
  sessionId: string
  kitIds: string[]
  defaultWarehouseName?: string | null
  onClose: () => void
  onDone: () => void
}) {
  const toast = useToast()
  const { data: warehouses = [] } = useQuery({ queryKey: ["inv-warehouses"], queryFn: () => getWarehousesApi() })
  const [warehouseId, setWarehouseId] = useState("")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: confirmKitReturnsApi,
    onSuccess: () => { toast.success("Kit return confirmed"); onDone() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not record that"),
  })

  return (
    <Modal title={kitIds.length === 1 ? "Confirm this kit's return" : `Confirm ${kitIds.length} kits' return`} onClose={onClose}>
      <Field label="Put it back on a shelf? (optional)">
        <select
          value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        >
          <option value="">Don&apos;t move it — just confirm</option>
          {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
        {defaultWarehouseName && (
          <p className="text-xs text-muted-foreground mt-1">This session's warehouse is {defaultWarehouseName}.</p>
        )}
      </Field>
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
      <ModalActions
        onCancel={onClose}
        onConfirm={() => {
          setError("")
          mutation.mutate({ sessionId, kitIds, restockWarehouseId: warehouseId || undefined })
        }}
        loading={mutation.isPending}
        disabled={false}
        label="Confirm"
      />
    </Modal>
  )
}
