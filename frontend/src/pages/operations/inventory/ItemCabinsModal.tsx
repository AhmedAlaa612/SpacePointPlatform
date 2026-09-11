import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MapPin, Plus, Trash2 } from "lucide-react"
import type { ItemCabinAssignment, WarehouseCabin } from "@/types/inventory"
import {
  getItemCabinsApi,
  getWarehouseCabinsApi,
  getWarehousesApi,
  setItemCabinsApi,
} from "@/api/inventory"
import { Field, Modal } from "@/pages/admin/components/common"

interface CabinRow {
  cabin_id: string
  qty: string
  notes: string
}

export function ItemCabinsModal({
  item,
  defaultWarehouseId,
  onClose,
}: {
  item: { id: string; name: string }
  defaultWarehouseId?: string
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [warehouseId, setWarehouseId] = useState(defaultWarehouseId || "")
  const [rows, setRows] = useState<CabinRow[]>([])
  const [error, setError] = useState("")

  const { data: warehouses = [] } = useQuery({
    queryKey: ["inv-warehouses-all"],
    queryFn: () => getWarehousesApi(),
  })

  // Pick first warehouse if none selected
  useEffect(() => {
    if (!warehouseId && warehouses.length > 0) {
      setWarehouseId(defaultWarehouseId || warehouses[0].id)
    }
  }, [warehouses, warehouseId, defaultWarehouseId])

  const { data: cabins = [] } = useQuery<WarehouseCabin[]>({
    queryKey: ["inv-warehouse-cabins", warehouseId],
    queryFn: () => getWarehouseCabinsApi(warehouseId),
    enabled: !!warehouseId,
  })

  const { data: currentAssignments = [], isLoading: loadingAssignments } = useQuery<
    ItemCabinAssignment[]
  >({
    queryKey: ["inv-item-cabins", item.id, warehouseId],
    queryFn: () => getItemCabinsApi(item.id, warehouseId),
    enabled: !!warehouseId,
  })

  useEffect(() => {
    if (currentAssignments) {
      setRows(
        currentAssignments.map((a) => ({
          cabin_id: a.cabin_id,
          qty: a.qty != null ? String(a.qty) : "",
          notes: a.notes ?? "",
        })),
      )
    }
  }, [currentAssignments])

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = rows
        .filter((r) => r.cabin_id)
        .map((r, idx) => ({
          cabin_id: r.cabin_id,
          qty: r.qty ? parseInt(r.qty, 10) : null,
          notes: r.notes.trim() || null,
          is_primary: idx === 0,
        }))
      return setItemCabinsApi(item.id, warehouseId, payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-stock"] })
      queryClient.invalidateQueries({ queryKey: ["inv-warehouse-cabins", warehouseId] })
      queryClient.invalidateQueries({ queryKey: ["inv-item-cabins", item.id, warehouseId] })
      onClose()
    },
    onError: (err: any) => {
      setError(err?.response?.data?.detail ?? "Could not save cabin assignments")
    },
  })

  const addRow = () => {
    const usedIds = new Set(rows.map((r) => r.cabin_id))
    const firstAvailable = cabins.find((c) => !usedIds.has(c.id))
    setRows((prev) => [
      ...prev,
      { cabin_id: firstAvailable ? firstAvailable.id : cabins[0]?.id || "", qty: "", notes: "" },
    ])
  }

  const updateRow = (index: number, patch: Partial<CabinRow>) => {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)))
  }

  const removeRow = (index: number) => {
    setRows((prev) => prev.filter((_, i) => i !== index))
  }

  const selectedWarehouse = warehouses.find((w) => w.id === warehouseId)

  return (
    <Modal
      title={`Cabin Placement · ${item.name}`}
      onClose={onClose}
      maxWidth="sm:max-w-lg max-w-lg"
    >
      <div className="flex flex-col gap-4">
        {error && (
          <p className="text-xs p-2.5 rounded-xl bg-red-50 dark:bg-red-950/30 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-900/50">
            {error}
          </p>
        )}

        {/* Warehouse Selector */}
        {warehouses.length > 1 && (
          <Field label="Warehouse">
            <select
              value={warehouseId}
              onChange={(e) => setWarehouseId(e.target.value)}
              className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm w-full cursor-pointer focus:outline-none focus:border-primary"
            >
              {warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </Field>
        )}

        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                <MapPin size={15} className="text-primary" />
                <span>Assigned Cabins</span>
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Specify which cabin(s) in {selectedWarehouse?.name ?? "the warehouse"} this component is stored in.
              </p>
            </div>
            {cabins.length > 0 && (
              <button
                type="button"
                onClick={addRow}
                className="inline-flex items-center gap-1 text-xs text-primary hover:underline font-medium cursor-pointer"
              >
                <Plus size={12} /> Add cabin
              </button>
            )}
          </div>

          {cabins.length === 0 ? (
            <div className="py-6 border border-dashed border-border rounded-xl text-center text-xs text-muted-foreground">
              <p>No cabins have been defined for {selectedWarehouse?.name ?? "this warehouse"} yet.</p>
              <p className="mt-1 text-[11px]">
                Create cabins in Warehouses settings or the layout view first.
              </p>
            </div>
          ) : loadingAssignments ? (
            <div className="py-6 text-center text-xs text-muted-foreground">
              Loading current assignments…
            </div>
          ) : rows.length === 0 ? (
            <div className="py-6 border border-dashed border-border rounded-xl text-center text-xs text-muted-foreground">
              <p>This item is currently unassigned to any cabin in this warehouse.</p>
              <button
                type="button"
                onClick={addRow}
                className="mt-2 inline-flex items-center gap-1 px-3 py-1.5 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:opacity-90 transition-opacity cursor-pointer"
              >
                <Plus size={12} /> Assign to a cabin
              </button>
            </div>
          ) : (
            <div className="flex flex-col gap-2.5 mt-1">
              {rows.map((row, idx) => (
                <div
                  key={idx}
                  className="p-2.5 rounded-xl border border-border bg-card/60 flex items-center gap-2 flex-wrap sm:flex-nowrap"
                >
                  <div className="w-full sm:w-44">
                    <select
                      value={row.cabin_id}
                      onChange={(e) => updateRow(idx, { cabin_id: e.target.value })}
                      className="h-8 px-2.5 text-xs border border-border bg-background text-foreground rounded-lg w-full cursor-pointer"
                    >
                      <option value="">Select cabin…</option>
                      {cabins.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="w-24 shrink-0">
                    <input
                      type="number"
                      min="0"
                      value={row.qty}
                      onChange={(e) => updateRow(idx, { qty: e.target.value })}
                      placeholder="Qty (opt)"
                      className="h-8 px-2.5 text-xs border border-border bg-background text-foreground rounded-lg w-full font-mono"
                    />
                  </div>

                  <div className="flex-1 min-w-[100px]">
                    <input
                      type="text"
                      value={row.notes}
                      onChange={(e) => updateRow(idx, { notes: e.target.value })}
                      placeholder="Note / Shelf (opt)"
                      className="h-8 px-2.5 text-xs border border-border bg-background text-foreground rounded-lg w-full"
                    />
                  </div>

                  <button
                    type="button"
                    onClick={() => removeRow(idx)}
                    className="p-1.5 text-muted-foreground hover:text-red-600 rounded-lg shrink-0 transition-colors cursor-pointer"
                    title="Remove"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 border border-border rounded-xl text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || cabins.length === 0}
            className="h-9 px-4 bg-primary text-primary-foreground text-xs font-medium rounded-xl hover:opacity-90 disabled:opacity-50 transition-opacity cursor-pointer"
          >
            {saveMutation.isPending ? "Saving…" : "Save Assignments"}
          </button>
        </div>
      </div>
    </Modal>
  )
}
