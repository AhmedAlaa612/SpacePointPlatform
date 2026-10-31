import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, Package, Search } from "lucide-react"
import type { Item, WarehouseBox } from "@/types/inventory"
import { getItemCategoriesApi, getItemsApi, setWarehouseBoxItemsApi } from "@/api/inventory"
import { Modal } from "@/pages/admin/components/common"
import { cn } from "@/lib/utils"

export function BoxItemsModal({
  box,
  warehouseId,
  onClose,
}: {
  box: WarehouseBox
  warehouseId: string
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set(box.item_ids ?? []))
  const [search, setSearch] = useState("")
  const [category, setCategory] = useState("")
  const [error, setError] = useState("")

  const { data: items = [], isLoading } = useQuery({
    queryKey: ["inv-items"],
    queryFn: () => getItemsApi(),
  })

  const { data: categories = [] } = useQuery({
    queryKey: ["inv-categories"],
    queryFn: () => getItemCategoriesApi(),
  })

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      if (category && item.category !== category) return false
      if (search.trim() && !item.name.toLowerCase().includes(search.trim().toLowerCase())) return false
      return true
    })
  }, [items, category, search])

  const toggleItem = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const saveMutation = useMutation({
    mutationFn: () => setWarehouseBoxItemsApi(warehouseId, box.id, Array.from(selectedIds)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-warehouse-boxes", warehouseId] })
      queryClient.invalidateQueries({ queryKey: ["inv-warehouse-cabins", warehouseId] })
      queryClient.invalidateQueries({ queryKey: ["inv-stock"] })
      onClose()
    },
    onError: (err: any) => setError(err?.response?.data?.detail ?? "Could not save items to box"),
  })

  return (
    <Modal
      title={`Box Items · ${box.name}`}
      onClose={onClose}
      maxWidth="sm:max-w-2xl max-w-2xl"
    >
      <div className="flex flex-col gap-4">
        {error && (
          <p className="text-xs p-2.5 rounded-xl bg-red-50 dark:bg-red-950/30 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-900/50">
            {error}
          </p>
        )}

        <div className="flex flex-col sm:flex-row sm:items-center gap-2">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search components…"
              className="h-9 w-full pl-8 pr-3 border border-border bg-background text-foreground rounded-xl text-xs"
            />
          </div>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-xs capitalize shrink-0 w-full sm:w-auto"
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c.id} value={c.name}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        <div className="rounded-xl border border-border divide-y divide-border max-h-[380px] overflow-y-auto">
          {isLoading ? (
            <p className="p-4 text-xs text-muted-foreground text-center">Loading components…</p>
          ) : filteredItems.length === 0 ? (
            <p className="p-4 text-xs text-muted-foreground text-center">No components found.</p>
          ) : (
            filteredItems.map((item: Item) => {
              const checked = selectedIds.has(item.id)
              return (
                <div
                  key={item.id}
                  onClick={() => toggleItem(item.id)}
                  className={cn(
                    "flex items-center justify-between gap-3 px-3 py-2 text-xs transition-colors cursor-pointer select-none",
                    checked ? "bg-primary/10" : "hover:bg-muted/40",
                  )}
                >
                  <div className="flex items-center gap-2.5 min-w-0 flex-1">
                    <div
                      className={cn(
                        "w-5 h-5 rounded-md border flex items-center justify-center shrink-0 transition-colors",
                        checked ? "bg-primary border-primary text-primary-foreground" : "border-border bg-background",
                      )}
                    >
                      {checked && <Check size={12} strokeWidth={3} />}
                    </div>
                    {item.image_url ? (
                      <img src={item.image_url} alt="" className="w-7 h-7 rounded-lg object-cover border border-border shrink-0" />
                    ) : (
                      <div className="w-7 h-7 rounded-lg bg-muted flex items-center justify-center text-muted-foreground shrink-0 border border-border">
                        <Package size={13} />
                      </div>
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold text-foreground truncate">{item.name}</p>
                      <span className="text-[10px] text-muted-foreground capitalize">{item.category}</span>
                    </div>
                  </div>
                </div>
              )
            })
          )}
        </div>

        <div className="flex items-center justify-between pt-3 border-t border-border">
          <span className="text-xs font-semibold text-foreground">
            {selectedIds.size} component{selectedIds.size === 1 ? "" : "s"} selected
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="h-8 px-3 border border-border rounded-xl text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="h-8 px-4 bg-primary text-primary-foreground text-xs font-semibold rounded-xl hover:opacity-90 disabled:opacity-50 transition-opacity cursor-pointer"
            >
              {saveMutation.isPending ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
