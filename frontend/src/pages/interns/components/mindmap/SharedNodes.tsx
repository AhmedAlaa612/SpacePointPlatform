import { useState } from "react"
import { Handle, Position, type NodeProps } from "@xyflow/react"
import { X, MessageCircle } from "lucide-react"
import { cn } from "@/lib/utils"
import type { WorkStatus } from "@/types/interns"

// â”€â”€ Shared status styling â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export const STATUS: Record<WorkStatus, { badge: string; dot: string }> = {
  todo:        { badge: "bg-gray-100 text-gray-500",    dot: "bg-gray-300"   },
  in_progress: { badge: "bg-[#d6c7e1] text-[#643f83]", dot: "bg-[#a880ff]"  },
  done:        { badge: "bg-black text-white",           dot: "bg-black"      },
}

// â”€â”€ Project node (only used in project map) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export function ProjectNode({ data }: NodeProps) {
  return (
    <div className="bg-black text-white rounded-2xl px-10 py-6 min-w-[260px] text-center shadow-2xl select-none cursor-pointer">
      <p className="text-[9px] font-bold uppercase tracking-widest text-gray-400 mb-2">Project</p>
      <p className="text-lg font-bold leading-snug">{String(data.label)}</p>
      <p className="text-[11px] text-gray-400 mt-2">
        {String(data.epicCount)} epic{Number(data.epicCount) !== 1 ? "s" : ""} &middot; {String(data.taskCount)} task{Number(data.taskCount) !== 1 ? "s" : ""}
      </p>
      <Handle type="source" position={Position.Bottom} style={{ background: "#643f83", width: 10, height: 10 }} />
    </div>
  )
}

// â”€â”€ Epic node â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export function EpicNode({ data }: NodeProps) {
  const teamName   = (data.team_name   as string | null) ?? null
  const leaderName = (data.leader_name as string | null) ?? null
  return (
    <div className="bg-black text-white rounded-2xl px-8 py-5 min-w-[220px] text-center shadow-2xl select-none cursor-pointer">
      <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-1.5">Epic</p>
      <p className="text-base font-bold leading-snug">{String(data.label)}</p>
      <div className="flex items-center justify-center gap-1.5 mt-2">
        <span className={cn("w-2 h-2 rounded-full", STATUS[data.status as WorkStatus]?.dot ?? "bg-gray-300")} />
        <span className="text-[10px] text-gray-400">{String(data.status).replace("_", " ")}</span>
      </div>
      {(teamName || leaderName) && (
        <div className="mt-2 pt-2 border-t border-gray-700 flex flex-col gap-0.5">
          {teamName && (
            <p className="text-[10px] text-gray-400">
              <span className="text-gray-500 uppercase tracking-widest text-[8px]">Team </span>
              {teamName}
            </p>
          )}
          {leaderName && (
            <p className="text-[10px] text-gray-400">
              <span className="text-gray-500 uppercase tracking-widest text-[8px]">Leader </span>
              {leaderName}
            </p>
          )}
        </div>
      )}
      <Handle type="target" position={Position.Top}    style={{ background: "#643f83", width: 10, height: 10 }} />
      <Handle type="source" position={Position.Bottom} style={{ background: "#643f83", width: 10, height: 10 }} />
    </div>
  )
}

// â”€â”€ Module node â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export function ModuleNode({ data, selected }: NodeProps) {
  return (
    <div className={cn(
      "bg-[#643f83] text-white rounded-xl px-5 py-3.5 min-w-[180px] max-w-[240px] shadow-lg select-none transition-all cursor-pointer border-2",
      selected ? "border-white shadow-xl" : "border-transparent"
    )}>
      <p className="text-[9px] font-bold uppercase tracking-widest text-[#d6c7e1] mb-1 text-center">Module</p>
      <p className="text-sm font-bold text-center">{String(data.label)}</p>
      {!!data.description && (
        <p className="text-[10px] text-[#d6c7e1] mt-1.5 leading-relaxed line-clamp-2 text-center opacity-80">
          {String(data.description)}
        </p>
      )}
      <Handle type="target" position={Position.Top}    style={{ background: "#a880ff", width: 8, height: 8 }} />
      <Handle type="source" position={Position.Bottom} style={{ background: "#a880ff", width: 8, height: 8 }} />
    </div>
  )
}

// â”€â”€ Task node â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
type AssigneeInfo = { id: string; full_name: string; email: string; role: string; phone: string | null }

export function TaskNode({ data, selected }: NodeProps) {
  const s = STATUS[data.status as WorkStatus] ?? STATUS.todo
  const assignees = (data.assignees as AssigneeInfo[] | undefined) ?? []
  const [activeAssignee, setActiveAssignee] = useState<AssigneeInfo | null>(null)

  const roleBadge: Record<string, string> = {
    admin:  "bg-black text-white",
    leader: "bg-[#643f83] text-white",
    intern: "bg-[#d6c7e1] text-[#643f83]",
  }

  return (
    <div className={cn(
      "bg-white rounded-xl px-3.5 py-3 min-w-[170px] max-w-[220px] shadow-md select-none transition-all cursor-pointer border-2",
      selected ? "border-black shadow-lg" : "border-gray-100 hover:border-gray-300"
    )}>
      <Handle type="target" position={Position.Top} style={{ background: "#d6c7e1", width: 8, height: 8 }} />
      <p className="text-[9px] font-bold uppercase tracking-widest text-gray-400 mb-1">Task</p>
      <p className="text-sm font-semibold text-black leading-snug mb-2">{String(data.label)}</p>
      <span className={cn("text-[9px] font-bold px-1.5 py-0.5 rounded-full", s.badge)}>
        {String(data.status).replace("_", " ")}
      </span>

      {assignees.length > 0 ? (
        <div className="mt-2 pt-1.5 border-t border-gray-100 flex flex-wrap gap-1">
          {assignees.map((u) => (
            <button
              key={u.id}
              onClick={(e) => { e.stopPropagation(); setActiveAssignee(activeAssignee?.id === u.id ? null : u) }}
              className={cn(
                "text-[9px] font-medium px-1.5 py-0.5 rounded-full transition-colors",
                activeAssignee?.id === u.id
                  ? "bg-[#643f83] text-white"
                  : "text-[#643f83] bg-[#f3eef9] hover:bg-[#e9dff5]"
              )}
            >
              {u.full_name.split(" ")[0]}
            </button>
          ))}
        </div>
      ) : (
        <p className="text-[9px] text-gray-300 mt-1.5 italic">Unassigned</p>
      )}

      {activeAssignee && (
        <div
          className="mt-2 pt-2 border-t border-gray-100"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-start justify-between gap-2 mb-1.5">
            <div className="flex items-center gap-1.5">
              <div className="w-6 h-6 rounded-full bg-[#643f83] text-white text-[9px] font-bold flex items-center justify-center flex-shrink-0">
                {activeAssignee.full_name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
              </div>
              <div>
                <p className="text-[11px] font-semibold text-black leading-none">{activeAssignee.full_name}</p>
                <span className={cn("text-[8px] font-bold px-1 py-0.5 rounded-full mt-0.5 inline-block", roleBadge[activeAssignee.role] ?? "bg-gray-100 text-gray-500")}>
                  {activeAssignee.role}
                </span>
              </div>
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); setActiveAssignee(null) }}
              className="text-gray-300 hover:text-gray-500 flex-shrink-0 mt-0.5"
            >
              <X size={10} />
            </button>
          </div>
          <p className="text-[9px] text-gray-400 truncate">{activeAssignee.email}</p>
          {activeAssignee.phone ? (
            <a
              href={`https://wa.me/${activeAssignee.phone.replace(/\D/g, "")}`}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="mt-1.5 flex items-center gap-1 text-[9px] font-semibold text-green-600 hover:text-green-700"
            >
              <MessageCircle size={10} /> WhatsApp
            </a>
          ) : (
            <p className="text-[9px] text-gray-300 mt-1 italic">No WhatsApp set</p>
          )}
        </div>
      )}

      {!!data.note && (
        <p className="text-[10px] text-gray-400 mt-1.5 italic line-clamp-2">"{String(data.note)}"</p>
      )}
    </div>
  )
}

// â”€â”€ nodeTypes maps â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export const epicMapNodeTypes = {
  epicNode:    EpicNode,
  moduleNode:  ModuleNode,
  taskNode:    TaskNode,
}

export const projectMapNodeTypes = {
  projectNode: ProjectNode,
  epicNode:    EpicNode,
  moduleNode:  ModuleNode,
  taskNode:    TaskNode,
}
