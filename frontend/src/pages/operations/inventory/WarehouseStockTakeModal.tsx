import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Package, Search } from "lucide-react"
import type { StockLevel } from "@/types/inventory"
import {
  adjustStockBulkApi,
  getItemCategoriesApi,
  getItemsApi,
  getStockApi,
  getWarehousesApi,
} from "@/api/inventory"
import { Field, Modal, ModalActions } from "@/pages/admin/components/common"

/** The transposed grid: one warehouse, every item. Same `adjust-bulk`
 *  endpoint as `StockCountModal`, just the other axis — this is the one that
 *  turns "stock 50 items into a new warehouse" from 50 separate saves into
 *  one, which is the actual reason most items never get a count anywhere. */
export function WarehouseStockTakeModal({
  initialWarehouseId,
  onClose,
}: {
  initialWarehouseId?: string
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [warehouseId, setWarehouseId] = useState(initialWarehouseId || "")
  const [search, setSearch] = useState("")
  const [category, setCategory] = useState("")
  const [subcategory, setSubcategory] = useState("")
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

  const selectedCategoryDef = useMemo(
    () => categories.find((c) => c.name === category),
    [categories, category],
  )
  const availableSubcategories = selectedCategoryDef?.subcategories ?? []

  // Switching warehouses starts the grid over.
  useEffect(() => {
    setValues({})
  }, [warehouseId])

  const stockByItem = useMemo(() => {
    const map: Record<string, number> = {}
    for (const s of stock) map[s.item_id] = s.qty
    return map
  }, [stock])

  const filteredItems = useMemo(() => items.filter((i) => {
    if (category && i.category !== category) return false
    if (subcategory && i.subcategory !== subcategory) return false
    if (search.trim() && !i.name.toLowerCase().includes(search.trim().toLowerCase())) return false
    if (onlyStockedHere && stockByItem[i.id] === undefined) return false
    return true
  }), [items, category, subcategory, search, onlyStockedHere, stockByItem])

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
                <div className="relative">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input
                    value={search} onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search by name…"
                    className="h-9 w-48 pl-8 pr-3 border border-border bg-background text-foreground rounded-xl text-sm"
                  />
                </div>
              </Field>
              <Field label="Category">
                <select
                  value={category}
                  onChange={(e) => {
                    setCategory(e.target.value)
                    setSubcategory("")
                  }}
                  className="h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm capitalize"
                >
                  <option value="">All categories</option>
                  {categories.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
                </select>
              </Field>
              <Field label="Subcategory">
                <select
                  value={subcategory}
                  onChange={(e) => setSubcategory(e.target.value)}
                  disabled={!category || availableSubcategories.length === 0}
                  className="h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm capitalize disabled:opacity-50"
                >
                  <option value="">
                    {!category
                      ? "All subcategories"
                      : availableSubcategories.length === 0
                        ? "No subcategories"
                        : "All subcategories"}
                  </option>
                  {availableSubcategories.map((sc) => (
                    <option key={sc.id} value={sc.name}>{sc.name}</option>
                  ))}
                </select>
              </Field>
              <label className="flex items-center gap-1.5 h-9 text-sm text-foreground cursor-pointer select-none">
                <input
                  type="checkbox" checked={onlyStockedHere}
                  onChange={(e) => setOnlyStockedHere(e.target.checked)}
                />
                Only stocked here
              </label>
            </div>

            <div className="rounded-2xl border border-border divide-y divide-border max-h-[520px] overflow-y-auto">
              {filteredItems.map((i) => {
                const wasText = stockByItem[i.id] === undefined ? "not stocked" : `was ${stockByItem[i.id]}`
                return (
                  <div
                    key={i.id}
                    className="flex items-center justify-between gap-3 px-3 sm:px-5 py-3.5 sm:py-4 hover:bg-muted/20 transition-colors"
                  >
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      {/* Item Image */}
                      <div className="w-14 h-14 sm:w-20 sm:h-20 rounded-xl sm:rounded-2xl overflow-hidden border border-border bg-muted/40 flex items-center justify-center shrink-0 shadow-xs">
                        {i.image_url ? (
                          <img src={i.image_url} alt="" className="w-full h-full object-cover" />
                        ) : (
                          <Package size={22} className="text-muted-foreground/50" />
                        )}
                      </div>

                      {/* Item Details */}
                      <div className="min-w-0 flex flex-col justify-center gap-1 flex-1 pr-1">
                        <span className="text-sm sm:text-base font-bold text-foreground leading-snug line-clamp-2" title={i.name}>
                          {i.name}
                        </span>
                        <div className="flex items-center gap-1.5 flex-wrap">
                          {i.category && (
                            <span className="inline-flex items-center text-[11px] sm:text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground capitalize font-medium">
                              {i.category}
                            </span>
                          )}
                          {i.subcategory && (
                            <span className="inline-flex items-center text-[11px] sm:text-xs px-2 py-0.5 rounded-full bg-muted/60 text-muted-foreground capitalize">
                              {i.subcategory}
                            </span>
                          )}
                          <span className="text-[11px] text-muted-foreground sm:hidden font-medium">
                            · {wasText}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 sm:gap-3 shrink-0">
                      <span className="text-xs text-muted-foreground w-24 text-right truncate hidden sm:inline">
                        {stockByItem[i.id] === undefined ? "not stocked here" : `was ${stockByItem[i.id]}`}
                      </span>
                      <input
                        type="number"
                        min={0}
                        value={values[i.id] ?? ""}
                        onChange={(e) => setValues((prev) => ({ ...prev, [i.id]: e.target.value }))}
                        placeholder="—"
                        className="w-16 sm:w-24 h-10 sm:h-11 px-2 sm:px-3 border border-border bg-background text-foreground rounded-xl text-sm sm:text-base font-semibold text-right focus:outline-none focus:border-primary shadow-xs"
                      />
                    </div>
                  </div>
                )
              })}
              {filteredItems.length === 0 && (
                <p className="px-4 py-12 text-sm text-muted-foreground text-center">Nothing matches that search.</p>
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
