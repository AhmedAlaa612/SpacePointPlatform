import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { StockLevel, Warehouse } from "@/types/inventory"
import { adjustStockBulkApi, getItemsApi, getStockApi, getWarehousesApi } from "@/api/inventory"
import { Field, Modal, ModalActions } from "@/pages/admin/components/common"

/** One item, every active warehouse, one save.
 *
 *  Replaces both Stock.tsx's `AdjustModal` and Catalog.tsx's
 *  `ItemAdjustModal` — same endpoint transposed into a grid instead of a
 *  one-warehouse-at-a-time form, so stocking an item across several
 *  warehouses (or stocking it anywhere for the first time) is one save
 *  instead of N.
 *
 *  A blank cell means "not stocked here, don't touch it"; a typed `0` means
 *  "stocked here and currently out" — the two states this exists to keep
 *  apart. Only cells that actually changed are sent.
 *
 *  `itemId` omitted (Stock.tsx's standalone "Record a count" button) shows
 *  an item picker first; passed in (either page's per-item "Adjust") skips
 *  straight to the grid.
 */
export function StockCountModal({ itemId: fixedItemId, itemName: fixedItemName, onClose }: {
  itemId?: string
  itemName?: string
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [itemId, setItemId] = useState(fixedItemId ?? "")
  const [values, setValues] = useState<Record<string, string>>({})
  const [reason, setReason] = useState("")
  const [error, setError] = useState("")

  const { data: items = [] } = useQuery({
    queryKey: ["inv-items"], queryFn: () => getItemsApi(), enabled: !fixedItemId,
  })
  const { data: warehouses = [] } = useQuery({
    queryKey: ["inv-warehouses-all"], queryFn: () => getWarehousesApi(),
  })
  const { data: stock = [] } = useQuery<StockLevel[]>({
    queryKey: ["inv-stock", "item", itemId],
    queryFn: () => getStockApi({ item_id: itemId }),
    enabled: !!itemId,
  })

  // Switching items (the standalone picker) starts the grid over — another
  // item's typed values are meaningless once the item underneath changes.
  useEffect(() => { setValues({}) }, [itemId])

  const stockByWarehouse = useMemo(() => {
    const map: Record<string, number> = {}
    for (const s of stock) map[s.warehouse_id] = s.qty
    return map
  }, [stock])

  // A location with exactly one warehouse shows just the location name and
  // no second picker — the pattern already proven for cohorts/sessions
  // (`_resolve_effective_warehouse`), just applied to the read side here.
  const groups = useMemo(() => {
    const byLocation: Record<string, { name: string; warehouses: Warehouse[] }> = {}
    for (const w of warehouses) {
      const key = w.location_id
      const entry = byLocation[key] ?? { name: w.location_name ?? "", warehouses: [] }
      entry.warehouses.push(w)
      byLocation[key] = entry
    }
    return Object.values(byLocation)
  }, [warehouses])

  const itemName = fixedItemName ?? items.find((i) => i.id === itemId)?.name

  const changedLevels = useMemo(() => warehouses.reduce<{ item_id: string; warehouse_id: string; new_qty: number }[]>(
    (acc, w) => {
      const raw = values[w.id]
      if (raw === undefined || raw.trim() === "") return acc
      const newQty = Math.max(0, Math.trunc(Number(raw)) || 0)
      const current = stockByWarehouse[w.id]
      if (current !== undefined && newQty === current) return acc
      acc.push({ item_id: itemId, warehouse_id: w.id, new_qty: newQty })
      return acc
    },
    [],
  ), [warehouses, values, stockByWarehouse, itemId])

  const mutation = useMutation({
    mutationFn: adjustStockBulkApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-stock"] })
      onClose()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not record that"),
  })

  return (
    <Modal title={itemName ? `Count ${itemName}` : "Record a count"} onClose={onClose} maxWidth="sm:max-w-2xl max-w-2xl">
      <div className="flex flex-col gap-4">
        {!fixedItemId && (
          <Field label="Item">
            <select
              value={itemId} onChange={(e) => setItemId(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
            >
              <option value="">Choose…</option>
              {items.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
            </select>
          </Field>
        )}

        {itemId && (
          <div className="rounded-2xl border border-border divide-y divide-border max-h-80 overflow-y-auto">
            {groups.map((g) => (
              g.warehouses.length === 1 ? (
                <CountRow
                  key={g.warehouses[0].id}
                  label={g.name}
                  current={stockByWarehouse[g.warehouses[0].id]}
                  value={values[g.warehouses[0].id] ?? (stockByWarehouse[g.warehouses[0].id]?.toString() ?? "")}
                  onChange={(v) => setValues((prev) => ({ ...prev, [g.warehouses[0].id]: v }))}
                />
              ) : (
                <div key={g.name} className="px-4 py-2.5">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">{g.name}</p>
                  <div className="flex flex-col gap-1.5">
                    {g.warehouses.map((w) => (
                      <CountRow
                        key={w.id}
                        label={w.name}
                        current={stockByWarehouse[w.id]}
                        value={values[w.id] ?? (stockByWarehouse[w.id]?.toString() ?? "")}
                        onChange={(v) => setValues((prev) => ({ ...prev, [w.id]: v }))}
                      />
                    ))}
                  </div>
                </div>
              )
            ))}
            {groups.length === 0 && (
              <p className="px-4 py-6 text-sm text-muted-foreground text-center">No active warehouses yet.</p>
            )}
          </div>
        )}

        <Field label="Reason (for everything changed above)">
          <input
            value={reason} onChange={(e) => setReason(e.target.value)}
            placeholder="Stocktake, delivery arrived, one was broken…"
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
          />
        </Field>

        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

        <ModalActions
          onCancel={onClose}
          onConfirm={() => {
            setError("")
            if (changedLevels.length === 0) { setError("Change at least one warehouse's count"); return }
            if (!reason.trim()) { setError("A reason is required"); return }
            mutation.mutate({ reason: reason.trim(), levels: changedLevels })
          }}
          loading={mutation.isPending}
          disabled={!itemId}
          label={changedLevels.length ? `Save ${changedLevels.length} change${changedLevels.length === 1 ? "" : "s"}` : "Save"}
        />
      </div>
    </Modal>
  )
}

function CountRow({ label, current, value, onChange }: {
  label: string
  current?: number
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-2">
      <span className="text-sm text-foreground truncate">{label}</span>
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-xs text-muted-foreground w-28 text-right truncate">
          {current === undefined ? "not stocked here" : `was ${current}`}
        </span>
        <input
          type="number" min={0} value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="—"
          className="w-20 h-8 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right"
        />
      </div>
    </div>
  )
}
