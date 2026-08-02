import { useMemo, useState } from "react"
import { Link, useParams } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, ArrowLeft, Building2, CheckCircle2, ClipboardList, ExternalLink, UserPlus } from "lucide-react"
import type { KitDetail as KitDetailType, KitStatus, Movement } from "@/types/inventory"
import {
  countKitApi,
  getHoldersApi,
  getKitApi,
  getKitHistoryApi,
  getLocationsApi,
  getWarehousesApi,
  moveKitApi,
  updateKitApi,
} from "@/api/inventory"
import { Field, Modal, ModalActions, Spinner } from "@/pages/admin/components/common"
import { KitQrCode } from "@/components/ui/KitQrCode"
import { LocationModal } from "@/pages/operations/inventory/LocationModal"
import { KitSessionsCalendar } from "@/pages/operations/inventory/KitSessionsCalendar"


const STATUSES: KitStatus[] = ["working", "damaged", "retired", "lost"]

const REASON_LABEL: Record<string, string> = {
  issue: "Handed out",
  return: "Returned",
  transfer: "Moved",
  refill: "Restocked",
  receive: "Received",
  writeoff: "Written off",
  adjust: "Count corrected",
  sold: "Sold",
}

export default function KitDetail() {
  const { kitId } = useParams({ from: "/auth/operations/inventory/kits/$kitId" })
  const queryClient = useQueryClient()
  const [moveAction, setMoveAction] = useState<"warehouse" | "person" | null>(null)
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null)
  const [counting, setCounting] = useState(false)

  const { data: kit, isLoading } = useQuery({ queryKey: ["inv-kit", kitId], queryFn: () => getKitApi(kitId) })
  const { data: history = [] } = useQuery({ queryKey: ["inv-kit-history", kitId], queryFn: () => getKitHistoryApi(kitId) })
  const { data: locations = [] } = useQuery({ queryKey: ["inv-locations"], queryFn: () => getLocationsApi() })

  const statusMutation = useMutation({
    mutationFn: updateKitApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-kit", kitId] })
      queryClient.invalidateQueries({ queryKey: ["inv-kits"] })
    },
  })

  if (isLoading || !kit) return <Spinner />

  const locationName = (id: string | null) =>
    id ? locations.find((l) => l.id === id)?.name ?? "somewhere" : null

  return (
    <div className="flex flex-col gap-6">
      <Link to="/operations/inventory" className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground w-fit transition-colors">
        <ArrowLeft size={14} /> All kits
      </Link>

      {/* Main Kit Identity Card with QR Code */}
      <div className="rounded-2xl border border-border bg-card p-6 flex flex-col md:flex-row gap-6 items-start justify-between">
        <div className="flex flex-col sm:flex-row items-start gap-5 min-w-0 flex-1">
          <KitQrCode
            label={kit.label}
            tokenOrId={kit.public_token || kit.id}
            size={130}
            showDownload={true}
            showCopyLink={true}
            className="shrink-0"
          />

          <div className="flex flex-col gap-2 min-w-0 flex-1">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-2xl font-bold text-foreground tracking-tight font-mono">{kit.label}</h1>
                <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-secondary text-secondary-foreground font-mono">
                  {kit.template_code}
                </span>
              </div>
              <p className="text-sm text-muted-foreground mt-0.5 font-medium">
                {kit.template_name}
              </p>
            </div>

            {/* Where or with whom the kit is right now */}
            <div className="flex flex-wrap items-center gap-3 mt-1 text-sm">
              <button
                type="button"
                onClick={() => setSelectedLocationId(kit.current_location_id)}
                title={`View ${kit.warehouse_name || kit.location_name} inventory`}
                className="text-foreground bg-muted/60 hover:bg-muted px-3 py-1.5 rounded-xl font-semibold transition-colors cursor-pointer inline-flex items-center gap-1 group/loc"
              >
                <span>{kit.warehouse_name || `${kit.location_name} Warehouse`}</span>
                <ExternalLink size={12} className="text-muted-foreground group-hover/loc:text-primary transition-colors" />
              </button>

              {kit.holder_name ? (
                <div className="text-primary bg-primary/10 px-3 py-1.5 rounded-xl font-semibold">
                  <span>with {kit.holder_name}</span>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setSelectedLocationId(kit.current_location_id)}
                  title={`View ${kit.warehouse_name || kit.location_name} inventory`}
                  className="text-muted-foreground hover:text-foreground bg-muted px-3 py-1.5 rounded-xl font-medium transition-colors cursor-pointer inline-flex items-center gap-1 group/loc"
                >
                  <span>On shelf in {kit.warehouse_name || `${kit.location_name} Warehouse`}</span>
                  <ExternalLink size={12} className="group-hover/loc:text-primary transition-colors" />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Action Controls & Status */}
        <div className="flex flex-col gap-3 shrink-0 w-full sm:w-auto">
          <div className="flex items-center gap-2 w-fit">
            <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider shrink-0">Status:</span>
            <select
              value={kit.status}
              onChange={(e) => statusMutation.mutate({ id: kitId, status: e.target.value as KitStatus })}
              className="h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm cursor-pointer focus:outline-none focus:border-primary shrink-0 transition-colors font-medium capitalize w-fit"
            >
              {STATUSES.map((s) => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}
            </select>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => setMoveAction("warehouse")}
              className="inline-flex items-center justify-center gap-1.5 h-9 px-4 border border-border text-foreground text-sm font-medium rounded-xl hover:bg-muted transition-colors whitespace-nowrap shrink-0 cursor-pointer"
            >
              <Building2 size={14} /> Move to warehouse
            </button>
            <button
              onClick={() => setMoveAction("person")}
              className="inline-flex items-center justify-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors whitespace-nowrap shrink-0 cursor-pointer"
            >
              <UserPlus size={14} /> Assign to a person
            </button>
          </div>
        </div>
      </div>

      {/* shortages first — this is the thing someone opened the page to find out */}
      {kit.shortages.length > 0 ? (
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4">
          <p className="flex items-center gap-2 text-sm font-semibold text-amber-700 dark:text-amber-400">
            <AlertTriangle size={15} /> Missing {kit.shortages.length} item{kit.shortages.length === 1 ? "" : "s"}
          </p>
          <div className="mt-3 flex flex-col gap-1.5">
            {kit.shortages.map((s) => (
              <div key={s.item_id} className="flex items-center justify-between text-sm">
                <span className="text-foreground">{s.item_name}</span>
                <span className="text-muted-foreground tabular-nums">
                  {s.actual} of {s.required} · <span className="text-amber-700 dark:text-amber-400 font-medium">short {s.short_by}</span>
                </span>
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground mt-3">
            Consumables (screws, wire) are never counted here — they&apos;d make this list permanent.
          </p>
        </div>
      ) : (
        <div className="flex items-center gap-2 rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-4 text-sm font-medium text-emerald-700 dark:text-emerald-400">
          <CheckCircle2 size={15} /> Complete — everything on the parts list is here
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* contents */}
        <section className="flex flex-col gap-2">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-foreground">What&apos;s in it</h2>
            <button
              onClick={() => setCounting(true)}
              className="flex items-center gap-1.5 h-7 px-2.5 border border-border bg-background text-foreground text-xs font-medium rounded-lg hover:bg-muted/60"
            >
              <ClipboardList size={12} /> Count this kit
            </button>
          </div>
          <div className="rounded-2xl border border-border bg-card divide-y divide-border">
            {kit.contents.map((c) => (
              <div key={c.item_id} className="flex items-center justify-between px-4 py-2.5 text-sm">
                <span className="text-foreground">{c.item_name}</span>
                <span className="text-muted-foreground tabular-nums">{c.qty}</span>
              </div>
            ))}
            {kit.contents.length === 0 && (
              <p className="px-4 py-6 text-sm text-muted-foreground text-center">Nothing recorded in this kit yet.</p>
            )}
          </div>
        </section>

        {/* history */}
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold text-foreground">History</h2>
          <div className="rounded-2xl border border-border bg-card divide-y divide-border max-h-[26rem] overflow-y-auto">
            {history.map((m) => (
              <HistoryRow key={m.id} movement={m} locationName={locationName} />
            ))}
            {history.length === 0 && (
              <p className="px-4 py-6 text-sm text-muted-foreground text-center">Nothing has happened to this kit yet.</p>
            )}
          </div>
        </section>
      </div>

      {/* sessions calendar */}
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-foreground">Sessions</h2>
        <div className="rounded-2xl border border-border bg-card p-4 max-w-md">
          <KitSessionsCalendar kitId={kitId} />
        </div>
      </section>

      {moveAction && (
        <MoveModal
          kitId={kitId}
          action={moveAction}
          hasHolder={!!kit.holder_name}
          onClose={() => setMoveAction(null)}
        />
      )}

      {selectedLocationId && (
        <LocationModal
          locationId={selectedLocationId}
          onClose={() => setSelectedLocationId(null)}
        />
      )}

      {counting && <CountKitModal kit={kit} onClose={() => setCounting(false)} />}
    </div>
  )
}

const REASON_PRESETS = ["Arrived complete", "Stocktake", "Correction"]

/** One item, one editable count, straight from the box — the direct write
 *  path the fulfilment queue can't offer (it only ever fixes a *shortage*,
 *  never lets someone say what's actually in the kit). Rows are the union of
 *  current contents and the template's expected lines, so an item missing
 *  entirely still gets a row to fill in.
 *
 *  `fromShelf` decides where the difference comes from/goes — see
 *  `count_kit()` on the backend for the four reason/destination combinations
 *  this maps to. */
function CountKitModal({ kit, onClose }: { kit: KitDetailType; onClose: () => void }) {
  const queryClient = useQueryClient()

  const rows = useMemo(() => {
    const byItem = new Map<string, { item_id: string; item_name: string; qty: number }>()
    for (const c of kit.contents) byItem.set(c.item_id, { item_id: c.item_id, item_name: c.item_name, qty: c.qty })
    for (const s of kit.shortages) {
      if (!byItem.has(s.item_id)) byItem.set(s.item_id, { item_id: s.item_id, item_name: s.item_name, qty: s.actual })
    }
    return Array.from(byItem.values()).sort((a, b) => a.item_name.localeCompare(b.item_name))
  }, [kit.contents, kit.shortages])

  const [values, setValues] = useState<Record<string, string>>(
    () => Object.fromEntries(rows.map((r) => [r.item_id, String(r.qty)])),
  )
  const [fromShelf, setFromShelf] = useState(false)
  const [reason, setReason] = useState("")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: countKitApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-kit", kit.id] })
      queryClient.invalidateQueries({ queryKey: ["inv-kit-history", kit.id] })
      queryClient.invalidateQueries({ queryKey: ["inv-kits"] })
      onClose()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not record that"),
  })

  const changedLines = rows.reduce<{ item_id: string; new_qty: number }[]>((acc, r) => {
    const raw = values[r.item_id]
    if (raw === undefined || raw.trim() === "") return acc
    const newQty = Math.max(0, Math.trunc(Number(raw)) || 0)
    if (newQty !== r.qty) acc.push({ item_id: r.item_id, new_qty: newQty })
    return acc
  }, [])

  return (
    <Modal title={`Count ${kit.label}`} onClose={onClose} maxWidth="sm:max-w-2xl max-w-2xl">
      <div className="flex flex-col gap-4">
        <div className="rounded-2xl border border-border divide-y divide-border max-h-72 overflow-y-auto">
          {rows.map((r) => (
            <div key={r.item_id} className="flex items-center justify-between gap-3 px-4 py-2">
              <span className="text-sm text-foreground truncate">{r.item_name}</span>
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-xs text-muted-foreground">was {r.qty}</span>
                <input
                  type="number" min={0}
                  value={values[r.item_id] ?? ""}
                  onChange={(e) => setValues((prev) => ({ ...prev, [r.item_id]: e.target.value }))}
                  className="w-20 h-8 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right"
                />
              </div>
            </div>
          ))}
          {rows.length === 0 && (
            <p className="px-4 py-6 text-sm text-muted-foreground text-center">Nothing on this kit&apos;s parts list yet.</p>
          )}
        </div>

        <label className="flex items-start gap-2 cursor-pointer">
          <input
            type="checkbox" checked={fromShelf}
            onChange={(e) => setFromShelf(e.target.checked)}
            className="mt-0.5"
          />
          <span className="text-sm text-foreground">
            Take the difference off the shelf at {kit.warehouse_name}
            <span className="block text-xs text-muted-foreground">
              Ticked: these parts genuinely came from (or go back to) that shelf. Unticked: the kit
              arrived already like this, or this is just a correction — nothing moves on the shelf.
            </span>
          </span>
        </label>

        <Field label="Why">
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-1.5 flex-wrap">
              {REASON_PRESETS.map((p) => (
                <button
                  key={p} type="button"
                  onClick={() => setReason(p)}
                  className="h-7 px-2.5 border border-border bg-background text-foreground text-xs font-medium rounded-lg hover:bg-muted/60"
                >
                  {p}
                </button>
              ))}
            </div>
            <input
              value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="Or describe it…"
              className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
            />
          </div>
        </Field>

        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

        <ModalActions
          onCancel={onClose}
          onConfirm={() => {
            setError("")
            if (changedLines.length === 0) { setError("Change at least one line"); return }
            if (!reason.trim()) { setError("A reason is required"); return }
            mutation.mutate({ kitId: kit.id, reason: reason.trim(), fromShelf, lines: changedLines })
          }}
          loading={mutation.isPending}
          disabled={rows.length === 0}
          label={changedLines.length ? `Save ${changedLines.length} change${changedLines.length === 1 ? "" : "s"}` : "Save"}
        />
      </div>
    </Modal>
  )
}

function HistoryRow({ movement, locationName }: {
  movement: Movement
  locationName: (id: string | null) => string | null
}) {
  const fromLoc = movement.from_location_name || locationName(movement.from_location_id)
  const toLoc = movement.to_location_name || locationName(movement.to_location_id)

  const fromText = movement.from_user_name || (fromLoc && movement.from_warehouse_name ? `${fromLoc} (${movement.from_warehouse_name})` : movement.from_warehouse_name || fromLoc)
  const toText = movement.to_user_name || (toLoc && movement.to_warehouse_name ? `${toLoc} (${movement.to_warehouse_name})` : movement.to_warehouse_name || toLoc)

  const when = movement.created_at ? new Date(movement.created_at).toLocaleDateString() : ""

  return (
    <div className="px-4 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-foreground">
          {REASON_LABEL[movement.reason] ?? movement.reason}
          {movement.qty != null && <span className="text-muted-foreground"> · {movement.qty}×</span>}
        </p>
        <span className="text-xs text-muted-foreground shrink-0">{when}</span>
      </div>
      <p className="text-xs text-muted-foreground mt-0.5">
        {fromText && <>from <span className="font-medium text-foreground/80">{fromText}</span> </>}
        {toText && <>to <span className="font-medium text-foreground/80">{toText}</span></>}
        {movement.due_back_on && <span className="text-amber-600 dark:text-amber-400 font-medium"> · due back {movement.due_back_on}</span>}
        {movement.confirmed_at
          ? <span className="text-emerald-600 dark:text-emerald-400 font-medium"> · confirmed</span>
          : movement.to_user_id && <span className="text-muted-foreground/70 font-medium"> · not yet confirmed</span>}
      </p>
      {movement.note && <p className="text-xs text-muted-foreground/80 mt-0.5 italic">{movement.note}</p>}
    </div>
  )
}

function MoveModal({ kitId, action, hasHolder, onClose }: {
  kitId: string
  /** The two things a kit can do (2026-08-01) — assigning it to a session
   *  lives in the cohort screen, not here. */
  action: "warehouse" | "person"
  /** Whether it's currently with someone — decides "return" vs "transfer"
   *  when moving to a warehouse. Either way it's the same form. */
  hasHolder: boolean
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const { data: locations = [] } = useQuery({
    queryKey: ["inv-locations"], queryFn: () => getLocationsApi(), enabled: action === "warehouse",
  })
  const { data: holders = [] } = useQuery({
    queryKey: ["inv-holders"], queryFn: getHoldersApi, enabled: action === "person",
  })

  const [locationId, setLocationId] = useState("")
  const [toWarehouseId, setToWarehouseId] = useState("")
  const [toUserId, setToUserId] = useState("")
  const [dueBack, setDueBack] = useState("")
  const [note, setNote] = useState("")
  const [error, setError] = useState("")

  const { data: warehouses = [] } = useQuery({
    queryKey: ["inv-warehouses", locationId],
    queryFn: () => getWarehousesApi(locationId || undefined),
    enabled: action === "warehouse" && !!locationId,
  })

  const mutation = useMutation({
    mutationFn: moveKitApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-kit", kitId] })
      queryClient.invalidateQueries({ queryKey: ["inv-kit-history", kitId] })
      queryClient.invalidateQueries({ queryKey: ["inv-kits"] })
      onClose()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not move the kit"),
  })

  return (
    <Modal title={action === "warehouse" ? "Move to a warehouse" : "Assign to a person"} onClose={onClose} maxWidth="sm:max-w-xl max-w-xl">
      {action === "warehouse" ? (
        <>
          <Field label="Location">
            <select
              value={locationId}
              onChange={(e) => { setLocationId(e.target.value); setToWarehouseId("") }}
              className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
            >
              <option value="">Choose a location…</option>
              {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </Field>
          <Field label="Warehouse">
            <select
              value={toWarehouseId}
              onChange={(e) => setToWarehouseId(e.target.value)}
              disabled={!locationId}
              className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm disabled:opacity-50"
            >
              <option value="">Choose a warehouse…</option>
              {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </Field>
        </>
      ) : (
        <>
          <Field label="To whom">
            <select
              value={toUserId}
              onChange={(e) => setToUserId(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
            >
              <option value="">Choose a person…</option>
              {holders.map((h) => <option key={h.id} value={h.id}>{h.full_name}</option>)}
            </select>
          </Field>
          <Field label="Due back (optional)">
            <input
              type="date" value={dueBack}
              onChange={(e) => setDueBack(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
            />
            <p className="text-xs text-muted-foreground mt-1">
              Leave empty if it stays with them indefinitely — only dated loans appear on the overdue list.
            </p>
          </Field>
        </>
      )}

      <Field label="Note (optional)">
        <input
          value={note} onChange={(e) => setNote(e.target.value)}
          placeholder="Anything worth remembering"
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        />
      </Field>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      <ModalActions
        onCancel={onClose}
        onConfirm={() => {
          setError("")
          mutation.mutate({
            id: kitId,
            reason: action === "warehouse" ? (hasHolder ? "return" : "transfer") : "issue",
            ...(action === "warehouse" ? { to_warehouse_id: toWarehouseId } : { to_user_id: toUserId }),
            ...(action === "person" && dueBack ? { due_back_on: dueBack } : {}),
            ...(note ? { note } : {}),
          })
        }}
        loading={mutation.isPending}
        disabled={action === "warehouse" ? !toWarehouseId : !toUserId}
        label={action === "warehouse" ? "Move it" : "Assign it"}
      />
    </Modal>
  )
}
