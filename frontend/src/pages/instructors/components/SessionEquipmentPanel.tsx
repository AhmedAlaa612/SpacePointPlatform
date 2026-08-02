import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Backpack, Package, Plus, Search } from "lucide-react"
import {
  getWarehousesApi,
  getSessionEquipmentApi,
  returnEquipmentApi,
  searchEquipmentApi,
  takeEquipmentApi,
  type EquipmentSearchResult,
} from "@/api/inventory"
import { updateSessionNotesApi } from "@/api/sessions/delivery"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Modal, Field, ModalActions } from "@/pages/admin/components/common"

/**
 * Non-kit equipment an instructor takes to a session (I2-7) — a mic speaker,
 * a battery charger, a roll of stickers, a bag of T-shirts.
 *
 * Today this is WhatsApp photos and never reaches a system. Three things make
 * the difference between a form that gets filled in and one that doesn't:
 *
 * - **The "add something" modal shows the whole shelf as a photo grid, with
 *   a search box to narrow it (2026-08-01).** The shelf still renders up
 *   front rather than waiting for input — a search that shows nothing until
 *   you guess right is worse than a short list — but images plus a filter
 *   let someone recognise a part by sight or narrow a long shelf by name.
 * - **Nobody is asked where they collected from.** Ops moves the kits to the
 *   session's warehouse first, so the kits' location already *is* the
 *   collection point. The dropdown appears only when there is nothing to
 *   derive from — no kits, or kits in more than one place.
 * - **"Returning later" is a real answer**, recorded as the line staying
 *   outstanding rather than as a state nobody will come back and correct.
 *
 * Unlike the kits panel this renders even with nothing taken, because taking
 * something is the action being offered. It stays one collapsed line until
 * there is something to show.
 */
export function SessionEquipmentPanel({
  sessionId,
  notes,
  onChanged,
}: {
  sessionId: string
  notes: string | null | undefined
  onChanged: () => void
}) {
  const qc = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [returning, setReturning] = useState(false)

  const { data } = useQuery({
    queryKey: ["session-equipment", sessionId],
    queryFn: () => getSessionEquipmentApi(sessionId),
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["session-equipment", sessionId] })
    onChanged()
  }

  if (!data) return null

  return (
    <Card>
      <CardContent className="p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Backpack size={15} /> Anything else you took?
          </p>
          {data.outstanding_count > 0 && (
            <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
              {data.outstanding_count} still out
            </span>
          )}
        </div>

        {data.lines.length === 0 ? (
          <p className="text-xs text-muted-foreground -mt-1">
            Stickers, a speaker, a charger, T-shirts — anything that isn&apos;t a kit.
            {data.warehouse_name && ` Picked up from ${data.warehouse_name}.`}
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {data.lines.map((line) => (
              <div
                key={line.item_id}
                className="flex items-center justify-between gap-3 rounded-xl border border-border bg-background/50 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{line.item_name}</p>
                  <p className="text-xs text-muted-foreground">
                    Took {line.qty_taken}
                    {line.qty_returned > 0 && ` · brought back ${line.qty_returned}`}
                  </p>
                </div>
                <span className="text-xs shrink-0 font-medium">
                  {line.outstanding > 0 ? (
                    <span className="text-amber-700 dark:text-amber-400">
                      {line.outstanding} with you
                    </span>
                  ) : (
                    <span className="text-emerald-600 dark:text-emerald-400">All back</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
            <Plus size={14} className="mr-1.5" /> Add something
          </Button>
          {data.outstanding_count > 0 && (
            <Button size="sm" variant="outline" onClick={() => setReturning(true)}>
              Bring it back
            </Button>
          )}
        </div>

        <SessionNotes sessionId={sessionId} notes={notes} onSaved={onChanged} />
      </CardContent>

      {adding && (
        <TakeModal
          sessionId={sessionId}
          warehouseId={data.warehouse_id}
          warehouseName={data.warehouse_name}
          onClose={() => setAdding(false)}
          onDone={() => { setAdding(false); refresh() }}
        />
      )}
      {returning && (
        <ReturnModal
          sessionId={sessionId}
          lines={data.lines.filter((l) => l.outstanding > 0)}
          warehouseId={data.warehouse_id}
          warehouseName={data.warehouse_name}
          onClose={() => setReturning(false)}
          onDone={() => { setReturning(false); refresh() }}
        />
      )}
    </Card>
  )
}

/**
 * The catch-all comment box (operator, 2026-07-30).
 *
 * Its immediate job is to absorb what the rest of this panel cannot model:
 * equipment search can only offer what `stock_levels` knows about, so until
 * ops has entered the co-working stock, "I took a speaker that isn't in the
 * list" has nowhere to go. Without this the fact is just lost — and a system
 * that silently drops what people tell it is how the last one ended up with
 * four empty tables.
 *
 * One text area, saved on blur. Deliberately not a comment log: the ask was
 * for something simple, and the known cost — a lead and a co-instructor
 * saving at the same moment overwrite each other — was accepted for that
 * simplicity. Saving on blur rather than per keystroke is the only mitigation
 * that costs nothing.
 */
function SessionNotes({ sessionId, notes, onSaved }: {
  sessionId: string
  notes: string | null | undefined
  onSaved: () => void
}) {
  const [error, setError] = useState("")
  const [saved, setSaved] = useState(false)

  const save = useMutation({
    mutationFn: (text: string) => updateSessionNotesApi(sessionId, text),
    onSuccess: () => {
      setError("")
      setSaved(true)
      onSaved()
    },
    onError: (e: any) =>
      setError(e?.response?.data?.detail ?? "Could not save that note"),
  })

  return (
    <div className="flex flex-col gap-1 border-t border-border pt-3">
      <label htmlFor={`notes-${sessionId}`} className="text-xs font-medium text-foreground">
        Comments
      </label>
      <textarea
        id={`notes-${sessionId}`}
        defaultValue={notes ?? ""}
        rows={3}
        placeholder="Anything worth noting — including things you took that aren't in the list yet."
        onFocus={() => setSaved(false)}
        onBlur={(e) => {
          if (e.target.value !== (notes ?? "")) save.mutate(e.target.value)
        }}
        className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-y"
      />
      <p className="text-xs text-muted-foreground">
        {save.isPending
          ? "Saving…"
          : saved
            ? "Saved — operations will see this on the session."
            : "Operations reads this on the session."}
      </p>
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}

/** B3: the whole shelf at the pickup point, shown as a photo grid and
 *  narrowable by a search box (2026-08-01) — recognise it by sight, or type
 *  a few letters when the shelf runs long. */
function TakeModal({ sessionId, warehouseId, warehouseName, onClose, onDone }: {
  sessionId: string
  warehouseId: string | null
  warehouseName: string | null
  onClose: () => void
  onDone: () => void
}) {
  const [picked, setPicked] = useState<Record<string, { row: EquipmentSearchResult; qty: number }>>({})
  const [chosenWarehouse, setChosenWarehouse] = useState("")
  const [search, setSearch] = useState("")
  const [error, setError] = useState("")

  // Only asked when there was nothing to derive from — the uncommon path.
  const needsWarehouse = warehouseId === null
  const effectiveWarehouse = warehouseId ?? (chosenWarehouse || null)

  const { data: warehouses = [] } = useQuery({
    queryKey: ["inv-warehouses"],
    queryFn: () => getWarehousesApi(),
    enabled: needsWarehouse,
  })

  const { data: shelf = [], isLoading } = useQuery({
    queryKey: ["equipment-shelf", sessionId, effectiveWarehouse],
    queryFn: () => searchEquipmentApi({ sessionId, warehouseId: effectiveWarehouse }),
    enabled: !!effectiveWarehouse,
  })

  const submit = useMutation({
    mutationFn: takeEquipmentApi,
    onSuccess: onDone,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not record that"),
  })

  const toggle = (row: EquipmentSearchResult) =>
    setPicked((p) => {
      if (p[row.item_id]) {
        const { [row.item_id]: _drop, ...rest } = p
        return rest
      }
      return { ...p, [row.item_id]: { row, qty: 1 } }
    })

  const setQty = (row: EquipmentSearchResult, qty: number) =>
    setPicked((p) => ({ ...p, [row.item_id]: { row, qty: Math.min(row.available, Math.max(1, qty || 1)) } }))

  const chosen = Object.values(picked)
  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    return q ? shelf.filter((row) => row.item_name.toLowerCase().includes(q)) : shelf
  }, [shelf, search])

  return (
    <Modal title="What else did you take?" onClose={onClose} maxWidth="max-w-xl">
      {needsWarehouse ? (
        <Field label="Where did you collect it from?">
          <select
            value={chosenWarehouse}
            onChange={(e) => { setChosenWarehouse(e.target.value); setPicked({}) }}
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
          >
            <option value="">Choose…</option>
            {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </Field>
      ) : (
        <p className="text-xs text-muted-foreground -mt-1">
          From {warehouseName}, where this session&apos;s kits are.
        </p>
      )}

      {effectiveWarehouse && shelf.length > 0 && (
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search this shelf…"
            className="w-full h-9 pl-8 pr-3 border border-border bg-background text-foreground rounded-xl text-sm"
          />
        </div>
      )}

      {effectiveWarehouse && (
        isLoading ? (
          <p className="text-sm text-muted-foreground py-2">Loading the shelf…</p>
        ) : shelf.length === 0 ? (
          <p className="text-sm text-muted-foreground py-2">
            Nothing is on record at this warehouse. Ask operations to add stock.
          </p>
        ) : visible.length === 0 ? (
          <p className="text-sm text-muted-foreground py-2">Nothing on this shelf matches that search.</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-[45vh] overflow-y-auto -mx-1 px-1 py-1">
            {visible.map((row) => {
              const isPicked = !!picked[row.item_id]
              return (
                <label
                  key={row.item_id}
                  className={`flex flex-col rounded-xl border overflow-hidden cursor-pointer transition-colors ${
                    isPicked ? "border-primary/50 bg-primary/5" : "border-border hover:bg-muted/60"
                  }`}
                >
                  <div className="relative w-full aspect-square bg-muted/40 flex items-center justify-center">
                    {row.image_url ? (
                      <img src={row.image_url} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <Package size={22} className="text-muted-foreground" />
                    )}
                    <input
                      type="checkbox"
                      checked={isPicked}
                      onChange={() => toggle(row)}
                      className="absolute top-1.5 left-1.5 rounded text-primary focus:ring-primary border-border bg-background shrink-0"
                    />
                    <span className="absolute bottom-1.5 right-1.5 text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-background/90 text-muted-foreground">
                      {row.available} there
                    </span>
                  </div>
                  <div className="p-1.5 flex flex-col gap-1">
                    <p className="text-xs font-medium text-foreground truncate" title={row.item_name}>
                      {row.item_name}
                    </p>
                    {isPicked && (
                      <input
                        type="number" min={1} max={row.available} value={picked[row.item_id].qty}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => setQty(row, Number(e.target.value))}
                        className="w-full h-7 px-1.5 border border-border bg-background text-foreground rounded-lg text-xs text-center tabular-nums"
                      />
                    )}
                  </div>
                </label>
              )
            })}
          </div>
        )
      )}

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      <ModalActions
        onCancel={onClose}
        onConfirm={() => {
          setError("")
          submit.mutate({
            sessionId,
            warehouseId: effectiveWarehouse,
            lines: chosen.map(({ row, qty }) => ({ item_id: row.item_id, qty })),
          })
        }}
        loading={submit.isPending}
        disabled={chosen.length === 0}
        label={chosen.length > 0 ? `Done — take ${chosen.length}` : "Done"}
      />
    </Modal>
  )
}

/** "Did you bring it back?" per line. Leaving a line at zero is the
 *  "returning later" answer — it stays outstanding, which is the truth. */
function ReturnModal({ sessionId, lines, warehouseId, warehouseName, onClose, onDone }: {
  sessionId: string
  lines: { item_id: string; item_name: string; outstanding: number }[]
  warehouseId: string | null
  warehouseName: string | null
  onClose: () => void
  onDone: () => void
}) {
  const [qtys, setQtys] = useState<Record<string, number>>(
    Object.fromEntries(lines.map((l) => [l.item_id, l.outstanding])),
  )
  const [chosenWarehouse, setChosenWarehouse] = useState("")
  const [error, setError] = useState("")

  const needsWarehouse = warehouseId === null
  const effectiveWarehouse = warehouseId ?? (chosenWarehouse || null)

  const { data: warehouses = [] } = useQuery({
    queryKey: ["inv-warehouses"],
    queryFn: () => getWarehousesApi(),
    enabled: needsWarehouse,
  })

  const submit = useMutation({
    mutationFn: returnEquipmentApi,
    onSuccess: onDone,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not record the return"),
  })

  const returning = lines
    .map((l) => ({ item_id: l.item_id, qty: qtys[l.item_id] ?? 0 }))
    .filter((l) => l.qty > 0)

  return (
    <Modal title="Did you bring it back?" onClose={onClose} maxWidth="max-w-md">
      <p className="text-xs text-muted-foreground -mt-1">
        Set anything you still have to zero — it stays on your list rather than being
        recorded as returned.
      </p>

      {needsWarehouse && (
        <Field label="Where are you leaving it?">
          <select
            value={chosenWarehouse} onChange={(e) => setChosenWarehouse(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
          >
            <option value="">Choose…</option>
            {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </Field>
      )}

      <div className="flex flex-col gap-1.5">
        {lines.map((l) => (
          <div key={l.item_id} className="flex items-center justify-between gap-3">
            <span className="text-sm text-foreground truncate">
              {l.item_name}
              <span className="text-xs text-muted-foreground"> / {l.outstanding}</span>
            </span>
            <input
              type="number" min={0} max={l.outstanding} value={qtys[l.item_id] ?? 0}
              onChange={(e) =>
                setQtys((q) => ({
                  ...q,
                  [l.item_id]: Math.min(l.outstanding, Math.max(0, Number(e.target.value) || 0)),
                }))
              }
              className="!w-16 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right tabular-nums"
            />
          </div>
        ))}
      </div>

      {!needsWarehouse && (
        <p className="text-xs text-muted-foreground">Going back to {warehouseName}.</p>
      )}
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      <ModalActions
        onCancel={onClose}
        onConfirm={() => {
          setError("")
          submit.mutate({ sessionId, lines: returning, toWarehouseId: effectiveWarehouse })
        }}
        loading={submit.isPending}
        disabled={returning.length === 0 || !effectiveWarehouse}
        label="Record it"
      />
    </Modal>
  )
}
