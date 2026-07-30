import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Clock, PackageCheck, Wrench } from "lucide-react"
import {
  fulfilKitApi,
  getFulfilmentQueueApi,
  getLocationsApi,
  setAwaitingPartsApi,
  type FulfilmentKit,
} from "@/api/inventory"
import { Field, Modal, ModalActions, Spinner } from "@/pages/admin/components/common"

/**
 * The storekeeper's queue (I3-1) — the other half of the loop the
 * post-session check opens.
 *
 * An instructor counts a kit, finds four MPUs where there should be five, and
 * that shortage has to reach someone who can act. Until this page it was
 * visible on the kit's own detail view and nowhere else, which means it was
 * visible to nobody: a storekeeper does not browse kits one at a time.
 *
 * **There is no task list behind this.** The task *is* the shortage — it is
 * computed, and refilling the kit makes it disappear without anything being
 * closed. The one stored fact is "I looked and the shelf was empty", because
 * that is the one thing you cannot work out from the data.
 *
 * Each line shows what is on the shelf **at that kit's own location**, so the
 * page already says which lines can be closed today and which cannot, rather
 * than sending someone to the shelf to find out.
 */
export default function Fulfilment() {
  const [locationId, setLocationId] = useState("")
  const [fulfilling, setFulfilling] = useState<FulfilmentKit | null>(null)
  const [flagging, setFlagging] = useState<FulfilmentKit | null>(null)

  const { data: locations = [] } = useQuery({
    queryKey: ["inv-locations"], queryFn: () => getLocationsApi(),
  })
  const { data: queue = [], isLoading } = useQuery({
    queryKey: ["inv-fulfilment", locationId],
    queryFn: () => getFulfilmentQueueApi(locationId || undefined),
  })

  const waiting = queue.filter((k) => k.awaiting_parts_since)
  const actionable = queue.filter((k) => k.fixable_now > 0)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-foreground tracking-tight">Fulfilment</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Kits that are short something, and what it would take to fix them
          </p>
        </div>
        <select
          value={locationId} onChange={(e) => setLocationId(e.target.value)}
          className="h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        >
          <option value="">All warehouses</option>
          {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
      </div>

      {!isLoading && queue.length > 0 && (
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-muted text-foreground font-medium">
            {queue.length} kit{queue.length === 1 ? "" : "s"} short
          </span>
          {actionable.length > 0 && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 font-medium">
              <PackageCheck size={12} /> {actionable.length} fixable now
            </span>
          )}
          {waiting.length > 0 && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400 font-medium">
              <Clock size={12} /> {waiting.length} awaiting parts
            </span>
          )}
        </div>
      )}

      {isLoading ? (
        <Spinner />
      ) : queue.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-10 text-center">
          <PackageCheck size={22} className="mx-auto text-muted-foreground" />
          <p className="text-sm font-medium text-foreground mt-2">Nothing is short</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Every kit matches its parts list. Shortages land here after a session count.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {queue.map((kit) => (
            <KitCard
              key={kit.kit_id}
              kit={kit}
              onFulfil={() => setFulfilling(kit)}
              onFlag={() => setFlagging(kit)}
            />
          ))}
        </div>
      )}

      {fulfilling && (
        <FulfilModal kit={fulfilling} onClose={() => setFulfilling(null)} />
      )}
      {flagging && (
        <AwaitingModal kit={flagging} onClose={() => setFlagging(null)} />
      )}
    </div>
  )
}

function KitCard({ kit, onFulfil, onFlag }: {
  kit: FulfilmentKit
  onFulfil: () => void
  onFlag: () => void
}) {
  const waitingSince = kit.awaiting_parts_since
    ? new Date(kit.awaiting_parts_since).toLocaleDateString()
    : null

  return (
    <div className="rounded-2xl border border-border bg-card p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-foreground font-mono">{kit.label}</p>
          <p className="text-xs text-muted-foreground">
            {kit.template_name} · {kit.location_name}
            {kit.out_with_someone && " · out with someone"}
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={onFulfil}
            disabled={kit.fixable_now === 0}
            className="h-8 px-3 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
          >
            <Wrench size={12} className="inline mr-1" />
            Fulfil
          </button>
          <button
            onClick={onFlag}
            className="h-8 px-3 border border-border text-foreground text-xs font-medium rounded-lg hover:bg-muted transition-colors"
          >
            {waitingSince ? "Update" : "No stock"}
          </button>
        </div>
      </div>

      {waitingSince && (
        <p className="text-xs text-amber-700 dark:text-amber-400 flex items-start gap-1.5">
          <Clock size={12} className="mt-0.5 shrink-0" />
          <span>
            Awaiting parts since {waitingSince}
            {kit.awaiting_parts_note && ` — ${kit.awaiting_parts_note}`}
          </span>
        </p>
      )}

      <div className="flex flex-col gap-1">
        {kit.shortages.map((s) => {
          const canFix = s.available >= s.short_by
          return (
            <div
              key={s.item_id}
              className="flex items-center justify-between gap-3 text-sm py-1 border-t border-border/60 first:border-t-0"
            >
              <span className="text-foreground truncate">{s.item_name}</span>
              <span className="flex items-center gap-3 shrink-0 tabular-nums text-xs">
                <span className="text-muted-foreground">
                  {s.actual} / {s.required}
                </span>
                <span className={canFix
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-amber-700 dark:text-amber-400"}>
                  need {s.short_by} · {s.available} on shelf
                </span>
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** Prefilled with the smaller of "what's missing" and "what's there", so the
 *  common case — take exactly what closes the gap — is one click. */
function FulfilModal({ kit, onClose }: { kit: FulfilmentKit; onClose: () => void }) {
  const qc = useQueryClient()
  const [qtys, setQtys] = useState<Record<string, number>>(
    Object.fromEntries(kit.shortages.map((s) => [s.item_id, Math.min(s.short_by, s.available)])),
  )
  const [error, setError] = useState("")

  const submit = useMutation({
    mutationFn: fulfilKitApi,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["inv-fulfilment"] })
      qc.invalidateQueries({ queryKey: ["inv-stock"] })
      onClose()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not fulfil that"),
  })

  const lines = kit.shortages
    .map((s) => ({ item_id: s.item_id, qty: qtys[s.item_id] ?? 0 }))
    .filter((l) => l.qty > 0)

  return (
    <Modal title={`Fulfil ${kit.label}`} onClose={onClose} maxWidth="max-w-md">
      <p className="text-xs text-muted-foreground -mt-1">
        Parts come off the shelf at {kit.location_name}, where this kit is.
      </p>

      <div className="flex flex-col gap-1.5 max-h-[45vh] overflow-y-auto">
        {kit.shortages.map((s) => (
          <div key={s.item_id} className="flex items-center justify-between gap-3">
            <span className="text-sm text-foreground truncate">
              {s.item_name}
              <span className="text-xs text-muted-foreground">
                {" "}· need {s.short_by}, {s.available} there
              </span>
            </span>
            <input
              type="number" min={0} max={Math.min(s.short_by, s.available)}
              value={qtys[s.item_id] ?? 0}
              onChange={(e) =>
                setQtys((q) => ({
                  ...q,
                  [s.item_id]: Math.min(
                    Math.min(s.short_by, s.available),
                    Math.max(0, Number(e.target.value) || 0),
                  ),
                }))
              }
              className="w-16 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right tabular-nums"
            />
          </div>
        ))}
      </div>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      <ModalActions
        onCancel={onClose}
        onConfirm={() => { setError(""); submit.mutate({ kitId: kit.kit_id, lines }) }}
        loading={submit.isPending}
        disabled={lines.length === 0}
        label="Put them in the kit"
      />
    </Modal>
  )
}

function AwaitingModal({ kit, onClose }: { kit: FulfilmentKit; onClose: () => void }) {
  const qc = useQueryClient()
  const [note, setNote] = useState(kit.awaiting_parts_note ?? "")
  const [error, setError] = useState("")

  const save = useMutation({
    mutationFn: setAwaitingPartsApi,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["inv-fulfilment"] })
      onClose()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not save that"),
  })

  return (
    <Modal title={`${kit.label} — awaiting parts`} onClose={onClose}>
      <p className="text-xs text-muted-foreground -mt-1 flex items-start gap-1.5">
        <AlertTriangle size={12} className="mt-0.5 shrink-0" />
        <span>
          Records that someone looked and there were none. Different from nobody having
          got to it yet, which is what the queue shows otherwise.
        </span>
      </p>

      <Field label="Note (optional)">
        <input
          value={note} onChange={(e) => setNote(e.target.value)}
          placeholder="On order, or none anywhere"
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        />
      </Field>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      <div className="flex flex-col gap-2">
        <ModalActions
          onCancel={onClose}
          onConfirm={() => {
            setError("")
            save.mutate({ kitId: kit.kit_id, awaiting: true, note: note || null })
          }}
          loading={save.isPending}
          label="Mark awaiting parts"
        />
        {kit.awaiting_parts_since && (
          <button
            onClick={() => {
              setError("")
              save.mutate({ kitId: kit.kit_id, awaiting: false })
            }}
            className="text-xs text-muted-foreground hover:text-foreground underline"
          >
            Clear the flag — parts turned up
          </button>
        )}
      </div>
    </Modal>
  )
}
