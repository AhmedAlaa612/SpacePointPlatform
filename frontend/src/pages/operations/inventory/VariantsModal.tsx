import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Trash2 } from "lucide-react"
import type { Item, StockLevel } from "@/types/inventory"
import { deleteItemApi, getItemsApi, getStockApi } from "@/api/inventory"
import { ConfirmDialog, Modal } from "@/pages/admin/components/common"
import { StockCountModal } from "@/pages/operations/inventory/StockCountModal"
import { useAuth } from "@/context/AuthContext"

/** "T-Shirt" opened as one card — every size, and where each one actually
 *  is. Each row is still a fully separate item underneath (its own stock
 *  rows, its own custody); this is purely a browsing/count surface over the
 *  `variant_group` items share. "Edit counts" reuses `StockCountModal`
 *  unchanged, scoped to that one variant. */
export function VariantsModal({ groupName, onClose }: { groupName: string; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { activeRole } = useAuth()
  const canDelete = activeRole === "admin"
  const [editing, setEditing] = useState<Item | null>(null)
  const [deletingItem, setDeletingItem] = useState<Item | null>(null)
  const [deleteError, setDeleteError] = useState("")

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteItemApi(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-items"] })
      setDeletingItem(null)
      setDeleteError("")
    },
    onError: (e: any) => setDeleteError(e?.response?.data?.detail ?? "Could not delete variant"),
  })

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
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-lg font-bold text-foreground tabular-nums mr-1">{total}</span>
                <button
                  onClick={() => setEditing(v)}
                  className="h-8 px-3 border border-border bg-background text-foreground text-xs font-medium rounded-lg hover:bg-muted/60 transition-colors"
                >
                  Edit counts
                </button>
                {canDelete && (
                  <button
                    onClick={() => {
                      setDeleteError("")
                      setDeletingItem(v)
                    }}
                    title="Delete variant component"
                    className="flex items-center justify-center h-8 w-8 border border-border bg-background text-muted-foreground hover:text-red-600 hover:border-red-300 dark:hover:border-red-800 rounded-lg transition-colors cursor-pointer"
                  >
                    <Trash2 size={13} />
                  </button>
                )}
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

      {deletingItem && (
        <ConfirmDialog
          title="Delete variant component?"
          description={`Are you sure you want to delete "${deletingItem.variant_label || deletingItem.name}"? This will permanently delete this component along with its stock counts and all movement history.`}
          confirmLabel="Delete"
          cancelLabel="Cancel"
          destructive
          pending={deleteMutation.isPending}
          error={deleteError}
          onCancel={() => {
            setDeletingItem(null)
            setDeleteError("")
          }}
          onConfirm={() => deleteMutation.mutate(deletingItem.id)}
        />
      )}
    </Modal>
  )
}
