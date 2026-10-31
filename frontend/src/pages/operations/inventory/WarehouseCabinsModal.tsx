import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Boxes,
  Crop as CropIcon,
  ImagePlus,
  MapPin,
  Package,
  Pencil,
  Plus,
  Trash2,
  Upload,
} from "lucide-react"
import type { Warehouse, WarehouseBox, WarehouseCabin } from "@/types/inventory"
import {
  createWarehouseBoxApi,
  createWarehouseCabinApi,
  deleteWarehouseBoxApi,
  deleteWarehouseCabinApi,
  getWarehouseBoxesApi,
  getWarehouseCabinsApi,
  getStockApi,
  removeWarehouseImageApi,
  setWarehouseImageApi,
  updateWarehouseBoxApi,
  updateWarehouseCabinApi,
} from "@/api/inventory"
import { Modal } from "@/pages/admin/components/common"
import { ImageCropModal } from "@/components/ui/ImageCropModal"
import { BoxItemsModal } from "./BoxItemsModal"
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
  const [selectedBoxId, setSelectedBoxId] = useState<string | null>(null)

  const [newCabinName, setNewCabinName] = useState("")
  const [newCabinDesc, setNewCabinDesc] = useState("")
  const [editingCabin, setEditingCabin] = useState<WarehouseCabin | null>(null)

  const [newBoxName, setNewBoxName] = useState("")
  const [newBoxDesc, setNewBoxDesc] = useState("")
  const [editingBox, setEditingBox] = useState<WarehouseBox | null>(null)
  const [managingBoxItems, setManagingBoxItems] = useState<WarehouseBox | null>(null)

  const [error, setError] = useState("")
  const [localImageUrl, setLocalImageUrl] = useState<string | null | undefined>(warehouse.image_url)
  const [cropSrc, setCropSrc] = useState<string | null>(null)
  const [cropOpen, setCropOpen] = useState(false)

  const activeImageUrl = localImageUrl !== undefined ? localImageUrl : warehouse.image_url

  const { data: cabins = [], isLoading: loadingCabins } = useQuery({
    queryKey: ["inv-warehouse-cabins", warehouse.id],
    queryFn: () => getWarehouseCabinsApi(warehouse.id),
  })

  const { data: boxes = [] } = useQuery({
    queryKey: ["inv-warehouse-boxes", warehouse.id],
    queryFn: () => getWarehouseBoxesApi(warehouse.id),
  })

  const { data: stock = [] } = useQuery({
    queryKey: ["inv-stock", "warehouse", warehouse.id],
    queryFn: () => getStockApi({ warehouse_id: warehouse.id }),
  })

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["inv-warehouse-cabins", warehouse.id] })
    queryClient.invalidateQueries({ queryKey: ["inv-warehouse-boxes", warehouse.id] })
    queryClient.invalidateQueries({ queryKey: ["inv-warehouses-all"] })
    queryClient.invalidateQueries({ queryKey: ["inv-warehouses"] })
    queryClient.invalidateQueries({ queryKey: ["inv-stock"] })
  }

  const imageUploadMutation = useMutation({
    mutationFn: (file: File) => setWarehouseImageApi(warehouse.id, file),
    onSuccess: (updatedWh) => {
      warehouse.image_url = updatedWh.image_url
      setLocalImageUrl(updatedWh.image_url)
      invalidateAll()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not upload image"),
  })

  const imageRemoveMutation = useMutation({
    mutationFn: () => removeWarehouseImageApi(warehouse.id),
    onSuccess: () => {
      warehouse.image_url = null
      setLocalImageUrl(null)
      invalidateAll()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not remove image"),
  })

  const handleFilePicked = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      const reader = new FileReader()
      reader.onload = () => {
        if (typeof reader.result === "string") {
          setCropSrc(reader.result)
          setCropOpen(true)
        }
      }
      reader.readAsDataURL(file)
    }
    e.target.value = ""
  }

  const handleCropExisting = async () => {
    if (!activeImageUrl) return
    try {
      const res = await fetch(activeImageUrl)
      const blob = await res.blob()
      const reader = new FileReader()
      reader.onload = () => {
        if (typeof reader.result === "string") {
          setCropSrc(reader.result)
          setCropOpen(true)
        }
      }
      reader.readAsDataURL(blob)
    } catch {
      setCropSrc(activeImageUrl)
      setCropOpen(true)
    }
  }

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

  const createBoxMutation = useMutation({
    mutationFn: () => {
      if (!selectedCabinId) throw new Error("Select a cabin first")
      return createWarehouseBoxApi(warehouse.id, {
        cabin_id: selectedCabinId,
        name: newBoxName.trim(),
        description: newBoxDesc.trim() || undefined,
      })
    },
    onSuccess: (newB) => {
      setNewBoxName("")
      setNewBoxDesc("")
      setSelectedBoxId(newB.id)
      setError("")
      invalidateAll()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not create box"),
  })

  const updateBoxMutation = useMutation({
    mutationFn: ({ boxId, data }: { boxId: string; data: Partial<WarehouseBox> }) =>
      updateWarehouseBoxApi(warehouse.id, boxId, data),
    onSuccess: () => {
      setEditingBox(null)
      setError("")
      invalidateAll()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not update box"),
  })

  const deleteBoxMutation = useMutation({
    mutationFn: (boxId: string) => deleteWarehouseBoxApi(warehouse.id, boxId),
    onSuccess: (_, boxId) => {
      if (selectedBoxId === boxId) setSelectedBoxId(null)
      setError("")
      invalidateAll()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not delete box"),
  })

  const handleImageClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!selectedCabinId) return
    const rect = e.currentTarget.getBoundingClientRect()
    if (rect.width === 0 || rect.height === 0) return
    const rawX = ((e.clientX - rect.left) / rect.width) * 100
    const rawY = ((e.clientY - rect.top) / rect.height) * 100
    const clampedX = Math.max(0, Math.min(100, rawX))
    const clampedY = Math.max(0, Math.min(100, rawY))
    const roundedX = Math.round(clampedX * 10) / 10
    const roundedY = Math.round(clampedY * 10) / 10

    updateCabinMutation.mutate({
      cabinId: selectedCabinId,
      data: { pin_x: roundedX, pin_y: roundedY },
    })
  }

  const selectedCabin = cabins.find((c) => c.id === selectedCabinId)
  const cabinBoxes = selectedCabin ? boxes.filter((b) => b.cabin_id === selectedCabin.id) : []
  const selectedBox = boxes.find((b) => b.id === selectedBoxId)

  // Items sitting in the selected cabin
  const itemsInSelectedCabin = selectedCabin
    ? stock.filter((s) => s.cabins?.some((c) => c.cabin_id === selectedCabin.id))
    : []

  // Items filtered by box if box selected, otherwise all in cabin
  const displayedItems = selectedBox
    ? itemsInSelectedCabin.filter((s) => s.cabins?.some((c) => c.box_id === selectedBox.id))
    : itemsInSelectedCabin

  return (
    <Modal
      title={`Cabins & Boxes · ${warehouse.name}`}
      onClose={onClose}
      maxWidth="sm:max-w-5xl max-w-5xl"
    >
      <div className="flex flex-col gap-4">
        {error && (
          <p className="text-xs p-2.5 rounded-xl bg-red-50 dark:bg-red-950/30 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-900/50">
            {error}
          </p>
        )}

        {/* 1. Warehouse Layout Image Section */}
        <div className="rounded-2xl border border-border bg-card/60 p-3 flex flex-col gap-2.5">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
              <MapPin size={14} className="text-primary" /> Warehouse Layout
            </span>
            <div className="flex items-center gap-2 flex-wrap">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handleFilePicked}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={imageUploadMutation.isPending}
                className="inline-flex items-center gap-1.5 h-7 px-2.5 text-xs font-medium border border-border rounded-lg bg-background hover:bg-muted text-foreground transition-colors cursor-pointer"
              >
                <Upload size={12} /> {activeImageUrl ? "Replace photo" : "Upload photo"}
              </button>
              {activeImageUrl && (
                <button
                  type="button"
                  onClick={handleCropExisting}
                  disabled={imageUploadMutation.isPending}
                  className="inline-flex items-center gap-1.5 h-7 px-2.5 text-xs font-medium border border-border rounded-lg bg-background hover:bg-muted text-foreground transition-colors cursor-pointer"
                >
                  <CropIcon size={12} /> Crop
                </button>
              )}
              {activeImageUrl && (
                <button
                  type="button"
                  onClick={() => imageRemoveMutation.mutate()}
                  disabled={imageRemoveMutation.isPending}
                  className="inline-flex items-center gap-1 h-7 px-2 text-xs font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 rounded-lg transition-colors cursor-pointer"
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          </div>

          {activeImageUrl ? (
            <div className="flex flex-col gap-1.5">
              <div className="w-full max-h-[340px] rounded-xl overflow-hidden border border-border bg-black/5 dark:bg-black/30 flex items-center justify-center select-none">
                <div
                  onClick={handleImageClick}
                  className={cn(
                    "relative inline-block max-h-[340px] max-w-full",
                    selectedCabinId ? "cursor-crosshair ring-2 ring-primary/40" : "cursor-default",
                  )}
                >
                  <img
                    src={activeImageUrl}
                    alt={warehouse.name}
                    className="max-h-[340px] max-w-full w-auto h-auto block pointer-events-none select-none"
                  />
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
                          setSelectedBoxId(null)
                        }}
                        style={{ left: `${c.pin_x}%`, top: `${c.pin_y}%` }}
                        className={cn(
                          "absolute -translate-x-1/2 -translate-y-1/2 flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold shadow-md transition-all cursor-pointer z-10 whitespace-nowrap",
                          isSelected
                            ? "bg-primary text-primary-foreground scale-110 ring-2 ring-white dark:ring-black"
                            : "bg-background/95 text-foreground hover:bg-primary/20 border border-border backdrop-blur-xs",
                        )}
                      >
                        <MapPin size={11} className={isSelected ? "text-primary-foreground fill-current" : "text-primary"} />
                        <span>{c.name}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
          ) : (
            <div
              onClick={() => fileInputRef.current?.click()}
              className="py-6 border border-dashed border-border rounded-xl flex flex-col items-center justify-center gap-1 hover:bg-muted/40 transition-colors cursor-pointer text-muted-foreground text-xs"
            >
              <ImagePlus size={20} className="text-muted-foreground/60" />
              <span className="font-semibold text-foreground">Upload warehouse layout photo</span>
            </div>
          )}
        </div>

        {/* 2. Cabins & Boxes Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {/* Col 1: Cabins list */}
          <div className="flex flex-col gap-2">
            <span className="text-xs font-bold text-foreground">Cabins ({cabins.length})</span>

            <div className="flex items-center gap-1.5">
              <input
                value={newCabinName}
                onChange={(e) => setNewCabinName(e.target.value)}
                placeholder="Cabin name"
                className="h-8 flex-1 px-2.5 border border-border bg-background text-foreground rounded-lg text-xs"
              />
              <button
                type="button"
                onClick={() => createCabinMutation.mutate()}
                disabled={!newCabinName.trim() || createCabinMutation.isPending}
                className="h-8 px-2.5 bg-primary text-primary-foreground text-xs font-semibold rounded-lg hover:opacity-90 disabled:opacity-50 transition-colors shrink-0 cursor-pointer flex items-center gap-1"
              >
                <Plus size={12} /> Add
              </button>
            </div>

            <div className="rounded-xl border border-border divide-y divide-border max-h-56 overflow-y-auto">
              {loadingCabins ? (
                <p className="p-3 text-xs text-muted-foreground text-center">Loading cabins…</p>
              ) : cabins.length === 0 ? (
                <p className="p-3 text-xs text-muted-foreground text-center">No cabins yet.</p>
              ) : (
                cabins.map((c) => {
                  const isSelected = c.id === selectedCabinId
                  const isEditing = editingCabin?.id === c.id

                  if (isEditing) {
                    return (
                      <div key={c.id} className="p-2 bg-muted/30 flex items-center gap-1.5">
                        <input
                          value={editingCabin.name}
                          onChange={(e) => setEditingCabin({ ...editingCabin, name: e.target.value })}
                          className="h-7 flex-1 px-2 text-xs border border-border bg-background rounded text-foreground"
                        />
                        <button
                          type="button"
                          onClick={() =>
                            updateCabinMutation.mutate({
                              cabinId: c.id,
                              data: { name: editingCabin.name.trim() },
                            })
                          }
                          disabled={!editingCabin.name.trim()}
                          className="h-7 px-2 bg-primary text-primary-foreground text-xs font-medium rounded"
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingCabin(null)}
                          className="h-7 px-2 text-xs text-muted-foreground hover:bg-muted rounded"
                        >
                          ✕
                        </button>
                      </div>
                    )
                  }

                  return (
                    <div
                      key={c.id}
                      onClick={() => {
                        setSelectedCabinId(c.id)
                        setSelectedBoxId(null)
                      }}
                      className={cn(
                        "flex items-center justify-between gap-2 px-3 py-2 text-xs transition-colors cursor-pointer",
                        isSelected ? "bg-primary/10" : "hover:bg-muted/40",
                      )}
                    >
                      <div className="min-w-0 flex-1 flex items-center gap-1.5">
                        <span className="font-semibold text-foreground truncate">{c.name}</span>
                        {c.pin_x !== null && c.pin_x !== undefined && (
                          <MapPin size={10} className="text-emerald-500 shrink-0" />
                        )}
                      </div>

                      <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-secondary text-secondary-foreground">
                          {c.boxes?.length ?? 0}b · {c.item_count ?? 0}i
                        </span>
                        <button
                          type="button"
                          onClick={() => setEditingCabin(c)}
                          className="p-1 text-muted-foreground hover:text-foreground rounded"
                        >
                          <Pencil size={11} />
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            if (confirm(`Delete "${c.name}"?`)) deleteCabinMutation.mutate(c.id)
                          }}
                          className="p-1 text-muted-foreground hover:text-red-600 rounded"
                        >
                          <Trash2 size={11} />
                        </button>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>

          {/* Col 2: Boxes inside selected cabin */}
          <div className="flex flex-col gap-2">
            <span className="text-xs font-bold text-foreground">
              {selectedCabin ? `Boxes in ${selectedCabin.name} (${cabinBoxes.length})` : "Boxes"}
            </span>

            {selectedCabin ? (
              <>
                <div className="flex items-center gap-1.5">
                  <input
                    value={newBoxName}
                    onChange={(e) => setNewBoxName(e.target.value)}
                    placeholder="Box name"
                    className="h-8 flex-1 px-2.5 border border-border bg-background text-foreground rounded-lg text-xs"
                  />
                  <button
                    type="button"
                    onClick={() => createBoxMutation.mutate()}
                    disabled={!newBoxName.trim() || createBoxMutation.isPending}
                    className="h-8 px-2.5 bg-primary text-primary-foreground text-xs font-semibold rounded-lg hover:opacity-90 disabled:opacity-50 transition-colors shrink-0 cursor-pointer flex items-center gap-1"
                  >
                    <Plus size={12} /> Add
                  </button>
                </div>

                <div className="rounded-xl border border-border divide-y divide-border max-h-56 overflow-y-auto">
                  {cabinBoxes.length === 0 ? (
                    <p className="p-3 text-xs text-muted-foreground text-center">No boxes in this cabin.</p>
                  ) : (
                    cabinBoxes.map((b) => {
                      const isSelected = b.id === selectedBoxId
                      const isEditing = editingBox?.id === b.id

                      if (isEditing) {
                        return (
                          <div key={b.id} className="p-2 bg-muted/30 flex flex-col gap-1.5">
                            <input
                              value={editingBox.name}
                              onChange={(e) => setEditingBox({ ...editingBox, name: e.target.value })}
                              className="h-7 px-2 text-xs border border-border bg-background rounded text-foreground"
                            />
                            <select
                              value={editingBox.cabin_id}
                              onChange={(e) => setEditingBox({ ...editingBox, cabin_id: e.target.value })}
                              className="h-7 px-2 text-xs border border-border bg-background rounded text-foreground"
                            >
                              {cabins.map((c) => (
                                <option key={c.id} value={c.id}>
                                  {c.name}
                                </option>
                              ))}
                            </select>
                            <div className="flex items-center justify-end gap-1">
                              <button
                                type="button"
                                onClick={() => setEditingBox(null)}
                                className="h-6 px-2 text-xs text-muted-foreground hover:bg-muted rounded"
                              >
                                Cancel
                              </button>
                              <button
                                type="button"
                                onClick={() =>
                                  updateBoxMutation.mutate({
                                    boxId: b.id,
                                    data: {
                                      name: editingBox.name.trim(),
                                      cabin_id: editingBox.cabin_id,
                                    },
                                  })
                                }
                                disabled={!editingBox.name.trim()}
                                className="h-6 px-2.5 bg-primary text-primary-foreground text-xs font-medium rounded"
                              >
                                Save
                              </button>
                            </div>
                          </div>
                        )
                      }

                      return (
                        <div
                          key={b.id}
                          onClick={() => setSelectedBoxId(isSelected ? null : b.id)}
                          className={cn(
                            "flex items-center justify-between gap-2 px-3 py-2 text-xs transition-colors cursor-pointer",
                            isSelected ? "bg-primary/10" : "hover:bg-muted/40",
                          )}
                        >
                          <div className="flex items-center gap-2 min-w-0 flex-1">
                            {b.image_url ? (
                              <img src={b.image_url} alt="" className="w-6 h-6 rounded object-cover border border-border shrink-0" />
                            ) : (
                              <div className="w-6 h-6 rounded bg-muted flex items-center justify-center text-muted-foreground shrink-0 border border-border">
                                <Boxes size={12} />
                              </div>
                            )}
                            <span className="font-semibold text-foreground truncate">{b.name}</span>
                          </div>

                          <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                            <button
                              type="button"
                              onClick={() => setManagingBoxItems(b)}
                              className="px-1.5 py-0.5 rounded text-[10px] bg-primary/10 text-primary hover:bg-primary/20 font-semibold cursor-pointer"
                            >
                              {b.item_count ?? 0} items
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingBox(b)}
                              className="p-1 text-muted-foreground hover:text-foreground rounded"
                            >
                              <Pencil size={11} />
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                if (confirm(`Delete box "${b.name}"?`)) deleteBoxMutation.mutate(b.id)
                              }}
                              className="p-1 text-muted-foreground hover:text-red-600 rounded"
                            >
                              <Trash2 size={11} />
                            </button>
                          </div>
                        </div>
                      )
                    })
                  )}
                </div>
              </>
            ) : (
              <p className="p-4 border border-dashed border-border rounded-xl text-center text-xs text-muted-foreground">
                Select a cabin to view boxes.
              </p>
            )}
          </div>

          {/* Col 3: Items in Cabin/Box */}
          <div className="flex flex-col gap-2 rounded-xl border border-border bg-card/40 p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                <Package size={14} className="text-primary" />
                {selectedBox ? selectedBox.name : selectedCabin ? selectedCabin.name : "Components"}
              </span>
              <span className="text-[11px] text-muted-foreground font-semibold">
                {displayedItems.length}
              </span>
            </div>

            {selectedCabin ? (
              displayedItems.length === 0 ? (
                <p className="py-6 text-center text-xs text-muted-foreground">
                  No components assigned.
                </p>
              ) : (
                <div className="divide-y divide-border max-h-56 overflow-y-auto">
                  {displayedItems.map((item) => {
                    const assign = item.cabins?.find((c) =>
                      selectedBox ? c.box_id === selectedBox.id : c.cabin_id === selectedCabin.id
                    )
                    return (
                      <div key={item.item_id} className="py-1.5 flex items-center justify-between text-xs gap-2">
                        <div className="min-w-0 flex-1">
                          <p className="font-medium text-foreground truncate">{item.item_name}</p>
                          {assign?.box_name && !selectedBox && (
                            <span className="text-[10px] text-primary">📦 {assign.box_name}</span>
                          )}
                        </div>
                        <span className="font-mono font-bold text-foreground shrink-0">{item.qty} pcs</span>
                      </div>
                    )
                  })}
                </div>
              )
            ) : (
              <p className="py-6 text-center text-xs text-muted-foreground">
                Select a cabin to view components.
              </p>
            )}
          </div>
        </div>

        <div className="flex justify-end pt-2 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="h-8 px-4 border border-border rounded-xl text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
          >
            Done
          </button>
        </div>
      </div>

      {cropSrc && (
        <ImageCropModal
          isOpen={cropOpen}
          onClose={() => {
            if (!imageUploadMutation.isPending) {
              setCropOpen(false)
              setCropSrc(null)
            }
          }}
          imageSrc={cropSrc}
          title="Crop Warehouse Layout"
          showPreview={false}
          onCropComplete={async (croppedFile) => {
            await imageUploadMutation.mutateAsync(croppedFile)
            setCropOpen(false)
            setCropSrc(null)
          }}
          isUploading={imageUploadMutation.isPending}
        />
      )}

      {managingBoxItems && (
        <BoxItemsModal
          box={managingBoxItems}
          warehouseId={warehouse.id}
          onClose={() => setManagingBoxItems(null)}
        />
      )}
    </Modal>
  )
}
