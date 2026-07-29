import { useState } from "react"
import { Link, useParams } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, ArrowLeft, CheckCircle2, MapPin, User as UserIcon } from "lucide-react"
import type { KitStatus, Movement } from "@/types/inventory"
import {
  getHoldersApi,
  getKitApi,
  getKitHistoryApi,
  getLocationsApi,
  moveKitApi,
  updateKitApi,
} from "@/api/inventory"
import { Field, Modal, ModalActions, Spinner } from "@/pages/admin/components/common"
import { cn } from "@/lib/utils"

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
  const [moveOpen, setMoveOpen] = useState(false)

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
      <Link to="/operations/inventory" className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground w-fit">
        <ArrowLeft size={14} /> All kits
      </Link>

      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-foreground tracking-tight font-mono">{kit.label}</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {kit.template_name} ({kit.template_code})
          </p>
          <div className="flex items-center gap-3 mt-2 text-sm">
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <MapPin size={14} /> {kit.location_name}
            </span>
            {kit.holder_name ? (
              <span className="flex items-center gap-1.5 text-foreground font-medium">
                <UserIcon size={14} /> with {kit.holder_name}
              </span>
            ) : (
              <span className="text-muted-foreground">on the shelf</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={kit.status}
            onChange={(e) => statusMutation.mutate({ id: kitId, status: e.target.value as KitStatus })}
            className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm cursor-pointer focus:outline-none focus:border-primary"
          >
            {STATUSES.map((s) => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}
          </select>
          <button
            onClick={() => setMoveOpen(true)}
            className="h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
          >
            {kit.holder_name ? "Take it back" : "Hand it out"}
          </button>
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
          <h2 className="text-sm font-semibold text-foreground">What&apos;s in it</h2>
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

      {moveOpen && (
        <MoveModal
          kitId={kitId}
          isOut={!!kit.holder_name}
          onClose={() => setMoveOpen(false)}
        />
      )}
    </div>
  )
}

function HistoryRow({ movement, locationName }: {
  movement: Movement
  locationName: (id: string | null) => string | null
}) {
  const to = locationName(movement.to_location_id)
  const from = locationName(movement.from_location_id)
  const when = movement.created_at ? new Date(movement.created_at).toLocaleDateString() : ""

  return (
    <div className="px-4 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-foreground">
          {REASON_LABEL[movement.reason] ?? movement.reason}
          {movement.qty != null && <span className="text-muted-foreground"> · {movement.qty}×</span>}
        </p>
        <span className="text-xs text-muted-foreground shrink-0">{when}</span>
      </div>
      <p className="text-xs text-muted-foreground">
        {from && <>from {from} </>}
        {to && <>to {to}</>}
        {movement.due_back_on && <span className="text-amber-600 dark:text-amber-400"> · due back {movement.due_back_on}</span>}
        {movement.confirmed_at
          ? <span className="text-emerald-600 dark:text-emerald-400"> · confirmed</span>
          : movement.to_user_id && <span className="text-muted-foreground/70"> · not yet confirmed</span>}
      </p>
      {movement.note && <p className="text-xs text-muted-foreground/80 mt-0.5 italic">{movement.note}</p>}
    </div>
  )
}

function MoveModal({ kitId, isOut, onClose }: { kitId: string; isOut: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data: locations = [] } = useQuery({ queryKey: ["inv-locations"], queryFn: () => getLocationsApi() })
  const { data: holders = [] } = useQuery({ queryKey: ["inv-holders"], queryFn: getHoldersApi })

  // Returning a kit sends it back to a place; handing one out sends it to a
  // person. The API rejects both at once, so the form only offers one.
  const [toLocationId, setToLocationId] = useState("")
  const [toUserId, setToUserId] = useState("")
  const [dueBack, setDueBack] = useState("")
  const [note, setNote] = useState("")
  const [error, setError] = useState("")

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
    <Modal title={isOut ? "Take the kit back" : "Hand the kit out"} onClose={onClose}>
      {isOut ? (
        <Field label="Back to">
          <select
            value={toLocationId}
            onChange={(e) => setToLocationId(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
          >
            <option value="">Choose a location…</option>
            {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </Field>
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
            reason: isOut ? "return" : "issue",
            ...(isOut ? { to_location_id: toLocationId } : { to_user_id: toUserId }),
            ...(!isOut && dueBack ? { due_back_on: dueBack } : {}),
            ...(note ? { note } : {}),
          })
        }}
        loading={mutation.isPending}
        disabled={isOut ? !toLocationId : !toUserId}
        label={isOut ? "Take it back" : "Hand it out"}
      />
    </Modal>
  )
}
