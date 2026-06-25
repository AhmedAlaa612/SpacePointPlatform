import { useState } from "react"
import { createPortal } from "react-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { X, Plus, Trash2, Check, Pencil, Eye, ArrowLeft } from "lucide-react"
import type { Epic, Module } from "@/types/interns"
import { getEpicForMapApi } from "@/api/interns/mindmap"
import { createModuleApi, updateModuleApi, deleteModuleApi } from "@/api/interns/modules"
import ModuleDetailDialog from "@/pages/interns/components/ModuleDetailDialog"

function ModuleEditDialog({ module: m, onSave, onClose, isPending }: {
  module: Module
  onSave: (title: string, desc: string) => void
  onClose: () => void
  isPending: boolean
}) {
  const [title, setTitle] = useState(m.title)
  const [desc,  setDesc]  = useState(m.description ?? "")

  return createPortal(
    <div className="fixed inset-0 bg-black/40 z-[9999] flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-card border border-border text-foreground rounded-2xl shadow-2xl flex flex-col overflow-hidden" onClick={(e) => e.stopPropagation()}>
        {/* header */}
        <div className="flex items-center gap-2 px-5 pt-5 pb-3 border-b border-border">
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex-shrink-0">
            <ArrowLeft size={15} />
          </button>
          <div className="flex-1 min-w-0">
            <p className="text-[9px] font-bold uppercase tracking-widest text-[#643f83] dark:text-[#d6c7e1]">Edit module</p>
            <p className="text-sm font-semibold text-foreground truncate">{m.title}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex-shrink-0">
            <X size={15} />
          </button>
        </div>

        {/* body */}
        <div className="px-5 py-4 flex flex-col gap-3">
          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">Name</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
              className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </div>
          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
              Scope / Description <span className="normal-case font-normal text-muted-foreground/60">— interns will see this</span>
            </label>
            <textarea
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder="Describe the scope of this module…"
              rows={4}
              className="w-full px-3 py-2.5 border border-border bg-background text-foreground rounded-xl text-sm resize-none focus:outline-none focus:border-primary transition-colors"
            />
          </div>
          <div className="flex gap-2 pt-1">
            <button onClick={onClose}
              className="flex-1 h-10 border border-border rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors">
              Cancel
            </button>
            <button
              onClick={() => onSave(title.trim(), desc.trim())}
              disabled={!title.trim() || isPending}
              className="flex-1 h-10 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:bg-primary/95 transition-colors disabled:opacity-50 flex items-center justify-center gap-1.5"
            >
              <Check size={14} /> {isPending ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  )
}

export default function ManageModulesModal({ epic, role, onClose }: {
  epic: Epic
  role: "admin" | "leader"
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [newTitle,    setNewTitle]    = useState("")
  const [newDesc,     setNewDesc]     = useState("")
  const [editModule,  setEditModule]  = useState<Module | null>(null)
  const [viewModule,  setViewModule]  = useState<Module | null>(null)
  const [error,       setError]       = useState("")

  const { data: fullEpic, isLoading } = useQuery<Epic>({
    queryKey: ["epic", epic.id, role],
    queryFn: () => getEpicForMapApi(epic.id, role),
  })
  const modules: Module[] = fullEpic?.modules ?? epic.modules ?? []

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["epic", epic.id, role] })
    qc.invalidateQueries({ queryKey: ["epics"] })
    qc.invalidateQueries({ queryKey: ["tasks"] })
  }

  const createMut = useMutation({
    mutationFn: () => createModuleApi(epic.id, { title: newTitle.trim(), description: newDesc.trim() || undefined }, role),
    onSuccess: () => { setNewTitle(""); setNewDesc(""); refresh() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to add module"),
  })

  const updateMut = useMutation({
    mutationFn: ({ title, desc }: { title: string; desc: string }) =>
      updateModuleApi(editModule!.id, { title: title || undefined, description: desc || undefined }, role),
    onSuccess: () => { setEditModule(null); refresh() },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteModuleApi(id, role),
    onSuccess: refresh,
  })

  return createPortal(
    <>
      <div className="fixed inset-0 bg-black/40 z-[9998] flex items-center justify-center p-4">
        <div className="w-full max-w-sm bg-card border border-border text-foreground rounded-2xl shadow-2xl flex flex-col max-h-[85vh] overflow-hidden">

          {/* header */}
          <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-border flex-shrink-0">
            <div className="min-w-0">
              <p className="text-base font-semibold text-foreground">Modules</p>
              <p className="text-xs text-muted-foreground truncate">{epic.title}</p>
            </div>
            <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex-shrink-0">
              <X size={16} />
            </button>
          </div>

          {/* add module */}
          <div className="px-5 py-3 border-b border-border/50 flex-shrink-0 flex flex-col gap-2">
            <input
              value={newTitle}
              onChange={(e) => { setNewTitle(e.target.value); setError("") }}
              placeholder="New module name"
              className="w-full h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
            <textarea
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="Scope / description (optional) — interns will see this"
              rows={2}
              className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-none focus:outline-none focus:border-primary transition-colors"
            />
            <div className="flex items-center gap-2">
              <button
                onClick={() => createMut.mutate()}
                disabled={!newTitle.trim() || createMut.isPending}
                className="flex items-center gap-1 h-9 px-4 bg-primary text-primary-foreground text-xs font-medium rounded-xl hover:bg-primary/95 transition-colors disabled:opacity-50 ml-auto"
              >
                <Plus size={13} /> Add module
              </button>
            </div>
            {error && <p className="text-xs text-red-500">{error}</p>}
          </div>

          {/* module list */}
          <div className="overflow-y-auto flex-1 p-3 flex flex-col gap-2">
            {isLoading ? (
              <div className="flex items-center justify-center h-20">
                <div className="w-5 h-5 border-2 border-muted border-t-transparent rounded-full animate-spin" />
              </div>
            ) : modules.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">No modules yet</p>
            ) : (
              modules.map((m) => (
                <div key={m.id} className="border border-border rounded-xl p-3 bg-muted/20">
                  <div className="flex items-start gap-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground">{m.title}</p>
                      {m.description ? (
                        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed line-clamp-2">{m.description}</p>
                      ) : (
                        <p className="text-xs text-muted-foreground/60 mt-0.5 italic">No description — interns won't see scope context</p>
                      )}
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <button
                        onClick={() => setViewModule(m)}
                        title="View details"
                        className="p-1.5 rounded-lg text-muted-foreground hover:text-[#643f83] dark:hover:text-[#d6c7e1] hover:bg-muted transition-colors"
                      >
                        <Eye size={12} />
                      </button>
                      <button
                        onClick={() => setEditModule(m)}
                        className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                      >
                        <Pencil size={12} />
                      </button>
                      <button
                        onClick={() => { if (confirm(`Delete module "${m.title}"? Its tasks will be deleted too.`)) deleteMut.mutate(m.id) }}
                        disabled={deleteMut.isPending}
                        className="p-1.5 rounded-lg text-muted-foreground hover:text-red-500 hover:bg-red-500/10 dark:hover:bg-red-500/20 transition-colors disabled:opacity-50"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {viewModule && (
        <ModuleDetailDialog
          module={viewModule}
          onClose={() => setViewModule(null)}
        />
      )}

      {editModule && (
        <ModuleEditDialog
          module={editModule}
          onSave={(title, desc) => updateMut.mutate({ title, desc })}
          onClose={() => setEditModule(null)}
          isPending={updateMut.isPending}
        />
      )}
    </>,
    document.body
  )
}
