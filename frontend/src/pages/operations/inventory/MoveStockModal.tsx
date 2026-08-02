import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, Trash2 } from "lucide-react"
import { getItemsApi, getWarehousesApi, moveStockApi } from "@/api/inventory"
import { Field, Modal, ModalActions } from "@/pages/admin/components/common"

type Mode = "transfer" | "receive"

interface Line {
  id: string
  itemId: string
  qty: number
}

function newLine(): Line {
  return { id: crypto.randomUUID(), itemId: "", qty: 1 }
}

/** The two things `move()` could always do but the UI never asked for:
 *  moving stock warehouse-to-warehouse, and receiving a delivery with the
 *  honest `receive` reason instead of faking it through a stocktake
 *  `adjust`. Each line is still its own `Movement` — this just loops
 *  `moveStockApi` once per line rather than adding a bulk endpoint move()
 *  doesn't have. */
export function MoveStockModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<Mode>("transfer")
  const [fromWarehouseId, setFromWarehouseId] = useState("")
  const [toWarehouseId, setToWarehouseId] = useState("")
  const [lines, setLines] = useState<Line[]>([newLine()])
  const [note, setNote] = useState("")
  const [error, setError] = useState("")

  const { data: items = [] } = useQuery({ queryKey: ["inv-items"], queryFn: () => getItemsApi() })
  const { data: warehouses = [] } = useQuery({ queryKey: ["inv-warehouses-all"], queryFn: () => getWarehousesApi() })

  const validLines = lines.filter((l) => l.itemId && l.qty > 0)
  const destinationsChosen = mode === "transfer"
    ? !!fromWarehouseId && !!toWarehouseId && fromWarehouseId !== toWarehouseId
    : !!toWarehouseId

  const mutation = useMutation({
    mutationFn: async () => {
      for (const line of validLines) {
        await moveStockApi({
          item_id: line.itemId,
          qty: line.qty,
          reason: mode,
          ...(mode === "transfer" ? { from_warehouse_id: fromWarehouseId } : {}),
          to_warehouse_id: toWarehouseId,
          note: note.trim() || null,
        })
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-stock"] })
      onClose()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not move that"),
  })

  return (
    <Modal title={mode === "transfer" ? "Transfer stock" : "Receive a delivery"} onClose={onClose} maxWidth="sm:max-w-2xl max-w-2xl">
      <div className="flex flex-col gap-4">
        <div className="flex gap-1.5 p-1 bg-muted rounded-xl w-fit">
          {(["transfer", "receive"] as Mode[]).map((m) => (
            <button
              key={m} type="button"
              onClick={() => { setMode(m); setError("") }}
              className={`h-8 px-3 rounded-lg text-xs font-medium transition-colors ${
                mode === m ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {m === "transfer" ? "Transfer between warehouses" : "Receive a delivery"}
            </button>
          ))}
        </div>

        {mode === "transfer" ? (
          <div className="grid grid-cols-2 gap-3">
            <Field label="From">
              <select
                value={fromWarehouseId} onChange={(e) => setFromWarehouseId(e.target.value)}
                className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
              >
                <option value="">Choose…</option>
                {warehouses.map((w) => <option key={w.id} value={w.id}>{w.location_name ? `${w.location_name} · ${w.name}` : w.name}</option>)}
              </select>
            </Field>
            <Field label="To">
              <select
                value={toWarehouseId} onChange={(e) => setToWarehouseId(e.target.value)}
                className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
              >
                <option value="">Choose…</option>
                {warehouses.filter((w) => w.id !== fromWarehouseId).map((w) => (
                  <option key={w.id} value={w.id}>{w.location_name ? `${w.location_name} · ${w.name}` : w.name}</option>
                ))}
              </select>
            </Field>
          </div>
        ) : (
          <Field label="Arriving at">
            <select
              value={toWarehouseId} onChange={(e) => setToWarehouseId(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
            >
              <option value="">Choose a warehouse…</option>
              {warehouses.map((w) => <option key={w.id} value={w.id}>{w.location_name ? `${w.location_name} · ${w.name}` : w.name}</option>)}
            </select>
            <p className="text-xs text-muted-foreground mt-1">
              Receiving straight into a kit instead? Use "Count this kit" on the kit's own page.
            </p>
          </Field>
        )}

        <div className="flex flex-col gap-2">
          <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Item & Quantity</label>
          {lines.map((line, i) => (
            <div key={line.id} className="flex items-center gap-2">
              <select
                value={line.itemId}
                onChange={(e) => setLines((ls) => ls.map((l) => l.id === line.id ? { ...l, itemId: e.target.value } : l))}
                className="flex-1 shrink min-w-0 h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
              >
                <option value="">Choose an item…</option>
                {items.map((it) => <option key={it.id} value={it.id}>{it.name}</option>)}
              </select>
              <input
                type="number" min={1} value={line.qty}
                onChange={(e) => setLines((ls) => ls.map((l) => l.id === line.id ? { ...l, qty: Math.max(1, Number(e.target.value) || 1) } : l))}
                className="w-24 shrink-0 h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm text-right tabular-nums"
              />
              {lines.length > 1 && (
                <button
                  type="button"
                  onClick={() => setLines((ls) => ls.filter((_, idx) => idx !== i))}
                  className="p-2 text-muted-foreground hover:text-red-600 dark:hover:text-red-400 shrink-0"
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          ))}
          <button
            type="button"
            onClick={() => setLines((ls) => [...ls, newLine()])}
            className="flex items-center gap-1.5 h-8 px-2 text-xs font-medium text-primary hover:underline w-fit"
          >
            <Plus size={12} /> Add another item
          </button>
        </div>

        <Field label="Note (optional)">
          <input
            value={note} onChange={(e) => setNote(e.target.value)}
            placeholder={mode === "transfer" ? "Why it's moving" : "Supplier, PO number…"}
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
          />
        </Field>

        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

        <ModalActions
          onCancel={onClose}
          onConfirm={() => { setError(""); mutation.mutate() }}
          loading={mutation.isPending}
          disabled={validLines.length === 0 || !destinationsChosen}
          label={mode === "transfer" ? "Transfer it" : "Receive it"}
        />
      </div>
    </Modal>
  )
}
