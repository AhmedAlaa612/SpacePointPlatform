import { useState } from "react"
import { Link } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ExternalLink, MessageSquare, Pencil, Plus, Trash2 } from "lucide-react"
import { getUsersApi } from "@/api/admin/users"
import {
  getActivityLogApi,
  getAmbassadorNetworkApi,
  getFullNetworkApi,
  getSettingsApi,
  updateSettingApi,
} from "@/api/ambassadors/admin"
import { getLeadsApi, updateLeadStatusApi } from "@/api/ambassadors/leads"
import { getTasksApi, getAssignableUsersApi, createTaskApi } from "@/api/ambassadors/tasks"
import { getTitlesApi, createTitleApi, updateTitleApi, deleteTitleApi } from "@/api/ambassadors/titles"
import { getBadgesApi, getCriteriaTypesApi, createBadgeApi, updateBadgeApi, deleteBadgeApi } from "@/api/ambassadors/badges"
import { getAllSessionsApi } from "@/api/ambassadors/network"
import type { Badge, Lead, Task, TeacherSession, Title } from "@/types/ambassadors"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner, StatusPill } from "@/pages/ambassadors/components/common"
import { DynamicIcon, ICON_NAMES } from "@/pages/ambassadors/components/icons"
import { TitleBadge } from "@/pages/ambassadors/components/title"
import { FullNetworkTree } from "@/pages/ambassadors/components/FullNetworkTree"
import { NetworkTree } from "@/pages/ambassadors/components/NetworkTree"
import { LeadDetailModal } from "@/pages/ambassadors/components/LeadDetailModal"
import { TaskDetailModal } from "@/pages/ambassadors/components/TaskDetailModal"
import { SessionDetailModal } from "@/pages/ambassadors/components/SessionDetailModal"
import { cn } from "@/lib/utils"

const TABS = ["Network", "Tasks", "Leads", "Sessions", "Titles", "Badges", "Settings"] as const
type Tab = (typeof TABS)[number]

export default function AmbassadorsAdmin() {
  const [tab, setTab] = useState<Tab>("Network")
  return (
    <div>
      <PageHeader title="Ambassadors Admin" subtitle="Network, tasks, leads, sessions and rewards." />
      <div className="flex gap-1 mb-6 border-b border-border overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors border-b-2 -mb-px",
              tab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === "Network" && <NetworkAdmin />}
      {tab === "Tasks" && <TasksAdmin />}
      {tab === "Leads" && <LeadsAdmin />}
      {tab === "Sessions" && <SessionsAdmin />}
      {tab === "Titles" && <TitlesAdmin />}
      {tab === "Badges" && <BadgesAdmin />}
      {tab === "Settings" && <SettingsAdmin />}
    </div>
  )
}

/* ================================================================== */
/* Network                                                              */

function NetworkAdmin() {
  const [view, setView] = useState<"full" | "ambassador">("full")
  const [selected, setSelected] = useState("")

  const users = useQuery({ queryKey: ["admin-users-all"], queryFn: getUsersApi })
  const ambassadors = (users.data ?? []).filter((u) => u.roles.includes("ambassador") && u.status === "active")

  const full = useQuery({ queryKey: ["admin-full-network"], queryFn: getFullNetworkApi, enabled: view === "full" })
  const single = useQuery({
    queryKey: ["admin-network", selected], queryFn: () => getAmbassadorNetworkApi(selected),
    enabled: view === "ambassador" && !!selected,
  })

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-4">
        <div className="flex rounded-lg border border-border overflow-hidden text-sm font-semibold w-fit">
          <button onClick={() => setView("full")} className={cn("px-4 py-2", view === "full" ? "bg-primary text-primary-foreground" : "text-muted-foreground")}>Full network</button>
          <button onClick={() => setView("ambassador")} className={cn("px-4 py-2", view === "ambassador" ? "bg-primary text-primary-foreground" : "text-muted-foreground")}>By ambassador</button>
        </div>
        {view === "ambassador" && (
          <select className="input !w-auto" value={selected} onChange={(e) => setSelected(e.target.value)}>
            <option value="">Select an ambassador…</option>
            {ambassadors.map((a) => <option key={a.id} value={a.id}>{a.full_name}</option>)}
          </select>
        )}
      </div>

      {view === "full" ? (
        full.isLoading || !full.data ? <Spinner /> : full.data.ambassadors.length === 0 ? (
          <EmptyState title="No active ambassadors yet" />
        ) : (
          <>
            <Card className="mb-5">
              <CardHeader><CardTitle>Platform network</CardTitle></CardHeader>
              <CardContent><FullNetworkTree ambassadors={full.data.ambassadors} /></CardContent>
            </Card>
            <ActivityLog />
          </>
        )
      ) : !selected ? (
        <EmptyState title="Pick an ambassador" hint="See their teacher/instructor network and sessions." />
      ) : single.isLoading || !single.data ? <Spinner /> : (
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>{single.data.ambassador.full_name}'s network</CardTitle>
            <Link to="/ambassadors/admin/ambassador/$ambassadorId" params={{ ambassadorId: selected }}>
              <Button size="sm" variant="outline"><ExternalLink size={14} className="mr-1.5" /> Full profile</Button>
            </Link>
          </CardHeader>
          <CardContent>
            <NetworkTree
              rootName={single.data.ambassador.full_name}
              teachers={single.data.teachers as any}
              instructors={single.data.instructors as any}
              sessions={single.data.sessions as any}
            />
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function ActivityLog() {
  const { data: events = [], isLoading } = useQuery({ queryKey: ["admin-activity"], queryFn: () => getActivityLogApi(80) })
  const KIND_STYLES: Record<string, string> = {
    points: "bg-green-50 text-green-600 dark:bg-green-950/30 dark:text-green-400",
    lead: "bg-blue-50 text-blue-600 dark:bg-blue-950/30 dark:text-blue-400",
    task: "bg-primary/15 text-primary",
    session: "bg-amber-50 text-amber-600 dark:bg-amber-950/30 dark:text-amber-400",
    signup: "bg-muted text-muted-foreground",
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Global activity</CardTitle>
        <p className="text-xs text-muted-foreground">All traffic across the platform, newest first.</p>
      </CardHeader>
      <CardContent>
        {isLoading ? <Spinner /> : events.length === 0 ? <EmptyState title="No activity yet" /> : (
          <div className="max-h-[420px] overflow-y-auto divide-y divide-border pr-1">
            {events.map((e, i) => (
              <div key={i} className="flex items-center justify-between gap-3 py-2.5">
                <div className="flex items-center gap-3 min-w-0">
                  <span className={cn("text-[10px] font-bold uppercase px-2 py-0.5 rounded-full shrink-0", KIND_STYLES[e.kind])}>{e.kind}</span>
                  <div className="min-w-0">
                    <p className="text-sm truncate">{e.actor && <span className="font-medium">{e.actor}</span>} {e.text}</p>
                    <p className="text-xs text-muted-foreground">{new Date(e.created_at).toLocaleString()}</p>
                  </div>
                </div>
                {e.amount != null && (
                  <span className={cn("text-sm font-semibold shrink-0", e.amount < 0 ? "text-destructive" : "text-green-600 dark:text-green-400")}>
                    {e.amount < 0 ? "" : "+"}{e.amount.toLocaleString()}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/* ================================================================== */
/* Tasks                                                                */

function TasksAdmin() {
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<Task | null>(null)
  const qc = useQueryClient()
  const { data: tasks = [], isLoading } = useQuery({ queryKey: ["admin-tasks"], queryFn: () => getTasksApi() })
  const refresh = () => { qc.invalidateQueries({ queryKey: ["admin-tasks"] }); qc.invalidateQueries({ queryKey: ["dashboard"] }) }

  return (
    <div>
      <div className="flex justify-end mb-4">
        <Button onClick={() => setOpen(true)}><Plus size={16} className="mr-1.5" /> Assign task</Button>
      </div>
      {isLoading ? <Spinner /> : tasks.length === 0 ? <EmptyState title="No tasks yet" /> : (
        <div className="flex flex-col gap-3">
          {tasks.map((t) => (
            <Card key={t.id}>
              <CardContent className="p-4 sm:p-5">
                <button onClick={() => setSelected(t)} className="w-full flex items-center justify-between gap-3 text-left">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-semibold">{t.title}</p>
                      <StatusPill status={t.status} />
                      <span className="text-xs font-semibold text-primary bg-primary/10 px-2 py-0.5 rounded-full">{t.points_reward} pts</span>
                    </div>
                    {t.description && <p className="text-sm text-muted-foreground mt-1 line-clamp-1">{t.description}</p>}
                  </div>
                  <MessageSquare size={16} className="text-muted-foreground shrink-0" />
                </button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      {selected && <TaskDetailModal task={selected} role="reviewer" onClose={() => setSelected(null)} />}
      <AssignTaskModal open={open} onClose={() => setOpen(false)} onSuccess={refresh} />
    </div>
  )
}

function AssignTaskModal({ open, onClose, onSuccess }: { open: boolean; onClose: () => void; onSuccess: () => void }) {
  const [form, setForm] = useState({ assigned_to: "", title: "", description: "", points_reward: 100, deadline: "" })
  const [error, setError] = useState("")
  const { data: users = [] } = useQuery({ queryKey: ["assignable"], queryFn: getAssignableUsersApi, enabled: open })
  const mutation = useMutation({
    mutationFn: () => createTaskApi({
      assigned_to: form.assigned_to, title: form.title, description: form.description || undefined,
      points_reward: Number(form.points_reward), deadline: form.deadline ? new Date(form.deadline).toISOString() : null,
    }),
    onSuccess: () => { onSuccess(); onClose() },
    onError: (e: any) => setError(e?.response?.data?.detail || "Failed to create task."),
  })

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Assign a task</DialogTitle></DialogHeader>
        <form onSubmit={(e) => { e.preventDefault(); setError(""); mutation.mutate() }} className="flex flex-col gap-3 mt-2">
          <select className="input" value={form.assigned_to} onChange={(e) => setForm((f) => ({ ...f, assigned_to: e.target.value }))} required>
            <option value="">Select an ambassador or teacher…</option>
            {users.map((u) => <option key={u.id} value={u.id}>{u.full_name} ({u.roles.join("/")})</option>)}
          </select>
          <input className="input" placeholder="Task title" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} required />
          <textarea className="input h-20 py-2 resize-none" placeholder="Description" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
          <div className="flex gap-3">
            <div className="flex-1"><input className="input" type="number" min={0} placeholder="Points" value={form.points_reward} onChange={(e) => setForm((f) => ({ ...f, points_reward: Number(e.target.value) }))} /></div>
            <div className="flex-1"><input className="input" type="date" value={form.deadline} onChange={(e) => setForm((f) => ({ ...f, deadline: e.target.value }))} /></div>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" disabled={mutation.isPending} className="mt-1">{mutation.isPending ? "Creating…" : "Assign task"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/* ================================================================== */
/* Leads                                                                */

function LeadsAdmin() {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<Lead | null>(null)
  const { data: leads = [], isLoading } = useQuery({ queryKey: ["admin-leads"], queryFn: getLeadsApi })
  const status = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => updateLeadStatusApi(id, status),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-leads"] }); qc.invalidateQueries({ queryKey: ["dashboard"] }) },
  })

  if (isLoading) return <Spinner />
  if (!leads.length) return <EmptyState title="No leads submitted yet" />

  return (
    <div className="flex flex-col gap-3">
      {leads.map((l) => (
        <Card key={l.id}>
          <CardContent className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="font-semibold">{l.company || l.contact_name}</p>
                <StatusPill status={l.status} />
              </div>
              <p className="text-xs text-muted-foreground mt-1">{l.contact_name} · {l.type} · by {(l as any).ambassador_name ?? "—"}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Button size="sm" variant="outline" onClick={() => setSelected(l)}><MessageSquare size={14} className="mr-1.5" /> Details</Button>
              <select className="input !w-auto" value={l.status} onChange={(e) => status.mutate({ id: l.id, status: e.target.value })}>
                <option value="submitted">Submitted</option>
                <option value="in review">In review</option>
                <option value="converted">Converted (awards points)</option>
                <option value="closed">Closed</option>
              </select>
            </div>
          </CardContent>
        </Card>
      ))}
      {selected && <LeadDetailModal lead={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}

/* ================================================================== */
/* Sessions                                                             */

function SessionsAdmin() {
  const [selected, setSelected] = useState<TeacherSession | null>(null)
  const { data: sessions = [], isLoading } = useQuery({ queryKey: ["admin-sessions"], queryFn: getAllSessionsApi })
  if (isLoading) return <Spinner />
  if (!sessions.length) return <EmptyState title="No sessions yet" />

  const sorted = [...sessions].sort((a, b) => +new Date(a.date) - +new Date(b.date))

  return (
    <Card>
      <CardHeader><CardTitle>All sessions</CardTitle></CardHeader>
      <CardContent>
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-sm min-w-[640px]">
            <thead>
              <tr className="text-left text-muted-foreground border-b border-border">
                <th className="py-2.5 pr-3 font-semibold">Date</th>
                <th className="py-2.5 pr-3 font-semibold">Session</th>
                <th className="py-2.5 pr-3 font-semibold">Teacher</th>
                <th className="py-2.5 pr-3 font-semibold">Ambassador</th>
                <th className="py-2.5 pr-3 font-semibold text-center">Students</th>
                <th className="py-2.5 pr-3 font-semibold text-right">Status</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((s) => (
                <tr key={s.id} onClick={() => setSelected(s)} className="border-b border-border/50 last:border-0 cursor-pointer hover:bg-muted">
                  <td className="py-2.5 pr-3 text-muted-foreground whitespace-nowrap">{new Date(s.date).toLocaleDateString()}</td>
                  <td className="py-2.5 pr-3 font-medium">{s.title}</td>
                  <td className="py-2.5 pr-3 text-muted-foreground">{(s as any).teacher_name ?? "—"}</td>
                  <td className="py-2.5 pr-3 text-muted-foreground">{(s as any).ambassador_name ?? "—"}</td>
                  <td className="py-2.5 pr-3 text-center">{s.status === "done" ? s.attended_students : s.planned_students}</td>
                  <td className="py-2.5 pr-3 text-right"><StatusPill status={s.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {selected && <SessionDetailModal session={selected} role="manager" onClose={() => setSelected(null)} />}
      </CardContent>
    </Card>
  )
}

/* ================================================================== */
/* Titles                                                               */

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

/* ================================================================== */
/* Badges                                                               */

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

/* ================================================================== */
/* Settings                                                             */

const REWARD_KEYS: { key: string; label: string; def: number }[] = [
  { key: "lead_points_reward", label: "Points per converted lead", def: 1000 },
  { key: "teacher_points_reward", label: "Points per recruited teacher", def: 500 },
  { key: "instructor_points_reward", label: "Points per recruited instructor", def: 500 },
  { key: "session_points_reward", label: "Points per completed session", def: 200 },
]

function SettingsAdmin() {
  const qc = useQueryClient()
  const { data: settings, isLoading } = useQuery({ queryKey: ["admin-settings"], queryFn: getSettingsApi })
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)

  const save = useMutation({
    mutationFn: async () => {
      const entries = REWARD_KEYS.map(({ key, def }) => [key, draft[key] ?? settings?.[key] ?? String(def)] as const)
      await Promise.all(entries.map(([key, value]) => updateSettingApi(key, value)))
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-settings"] }); setSaved(true); setTimeout(() => setSaved(false), 2000) },
  })

  if (isLoading) return <Spinner />

  return (
    <Card className="max-w-xl">
      <CardHeader><CardTitle>Reward settings</CardTitle></CardHeader>
      <CardContent>
        <div className="space-y-4">
          {REWARD_KEYS.map(({ key, label, def }) => (
            <div key={key} className="flex items-center justify-between gap-3">
              <label className="text-sm">{label}</label>
              <div className="w-32">
                <input className="input" type="number" min={0} value={draft[key] ?? settings?.[key] ?? String(def)}
                  onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))} />
              </div>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-3 mt-5">
          <Button onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? "Saving…" : "Save changes"}</Button>
          {saved && <span className="text-sm text-green-600 dark:text-green-400">Saved ✓</span>}
        </div>
      </CardContent>
    </Card>
  )
}
