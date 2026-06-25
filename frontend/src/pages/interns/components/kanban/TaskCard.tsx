import { useState } from "react"
import { useDraggable } from "@dnd-kit/core"
import { CSS } from "@dnd-kit/utilities"
import { Info, X } from "lucide-react"
import { cn } from "@/lib/utils"
import type { BoardCard } from "@/types/interns"

interface TaskCardProps {
  card: BoardCard
  onClick: () => void
}

function formatDue(dateStr: string | null) {
  if (!dateStr) return null
  const date = new Date(dateStr)
  const diff = Math.ceil((date.getTime() - Date.now()) / 86400000)
  if (diff < 0)   return { label: "Overdue",   urgent: true }
  if (diff === 0) return { label: "Today",     urgent: true }
  if (diff === 1) return { label: "Tomorrow",  urgent: false }
  return { label: `${diff}d`, urgent: false }
}

export default function TaskCard({ card, onClick }: TaskCardProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: card.id })
  const due       = formatDue(card.due_date)
  const latestSub = card.submissions?.[card.submissions.length - 1]
  const [scopeOpen, setScopeOpen] = useState(false)

  const isGeneral  = !card.module_title || card.module_title === "General"
  const scopeText  = card.module_description ?? (isGeneral ? (card.epic_description ?? null) : null)
  const scopeLabel = !isGeneral ? card.module_title! : (card.epic_title ?? "Epic scope")
  const hasScope   = !!scopeText

  return (
    <>
      <div
        ref={setNodeRef}
        style={{ transform: CSS.Translate.toString(transform), opacity: isDragging ? 0.4 : 1 }}
        {...attributes}
        {...listeners}
        onClick={onClick}
        className={cn(
          "bg-card border border-border rounded-xl p-3 cursor-pointer select-none transition-all hover:border-[#a880ff]/50 dark:hover:border-[#d6c7e1]/50 hover:shadow-sm",
          isDragging && "shadow-lg"
        )}
      >
        {/* Breadcrumb: project › epic › module */}
        {(card.project_title || card.epic_title || (card.module_title && !isGeneral)) && (
          <p className="text-[10px] mb-1.5 flex items-center gap-1 flex-wrap">
            {card.project_title && <span className="text-muted-foreground">{card.project_title}</span>}
            {card.project_title && card.epic_title && <span className="text-muted-foreground/50">›</span>}
            {card.epic_title && <span className="font-semibold text-[#643f83] dark:text-[#d6c7e1]">{card.epic_title}</span>}
            {!isGeneral && (
              <>
                <span className="text-muted-foreground/50">›</span>
                <span className="text-muted-foreground">{card.module_title}</span>
              </>
            )}
            {hasScope && (
              <button
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => { e.stopPropagation(); setScopeOpen(true) }}
                className="inline-flex items-center gap-0.5 text-[#643f83] dark:text-[#d6c7e1] hover:text-[#4a2d63] dark:hover:text-[#e4daf0] transition-colors"
                title="View module scope"
              >
                <Info size={10} />
              </button>
            )}
          </p>
        )}

        {/* No breadcrumb but scope exists (General module with epic desc) */}
        {!card.project_title && !card.epic_title && isGeneral && hasScope && (
          <button
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => { e.stopPropagation(); setScopeOpen(true) }}
            className="flex items-center gap-1 text-[10px] text-[#643f83] dark:text-[#d6c7e1] hover:text-[#4a2d63] dark:hover:text-[#e4daf0] mb-1.5 transition-colors"
          >
            <Info size={10} /> Scope
          </button>
        )}

        {/* Title */}
        <p className="text-sm font-semibold text-foreground leading-snug mb-1">{card.title}</p>

        {/* Footer */}
        <div className="flex items-center justify-between gap-2 mt-2">
          {due ? (
            <span className={cn(
              "text-[11px] font-medium px-2 py-0.5 rounded-full",
              due.urgent ? "bg-red-50 text-red-500 dark:bg-red-950/30 dark:text-red-400" : "bg-muted text-muted-foreground"
            )}>
              {due.label}
            </span>
          ) : <span />}

          <div className="flex items-center gap-2">
            {latestSub && (
              <span className={cn(
                "text-[10px] font-medium px-2 py-0.5 rounded-full",
                latestSub.status === "reviewed"
                  ? "bg-foreground text-background"
                  : "bg-[#d6c7e1] text-[#643f83] dark:bg-[#643f83] dark:text-[#d6c7e1]"
              )}>
                {latestSub.status === "reviewed" ? "Reviewed" : "Submitted"}
              </span>
            )}

            {card.assignees.length > 0 && (
              <div className="flex -space-x-1.5">
                {card.assignees.slice(0, 3).map((u) => (
                  <div key={u.id} title={u.full_name}
                    className="w-6 h-6 rounded-full bg-[#d6c7e1] dark:bg-[#d6c7e1]/20 text-[#643f83] dark:text-[#d6c7e1] text-[9px] font-bold flex items-center justify-center border-2 border-card flex-shrink-0">
                    {u.full_name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase()}
                  </div>
                ))}
                {card.assignees.length > 3 && (
                  <div className="w-6 h-6 rounded-full bg-muted text-muted-foreground text-[9px] font-bold flex items-center justify-center border-2 border-card flex-shrink-0">
                    +{card.assignees.length - 3}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Scope popup */}
      {scopeOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
          onPointerDown={() => setScopeOpen(false)}
        >
          <div
            className="w-full max-w-sm bg-card border border-border rounded-2xl shadow-2xl p-5 flex flex-col gap-3"
            onPointerDown={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between">
              <div>
                <span className="text-[9px] font-bold uppercase tracking-widest text-[#643f83] dark:text-[#d6c7e1]">
                  {isGeneral ? "Epic scope" : "Module scope"}
                </span>
                <p className="text-sm font-semibold text-foreground mt-0.5">{scopeLabel}</p>
              </div>
              <button onClick={() => setScopeOpen(false)}
                className="p-1 rounded-lg text-muted-foreground hover:text-foreground transition-colors">
                <X size={14} />
              </button>
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">{scopeText}</p>
          </div>
        </div>
      )}
    </>
  )
}
