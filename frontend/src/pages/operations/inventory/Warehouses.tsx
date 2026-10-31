import { useEffect, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  AlertCircle,
  Boxes,
  ImageOff,
  ImagePlus,
  MapPin,
  Package,
  PackageCheck,
  Pencil,
  Search,
  Tag,
} from "lucide-react"
import {
  getItemCategoriesApi,
  getItemsApi,
  getStockApi,
  getWarehouseBoxesApi,
  getWarehouseCabinsApi,
  getWarehousesApi,
} from "@/api/inventory"
import type { Item, StockLevel, WarehouseBox, WarehouseCabin } from "@/types/inventory"
import { Field, Spinner } from "@/pages/admin/components/common"
import { cn } from "@/lib/utils"

import { StockCountModal } from "./StockCountModal"
import { ItemCabinsModal } from "./ItemCabinsModal"
import { WarehouseCabinsModal } from "./WarehouseCabinsModal"
import { WarehouseStockTakeModal } from "./WarehouseStockTakeModal"
import { VariantsModal } from "./VariantsModal"

export default function WarehousesPage() {
  // Fetch all active warehouses
  const { data: warehouses = [], isLoading: loadingWarehouses } = useQuery({
    queryKey: ["inv-warehouses-all"],
    queryFn: () => getWarehousesApi(undefined, true),
  })

  // Selected warehouse with localStorage persistence
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<string>(() => {
    return localStorage.getItem("inv_selected_warehouse") || ""
  })

  useEffect(() => {
    if (!selectedWarehouseId && warehouses.length > 0) {
      setSelectedWarehouseId(warehouses[0].id)
    } else if (selectedWarehouseId && !warehouses.some((w) => w.id === selectedWarehouseId) && warehouses.length > 0) {
      setSelectedWarehouseId(warehouses[0].id)
    }
  }, [warehouses, selectedWarehouseId])

  const handleSelectWarehouse = (id: string) => {
    setSelectedWarehouseId(id)
    localStorage.setItem("inv_selected_warehouse", id)
    setCabinId("") // reset cabin filter on warehouse switch
    setBoxId("")
  }

  const currentWarehouse = warehouses.find((w) => w.id === selectedWarehouseId)

  // Cabins for the selected warehouse
  const { data: cabins = [] } = useQuery<WarehouseCabin[]>({
    queryKey: ["inv-warehouse-cabins", selectedWarehouseId],
    queryFn: () => getWarehouseCabinsApi(selectedWarehouseId),
    enabled: !!selectedWarehouseId,
  })

  // Boxes for the selected warehouse
  const { data: boxes = [] } = useQuery<WarehouseBox[]>({
    queryKey: ["inv-warehouse-boxes", selectedWarehouseId],
    queryFn: () => getWarehouseBoxesApi(selectedWarehouseId),
    enabled: !!selectedWarehouseId,
  })

  // Stock for the selected warehouse
  const { data: stock = [], isLoading: loadingStock } = useQuery<StockLevel[]>({
    queryKey: ["inv-stock", "warehouse", selectedWarehouseId],
    queryFn: () => getStockApi({ warehouse_id: selectedWarehouseId }),
    enabled: !!selectedWarehouseId,
  })

  // All catalog items
  const { data: items = [] } = useQuery({ queryKey: ["inv-items"], queryFn: () => getItemsApi() })

  // Categories for filtering
  const { data: categories = [] } = useQuery({
    queryKey: ["inv-categories"],
    queryFn: () => getItemCategoriesApi(),
  })

  // Filters & view controls (copied directly from Stock.tsx)
  const [search, setSearch] = useState("")
  const [category, setCategory] = useState("")
  const [subcategory, setSubcategory] = useState("")
  const [cabinId, setCabinId] = useState("")
  const [boxId, setBoxId] = useState("")
  const [onlyInStock, setOnlyInStock] = useState(false)
  const [onlyOutOfStock, setOnlyOutOfStock] = useState(false)
  const [onlyUnstocked, setOnlyUnstocked] = useState(false)

  // Modals state
  const [counting, setCounting] = useState<{ itemId: string; itemName: string } | null>(null)
  const [viewingGroup, setViewingGroup] = useState<string | null>(null)
  const [managingCabinsItem, setManagingCabinsItem] = useState<Item | null>(null)
  const [managingCabinsLayout, setManagingCabinsLayout] = useState(false)
  const [stocktaking, setStocktaking] = useState(false)

  const selectedCategoryDef = useMemo(
    () => categories.find((c) => c.name === category),
    [categories, category],
  )
  const availableSubcategories = selectedCategoryDef?.subcategories ?? []

  // Summary Metrics
  const totalUnits = useMemo(() => stock.reduce((sum, s) => sum + s.qty, 0), [stock])
  const unassignedItems = useMemo(
    () => stock.filter((s) => !s.cabins || s.cabins.length === 0),
    [stock],
  )

  // Cards calculation identical to Stock.tsx scoped to this warehouse
  const cards = useMemo(() => {
    const rowsByItem = new Map<string, StockLevel[]>()
    for (const s of stock) {
      const rows = rowsByItem.get(s.item_id)
      if (rows) rows.push(s)
      else rowsByItem.set(s.item_id, [s])
    }

    const inScope = (level: StockLevel) => {
      if (level.warehouse_id !== selectedWarehouseId) return false
      const itemCabins = level.cabins ?? []
      if (cabinId) {
        if (cabinId === "unassigned") {
          return itemCabins.length === 0
        }
        const matchesCabin = itemCabins.some((c) => c.cabin_id === cabinId)
        if (!matchesCabin) return false

        if (boxId) {
          if (boxId === "loose") {
            return itemCabins.some((c) => c.cabin_id === cabinId && !c.box_id)
          }
          return itemCabins.some((c) => c.cabin_id === cabinId && c.box_id === boxId)
        }
        return true
      }
      if (boxId) {
        if (boxId === "loose") {
          return itemCabins.some((c) => !c.box_id)
        }
        return itemCabins.some((c) => c.box_id === boxId)
      }
      return true
    }

    const perItem = items
      .filter((item) => !category || item.category === category)
      .filter((item) => !subcategory || item.subcategory === subcategory)
      .filter((item) => !search.trim() || item.name.toLowerCase().includes(search.trim().toLowerCase()))
      .map((item) => {
        const allRows = rowsByItem.get(item.id) ?? []
        const scopedRows = allRows.filter(inScope)
        const cabinSummary: { name: string; box_name?: string | null }[] = []
        for (const r of scopedRows) {
          for (const c of r.cabins ?? []) {
            const key = c.box_name ? `${c.cabin_name} › ${c.box_name}` : c.cabin_name
            if (!cabinSummary.some((existing) => (existing.box_name ? `${existing.name} › ${existing.box_name}` : existing.name) === key)) {
              cabinSummary.push({ name: c.cabin_name, box_name: c.box_name })
            }
          }
        }
        const total = scopedRows.reduce((sum, r) => sum + r.qty, 0)
        const breakdown = scopedRows.map((r) => ({ name: r.warehouse_name, qty: r.qty }))

        return {
          item,
          total,
          hasRowsInScope: scopedRows.length > 0,
          stockedAnywhere: allRows.length > 0,
          breakdown,
          cabins: cabinSummary,
        }
      })

    const byGroup = new Map<string, typeof perItem>()
    const singles: typeof perItem = []
    for (const entry of perItem) {
      if (entry.item.variant_group) {
        const members = byGroup.get(entry.item.variant_group)
        if (members) members.push(entry)
        else byGroup.set(entry.item.variant_group, [entry])
      } else {
        singles.push(entry)
      }
    }

    const groupCards = Array.from(byGroup.entries()).map(([groupName, members]) => {
      const sorted = [...members].sort((a, b) => a.item.name.localeCompare(b.item.name))
      const cabinSummary: { name: string; box_name?: string | null }[] = []
      for (const m of sorted) {
        for (const c of m.cabins) {
          const key = c.box_name ? `${c.name} › ${c.box_name}` : c.name
          if (!cabinSummary.some((existing) => (existing.box_name ? `${existing.name} › ${existing.box_name}` : existing.name) === key)) {
            cabinSummary.push(c)
          }
        }
      }
      return {
        kind: "group" as const,
        groupName,
        representative: sorted[0].item,
        memberCount: sorted.length,
        total: sorted.reduce((sum, m) => sum + m.total, 0),
        hasRowsInScope: sorted.some((m) => m.hasRowsInScope),
        stockedAnywhere: sorted.some((m) => m.stockedAnywhere),
        breakdown: sorted[0].breakdown,
        cabins: cabinSummary,
      }
    })
    const singleCards = singles.map((entry) => ({ kind: "single" as const, ...entry }))

    return [...groupCards, ...singleCards]
      .filter((c) => {
        if (onlyUnstocked) return !c.hasRowsInScope
        if (onlyInStock) return c.total > 0
        if (onlyOutOfStock) return c.hasRowsInScope && c.total === 0
        return c.hasRowsInScope
      })
      .sort((a, b) => {
        const nameA = a.kind === "group" ? a.groupName : a.item.name
        const nameB = b.kind === "group" ? b.groupName : b.item.name
        return nameA.localeCompare(nameB)
      })
  }, [items, stock, selectedWarehouseId, category, subcategory, search, cabinId, boxId, onlyInStock, onlyOutOfStock, onlyUnstocked])

  if (loadingWarehouses) {
    return (
      <div className="flex items-center justify-center p-12">
        <Spinner />
      </div>
    )
  }

  if (warehouses.length === 0) {
    return (
      <div className="p-8 text-center bg-card border border-border rounded-2xl max-w-xl mx-auto my-12">
        <h2 className="text-lg font-bold text-foreground">No Warehouses Configured</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Add warehouses in the Catalogue page before accessing warehouse stock operations.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      {/* 1. Header & Warehouse Switcher (Code next to selector, no building icon) */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-card border border-border p-4 sm:p-6 rounded-2xl shadow-xs">
        <div className="flex items-center gap-2.5 flex-nowrap min-w-0">
          <select
            value={selectedWarehouseId}
            onChange={(e) => handleSelectWarehouse(e.target.value)}
            className="h-9 font-bold text-base bg-background text-foreground border border-border rounded-xl px-3 cursor-pointer focus:outline-none focus:border-primary shadow-xs shrink-0 max-w-[280px] sm:max-w-none truncate"
          >
            {warehouses.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name} {w.location_name ? `(${w.location_name})` : ""}
              </option>
            ))}
          </select>
          {currentWarehouse?.code && (
            <span className="font-mono text-xs font-bold px-2.5 py-1.5 rounded-xl bg-secondary text-secondary-foreground border border-border shrink-0 whitespace-nowrap">
              {currentWarehouse.code}
            </span>
          )}
          {currentWarehouse?.address && (
            <span className="text-xs text-muted-foreground truncate hidden md:inline shrink min-w-0">
              📍 {currentWarehouse.address}
            </span>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2 flex-wrap shrink-0">
          <button
            type="button"
            onClick={() => setStocktaking(true)}
            className="inline-flex items-center gap-1.5 h-9 px-3.5 bg-primary text-primary-foreground text-xs font-semibold rounded-xl hover:opacity-90 transition-opacity shadow-xs cursor-pointer"
          >
            <PackageCheck size={14} />
            <span>Stocktake Warehouse</span>
          </button>
          <button
            type="button"
            onClick={() => setManagingCabinsLayout(true)}
            className="inline-flex items-center gap-1.5 h-9 px-3.5 bg-background border border-border text-foreground hover:bg-muted text-xs font-medium rounded-xl transition-colors cursor-pointer"
          >
            <MapPin size={14} className="text-primary" />
            <span>Cabins & Layout</span>
          </button>
        </div>
      </div>

      {/* 2. Top Summary KPI Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-4 rounded-xl border border-border bg-card">
          <p className="text-xs text-muted-foreground font-medium">Components in Warehouse</p>
          <p className="text-2xl font-bold text-foreground mt-1">{stock.length}</p>
        </div>
        <div className="p-4 rounded-xl border border-border bg-card">
          <p className="text-xs text-muted-foreground font-medium">Total Units in Stock</p>
          <p className="text-2xl font-bold text-foreground mt-1">{totalUnits.toLocaleString()}</p>
        </div>
        <div className="p-4 rounded-xl border border-border bg-card">
          <p className="text-xs text-muted-foreground font-medium">Configured Cabins</p>
          <p className="text-2xl font-bold text-foreground mt-1">{cabins.length}</p>
        </div>
        <div
          onClick={() => setCabinId(cabinId === "unassigned" ? "" : "unassigned")}
          className={cn(
            "p-4 rounded-xl border transition-all cursor-pointer",
            cabinId === "unassigned"
              ? "bg-amber-500/15 border-amber-500/40 text-amber-900 dark:text-amber-200 ring-2 ring-amber-500/30"
              : unassignedItems.length > 0
                ? "bg-card border-amber-500/30 hover:bg-amber-500/5"
                : "bg-card border-border",
          )}
        >
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground font-medium">Unassigned to Cabin</p>
            {unassignedItems.length > 0 && <AlertCircle size={14} className="text-amber-500" />}
          </div>
          <p className="text-2xl font-bold text-foreground mt-1">
            {unassignedItems.length}
            {cabinId === "unassigned" && <span className="text-xs font-normal ml-2">(filtered)</span>}
          </p>
        </div>
      </div>

      {/* 3. Visual Layout Photo & Cabin Pins */}
      {currentWarehouse?.image_url ? (
        <div className="bg-card border border-border rounded-2xl p-4 flex flex-col gap-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <MapPin size={16} className="text-primary shrink-0" />
              <h3 className="text-sm font-bold text-foreground whitespace-nowrap">Cabin Map</h3>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setManagingCabinsLayout(true)}
                className="text-xs text-muted-foreground hover:text-foreground font-medium cursor-pointer transition-colors"
                title="Edit visual layout and pins"
              >
                Edit layout
              </button>
              {cabinId && (
                <button
                  type="button"
                  onClick={() => {
                    setCabinId("")
                    setBoxId("")
                  }}
                  className="text-xs text-primary hover:underline font-medium cursor-pointer shrink-0"
                >
                  Clear filter
                </button>
              )}
            </div>
          </div>

          <div className="w-full rounded-xl overflow-hidden border border-border bg-black/5 dark:bg-black/40 max-h-[360px] flex items-center justify-center select-none">
            <div className="relative max-h-[360px] max-w-full">
              <img
                src={currentWarehouse.image_url}
                alt={currentWarehouse.name}
                className="max-h-[360px] max-w-full w-auto h-auto block pointer-events-none select-none"
              />
      {/* Clickable Cabin Pins */}
              {cabins.map((c) => {
                if (c.pin_x == null || c.pin_y == null) return null
                const isSelected = cabinId === c.id
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => {
                      setCabinId(isSelected ? "" : c.id)
                      setBoxId("")
                    }}
                    style={{ left: `${c.pin_x}%`, top: `${c.pin_y}%` }}
                    className={cn(
                      "absolute -translate-x-1/2 -translate-y-1/2 flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold shadow-lg transition-all cursor-pointer z-10 whitespace-nowrap",
                      isSelected
                        ? "bg-primary text-primary-foreground scale-125 ring-3 ring-white dark:ring-black"
                        : "bg-background/95 text-foreground hover:bg-primary/20 border border-border backdrop-blur-xs hover:scale-105",
                    )}
                    title={`${c.name} · ${c.item_count ?? 0} items`}
                  >
                    <MapPin size={12} className={isSelected ? "text-primary-foreground fill-current" : "text-primary"} />
                    <span>{c.name}</span>
                    {c.item_count ? (
                      <span
                        className={cn(
                          "text-[10px] px-1 rounded-full",
                          isSelected ? "bg-white/20 text-white" : "bg-muted text-muted-foreground",
                        )}
                      >
                        {c.item_count}
                      </span>
                    ) : null}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      ) : (
        <div
          onClick={() => setManagingCabinsLayout(true)}
          className="p-5 border border-dashed border-border rounded-2xl bg-card/40 flex items-center justify-between gap-4 cursor-pointer hover:bg-muted/30 transition-colors"
        >
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-primary/10 text-primary">
              <ImagePlus size={20} />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground">No warehouse layout photo uploaded</p>
              <p className="text-xs text-muted-foreground">
                Upload a photo of your warehouse shelves or floor plan to enable interactive cabin pin navigation.
              </p>
            </div>
          </div>
          <button
            type="button"
            className="text-xs font-semibold px-3 py-1.5 bg-primary text-primary-foreground rounded-lg hover:opacity-90 shrink-0"
          >
            Upload Photo
          </button>
        </div>
      )}

      {/* 4. Boxes Strip inside Selected Cabin */}
      {cabinId && cabinId !== "unassigned" && (
        <div className="bg-card border border-border rounded-2xl p-4 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
              <Boxes size={15} className="text-primary" /> Boxes in {cabins.find((c) => c.id === cabinId)?.name}
            </span>
            {boxId && (
              <button
                type="button"
                onClick={() => setBoxId("")}
                className="text-xs text-primary hover:underline font-medium cursor-pointer"
              >
                Show all in cabin
              </button>
            )}
          </div>

          <div className="flex items-center gap-2 overflow-x-auto pb-1">
            <button
              type="button"
              onClick={() => setBoxId("")}
              className={cn(
                "flex items-center gap-2 px-3 py-2 rounded-xl border text-xs font-semibold cursor-pointer shrink-0 transition-all",
                !boxId ? "bg-primary text-primary-foreground border-primary" : "bg-card border-border hover:bg-muted/50 text-foreground",
              )}
            >
              <Package size={14} />
              <span>All in Cabin</span>
            </button>

            <button
              type="button"
              onClick={() => setBoxId(boxId === "loose" ? "" : "loose")}
              className={cn(
                "flex items-center gap-2 px-3 py-2 rounded-xl border text-xs font-semibold cursor-pointer shrink-0 transition-all",
                boxId === "loose" ? "bg-primary text-primary-foreground border-primary" : "bg-card border-border hover:bg-muted/50 text-foreground",
              )}
            >
              <span>Loose on shelf</span>
            </button>

            {boxes
              .filter((b) => b.cabin_id === cabinId)
              .map((b) => {
                const isSelected = boxId === b.id
                return (
                  <button
                    key={b.id}
                    type="button"
                    onClick={() => setBoxId(isSelected ? "" : b.id)}
                    className={cn(
                      "flex items-center gap-2 px-3 py-2 rounded-xl border text-xs font-semibold cursor-pointer shrink-0 transition-all",
                      isSelected
                        ? "bg-primary text-primary-foreground border-primary shadow-xs"
                        : "bg-card border-border hover:bg-muted/50 text-foreground",
                    )}
                  >
                    {b.image_url ? (
                      <img src={b.image_url} alt="" className="w-5 h-5 rounded object-cover border border-white/20 shrink-0" />
                    ) : (
                      <Boxes size={14} className={isSelected ? "text-primary-foreground" : "text-primary"} />
                    )}
                    <span>{b.name}</span>
                    <span
                      className={cn(
                        "text-[10px] px-1.5 py-0.2 rounded-full",
                        isSelected ? "bg-white/20 text-white" : "bg-secondary text-secondary-foreground",
                      )}
                    >
                      {b.item_count ?? 0}
                    </span>
                  </button>
                )
              })}
          </div>
        </div>
      )}

      {/* 5. Filters & Controls (Identical structure to Stock.tsx) */}
      <div className="flex flex-col gap-3">
        <div className="flex items-end gap-3 flex-wrap">
          {/* 1. Search */}
          <Field label="Search stock" className="w-full sm:w-56">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name…"
                className="h-9 w-full pl-8 pr-3 border border-border bg-background text-foreground rounded-xl text-sm"
              />
            </div>
          </Field>

          {/* 2. Category and Subcategory */}
          <div className="grid grid-cols-2 gap-3 w-full sm:w-auto sm:flex sm:items-end">
            <Field label="Category" className="w-full sm:w-44">
              <select
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value)
                  setSubcategory("")
                }}
                className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm w-full cursor-pointer focus:outline-none focus:border-primary capitalize"
              >
                <option value="">All categories</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Subcategory" className="w-full sm:w-44">
              <select
                value={subcategory}
                onChange={(e) => setSubcategory(e.target.value)}
                disabled={!category || availableSubcategories.length === 0}
                className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm w-full cursor-pointer focus:outline-none focus:border-primary capitalize disabled:opacity-50"
              >
                <option value="">All subcategories</option>
                {availableSubcategories.map((s) => (
                  <option key={s.id} value={s.name}>
                    {s.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          {/* 3. Cabin and Box Dropdowns */}
          <div className="grid grid-cols-2 gap-3 w-full sm:w-auto sm:flex sm:items-end">
            <Field label="Cabin" className="w-full sm:w-44">
              <select
                value={cabinId}
                onChange={(e) => {
                  setCabinId(e.target.value)
                  setBoxId("")
                }}
                className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm w-full cursor-pointer focus:outline-none focus:border-primary"
              >
                <option value="">All cabins</option>
                <option value="unassigned">Unassigned</option>
                {cabins.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} {c.item_count ? `(${c.item_count})` : ""}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Box" className="w-full sm:w-44">
              <select
                value={boxId}
                onChange={(e) => setBoxId(e.target.value)}
                disabled={cabinId === "unassigned"}
                className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm w-full cursor-pointer focus:outline-none focus:border-primary disabled:opacity-50"
              >
                <option value="">All boxes</option>
                {cabinId && <option value="loose">Loose (no box)</option>}
                {(cabinId ? boxes.filter((b) => b.cabin_id === cabinId) : boxes).map((b) => (
                  <option key={b.id} value={b.id}>
                    📦 {b.name} {b.item_count ? `(${b.item_count})` : ""}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        </div>

        {/* 4. Checkboxes (In stock only, Not stocked, Out of stock) */}
        <div className="flex items-center gap-4 flex-wrap pt-0.5">
          <label className="flex items-center gap-1.5 text-sm text-foreground cursor-pointer select-none">
            <input
              type="checkbox"
              checked={onlyInStock}
              onChange={(e) => {
                setOnlyInStock(e.target.checked)
                if (e.target.checked) {
                  setOnlyOutOfStock(false)
                  setOnlyUnstocked(false)
                }
              }}
            />
            In stock only
          </label>
          <label className="flex items-center gap-1.5 text-sm text-foreground cursor-pointer select-none">
            <input
              type="checkbox"
              checked={onlyUnstocked}
              onChange={(e) => {
                setOnlyUnstocked(e.target.checked)
                if (e.target.checked) {
                  setOnlyOutOfStock(false)
                  setOnlyInStock(false)
                }
              }}
            />
            Not stocked
          </label>
          <label className="flex items-center gap-1.5 text-sm text-foreground cursor-pointer select-none">
            <input
              type="checkbox"
              checked={onlyOutOfStock}
              onChange={(e) => {
                setOnlyOutOfStock(e.target.checked)
                if (e.target.checked) {
                  setOnlyUnstocked(false)
                  setOnlyInStock(false)
                }
              }}
            />
            Out of stock
          </label>
        </div>
      </div>

      {/* 5. Component Cards Grid (identical to Stock.tsx) */}
      {loadingStock ? (
        <Spinner />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {cards.map((card) => {
            const item = card.kind === "group" ? card.representative : card.item
            return (
              <StockCard
                key={card.kind === "group" ? card.groupName : item.id}
                item={item}
                displayName={card.kind === "group" ? card.groupName : item.name}
                memberCount={card.kind === "group" ? card.memberCount : undefined}
                total={card.total}
                breakdown={card.breakdown}
                cabins={card.cabins}
                onEdit={() =>
                  card.kind === "group"
                    ? setViewingGroup(card.groupName)
                    : setCounting({ itemId: item.id, itemName: item.name })
                }
                onManageCabins={() =>
                  setManagingCabinsItem(card.kind === "group" ? card.representative : card.item)
                }
              />
            )
          })}
          {cards.length === 0 && (
            <div className="col-span-full flex flex-col items-center justify-center gap-2 h-40 border border-dashed border-border rounded-2xl text-center px-6">
              <Boxes size={20} className="text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                {stock.length === 0
                  ? "Nothing in this warehouse yet — use “Stocktake Warehouse” to enter what's there."
                  : "Nothing matches these filters."}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Modals */}
      {counting && (
        <StockCountModal
          itemId={counting.itemId}
          itemName={counting.itemName}
          warehouseId={selectedWarehouseId}
          onClose={() => setCounting(null)}
        />
      )}

      {viewingGroup && (
        <VariantsModal
          groupName={viewingGroup}
          warehouseId={selectedWarehouseId}
          onClose={() => setViewingGroup(null)}
        />
      )}

      {managingCabinsItem && (
        <ItemCabinsModal
          item={managingCabinsItem}
          defaultWarehouseId={selectedWarehouseId}
          onClose={() => setManagingCabinsItem(null)}
        />
      )}

      {managingCabinsLayout && currentWarehouse && (
        <WarehouseCabinsModal
          warehouse={currentWarehouse}
          onClose={() => setManagingCabinsLayout(false)}
        />
      )}

      {stocktaking && (
        <WarehouseStockTakeModal
          initialWarehouseId={selectedWarehouseId}
          onClose={() => setStocktaking(false)}
        />
      )}
    </div>
  )
}

function StockCard({
  item,
  displayName,
  memberCount,
  total,
  breakdown,
  cabins,
  onEdit,
  onManageCabins,
}: {
  item: Item
  displayName: string
  memberCount?: number
  total: number
  breakdown: { name: string; qty: number }[]
  cabins?: { name: string; box_name?: string | null; qty?: number | null }[]
  onEdit: () => void
  onManageCabins?: () => void
}) {
  const shown = breakdown.slice(0, 3)
  const hidden = breakdown.length - shown.length

  return (
    <div className="rounded-2xl border border-border bg-card overflow-hidden flex flex-col">
      <div className="w-full aspect-square bg-muted/40 border-b border-border flex items-center justify-center">
        {item.image_url ? (
          <img src={item.image_url} alt="" className="w-full h-full object-cover" />
        ) : (
          <ImageOff size={24} className="text-muted-foreground" />
        )}
      </div>
      <div className="p-3 flex flex-col gap-2 flex-1">
        <div>
          <p className="text-sm font-semibold text-foreground truncate" title={displayName}>
            {displayName}
          </p>
          <div className="flex items-center gap-1.5 flex-wrap mt-1">
            <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground capitalize">
              <Tag size={11} /> {item.category}
            </span>
            {item.subcategory && (
              <span className="inline-flex items-center text-xs px-2 py-0.5 rounded-full bg-muted/60 text-muted-foreground capitalize">
                {item.subcategory}
              </span>
            )}
            {memberCount !== undefined && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground">
                {memberCount} sizes
              </span>
            )}
          </div>
          {cabins && cabins.length > 0 ? (
            <div className="flex items-center gap-1 flex-wrap mt-2">
              {cabins.map((c, idx) => {
                const label = c.box_name ? `${c.name} › 📦 ${c.box_name}` : c.name
                return (
                  <span
                    key={`${label}-${idx}`}
                    className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-md bg-primary/10 text-primary border border-primary/20"
                  >
                    <MapPin size={10} />
                    <span>{label}</span>
                    {c.qty != null && <span className="opacity-75 font-mono">({c.qty})</span>}
                  </span>
                )
              })}
            </div>
          ) : total > 0 ? (
            <div className="flex items-center gap-1 flex-wrap mt-2">
              <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-md bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/20">
                <AlertCircle size={10} />
                <span>Unassigned</span>
              </span>
            </div>
          ) : null}
        </div>
        <div className="mt-auto pt-1">
          <p className="text-lg font-bold text-foreground tabular-nums">{total}</p>
          {breakdown.length > 0 ? (
            <p
              className="text-xs text-muted-foreground truncate"
              title={breakdown.map((b) => `${b.name} ${b.qty}`).join(" · ")}
            >
              {shown.map((b) => `${b.name} ${b.qty}`).join(" · ")}
              {hidden > 0 && ` · +${hidden} more`}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">Not stocked here</p>
          )}
        </div>
        <div className="flex items-center gap-1.5 mt-1">
          <button
            onClick={onEdit}
            className="flex-1 flex items-center justify-center gap-1.5 h-8 px-2 border border-border bg-background text-foreground text-xs font-medium rounded-lg hover:bg-muted/60 transition-colors cursor-pointer"
          >
            <Pencil size={12} /> {memberCount !== undefined ? "View sizes" : "Edit counts"}
          </button>
          {onManageCabins && (
            <button
              type="button"
              onClick={onManageCabins}
              title="Cabin placement"
              className="flex items-center justify-center gap-1 h-8 px-2.5 border border-border bg-background text-foreground text-xs font-medium rounded-lg hover:bg-muted/60 transition-colors cursor-pointer"
            >
              <MapPin size={12} className="text-primary" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
