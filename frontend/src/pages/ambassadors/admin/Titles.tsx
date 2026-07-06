import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Pencil, Plus, Trash2 } from "lucide-react"
import { getTitlesApi, createTitleApi, updateTitleApi, deleteTitleApi } from "@/api/ambassadors/titles"
import type { Title } from "@/types/ambassadors"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner } from "@/pages/ambassadors/components/common"
import { ICON_NAMES } from "@/pages/ambassadors/components/icons"
import { TitleBadge } from "@/pages/ambassadors/components/title"

export default function AmbassadorsAdminTitles() {
  return (
    <div>
      <PageHeader title="Ambassadors Admin" subtitle="Manage the ambassador and teacher title ladders." />
      <TitlesAdmin />
    </div>
  )
}

function TitlesAdmin() {
  const qc = useQueryClient()
  const { data: titles = [], isLoading } = useQuery({ queryKey: ["admin-titles"], queryFn: () => getTitlesApi() })
  const [editing, setEditing] = useState<Title | null>(null)
  const [creating, setCreating] = useState(false)
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-titles"] })
  const remove = useMutation({ mutationFn: deleteTitleApi, onSuccess: refresh })

  if (isLoading) return <Spinner />

  return (
    <div>
      <div className="flex justify-end mb-4">
        <Button onClick={() => setCreating(true)}><Plus size={16} className="mr-1.5" /> Add title</Button>
      </div>
      <Card>
        <CardHeader><CardTitle>Title ladder</CardTitle></CardHeader>
        <CardContent>
          {titles.length === 0 ? <EmptyState title="No titles yet" hint="Add the first rung of the ladder." /> : (
            <div className="divide-y divide-border">
              {titles.map((t) => (
                <div key={t.id} className="flex items-center justify-between py-3 gap-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <TitleBadge title={t} />
                    <span className="text-[10px] font-bold uppercase text-muted-foreground">{t.audience}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground">{t.min_points.toLocaleString()} pts</span>
                    <Button size="sm" variant="ghost" onClick={() => setEditing(t)}><Pencil size={15} /></Button>
                    <button onClick={() => { if (confirm(`Delete title "${t.name}"?`)) remove.mutate(t.id) }} className="p-1.5 text-muted-foreground hover:text-destructive"><Trash2 size={15} /></button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
      {creating && <TitleModal onClose={() => setCreating(false)} onSaved={refresh} />}
      {editing && <TitleModal title={editing} onClose={() => setEditing(null)} onSaved={refresh} />}
    </div>
  )
}

function TitleModal({ title, onClose, onSaved }: { title?: Title; onClose: () => void; onSaved: () => void }) {
  const [draft, setDraft] = useState<Omit<Title, "id">>(
    title
      ? { name: title.name, min_points: title.min_points, icon: title.icon ?? "Award", color: title.color ?? "#a880ff", sort_order: title.sort_order, audience: title.audience ?? "ambassador" }
      : { name: "", min_points: 0, icon: "Award", color: "#a880ff", sort_order: 0, audience: "ambassador" }
  )
  const mutation = useMutation({
    mutationFn: () => (title ? updateTitleApi(title.id, draft) : createTitleApi(draft)),
    onSuccess: () => { onSaved(); onClose() },
  })

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{title ? "Edit title" : "Add title"}</DialogTitle></DialogHeader>
        <form onSubmit={(e) => { e.preventDefault(); mutation.mutate() }} className="flex flex-col gap-3 mt-2">
          <input className="input" placeholder="Title name" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} required />
          <select className="input" value={draft.audience} onChange={(e) => setDraft((d) => ({ ...d, audience: e.target.value as Title["audience"] }))}>
            <option value="ambassador">Ambassador ladder</option>
            <option value="teacher">Teacher ladder</option>
          </select>
          <div className="flex gap-3">
            <div className="flex-1"><input className="input" type="number" min={0} placeholder="Min points" value={draft.min_points} onChange={(e) => setDraft((d) => ({ ...d, min_points: Number(e.target.value) }))} /></div>
            <div className="flex-1"><input className="input" type="number" min={0} placeholder="Sort order" value={draft.sort_order} onChange={(e) => setDraft((d) => ({ ...d, sort_order: Number(e.target.value) }))} /></div>
          </div>
          <select className="input" value={draft.icon ?? "Award"} onChange={(e) => setDraft((d) => ({ ...d, icon: e.target.value }))}>
            {ICON_NAMES.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <div className="flex items-center gap-3">
            <input type="color" value={draft.color ?? "#a880ff"} onChange={(e) => setDraft((d) => ({ ...d, color: e.target.value }))} className="h-11 w-14 rounded-lg border border-border" />
            <div className="flex-1"><TitleBadge title={{ id: "preview", ...draft }} /></div>
          </div>
          <Button type="submit" disabled={mutation.isPending} className="mt-1">{mutation.isPending ? "Saving…" : "Save"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
