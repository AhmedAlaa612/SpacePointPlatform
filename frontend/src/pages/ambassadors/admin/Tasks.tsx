import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MessageSquare, Plus } from "lucide-react"
import { getTasksApi, getAssignableUsersApi, createTaskApi } from "@/api/ambassadors/tasks"
import type { Task } from "@/types/ambassadors"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner, StatusPill } from "@/pages/ambassadors/components/common"
import { TaskDetailModal } from "@/pages/ambassadors/components/TaskDetailModal"

export default function AmbassadorsAdminTasks() {
  return (
    <div>
      <PageHeader title="Ambassadors Admin" subtitle="Assign and review tasks." />
      <TasksAdmin />
    </div>
  )
}

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
