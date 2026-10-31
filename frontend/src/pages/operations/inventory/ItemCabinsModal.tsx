import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MapPin, Plus, Trash2 } from "lucide-react"
import type { ItemCabinAssignment, StockLevel, WarehouseBox, WarehouseCabin } from "@/types/inventory"
import {
  getItemCabinsApi,
  getStockApi,
  getWarehouseBoxesApi,
  getWarehouseCabinsApi,
  getWarehousesApi,
  setItemCabinsApi,
} from "@/api/inventory"
import { Field, Modal } from "@/pages/admin/components/common"

interface PlacementRow {
  cabin_id: string
  box_id: string
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
  const [placements, setPlacements] = useState<PlacementRow[]>([])
  const [error, setError] = useState("")

  const { data: warehouses } = useQuery({
    queryKey: ["inv-warehouses-all"],
    queryFn: () => getWarehousesApi(),
  })

  useEffect(() => {
    if (!warehouseId && warehouses && warehouses.length > 0) {
      setWarehouseId(defaultWarehouseId || warehouses[0].id)
    }
  }, [warehouses, warehouseId, defaultWarehouseId])

  const { data: stockLevels } = useQuery<StockLevel[]>({
    queryKey: ["inv-stock", "warehouse", warehouseId, "item", item.id],
    queryFn: () => getStockApi({ warehouse_id: warehouseId, item_id: item.id }),
    enabled: !!warehouseId && !!item.id,
  })

  const { data: cabins = [] } = useQuery<WarehouseCabin[]>({
    queryKey: ["inv-warehouse-cabins", warehouseId],
    queryFn: () => getWarehouseCabinsApi(warehouseId),
    enabled: !!warehouseId,
  })

  const { data: boxes = [] } = useQuery<WarehouseBox[]>({
    queryKey: ["inv-warehouse-boxes", warehouseId],
    queryFn: () => getWarehouseBoxesApi(warehouseId),
    enabled: !!warehouseId,
  })

  const { data: currentAssignments, isLoading: loadingAssignments } = useQuery<ItemCabinAssignment[]>({
    queryKey: ["inv-item-cabins", warehouseId, item.id],
    queryFn: () => getItemCabinsApi(warehouseId, item.id),
    enabled: !!warehouseId,
  })

  useEffect(() => {
    if (currentAssignments) {
      setPlacements(
        currentAssignments.map((a) => ({
          cabin_id: a.cabin_id,
          box_id: a.box_id ?? "",
          notes: a.notes ?? "",
        }))
      )
    }
  }, [currentAssignments])

  const addPlacement = () => {
    const defaultCabinId = cabins[0]?.id ?? ""
    setPlacements((prev) => [...prev, { cabin_id: defaultCabinId, box_id: "", notes: "" }])
  }

  const updatePlacement = (index: number, patch: Partial<PlacementRow>) => {
    setPlacements((prev) => {
      const next = [...prev]
      next[index] = { ...next[index], ...patch }
      // If cabin changed, clear box if it doesn't belong to the new cabin
      if (patch.cabin_id && patch.cabin_id !== prev[index].cabin_id) {
        const cabinBoxes = boxes.filter((b) => b.cabin_id === patch.cabin_id)
        if (!cabinBoxes.some((b) => b.id === next[index].box_id)) {
          next[index].box_id = ""
        }
      }
      return next
    })
  }

  const removePlacement = (index: number) => {
    setPlacements((prev) => prev.filter((_, i) => i !== index))
  }

  const saveMutation = useMutation({
    mutationFn: () => {
      const valid = placements
        .filter((p) => !!p.cabin_id)
        .map((p) => ({
          cabin_id: p.cabin_id,
          box_id: p.box_id || null,
          notes: p.notes.trim() || null,
        }))
      return setItemCabinsApi(warehouseId, item.id, valid)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-stock"] })
      queryClient.invalidateQueries({ queryKey: ["inv-warehouse-cabins", warehouseId] })
      queryClient.invalidateQueries({ queryKey: ["inv-warehouse-boxes", warehouseId] })
      queryClient.invalidateQueries({ queryKey: ["inv-item-cabins"] })
      onClose()
    },
    onError: (err: any) => {
      setError(err?.response?.data?.detail ?? "Could not save cabin assignment")
    },
  })

  const currentWarehouseStock = stockLevels?.[0]?.qty

  return (
    <Modal
      title={`Placement · ${item.name}`}
      onClose={onClose}
      maxWidth="sm:max-w-xl max-w-xl"
    >
      <div className="flex flex-col gap-4">
        {error && (
          <p className="text-xs p-2.5 rounded-xl bg-red-50 dark:bg-red-950/30 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-900/50">
            {error}
          </p>
        )}

        {warehouses && warehouses.length > 1 && (
          <Field label="Warehouse">
            <select
              value={warehouseId}
              onChange={(e) => setWarehouseId(e.target.value)}
              className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-xs w-full cursor-pointer focus:outline-none focus:border-primary"
            >
              {warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </Field>
        )}

        <div className="p-3 rounded-xl bg-muted/40 border border-border flex items-center justify-between gap-2 text-xs">
          <div>
            <span className="text-muted-foreground">Warehouse stock: </span>
            <strong className="text-foreground">
              {currentWarehouseStock !== undefined ? `${currentWarehouseStock} pcs` : "0 pcs"}
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground">Placements: </span>
            <strong className="text-primary">{placements.length}</strong>
          </div>
        </div>

        <div className="flex flex-col gap-2.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
              <MapPin size={14} className="text-primary" /> Placements
            </span>
            <button
              type="button"
              onClick={addPlacement}
              disabled={cabins.length === 0}
              className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 bg-primary text-primary-foreground rounded-lg hover:opacity-90 disabled:opacity-50 cursor-pointer"
            >
              <Plus size={12} /> Add placement
            </button>
          </div>

          {cabins.length === 0 ? (
            <p className="py-6 border border-dashed border-border rounded-xl text-center text-xs text-muted-foreground">
              No cabins configured for this warehouse.
            </p>
          ) : loadingAssignments ? (
            <p className="py-6 text-center text-xs text-muted-foreground">Loading…</p>
          ) : placements.length === 0 ? (
            <p className="py-6 border border-dashed border-border rounded-xl text-center text-xs text-muted-foreground">
              Item is unassigned.
            </p>
          ) : (
            <div className="flex flex-col gap-2 max-h-72 overflow-y-auto pr-1">
              {placements.map((p, idx) => {
                const cabinBoxes = boxes.filter((b) => b.cabin_id === p.cabin_id)
                return (
                  <div
                    key={idx}
                    className="p-2.5 rounded-xl border border-border bg-card/60 flex flex-col sm:flex-row sm:items-center gap-2"
                  >
                    <div className="grid grid-cols-2 gap-2 flex-1 w-full sm:w-auto">
                      <select
                        value={p.cabin_id}
                        onChange={(e) => updatePlacement(idx, { cabin_id: e.target.value })}
                        className="h-8 px-2 border border-border bg-background text-foreground rounded-lg text-xs w-full"
                      >
                        {cabins.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </select>

                      <select
                        value={p.box_id}
                        onChange={(e) => updatePlacement(idx, { box_id: e.target.value })}
                        className="h-8 px-2 border border-border bg-background text-foreground rounded-lg text-xs w-full"
                      >
                        <option value="">Loose in cabin</option>
                        {cabinBoxes.map((b) => (
                          <option key={b.id} value={b.id}>
                            📦 {b.name}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="flex items-center gap-2 w-full sm:w-auto">
                      <input
                        type="text"
                        value={p.notes}
                        onChange={(e) => updatePlacement(idx, { notes: e.target.value })}
                        placeholder="Note (optional)"
                        className="h-8 px-2 text-xs border border-border bg-background text-foreground rounded-lg flex-1 sm:w-32"
                      />

                      <button
                        type="button"
                        onClick={() => removePlacement(idx)}
                        className="p-1.5 text-muted-foreground hover:text-red-600 rounded-lg cursor-pointer shrink-0"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="h-8 px-3 border border-border rounded-xl text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || cabins.length === 0}
            className="h-8 px-4 bg-primary text-primary-foreground text-xs font-semibold rounded-xl hover:opacity-90 disabled:opacity-50 transition-opacity cursor-pointer"
          >
            {saveMutation.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </Modal>
  )
}
