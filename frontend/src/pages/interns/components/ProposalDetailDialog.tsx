import { createPortal } from "react-dom"
import { ArrowLeft, X, CalendarDays, User } from "lucide-react"
import { cn } from "@/lib/utils"
import type { Proposal } from "@/types/interns"

interface Props {
  proposal: Proposal
  /** If provided, Accept + Reject buttons are shown */
  onAccept?: () => void
  onReject?: () => void
  acceptLabel?: string
  isPending?: boolean
  onClose: () => void
}

export default function ProposalDetailDialog({ proposal: p, onAccept, onReject, acceptLabel = "Accept", isPending, onClose }: Props) {
  return createPortal(
    <div
      className="fixed inset-0 bg-black/40 z-[9999] flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm bg-card border border-border text-foreground rounded-2xl shadow-2xl flex flex-col max-h-[80vh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* header */}
        <div className="flex items-center gap-2 px-5 pt-5 pb-3 border-b border-border flex-shrink-0">
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex-shrink-0">
            <ArrowLeft size={15} />
          </button>
          <div className="flex-1 min-w-0">
            <p className="text-[9px] font-bold uppercase tracking-widest text-[#643f83] dark:text-[#d6c7e1]">Proposal</p>
            <p className="text-sm font-semibold text-foreground truncate">{p.title}</p>
          </div>
          <span className={cn(
            "text-[10px] font-semibold px-2.5 py-1 rounded-full flex-shrink-0",
            p.status === "pending"  ? "bg-[#d6c7e1] text-[#643f83] dark:bg-[#643f83]/40 dark:text-[#d6c7e1]" :
            p.status === "accepted" ? "bg-primary text-primary-foreground" :
            "bg-muted text-muted-foreground"
          )}>
            {p.status}
          </span>
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex-shrink-0">
            <X size={15} />
          </button>
        </div>

        {/* body */}
        <div className="overflow-y-auto flex-1 px-5 py-4 flex flex-col gap-4">

          {/* description */}
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">Description</p>
            {p.description ? (
              <p className="text-sm text-muted-foreground leading-relaxed">{p.description}</p>
            ) : (
              <p className="text-sm text-muted-foreground/50 italic">No description provided</p>
            )}
          </div>

          {/* meta */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <User size={12} className="text-muted-foreground" />
              Proposed by <span className="font-medium text-foreground">{p.proposer_name ?? "Unknown"}</span>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <CalendarDays size={12} className="text-muted-foreground" />
              {new Date(p.created_at).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" })}
            </div>
            {p.reviewed_at && (
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <CalendarDays size={12} className="text-muted-foreground" />
                Reviewed {new Date(p.reviewed_at).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" })}
              </div>
            )}
          </div>

          {/* actions */}
          {p.status === "pending" && onAccept && onReject && (
            <div className="flex gap-2 pt-1">
              <button
                onClick={onAccept}
                disabled={isPending}
                className="flex-1 h-10 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:bg-primary/95 transition-colors disabled:opacity-50"
              >
                {acceptLabel}
              </button>
              <button
                onClick={onReject}
                disabled={isPending}
                className="flex-1 h-10 border border-border text-muted-foreground bg-background rounded-xl text-sm font-medium hover:bg-red-500/10 hover:text-red-500 hover:border-red-500/20 transition-colors disabled:opacity-50"
              >
                Reject
              </button>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  )
}
