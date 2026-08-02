import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  Eye,
  Layers,
  Plus,
  Search,
} from "lucide-react"
import type { KitListItem, KitStatus } from "@/types/inventory"
import {
  bulkCreateKitsApi,
  getKitsApi,
  getLocationsApi,
  getWarehousesApi,
  getTemplatesApi,
} from "@/api/inventory"
import { Field, Modal, ModalActions, Spinner } from "@/pages/admin/components/common"
import { KitQrCode, downloadKitQrLabel } from "@/components/ui/KitQrCode"
import { KitModal } from "@/pages/operations/inventory/KitModal"
import { LocationModal } from "@/pages/operations/inventory/LocationModal"
import { cn } from "@/lib/utils"

const STATUS_LABEL: Record<KitStatus, string> = {
  working: "Working",
  damaged: "Damaged",
  retired: "Retired",
  lost: "Lost",
}

const STATUS_STYLE: Record<KitStatus, string> = {
  working: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  damaged: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
  retired: "bg-muted text-muted-foreground",
  lost: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400",
}

export default function Kits() {
  const [locationId, setLocationId] = useState("")
  const [warehouseId, setWarehouseId] = useState("")
  const [status, setStatus] = useState("")
  const [availableOnly, setAvailableOnly] = useState(false)
  const [completeOnly, setCompleteOnly] = useState(false)
  const [search, setSearch] = useState("")
  const [bulkOpen, setBulkOpen] = useState(false)
  const [selectedKitId, setSelectedKitId] = useState<string | null>(null)
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null)

  const { data: locations = [] } = useQuery({ queryKey: ["inv-locations"], queryFn: () => getLocationsApi() })
  const { data: warehouses = [] } = useQuery({
    queryKey: ["inv-warehouses", locationId],
    queryFn: () => getWarehousesApi(locationId || undefined),
  })
  const { data: kits = [], isLoading } = useQuery<KitListItem[]>({
    queryKey: ["inv-kits", locationId, warehouseId, status, availableOnly],
    queryFn: () => getKitsApi({
      location_id: locationId || undefined,
      warehouse_id: warehouseId || undefined,
      status: status || undefined,
      available_only: availableOnly || undefined,
    }),
  })

  const term = search.trim().toLowerCase()
  const visible = kits
    .filter((k) => !completeOnly || k.shortage_count === 0)
    .filter((k) => !term ||
      k.label.toLowerCase().includes(term) ||
      (k.holder_name ?? "").toLowerCase().includes(term))

  const out = kits.filter((k) => k.current_holder_user_id).length
  const short = kits.filter((k) => k.shortage_count > 0).length

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-foreground tracking-tight">Kits</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {kits.length} kit{kits.length === 1 ? "" : "s"} · {out} out with someone · {short} incomplete
          </p>
        </div>
        <button
          onClick={() => setBulkOpen(true)}
          className="inline-flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors whitespace-nowrap shrink-0 cursor-pointer"
        >
          <Plus size={14} /> Add kits
        </button>
      </div>

      {/* filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Label or holder…"
            className="h-9 pl-9 pr-3 border border-border bg-card text-foreground rounded-xl text-sm w-56 focus:outline-none focus:border-primary transition-colors"
          />
        </div>
        <select
          value={locationId}
          onChange={(e) => {
            setLocationId(e.target.value)
            setWarehouseId("") // reset warehouse filter if location changes
          }}
          className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm cursor-pointer focus:outline-none focus:border-primary"
        >
          <option value="">All locations</option>
          {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
        <select
          value={warehouseId}
          onChange={(e) => setWarehouseId(e.target.value)}
          className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm cursor-pointer focus:outline-none focus:border-primary"
        >
          <option value="">Any warehouse</option>
          {warehouses.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm cursor-pointer focus:outline-none focus:border-primary"
        >
          <option value="">Any status</option>
          {Object.entries(STATUS_LABEL).map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
        <button
          onClick={() => setAvailableOnly((v) => !v)}
          className={cn(
            "h-9 px-3 rounded-xl text-sm font-medium border transition-colors cursor-pointer",
            availableOnly
              ? "border-primary/30 bg-primary/10 text-primary"
              : "border-border text-muted-foreground hover:bg-muted",
          )}
        >
          Available only
        </button>
        <button
          onClick={() => setCompleteOnly((v) => !v)}
          className={cn(
            "h-9 px-3 rounded-xl text-sm font-medium border transition-colors cursor-pointer",
            completeOnly
              ? "border-primary/30 bg-primary/10 text-primary"
              : "border-border text-muted-foreground hover:bg-muted",
          )}
        >
          Complete only
        </button>
      </div>

      {/* kits list */}
      {isLoading ? (
        <div className="py-12 flex justify-center"><Spinner /></div>
      ) : (
        <div className="flex flex-col gap-3">
          {visible.map((k) => (
            <div
              key={k.id}
              onClick={() => setSelectedKitId(k.id)}
              className="p-4 rounded-2xl border border-border bg-card hover:border-primary/40 hover:shadow-xs transition-all cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-4 group"
            >
              <div className="flex items-center gap-4 min-w-0">
                {/* QR Code Matrix preview */}
                <div
                  className="shrink-0 p-1.5 bg-white rounded-xl border border-border shadow-2xs group-hover:border-primary/30 transition-colors"
                  onClick={(e) => e.stopPropagation()}
                >
                  <KitQrCode label={k.label} tokenOrId={k.id} size={72} showDownload={false} showCopyLink={false} />
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-base font-bold font-mono text-foreground group-hover:text-primary transition-colors">
                      {k.label}
                    </p>
                    <span className={cn("text-xs font-semibold px-2.5 py-0.5 rounded-full capitalize", STATUS_STYLE[k.status])}>
                      {STATUS_LABEL[k.status]}
                    </span>
                    {k.shortage_count > 0 ? (
                      <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400 flex items-center gap-1">
                        <AlertTriangle size={12} /> {k.shortage_count} missing
                      </span>
                    ) : (
                      <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 flex items-center gap-1">
                        <CheckCircle2 size={12} /> Complete
                      </span>
                    )}
                  </div>

                  {/* Location & Warehouse Details */}
                  <div className="flex items-center gap-2 mt-1.5 text-xs text-muted-foreground flex-wrap">
                    <span className="font-mono text-muted-foreground/80 font-medium">{k.template_code}</span>
                    <span>•</span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        setSelectedLocationId(k.current_location_id)
                      }}
                      title={`View ${k.location_name}`}
                      className="font-medium text-foreground hover:text-primary hover:underline transition-colors cursor-pointer"
                    >
                      {k.location_name}
                    </button>
                    <span>·</span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        setLocationId(k.current_location_id)
                        setWarehouseId(k.current_warehouse_id)
                      }}
                      title={`Filter to ${k.warehouse_name}`}
                      className="font-medium text-foreground hover:text-primary hover:underline transition-colors cursor-pointer"
                    >
                      {k.warehouse_name}
                    </button>
                    <span>•</span>
                    {k.holder_name ? (
                      <span className="text-primary font-semibold bg-primary/10 px-2 py-0.5 rounded-md">
                        with {k.holder_name}
                      </span>
                    ) : (
                      <span className="text-muted-foreground bg-muted px-2 py-0.5 rounded-md font-medium">
                        On shelf
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    downloadKitQrLabel(k.label, k.id)
                  }}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-background hover:bg-muted text-foreground rounded-xl transition-colors cursor-pointer"
                >
                  <Download size={13} /> Download QR
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedKitId(k.id)}
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-xl hover:opacity-90 transition-colors cursor-pointer shadow-2xs"
                >
                  <Eye size={13} /> View details
                </button>
              </div>
            </div>
          ))}

          {visible.length === 0 && (
            <div className="flex flex-col items-center justify-center gap-2 h-40 border border-dashed border-border rounded-2xl text-center px-6">
              <Layers size={20} className="text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                {kits.length === 0
                  ? "No kits yet — use “Add kits” to enter the fleet in one go."
                  : "No kits match those filters."}
              </p>
            </div>
          )}
        </div>
      )}

      {selectedKitId && (
        <KitModal kitId={selectedKitId} onClose={() => setSelectedKitId(null)} />
      )}

      {selectedLocationId && (
        <LocationModal locationId={selectedLocationId} onClose={() => setSelectedLocationId(null)} />
      )}

      {bulkOpen && <BulkCreateModal onClose={() => setBulkOpen(false)} />}
    </div>
  )
}

/** The first-day path: enter a whole shelf at once rather than one form per box. */
function BulkCreateModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data: templates = [] } = useQuery({ queryKey: ["inv-templates"], queryFn: getTemplatesApi })
  const { data: locations = [] } = useQuery({ queryKey: ["inv-locations"], queryFn: () => getLocationsApi() })

  const [templateId, setTemplateId] = useState("")
  const [locationId, setLocationId] = useState("")
  const [warehouseId, setWarehouseId] = useState("")
  const [count, setCount] = useState(1)
  const [complete, setComplete] = useState(true)
  const [error, setError] = useState("")

  const { data: warehouses = [] } = useQuery({
    queryKey: ["inv-warehouses", locationId],
    queryFn: () => getWarehousesApi(locationId || undefined),
    enabled: !!locationId,
  })

  const mutation = useMutation({
    mutationFn: bulkCreateKitsApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-kits"] })
      onClose()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not create the kits"),
  })

  return (
    <Modal title="Add kits" onClose={onClose} maxWidth="sm:max-w-xl max-w-xl">
      <p className="text-xs text-muted-foreground -mt-1">
        Labels continue from the highest existing number for that template, so this is safe to run again.
      </p>
      <Field label="Kit type">
        <select
          value={templateId}
          onChange={(e) => setTemplateId(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        >
          <option value="">Choose…</option>
          {templates.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.code})</option>)}
        </select>
      </Field>
      <Field label="Location">
        <select
          value={locationId}
          onChange={(e) => { setLocationId(e.target.value); setWarehouseId("") }}
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        >
          <option value="">Choose…</option>
          {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
      </Field>
      <Field label="Warehouse">
        <select
          value={warehouseId}
          onChange={(e) => setWarehouseId(e.target.value)}
          disabled={!locationId}
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm disabled:opacity-50"
        >
          <option value="">Choose…</option>
          {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
      </Field>
      <Field label="How many">
        <input
          type="number" min={1} max={200} value={count}
          onChange={(e) => setCount(Math.max(1, Number(e.target.value) || 1))}
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        />
      </Field>
      <label className="flex items-start gap-2 cursor-pointer">
        <input
          type="checkbox" checked={complete}
          onChange={(e) => setComplete(e.target.checked)}
          className="mt-0.5"
        />
        <span className="text-sm text-foreground">
          They&apos;re complete
          <span className="block text-xs text-muted-foreground">
            Fills each kit to its parts list. Untick if you&apos;ll count them one by one.
          </span>
        </span>
      </label>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      <ModalActions
        onCancel={onClose}
        onConfirm={() => {
          setError("")
          mutation.mutate({ template_id: templateId, warehouse_id: warehouseId, count, complete })
        }}
        loading={mutation.isPending}
        disabled={!templateId || !warehouseId}
        label={`Add ${count} kit${count === 1 ? "" : "s"}`}
      />
    </Modal>
  )
}
