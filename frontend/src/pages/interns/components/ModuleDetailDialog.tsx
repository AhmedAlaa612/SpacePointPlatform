import { createPortal } from "react-dom"
import { ArrowLeft, CalendarDays, Clock, Users, X } from "lucide-react"
import type { Module, TaskBrief } from "@/types/interns"

const STATUS_COLORS: Record<string, string> = {
  todo: "bg-gray-200",
  in_progress: "bg-blue-400",
  in_review: "bg-yellow-400",
  done: "bg-green-400",
}
const STATUS_LABEL: Record<string, string> = {
  todo: "To do",
  in_progress: "In progress",
  in_review: "In review",
  done: "Done",
}

export default function ModuleDetailDialog({ module: m, onClose }: {
  module: Module
  onClose: () => void
}) {
  return createPortal(
    <div className="fixed inset-0 bg-black/40 z-[9999] flex items-center justify-center p-4" onClick={(e) => e.stopPropagation()}>
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-2xl flex flex-col max-h-[80vh] overflow-hidden">

        {/* header */}
        <div className="flex items-center gap-2 px-5 pt-5 pb-3 border-b border-gray-100 flex-shrink-0">
          <button onClick={onClose} className="p-1.5 rounded-lg text-gray-400 hover:text-black transition-colors flex-shrink-0">
            <ArrowLeft size={15} />
          </button>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-black truncate">{m.title}</p>
            <p className="text-xs text-gray-400">{m.tasks.length} task{m.tasks.length !== 1 ? "s" : ""}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-gray-400 hover:text-black transition-colors flex-shrink-0">
            <X size={15} />
          </button>
        </div>

        {/* body */}
        <div className="overflow-y-auto flex-1 px-5 py-4 flex flex-col gap-4">

          {/* description */}
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-1.5">Description</p>
            {m.description ? (
              <p className="text-sm text-gray-700 leading-relaxed">{m.description}</p>
            ) : (
              <p className="text-sm text-gray-300 italic">No description added</p>
            )}
          </div>

          {/* created */}
          <div className="flex items-center gap-1.5 text-xs text-gray-400">
            <CalendarDays size={12} />
            Created {new Date(m.created_at).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" })}
          </div>

          {/* tasks */}
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-2">Tasks</p>
            {m.tasks.length === 0 ? (
              <p className="text-sm text-gray-300 italic">No tasks in this module yet</p>
            ) : (
              <div className="flex flex-col gap-2">
                {m.tasks.map((t: TaskBrief) => (
                  <div key={t.id} className="border border-gray-100 rounded-xl p-3">
                    <div className="flex items-start gap-2">
                      <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${STATUS_COLORS[t.status] ?? "bg-gray-300"}`} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-black leading-snug">{t.title}</p>
                        <p className="text-xs text-gray-400 mt-0.5">{STATUS_LABEL[t.status] ?? t.status}</p>
                        <div className="flex flex-wrap gap-2 mt-2">
                          {t.due_date && (
                            <span className="flex items-center gap-1 text-[11px] text-gray-500 bg-gray-50 px-2 py-0.5 rounded-lg">
                              <CalendarDays size={10} />
                              {new Date(t.due_date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                            </span>
                          )}
                          {t.expected_time != null && (
                            <span className="flex items-center gap-1 text-[11px] text-gray-500 bg-gray-50 px-2 py-0.5 rounded-lg">
                              <Clock size={10} /> {t.expected_time}h est
                            </span>
                          )}
                          {t.actual_time != null && (
                            <span className="flex items-center gap-1 text-[11px] text-gray-500 bg-gray-50 px-2 py-0.5 rounded-lg">
                              <Clock size={10} /> {t.actual_time}h actual
                            </span>
                          )}
                          {t.assignee_count > 0 && (
                            <span className="flex items-center gap-1 text-[11px] text-gray-500 bg-gray-50 px-2 py-0.5 rounded-lg">
                              <Users size={10} /> {t.assignee_count} assignee{t.assignee_count !== 1 ? "s" : ""}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body
  )
}
