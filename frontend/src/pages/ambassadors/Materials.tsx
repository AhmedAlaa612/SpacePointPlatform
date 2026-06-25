import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus, Pencil, Trash2, ExternalLink, Copy, Search } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { getMaterialsApi, createMaterialApi, updateMaterialApi, deleteMaterialApi } from "@/api/ambassadors/materials"
import type { Material } from "@/types/ambassadors"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { PageHeader, Spinner, EmptyState } from "@/pages/ambassadors/components/common"

export default function Materials() {
  const { currentUser } = useAuth()
  const qc = useQueryClient()
  const [q, setQ] = useState("")
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Material | null>(null)

  const canManage = currentUser?.roles?.includes("admin") || currentUser?.roles?.includes("ambassador")
  const { data: materials = [], isLoading } = useQuery({
    queryKey: ["materials", q],
    queryFn: () => getMaterialsApi(q || undefined),
  })
  const refresh = () => qc.invalidateQueries({ queryKey: ["materials"] })
  const remove = useMutation({ mutationFn: deleteMaterialApi, onSuccess: refresh })

  const canEditItem = (m: Material) =>
    currentUser?.roles?.includes("admin") || m.created_by === currentUser?.id

  return (
    <div>
      <PageHeader
        title="Materials"
        subtitle="Shared slides, decks and guides for your sessions."
        action={canManage ? <Button onClick={() => setCreating(true)}><Plus size={16} /> Add material</Button> : undefined}
      />

      <div className="relative mb-5 max-w-sm">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input className="input pl-9 w-full" placeholder="Search materials…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {isLoading ? (
        <Spinner />
      ) : materials.length === 0 ? (
        <Card><CardContent className="p-0"><EmptyState title="No materials yet" hint={canManage ? "Add the first resource to the library." : "Your ambassador hasn't shared materials yet."} /></CardContent></Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {materials.map((m) => (
            <Card key={m.id}>
              <CardContent className="p-5 flex flex-col gap-2 h-full">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-semibold text-foreground min-w-0">{m.title}</p>
                  {m.category && <span className="text-[10px] font-bold uppercase text-affair dark:text-heliotrope bg-snuff/40 dark:bg-snuff/10 px-2 py-0.5 rounded-full shrink-0">{m.category}</span>}
                </div>
                {m.description && <p className="text-sm text-muted-foreground dark:text-zinc-300 line-clamp-3">{m.description}</p>}
                <p className="text-xs text-gray-400 mt-auto pt-2">
                  {m.created_by_name ? `Added by ${m.created_by_name} · ` : ""}{new Date(m.created_at).toLocaleDateString()}
                </p>
                <div className="flex items-center gap-2 pt-1">
                  <a href={m.link} target="_blank" rel="noreferrer" className="flex-1">
                    <Button size="sm" variant="outline" className="w-full"><ExternalLink size={14} /> Open</Button>
                  </a>
                  <Button size="sm" variant="ghost" onClick={() => navigator.clipboard?.writeText(m.link)} title="Copy link"><Copy size={14} /></Button>
                  {canEditItem(m) && (
                    <>
                      <Button size="sm" variant="ghost" onClick={() => setEditing(m)}><Pencil size={14} /></Button>
                      <Button size="sm" variant="ghost" disabled={remove.isPending}
                        onClick={() => { if (confirm(`Delete "${m.title}" from the library?`)) remove.mutate(m.id) }}>
                        <Trash2 size={14} />
                      </Button>
                    </>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {creating && <MaterialModal onClose={() => setCreating(false)} onSaved={refresh} />}
      {editing && <MaterialModal material={editing} onClose={() => setEditing(null)} onSaved={refresh} />}
    </div>
  )
}

function MaterialModal({ material, onClose, onSaved }: { material?: Material; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    title: material?.title ?? "",
    description: material?.description ?? "",
    link: material?.link ?? "",
    category: material?.category ?? "",
  })
  const [error, setError] = useState("")
  const mutation = useMutation({
    mutationFn: () => {
      const data = {
        title: form.title,
        description: form.description || undefined,
        link: form.link,
        category: form.category || undefined,
      }
      return material ? updateMaterialApi(material.id, data) : createMaterialApi(data)
    },
    onSuccess: () => { onSaved(); onClose() },
    onError: (e: any) => setError(e?.response?.data?.detail || "Failed to save material."),
  })

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{material ? "Edit material" : "Add material"}</DialogTitle></DialogHeader>
        <form onSubmit={(e) => { e.preventDefault(); setError(""); mutation.mutate() }} className="flex flex-col gap-3 mt-2">
          <input className="input" placeholder="Title" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} required />
          <input className="input" placeholder="Link (https://… slides, deck, guide)" value={form.link} onChange={(e) => setForm((f) => ({ ...f, link: e.target.value }))} required />
          <input className="input" placeholder="Category (optional, e.g. Workshops)" value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))} />
          <textarea className="input h-20 py-2 resize-none" placeholder="Description (optional)" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
          {error && <p className="text-sm text-red-500">{error}</p>}
          <Button type="submit" disabled={mutation.isPending} className="mt-1">{mutation.isPending ? "Saving…" : "Save"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
