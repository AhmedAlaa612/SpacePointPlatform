import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ImagePlus,
  MapPin,
  Package,
  Pencil,
  Plus,
  Trash2,
  Upload,
} from "lucide-react"
import type { Warehouse, WarehouseCabin } from "@/types/inventory"
import {
  createWarehouseCabinApi,
  deleteWarehouseCabinApi,
  getWarehouseCabinsApi,
  getStockApi,
  removeWarehouseImageApi,
  setWarehouseImageApi,
  updateWarehouseCabinApi,
} from "@/api/inventory"
import { Modal } from "@/pages/admin/components/common"
import { cn } from "@/lib/utils"

export function WarehouseCabinsModal({
  warehouse,
  onClose,
}: {
  warehouse: Warehouse
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [selectedCabinId, setSelectedCabinId] = useState<string | null>(null)
  const [newCabinName, setNewCabinName] = useState("")
  const [newCabinDesc, setNewCabinDesc] = useState("")
  const [editingCabin, setEditingCabin] = useState<WarehouseCabin | null>(null)
  const [error, setError] = useState("")

  const { data: cabins = [], isLoading: loadingCabins } = useQuery({
    queryKey: ["inv-warehouse-cabins", warehouse.id],
    queryFn: () => getWarehouseCabinsApi(warehouse.id),
  })

  const { data: stock = [] } = useQuery({
    queryKey: ["inv-stock", "warehouse", warehouse.id],
    queryFn: () => getStockApi({ warehouse_id: warehouse.id }),
  })

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["inv-warehouse-cabins", warehouse.id] })
    queryClient.invalidateQueries({ queryKey: ["inv-warehouses-all"] })
    queryClient.invalidateQueries({ queryKey: ["inv-warehouses"] })
    queryClient.invalidateQueries({ queryKey: ["inv-stock"] })
  }

  const imageUploadMutation = useMutation({
    mutationFn: (file: File) => setWarehouseImageApi(warehouse.id, file),
    onSuccess: (updatedWh) => {
      warehouse.image_url = updatedWh.image_url
      invalidateAll()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not upload image"),
  })

  const imageRemoveMutation = useMutation({
    mutationFn: () => removeWarehouseImageApi(warehouse.id),
    onSuccess: () => {
      warehouse.image_url = null
      invalidateAll()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not remove image"),
  })

  const createCabinMutation = useMutation({
    mutationFn: () =>
      createWarehouseCabinApi(warehouse.id, {
        name: newCabinName.trim(),
        description: newCabinDesc.trim() || undefined,
      }),
    onSuccess: (newC) => {
      setNewCabinName("")
      setNewCabinDesc("")
      setSelectedCabinId(newC.id)
      setError("")
      invalidateAll()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not create cabin"),
  })

  const updateCabinMutation = useMutation({
    mutationFn: ({ cabinId, data }: { cabinId: string; data: Partial<WarehouseCabin> }) =>
      updateWarehouseCabinApi(warehouse.id, cabinId, data),
    onSuccess: () => {
      setEditingCabin(null)
      setError("")
      invalidateAll()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not update cabin"),
  })

  const deleteCabinMutation = useMutation({
    mutationFn: (cabinId: string) => deleteWarehouseCabinApi(warehouse.id, cabinId),
    onSuccess: (_, cabinId) => {
      if (selectedCabinId === cabinId) setSelectedCabinId(null)
      setError("")
      invalidateAll()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not delete cabin"),
  })

  // Handle placing a pin on the image
  const handleImageClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!selectedCabinId) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * 100
    const y = ((e.clientY - rect.top) / rect.height) * 100
    const roundedX = Math.round(x * 10) / 10
    const roundedY = Math.round(y * 10) / 10

    updateCabinMutation.mutate({
      cabinId: selectedCabinId,
      data: { pin_x: roundedX, pin_y: roundedY },
    })
  }

  const selectedCabin = cabins.find((c) => c.id === selectedCabinId)

  // Items sitting in the selected cabin
  const itemsInSelectedCabin = selectedCabin
    ? stock.filter((s) => s.cabins?.some((c) => c.cabin_id === selectedCabin.id))
    : []

  return (
    <Modal
      title={`Cabins & Spatial Layout · ${warehouse.name}`}
      onClose={onClose}
      maxWidth="sm:max-w-4xl max-w-4xl"
    >
      <div className="flex flex-col gap-5">
        {error && (
          <p className="text-xs p-2.5 rounded-xl bg-red-50 dark:bg-red-950/30 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-900/50">
            {error}
          </p>
        )}

        {/* 1. Warehouse Layout Image Section */}
        <div className="rounded-2xl border border-border bg-card/60 p-4 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                <MapPin size={16} className="text-primary" /> Visual Warehouse Layout / Photo
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Upload a photo of your shelves or floorplan. Select a cabin below, then click on the photo to drop its pin.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) imageUploadMutation.mutate(file)
                }}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={imageUploadMutation.isPending}
                className="inline-flex items-center gap-1.5 h-8 px-3 text-xs font-medium border border-border rounded-xl bg-background hover:bg-muted text-foreground transition-colors cursor-pointer"
              >
                <Upload size={13} /> {warehouse.image_url ? "Replace photo" : "Upload photo"}
              </button>
              {warehouse.image_url && (
                <button
                  type="button"
                  onClick={() => imageRemoveMutation.mutate()}
                  disabled={imageRemoveMutation.isPending}
                  className="inline-flex items-center gap-1 h-8 px-2.5 text-xs font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 rounded-xl transition-colors cursor-pointer"
                  title="Remove photo"
                >
                  <Trash2 size={13} /> Remove
                </button>
              )}
            </div>
          </div>

          {/* Photo viewer with interactive pins */}
          {warehouse.image_url ? (
            <div className="flex flex-col gap-2">
              <div
                onClick={handleImageClick}
                className={cn(
                  "relative w-full max-h-[420px] rounded-xl overflow-hidden border border-border bg-black/5 dark:bg-black/30 flex items-center justify-center select-none",
                  selectedCabinId ? "cursor-crosshair ring-2 ring-primary/40" : "cursor-default",
                )}
              >
                <img
                  src={warehouse.image_url}
                  alt={warehouse.name}
                  className="max-h-[420px] w-full object-contain pointer-events-none"
                />

                {/* Pins */}
                {cabins.map((c) => {
                  if (c.pin_x === null || c.pin_y === null || c.pin_x === undefined || c.pin_y === undefined) return null
                  const isSelected = c.id === selectedCabinId
                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        setSelectedCabinId(c.id)
                      }}
                      style={{ left: `${c.pin_x}%`, top: `${c.pin_y}%` }}
                      className={cn(
                        "absolute -translate-x-1/2 -translate-y-1/2 flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold shadow-md transition-all cursor-pointer z-10",
                        isSelected
                          ? "bg-primary text-primary-foreground scale-110 ring-2 ring-white dark:ring-black"
                          : "bg-background/95 text-foreground hover:bg-primary/20 border border-border backdrop-blur-xs",
                      )}
                      title={`${c.name}${c.description ? ` · ${c.description}` : ""}`}
                    >
                      <MapPin size={11} className={isSelected ? "text-primary-foreground fill-current" : "text-primary"} />
                      <span>{c.name}</span>
                    </button>
                  )
                })}
              </div>

              <div className="flex items-center justify-between text-xs text-muted-foreground px-1">
                {selectedCabin ? (
                  <span>
                    Active: <strong className="text-foreground">{selectedCabin.name}</strong> · Click on the photo to reposition its pin.
                  </span>
                ) : (
                  <span>Click a cabin below to highlight or set its pin on this photo.</span>
                )}
                {selectedCabin && (selectedCabin.pin_x !== null && selectedCabin.pin_x !== undefined) && (
                  <button
                    type="button"
                    onClick={() =>
                      updateCabinMutation.mutate({
                        cabinId: selectedCabin.id,
                        data: { pin_x: null, pin_y: null },
                      })
                    }
                    className="text-muted-foreground hover:text-red-600 transition-colors cursor-pointer"
                  >
                    Clear pin
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div
              onClick={() => fileInputRef.current?.click()}
              className="py-10 border border-dashed border-border rounded-xl flex flex-col items-center justify-center gap-2 hover:bg-muted/40 transition-colors cursor-pointer text-muted-foreground"
            >
              <ImagePlus size={32} className="text-muted-foreground/60" />
              <p className="text-sm font-medium text-foreground">Add warehouse or cabin layout photo</p>
              <p className="text-xs text-muted-foreground">Click to upload a picture of the shelves or floor layout.</p>
            </div>
          )}
        </div>

        {/* 2. Cabins Management List */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Left col: Cabins list */}
          <div className="flex flex-col gap-3">
            <p className="text-sm font-semibold text-foreground">Defined Cabins / Shelves ({cabins.length})</p>

            {/* Inline add cabin form */}
            <div className="flex items-center gap-2">
              <input
                value={newCabinName}
                onChange={(e) => setNewCabinName(e.target.value)}
                placeholder="Cabin / Rack name (e.g. Cabin 1)"
                className="h-9 flex-1 px-3 border border-border bg-background text-foreground rounded-xl text-xs"
              />
              <input
                value={newCabinDesc}
                onChange={(e) => setNewCabinDesc(e.target.value)}
                placeholder="Description (optional)"
                className="h-9 flex-1 px-3 border border-border bg-background text-foreground rounded-xl text-xs"
              />
              <button
                type="button"
                onClick={() => createCabinMutation.mutate()}
                disabled={!newCabinName.trim() || createCabinMutation.isPending}
                className="h-9 px-3 bg-primary text-primary-foreground text-xs font-medium rounded-xl hover:opacity-90 disabled:opacity-50 transition-colors shrink-0 cursor-pointer flex items-center gap-1"
              >
                <Plus size={13} /> Add
              </button>
            </div>

            {/* Cabins list items */}
            <div className="rounded-xl border border-border divide-y divide-border max-h-60 overflow-y-auto">
              {loadingCabins ? (
                <p className="p-4 text-xs text-muted-foreground text-center">Loading cabins…</p>
              ) : cabins.length === 0 ? (
                <p className="p-4 text-xs text-muted-foreground text-center">
                  No cabins created yet for this warehouse.
                </p>
              ) : (
                cabins.map((c) => {
                  const isSelected = c.id === selectedCabinId
                  const isEditing = editingCabin?.id === c.id

                  if (isEditing) {
                    return (
                      <div key={c.id} className="p-2.5 bg-muted/30 flex flex-col gap-2">
                        <div className="flex items-center gap-2">
                          <input
                            value={editingCabin.name}
                            onChange={(e) =>
                              setEditingCabin({ ...editingCabin, name: e.target.value })
                            }
                            className="h-8 flex-1 px-2 text-xs border border-border bg-background rounded-lg text-foreground"
                          />
                          <input
                            value={editingCabin.description ?? ""}
                            onChange={(e) =>
                              setEditingCabin({ ...editingCabin, description: e.target.value })
                            }
                            placeholder="Description"
                            className="h-8 flex-1 px-2 text-xs border border-border bg-background rounded-lg text-foreground"
                          />
                        </div>
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={() => setEditingCabin(null)}
                            className="h-7 px-2.5 text-xs text-muted-foreground hover:bg-muted rounded-lg"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              updateCabinMutation.mutate({
                                cabinId: c.id,
                                data: {
                                  name: editingCabin.name.trim(),
                                  description: editingCabin.description?.trim() || null,
                                },
                              })
                            }
                            disabled={!editingCabin.name.trim() || updateCabinMutation.isPending}
                            className="h-7 px-3 bg-primary text-primary-foreground text-xs font-medium rounded-lg"
                          >
                            Save
                          </button>
                        </div>
                      </div>
                    )
                  }

                  return (
                    <div
                      key={c.id}
                      onClick={() => setSelectedCabinId(c.id)}
                      className={cn(
                        "flex items-center justify-between gap-3 px-3 py-2 text-xs transition-colors cursor-pointer",
                        isSelected ? "bg-primary/10" : "hover:bg-muted/40",
                      )}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground truncate">{c.name}</span>
                          {c.pin_x !== null && c.pin_x !== undefined ? (
                            <span className="text-[10px] text-emerald-600 dark:text-emerald-400 flex items-center gap-0.5">
                              <MapPin size={9} /> Pinned
                            </span>
                          ) : (
                            <span className="text-[10px] text-muted-foreground/70 italic">No pin</span>
                          )}
                        </div>
                        {c.description && (
                          <p className="text-[11px] text-muted-foreground truncate mt-0.5">
                            {c.description}
                          </p>
                        )}
                      </div>

                      <div className="flex items-center gap-1.5 shrink-0" onClick={(e) => e.stopPropagation()}>
                        <span className="text-[11px] px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground">
                          {c.item_count ?? 0} item{(c.item_count ?? 0) === 1 ? "" : "s"}
                        </span>
                        <button
                          type="button"
                          onClick={() => setEditingCabin(c)}
                          className="p-1 text-muted-foreground hover:text-foreground rounded-lg"
                          title="Rename"
                        >
                          <Pencil size={12} />
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            if (confirm(`Delete cabin "${c.name}"? Items inside will become unassigned.`)) {
                              deleteCabinMutation.mutate(c.id)
                            }
                          }}
                          className="p-1 text-muted-foreground hover:text-red-600 rounded-lg"
                          title="Delete cabin"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>

          {/* Right col: Items inside selected cabin */}
          <div className="flex flex-col gap-3 rounded-xl border border-border bg-card/40 p-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                <Package size={15} className="text-primary" />
                {selectedCabin ? `Items in ${selectedCabin.name}` : "Cabin Contents"}
              </p>
              {selectedCabin && (
                <span className="text-xs text-muted-foreground">
                  {itemsInSelectedCabin.length} component{itemsInSelectedCabin.length === 1 ? "" : "s"}
                </span>
              )}
            </div>

            {selectedCabin ? (
              itemsInSelectedCabin.length === 0 ? (
                <div className="py-8 text-center text-muted-foreground text-xs">
                  <p>No items assigned to {selectedCabin.name} yet.</p>
                  <p className="mt-1 text-[11px]">
                    You can assign items to this cabin in the Stock view or Stocktake modal.
                  </p>
                </div>
              ) : (
                <div className="divide-y divide-border max-h-60 overflow-y-auto">
                  {itemsInSelectedCabin.map((item) => {
                    const assign = item.cabins?.find((c) => c.cabin_id === selectedCabin.id)
                    return (
                      <div key={item.item_id} className="py-2 flex items-center justify-between text-xs">
                        <div className="min-w-0 pr-2">
                          <p className="font-medium text-foreground truncate">{item.item_name}</p>
                          {assign?.notes && (
                            <p className="text-[10px] text-muted-foreground truncate">{assign.notes}</p>
                          )}
                        </div>
                        <div className="text-right shrink-0">
                          <span className="font-mono font-bold text-foreground">
                            {assign?.qty !== null && assign?.qty !== undefined ? `${assign.qty} pcs` : `${item.qty} pcs`}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )
            ) : (
              <p className="py-8 text-center text-muted-foreground text-xs">
                Select a cabin to view the items stored inside it.
              </p>
            )}
          </div>
        </div>

        <div className="flex justify-end pt-2 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
          >
            Done
          </button>
        </div>
      </div>
    </Modal>
  )
}
