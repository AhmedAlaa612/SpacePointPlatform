import { useDroppable } from "@dnd-kit/core"
import { cn } from "@/lib/utils"
import type { BoardCard, WorkStatus } from "@/types/interns"
import TaskCard from "./TaskCard"

interface ColumnProps {
  title: string
  status: WorkStatus
  cards: BoardCard[]
  onCardClick: (card: BoardCard) => void
}

const styles: Record<WorkStatus, { dot: string; badge: string }> = {
  todo:        { dot: "bg-gray-300",  badge: "text-gray-500 bg-gray-100" },
  in_progress: { dot: "bg-[#a880ff]", badge: "text-[#643f83] bg-[#d6c7e1]" },
  done:        { dot: "bg-black",     badge: "text-white bg-black" },
}

export default function Column({ title, status, cards, onCardClick }: ColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id: status })
  const s = styles[status]

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "flex flex-col gap-3 rounded-2xl border p-4 min-h-[500px] transition-colors",
        isOver ? "border-[#a880ff] bg-[#a880ff]/5" : "border-gray-100 bg-gray-50/50"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className={cn("w-2 h-2 rounded-full", s.dot)} />
          <span className="text-xs font-semibold text-black uppercase tracking-widest">{title}</span>
        </div>
        <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full", s.badge)}>
          {cards.length}
        </span>
      </div>

      {/* Cards */}
      <div className="flex flex-col gap-2 flex-1">
        {cards.map((card) => (
          <TaskCard key={card.id} card={card} onClick={() => onCardClick(card)} />
        ))}
      </div>

      {cards.length === 0 && (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-xs text-gray-300">Drop here</p>
        </div>
      )}
    </div>
  )
}
