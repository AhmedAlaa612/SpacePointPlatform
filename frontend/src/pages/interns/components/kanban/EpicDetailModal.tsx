import { useState } from "react"
import { createPortal } from "react-dom"
import { cn } from "@/lib/utils"
import { X, Eye, Pencil, Check } from "lucide-react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import type { Epic, Module, WorkStatus } from "@/types/interns"
import ModuleDetailDialog from "@/pages/interns/components/ModuleDetailDialog"
import { updateLeaderEpicApi } from "@/api/interns/epics"

const STATUS_LABEL: Record<string, string> = {
  todo: "To do",
  in_progress: "In progress",
  done: "Done",
}

const STATUS_STYLE: Record<string, string> = {
  todo: "bg-gray-100 text-gray-500",
  in_progress: "bg-[#d6c7e1] text-[#643f83]",
  done: "bg-black text-white",
}

interface Props {
  epic: Epic | null
  projectName: string
  open: boolean
  onClose: () => void
}

export default function EpicDetailModal({ epic, projectName, open, onClose }: Props) {
  const queryClient = useQueryClient()
  const [viewModule,  setViewModule]  = useState<Module | null>(null)
  const [editing,     setEditing]     = useState(false)
  const [editTitle,   setEditTitle]   = useState("")
  const [editDesc,    setEditDesc]    = useState("")
  const [editStatus,  setEditStatus]  = useState<WorkStatus>("todo")

  const openEdit = () => {
    setEditTitle(epic!.title)
    setEditDesc(epic!.description ?? "")
    setEditStatus(epic!.status as WorkStatus)
    setEditing(true)
  }

  const saveMutation = useMutation({
    mutationFn: () => updateLeaderEpicApi(epic!.id, {
      title:       editTitle.trim() || undefined,
      description: editDesc.trim()  || undefined,
      status:      editStatus,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["epics", "leader"] })
      setEditing(false)
    },
  })

  if (!epic || !open) return null

  const totalTasks = epic.modules.reduce((acc, m) => acc + m.tasks.length, 0)
  const doneTasks  = epic.modules.reduce(
    (acc, m) => acc + m.tasks.filter((t) => t.status === "done").length,
    0
  )

  const nonEmptyModules = epic.modules.filter((m) => m.tasks.length > 0)

  return createPortal(
    <>
      <div
        className="fixed inset-0 bg-black/40 z-[9990] flex items-center justify-center p-4"
        onClick={onClose}
      >
        <div
          className="w-full max-w-md bg-white border border-gray-100 shadow-xl rounded-2xl overflow-hidden flex flex-col max-h-[85vh]"
          onClick={(e) => e.stopPropagation()}
        >
          {/* header */}
          <div className="flex items-start justify-between gap-3 px-6 pt-6 pb-4 border-b border-gray-100 flex-shrink-0">
            <div className="min-w-0">
              <span className="text-[9px] font-bold uppercase tracking-widest text-[#643f83]">Epic</span>
              <p className="text-base font-semibold text-black leading-snug mt-0.5">{epic.title}</p>
              {projectName && (
                <p className="text-xs text-gray-400 mt-0.5">{projectName}</p>
              )}
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <span className={cn(
                "text-[10px] font-semibold px-2.5 py-1 rounded-full whitespace-nowrap",
                STATUS_STYLE[epic.status] ?? STATUS_STYLE.todo
              )}>
                {STATUS_LABEL[epic.status] ?? epic.status}
              </span>
              {!editing && (
                <button onClick={openEdit} className="p-1.5 rounded-lg text-gray-400 hover:text-black hover:bg-gray-100 transition-colors" title="Edit epic">
                  <Pencil size={14} />
                </button>
              )}
              <button onClick={onClose} className="p-1.5 rounded-lg text-gray-400 hover:text-black transition-colors">
                <X size={15} />
              </button>
            </div>
          </div>

          {/* body */}
          <div className="overflow-y-auto flex-1 px-6 py-4 flex flex-col gap-4">

            {editing ? (
              <div className="flex flex-col gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1.5">Title</label>
                  <input value={editTitle} onChange={(e) => setEditTitle(e.target.value)}
                    className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-black transition-colors" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1.5">Description</label>
                  <textarea value={editDesc} onChange={(e) => setEditDesc(e.target.value)}
                    rows={4} placeholder="Optional"
                    className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:border-black transition-colors" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1.5">Status</label>
                  <select value={editStatus} onChange={(e) => setEditStatus(e.target.value as WorkStatus)}
                    className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm bg-white focus:outline-none focus:border-black transition-colors">
                    <option value="todo">To do</option>
                    <option value="in_progress">In progress</option>
                    <option value="done">Done</option>
                  </select>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => setEditing(false)}
                    className="flex-1 h-10 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors">
                    Cancel
                  </button>
                  <button onClick={() => saveMutation.mutate()}
                    disabled={!editTitle.trim() || saveMutation.isPending}
                    className="flex-1 h-10 bg-black text-white rounded-xl text-sm font-medium hover:bg-gray-900 transition-colors disabled:opacity-50 flex items-center justify-center gap-1.5">
                    <Check size={14} /> {saveMutation.isPending ? "Saving…" : "Save"}
                  </button>
                </div>
              </div>
            ) : epic.description ? (
              <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">{epic.description}</p>
            ) : (
              <p className="text-sm text-gray-300 italic">No description provided.</p>
            )}

            {/* progress */}
            <div className="flex items-center gap-3 text-xs text-gray-500 bg-gray-50 rounded-xl px-3 py-2.5">
              <span className="font-medium text-black">{doneTasks}/{totalTasks}</span>
              tasks done
              {totalTasks > 0 && (
                <>
                  <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[#643f83] rounded-full transition-all"
                      style={{ width: `${Math.round((doneTasks / totalTasks) * 100)}%` }}
                    />
                  </div>
                  <span>{Math.round((doneTasks / totalTasks) * 100)}%</span>
                </>
              )}
            </div>

            {/* modules */}
            {nonEmptyModules.length > 0 && (
              <div>
                <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Modules</p>
                <div className="flex flex-col gap-1.5">
                  {nonEmptyModules.map((m) => {
                    const mDone = m.tasks.filter((t) => t.status === "done").length
                    return (
                      <div key={m.id} className="flex items-center justify-between px-3 py-2 rounded-xl border border-gray-100 bg-gray-50/60 gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-black font-medium truncate">{m.title}</p>
                          <p className="text-[11px] text-gray-400">{mDone}/{m.tasks.length} done</p>
                        </div>
                        <button
                          onClick={() => setViewModule(m)}
                          title="View module details"
                          className="p-1.5 rounded-lg text-gray-400 hover:text-[#643f83] hover:bg-purple-50 transition-colors flex-shrink-0"
                        >
                          <Eye size={13} />
                        </button>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            <p className="text-[11px] text-gray-300">
              Created {new Date(epic.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
            </p>
          </div>
        </div>
      </div>

      {viewModule && (
        <ModuleDetailDialog
          module={viewModule}
          onClose={() => setViewModule(null)}
        />
      )}
    </>,
    document.body
  )
}
