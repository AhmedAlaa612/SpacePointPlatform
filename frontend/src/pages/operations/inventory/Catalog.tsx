import { useMemo, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Boxes, ImagePlus, MapPin, Pencil, Plus, Search, Tag, Trash2, X } from "lucide-react"
import type { City, Item, ItemCategory, ItemCategoryDef, KitTemplate, Location, StockLevel, Warehouse } from "@/types/inventory"
import {
  createCityApi,
  createItemApi,
  createItemCategoryApi,
  createLocationApi,
  createTemplateApi,
  createWarehouseApi,
  deleteItemCategoryApi,
  deleteTemplateApi,
  getCitiesApi,
  getItemCategoriesApi,
  getItemsApi,
  getLocationsApi,
  getWarehousesApi,
  getStockApi,
  getTemplateApi,
  getTemplatesApi,
  removeItemImageApi,
  setItemImageApi,
  setTemplateItemsApi,
  updateCityApi,
  updateItemApi,
  updateItemCategoryApi,
  updateLocationApi,
  updateTemplateApi,
  updateWarehouseApi,
} from "@/api/inventory"
import { Field, Modal, ModalActions, Spinner } from "@/pages/admin/components/common"
import { StockCountModal } from "@/pages/operations/inventory/StockCountModal"
import { VariantsModal } from "@/pages/operations/inventory/VariantsModal"
import { CountrySelect } from "@/components/ui/CountrySelect"
import { cn } from "@/lib/utils"
import { getCountries } from "@/lib/countries"

type Tab = "templates" | "items" | "locations" | "cities" | "warehouses" | "categories"

export default function Catalog() {
  const [tab, setTab] = useState<Tab>("templates")

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold text-foreground tracking-tight">Catalogue</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          What a kit should contain, what we stock, and where things live
        </p>
      </div>

      <div className="flex gap-1 border-b border-border">
        {(["templates", "items", "locations", "cities", "warehouses", "categories"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors capitalize",
              tab === t
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "templates" && <Templates />}
      {tab === "items" && <Items />}
      {tab === "locations" && <Locations />}
      {tab === "cities" && <Cities />}
      {tab === "warehouses" && <Warehouses />}
      {tab === "categories" && <Categories />}
    </div>
  )
}

/* ── kit types + their parts list ──────────────────────────────────────── */

function Templates() {
  const queryClient = useQueryClient()
  const { data: templates = [], isLoading } = useQuery({ queryKey: ["inv-templates"], queryFn: getTemplatesApi })
  const [openId, setOpenId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<KitTemplate | null>(null)
  const [error, setError] = useState("")

  const remove = useMutation({
    mutationFn: deleteTemplateApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-templates"] })
      setError("")
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not delete that kit type"),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-4">
      <button
        onClick={() => setCreating(true)}
        className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 w-fit"
      >
        <Plus size={14} /> New kit type
      </button>

      <div className="flex flex-col gap-2">
        {templates.map((t) => (
          <div key={t.id} className="rounded-2xl border border-border bg-card">
            <div className="w-full flex items-center justify-between p-4 text-left gap-3">
              <button
                onClick={() => setOpenId(openId === t.id ? null : t.id)}
                className="flex-1 min-w-0 text-left"
              >
                <p className="text-sm font-medium text-foreground">{t.name}</p>
                <p className="text-xs text-muted-foreground font-mono">SP-{t.code}-0001</p>
              </button>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => setOpenId(openId === t.id ? null : t.id)}
                  className="text-xs text-muted-foreground px-2 py-1"
                >
                  {openId === t.id ? "Hide" : "Parts list"}
                </button>
                <button
                  onClick={() => setEditing(t)}
                  title="Edit"
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
                >
                  <Pencil size={14} />
                </button>
                <button
                  onClick={() => {
                    if (confirm(`Delete the kit type "${t.name}"? This only works if no kit was built from it.`)) {
                      remove.mutate(t.id)
                    }
                  }}
                  disabled={remove.isPending}
                  title="Delete"
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
            {openId === t.id && <TemplateLines templateId={t.id} />}
          </div>
        ))}
        {templates.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-10 border border-dashed border-border rounded-2xl">
            No kit types yet.
          </p>
        )}
      </div>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      {(creating || editing) && (
        <TemplateModal
          existing={editing}
          onClose={() => { setCreating(false); setEditing(null) }}
        />
      )}
    </div>
  )
}

function TemplateModal({ existing, onClose }: { existing?: KitTemplate | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const isEdit = !!existing
  const [name, setName] = useState(existing?.name ?? "")
  const [code, setCode] = useState(existing?.code ?? "")
  const [error, setError] = useState("")

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["inv-templates"] })

  const mutation = useMutation({
    mutationFn: () => isEdit
      ? updateTemplateApi({ id: existing!.id, name: name.trim(), code: code.trim() })
      : createTemplateApi({ name: name.trim(), code: code.trim() }),
    onSuccess: () => { invalidate(); onClose() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not save the kit type"),
  })

  return (
    <Modal title={isEdit ? `Edit ${existing!.name}` : "New kit type"} onClose={onClose} maxWidth="sm:max-w-xl max-w-xl">
      <Field label="Name">
        <input
          value={name} onChange={(e) => setName(e.target.value)}
          placeholder="SatKit v1, Mission Payload Kit…"
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        />
      </Field>
      <Field label="Code">
        <input
          value={code} onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="SATKIT"
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm font-mono uppercase"
        />
        <p className="text-xs text-muted-foreground mt-1">
          Label prefix — kits of this type are numbered SP-{code || "…"}-0001.
        </p>
      </Field>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      <ModalActions
        onCancel={onClose}
        onConfirm={() => { setError(""); mutation.mutate() }}
        loading={mutation.isPending}
        disabled={!name.trim() || !code.trim()}
        label={isEdit ? "Save" : "Create"}
      />
    </Modal>
  )
}

function TemplateLines({ templateId }: { templateId: string }) {
  const queryClient = useQueryClient()
  const { data: detail, isLoading } = useQuery({
    queryKey: ["inv-template", templateId],
    queryFn: () => getTemplateApi(templateId),
  })
  const { data: items = [] } = useQuery({ queryKey: ["inv-items"], queryFn: () => getItemsApi() })
  const [adding, setAdding] = useState(false)
  const [newItemId, setNewItemId] = useState("")
  const [newQty, setNewQty] = useState(1)

  // The API replaces the whole list, so every edit sends the full set — no
  // diffing on the client, and a half-applied edit is impossible.
  const save = useMutation({
    mutationFn: setTemplateItemsApi,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["inv-template", templateId] }),
  })

  if (isLoading || !detail) return <div className="px-4 pb-4"><Spinner /></div>

  const lines = detail.items.map((l) => ({ item_id: l.item_id, required_qty: l.required_qty }))

  return (
    <div className="border-t border-border px-4 py-3 flex flex-col gap-2">
      {detail.items.map((line) => (
        <div key={line.item_id} className="flex items-center justify-between gap-3">
          <span className="text-sm text-foreground">{line.item_name}</span>
          <div className="flex items-center gap-2">
            <input
              type="number" min={1} defaultValue={line.required_qty}
              onBlur={(e) => {
                const qty = Math.max(1, Number(e.target.value) || 1)
                if (qty === line.required_qty) return
                save.mutate({
                  id: templateId,
                  lines: lines.map((l) => l.item_id === line.item_id ? { ...l, required_qty: qty } : l),
                })
              }}
              className="w-16 h-8 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right tabular-nums"
            />
            <button
              onClick={() => save.mutate({ id: templateId, lines: lines.filter((l) => l.item_id !== line.item_id) })}
              className="text-xs text-muted-foreground hover:text-red-600 px-1"
            >
              Remove
            </button>
          </div>
        </div>
      ))}

      {detail.items.length === 0 && (
        <p className="text-sm text-muted-foreground py-2">
          No parts list yet — nothing will be reported missing until there is one.
        </p>
      )}

      {adding ? (
        <div className="flex items-center gap-2 pt-2 border-t border-border">
          <select
            value={newItemId} onChange={(e) => setNewItemId(e.target.value)}
            className="flex-1 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm"
          >
            <option value="">Choose an item…</option>
            {items
              .filter((i) => !detail.items.some((l) => l.item_id === i.id))
              .map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
          </select>
          <input
            type="number" min={1} value={newQty}
            onChange={(e) => setNewQty(Math.max(1, Number(e.target.value) || 1))}
            className="w-16 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right"
          />
          <button
            disabled={!newItemId}
            onClick={() => {
              save.mutate({ id: templateId, lines: [...lines, { item_id: newItemId, required_qty: newQty }] })
              setNewItemId(""); setNewQty(1); setAdding(false)
            }}
            className="h-9 px-3 bg-primary text-primary-foreground rounded-lg text-sm disabled:opacity-50"
          >
            Add
          </button>
        </div>
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="flex items-center gap-1.5 text-sm text-primary hover:underline w-fit pt-1"
        >
          <Plus size={13} /> Add a part
        </button>
      )}
    </div>
  )
}

/* ── items — a searchable, filterable image grid ─────────────────────────
 *
 * Matches the reference layout the operator wants: search + category filter
 * up top, an "Add Component" button, and a card per item with its photo,
 * category tag, total quantity (summed across every location, not just one),
 * and Adjust/Edit actions. The category-grouped read-only list this replaces
 * is gone — the filter dropdown does that job on demand instead.
 */

function Items() {
  const { data: items = [], isLoading } = useQuery({ queryKey: ["inv-items"], queryFn: () => getItemsApi() })
  const { data: categories = [] } = useQuery({ queryKey: ["inv-categories"], queryFn: () => getItemCategoriesApi() })
  const { data: stock = [] } = useQuery<StockLevel[]>({ queryKey: ["inv-stock", ""], queryFn: () => getStockApi() })

  const [search, setSearch] = useState("")
  const [category, setCategory] = useState("")
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Item | null>(null)
  const [counting, setCounting] = useState<Item | null>(null)
  const [viewingGroup, setViewingGroup] = useState<string | null>(null)

  const totalByItem = useMemo(() => {
    const totals: Record<string, number> = {}
    for (const level of stock) totals[level.item_id] = (totals[level.item_id] ?? 0) + level.qty
    return totals
  }, [stock])

  const filtered = items.filter((i) =>
    (!category || i.category === category) &&
    (!search.trim() || i.name.toLowerCase().includes(search.trim().toLowerCase())),
  )

  // Sized/variant merchandise (T-Shirt S/M/L…) browses as one card — the
  // representative is just whichever variant sorts first, only used for the
  // photo/category/returnable badge; the real per-variant detail lives in
  // VariantsModal. Ungrouped items render exactly as before.
  const cards = useMemo(() => {
    const byGroup = new Map<string, Item[]>()
    const singles: Item[] = []
    for (const item of filtered) {
      if (item.variant_group) {
        const members = byGroup.get(item.variant_group)
        if (members) members.push(item)
        else byGroup.set(item.variant_group, [item])
      } else {
        singles.push(item)
      }
    }
    const groupCards = Array.from(byGroup.entries()).map(([groupName, members]) => {
      const sorted = [...members].sort((a, b) => a.name.localeCompare(b.name))
      const total = sorted.reduce((sum, m) => sum + (totalByItem[m.id] ?? 0), 0)
      return { kind: "group" as const, groupName, representative: sorted[0], memberCount: sorted.length, total }
    })
    const singleCards = singles.map((item) => ({ kind: "single" as const, item }))
    return [...groupCards, ...singleCards].sort((a, b) => {
      const nameA = a.kind === "group" ? a.groupName : a.item.name
      const nameB = b.kind === "group" ? b.groupName : b.item.name
      return nameA.localeCompare(nameB)
    })
  }, [filtered, totalByItem])

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div className="flex items-end gap-3 flex-wrap">
          <Field label="Search components">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                value={search} onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name…"
                className="h-9 w-56 pl-8 pr-3 border border-border bg-background text-foreground rounded-xl text-sm"
              />
            </div>
          </Field>
          <Field label="Filter by category">
            <select
              value={category} onChange={(e) => setCategory(e.target.value)}
              className="h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm capitalize min-w-40"
            >
              <option value="">All categories</option>
              {categories.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
            </select>
          </Field>
        </div>
        <button
          onClick={() => setOpen(true)}
          className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90"
        >
          <Plus size={14} /> Add Component
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
        {cards.map((card) => {
          const item = card.kind === "group" ? card.representative : card.item
          const total = card.kind === "group" ? card.total : (totalByItem[item.id] ?? 0)
          const displayName = card.kind === "group" ? card.groupName : item.name
          return (
            <div key={card.kind === "group" ? card.groupName : item.id} className="rounded-2xl border border-border bg-card overflow-hidden flex flex-col">
              <ItemPhoto item={item} />
              <div className="p-3 flex flex-col gap-2 flex-1">
                <div>
                  <p className="text-sm font-semibold text-foreground truncate" title={displayName}>{displayName}</p>
                  <div className="flex items-center gap-1.5 flex-wrap mt-1">
                    <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground capitalize">
                      <Tag size={11} /> {item.category}
                    </span>
                    {card.kind === "group" && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground">
                        {card.memberCount} sizes
                      </span>
                    )}
                  </div>
                </div>
                {item.returnable_default && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400">
                      comes back
                    </span>
                  </div>
                )}
                <div className="mt-auto pt-1">
                  <p className="text-xs text-muted-foreground">Total Quantity</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">{total}</p>
                </div>
                <div className="flex flex-col gap-1.5 pt-1">
                  {card.kind === "group" ? (
                    <button
                      onClick={() => setViewingGroup(card.groupName)}
                      className="flex items-center justify-center gap-1.5 h-8 px-3 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:opacity-90"
                    >
                      <Boxes size={13} /> View sizes
                    </button>
                  ) : (
                    <button
                      onClick={() => setCounting(item)}
                      className="flex items-center justify-center gap-1.5 h-8 px-3 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:opacity-90"
                    >
                      <Boxes size={13} /> Adjust
                    </button>
                  )}
                  <button
                    onClick={() => setEditing(item)}
                    className="flex items-center justify-center gap-1.5 h-8 px-3 border border-border bg-background text-foreground text-xs font-medium rounded-lg hover:bg-muted/60"
                  >
                    <Pencil size={12} /> Edit{card.kind === "group" ? ` ${item.variant_label || item.name}` : ""}
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {filtered.length === 0 && (
        <p className="text-sm text-muted-foreground text-center py-10 border border-dashed border-border rounded-2xl">
          {items.length === 0 ? "No components yet." : "Nothing matches that search."}
        </p>
      )}

      {open && <ItemModal onClose={() => setOpen(false)} />}
      {editing && <ItemModal existing={editing} onClose={() => setEditing(null)} />}
      {counting && <StockCountModal itemId={counting.id} itemName={counting.name} onClose={() => setCounting(null)} />}
      {viewingGroup && <VariantsModal groupName={viewingGroup} onClose={() => setViewingGroup(null)} />}
    </div>
  )
}

/** Optional photo shown to instructors picking this off the shelf (B3).
 *  Click the thumbnail (or the placeholder) to upload/replace; the X removes it. */
function ItemPhoto({ item }: { item: Item }) {
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["inv-items"] })
  const upload = useMutation({ mutationFn: setItemImageApi, onSuccess: invalidate })
  const remove = useMutation({ mutationFn: removeItemImageApi, onSuccess: invalidate })

  return (
    <div className="relative group w-full aspect-square bg-muted/40 border-b border-border">
      <input
        ref={fileInput} type="file" accept="image/*" className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) upload.mutate({ id: item.id, file })
          e.target.value = ""
        }}
      />
      <button
        type="button"
        onClick={() => fileInput.current?.click()}
        title={item.image_url ? "Replace photo" : "Add a photo"}
        className="w-full h-full flex items-center justify-center overflow-hidden hover:opacity-80 transition-opacity"
      >
        {item.image_url ? (
          <img src={item.image_url} alt="" className="w-full h-full object-cover" />
        ) : (
          <ImagePlus size={28} className="text-muted-foreground" />
        )}
      </button>
      {item.image_url && (
        <button
          type="button"
          onClick={() => remove.mutate(item.id)}
          title="Remove photo"
          className="absolute top-2 right-2 w-6 h-6 rounded-full bg-red-600 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <X size={13} />
        </button>
      )}
    </div>
  )
}

function ItemModal({ existing, onClose }: { existing?: Item; onClose: () => void }) {
  const queryClient = useQueryClient()
  const isEdit = !!existing
  const { data: categories = [] } = useQuery({ queryKey: ["inv-categories"], queryFn: () => getItemCategoriesApi() })
  const { data: allItems = [] } = useQuery({ queryKey: ["inv-items"], queryFn: () => getItemsApi() })
  const [name, setName] = useState(existing?.name ?? "")
  const [category, setCategory] = useState<ItemCategory>(existing?.category ?? "")
  const [returnable, setReturnable] = useState(existing?.returnable_default ?? false)
  const [description, setDescription] = useState(existing?.description ?? "")
  const [variantGroup, setVariantGroup] = useState(existing?.variant_group ?? "")
  const [variantLabel, setVariantLabel] = useState(existing?.variant_label ?? "")
  const [error, setError] = useState("")

  const existingGroups = useMemo(
    () => Array.from(new Set(allItems.map((i) => i.variant_group).filter((g): g is string => !!g))).sort(),
    [allItems],
  )

  // Defensive: an item whose category name doesn't match any current row
  // (shouldn't happen — delete is refused while items use a category, and
  // rename relabels them) still needs its own value selectable so saving
  // the form doesn't silently change it to something else.
  const categoryOptions = existing && !categories.some((c) => c.name === existing.category)
    ? [{ id: "current", name: existing.category, sort_order: -1 }, ...categories]
    : categories

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["inv-items"] })

  const mutation = useMutation({
    mutationFn: () => isEdit
      ? updateItemApi({
          id: existing!.id, name, category,
          returnable_default: returnable, description: description.trim() || null,
          variant_group: variantGroup.trim() || null, variant_label: variantLabel.trim() || null,
        })
      : createItemApi({
          name, category, returnable_default: returnable,
          description: description.trim() || null,
          variant_group: variantGroup.trim() || null, variant_label: variantLabel.trim() || null,
        }),
    onSuccess: () => { invalidate(); onClose() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not save the item"),
  })

  return (
    <Modal title={isEdit ? `Edit ${existing!.name}` : "New component"} onClose={onClose} maxWidth="sm:max-w-xl max-w-xl">
      <Field label="Name">
        <input
          value={name} onChange={(e) => setName(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        />
      </Field>
      <Field label="Category">
        <select
          value={category} onChange={(e) => setCategory(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm capitalize"
        >
          {!category && <option value="">Choose…</option>}
          {categoryOptions.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
        </select>
      </Field>
      <Field label="Description (optional)">
        <textarea
          value={description ?? ""} onChange={(e) => setDescription(e.target.value)}
          rows={2}
          placeholder="Shown to instructors picking this up for a session."
          className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-y"
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Sized/variant of (optional)">
          <input
            value={variantGroup} onChange={(e) => setVariantGroup(e.target.value)}
            placeholder="e.g. T-Shirt"
            list="variant-group-options"
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
          />
          <datalist id="variant-group-options">
            {existingGroups.map((g) => <option key={g} value={g} />)}
          </datalist>
        </Field>
        <Field label="Size / variant label">
          <input
            value={variantLabel} onChange={(e) => setVariantLabel(e.target.value)}
            placeholder="e.g. L"
            disabled={!variantGroup.trim()}
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm disabled:opacity-50"
          />
        </Field>
      </div>
      {variantGroup.trim() && (
        <p className="text-xs text-muted-foreground -mt-2">
          Browses together with every other item under "{variantGroup.trim()}" in the catalogue and
          stock pages — stock and custody still count this item on its own.
        </p>
      )}

      <label className="flex items-start gap-2 cursor-pointer">
        <input type="checkbox" checked={returnable} onChange={(e) => setReturnable(e.target.checked)} className="mt-0.5" />
        <span className="text-sm text-foreground">
          Expected back
          <span className="block text-xs text-muted-foreground">
            Default when handing one to someone. Vests yes, T-shirts no.
          </span>
        </span>
      </label>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      <ModalActions
        onCancel={onClose}
        onConfirm={() => { setError(""); mutation.mutate() }}
        loading={mutation.isPending}
        disabled={!name.trim() || !category}
        label={isEdit ? "Save" : "Create"}
      />
    </Modal>
  )
}

/* ── categories ────────────────────────────────────────────────────────── */

function Categories() {
  const queryClient = useQueryClient()
  const { data: categories = [], isLoading } = useQuery({
    queryKey: ["inv-categories"],
    queryFn: () => getItemCategoriesApi(),
  })
  // Item counts per category, so the delete button can be disabled up front
  // instead of everyone discovering the 409 by trying.
  const { data: items = [] } = useQuery({ queryKey: ["inv-items"], queryFn: () => getItemsApi() })
  const countByCategory = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const i of items) counts[i.category] = (counts[i.category] ?? 0) + 1
    return counts
  }, [items])

  const [name, setName] = useState("")
  const [error, setError] = useState("")

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["inv-categories"] })
    queryClient.invalidateQueries({ queryKey: ["inv-items"] })
  }

  const create = useMutation({
    mutationFn: createItemCategoryApi,
    onSuccess: () => { invalidate(); setName("") },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not add that category"),
  })
  const remove = useMutation({
    mutationFn: deleteItemCategoryApi,
    onSuccess: () => { invalidate(); setError("") },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not delete that category"),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-4 max-w-lg">
      <p className="text-sm text-muted-foreground -mt-1">
        Groupings used across the catalogue, the "add a component" form and the equipment
        filter. Every category is editable; one still in use by a component can't be deleted —
        move those components to another category first.
      </p>

      <div className="rounded-2xl border border-border bg-card divide-y divide-border">
        {categories.map((c) => {
          const inUse = countByCategory[c.name] ?? 0
          return (
            <div key={c.id} className="flex items-center justify-between px-4 py-2.5 gap-3">
              <RenamableCategory category={c} onSaved={invalidate} />
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-xs text-muted-foreground tabular-nums">
                  {inUse} component{inUse === 1 ? "" : "s"}
                </span>
                <button
                  onClick={() => remove.mutate(c.id)}
                  disabled={inUse > 0 || remove.isPending}
                  title={inUse > 0 ? "Still in use — move its components first" : "Delete"}
                  className="text-xs text-red-600 dark:text-red-400 hover:underline disabled:text-muted-foreground disabled:no-underline disabled:cursor-not-allowed"
                >
                  Delete
                </button>
              </div>
            </div>
          )
        })}
        {categories.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-6">No categories yet.</p>
        )}
      </div>

      <div className="flex items-center gap-2">
        <input
          value={name} onChange={(e) => { setName(e.target.value); setError("") }}
          placeholder="New category name…"
          className="flex-1 h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        />
        <button
          disabled={!name.trim() || create.isPending}
          onClick={() => create.mutate(name.trim())}
          className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 disabled:opacity-50"
        >
          <Plus size={14} /> Add
        </button>
      </div>
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}

/** Click the name to rename in place — renaming re-labels every item already
 *  using the old name (handled server-side), so it never strands them. */
function RenamableCategory({ category, onSaved }: { category: ItemCategoryDef; onSaved: () => void }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(category.name)

  const mutation = useMutation({
    mutationFn: updateItemCategoryApi,
    onSuccess: () => { onSaved(); setEditing(false) },
  })

  if (!editing) {
    return (
      <button
        onClick={() => { setValue(category.name); setEditing(true) }}
        className="flex items-center gap-1.5 text-sm text-foreground capitalize hover:text-primary min-w-0 truncate"
      >
        <Tag size={13} className="shrink-0 text-muted-foreground" /> {category.name}
      </button>
    )
  }

  return (
    <input
      autoFocus
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => {
        const trimmed = value.trim()
        if (trimmed && trimmed.toLowerCase() !== category.name.toLowerCase()) {
          mutation.mutate({ id: category.id, name: trimmed })
        } else {
          setEditing(false)
        }
      }}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur() }}
      className="h-8 px-2 border border-border bg-background text-foreground rounded-lg text-sm flex-1 min-w-0"
    />
  )
}

/* ── locations ─────────────────────────────────────────────────────────── */

function Locations() {
  const { data: locations = [], isLoading } = useQuery({
    queryKey: ["inv-locations-all"],
    queryFn: () => getLocationsApi(true),
  })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Location | null>(null)

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground -mt-1">
        A location is a site — a workshop space, an office. No warehouse is
        created automatically; add one from the Warehouses tab once you
        actually need to hold stock here.
      </p>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 w-fit"
      >
        <Plus size={14} /> New location
      </button>

      <div className="rounded-2xl border border-border bg-card divide-y divide-border">
        {locations.map((l) => (
          <button
            key={l.id}
            onClick={() => setEditing(l)}
            className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-muted/40 transition-colors"
          >
            <div className="min-w-0">
              <p className="text-sm text-foreground">{l.name}</p>
              <p className="text-xs text-muted-foreground truncate">
                {l.city_name ? `${l.city_name}${l.country ? `, ${l.country}` : ""}` : (l.country ?? "no city yet")}
                {l.address && ` · ${l.address}`}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {l.maps_url && (
                <a
                  href={l.maps_url} target="_blank" rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="text-muted-foreground hover:text-primary"
                  title="Open in maps"
                >
                  <MapPin size={14} />
                </a>
              )}
              {!l.is_active && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">inactive</span>
              )}
              <Pencil size={12} className="text-muted-foreground" />
            </div>
          </button>
        ))}
      </div>

      {(open || editing) && (
        <LocationModal
          location={editing}
          onClose={() => { setOpen(false); setEditing(null) }}
        />
      )}
    </div>
  )
}

function LocationModal({ location, onClose }: { location: Location | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const isEdit = !!location
  const [name, setName] = useState(location?.name ?? "")
  const [cityId, setCityId] = useState(location?.city_id ?? "")
  const [address, setAddress] = useState(location?.address ?? "")
  const [mapsUrl, setMapsUrl] = useState(location?.maps_url ?? "")
  const [error, setError] = useState("")

  const { data: cities = [] } = useQuery({ queryKey: ["inv-cities"], queryFn: () => getCitiesApi() })

  // A location is in a city, a city is in a country — the country shown is
  // always the picked city's, never entered by hand.
  const pickedCity = cities.find((c) => c.id === cityId)
  const countryName = pickedCity
    ? (getCountries().find((c) => c.code === pickedCity.country)?.name ?? pickedCity.country)
    : null

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["inv-locations-all"] })
    queryClient.invalidateQueries({ queryKey: ["inv-locations"] })
  }

  const mutation = useMutation({
    mutationFn: () => isEdit
      ? updateLocationApi({
          id: location!.id, name, city_id: cityId,
          address: address.trim() || null, maps_url: mapsUrl.trim() || null,
        })
      : createLocationApi({
          name, city_id: cityId,
          address: address.trim() || null, maps_url: mapsUrl.trim() || null,
        }),
    onSuccess: () => { invalidate(); onClose() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not save the location"),
  })

  return (
    <Modal title={isEdit ? `Edit ${location!.name}` : "New location"} onClose={onClose}>
      <Field label="Name">
        <input
          value={name} onChange={(e) => setName(e.target.value)}
          placeholder="SpacePoint HQ, Al Ain Depot…"
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        />
      </Field>
      <Field label="City">
        <select
          value={cityId} onChange={(e) => setCityId(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm cursor-pointer"
        >
          <option value="" disabled>— Pick a city —</option>
          {cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <p className="text-xs text-muted-foreground mt-1">
          {countryName
            ? `Country: ${countryName} — derived from the city, always.`
            : "Every location sits in a city; the country follows from it."}
          {" "}Manage the city list in the Cities tab.
        </p>
      </Field>
      <Field label="Address (optional)">
        <input
          value={address} onChange={(e) => setAddress(e.target.value)}
          placeholder="Building, street, city"
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        />
      </Field>
      <Field label="Maps link (optional)">
        <input
          value={mapsUrl} onChange={(e) => setMapsUrl(e.target.value)}
          placeholder="https://maps.google.com/…"
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        />
        <p className="text-xs text-muted-foreground mt-1">
          Instructors sent here won't have to find the place themselves.
        </p>
      </Field>
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
      <ModalActions
        onCancel={onClose}
        onConfirm={() => { setError(""); mutation.mutate() }}
        loading={mutation.isPending}
        disabled={!name.trim() || !cityId}
        label={isEdit ? "Save" : "Create"}
      />
    </Modal>
  )
}

/* ── cities ────────────────────────────────────────────────────────────── */

function Cities() {
  const { data: cities = [], isLoading } = useQuery({
    queryKey: ["inv-cities-all"],
    queryFn: () => getCitiesApi(true),
  })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<City | null>(null)

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground -mt-1">
        The cities instructors can mark as "open to work in", and locations
        can sit in — seeded with the UAE emirates, add more as the org
        expands. Reflected live on the instructor apply form and profile.
      </p>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 w-fit"
      >
        <Plus size={14} /> New city
      </button>

      <div className="rounded-2xl border border-border bg-card divide-y divide-border">
        {cities.map((c) => (
          <button
            key={c.id}
            onClick={() => setEditing(c)}
            className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-muted/40 transition-colors"
          >
            <div className="min-w-0">
              <p className="text-sm text-foreground">{c.name}</p>
              <p className="text-xs text-muted-foreground">{c.country}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {!c.is_active && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">inactive</span>
              )}
              <Pencil size={12} className="text-muted-foreground" />
            </div>
          </button>
        ))}
        {cities.length === 0 && (
          <div className="p-8 text-center text-sm text-muted-foreground">No cities yet.</div>
        )}
      </div>

      {(open || editing) && (
        <CityModal city={editing} onClose={() => { setOpen(false); setEditing(null) }} />
      )}
    </div>
  )
}

function CityModal({ city, onClose }: { city: City | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const isEdit = !!city
  const [name, setName] = useState(city?.name ?? "")
  const [country, setCountry] = useState(city?.country ?? "AE")
  const [error, setError] = useState("")

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["inv-cities-all"] })
    queryClient.invalidateQueries({ queryKey: ["inv-cities"] })
  }

  const mutation = useMutation({
    mutationFn: () => isEdit
      ? updateCityApi({ id: city!.id, name, country })
      : createCityApi({ name, country }),
    onSuccess: () => { invalidate(); onClose() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not save the city"),
  })

  return (
    <Modal title={isEdit ? `Edit ${city!.name}` : "New city"} onClose={onClose}>
      <Field label="Name">
        <input
          value={name} onChange={(e) => setName(e.target.value)}
          placeholder="Dubai, Abu Dhabi, Cairo…"
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        />
      </Field>
      <Field label="Country">
        <CountrySelect
          value={country} onChange={setCountry} valueType="code"
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm cursor-pointer"
        />
      </Field>
      {isEdit && (
        <Field label="Status">
          <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer w-fit">
            <input
              type="checkbox" checked={city!.is_active}
              onChange={() => updateCityApi({ id: city!.id, is_active: !city!.is_active }).then(invalidate)}
            />
            Active
          </label>
        </Field>
      )}
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
      <ModalActions
        onCancel={onClose}
        onConfirm={() => { setError(""); mutation.mutate() }}
        loading={mutation.isPending}
        disabled={!name.trim() || country.length !== 2}
        label={isEdit ? "Save" : "Create"}
      />
    </Modal>
  )
}

/* ── warehouses ────────────────────────────────────────────────────────── */

function Warehouses() {
  const { data: warehouses = [], isLoading } = useQuery({
    queryKey: ["inv-warehouses-all"],
    queryFn: () => getWarehousesApi(undefined, true),
  })
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Warehouse | null>(null)

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-muted-foreground">
          A warehouse is a store within a location — the shelf stock and kits are actually counted
          against. Most locations need exactly one; add a second only where a site genuinely has two
          separate stores (a depot and a workshop, say).
        </p>
        <button
          onClick={() => setOpen(true)}
          className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 shrink-0 cursor-pointer"
        >
          <Plus size={14} /> New warehouse
        </button>
      </div>

      <div className="rounded-2xl border border-border bg-card divide-y divide-border">
        {warehouses.map((w) => (
          <button
            key={w.id}
            onClick={() => setEditing(w)}
            className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-muted/40 transition-colors cursor-pointer"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-foreground">{w.name}</p>
                {w.code && (
                  <span className="text-[11px] font-mono font-medium px-2 py-0.5 rounded-md bg-secondary text-secondary-foreground">
                    {w.code}
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground truncate mt-0.5">
                Location: <span className="font-medium text-foreground">{w.location_name}</span>
                {w.address && ` · ${w.address}`}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {!w.is_active && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">inactive</span>
              )}
              <Pencil size={12} className="text-muted-foreground" />
            </div>
          </button>
        ))}

        {warehouses.length === 0 && (
          <div className="p-8 text-center text-sm text-muted-foreground">
            No warehouses created yet. Click "New warehouse" above to add one.
          </div>
        )}
      </div>

      {(open || editing) && (
        <WarehouseEditModal
          warehouse={editing}
          onClose={() => { setOpen(false); setEditing(null) }}
        />
      )}
    </div>
  )
}

function WarehouseEditModal({ warehouse, onClose }: { warehouse: Warehouse | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const isEdit = !!warehouse
  const { data: locations = [] } = useQuery({
    queryKey: ["inv-locations"],
    queryFn: () => getLocationsApi(),
  })

  const [name, setName] = useState(warehouse?.name ?? "")
  const [code, setCode] = useState(warehouse?.code ?? "")
  const [locationId, setLocationId] = useState(warehouse?.location_id ?? (locations[0]?.id ?? ""))
  const [address, setAddress] = useState(warehouse?.address ?? "")
  const [notes, setNotes] = useState(warehouse?.notes ?? "")
  const [error, setError] = useState("")

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["inv-warehouses-all"] })
    queryClient.invalidateQueries({ queryKey: ["inv-warehouses"] })
  }

  const mutation = useMutation({
    mutationFn: () =>
      isEdit
        ? updateWarehouseApi({
            id: warehouse!.id,
            name: name.trim(),
            code: code.trim() || undefined,
            location_id: locationId,
            address: address.trim() || undefined,
            notes: notes.trim() || undefined,
          })
        : createWarehouseApi({
            location_id: locationId,
            name: name.trim(),
            code: code.trim() || undefined,
            address: address.trim() || undefined,
            notes: notes.trim() || undefined,
          }),
    onSuccess: () => {
      invalidate()
      onClose()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not save warehouse"),
  })

  return (
    <Modal title={isEdit ? `Edit ${warehouse!.name}` : "New warehouse"} onClose={onClose}>
      <Field label="Warehouse Name">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Dubai Central Warehouse, Al Quoz Depot"
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        />
      </Field>

      <Field label="Parent Location">
        <select
          value={locationId}
          onChange={(e) => setLocationId(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        >
          {locations.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name} ({l.country})
            </option>
          ))}
        </select>
      </Field>

      <Field label="Code (optional)">
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="e.g. WH-DXB-01"
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm font-mono"
        />
      </Field>

      <Field label="Address (optional)">
        <input
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          placeholder="Specific depot or storage room address"
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        />
      </Field>

      <Field label="Notes (optional)">
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder="Access codes, storekeeper contact info…"
          className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-y"
        />
      </Field>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      <ModalActions
        onCancel={onClose}
        onConfirm={() => {
          setError("")
          mutation.mutate()
        }}
        loading={mutation.isPending}
        disabled={!name.trim() || !locationId}
        label={isEdit ? "Save" : "Create"}
      />
    </Modal>
  )
}
