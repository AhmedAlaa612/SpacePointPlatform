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
        className="w-full max-w-sm bg-white rounded-2xl shadow-2xl flex flex-col max-h-[80vh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* header */}
        <div className="flex items-center gap-2 px-5 pt-5 pb-3 border-b border-gray-100 flex-shrink-0">
          <button onClick={onClose} className="p-1.5 rounded-lg text-gray-400 hover:text-black transition-colors flex-shrink-0">
            <ArrowLeft size={15} />
          </button>
          <div className="flex-1 min-w-0">
            <p className="text-[9px] font-bold uppercase tracking-widest text-[#643f83]">Proposal</p>
            <p className="text-sm font-semibold text-black truncate">{p.title}</p>
          </div>
          <span className={cn(
            "text-[10px] font-semibold px-2.5 py-1 rounded-full flex-shrink-0",
            p.status === "pending"  ? "bg-[#d6c7e1] text-[#643f83]" :
            p.status === "accepted" ? "bg-black text-white" :
            "bg-gray-100 text-gray-400"
          )}>
            {p.status}
          </span>
          <button onClick={onClose} className="p-1.5 rounded-lg text-gray-400 hover:text-black transition-colors flex-shrink-0">
            <X size={15} />
          </button>
        </div>

        {/* body */}
        <div className="overflow-y-auto flex-1 px-5 py-4 flex flex-col gap-4">

          {/* description */}
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-1.5">Description</p>
            {p.description ? (
              <p className="text-sm text-gray-700 leading-relaxed">{p.description}</p>
            ) : (
              <p className="text-sm text-gray-300 italic">No description provided</p>
            )}
          </div>

          {/* meta */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-1.5 text-xs text-gray-500">
              <User size={12} className="text-gray-400" />
              Proposed by <span className="font-medium text-black">{p.proposer_name ?? "Unknown"}</span>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-gray-500">
              <CalendarDays size={12} className="text-gray-400" />
              {new Date(p.created_at).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" })}
            </div>
            {p.reviewed_at && (
              <div className="flex items-center gap-1.5 text-xs text-gray-500">
                <CalendarDays size={12} className="text-gray-400" />
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
                className="flex-1 h-10 bg-black text-white rounded-xl text-sm font-medium hover:bg-gray-900 transition-colors disabled:opacity-50"
              >
                {acceptLabel}
              </button>
              <button
                onClick={onReject}
                disabled={isPending}
                className="flex-1 h-10 border border-gray-200 text-gray-600 rounded-xl text-sm font-medium hover:bg-red-50 hover:text-red-500 hover:border-red-200 transition-colors disabled:opacity-50"
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
