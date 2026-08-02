import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  Boxes,
  ExternalLink,
  MapPin,
  Package,
  Search,
  Tag,
  Warehouse,
} from "lucide-react"
import type { KitListItem, Location, StockLevel } from "@/types/inventory"
import { getKitsApi, getLocationsApi, getStockApi, getWarehousesApi } from "@/api/inventory"
import { Modal, Spinner } from "@/pages/admin/components/common"
import { KitQrCode } from "@/components/ui/KitQrCode"
import { KitModal } from "@/pages/operations/inventory/KitModal"
import { cn } from "@/lib/utils"

interface LocationModalProps {
  locationId?: string
  locationName?: string
  onClose: () => void
}

export function LocationModal({ locationId, locationName, onClose }: LocationModalProps) {
  const [activeTab, setActiveTab] = useState<"kits" | "stock">("kits")
  const [search, setSearch] = useState("")
  const [selectedKitId, setSelectedKitId] = useState<string | null>(null)
  const [warehouseId, setWarehouseId] = useState("")

  // Fetch all locations to resolve location by ID or Name
  const { data: locations = [], isLoading: loadingLocations } = useQuery({
    queryKey: ["inv-locations"],
    queryFn: () => getLocationsApi(true),
  })

  const location: Location | undefined = locations.find(
    (l) => l.id === locationId || (locationName && l.name.toLowerCase() === locationName.toLowerCase())
  )

  const locId = location?.id || locationId || ""

  // A location can hold more than one warehouse — this is the picker that
  // narrows "everything at this location" down to one shelf.
  const { data: warehouses = [] } = useQuery({
    queryKey: ["inv-warehouses", locId],
    queryFn: () => getWarehousesApi(locId),
    enabled: !!locId,
  })

  // Fetch stock levels at this location (or one warehouse within it)
  const { data: stock = [], isLoading: loadingStock } = useQuery<StockLevel[]>({
    queryKey: ["inv-stock-location", locId, warehouseId],
    queryFn: () => getStockApi({ location_id: locId, warehouse_id: warehouseId || undefined }),
    enabled: !!locId,
  })

  // Fetch kits stored at this location (or one warehouse within it)
  const { data: kits = [], isLoading: loadingKits } = useQuery<KitListItem[]>({
    queryKey: ["inv-kits-location", locId, warehouseId],
    queryFn: () => getKitsApi({ location_id: locId, warehouse_id: warehouseId || undefined }),
    enabled: !!locId,
  })

  if (loadingLocations) {
    return (
      <Modal title="" onClose={onClose} maxWidth="max-w-4xl">
        <div className="py-12 flex justify-center">
          <Spinner />
        </div>
      </Modal>
    )
  }

  const displayName = location?.name || locationName || "Warehouse"
  const address = location?.address
  const mapsUrl = location?.maps_url
  const country = location?.country
  const notes = location?.notes

  const filteredStock = stock.filter((s) =>
    !search.trim() || s.item_name.toLowerCase().includes(search.trim().toLowerCase())
  )

  const filteredKits = kits.filter((k) =>
    !search.trim() ||
    k.label.toLowerCase().includes(search.trim().toLowerCase()) ||
    (k.template_code ?? "").toLowerCase().includes(search.trim().toLowerCase())
  )

  return (
    <Modal title="" onClose={onClose} maxWidth="max-w-4xl">
      <div className="flex flex-col gap-6 -mt-3">
        {/* Warehouse Header Banner */}
        <div className="rounded-2xl border border-border bg-card p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="p-3 bg-primary/10 text-primary rounded-2xl shrink-0">
              <Warehouse size={28} />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-xl font-bold text-foreground">{displayName}</h2>
                {country && (
                  <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-secondary text-secondary-foreground">
                    {country}
                  </span>
                )}
              </div>

              {address ? (
                <p className="text-xs text-muted-foreground flex items-center gap-1 mt-1">
                  <MapPin size={13} className="text-primary shrink-0" />
                  <span>{address}</span>
                </p>
              ) : (
                <p className="text-xs text-muted-foreground mt-0.5">Primary regional equipment warehouse</p>
              )}

              {notes && (
                <p className="text-xs text-muted-foreground/80 mt-1 italic">
                  Note: {notes}
                </p>
              )}
            </div>
          </div>

          {mapsUrl && (
            <a
              href={mapsUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium text-primary border border-primary/20 bg-primary/5 hover:bg-primary/10 rounded-xl transition-colors shrink-0 self-start md:self-center"
            >
              <MapPin size={13} /> Open in Google Maps <ExternalLink size={12} />
            </a>
          )}
        </div>

        {/* Stats Summary Bar */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <div className="p-4 rounded-xl border border-border bg-card flex flex-col">
            <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Kits On Shelf</span>
            <span className="text-2xl font-bold font-mono text-foreground mt-1">{kits.length}</span>
          </div>
          <div className="p-4 rounded-xl border border-border bg-card flex flex-col">
            <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Loose Components</span>
            <span className="text-2xl font-bold font-mono text-foreground mt-1">
              {stock.reduce((sum, item) => sum + item.qty, 0)}
            </span>
          </div>
          <div className="p-4 rounded-xl border border-border bg-card flex flex-col col-span-2 sm:col-span-1">
            <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Incomplete Kits</span>
            <span className="text-2xl font-bold font-mono text-amber-600 dark:text-amber-400 mt-1">
              {kits.filter((k) => k.shortage_count > 0).length}
            </span>
          </div>
        </div>

        {/* Warehouse picker — only worth showing once there's a choice to make */}
        {warehouses.length > 1 && (
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => setWarehouseId("")}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors cursor-pointer",
                warehouseId === ""
                  ? "border-primary/30 bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:bg-muted",
              )}
            >
              All warehouses
            </button>
            {warehouses.map((w) => (
              <button
                key={w.id}
                onClick={() => setWarehouseId(w.id)}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors cursor-pointer",
                  warehouseId === w.id
                    ? "border-primary/30 bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:bg-muted",
                )}
              >
                {w.name}
              </button>
            ))}
          </div>
        )}

        {/* Filter & View Tabs */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab("kits")}
              className={cn(
                "inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold transition-colors cursor-pointer",
                activeTab === "kits"
                  ? "bg-primary text-primary-foreground shadow-2xs"
                  : "bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted"
              )}
            >
              <Boxes size={14} /> Kits Stored ({kits.length})
            </button>
            <button
              onClick={() => setActiveTab("stock")}
              className={cn(
                "inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold transition-colors cursor-pointer",
                activeTab === "stock"
                  ? "bg-primary text-primary-foreground shadow-2xs"
                  : "bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted"
              )}
            >
              <Package size={14} /> Components & Stock ({stock.length})
            </button>
          </div>

          <div className="relative w-full sm:w-64">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={`Search ${activeTab === "kits" ? "kits" : "items"} in ${displayName}…`}
              className="h-9 w-full pl-9 pr-3 border border-border bg-card text-foreground rounded-xl text-xs focus:outline-none focus:border-primary"
            />
          </div>
        </div>

        {/* Tab Content: Kits stored at this warehouse */}
        {activeTab === "kits" && (
          <div>
            {loadingKits ? (
              <div className="py-8 flex justify-center"><Spinner /></div>
            ) : filteredKits.length === 0 ? (
              <div className="p-8 border border-dashed border-border rounded-2xl text-center">
                <Boxes size={24} className="mx-auto text-muted-foreground mb-2" />
                <p className="text-sm font-medium text-foreground">No kits stored here</p>
                <p className="text-xs text-muted-foreground mt-0.5">There are no kits matching this search at {displayName}.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[26rem] overflow-y-auto pr-1">
                {filteredKits.map((k) => (
                  <div
                    key={k.id}
                    onClick={() => setSelectedKitId(k.id)}
                    className="p-3.5 rounded-xl border border-border bg-card hover:border-primary/40 hover:shadow-2xs transition-all cursor-pointer flex items-center gap-3 group"
                  >
                    <div className="shrink-0 p-1 bg-white rounded-lg border border-border shadow-2xs" onClick={(e) => e.stopPropagation()}>
                      <KitQrCode label={k.label} tokenOrId={k.id} size={50} showDownload={false} showCopyLink={false} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-bold font-mono text-foreground group-hover:text-primary transition-colors">
                          {k.label}
                        </p>
                        {k.shortage_count > 0 ? (
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
                            {k.shortage_count} missing
                          </span>
                        ) : (
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400">
                            Complete
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground truncate mt-0.5 font-mono">
                        {k.template_code}
                        {!warehouseId && warehouses.length > 1 && <span> · {k.warehouse_name}</span>}
                        {k.holder_name ? (
                          <span className="text-primary font-medium"> · with {k.holder_name}</span>
                        ) : (
                          <span> · on the shelf</span>
                        )}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab Content: Loose components and stock at this warehouse */}
        {activeTab === "stock" && (
          <div>
            {loadingStock ? (
              <div className="py-8 flex justify-center"><Spinner /></div>
            ) : filteredStock.length === 0 ? (
              <div className="p-8 border border-dashed border-border rounded-2xl text-center">
                <Package size={24} className="mx-auto text-muted-foreground mb-2" />
                <p className="text-sm font-medium text-foreground">No stock recorded</p>
                <p className="text-xs text-muted-foreground mt-0.5">No loose components are cataloged at {displayName}.</p>
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 max-h-[26rem] overflow-y-auto pr-1">
                {filteredStock.map((item) => (
                  <div key={item.item_id} className="p-3 rounded-xl border border-border bg-card flex flex-col justify-between gap-2">
                    <div>
                      <p className="text-xs font-semibold text-foreground line-clamp-2">{item.item_name}</p>
                      {item.category && (
                        <p className="text-[10px] text-muted-foreground flex items-center gap-1 mt-1 font-mono uppercase">
                          <Tag size={9} /> {item.category}
                        </p>
                      )}
                      {!warehouseId && warehouses.length > 1 && (
                        <p className="text-[10px] text-muted-foreground/80 mt-0.5">{item.warehouse_name}</p>
                      )}
                    </div>
                    <div className="flex items-center justify-between pt-2 border-t border-border mt-1">
                      <span className="text-[11px] text-muted-foreground">On hand:</span>
                      <span className="text-sm font-bold font-mono text-foreground">{item.qty}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {selectedKitId && (
          <KitModal kitId={selectedKitId} onClose={() => setSelectedKitId(null)} />
        )}
      </div>
    </Modal>
  )
}
