import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import type { ItemCategory } from "@/types/inventory"
import {
  createItemApi,
  createLocationApi,
  getItemsApi,
  getLocationsApi,
  getTemplateApi,
  getTemplatesApi,
  setTemplateItemsApi,
} from "@/api/inventory"
import { Field, Modal, ModalActions, Spinner } from "@/pages/admin/components/common"
import { cn } from "@/lib/utils"

const CATEGORIES: ItemCategory[] = ["board", "sensor", "mechanical", "tool", "merch", "other"]
type Tab = "templates" | "items" | "locations"

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
        {(["templates", "items", "locations"] as Tab[]).map((t) => (
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
            {t === "templates" ? "Kit types" : t}
          </button>
        ))}
      </div>

      {tab === "templates" && <Templates />}
      {tab === "items" && <Items />}
      {tab === "locations" && <Locations />}
    </div>
  )
}

/* ── kit types + their parts list ──────────────────────────────────────── */

function Templates() {
  const { data: templates = [], isLoading } = useQuery({ queryKey: ["inv-templates"], queryFn: getTemplatesApi })
  const [openId, setOpenId] = useState<string | null>(null)

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-2">
      {templates.map((t) => (
        <div key={t.id} className="rounded-2xl border border-border bg-card">
          <button
            onClick={() => setOpenId(openId === t.id ? null : t.id)}
            className="w-full flex items-center justify-between p-4 text-left"
          >
            <div>
              <p className="text-sm font-medium text-foreground">{t.name}</p>
              <p className="text-xs text-muted-foreground font-mono">SP-{t.code}-0001</p>
            </div>
            <span className="text-xs text-muted-foreground">{openId === t.id ? "Hide" : "Parts list"}</span>
          </button>
          {openId === t.id && <TemplateLines templateId={t.id} />}
        </div>
      ))}
      {templates.length === 0 && (
        <p className="text-sm text-muted-foreground text-center py-10 border border-dashed border-border rounded-2xl">
          No kit types yet.
        </p>
      )}
    </div>
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
          <span className="text-sm text-foreground">
            {line.item_name}
            {line.is_consumable && (
              <span className="ml-2 text-xs text-muted-foreground">consumable — never counted as missing</span>
            )}
          </span>
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

/* ── items ─────────────────────────────────────────────────────────────── */

function Items() {
  const { data: items = [], isLoading } = useQuery({ queryKey: ["inv-items"], queryFn: () => getItemsApi() })
  const [open, setOpen] = useState(false)

  if (isLoading) return <Spinner />

  const byCategory = items.reduce<Record<string, typeof items>>((acc, i) => {
    (acc[i.category] ??= []).push(i)
    return acc
  }, {})

  return (
    <div className="flex flex-col gap-4">
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 w-fit"
      >
        <Plus size={14} /> New item
      </button>

      {Object.entries(byCategory).map(([category, group]) => (
        <section key={category} className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold text-foreground capitalize">{category}</h2>
          <div className="rounded-2xl border border-border bg-card divide-y divide-border">
            {group.map((i) => (
              <div key={i.id} className="flex items-center justify-between px-4 py-2.5">
                <span className="text-sm text-foreground">{i.name}</span>
                <div className="flex items-center gap-2">
                  {i.is_consumable && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">consumable</span>
                  )}
                  {i.returnable_default && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400">
                      comes back
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}

      {open && <NewItemModal onClose={() => setOpen(false)} />}
    </div>
  )
}

function NewItemModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState("")
  const [category, setCategory] = useState<ItemCategory>("board")
  const [isConsumable, setIsConsumable] = useState(false)
  const [returnable, setReturnable] = useState(false)
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: createItemApi,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["inv-items"] }); onClose() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not create the item"),
  })

  return (
    <Modal title="New item" onClose={onClose}>
      <Field label="Name">
        <input
          value={name} onChange={(e) => setName(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        />
      </Field>
      <Field label="Category">
        <select
          value={category} onChange={(e) => setCategory(e.target.value as ItemCategory)}
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm capitalize"
        >
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </Field>
      <label className="flex items-start gap-2 cursor-pointer">
        <input type="checkbox" checked={isConsumable} onChange={(e) => setIsConsumable(e.target.checked)} className="mt-0.5" />
        <span className="text-sm text-foreground">
          Consumable
          <span className="block text-xs text-muted-foreground">
            Screws, wire — never reported as missing from a kit, so the shortage list stays readable.
          </span>
        </span>
      </label>
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
        onConfirm={() => {
          setError("")
          mutation.mutate({ name, category, is_consumable: isConsumable, returnable_default: returnable })
        }}
        loading={mutation.isPending}
        disabled={!name.trim()}
        label="Create"
      />
    </Modal>
  )
}

/* ── locations ─────────────────────────────────────────────────────────── */

function Locations() {
  const queryClient = useQueryClient()
  const { data: locations = [], isLoading } = useQuery({
    queryKey: ["inv-locations-all"],
    queryFn: () => getLocationsApi(true),
  })
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [country, setCountry] = useState("AE")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: createLocationApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inv-locations-all"] })
      queryClient.invalidateQueries({ queryKey: ["inv-locations"] })
      setOpen(false); setName("")
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not create the location"),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-4">
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 w-fit"
      >
        <Plus size={14} /> New location
      </button>

      <div className="rounded-2xl border border-border bg-card divide-y divide-border">
        {locations.map((l) => (
          <div key={l.id} className="flex items-center justify-between px-4 py-3">
            <div>
              <p className="text-sm text-foreground">{l.name}</p>
              <p className="text-xs text-muted-foreground">{l.country}</p>
            </div>
            {!l.is_active && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">inactive</span>
            )}
          </div>
        ))}
      </div>

      {open && (
        <Modal title="New location" onClose={() => setOpen(false)}>
          <Field label="Name">
            <input
              value={name} onChange={(e) => setName(e.target.value)}
              placeholder="Main Warehouse, Dubai, Egypt…"
              className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
            />
          </Field>
          <Field label="Country">
            <input
              value={country} maxLength={2}
              onChange={(e) => setCountry(e.target.value.toUpperCase())}
              className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
            />
            <p className="text-xs text-muted-foreground mt-1">
              Two letters — AE, EG. Used to tell a local move from a cross-border one.
            </p>
          </Field>
          {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
          <ModalActions
            onCancel={() => setOpen(false)}
            onConfirm={() => { setError(""); mutation.mutate({ name, country }) }}
            loading={mutation.isPending}
            disabled={!name.trim() || country.length !== 2}
            label="Create"
          />
        </Modal>
      )}
    </div>
  )
}
