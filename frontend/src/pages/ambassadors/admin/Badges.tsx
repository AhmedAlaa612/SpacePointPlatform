import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Pencil, Plus, Trash2 } from "lucide-react"
import { getBadgesApi, getCriteriaTypesApi, createBadgeApi, updateBadgeApi, deleteBadgeApi } from "@/api/ambassadors/badges"
import type { Badge } from "@/types/ambassadors"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner } from "@/pages/ambassadors/components/common"
import { DynamicIcon, ICON_NAMES } from "@/pages/ambassadors/components/icons"

export default function AmbassadorsAdminBadges() {
  return (
    <div>
      <PageHeader title="Ambassadors Admin" subtitle="Manage milestone badges and unlock criteria." />
      <BadgesAdmin />
    </div>
  )
}

const CRITERIA_LABELS: Record<string, string> = {
  converted_leads: "Leads converted",
  active_teachers: "Active teachers",
  sessions_done: "Sessions delivered",
  students_reached: "Students reached",
  lifetime_points: "Lifetime points",
}

function BadgesAdmin() {
  const qc = useQueryClient()
  const { data: badges = [], isLoading } = useQuery({ queryKey: ["admin-badges"], queryFn: getBadgesApi })
  const [editing, setEditing] = useState<Badge | null>(null)
  const [creating, setCreating] = useState(false)
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-badges"] })
  const remove = useMutation({ mutationFn: deleteBadgeApi, onSuccess: refresh })

  if (isLoading) return <Spinner />

  return (
    <div>
      <div className="flex justify-end mb-4">
        <Button onClick={() => setCreating(true)}><Plus size={16} className="mr-1.5" /> Add badge</Button>
      </div>
      <Card>
        <CardHeader><CardTitle>Milestone badges</CardTitle></CardHeader>
        <CardContent>
          {badges.length === 0 ? <EmptyState title="No badges yet" hint="Add a badge and the criteria that unlocks it." /> : (
            <div className="divide-y divide-border">
              {badges.map((b) => (
                <div key={b.id} className="flex items-center justify-between py-3 gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-9 h-9 rounded-full bg-primary/10 text-primary flex items-center justify-center shrink-0">
                      <DynamicIcon name={b.icon} size={17} />
                    </div>
                    <div className="min-w-0">
                      <p className="font-medium truncate">{b.label}</p>
                      <p className="text-xs text-muted-foreground truncate">{b.description}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-[10px] font-bold uppercase text-muted-foreground">{b.audience}</span>
                    <span className="text-xs text-muted-foreground hidden sm:inline">
                      {CRITERIA_LABELS[b.criteria_type] ?? b.criteria_type} ≥ {b.threshold.toLocaleString()}
                    </span>
                    <Button size="sm" variant="ghost" onClick={() => setEditing(b)}><Pencil size={15} /></Button>
                    <button onClick={() => { if (confirm(`Delete badge "${b.label}"?`)) remove.mutate(b.id) }} className="p-1.5 text-muted-foreground hover:text-destructive"><Trash2 size={15} /></button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
      {creating && <BadgeModal onClose={() => setCreating(false)} onSaved={refresh} />}
      {editing && <BadgeModal badge={editing} onClose={() => setEditing(null)} onSaved={refresh} />}
    </div>
  )
}

function BadgeModal({ badge, onClose, onSaved }: { badge?: Badge; onClose: () => void; onSaved: () => void }) {
  const { data: criteria = {} } = useQuery({ queryKey: ["badge-criteria"], queryFn: getCriteriaTypesApi })
  const [draft, setDraft] = useState({
    label: badge?.label ?? "", description: badge?.description ?? "", icon: badge?.icon ?? "Award",
    criteria_type: badge?.criteria_type ?? "converted_leads", threshold: badge?.threshold ?? 1,
    sort_order: badge?.sort_order ?? 0, audience: (badge?.audience ?? "ambassador") as Badge["audience"],
  })
  const audienceCriteria: string[] = (criteria as any)[draft.audience] ?? Object.keys(CRITERIA_LABELS)
  const mutation = useMutation({
    mutationFn: () => (badge ? updateBadgeApi(badge.id, draft) : createBadgeApi(draft)),
    onSuccess: () => { onSaved(); onClose() },
  })

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{badge ? "Edit badge" : "Add badge"}</DialogTitle></DialogHeader>
        <form onSubmit={(e) => { e.preventDefault(); mutation.mutate() }} className="flex flex-col gap-3 mt-2">
          <input className="input" placeholder="Badge name" value={draft.label} onChange={(e) => setDraft((d) => ({ ...d, label: e.target.value }))} required />
          <input className="input" placeholder="Description" value={draft.description} onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))} />
          <select
            className="input" value={draft.audience}
            onChange={(e) => {
              const audience = e.target.value as Badge["audience"]
              setDraft((d) => {
                const allowed: string[] = (criteria as any)[audience] ?? []
                return { ...d, audience, criteria_type: allowed.includes(d.criteria_type) ? d.criteria_type : (allowed[0] ?? d.criteria_type) }
              })
            }}
          >
            <option value="ambassador">Ambassador badge</option>
            <option value="teacher">Teacher badge</option>
          </select>
          <div className="flex items-center gap-3">
            <select className="input" value={draft.icon} onChange={(e) => setDraft((d) => ({ ...d, icon: e.target.value }))}>
              {ICON_NAMES.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <DynamicIcon name={draft.icon} size={18} />
            </div>
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <select className="input" value={draft.criteria_type} onChange={(e) => setDraft((d) => ({ ...d, criteria_type: e.target.value }))}>
                {audienceCriteria.map((c) => <option key={c} value={c}>{CRITERIA_LABELS[c] ?? c}</option>)}
              </select>
            </div>
            <div className="w-28"><input className="input" type="number" min={1} placeholder="Threshold" value={draft.threshold} onChange={(e) => setDraft((d) => ({ ...d, threshold: Number(e.target.value) }))} /></div>
          </div>
          <p className="text-xs text-muted-foreground">Unlocks when {CRITERIA_LABELS[draft.criteria_type] ?? draft.criteria_type} reaches {draft.threshold}.</p>
          <Button type="submit" disabled={mutation.isPending} className="mt-1">{mutation.isPending ? "Saving…" : "Save"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
