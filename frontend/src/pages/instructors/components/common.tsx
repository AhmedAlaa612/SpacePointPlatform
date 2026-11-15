import { useEffect, useState } from "react"
import { Clock } from "lucide-react"

export { PageHeader, StatCard, EmptyState, Spinner } from "@/components/ui/primitives"

const TIMED_APPLICATION_STATUSES = new Set([
  "in_progress",
  "phase_1_approved",
  "research_approved",
])

function formatRemainingDuration(diffMs: number): string {
  const totalMinutes = Math.max(1, Math.floor(diffMs / 60_000))
  const days = Math.floor(totalMinutes / (60 * 24))
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60)
  const minutes = totalMinutes % 60
  if (days > 0) return `${days}d ${hours}h left`
  if (hours > 0) return `${hours}h ${minutes}m left`
  return `${minutes}m left`
}

export function PhaseDeadlineBadge({
  phaseDeadline,
  status,
  extensionUsed,
  emptyFallback = false,
}: {
  phaseDeadline?: string | null
  status: string
  extensionUsed?: boolean
  emptyFallback?: boolean
}) {
  const [nowMs, setNowMs] = useState(() => Date.now())
  const isTimed = Boolean(phaseDeadline && TIMED_APPLICATION_STATUSES.has(status))

  useEffect(() => {
    if (!isTimed) return
    const id = window.setInterval(() => setNowMs(Date.now()), 60_000)
    return () => window.clearInterval(id)
  }, [isTimed])

  if (!phaseDeadline || !TIMED_APPLICATION_STATUSES.has(status)) {
    return emptyFallback ? <span className="text-muted-foreground">—</span> : null
  }
  const dueDate = new Date(phaseDeadline)
  const targetMs = dueDate.getTime()
  if (Number.isNaN(targetMs)) {
    return emptyFallback ? <span className="text-muted-foreground">—</span> : null
  }

  const diffMs = targetMs - nowMs
  const isExpired = diffMs <= 0
  const isUrgent = !isExpired && diffMs < 24 * 60 * 60 * 1000
  const timeLabel = isExpired ? "Expired" : formatRemainingDuration(diffMs)

  const pillCls = isExpired
    ? "bg-red-50 text-red-600 border-red-200 dark:bg-red-950/30 dark:text-red-400 dark:border-red-900/50"
    : isUrgent
      ? "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-400 dark:border-amber-900/50"
      : "bg-muted text-foreground border-border"

  const dueText = dueDate.toLocaleDateString(undefined, { month: "short", day: "numeric" })
  const dueTime = dueDate.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })

  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full border whitespace-nowrap ${pillCls}`}>
          <Clock size={11} />
          {timeLabel}
        </span>
        {extensionUsed && (
          <span
            title="Applicant used 24h deadline extension"
            className="inline-flex items-center text-[10px] font-semibold px-1.5 py-0.5 rounded-full border bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950/30 dark:text-purple-300 dark:border-purple-900/50 whitespace-nowrap"
          >
            +24h ext
          </span>
        )}
      </div>
      <span className="text-[11px] text-muted-foreground whitespace-nowrap">
        Due {dueText}, {dueTime}
      </span>
    </div>
  )
}

const STATUS_STYLES: Record<string, string> = {
  draft: "bg-muted text-muted-foreground border-border",
  in_progress: "bg-amber-50 text-amber-600 border-amber-200 dark:bg-amber-950/30 dark:text-amber-400 dark:border-amber-900/50",
  submitted: "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-900/50",
  under_review: "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-900/50",
  under_review_rejected: "bg-red-50 text-red-600 border-red-200 dark:bg-red-950/30 dark:text-red-400 dark:border-red-900/50",
  phase_1_approved: "bg-purple-50 text-purple-600 border-purple-200 dark:bg-purple-950/30 dark:text-purple-400 dark:border-purple-900/50",
  research_approved: "bg-indigo-50 text-indigo-600 border-indigo-200 dark:bg-indigo-950/30 dark:text-indigo-400 dark:border-indigo-900/50",
  approved: "bg-green-50 text-green-600 border-green-200 dark:bg-green-950/30 dark:text-green-400 dark:border-green-900/50",
  rejected: "bg-red-50 text-red-600 border-red-200 dark:bg-red-950/30 dark:text-red-400 dark:border-red-900/50",
}

const STATUS_LABELS: Record<string, string> = {
  under_review_rejected: "UNDER REVIEW — REJECTED ITEMS",
}

export function StatusPill({ status }: { status: string }) {
  const cls = STATUS_STYLES[status] ?? "bg-muted text-muted-foreground border-border"
  const label = STATUS_LABELS[status] ?? status.replace(/_/g, " ").toUpperCase()
  return (
    <span className={`inline-flex items-center text-[11px] font-semibold px-2.5 py-0.5 rounded-full border whitespace-nowrap ${cls}`}>
      {label}
    </span>
  )
}
