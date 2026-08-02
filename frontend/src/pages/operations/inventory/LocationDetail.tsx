import { useState } from "react"
import { Link, useParams } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import {
  ArrowLeft,
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
import { Spinner } from "@/pages/admin/components/common"
import { KitQrCode } from "@/components/ui/KitQrCode"
import { KitModal } from "@/pages/operations/inventory/KitModal"
import { cn } from "@/lib/utils"

export default function LocationDetail() {
  const { locationId } = useParams({ from: "/auth/operations/inventory/locations/$locationId" })
  const [activeTab, setActiveTab] = useState<"kits" | "stock">("kits")
  const [search, setSearch] = useState("")
  const [selectedKitId, setSelectedKitId] = useState<string | null>(null)
  const [warehouseId, setWarehouseId] = useState("")

  const { data: locations = [], isLoading: loadingLocations } = useQuery({
    queryKey: ["inv-locations"],
    queryFn: () => getLocationsApi(true),
  })

  const location: Location | undefined = locations.find((l) => l.id === locationId)

  // A location can hold more than one warehouse — this is the picker that
  // narrows "everything at this location" down to one shelf.
  const { data: warehouses = [] } = useQuery({
    queryKey: ["inv-warehouses", locationId],
    queryFn: () => getWarehousesApi(locationId),
    enabled: !!locationId,
  })

  const { data: stock = [], isLoading: loadingStock } = useQuery<StockLevel[]>({
    queryKey: ["inv-stock-location", locationId, warehouseId],
    queryFn: () => getStockApi({ location_id: locationId, warehouse_id: warehouseId || undefined }),
    enabled: !!locationId,
  })

  const { data: kits = [], isLoading: loadingKits } = useQuery<KitListItem[]>({
    queryKey: ["inv-kits-location", locationId, warehouseId],
    queryFn: () => getKitsApi({ location_id: locationId, warehouse_id: warehouseId || undefined }),
    enabled: !!locationId,
  })

  if (loadingLocations) return <Spinner />

  const displayName = location?.name || "Warehouse"
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
    <div className="flex flex-col gap-6">
      <Link to="/operations/inventory" className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground w-fit transition-colors">
        <ArrowLeft size={14} /> Inventory overview
      </Link>

      {/* Warehouse Banner */}
      <div className="rounded-2xl border border-border bg-card p-6 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-2xs">
        <div className="flex items-start gap-4">
          <div className="p-3 bg-primary/10 text-primary rounded-2xl shrink-0">
            <Warehouse size={32} />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-2xl font-bold text-foreground">{displayName}</h1>
              {country && (
                <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-secondary text-secondary-foreground">
                  {country}
                </span>
              )}
            </div>

            {address ? (
              <p className="text-sm text-muted-foreground flex items-center gap-1.5 mt-1">
                <MapPin size={15} className="text-primary shrink-0" />
                <span>{address}</span>
              </p>
            ) : (
              <p className="text-sm text-muted-foreground mt-0.5">Primary regional equipment warehouse</p>
            )}

            {notes && (
              <p className="text-xs text-muted-foreground mt-1.5 italic">
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
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-primary border border-primary/20 bg-primary/5 hover:bg-primary/10 rounded-xl transition-colors shrink-0 self-start md:self-center cursor-pointer"
          >
            <MapPin size={15} /> Open in Google Maps <ExternalLink size={13} />
          </a>
        )}
      </div>

      {/* Stats Summary Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <div className="p-5 rounded-2xl border border-border bg-card flex flex-col">
          <span className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">Kits On Shelf</span>
          <span className="text-3xl font-bold font-mono text-foreground mt-1">{kits.length}</span>
        </div>
        <div className="p-5 rounded-2xl border border-border bg-card flex flex-col">
          <span className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">Loose Components</span>
          <span className="text-3xl font-bold font-mono text-foreground mt-1">
            {stock.reduce((sum, item) => sum + item.qty, 0)}
          </span>
        </div>
        <div className="p-5 rounded-2xl border border-border bg-card flex flex-col col-span-2 sm:col-span-1">
          <span className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">Incomplete Kits</span>
          <span className="text-3xl font-bold font-mono text-amber-600 dark:text-amber-400 mt-1">
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
              "px-3.5 py-2 rounded-xl text-sm font-medium border transition-colors cursor-pointer",
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
                "px-3.5 py-2 rounded-xl text-sm font-medium border transition-colors cursor-pointer",
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

      {/* Navigation Tabs & Search */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-4">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab("kits")}
            className={cn(
              "inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-colors cursor-pointer",
              activeTab === "kits"
                ? "bg-primary text-primary-foreground shadow-2xs"
                : "bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted"
            )}
          >
            <Boxes size={16} /> Kits Stored ({kits.length})
          </button>
          <button
            onClick={() => setActiveTab("stock")}
            className={cn(
              "inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-colors cursor-pointer",
              activeTab === "stock"
                ? "bg-primary text-primary-foreground shadow-2xs"
                : "bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted"
            )}
          >
            <Package size={16} /> Loose Components ({stock.length})
          </button>
        </div>

        <div className="relative w-full sm:w-72">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={`Search ${activeTab === "kits" ? "kits" : "items"} in ${displayName}…`}
            className="h-10 w-full pl-9 pr-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </div>
      </div>

      {/* Tab: Kits */}
      {activeTab === "kits" && (
        <div>
          {loadingKits ? (
            <div className="py-12 flex justify-center"><Spinner /></div>
          ) : filteredKits.length === 0 ? (
            <div className="p-12 border border-dashed border-border rounded-2xl text-center">
              <Boxes size={28} className="mx-auto text-muted-foreground mb-2" />
              <p className="text-base font-semibold text-foreground">No kits stored here</p>
              <p className="text-sm text-muted-foreground mt-1">There are no kits matching this search at {displayName}.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredKits.map((k) => (
                <div
                  key={k.id}
                  onClick={() => setSelectedKitId(k.id)}
                  className="p-4 rounded-2xl border border-border bg-card hover:border-primary/40 hover:shadow-xs transition-all cursor-pointer flex items-center gap-4 group"
                >
                  <div className="shrink-0 p-1 bg-white rounded-xl border border-border shadow-2xs" onClick={(e) => e.stopPropagation()}>
                    <KitQrCode label={k.label} tokenOrId={k.id} size={56} showDownload={false} showCopyLink={false} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-base font-bold font-mono text-foreground group-hover:text-primary transition-colors">
                        {k.label}
                      </p>
                      {k.shortage_count > 0 ? (
                        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
                          {k.shortage_count} missing
                        </span>
                      ) : (
                        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400">
                          Complete
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground truncate mt-1 font-mono">
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

      {/* Tab: Stock */}
      {activeTab === "stock" && (
        <div>
          {loadingStock ? (
            <div className="py-12 flex justify-center"><Spinner /></div>
          ) : filteredStock.length === 0 ? (
            <div className="p-12 border border-dashed border-border rounded-2xl text-center">
              <Package size={28} className="mx-auto text-muted-foreground mb-2" />
              <p className="text-base font-semibold text-foreground">No loose stock recorded</p>
              <p className="text-sm text-muted-foreground mt-1">No components or merch are currently cataloged at {displayName}.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
              {filteredStock.map((item) => (
                <div key={item.item_id} className="p-4 rounded-2xl border border-border bg-card flex flex-col justify-between gap-3 shadow-2xs">
                  <div>
                    <p className="text-sm font-semibold text-foreground line-clamp-2">{item.item_name}</p>
                    {item.category && (
                      <p className="text-xs text-muted-foreground flex items-center gap-1 mt-1 font-mono uppercase">
                        <Tag size={11} /> {item.category}
                      </p>
                    )}
                    {!warehouseId && warehouses.length > 1 && (
                      <p className="text-xs text-muted-foreground/80 mt-1">{item.warehouse_name}</p>
                    )}
                  </div>
                  <div className="flex items-center justify-between pt-3 border-t border-border">
                    <span className="text-xs text-muted-foreground">On hand:</span>
                    <span className="text-base font-bold font-mono text-foreground">{item.qty}</span>
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
  )
}
