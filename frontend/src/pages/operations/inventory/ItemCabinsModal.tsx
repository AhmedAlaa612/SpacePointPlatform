import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MapPin } from "lucide-react"
import type { ItemCabinAssignment, StockLevel, WarehouseCabin } from "@/types/inventory"
import {
  getItemCabinsApi,
  getStockApi,
  getWarehouseCabinsApi,
  getWarehousesApi,
  setItemCabinsApi,
} from "@/api/inventory"
import { Field, Modal } from "@/pages/admin/components/common"

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
  const [cabinId, setCabinId] = useState("")
  const [notes, setNotes] = useState("")
  const [error, setError] = useState("")

  const { data: warehouses } = useQuery({
    queryKey: ["inv-warehouses-all"],
    queryFn: () => getWarehousesApi(),
  })

  // Pick first warehouse if none selected
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

  const { data: cabins } = useQuery<WarehouseCabin[]>({
    queryKey: ["inv-warehouse-cabins", warehouseId],
    queryFn: () => getWarehouseCabinsApi(warehouseId),
    enabled: !!warehouseId,
  })

  const { data: currentAssignments, isLoading: loadingAssignments } = useQuery<
    ItemCabinAssignment[]
  >({
    queryKey: ["inv-item-cabins", warehouseId, item.id],
    queryFn: () => getItemCabinsApi(warehouseId, item.id),
    enabled: !!warehouseId,
  })

  // Reset selection when warehouse changes
  useEffect(() => {
    setCabinId("")
    setNotes("")
  }, [warehouseId])

  useEffect(() => {
    if (currentAssignments) {
      setCabinId(currentAssignments[0]?.cabin_id ?? "")
      setNotes(currentAssignments[0]?.notes ?? "")
    }
  }, [currentAssignments])

  const cabinList = cabins ?? []
  const warehouseList = warehouses ?? []

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = cabinId
        ? [{ cabin_id: cabinId, notes: notes.trim() || null }]
        : []
      return setItemCabinsApi(warehouseId, item.id, payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-stock"] })
      queryClient.invalidateQueries({ queryKey: ["inv-warehouse-cabins", warehouseId] })
      queryClient.invalidateQueries({ queryKey: ["inv-item-cabins"] })
      onClose()
    },
    onError: (err: any) => {
      setError(err?.response?.data?.detail ?? "Could not save cabin assignment")
    },
  })

  const selectedWarehouse = warehouseList.find((w) => w.id === warehouseId)
  const currentWarehouseStock = stockLevels?.[0]?.qty
  const isAssigned = (currentAssignments?.length ?? 0) > 0

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
        {warehouseList.length > 1 && (
          <Field label="Warehouse">
            <select
              value={warehouseId}
              onChange={(e) => setWarehouseId(e.target.value)}
              className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm w-full cursor-pointer focus:outline-none focus:border-primary"
            >
              {warehouseList.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </Field>
        )}

        {/* Stock status — quantity lives on stock, cabin is location only */}
        <div className="p-3 rounded-xl bg-muted/40 border border-border flex items-center justify-between gap-2 text-xs">
          <div>
            <span className="text-muted-foreground">Warehouse stock: </span>
            <strong className="text-foreground">
              {currentWarehouseStock !== undefined ? `${currentWarehouseStock} pcs` : "0 pcs (uncounted)"}
            </strong>
          </div>
          <div>
            <span className="text-muted-foreground">Cabin: </span>
            <strong className="text-primary">
              {isAssigned ? (currentAssignments?.[0]?.cabin_name ?? "Assigned") : "Unassigned"}
            </strong>
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <p className="text-sm font-semibold text-foreground flex items-center gap-1.5">
            <MapPin size={15} className="text-primary" />
            <span>Home cabin</span>
          </p>
          <p className="text-xs text-muted-foreground -mt-1">
            One home per item in {selectedWarehouse?.name ?? "the warehouse"}. Counting stock never changes this — moving it changes where it lives, not how many there are.
          </p>

          {cabinList.length === 0 ? (
            <div className="py-6 border border-dashed border-border rounded-xl text-center text-xs text-muted-foreground">
              <p>No cabins have been defined for {selectedWarehouse?.name ?? "this warehouse"} yet.</p>
              <p className="mt-1 text-[11px]">
                Create cabins in Warehouses settings or the layout view first.
              </p>
            </div>
          ) : loadingAssignments ? (
            <div className="py-6 text-center text-xs text-muted-foreground">
              Loading current assignment…
            </div>
          ) : (
            <div className="flex flex-col gap-2.5 mt-1">
              <Field label="Cabin">
                <select
                  value={cabinId}
                  onChange={(e) => setCabinId(e.target.value)}
                  className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm w-full cursor-pointer focus:outline-none focus:border-primary"
                >
                  <option value="">Unassigned — no cabin</option>
                  {cabinList.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Note / shelf (optional)">
                <input
                  type="text"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Top tray, back shelf…"
                  className="h-9 px-3 text-sm border border-border bg-background text-foreground rounded-xl w-full"
                />
              </Field>
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
            disabled={saveMutation.isPending || cabinList.length === 0}
            className="h-9 px-4 bg-primary text-primary-foreground text-xs font-medium rounded-xl hover:opacity-90 disabled:opacity-50 transition-opacity cursor-pointer"
          >
            {saveMutation.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </Modal>
  )
}
