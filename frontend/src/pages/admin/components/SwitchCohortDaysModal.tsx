import { useMemo, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  ArrowLeftRight,
  ChevronDown,
  ChevronUp,
  GripVertical,
  Loader2,
  RotateCcw,
} from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useToast } from "@/components/ui/toast"
import {
  switchCohortDaysApi,
  type CohortChecklistsSummary,
  type SessionChecklistSummary,
  type SwitchDaysScope,
} from "@/api/sessions/day"
import type { Cohort } from "@/types/sessions"
import { cn, getErrorMessage } from "@/lib/utils"
import { OrderNumberInput } from "./OrderNumberInput"

function formatShortDate(iso: string) {
  const d = new Date(iso + "T00:00:00")
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })
}

export function SwitchCohortDaysModal({
  open,
  onClose,
  cohort,
  summary,
  summaryLoading = false,
  isOrgScope = false,
  onSuccess,
}: {
  open: boolean
  onClose: () => void
  cohort: Cohort
  summary?: CohortChecklistsSummary
  summaryLoading?: boolean
  isOrgScope?: boolean
  onSuccess: () => void
}) {
  const sessions = summary?.sessions ?? []
  const sessionKey = sessions.map((s) => s.session_id).join(",")

  return (
    <Dialog open={open} onOpenChange={(val) => !val && onClose()}>
      <DialogContent className="w-full max-w-[calc(100%-1rem)] sm:max-w-3xl max-h-[92vh] flex flex-col p-0 overflow-hidden bg-background text-foreground border border-border">
        {open && (
          <SwitchCohortDaysBody
            key={sessionKey}
            cohort={cohort}
            sessions={sessions}
            summaryLoading={summaryLoading}
            isOrgScope={isOrgScope}
            onClose={onClose}
            onSuccess={onSuccess}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function SwitchCohortDaysBody({
  cohort,
  sessions,
  summaryLoading,
  isOrgScope,
  onClose,
  onSuccess,
}: {
  cohort: Cohort
  sessions: SessionChecklistSummary[]
  summaryLoading: boolean
  isOrgScope: boolean
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  const qc = useQueryClient()

  const sessionById = useMemo(() => {
    const map = new Map<string, SessionChecklistSummary>()
    for (const s of sessions) map.set(s.session_id, s)
    return map
  }, [sessions])

  const [scope, setScope] = useState<SwitchDaysScope>("both")
  const [includeTitles, setIncludeTitles] = useState(true)
  const [planOrder, setPlanOrder] = useState<string[]>(() => sessions.map((s) => s.session_id))
  const [dragIndex, setDragIndex] = useState<number | null>(null)

  const handleScopeChange = (nextScope: SwitchDaysScope) => {
    setScope(nextScope)
    setIncludeTitles(nextScope === "both")
  }

  const isDirty = useMemo(
    () => planOrder.length === sessions.length && planOrder.some((id, idx) => id !== sessions[idx]?.session_id),
    [planOrder, sessions],
  )

  const moveIndex = (from: number, to: number) => {
    if (from === to || from < 0 || to < 0 || from >= planOrder.length || to >= planOrder.length) return
    const next = [...planOrder]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    setPlanOrder(next)
  }

  const hasProgressForScope = (s: SessionChecklistSummary) => {
    if (scope === "instructor") return s.has_instructor_progress
    if (scope === "internal") return s.has_internal_progress
    return s.has_instructor_progress || s.has_internal_progress
  }

  const hasApprovedForScope = (s: SessionChecklistSummary) =>
    scope !== "internal" && Boolean(s.has_approved_instructor_day)

  const movedWithProgress = planOrder.some((srcId, idx) => {
    const dst = sessions[idx]
    const src = sessionById.get(srcId)
    if (!dst || !src || srcId === dst.session_id) return false
    return hasProgressForScope(dst) || hasProgressForScope(src)
  })

  const movedHasApproved =
    scope !== "internal" &&
    planOrder.some((srcId, idx) => {
      const dst = sessions[idx]
      const src = sessionById.get(srcId)
      if (!dst || !src || srcId === dst.session_id) return false
      return Boolean(dst.has_approved_instructor_day || src.has_approved_instructor_day)
    })

  const switchMutation = useMutation({
    mutationFn: () =>
      switchCohortDaysApi(cohort.id, {
        session_plan_order: planOrder,
        scope,
        include_titles: includeTitles,
      }),
    onSuccess: async (res) => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["checklist-items"] }),
        qc.invalidateQueries({ queryKey: ["cohort-checklists-summary", cohort.id] }),
        qc.invalidateQueries({ queryKey: ["sessions-sessions", cohort.id] }),
        qc.invalidateQueries({ queryKey: ["wizard-sessions", cohort.id] }),
        qc.invalidateQueries({ queryKey: ["session-internal-checklist"] }),
      ])
      toast.success(
        `Switched ${res.sessions_switched} day${res.sessions_switched === 1 ? "" : "s"} (${res.items_moved} checklist item${res.items_moved === 1 ? "" : "s"} moved)`,
      )
      onSuccess()
      onClose()
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, "Could not switch days"))
    },
  })

  const internalLabel = isOrgScope ? "Operational" : "Internal team"

  return (
    <>
      <div className="p-4 sm:p-5 pr-12 border-b border-border bg-card">
        <DialogHeader>
          <div className="flex items-center gap-2 text-primary text-xs font-semibold uppercase tracking-wider">
            <ArrowLeftRight className="w-3.5 h-3.5" />
            <span>Switch Days</span>
          </div>
          <DialogTitle className="text-base sm:text-lg font-bold">
            Reorder Day Plans Across Fixed Session Dates
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Session dates, start times, attendance, kits, and assigned instructors stay fixed on
            their dates. Drag or move a day plan on the right to run it on another date.
          </DialogDescription>
        </DialogHeader>
      </div>

      <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4">
        {/* Scope Selector & Title Toggle */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border">
          <div className="flex items-center gap-1.5 flex-wrap">
            {(
              [
                { key: "both", label: "Both (Instructors + Internal)" },
                { key: "instructor", label: "Instructors only" },
                { key: "internal", label: `${internalLabel} only` },
              ] as const
            ).map((opt) => (
              <button
                key={opt.key}
                type="button"
                onClick={() => handleScopeChange(opt.key)}
                className={cn(
                  "h-8 px-3 rounded-full text-xs font-semibold transition-colors cursor-pointer",
                  scope === opt.key
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted",
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <label className="flex items-center gap-2 text-xs font-medium text-foreground cursor-pointer select-none shrink-0">
            <input
              type="checkbox"
              checked={includeTitles}
              onChange={(e) => setIncludeTitles(e.target.checked)}
              className="rounded border-border accent-primary"
            />
            <span>Also switch session titles</span>
          </label>
        </div>

        {movedHasApproved && (
          <div className="flex items-start gap-2 p-3 rounded-xl border border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300 text-xs">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>
              One or more switched days already have an approved instructor report and cannot be
              switched for instructors. Reopen those day reports first, or select &ldquo;{internalLabel}{" "}
              only&rdquo;.
            </span>
          </div>
        )}

        {!movedHasApproved && movedWithProgress && (
          <div className="flex items-start gap-2 p-3 rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300 text-xs">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>
              One or more switched days already have recorded checklist progress. Moving checklists
              between dates will clear in-progress ticks on those moved days for the switched
              team(s), while keeping check-in and attendance fixed.
            </span>
          </div>
        )}

        {summaryLoading && sessions.length === 0 ? (
          <div className="flex items-center justify-center gap-2 p-6 text-xs text-muted-foreground border border-border rounded-xl">
            <Loader2 className="w-4 h-4 animate-spin text-primary" /> Loading session checklists…
          </div>
        ) : sessions.length < 2 ? (
          <div className="p-6 text-center text-xs text-muted-foreground border border-dashed border-border rounded-xl">
            At least 2 sessions are needed to switch days.
          </div>
        ) : (
          <div className="space-y-2">
            <div className="grid grid-cols-1 sm:grid-cols-[190px_1fr] gap-2 px-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
              <span>Fixed Calendar Date</span>
              <span>Day Plan to Run</span>
            </div>

            {sessions.map((fixedSlot, slotIdx) => {
              const srcId = planOrder[slotIdx] ?? fixedSlot.session_id
              const plan = sessionById.get(srcId) ?? fixedSlot
              const isMoved = plan.session_id !== fixedSlot.session_id
              const slotHasApproved =
                hasApprovedForScope(plan) || (isMoved && hasApprovedForScope(fixedSlot))
              const slotHasProgress = hasProgressForScope(plan) || (isMoved && hasProgressForScope(fixedSlot))

              return (
                <div
                  key={fixedSlot.session_id}
                  className="grid grid-cols-1 sm:grid-cols-[190px_1fr] gap-2 items-stretch"
                >
                  {/* Fixed Calendar Slot */}
                  <div className="flex flex-col justify-center px-3 py-2 rounded-xl border border-border bg-muted/30">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                        Day {slotIdx + 1}
                      </span>
                      <span className="text-[11px] font-medium text-foreground">
                        {formatShortDate(fixedSlot.meeting_date)}
                      </span>
                    </div>
                    <span className="text-[10px] text-muted-foreground mt-0.5">
                      {fixedSlot.starts_at ? `Starts ${fixedSlot.starts_at.slice(0, 5)} · ` : ""}
                      Date fixed
                    </span>
                  </div>

                  {/* Reorderable Day Plan */}
                  <div
                    draggable
                    onDragStart={() => setDragIndex(slotIdx)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault()
                      if (dragIndex !== null) moveIndex(dragIndex, slotIdx)
                      setDragIndex(null)
                    }}
                    onDragEnd={() => setDragIndex(null)}
                    className={cn(
                      "flex items-center justify-between gap-2 p-2.5 rounded-xl border bg-card transition-all",
                      dragIndex === slotIdx
                        ? "opacity-40 border-primary ring-1 ring-primary/40"
                        : isMoved
                          ? "border-primary/50 bg-primary/5"
                          : "border-border hover:border-border/80",
                    )}
                  >
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <GripVertical
                        size={15}
                        className="text-muted-foreground cursor-grab active:cursor-grabbing shrink-0"
                      />
                      <OrderNumberInput
                        value={slotIdx + 1}
                        totalCount={planOrder.length}
                        onCommit={(pos) => {
                          const clamped = Math.min(Math.max(Math.round(pos), 1), planOrder.length)
                          moveIndex(slotIdx, clamped - 1)
                        }}
                      />

                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="text-xs sm:text-sm font-semibold text-foreground truncate">
                            {plan.title || `Day ${plan.day_number}`}
                          </span>
                          {isMoved && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-primary/15 text-primary">
                              From Day {plan.day_number}
                            </span>
                          )}
                          {slotHasApproved ? (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-red-500/15 text-red-600 dark:text-red-400">
                              <AlertTriangle className="w-2.5 h-2.5" /> Approved (locked)
                            </span>
                          ) : (
                            slotHasProgress && (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-500/15 text-amber-600 dark:text-amber-400">
                                <AlertTriangle className="w-2.5 h-2.5" /> Has progress
                              </span>
                            )
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-[11px] text-muted-foreground mt-0.5 flex-wrap">
                          <span>
                            {plan.effective_instructor_items_count} instructor
                            {plan.is_instructor_inherited ? " (inherited)" : ""}
                          </span>
                          <span>·</span>
                          <span>
                            {plan.effective_internal_items_count} {isOrgScope ? "ops" : "internal"}
                            {plan.is_internal_inherited ? " (inherited)" : ""}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-0.5 shrink-0">
                      <button
                        type="button"
                        onClick={() => moveIndex(slotIdx, slotIdx - 1)}
                        disabled={slotIdx === 0}
                        title="Move earlier"
                        className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-20 transition-colors cursor-pointer"
                      >
                        <ChevronUp size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => moveIndex(slotIdx, slotIdx + 1)}
                        disabled={slotIdx === planOrder.length - 1}
                        title="Move later"
                        className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-20 transition-colors cursor-pointer"
                      >
                        <ChevronDown size={14} />
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="p-3.5 sm:p-4 border-t border-border bg-muted/20 flex items-center justify-between gap-2">
        <div>
          {isDirty && (
            <button
              type="button"
              onClick={() => setPlanOrder(sessions.map((s) => s.session_id))}
              className="h-9 px-3 rounded-xl border border-border text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors inline-flex items-center gap-1.5 cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5" /> Reset order
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={switchMutation.isPending}
            className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => switchMutation.mutate()}
            disabled={!isDirty || movedHasApproved || switchMutation.isPending}
            className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 disabled:opacity-50 transition-opacity inline-flex items-center gap-1.5 cursor-pointer"
          >
            {switchMutation.isPending ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> Switching…
              </>
            ) : (
              <>
                <ArrowLeftRight className="w-3.5 h-3.5" /> Apply Switch
              </>
            )}
          </button>
        </div>
      </div>
    </>
  )
}
