import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronDown, ChevronRight, Edit2, Plus, Trash2 } from "lucide-react"
import {
  getApplicationVideosApi,
  updateApplicationVideosApi,
  listApplicationModulesApi,
  createApplicationModuleApi,
  updateApplicationModuleApi,
  deleteApplicationModuleApi,
  createApplicationItemApi,
  updateApplicationItemApi,
  deleteApplicationItemApi,
} from "@/api/instructors/facilitator"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"
import type { ApplicationChecklistItem, ApplicationModule, ApplicationVideoConfig } from "@/types/instructors"

type Tab = "videos" | "modules"

interface ItemFormState {
  item_code: string
  title: string
  description: string
  is_required: boolean
  sort_order: string
}

function ItemForm({
  form,
  setForm,
}: {
  form: ItemFormState
  setForm: (f: ItemFormState) => void
}) {
  return (
    <div className="space-y-3">
      <div>
        <label className="text-xs font-medium text-muted-foreground mb-1 block">Item code</label>
        <input
          className="input"
          placeholder="e.g. MOD1-1"
          value={form.item_code}
          onChange={(e) => setForm({ ...form, item_code: e.target.value })}
        />
      </div>
      <div>
        <label className="text-xs font-medium text-muted-foreground mb-1 block">Title</label>
        <input
          className="input"
          placeholder="Checklist item title"
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
        />
      </div>
      <div>
        <label className="text-xs font-medium text-muted-foreground mb-1 block">Description (optional)</label>
        <textarea
          className="input min-h-[72px] resize-y"
          placeholder="Describe what the applicant should do…"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
      </div>
      <div>
        <label className="text-xs font-medium text-muted-foreground mb-1 block">Sort order</label>
        <input
          className="input"
          type="number"
          placeholder="1"
          value={form.sort_order}
          onChange={(e) => setForm({ ...form, sort_order: e.target.value })}
        />
      </div>
      <label className="flex items-center gap-2 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={form.is_required}
          onChange={(e) => setForm({ ...form, is_required: e.target.checked })}
          className="w-4 h-4 rounded border-border accent-primary"
        />
        <span className="text-sm font-medium">Required</span>
      </label>
    </div>
  )
}

export default function FacilitatorApplication() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>("videos")

  // ── Videos ────────────────────────────────────────────────────

  const { data: videos, isLoading: videosLoading } = useQuery({
    queryKey: ["facilitator-app-videos"],
    queryFn: getApplicationVideosApi,
  })

  const [localVideos, setLocalVideos] = useState<ApplicationVideoConfig[]>([
    { video_no: 1, title: "Video 1", url: "" },
    { video_no: 2, title: "Video 2", url: "" },
    { video_no: 3, title: "Video 3", url: "" },
  ])

  useEffect(() => {
    if (videos) {
      setLocalVideos(
        [1, 2, 3].map((n) => {
          const v = videos.find((x) => x.video_no === n)
          return { video_no: n, title: v?.title ?? `Video ${n}`, url: v?.url ?? "" }
        }),
      )
    }
  }, [videos])

  const setVideoField = (n: number, field: "title" | "url", value: string) => {
    setLocalVideos((prev) => prev.map((v) => (v.video_no === n ? { ...v, [field]: value } : v)))
  }

  const saveVideos = useMutation({
    mutationFn: () => updateApplicationVideosApi(localVideos),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["facilitator-app-videos"] }),
  })

  // ── Modules ───────────────────────────────────────────────────

  const { data: modules, isLoading: modulesLoading } = useQuery({
    queryKey: ["facilitator-app-modules"],
    queryFn: listApplicationModulesApi,
  })

  const [expandedModules, setExpandedModules] = useState<Set<string>>(new Set())
  const toggleExpand = (id: string) =>
    setExpandedModules((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  // Module dialogs
  const [newModuleOpen, setNewModuleOpen] = useState(false)
  const [newModuleTitle, setNewModuleTitle] = useState("")
  const [newModuleOrder, setNewModuleOrder] = useState("1")

  const [editModule, setEditModule] = useState<ApplicationModule | null>(null)
  const [editModuleTitle, setEditModuleTitle] = useState("")
  const [editModuleOrder, setEditModuleOrder] = useState("1")

  const openEditModule = (m: ApplicationModule) => {
    setEditModule(m)
    setEditModuleTitle(m.title)
    setEditModuleOrder(String(m.sort_order))
  }

  const createModule = useMutation({
    mutationFn: () =>
      createApplicationModuleApi({ title: newModuleTitle, sort_order: parseInt(newModuleOrder) || 1 }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facilitator-app-modules"] })
      setNewModuleOpen(false)
      setNewModuleTitle("")
      setNewModuleOrder("1")
    },
  })

  const updateModule = useMutation({
    mutationFn: () =>
      updateApplicationModuleApi(editModule!.id, {
        title: editModuleTitle,
        sort_order: parseInt(editModuleOrder) || 1,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facilitator-app-modules"] })
      setEditModule(null)
    },
  })

  const deleteModule = useMutation({
    mutationFn: (id: string) => deleteApplicationModuleApi(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["facilitator-app-modules"] }),
  })

  // Item dialogs
  const blankItemForm: ItemFormState = {
    item_code: "",
    title: "",
    description: "",
    is_required: true,
    sort_order: "1",
  }
  const [addItemModuleId, setAddItemModuleId] = useState<string | null>(null)
  const [editItem, setEditItem] = useState<ApplicationChecklistItem | null>(null)
  const [itemForm, setItemForm] = useState<ItemFormState>(blankItemForm)

  const openAddItem = (moduleId: string) => {
    setAddItemModuleId(moduleId)
    setItemForm(blankItemForm)
  }

  const openEditItem = (item: ApplicationChecklistItem) => {
    setEditItem(item)
    setItemForm({
      item_code: item.item_code,
      title: item.title,
      description: item.description ?? "",
      is_required: item.is_required,
      sort_order: String(item.sort_order),
    })
  }

  const createItem = useMutation({
    mutationFn: () =>
      createApplicationItemApi(addItemModuleId!, {
        item_code: itemForm.item_code,
        title: itemForm.title,
        description: itemForm.description || null,
        is_required: itemForm.is_required,
        sort_order: parseInt(itemForm.sort_order) || 1,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facilitator-app-modules"] })
      setAddItemModuleId(null)
      setItemForm(blankItemForm)
    },
  })

  const updateItem = useMutation({
    mutationFn: () =>
      updateApplicationItemApi(editItem!.id, {
        item_code: itemForm.item_code,
        title: itemForm.title,
        description: itemForm.description || null,
        is_required: itemForm.is_required,
        sort_order: parseInt(itemForm.sort_order) || 1,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facilitator-app-modules"] })
      setEditItem(null)
      setItemForm(blankItemForm)
    },
  })

  const deleteItem = useMutation({
    mutationFn: (id: string) => deleteApplicationItemApi(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["facilitator-app-modules"] }),
  })

  // ── Render ────────────────────────────────────────────────────

  return (
    <div>
      <PageHeader
        title="Application Content"
        subtitle="Manage the videos and checklist modules shown to applicants in the scholarship pipeline."
      />

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-border mb-6">
        {(["videos", "modules"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={[
              "px-4 py-2.5 text-sm font-medium transition-colors",
              tab === t
                ? "text-primary border-b-2 border-primary -mb-px"
                : "text-muted-foreground hover:text-foreground",
            ].join(" ")}
          >
            {t === "videos" ? "Video Links" : "Checklist Modules"}
          </button>
        ))}
      </div>

      {/* ── Videos tab ── */}
      {tab === "videos" && (
        <div>
          {videosLoading ? (
            <Spinner />
          ) : (
            <>
              <p className="text-sm text-muted-foreground mb-4">
                These are the three YouTube videos all applicants must watch and summarise during Phase 1.
                Changing a URL here takes effect for new applicants immediately.
              </p>
              <div className="space-y-4 mb-6">
                {localVideos.map((v) => (
                  <Card key={v.video_no}>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Video {v.video_no}</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <div>
                        <label className="text-xs font-medium text-muted-foreground mb-1 block">
                          Title shown to applicant
                        </label>
                        <input
                          className="input"
                          placeholder={`Video ${v.video_no}`}
                          value={v.title}
                          onChange={(e) => setVideoField(v.video_no, "title", e.target.value)}
                        />
                      </div>
                      <div>
                        <label className="text-xs font-medium text-muted-foreground mb-1 block">
                          YouTube URL
                        </label>
                        <input
                          className="input"
                          placeholder="https://youtu.be/…"
                          value={v.url}
                          onChange={(e) => setVideoField(v.video_no, "url", e.target.value)}
                        />
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
              <Button onClick={() => saveVideos.mutate()} disabled={saveVideos.isPending}>
                {saveVideos.isPending ? "Saving…" : "Save video links"}
              </Button>
              {saveVideos.isSuccess && (
                <p className="text-sm text-green-600 dark:text-green-400 mt-2">Saved successfully.</p>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Modules tab ── */}
      {tab === "modules" && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-muted-foreground">
              Modules added after an applicant has already submitted will not be required for their review.
            </p>
            <Button onClick={() => setNewModuleOpen(true)} className="shrink-0">
              <Plus size={16} className="mr-1.5" /> New module
            </Button>
          </div>

          {modulesLoading ? (
            <Spinner />
          ) : (modules ?? []).length === 0 ? (
            <EmptyState
              title="No checklist modules yet"
              hint="Add your first module to define what applicants must complete in Phase 1."
            />
          ) : (
            <div className="space-y-3">
              {modules!.map((m) => {
                const expanded = expandedModules.has(m.id)
                return (
                  <Card key={m.id}>
                    <CardHeader className="py-3">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => toggleExpand(m.id)}
                          className="p-0.5 text-muted-foreground hover:text-foreground shrink-0"
                          aria-label={expanded ? "Collapse" : "Expand"}
                        >
                          {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                        </button>
                        <span className="font-semibold flex-1 truncate">{m.title}</span>
                        <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded shrink-0">
                          #{m.sort_order}
                        </span>
                        <span className="text-xs text-muted-foreground shrink-0">
                          {m.items.length} item{m.items.length !== 1 ? "s" : ""}
                        </span>
                        <button
                          onClick={() => openEditModule(m)}
                          className="p-1.5 text-muted-foreground hover:text-foreground rounded shrink-0"
                          aria-label="Edit module"
                        >
                          <Edit2 size={14} />
                        </button>
                        <button
                          onClick={() => deleteModule.mutate(m.id)}
                          className="p-1.5 text-muted-foreground hover:text-destructive rounded shrink-0"
                          aria-label="Delete module"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </CardHeader>

                    {expanded && (
                      <CardContent className="pt-0 pb-4">
                        <div className="space-y-2 mb-3">
                          {m.items.length === 0 ? (
                            <p className="text-sm text-muted-foreground py-1">No items yet.</p>
                          ) : (
                            m.items.map((item) => (
                              <div
                                key={item.id}
                                className="flex items-start gap-2 p-3 rounded-lg border border-border bg-muted/20"
                              >
                                <span className="text-[10px] font-mono font-bold bg-muted border border-border px-1.5 py-0.5 rounded shrink-0 mt-0.5">
                                  {item.item_code}
                                </span>
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm font-medium leading-snug">{item.title}</p>
                                  {item.description && (
                                    <p className="text-xs text-muted-foreground mt-0.5 leading-snug">
                                      {item.description}
                                    </p>
                                  )}
                                </div>
                                <span
                                  className={[
                                    "text-[10px] font-semibold px-1.5 py-0.5 rounded border shrink-0 whitespace-nowrap",
                                    item.is_required
                                      ? "bg-red-50 text-red-600 border-red-200 dark:bg-red-950/30 dark:text-red-400 dark:border-red-900/50"
                                      : "bg-muted text-muted-foreground border-border",
                                  ].join(" ")}
                                >
                                  {item.is_required ? "Required" : "Optional"}
                                </span>
                                <button
                                  onClick={() => openEditItem(item)}
                                  className="p-1 text-muted-foreground hover:text-foreground shrink-0"
                                  aria-label="Edit item"
                                >
                                  <Edit2 size={13} />
                                </button>
                                <button
                                  onClick={() => deleteItem.mutate(item.id)}
                                  className="p-1 text-muted-foreground hover:text-destructive shrink-0"
                                  aria-label="Delete item"
                                >
                                  <Trash2 size={13} />
                                </button>
                              </div>
                            ))
                          )}
                        </div>
                        <Button size="sm" variant="outline" onClick={() => openAddItem(m.id)}>
                          <Plus size={13} className="mr-1" /> Add item
                        </Button>
                      </CardContent>
                    )}
                  </Card>
                )
              })}
            </div>
          )}

          {/* New Module dialog */}
          <Dialog open={newModuleOpen} onOpenChange={setNewModuleOpen}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>New checklist module</DialogTitle>
              </DialogHeader>
              <div className="space-y-3 mt-1">
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">Title</label>
                  <input
                    className="input"
                    placeholder="Module title"
                    value={newModuleTitle}
                    onChange={(e) => setNewModuleTitle(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">Sort order</label>
                  <input
                    className="input"
                    type="number"
                    placeholder="1"
                    value={newModuleOrder}
                    onChange={(e) => setNewModuleOrder(e.target.value)}
                  />
                </div>
                <Button
                  onClick={() => createModule.mutate()}
                  disabled={!newModuleTitle.trim() || createModule.isPending}
                  className="w-full"
                >
                  {createModule.isPending ? "Creating…" : "Create module"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>

          {/* Edit Module dialog */}
          <Dialog open={!!editModule} onOpenChange={(open) => !open && setEditModule(null)}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Edit module</DialogTitle>
              </DialogHeader>
              <div className="space-y-3 mt-1">
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">Title</label>
                  <input
                    className="input"
                    placeholder="Module title"
                    value={editModuleTitle}
                    onChange={(e) => setEditModuleTitle(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">Sort order</label>
                  <input
                    className="input"
                    type="number"
                    placeholder="1"
                    value={editModuleOrder}
                    onChange={(e) => setEditModuleOrder(e.target.value)}
                  />
                </div>
                <Button
                  onClick={() => updateModule.mutate()}
                  disabled={!editModuleTitle.trim() || updateModule.isPending}
                  className="w-full"
                >
                  {updateModule.isPending ? "Saving…" : "Save changes"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>

          {/* Add Item dialog */}
          <Dialog open={!!addItemModuleId} onOpenChange={(open) => !open && setAddItemModuleId(null)}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Add checklist item</DialogTitle>
              </DialogHeader>
              <div className="mt-1">
                <ItemForm form={itemForm} setForm={setItemForm} />
                <Button
                  onClick={() => createItem.mutate()}
                  disabled={!itemForm.title.trim() || !itemForm.item_code.trim() || createItem.isPending}
                  className="w-full mt-4"
                >
                  {createItem.isPending ? "Adding…" : "Add item"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>

          {/* Edit Item dialog */}
          <Dialog open={!!editItem} onOpenChange={(open) => !open && setEditItem(null)}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Edit item</DialogTitle>
              </DialogHeader>
              <div className="mt-1">
                <ItemForm form={itemForm} setForm={setItemForm} />
                <Button
                  onClick={() => updateItem.mutate()}
                  disabled={!itemForm.title.trim() || !itemForm.item_code.trim() || updateItem.isPending}
                  className="w-full mt-4"
                >
                  {updateItem.isPending ? "Saving…" : "Save changes"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      )}
    </div>
  )
}
