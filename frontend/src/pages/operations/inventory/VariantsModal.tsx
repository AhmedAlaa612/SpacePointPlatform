import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import type { Item, StockLevel } from "@/types/inventory"
import { getItemsApi, getStockApi } from "@/api/inventory"
import { Modal } from "@/pages/admin/components/common"
import { StockCountModal } from "@/pages/operations/inventory/StockCountModal"

/** "T-Shirt" opened as one card — every size, and where each one actually
 *  is. Each row is still a fully separate item underneath (its own stock
 *  rows, its own custody); this is purely a browsing/count surface over the
 *  `variant_group` items share. "Edit counts" reuses `StockCountModal`
 *  unchanged, scoped to that one variant. */
export function VariantsModal({ groupName, onClose }: { groupName: string; onClose: () => void }) {
  const [editing, setEditing] = useState<Item | null>(null)

  const { data: items = [] } = useQuery({ queryKey: ["inv-items"], queryFn: () => getItemsApi() })
  const { data: stock = [] } = useQuery<StockLevel[]>({ queryKey: ["inv-stock", "all"], queryFn: () => getStockApi() })

  const variants = useMemo(() => items
    .filter((i) => i.variant_group === groupName)
    .sort((a, b) => (a.variant_label ?? a.name).localeCompare(b.variant_label ?? b.name)),
  [items, groupName])

  const breakdownFor = (itemId: string) => {
    const rows = stock.filter((s) => s.item_id === itemId)
    const byLocation = new Map<string, { name: string; qty: number }>()
    for (const r of rows) {
      const entry = byLocation.get(r.location_id) ?? { name: r.location_name, qty: 0 }
      entry.qty += r.qty
      byLocation.set(r.location_id, entry)
    }
    return {
      total: rows.reduce((sum, r) => sum + r.qty, 0),
      breakdown: Array.from(byLocation.values()).sort((a, b) => b.qty - a.qty),
    }
  }

  return (
    <Modal title={groupName} onClose={onClose} maxWidth="sm:max-w-2xl max-w-2xl">
      <div className="flex flex-col gap-2">
        {variants.map((v) => {
          const { total, breakdown } = breakdownFor(v.id)
          return (
            <div
              key={v.id}
              className="flex items-center justify-between gap-3 rounded-xl border border-border px-3 py-2.5"
            >
              <div className="min-w-0">
                <p className="text-sm font-semibold text-foreground">{v.variant_label || v.name}</p>
                <p className="text-xs text-muted-foreground truncate">
                  {breakdown.length > 0
                    ? breakdown.map((b) => `${b.name} ${b.qty}`).join(" · ")
                    : "Not stocked anywhere"}
                </p>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <span className="text-lg font-bold text-foreground tabular-nums">{total}</span>
                <button
                  onClick={() => setEditing(v)}
                  className="h-8 px-3 border border-border bg-background text-foreground text-xs font-medium rounded-lg hover:bg-muted/60"
                >
                  Edit counts
                </button>
              </div>
            </div>
          )
        })}
        {variants.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-6">No variants found for this group.</p>
        )}
      </div>

      {editing && (
        <StockCountModal itemId={editing.id} itemName={editing.name} onClose={() => setEditing(null)} />
      )}
    </Modal>
  )
}
