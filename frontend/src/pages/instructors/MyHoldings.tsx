import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Boxes, Package } from "lucide-react"
import {
  getWarehousesApi,
  getMyHeldItemsApi,
  getMyKitsApi,
  returnMyItemApi,
  returnMyKitApi,
} from "@/api/inventory"
import type { MyHeldItem, MyKit } from "@/types/inventory"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"
import { Modal, Field, ModalActions } from "@/pages/admin/components/common"

/**
 * Everything this person is currently holding — kits and items both,
 * wherever they came from: a session's "I'll bring this back later", or
 * something ops handed them directly (2026-08-01).
 *
 * No custody leg drives this — a kit's holder and an item's outstanding
 * ledger balance are already the source of truth. This page just reads them
 * and offers the one action either needs: bring it back, to a warehouse
 * that defaults to wherever it actually makes sense (the session it came
 * from, if there was one).
 */
export default function MyHoldings() {
  const qc = useQueryClient()
  const kits = useQuery({ queryKey: ["my-kits"], queryFn: getMyKitsApi })
  const items = useQuery({ queryKey: ["my-held-items"], queryFn: getMyHeldItemsApi })

  const [returningKit, setReturningKit] = useState<MyKit | null>(null)
  const [returningItem, setReturningItem] = useState<MyHeldItem | null>(null)

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["my-kits"] })
    qc.invalidateQueries({ queryKey: ["my-held-items"] })
  }

  if (kits.isLoading || items.isLoading) return <Spinner />

  const kitList = kits.data ?? []
  const itemList = items.data ?? []

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="What I'm holding" subtitle="Kits and equipment currently with you, from any session or a direct hand-out" />

      <section className="flex flex-col gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Boxes size={15} /> Kits
        </h2>
        {kitList.length === 0 ? (
          <p className="text-sm text-muted-foreground">No kits with you right now.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {kitList.map((k) => (
              <Card key={k.id}>
                <CardContent className="p-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground font-mono">{k.label}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {k.template_name}
                      {k.shortage_count > 0 && (
                        <span className="text-amber-600 dark:text-amber-400"> · {k.shortage_count} missing</span>
                      )}
                      {k.due_back_on && (
                        <span> · due back {new Date(k.due_back_on).toLocaleDateString()}</span>
                      )}
                    </p>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => setReturningKit(k)}>
                    Mark returned
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Package size={15} /> Items
        </h2>
        {itemList.length === 0 ? (
          <p className="text-sm text-muted-foreground">No equipment or merch with you right now.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {itemList.map((l) => (
              <Card key={l.item_id}>
                <CardContent className="p-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {l.item_name}
                      {l.variant_label && (
                        <span className="ml-1.5 text-xs font-semibold px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                          {l.variant_label}
                        </span>
                      )}
                      {" "}<span className="text-xs text-muted-foreground">× {l.qty}</span>
                    </p>
                    {l.due_back_on && (
                      <p className="text-xs text-muted-foreground">
                        Due back {new Date(l.due_back_on).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                  <Button size="sm" variant="outline" onClick={() => setReturningItem(l)}>
                    Mark returned
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      {kitList.length === 0 && itemList.length === 0 && (
        <EmptyState title="Nothing with you right now" hint="Kits and items you're holding will show up here." />
      )}

      {returningKit && (
        <ReturnKitModal
          kit={returningKit}
          onClose={() => setReturningKit(null)}
          onDone={() => { setReturningKit(null); refresh() }}
        />
      )}
      {returningItem && (
        <ReturnItemModal
          item={returningItem}
          onClose={() => setReturningItem(null)}
          onDone={() => { setReturningItem(null); refresh() }}
        />
      )}
    </div>
  )
}

function ReturnKitModal({ kit, onClose, onDone }: { kit: MyKit; onClose: () => void; onDone: () => void }) {
  const { data: warehouses = [] } = useQuery({
    queryKey: ["inv-warehouses"], queryFn: () => getWarehousesApi(),
  })
  const [chosenWarehouse, setChosenWarehouse] = useState(kit.default_return_warehouse_id ?? "")
  const [note, setNote] = useState("")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: returnMyKitApi,
    onSuccess: onDone,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not record the return"),
  })

  return (
    <Modal title={`Return ${kit.label}`} onClose={onClose}>
      <div className="flex flex-col gap-4">
        <Field label="Return to warehouse">
          <select
            value={chosenWarehouse} onChange={(e) => setChosenWarehouse(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
          >
            <option value="">Choose a warehouse…</option>
            {warehouses.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name} {w.id === kit.default_return_warehouse_id ? "(Default — origin)" : ""}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Note (optional)">
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. Returned to shelf 2, missing 1 screwdriver"
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
          />
        </Field>

        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
        <ModalActions
          onCancel={onClose}
          onConfirm={() => {
            setError("")
            mutation.mutate({ kitId: kit.id, toWarehouseId: chosenWarehouse || null, note: note.trim() || null })
          }}
          loading={mutation.isPending}
          disabled={!chosenWarehouse}
          label="Mark returned"
        />
      </div>
    </Modal>
  )
}

function ReturnItemModal({ item, onClose, onDone }: { item: MyHeldItem; onClose: () => void; onDone: () => void }) {
  const { data: warehouses = [] } = useQuery({
    queryKey: ["inv-warehouses"], queryFn: () => getWarehousesApi(),
  })
  const [chosenWarehouse, setChosenWarehouse] = useState(item.default_warehouse_id ?? "")
  const [qty, setQty] = useState(item.qty)
  const [note, setNote] = useState("")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: returnMyItemApi,
    onSuccess: onDone,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not record the return"),
  })

  return (
    <Modal title={`Return ${item.item_name}`} onClose={onClose}>
      <div className="flex flex-col gap-4">
        <Field label="How many?">
          <input
            type="number" min={1} max={item.qty} value={qty}
            onChange={(e) => setQty(Math.max(1, Math.min(item.qty, Number(e.target.value) || 1)))}
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
          />
        </Field>

        <Field label="Return to warehouse">
          <select
            value={chosenWarehouse} onChange={(e) => setChosenWarehouse(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
          >
            <option value="">Choose a warehouse…</option>
            {warehouses.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name} {w.id === item.default_warehouse_id ? "(Default — origin)" : ""}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Note (optional)">
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. Left in storage box B"
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
          />
        </Field>

        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
        <ModalActions
          onCancel={onClose}
          onConfirm={() => {
            setError("")
            mutation.mutate({ itemId: item.item_id, qty, toWarehouseId: chosenWarehouse || null, note: note.trim() || null })
          }}
          loading={mutation.isPending}
          disabled={!chosenWarehouse}
          label="Mark returned"
        />
      </div>
    </Modal>
  )
}
