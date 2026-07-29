import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Boxes, Clock, Pencil } from "lucide-react"
import type { StockLevel } from "@/types/inventory"
import {
  adjustStockApi,
  getItemsApi,
  getLocationsApi,
  getOverdueApi,
  getStockApi,
} from "@/api/inventory"
import { Field, Modal, ModalActions, Spinner } from "@/pages/admin/components/common"

export default function Stock() {
  const [locationId, setLocationId] = useState("")
  const [adjusting, setAdjusting] = useState<StockLevel | null>(null)
  const [addOpen, setAddOpen] = useState(false)

  const { data: locations = [] } = useQuery({ queryKey: ["inv-locations"], queryFn: () => getLocationsApi() })
  const { data: stock = [], isLoading } = useQuery<StockLevel[]>({
    queryKey: ["inv-stock", locationId],
    queryFn: () => getStockApi({ location_id: locationId || undefined }),
  })
  const { data: overdue = [] } = useQuery({ queryKey: ["inv-overdue"], queryFn: getOverdueApi })

  const byLocation = stock.reduce<Record<string, StockLevel[]>>((acc, level) => {
    (acc[level.location_name] ??= []).push(level)
    return acc
  }, {})

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-foreground tracking-tight">Stock</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Loose components and merchandise, by location</p>
        </div>
        <button
          onClick={() => setAddOpen(true)}
          className="h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
        >
          Record a count
        </button>
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

      <select
        value={locationId}
        onChange={(e) => setLocationId(e.target.value)}
        className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm w-fit cursor-pointer focus:outline-none focus:border-primary"
      >
        <option value="">All locations</option>
        {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
      </select>

      {isLoading ? <Spinner /> : (
        <div className="flex flex-col gap-6">
          {Object.entries(byLocation).map(([name, levels]) => (
            <section key={name} className="flex flex-col gap-2">
              <h2 className="text-sm font-semibold text-foreground">{name}</h2>
              <div className="rounded-2xl border border-border bg-card divide-y divide-border">
                {levels.map((level) => (
                  <div key={`${level.item_id}-${level.location_id}`} className="flex items-center justify-between px-4 py-2.5">
                    <span className="text-sm text-foreground">{level.item_name}</span>
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-muted-foreground tabular-nums">{level.qty}</span>
                      <button
                        onClick={() => setAdjusting(level)}
                        className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                        title="Correct this count"
                      >
                        <Pencil size={13} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}
          {stock.length === 0 && (
            <div className="flex flex-col items-center justify-center gap-2 h-40 border border-dashed border-border rounded-2xl text-center px-6">
              <Boxes size={20} className="text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                Nothing on the shelves yet — use “Record a count” to enter what&apos;s there.
              </p>
            </div>
          )}
        </div>
      )}

      {(adjusting || addOpen) && (
        <AdjustModal
          existing={adjusting}
          onClose={() => { setAdjusting(null); setAddOpen(false) }}
        />
      )}
    </div>
  )
}

/** Takes the counted total, not a change — that's what the person holding the
 *  clipboard actually knows. The reason is mandatory on purpose. */
function AdjustModal({ existing, onClose }: { existing: StockLevel | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data: items = [] } = useQuery({ queryKey: ["inv-items"], queryFn: () => getItemsApi() })
  const { data: locations = [] } = useQuery({ queryKey: ["inv-locations"], queryFn: () => getLocationsApi() })

  const [itemId, setItemId] = useState(existing?.item_id ?? "")
  const [locationId, setLocationId] = useState(existing?.location_id ?? "")
  const [qty, setQty] = useState(existing?.qty ?? 0)
  const [reason, setReason] = useState("")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: adjustStockApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-stock"] })
      onClose()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not record that"),
  })

  return (
    <Modal title={existing ? `Correct ${existing.item_name}` : "Record a count"} onClose={onClose}>
      {!existing && (
        <>
          <Field label="Item">
            <select
              value={itemId} onChange={(e) => setItemId(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
            >
              <option value="">Choose…</option>
              {items.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
            </select>
          </Field>
          <Field label="Location">
            <select
              value={locationId} onChange={(e) => setLocationId(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
            >
              <option value="">Choose…</option>
              {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </Field>
        </>
      )}

      <Field label="How many are actually there">
        <input
          type="number" min={0} value={qty}
          onChange={(e) => setQty(Math.max(0, Number(e.target.value) || 0))}
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        />
      </Field>
      <Field label="Why">
        <input
          value={reason} onChange={(e) => setReason(e.target.value)}
          placeholder="Stocktake, delivery arrived, one was broken…"
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        />
      </Field>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      <ModalActions
        onCancel={onClose}
        onConfirm={() => {
          setError("")
          mutation.mutate({ item_id: itemId, location_id: locationId, new_qty: qty, reason })
        }}
        loading={mutation.isPending}
        disabled={!itemId || !locationId || !reason.trim()}
        label="Record it"
      />
    </Modal>
  )
}
