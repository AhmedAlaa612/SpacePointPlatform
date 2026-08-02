import { useState } from "react"
import { Link } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  ExternalLink,
  UserPlus,
} from "lucide-react"
import type { KitStatus } from "@/types/inventory"
import {
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

interface KitModalProps {
  kitId: string
  onClose: () => void
}

export function KitModal({ kitId, onClose }: KitModalProps) {
  const queryClient = useQueryClient()
  const [moveAction, setMoveAction] = useState<"warehouse" | "person" | null>(null)
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null)

  const { data: kit, isLoading } = useQuery({
    queryKey: ["inv-kit", kitId],
    queryFn: () => getKitApi(kitId),
  })
  const { data: history = [] } = useQuery({
    queryKey: ["inv-kit-history", kitId],
    queryFn: () => getKitHistoryApi(kitId),
  })
  const { data: locations = [] } = useQuery({
    queryKey: ["inv-locations"],
    queryFn: () => getLocationsApi(),
  })

  const statusMutation = useMutation({
    mutationFn: updateKitApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-kit", kitId] })
      queryClient.invalidateQueries({ queryKey: ["inv-kits"] })
    },
  })

  const locationName = (id: string | null) =>
    id ? locations.find((l) => l.id === id)?.name ?? "somewhere" : null

  return (
    <Modal title="" onClose={onClose} maxWidth="sm:max-w-4xl max-w-4xl">
      {isLoading || !kit ? (
        <div className="py-12 flex justify-center">
          <Spinner />
        </div>
      ) : (
        <div className="flex flex-col gap-6 -mt-3">
          {/* Header Bar */}
          <div className="flex items-center justify-between gap-3 border-b border-border pb-4">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-xl font-bold font-mono text-foreground">{kit.label}</h2>
                <span className="text-xs font-mono font-semibold px-2 py-0.5 rounded-md bg-secondary text-secondary-foreground">
                  {kit.template_code}
                </span>
                {kit.shortages.length > 0 ? (
                  <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
                    <AlertTriangle size={12} /> {kit.shortages.length} missing
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400">
                    <CheckCircle2 size={12} /> Complete
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">{kit.template_name}</p>
            </div>

            <Link
              to="/operations/inventory/kits/$kitId"
              params={{ kitId: kit.id }}
              className="inline-flex items-center gap-1 text-xs text-primary hover:underline font-medium"
            >
              Full view <ExternalLink size={12} />
            </Link>
          </div>

          {/* Kit Identity, QR & Current Location/Holder */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 bg-card rounded-2xl border border-border p-5">
            {/* QR Code Section */}
            <div className="flex flex-col items-center justify-center border-b md:border-b-0 md:border-r border-border pb-4 md:pb-0 md:pr-4">
              <KitQrCode
                label={kit.label}
                tokenOrId={kit.public_token || kit.id}
                size={135}
                showDownload={true}
                showCopyLink={true}
              />
            </div>

            {/* Holder & Location Details */}
            <div className="md:col-span-2 flex flex-col justify-between gap-4">
              <div className="flex flex-col gap-3">
                <div>
                  <p className="text-xs text-muted-foreground uppercase font-semibold tracking-wider mb-1">Current Warehouse</p>
                  <button
                    type="button"
                    onClick={() => setSelectedLocationId(kit.current_location_id)}
                    title={`View ${kit.warehouse_name || kit.location_name} inventory`}
                    className="w-full text-left text-sm font-semibold text-foreground bg-muted/50 hover:bg-muted px-3 py-2 rounded-xl transition-colors cursor-pointer flex items-center justify-between group/loc"
                  >
                    <span>{kit.warehouse_name || `${kit.location_name} Warehouse`}</span>
                    <ExternalLink size={13} className="text-muted-foreground group-hover/loc:text-primary transition-colors" />
                  </button>
                </div>

                <div>
                  <p className="text-xs text-muted-foreground uppercase font-semibold tracking-wider mb-1">With Whom</p>
                  {kit.holder_name ? (
                    <div className="text-sm font-semibold text-primary bg-primary/10 px-3 py-2 rounded-xl">
                      <span>{kit.holder_name}</span>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setSelectedLocationId(kit.current_location_id)}
                      title={`View ${kit.warehouse_name || kit.location_name} inventory`}
                      className="w-full text-left text-sm font-medium text-muted-foreground hover:text-foreground bg-muted/60 hover:bg-muted px-3 py-2 rounded-xl transition-colors cursor-pointer flex items-center justify-between group/loc"
                    >
                      <span>On shelf in {kit.warehouse_name || `${kit.location_name} Warehouse`}</span>
                      <ExternalLink size={13} className="group-hover/loc:text-primary transition-colors" />
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-2 pt-1 w-fit">
                  <span className="text-xs text-muted-foreground uppercase font-semibold tracking-wider shrink-0">Status:</span>
                  <select
                    value={kit.status}
                    onChange={(e) => statusMutation.mutate({ id: kitId, status: e.target.value as KitStatus })}
                    className="h-8 px-2.5 border border-border bg-background text-foreground rounded-lg text-xs font-medium cursor-pointer capitalize w-fit shrink-0"
                  >
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Change Holder Buttons */}
              <div className="flex items-center gap-2 flex-wrap pt-2 border-t border-border">
                <button
                  type="button"
                  onClick={() => setMoveAction("warehouse")}
                  className="flex-1 inline-flex items-center justify-center gap-1.5 h-9 px-3 border border-border text-foreground text-xs font-semibold rounded-xl hover:bg-muted transition-colors whitespace-nowrap cursor-pointer"
                >
                  <Building2 size={14} /> Move to warehouse
                </button>
                <button
                  type="button"
                  onClick={() => setMoveAction("person")}
                  className="flex-1 inline-flex items-center justify-center gap-1.5 h-9 px-3 bg-primary text-primary-foreground text-xs font-semibold rounded-xl hover:opacity-90 transition-colors whitespace-nowrap cursor-pointer"
                >
                  <UserPlus size={14} /> Assign to a person
                </button>
              </div>
            </div>
          </div>

          {/* Shortages Alert */}
          {kit.shortages.length > 0 ? (
            <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4">
              <p className="flex items-center gap-2 text-xs font-semibold text-amber-700 dark:text-amber-400">
                <AlertTriangle size={14} /> Missing {kit.shortages.length} item{kit.shortages.length === 1 ? "" : "s"}
              </p>
              <div className="mt-2.5 flex flex-col gap-1">
                {kit.shortages.map((s) => (
                  <div key={s.item_id} className="flex items-center justify-between text-xs">
                    <span className="text-foreground">{s.item_name}</span>
                    <span className="text-muted-foreground tabular-nums">
                      {s.actual} of {s.required} · <span className="text-amber-700 dark:text-amber-400 font-medium">short {s.short_by}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3 text-xs font-medium text-emerald-700 dark:text-emerald-400">
              <CheckCircle2 size={14} /> Complete — everything on the parts list is accounted for
            </div>
          )}

          {/* Contents & History */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <section className="flex flex-col gap-2">
              <h3 className="text-xs font-semibold text-foreground uppercase tracking-wider">What&apos;s in it</h3>
              <div className="rounded-xl border border-border bg-card divide-y divide-border max-h-48 overflow-y-auto">
                {kit.contents.map((c) => (
                  <div key={c.item_id} className="flex items-center justify-between px-3 py-2 text-xs">
                    <span className="text-foreground">{c.item_name}</span>
                    <span className="text-muted-foreground tabular-nums font-mono">{c.qty}</span>
                  </div>
                ))}
                {kit.contents.length === 0 && (
                  <p className="px-3 py-4 text-xs text-muted-foreground text-center">Nothing recorded in this kit.</p>
                )}
              </div>
            </section>

            <section className="flex flex-col gap-2">
              <h3 className="text-xs font-semibold text-foreground uppercase tracking-wider">Recent History</h3>
              <div className="rounded-xl border border-border bg-card divide-y divide-border max-h-48 overflow-y-auto">
                {history.slice(0, 5).map((m) => (
                  <div key={m.id} className="px-3 py-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-foreground">{REASON_LABEL[m.reason] ?? m.reason}</span>
                      <span className="text-[10px] text-muted-foreground">{m.created_at ? new Date(m.created_at).toLocaleDateString() : ""}</span>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      {locationName(m.from_location_id) && <>from {locationName(m.from_location_id)} </>}
                      {locationName(m.to_location_id) && <>to {locationName(m.to_location_id)}</>}
                    </p>
                  </div>
                ))}
                {history.length === 0 && (
                  <p className="px-3 py-4 text-xs text-muted-foreground text-center">No history yet.</p>
                )}
              </div>
            </section>
          </div>

          {/* Sessions calendar */}
          <section className="flex flex-col gap-2">
            <h3 className="text-xs font-semibold text-foreground uppercase tracking-wider">Sessions</h3>
            <div className="rounded-xl border border-border bg-card p-3 max-w-xs">
              <KitSessionsCalendar kitId={kitId} compact />
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
        </div>
      )}
    </Modal>
  )
}

function MoveModal({ kitId, action, hasHolder, onClose }: {
  kitId: string
  action: "warehouse" | "person"
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
    <Modal title={action === "warehouse" ? "Move to a warehouse" : "Assign to a person"} onClose={onClose}>
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
