import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus, ChevronRight } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { getTasksApi, getAssignableUsersApi, createTaskApi } from "@/api/ambassadors/tasks"
import type { Task } from "@/types/ambassadors"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { PageHeader, Spinner, EmptyState, StatusPill } from "@/pages/ambassadors/components/common"
import { TaskDetailModal } from "@/pages/ambassadors/components/TaskDetailModal"

export default function Tasks() {
  const { currentUser } = useAuth()
  const qc = useQueryClient()
  const isAmbassador = currentUser?.roles?.includes("ambassador")
  const [tab, setTab] = useState<"assigned" | "created">("assigned")
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<Task | null>(null)

  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ["tasks", tab],
    queryFn: () => getTasksApi(tab),
  })

  return (
    <div>
      <PageHeader
        title="Tasks"
        subtitle="Complete assigned tasks to earn points."
        action={isAmbassador && tab === "created" ? <Button onClick={() => setOpen(true)}><Plus size={16} /> Assign task</Button> : undefined}
      />

      {isAmbassador && (
        <div className="flex rounded-lg border border-border overflow-hidden text-sm font-semibold w-fit mb-5">
          <button onClick={() => setTab("assigned")} className={tab === "assigned" ? "px-4 py-2 bg-foreground text-background" : "px-4 py-2 text-muted-foreground hover:bg-muted/50"}>Assigned to me</button>
          <button onClick={() => setTab("created")} className={tab === "created" ? "px-4 py-2 bg-foreground text-background" : "px-4 py-2 text-muted-foreground hover:bg-muted/50"}>I assigned</button>
        </div>
      )}

      {isLoading ? (
        <Spinner />
      ) : tasks.length === 0 ? (
        <Card><CardContent className="p-0"><EmptyState title="No tasks here yet" /></CardContent></Card>
      ) : (
        <div className="flex flex-col gap-3">
          {tasks.map((t) => (
            <TaskRow key={t.id} task={t} onOpen={() => setSelected(t)} />
          ))}
        </div>
      )}

      {selected && (
        <TaskDetailModal
          task={selected}
          role={tab === "assigned" ? "assignee" : "reviewer"}
          onClose={() => setSelected(null)}
        />
      )}
      <AssignTaskModal open={open} onClose={() => setOpen(false)} onSuccess={() => qc.invalidateQueries({ queryKey: ["tasks", "created"] })} />
    </div>
  )
}

function TaskRow({ task, onOpen }: { task: Task; onOpen: () => void }) {
  const needsAction =
    task.status === "pending" || task.status === "submitted" || task.status === "edit_requested"
  return (
    <Card>
      <CardContent className="p-4 sm:p-5">
        <button onClick={onOpen} className="w-full flex items-center gap-3 sm:gap-4 text-left">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="font-semibold text-foreground">{task.title}</p>
              <StatusPill status={task.status} />
              <span className="text-xs font-semibold text-affair dark:text-heliotrope bg-snuff/40 dark:bg-snuff/10 px-2 py-0.5 rounded-full">{task.points_reward} pts</span>
              {needsAction && <span className="w-2 h-2 rounded-full bg-heliotrope" title="Needs action" />}
            </div>
            {task.description && <p className="text-sm text-gray-500 mt-1 line-clamp-1">{task.description}</p>}
            {task.deadline && <p className="text-xs text-gray-400 mt-1">Due {new Date(task.deadline).toLocaleDateString()}</p>}
          </div>
          <ChevronRight size={18} className="text-gray-300 shrink-0" />
        </button>
      </CardContent>
    </Card>
  )
}

function AssignTaskModal({ open, onClose, onSuccess }: { open: boolean; onClose: () => void; onSuccess: () => void }) {
  const [form, setForm] = useState({ assigned_to: "", title: "", description: "", points_reward: 100, deadline: "" })
  const [error, setError] = useState("")
  const { data: users = [] } = useQuery({ queryKey: ["assignable"], queryFn: getAssignableUsersApi, enabled: open })

  const mutation = useMutation({
    mutationFn: () =>
      createTaskApi({
        assigned_to: form.assigned_to,
        title: form.title,
        description: form.description || undefined,
        points_reward: Number(form.points_reward),
        deadline: form.deadline ? new Date(form.deadline).toISOString() : null,
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
            <option value="">Select a teacher…</option>
            {users.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
          <input className="input" placeholder="Task title" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} required />
          <textarea className="input h-20 py-2 resize-none" placeholder="Description" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
          <div className="flex gap-3">
            <input className="input" type="number" min={0} placeholder="Points" value={form.points_reward} onChange={(e) => setForm((f) => ({ ...f, points_reward: Number(e.target.value) }))} />
            <input className="input" type="date" value={form.deadline} onChange={(e) => setForm((f) => ({ ...f, deadline: e.target.value }))} />
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
          <Button type="submit" disabled={mutation.isPending} className="mt-1">{mutation.isPending ? "Creating…" : "Assign task"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
