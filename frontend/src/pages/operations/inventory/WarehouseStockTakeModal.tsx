import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { StockLevel } from "@/types/inventory"
import { adjustStockBulkApi, getItemCategoriesApi, getItemsApi, getStockApi, getWarehousesApi } from "@/api/inventory"
import { Field, Modal, ModalActions } from "@/pages/admin/components/common"

/** The transposed grid: one warehouse, every item. Same `adjust-bulk`
 *  endpoint as `StockCountModal`, just the other axis — this is the one that
 *  turns "stock 50 items into a new warehouse" from 50 separate saves into
 *  one, which is the actual reason most items never get a count anywhere. */
export function WarehouseStockTakeModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [warehouseId, setWarehouseId] = useState("")
  const [search, setSearch] = useState("")
  const [category, setCategory] = useState("")
  const [onlyStockedHere, setOnlyStockedHere] = useState(false)
  const [values, setValues] = useState<Record<string, string>>({})
  const [reason, setReason] = useState("")
  const [error, setError] = useState("")

  const { data: warehouses = [] } = useQuery({ queryKey: ["inv-warehouses-all"], queryFn: () => getWarehousesApi() })
  const { data: items = [] } = useQuery({ queryKey: ["inv-items"], queryFn: () => getItemsApi() })
  const { data: categories = [] } = useQuery({ queryKey: ["inv-categories"], queryFn: () => getItemCategoriesApi() })
  const { data: stock = [] } = useQuery<StockLevel[]>({
    queryKey: ["inv-stock", "warehouse", warehouseId],
    queryFn: () => getStockApi({ warehouse_id: warehouseId }),
    enabled: !!warehouseId,
  })

  // Switching warehouses starts the grid over.
  useEffect(() => { setValues({}) }, [warehouseId])

  const stockByItem = useMemo(() => {
    const map: Record<string, number> = {}
    for (const s of stock) map[s.item_id] = s.qty
    return map
  }, [stock])

  const filteredItems = useMemo(() => items.filter((i) => {
    if (category && i.category !== category) return false
    if (search.trim() && !i.name.toLowerCase().includes(search.trim().toLowerCase())) return false
    if (onlyStockedHere && stockByItem[i.id] === undefined) return false
    return true
  }), [items, category, search, onlyStockedHere, stockByItem])

  const changedLevels = useMemo(() => filteredItems.reduce<{ item_id: string; warehouse_id: string; new_qty: number }[]>(
    (acc, i) => {
      const raw = values[i.id]
      if (raw === undefined || raw.trim() === "") return acc
      const newQty = Math.max(0, Math.trunc(Number(raw)) || 0)
      const current = stockByItem[i.id]
      if (current !== undefined && newQty === current) return acc
      acc.push({ item_id: i.id, warehouse_id: warehouseId, new_qty: newQty })
      return acc
    },
    [],
  ), [filteredItems, values, stockByItem, warehouseId])

  const mutation = useMutation({
    mutationFn: adjustStockBulkApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-stock"] })
      onClose()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not record that"),
  })

  return (
    <Modal title="Stock take" onClose={onClose} maxWidth="sm:max-w-3xl max-w-3xl">
      <div className="flex flex-col gap-4">
        <Field label="Warehouse">
          <select
            value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
          >
            <option value="">Choose…</option>
            {warehouses.map((w) => (
              <option key={w.id} value={w.id}>{w.location_name ? `${w.location_name} · ${w.name}` : w.name}</option>
            ))}
          </select>
        </Field>

        {warehouseId && (
          <>
            <div className="flex items-end gap-3 flex-wrap">
              <Field label="Search">
                <input
                  value={search} onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search by name…"
                  className="h-9 w-48 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
                />
              </Field>
              <Field label="Category">
                <select
                  value={category} onChange={(e) => setCategory(e.target.value)}
                  className="h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm capitalize"
                >
                  <option value="">All categories</option>
                  {categories.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
                </select>
              </Field>
              <label className="flex items-center gap-1.5 h-9 text-sm text-foreground cursor-pointer">
                <input
                  type="checkbox" checked={onlyStockedHere}
                  onChange={(e) => setOnlyStockedHere(e.target.checked)}
                />
                Only items already stocked here
              </label>
            </div>

            <div className="rounded-2xl border border-border divide-y divide-border max-h-80 overflow-y-auto">
              {filteredItems.map((i) => (
                <div key={i.id} className="flex items-center justify-between gap-3 px-4 py-2">
                  <span className="text-sm text-foreground truncate">{i.name}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs text-muted-foreground w-28 text-right truncate">
                      {stockByItem[i.id] === undefined ? "not stocked here" : `was ${stockByItem[i.id]}`}
                    </span>
                    <input
                      type="number" min={0}
                      value={values[i.id] ?? ""}
                      onChange={(e) => setValues((prev) => ({ ...prev, [i.id]: e.target.value }))}
                      placeholder="—"
                      className="w-20 h-8 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right"
                    />
                  </div>
                </div>
              ))}
              {filteredItems.length === 0 && (
                <p className="px-4 py-6 text-sm text-muted-foreground text-center">Nothing matches that search.</p>
              )}
            </div>
          </>
        )}

        <Field label="Reason (for everything changed above)">
          <input
            value={reason} onChange={(e) => setReason(e.target.value)}
            placeholder="Monthly stocktake, new warehouse first fill…"
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
          />
        </Field>

        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

        <ModalActions
          onCancel={onClose}
          onConfirm={() => {
            setError("")
            if (changedLevels.length === 0) { setError("Change at least one item's count"); return }
            if (!reason.trim()) { setError("A reason is required"); return }
            mutation.mutate({ reason: reason.trim(), levels: changedLevels })
          }}
          loading={mutation.isPending}
          disabled={!warehouseId}
          label={changedLevels.length ? `Save ${changedLevels.length} change${changedLevels.length === 1 ? "" : "s"}` : "Save"}
        />
      </div>
    </Modal>
  )
}
