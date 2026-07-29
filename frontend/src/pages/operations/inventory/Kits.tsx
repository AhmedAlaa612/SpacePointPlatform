import { useState } from "react"
import { Link } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2, Layers, Plus, Search } from "lucide-react"
import type { KitListItem, KitStatus } from "@/types/inventory"
import {
  bulkCreateKitsApi,
  getKitsApi,
  getLocationsApi,
  getTemplatesApi,
} from "@/api/inventory"
import { Field, Modal, ModalActions, Spinner } from "@/pages/admin/components/common"
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
  const [status, setStatus] = useState("")
  const [outOnly, setOutOnly] = useState(false)
  const [search, setSearch] = useState("")
  const [bulkOpen, setBulkOpen] = useState(false)

  const { data: locations = [] } = useQuery({ queryKey: ["inv-locations"], queryFn: () => getLocationsApi() })
  const { data: kits = [], isLoading } = useQuery<KitListItem[]>({
    queryKey: ["inv-kits", locationId, status, outOnly],
    queryFn: () => getKitsApi({
      location_id: locationId || undefined,
      status: status || undefined,
      out_only: outOnly || undefined,
    }),
  })

  const term = search.trim().toLowerCase()
  const visible = term
    ? kits.filter((k) =>
        k.label.toLowerCase().includes(term) ||
        (k.holder_name ?? "").toLowerCase().includes(term))
    : kits

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
          className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
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
          onChange={(e) => setLocationId(e.target.value)}
          className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm cursor-pointer focus:outline-none focus:border-primary"
        >
          <option value="">All locations</option>
          {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
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
          onClick={() => setOutOnly((v) => !v)}
          className={cn(
            "h-9 px-3 rounded-xl text-sm font-medium border transition-colors",
            outOnly
              ? "border-primary/30 bg-primary/10 text-primary"
              : "border-border text-muted-foreground hover:bg-muted",
          )}
        >
          Out with someone
        </button>
      </div>

      {isLoading ? <Spinner /> : (
        <div className="flex flex-col gap-2">
          {visible.map((k) => (
            <Link
              key={k.id}
              to="/operations/inventory/kits/$kitId"
              params={{ kitId: k.id }}
              className="flex items-center justify-between gap-3 p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-sm font-semibold text-foreground font-mono">{k.label}</p>
                  <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full", STATUS_STYLE[k.status])}>
                    {STATUS_LABEL[k.status]}
                  </span>
                  {k.shortage_count > 0 ? (
                    <span className="flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
                      <AlertTriangle size={11} />
                      {k.shortage_count} missing
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400">
                      <CheckCircle2 size={11} /> Complete
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground truncate mt-0.5">
                  {k.template_code} · {k.location_name}
                  {k.holder_name && <> · <span className="text-foreground/80">with {k.holder_name}</span></>}
                </p>
              </div>
            </Link>
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
  const [count, setCount] = useState(1)
  const [complete, setComplete] = useState(true)
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: bulkCreateKitsApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-kits"] })
      onClose()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not create the kits"),
  })

  return (
    <Modal title="Add kits" onClose={onClose}>
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
      <Field label="Where they are">
        <select
          value={locationId}
          onChange={(e) => setLocationId(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        >
          <option value="">Choose…</option>
          {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
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
          mutation.mutate({ template_id: templateId, location_id: locationId, count, complete })
        }}
        loading={mutation.isPending}
        disabled={!templateId || !locationId}
        label={`Add ${count} kit${count === 1 ? "" : "s"}`}
      />
    </Modal>
  )
}
