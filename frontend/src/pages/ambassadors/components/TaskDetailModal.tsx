import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Pencil, Trash2 } from "lucide-react"
import type { Task } from "@/types/ambassadors"
import { updateTaskStatusApi, editTaskApi, deleteTaskApi } from "@/api/ambassadors/tasks"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { StatusPill } from "./common"

/** role: "assignee" (the ambassador the task is assigned to) or
 *  "reviewer" (the admin / ambassador who created it). */
export function TaskDetailModal({
  task,
  role,
  onClose,
}: {
  task: Task
  role: "assignee" | "reviewer"
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [submission, setSubmission] = useState(task.submission ?? "")
  const [reviewNotes, setReviewNotes] = useState("")
  const [editing, setEditing] = useState(false)
  const [edit, setEdit] = useState({
    title: task.title,
    description: task.description ?? "",
    points_reward: task.points_reward,
    deadline: task.deadline ? task.deadline.slice(0, 10) : "",
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["tasks"] })
    qc.invalidateQueries({ queryKey: ["admin-tasks"] })
    qc.invalidateQueries({ queryKey: ["dashboard"] })
    qc.invalidateQueries({ queryKey: ["notifications"] })
  }

  const mutation = useMutation({
    mutationFn: (vars: { status: string; submission?: string; edit_notes?: string }) =>
      updateTaskStatusApi(task.id, vars.status, { submission: vars.submission, edit_notes: vars.edit_notes }),
    onSuccess: () => { refresh(); onClose() },
  })

  const saveEdit = useMutation({
    mutationFn: () => editTaskApi(task.id, {
      title: edit.title,
      description: edit.description || undefined,
      points_reward: Number(edit.points_reward),
      deadline: edit.deadline ? new Date(edit.deadline).toISOString() : null,
    }),
    onSuccess: () => { refresh(); onClose() },
  })

  const remove = useMutation({
    mutationFn: () => deleteTaskApi(task.id),
    onSuccess: () => { refresh(); onClose() },
  })

  const canManage = role === "reviewer"

  // Mirrors the backend state machine: pending → accepted → submitted → review.
  const canSubmit = role === "assignee" && ["accepted", "edit_requested"].includes(task.status)
  const canAccept = role === "assignee" && task.status === "pending"
  const canReview = role === "reviewer" && task.status === "submitted"
  const canRevoke = role === "reviewer" && task.status === "approved"

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 flex-wrap pr-6">
            {task.title}
            <StatusPill status={task.status} />
            <span className="text-xs font-semibold text-affair dark:text-heliotrope bg-snuff/40 dark:bg-snuff/10 px-2 py-0.5 rounded-full">{task.points_reward} pts</span>
          </DialogTitle>
        </DialogHeader>

        {editing ? (
          <form onSubmit={(e) => { e.preventDefault(); saveEdit.mutate() }} className="mt-2 space-y-3">
            <input className="input" placeholder="Title" value={edit.title} onChange={(e) => setEdit((s) => ({ ...s, title: e.target.value }))} required />
            <textarea className="input h-24 py-2 resize-none" placeholder="Description" value={edit.description} onChange={(e) => setEdit((s) => ({ ...s, description: e.target.value }))} />
            <div className="flex gap-3">
              <input className="input" type="number" min={0} placeholder="Points" value={edit.points_reward} onChange={(e) => setEdit((s) => ({ ...s, points_reward: Number(e.target.value) }))} />
              <input className="input" type="date" value={edit.deadline} onChange={(e) => setEdit((s) => ({ ...s, deadline: e.target.value }))} />
            </div>
            <div className="flex gap-2">
              <Button type="submit" variant="default" disabled={saveEdit.isPending}>{saveEdit.isPending ? "Saving…" : "Save changes"}</Button>
              <Button type="button" variant="outline" onClick={() => setEditing(false)}>Cancel</Button>
            </div>
          </form>
        ) : (
        <div className="mt-2 space-y-3 text-sm">
          {task.deadline && <p className="text-gray-500">Due <span className="text-foreground font-medium">{new Date(task.deadline).toLocaleDateString()}</span></p>}

          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-1">Description</p>
            <p className="text-gray-700 dark:text-zinc-300 whitespace-pre-wrap">{task.description || "No description provided."}</p>
          </div>

          {task.edit_notes && (
            <div className="rounded-lg bg-purple-50 dark:bg-purple-950/20 border border-purple-100 dark:border-purple-900/50 p-3">
              <p className="text-xs font-semibold text-purple-700 dark:text-purple-400 mb-0.5">Revision requested</p>
              <p className="text-purple-700 dark:text-purple-300 whitespace-pre-wrap">{task.edit_notes}</p>
            </div>
          )}

          {/* Submission */}
          {canSubmit || canAccept ? (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-1">Your submission</p>
              <textarea
                className="input h-24 py-2 resize-none w-full"
                placeholder="Paste a link to your work, or describe what you did…"
                value={submission}
                onChange={(e) => setSubmission(e.target.value)}
              />
            </div>
          ) : (
            task.submission && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-1">Submission</p>
                <p className="text-gray-700 dark:text-zinc-300 whitespace-pre-wrap break-words">{task.submission}</p>
              </div>
            )
          )}

          {/* Reviewer revision notes */}
          {canReview && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-1">Revision notes (optional)</p>
              <textarea
                className="input h-16 py-2 resize-none w-full"
                placeholder="Needed only if you request changes…"
                value={reviewNotes}
                onChange={(e) => setReviewNotes(e.target.value)}
              />
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap gap-2 pt-1">
            {canAccept && (
              <Button variant="outline" disabled={mutation.isPending} onClick={() => mutation.mutate({ status: "accepted" })}>Accept</Button>
            )}
            {canSubmit && (
              <Button variant="default" disabled={mutation.isPending || !submission.trim()} onClick={() => mutation.mutate({ status: "submitted", submission })}>
                {task.status === "edit_requested" ? "Resubmit" : "Submit work"}
              </Button>
            )}
            {canReview && (
              <>
                <Button variant="default" disabled={mutation.isPending} onClick={() => mutation.mutate({ status: "approved" })}>Approve · +{task.points_reward}</Button>
                <Button variant="outline" disabled={mutation.isPending} onClick={() => mutation.mutate({ status: "edit_requested", edit_notes: reviewNotes })}>Request changes</Button>
                <Button variant="destructive" disabled={mutation.isPending} onClick={() => mutation.mutate({ status: "rejected" })}>Reject</Button>
              </>
            )}
            {canRevoke && (
              <Button variant="destructive" disabled={mutation.isPending}
                onClick={() => { if (confirm(`Revoke approval? ${task.points_reward} points will be reclaimed.`)) mutation.mutate({ status: "edit_requested", edit_notes: reviewNotes }) }}>
                Revoke approval · −{task.points_reward}
              </Button>
            )}
          </div>

          {/* Manage (creator / admin) */}
          {canManage && (
            <div className="flex gap-2 pt-2 border-t border-gray-100 dark:border-zinc-800">
              <Button variant="ghost" size="sm" onClick={() => setEditing(true)}><Pencil size={14} /> Edit</Button>
              <Button variant="ghost" size="sm" disabled={remove.isPending}
                onClick={() => { if (confirm(`Delete task "${task.title}"? This can't be undone.`)) remove.mutate() }}>
                <Trash2 size={14} /> Delete
              </Button>
            </div>
          )}
        </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
