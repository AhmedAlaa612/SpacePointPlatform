import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ArrowLeftRight, Boxes, ClipboardList, Clock, ImageOff, Pencil, Search, Tag } from "lucide-react"
import type { Item, StockLevel } from "@/types/inventory"
import {
  getItemCategoriesApi,
  getItemsApi,
  getLocationsApi,
  getOverdueApi,
  getStockApi,
  getWarehousesApi,
} from "@/api/inventory"
import { Field, Spinner } from "@/pages/admin/components/common"
import { MoveStockModal } from "@/pages/operations/inventory/MoveStockModal"
import { StockCountModal } from "@/pages/operations/inventory/StockCountModal"
import { VariantsModal } from "@/pages/operations/inventory/VariantsModal"
import { WarehouseStockTakeModal } from "@/pages/operations/inventory/WarehouseStockTakeModal"

/** One card per item — "how many do we own, and where" — with location and
 *  warehouse as filters rather than the unit of grouping. A warehouse filter
 *  swaps the headline number for that warehouse's count and drops cards with
 *  nothing there; it doesn't change what a card *is*. */
export default function Stock() {
  const [locationId, setLocationId] = useState("")
  const [warehouseId, setWarehouseId] = useState("")
  const [category, setCategory] = useState("")
  const [search, setSearch] = useState("")
  const [onlyInStock, setOnlyInStock] = useState(false)
  const [onlyOutOfStock, setOnlyOutOfStock] = useState(false)
  const [onlyUnstocked, setOnlyUnstocked] = useState(false)
  const [counting, setCounting] = useState<{ itemId: string; itemName: string } | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [stockTakeOpen, setStockTakeOpen] = useState(false)
  const [moveOpen, setMoveOpen] = useState(false)
  const [viewingGroup, setViewingGroup] = useState<string | null>(null)

  const { data: locations = [] } = useQuery({ queryKey: ["inv-locations"], queryFn: () => getLocationsApi() })
  const { data: warehouses = [] } = useQuery({ queryKey: ["inv-warehouses-all"], queryFn: () => getWarehousesApi() })
  const { data: categories = [] } = useQuery({ queryKey: ["inv-categories"], queryFn: () => getItemCategoriesApi() })
  // Unfiltered — location/warehouse/category/search all narrow client-side,
  // so switching a filter never needs a second round trip.
  const { data: stock = [], isLoading } = useQuery<StockLevel[]>({
    queryKey: ["inv-stock", "all"], queryFn: () => getStockApi(),
  })
  const { data: items = [] } = useQuery({ queryKey: ["inv-items"], queryFn: () => getItemsApi() })
  const { data: overdue = [] } = useQuery({ queryKey: ["inv-overdue"], queryFn: getOverdueApi })

  const warehousesForLocation = locationId ? warehouses.filter((w) => w.location_id === locationId) : warehouses

  const cards = useMemo(() => {
    const rowsByItem = new Map<string, StockLevel[]>()
    for (const s of stock) {
      const rows = rowsByItem.get(s.item_id)
      if (rows) rows.push(s)
      else rowsByItem.set(s.item_id, [s])
    }

    const inScope = (level: StockLevel) => {
      if (warehouseId) return level.warehouse_id === warehouseId
      if (locationId) return level.location_id === locationId
      return true
    }

    const perItem = items
      .filter((item) => !category || item.category === category)
      .filter((item) => !search.trim() || item.name.toLowerCase().includes(search.trim().toLowerCase()))
      .map((item) => {
        const allRows = rowsByItem.get(item.id) ?? []
        const scopedRows = allRows.filter(inScope)
        const byLocation = new Map<string, { name: string; qty: number }>()
        for (const r of scopedRows) {
          const entry = byLocation.get(r.location_id) ?? { name: r.location_name, qty: 0 }
          entry.qty += r.qty
          byLocation.set(r.location_id, entry)
        }
        return {
          item,
          total: scopedRows.reduce((sum, r) => sum + r.qty, 0),
          hasRowsInScope: scopedRows.length > 0,
          stockedAnywhere: allRows.length > 0,
          breakdown: Array.from(byLocation.values()).sort((a, b) => b.qty - a.qty),
        }
      })

    // Sized/variant merchandise browses as one card summing every size —
    // "not stocked anywhere"/"out of stock" and the location/warehouse scope
    // all roll up across the group rather than applying per size.
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
      const byLocation = new Map<string, { name: string; qty: number }>()
      for (const m of sorted) for (const b of m.breakdown) {
        const entry = byLocation.get(b.name) ?? { name: b.name, qty: 0 }
        entry.qty += b.qty
        byLocation.set(b.name, entry)
      }
      return {
        kind: "group" as const,
        groupName,
        representative: sorted[0].item,
        memberCount: sorted.length,
        total: sorted.reduce((sum, m) => sum + m.total, 0),
        hasRowsInScope: sorted.some((m) => m.hasRowsInScope),
        stockedAnywhere: sorted.some((m) => m.stockedAnywhere),
        breakdown: Array.from(byLocation.values()).sort((a, b) => b.qty - a.qty),
      }
    })
    const singleCards = singles.map((entry) => ({ kind: "single" as const, ...entry }))

    return [...groupCards, ...singleCards]
      .filter((c) => {
        if (onlyUnstocked) return !c.stockedAnywhere
        if (onlyInStock) return c.total > 0
        if ((locationId || warehouseId) && !c.hasRowsInScope) return false
        if (onlyOutOfStock && !(c.hasRowsInScope && c.total === 0)) return false
        return true
      })
      .sort((a, b) => {
        const nameA = a.kind === "group" ? a.groupName : a.item.name
        const nameB = b.kind === "group" ? b.groupName : b.item.name
        return nameA.localeCompare(nameB)
      })
  }, [items, stock, category, search, locationId, warehouseId, onlyInStock, onlyOutOfStock, onlyUnstocked])

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-foreground tracking-tight">Stock</h1>
          <p className="text-sm text-muted-foreground mt-0.5">What we own, and where it is</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setMoveOpen(true)}
            className="inline-flex items-center justify-center gap-1.5 h-9 px-4 border border-border text-foreground text-sm font-medium rounded-xl hover:bg-muted transition-colors whitespace-nowrap cursor-pointer"
          >
            <ArrowLeftRight size={14} /> Transfer / receive
          </button>
          <button
            onClick={() => setStockTakeOpen(true)}
            className="inline-flex items-center justify-center gap-1.5 h-9 px-4 border border-border text-foreground text-sm font-medium rounded-xl hover:bg-muted transition-colors whitespace-nowrap cursor-pointer"
          >
            <ClipboardList size={14} /> Stock take
          </button>
          <button
            onClick={() => setAddOpen(true)}
            className="inline-flex items-center justify-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors whitespace-nowrap cursor-pointer"
          >
            Record a count
          </button>
        </div>
      </div>

      {overdue.length > 0 && (
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4">
          <p className="flex items-center gap-2 text-sm font-semibold text-amber-700 dark:text-amber-400">
            <Clock size={15} /> {overdue.length} thing{overdue.length === 1 ? "" : "s"} overdue
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Issued to someone with a return date that has passed, and not yet handed back.
          </p>
        </div>
      )}

      <div className="flex items-end gap-3 flex-wrap">
        <Field label="Search stock">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name…"
              className="h-9 w-56 pl-8 pr-3 border border-border bg-background text-foreground rounded-xl text-sm"
            />
          </div>
        </Field>
        <Field label="Category">
          <select
            value={category} onChange={(e) => setCategory(e.target.value)}
            className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm w-fit cursor-pointer focus:outline-none focus:border-primary capitalize"
          >
            <option value="">All categories</option>
            {categories.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
          </select>
        </Field>
        <Field label="Location">
          <select
            value={locationId}
            onChange={(e) => { setLocationId(e.target.value); setWarehouseId("") }}
            className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm w-fit cursor-pointer focus:outline-none focus:border-primary"
          >
            <option value="">All locations</option>
            {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </Field>
        <Field label="Warehouse">
          <select
            value={warehouseId}
            onChange={(e) => setWarehouseId(e.target.value)}
            className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm w-fit cursor-pointer focus:outline-none focus:border-primary"
          >
            <option value="">All warehouses</option>
            {warehousesForLocation.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </Field>
        <label className="flex items-center gap-1.5 h-9 text-sm text-foreground cursor-pointer">
          <input
            type="checkbox" checked={onlyInStock}
            onChange={(e) => { setOnlyInStock(e.target.checked); if (e.target.checked) { setOnlyOutOfStock(false); setOnlyUnstocked(false) } }}
          />
          In stock only
        </label>
        <label className="flex items-center gap-1.5 h-9 text-sm text-foreground cursor-pointer">
          <input
            type="checkbox" checked={onlyOutOfStock}
            onChange={(e) => { setOnlyOutOfStock(e.target.checked); if (e.target.checked) { setOnlyUnstocked(false); setOnlyInStock(false) } }}
          />
          Out of stock
        </label>
        <label className="flex items-center gap-1.5 h-9 text-sm text-foreground cursor-pointer">
          <input
            type="checkbox" checked={onlyUnstocked}
            onChange={(e) => { setOnlyUnstocked(e.target.checked); if (e.target.checked) { setOnlyOutOfStock(false); setOnlyInStock(false) } }}
          />
          Not stocked anywhere
        </label>
      </div>

      {isLoading ? <Spinner /> : (
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
                onEdit={() => card.kind === "group"
                  ? setViewingGroup(card.groupName)
                  : setCounting({ itemId: item.id, itemName: item.name })}
              />
            )
          })}
          {cards.length === 0 && (
            <div className="col-span-full flex flex-col items-center justify-center gap-2 h-40 border border-dashed border-border rounded-2xl text-center px-6">
              <Boxes size={20} className="text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                {stock.length === 0
                  ? "Nothing on the shelves yet — use “Record a count” or “Stock take” to enter what's there."
                  : "Nothing matches these filters."}
              </p>
            </div>
          )}
        </div>
      )}

      {(counting || addOpen) && (
        <StockCountModal
          itemId={counting?.itemId}
          itemName={counting?.itemName}
          onClose={() => { setCounting(null); setAddOpen(false) }}
        />
      )}
      {stockTakeOpen && <WarehouseStockTakeModal onClose={() => setStockTakeOpen(false)} />}
      {moveOpen && <MoveStockModal onClose={() => setMoveOpen(false)} />}
      {viewingGroup && <VariantsModal groupName={viewingGroup} onClose={() => setViewingGroup(null)} />}
    </div>
  )
}

function StockCard({ item, displayName, memberCount, total, breakdown, onEdit }: {
  item: Item
  displayName: string
  memberCount?: number
  total: number
  breakdown: { name: string; qty: number }[]
  onEdit: () => void
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
          <p className="text-sm font-semibold text-foreground truncate" title={displayName}>{displayName}</p>
          <div className="flex items-center gap-1.5 flex-wrap mt-1">
            <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground capitalize">
              <Tag size={11} /> {item.category}
            </span>
            {memberCount !== undefined && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground">
                {memberCount} sizes
              </span>
            )}
          </div>
        </div>
        <div className="mt-auto pt-1">
          <p className="text-lg font-bold text-foreground tabular-nums">{total}</p>
          {breakdown.length > 0 ? (
            <p className="text-xs text-muted-foreground truncate" title={breakdown.map((b) => `${b.name} ${b.qty}`).join(" · ")}>
              {shown.map((b) => `${b.name} ${b.qty}`).join(" · ")}
              {hidden > 0 && ` · +${hidden} more`}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">Not stocked here</p>
          )}
        </div>
        <button
          onClick={onEdit}
          className="flex items-center justify-center gap-1.5 h-8 px-3 border border-border bg-background text-foreground text-xs font-medium rounded-lg hover:bg-muted/60"
        >
          <Pencil size={12} /> {memberCount !== undefined ? "View sizes" : "Edit counts"}
        </button>
      </div>
    </div>
  )
}
