import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { Package, Pencil, Plus, ShoppingCart, Trash2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { PageHeader, Spinner } from "@/components/ui/primitives"
import { Modal, ModalActions } from "@/pages/admin/components/common"
import { AssetField } from "@/pages/operations/website/WebsiteManagement"
import { useToast } from "@/components/ui/toast"
import { useAuth } from "@/context/AuthContext"
import { getWarehousesApi } from "@/api/inventory"
import {
  createShopItem,
  deleteShopItem,
  fulfillShopOrder,
  getShopItems,
  getShopOrders,
  updateShopItem,
} from "@/api/shop"
import type { ShopItem, ShopOrder } from "@/types/shop"

type Tab = "catalog" | "orders"

const WEBSITE_BASE_URL =
  (import.meta.env.VITE_WEBSITE_URL as string | undefined)?.replace(/\/$/, "") ||
  "http://localhost:4321"

function resolveWebsiteAsset(url: string | null | undefined): string {
  const raw = (url ?? "").trim()
  if (!raw) return ""
  if (/^(https?:|data:|blob:)/i.test(raw)) return raw
  const path = raw.startsWith("/") ? raw : `/${raw}`
  return `${WEBSITE_BASE_URL}${encodeURI(path)}`
}

function errorDetail(e: unknown, fallback: string): string {
  if (isAxiosError(e)) {
    const detail = (e.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === "string") return detail
  } else if (e instanceof Error) {
    return e.message
  }
  return fallback
}

const ORDER_STATUS_STYLES: Record<string, string> = {
  pending_payment: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
  paid: "bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20",
  fulfilled: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
  failed: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20",
  expired: "bg-muted text-muted-foreground border-border",
}

const ORDER_STATUSES = ["pending_payment", "paid", "fulfilled", "failed", "expired"] as const

function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
        {label}
      </span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground"
      />
    </label>
  )
}

/**
 * Ground Station shop operations (Step 7) — catalogue control plus order
 * tracking and warehouse fulfillment. Writes are gated on
 * require_inventory_manage parity (operations/coo/admin): a storekeeper
 * never sees a button that would 403.
 */
export default function Shop() {
  const { activeRole } = useAuth()
  const canManage = activeRole !== "storekeeper"
  const [tab, setTab] = useState<Tab>("catalog")

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Ground Station Shop"
        subtitle="Storefront catalogue, Stripe AED orders, and warehouse fulfillment."
      />
      <div className="inline-flex rounded-xl bg-muted/60 p-1 ring-1 ring-border self-start">
        {(["catalog", "orders"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-2 rounded-lg text-sm font-semibold transition-all capitalize",
              tab === t ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t === "catalog" ? "Catalog" : "Orders"}
          </button>
        ))}
      </div>
      {tab === "catalog" ? <CatalogSection canManage={canManage} /> : <OrdersSection canManage={canManage} />}
    </div>
  )
}

// ── Catalogue ─────────────────────────────────────────────────────────────────

function CatalogSection({ canManage }: { canManage: boolean }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [modal, setModal] = useState<{ open: boolean; item: ShopItem | null }>({
    open: false,
    item: null,
  })

  const { data: items = [], isLoading, isError } = useQuery({
    queryKey: ["shop-items"],
    queryFn: getShopItems,
  })

  const togglePublished = useMutation({
    mutationFn: (item: ShopItem) => updateShopItem(item.id, { is_published: !item.is_published }),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["shop-items"] })
      toast.success(saved.is_published ? `“${saved.display_name}” is live on /shop` : `“${saved.display_name}” unpublished`)
    },
    onError: (e) => toast.error(errorDetail(e, "Could not update this product")),
  })
  const remove = useMutation({
    mutationFn: (id: string) => deleteShopItem(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["shop-items"] })
      toast.success("Product deleted")
    },
    onError: (e) => toast.error(errorDetail(e, "Could not delete this product")),
  })

  if (isLoading) return <Spinner />
  if (isError) {
    return <p className="text-sm text-red-600 dark:text-red-400">Could not load the catalogue.</p>
  }

  return (
    <div className="flex flex-col gap-4">
      {canManage && (
        <div className="flex items-center justify-end">
          <button
            onClick={() => setModal({ open: true, item: null })}
            className="h-9 px-4 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 inline-flex items-center gap-1.5"
          >
            <Plus size={15} /> Add Product
          </button>
        </div>
      )}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {items.map((item) => (
          <div key={item.id} className="rounded-2xl border border-border bg-card p-4 flex items-center gap-4 flex-wrap">
            <div className="w-20 h-20 rounded-xl overflow-hidden shrink-0 bg-[#130921] border border-border flex items-center justify-center p-1.5">
              {item.cover_image_url ? (
                <img
                  src={resolveWebsiteAsset(item.cover_image_url)}
                  alt={item.display_name}
                  className="w-full h-full object-contain"
                  onError={(e) => {
                    e.currentTarget.style.display = "none"
                  }}
                />
              ) : (
                <Package size={20} className="text-muted-foreground" />
              )}
            </div>
            <div className="flex-1 min-w-44">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-semibold text-foreground">{item.display_name}</p>
                <span
                  className={cn(
                    "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase border",
                    item.is_published
                      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                      : "bg-muted text-muted-foreground border-border",
                  )}
                >
                  {item.is_published ? "Published" : "Hidden"}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5 font-mono">{item.slug}</p>
              <p className="text-sm font-bold text-foreground mt-1 tabular-nums">
                {Number(item.price_aed).toLocaleString("en-US")} AED
              </p>
            </div>
            {canManage && (
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => togglePublished.mutate(item)}
                  disabled={togglePublished.isPending}
                  className="h-8 px-3 border border-border text-xs font-medium rounded-lg hover:bg-muted text-foreground disabled:opacity-40"
                >
                  {item.is_published ? "Unpublish" : "Publish"}
                </button>
                <button
                  onClick={() => setModal({ open: true, item })}
                  className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  aria-label={`Edit ${item.display_name}`}
                >
                  <Pencil size={15} />
                </button>
                <button
                  onClick={() => {
                    if (confirm(`Delete “${item.display_name}” from the catalogue?`)) remove.mutate(item.id)
                  }}
                  className="p-2 rounded-lg text-muted-foreground hover:text-red-600 dark:hover:text-red-400 hover:bg-muted transition-colors"
                  aria-label={`Delete ${item.display_name}`}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            )}
          </div>
        ))}
        {items.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center col-span-full">
            No products yet — add the first one to stock the storefront.
          </p>
        )}
      </div>
      {modal.open && (
        <ShopItemModal
          key={modal.item?.id ?? "new"}
          item={modal.item}
          onClose={() => setModal({ open: false, item: null })}
        />
      )}
    </div>
  )
}

function ShopItemModal({ item, onClose }: { item: ShopItem | null; onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [slug, setSlug] = useState(item?.slug ?? "")
  const [name, setName] = useState(item?.display_name ?? "")
  const [subtitle, setSubtitle] = useState(item?.subtitle ?? "")
  const [description, setDescription] = useState(item?.description ?? "")
  const [price, setPrice] = useState(item != null ? String(item.price_aed) : "")
  const [cover, setCover] = useState(item?.cover_image_url ?? "")
  const [gallery, setGallery] = useState((item?.gallery_images ?? []).join("\n"))
  const [catalogId, setCatalogId] = useState(item?.item_id ?? "")
  const [published, setPublished] = useState(item?.is_published ?? false)
  const [preorder, setPreorder] = useState(item?.is_preorder_enabled ?? true)
  const [preorderMsg, setPreorderMsg] = useState(
    item?.preorder_message ?? "Coming Soon",
  )
  const [order, setOrder] = useState(String(item?.display_order ?? 0))

  const save = useMutation({
    mutationFn: () => {
      if (!slug.trim()) throw new Error("Slug is required")
      if (!name.trim()) throw new Error("Display name is required")
      const priceNum = Number(price)
      if (!Number.isFinite(priceNum) || priceNum < 0) throw new Error("Price must be a non-negative number")
      const payload = {
        slug: slug.trim().toLowerCase().replace(/\s+/g, "-"),
        display_name: name.trim(),
        subtitle: subtitle.trim() || null,
        description: description.trim() || null,
        price_aed: Math.round(priceNum * 100) / 100,
        compare_at_price_aed: null,
        cover_image_url: cover.trim() || null,
        gallery_images: gallery.split("\n").map((g) => g.trim()).filter(Boolean),
        item_id: catalogId.trim() || null,
        is_published: published,
        is_preorder_enabled: preorder,
        preorder_message: preorderMsg.trim() || "Coming Soon",
        display_order: Number(order) || 0,
      }
      return item ? updateShopItem(item.id, payload) : createShopItem(payload)
    },
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["shop-items"] })
      toast.success(`“${saved.display_name}” saved`)
      onClose()
    },
    onError: (e) => toast.error(errorDetail(e, "Could not save this product")),
  })

  return (
    <Modal title={item ? "Edit Product" : "Add Product"} onClose={onClose} maxWidth="sm:max-w-2xl max-w-2xl">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <TextField label="Display Name" value={name} onChange={setName} />
        <TextField label="Slug" value={slug} onChange={setSlug} placeholder="e.g. minisat-explorer" />
        <TextField label="Subtitle" value={subtitle} onChange={setSubtitle} placeholder="optional" />
        <TextField label="Catalogue Item ID (stock link)" value={catalogId} onChange={setCatalogId} placeholder="UUID, optional" />
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Price (AED)
          </span>
          <input
            type="number" min={0} step="0.01" value={price}
            onChange={(e) => setPrice(e.target.value)}
            className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground tabular-nums"
          />
        </label>
        <TextField label="Display Order" value={order} onChange={setOrder} placeholder="0" />
      </div>
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Description
        </span>
        <textarea
          value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
          className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-y"
        />
      </label>
      <AssetField
        label="Cover Image"
        value={cover}
        onChange={setCover}
        accept="image/*"
        placeholder="https://… or upload product image"
        aspect={4 / 3}
        aspectHint="4:3 Card"
      />
      {cover.trim() && (
        <div className="w-28 h-28 rounded-xl overflow-hidden border border-border bg-[#130921] flex items-center justify-center p-2">
          <img
            src={resolveWebsiteAsset(cover.trim())}
            alt="Cover preview"
            className="w-full h-full object-contain"
            onError={(e) => {
              e.currentTarget.style.display = "none"
            }}
          />
        </div>
      )}
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Gallery Images (one URL per line)
        </span>
        <textarea
          value={gallery} onChange={(e) => setGallery(e.target.value)} rows={2}
          className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-y font-mono"
        />
      </label>
      <TextField label="Preorder Message" value={preorderMsg} onChange={setPreorderMsg} />
      <div className="flex items-center gap-5">
        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
          <input type="checkbox" checked={published} onChange={(e) => setPublished(e.target.checked)} className="w-4 h-4 accent-primary" />
          Published on /shop
        </label>
        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
          <input type="checkbox" checked={preorder} onChange={(e) => setPreorder(e.target.checked)} className="w-4 h-4 accent-primary" />
          Preorder enabled
        </label>
      </div>
      <ModalActions
        onCancel={onClose}
        onConfirm={() => save.mutate()}
        loading={save.isPending}
        disabled={!slug.trim() || !name.trim() || !price.trim()}
        label={item ? "Save changes" : "Add product"}
      />
    </Modal>
  )
}

// ── Orders ────────────────────────────────────────────────────────────────────

function OrdersSection({ canManage }: { canManage: boolean }) {
  const [status, setStatus] = useState<string>("")
  const [fulfilling, setFulfilling] = useState<ShopOrder | null>(null)

  const { data: orders = [], isLoading, isError } = useQuery({
    queryKey: ["shop-orders", status],
    queryFn: () => getShopOrders(status || undefined),
  })

  if (isLoading) return <Spinner />
  if (isError) {
    return <p className="text-sm text-red-600 dark:text-red-400">Could not load orders.</p>
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="inline-flex rounded-xl bg-muted/60 p-1 ring-1 ring-border self-start flex-wrap">
        {["", ...ORDER_STATUSES].map((s) => (
          <button
            key={s || "all"}
            onClick={() => setStatus(s)}
            className={cn(
              "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all capitalize",
              status === s ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {s === "" ? "All" : s.replace(/_/g, " ")}
          </button>
        ))}
      </div>
      <div className="flex flex-col gap-2">
        {orders.map((o) => (
          <div key={o.id} className="rounded-2xl border border-border bg-card p-4 flex flex-col gap-2">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-sm font-semibold text-foreground font-mono">{o.order_number}</p>
                  <span
                    className={cn(
                      "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase border",
                      ORDER_STATUS_STYLES[o.status] ?? ORDER_STATUS_STYLES.pending_payment,
                    )}
                  >
                    {o.status.replace(/_/g, " ")}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {o.customer_name} · {o.customer_email} · {new Date(o.created_at).toLocaleString()}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <p className="text-base font-bold text-foreground tabular-nums">
                  {Number(o.total_amount_aed).toLocaleString("en-US")} {o.currency}
                </p>
                {canManage && o.status === "paid" && (
                  <button
                    onClick={() => setFulfilling(o)}
                    className="h-8 px-3 bg-primary text-primary-foreground text-xs font-semibold rounded-lg hover:opacity-90"
                  >
                    Fulfill
                  </button>
                )}
              </div>
            </div>
            <div className="flex flex-col gap-1 text-xs text-muted-foreground">
              {o.items.map((line) => (
                <p key={line.id} className="tabular-nums">
                  {line.quantity}× {line.item_name} @ {Number(line.unit_price_aed).toLocaleString("en-US")} AED
                  {line.is_preorder ? " (preorder)" : ""}
                </p>
              ))}
            </div>
            {o.fulfillment_notes && (
              <p className="text-xs text-muted-foreground">Notes: {o.fulfillment_notes}</p>
            )}
          </div>
        ))}
        {orders.length === 0 && (
          <div className="rounded-2xl border border-dashed border-border p-10 text-center">
            <ShoppingCart size={20} className="mx-auto mb-2 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">No orders in this state yet.</p>
          </div>
        )}
      </div>
      {fulfilling && (
        <FulfillModal order={fulfilling} onClose={() => setFulfilling(null)} />
      )}
    </div>
  )
}

function FulfillModal({ order, onClose }: { order: ShopOrder; onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [warehouseId, setWarehouseId] = useState(order.fulfilled_warehouse_id ?? "")
  const [notes, setNotes] = useState(order.fulfillment_notes ?? "")

  const { data: warehouses = [] } = useQuery({
    queryKey: ["inv-warehouses-all"],
    queryFn: () => getWarehousesApi(undefined, true),
  })

  const fulfill = useMutation({
    mutationFn: () =>
      fulfillShopOrder(order.id, {
        warehouse_id: warehouseId || null,
        notes: notes.trim() || null,
      }),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["shop-orders"] })
      toast.success(`Order ${saved.order_number} fulfilled — stock ledger updated`)
      onClose()
    },
    onError: (e) => toast.error(errorDetail(e, "Could not fulfill this order")),
  })

  return (
    <Modal title={`Fulfill ${order.order_number}`} onClose={onClose}>
      <p className="text-xs text-muted-foreground">
        Fulfilling decrements linked catalogue stock at the chosen warehouse and writes{" "}
        <code className="bg-muted px-1 rounded">sold</code> ledger movements. Preorder-only
        lines skip the ledger automatically.
      </p>
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Warehouse
        </span>
        <select
          value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}
          className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground"
        >
          <option value="">No warehouse (no stock movement)</option>
          {warehouses.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Fulfillment Notes
        </span>
        <textarea
          value={notes} onChange={(e) => setNotes(e.target.value)} rows={2}
          placeholder="Courier, tracking number, handover notes…"
          className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-y"
        />
      </label>
      <ModalActions
        onCancel={onClose}
        onConfirm={() => fulfill.mutate()}
        loading={fulfill.isPending}
        disabled={false}
        label="Mark fulfilled"
      />
    </Modal>
  )
}
