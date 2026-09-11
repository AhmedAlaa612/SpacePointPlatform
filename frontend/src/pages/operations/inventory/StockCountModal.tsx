import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MapPin } from "lucide-react"
import type { StockLevel, Warehouse, WarehouseCabin } from "@/types/inventory"
import {
  adjustStockBulkApi,
  getItemsApi,
  getStockApi,
  getWarehousesApi,
  setItemCabinsApi,
} from "@/api/inventory"
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
export function StockCountModal({
  itemId: fixedItemId,
  itemName: fixedItemName,
  warehouseId,
  onClose,
}: {
  itemId?: string
  itemName?: string
  warehouseId?: string
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [itemId, setItemId] = useState(fixedItemId ?? "")
  const [values, setValues] = useState<Record<string, string>>({})
  const [selectedCabins, setSelectedCabins] = useState<Record<string, string>>({})
  const [reason, setReason] = useState("")
  const [error, setError] = useState("")

  const { data: items } = useQuery({
    queryKey: ["inv-items"],
    queryFn: () => getItemsApi(),
    enabled: !fixedItemId,
  })
  const { data: warehouses } = useQuery({
    queryKey: ["inv-warehouses-all"],
    queryFn: () => getWarehousesApi(),
  })
  const { data: stock } = useQuery<StockLevel[]>({
    queryKey: ["inv-stock", "item", itemId],
    queryFn: () => getStockApi({ item_id: itemId }),
    enabled: !!itemId,
  })

  const itemList = items ?? []
  const warehouseList = useMemo(() => {
    const list = warehouses ?? []
    if (warehouseId) {
      return list.filter((w) => w.id === warehouseId)
    }
    return list
  }, [warehouses, warehouseId])
  const stockList = stock ?? []

  // Switching items (the standalone picker) starts the grid over — another
  // item's typed values are meaningless once the item underneath changes.
  useEffect(() => {
    setValues({})
    setSelectedCabins({})
  }, [itemId])

  // Populate initial cabin assignments from existing stock levels
  useEffect(() => {
    if (!stock || stock.length === 0) return
    const map: Record<string, string> = {}
    for (const s of stock) {
      if (s.cabins && s.cabins.length > 0) {
        map[s.warehouse_id] = s.cabins[0].cabin_id
      }
    }
    setSelectedCabins(map)
  }, [stock])

  const stockByWarehouse = useMemo(() => {
    const map: Record<string, number> = {}
    for (const s of stockList) map[s.warehouse_id] = s.qty
    return map
  }, [stockList])

  // A location with exactly one warehouse shows just the location name and
  // no second picker — the pattern already proven for cohorts/sessions
  // (`_resolve_effective_warehouse`), just applied to the read side here.
  const groups = useMemo(() => {
    const byLocation: Record<string, { name: string; warehouses: Warehouse[] }> = {}
    for (const w of warehouseList) {
      const key = w.location_id
      const entry = byLocation[key] ?? { name: w.location_name ?? "", warehouses: [] }
      entry.warehouses.push(w)
      byLocation[key] = entry
    }
    return Object.values(byLocation)
  }, [warehouseList])

  const itemName = fixedItemName ?? itemList.find((i) => i.id === itemId)?.name

  const changedLevels = useMemo(() => warehouseList.reduce<{ item_id: string; warehouse_id: string; new_qty: number }[]>(
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
  ), [warehouseList, values, stockByWarehouse, itemId])

  const hasCabinChanges = warehouseList.some((w) => {
    const oldCabin = stockList.find((s) => s.warehouse_id === w.id)?.cabins?.[0]?.cabin_id ?? ""
    const newCabin = selectedCabins[w.id] ?? ""
    return newCabin !== oldCabin
  })

  const mutation = useMutation({
    mutationFn: async () => {
      if (changedLevels.length > 0) {
        await adjustStockBulkApi({ reason: reason.trim() || "Count update", levels: changedLevels })
      }
      for (const w of warehouseList) {
        const oldCabin = stockList.find((s) => s.warehouse_id === w.id)?.cabins?.[0]?.cabin_id ?? ""
        const newCabin = selectedCabins[w.id] ?? ""
        if (newCabin !== oldCabin) {
          const payload = newCabin ? [{ cabin_id: newCabin, is_primary: true }] : []
          await setItemCabinsApi(w.id, itemId, payload)
        }
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-stock"] })
      queryClient.invalidateQueries({ queryKey: ["inv-warehouse-cabins"] })
      queryClient.invalidateQueries({ queryKey: ["inv-item-cabins"] })
      onClose()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not record that"),
  })

  const currentWarehouse = useMemo(() => {
    if (!warehouseId || !warehouses) return null
    return warehouses.find((w) => w.id === warehouseId)
  }, [warehouses, warehouseId])

  const modalTitle = currentWarehouse
    ? (itemName ? `Count ${itemName} · ${currentWarehouse.name}` : `Record count · ${currentWarehouse.name}`)
    : (itemName ? `Count ${itemName}` : "Record a count")

  return (
    <Modal title={modalTitle} onClose={onClose} maxWidth="sm:max-w-2xl max-w-2xl">
      <div className="flex flex-col gap-4">
        {!fixedItemId && (
          <Field label="Item">
            <select
              value={itemId} onChange={(e) => setItemId(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
            >
              <option value="">Choose…</option>
              {itemList.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
            </select>
          </Field>
        )}

        {itemId && (
          <div className="rounded-2xl border border-border divide-y divide-border max-h-80 overflow-y-auto">
            {groups.map((g) => (
              g.warehouses.length === 1 ? (
                <CountRow
                  key={g.warehouses[0].id}
                  label={
                    warehouseId
                      ? `${g.warehouses[0].name}${g.name && g.name !== g.warehouses[0].name ? ` (${g.name})` : ""}`
                      : g.name
                  }
                  current={stockByWarehouse[g.warehouses[0].id]}
                  value={values[g.warehouses[0].id] ?? (stockByWarehouse[g.warehouses[0].id]?.toString() ?? "")}
                  cabins={g.warehouses[0].cabins ?? []}
                  selectedCabinId={selectedCabins[g.warehouses[0].id] ?? ""}
                  onChange={(v) => setValues((prev) => ({ ...prev, [g.warehouses[0].id]: v }))}
                  onCabinChange={(cid) => setSelectedCabins((prev) => ({ ...prev, [g.warehouses[0].id]: cid }))}
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
                        cabins={w.cabins ?? []}
                        selectedCabinId={selectedCabins[w.id] ?? ""}
                        onChange={(v) => setValues((prev) => ({ ...prev, [w.id]: v }))}
                        onCabinChange={(cid) => setSelectedCabins((prev) => ({ ...prev, [w.id]: cid }))}
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
            if (changedLevels.length === 0 && !hasCabinChanges) {
              setError("Change at least one warehouse's count or cabin")
              return
            }
            if (changedLevels.length > 0 && !reason.trim()) {
              setError("A reason is required")
              return
            }
            mutation.mutate()
          }}
          loading={mutation.isPending}
          disabled={!itemId}
          label={
            changedLevels.length || hasCabinChanges
              ? `Save changes`
              : "Save"
          }
        />
      </div>
    </Modal>
  )
}

function CountRow({
  label,
  current,
  value,
  cabins,
  selectedCabinId,
  onChange,
  onCabinChange,
}: {
  label: string
  current?: number
  value: string
  cabins: WarehouseCabin[]
  selectedCabinId: string
  onChange: (v: string) => void
  onCabinChange: (cid: string) => void
}) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 px-4 py-2.5">
      <div className="min-w-0 flex-1">
        <span className="text-sm font-medium text-foreground truncate">{label}</span>
        {cabins.length > 0 && (
          <div className="flex items-center gap-1.5 mt-1">
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <MapPin size={11} className="text-primary" /> Cabin:
            </span>
            <select
              value={selectedCabinId}
              onChange={(e) => onCabinChange(e.target.value)}
              className="h-7 px-2 text-xs border border-border bg-background text-foreground rounded-lg cursor-pointer focus:outline-none focus:border-primary max-w-[200px]"
            >
              <option value="">None (unassigned)</option>
              {cabins.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
        <span className="text-xs text-muted-foreground w-28 text-right truncate">
          {current === undefined ? "not stocked here" : `was ${current}`}
        </span>
        <input
          type="number"
          min={0}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="—"
          className="w-20 h-8 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right"
        />
      </div>
    </div>
  )
}
