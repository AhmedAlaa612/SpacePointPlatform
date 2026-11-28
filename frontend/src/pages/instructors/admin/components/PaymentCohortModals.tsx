import { useEffect, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Ban,
  Calendar,
  Check,
  CheckCircle2,
  ExternalLink,
  Layers,
  MapPin,
  RotateCcw,
} from "lucide-react"
import {
  ignorePaymentCohortApi,
  restorePaymentCohortApi,
  settlePaymentCohortApi,
  type CohortInstructorPayment,
  type CompletedCohortPayment,
  type SettleCohortPaymentResponse,
} from "@/api/instructors/payments_admin"
import type { PaymentBatch } from "@/api/instructors/payments_admin"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useToast } from "@/components/ui/toast"
import { cn, getErrorMessage } from "@/lib/utils"

export type PaymentBadgeVariant =
  | "pending"
  | "settled"
  | "added"
  | "ignored"
  | "partial"
  | "draft"
  | "published"
  | "signed"
  | "paid"
  | "append"
  | "new_draft"
  | "missing_rate"
  | "pdf_ready"

const BADGE_CLASSES: Record<PaymentBadgeVariant, string> = {
  pending: "bg-muted/70 text-foreground border border-border",
  draft: "bg-muted/70 text-foreground border border-border",
  settled:
    "bg-emerald-600/12 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300 border border-emerald-600/30",
  added:
    "bg-emerald-600/12 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300 border border-emerald-600/30",
  paid:
    "bg-emerald-600/15 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300 border border-emerald-600/35",
  pdf_ready:
    "bg-emerald-600/12 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300 border border-emerald-600/30",
  published:
    "bg-[#653F84]/12 text-[#653F84] dark:bg-purple-500/20 dark:text-purple-200 border border-[#653F84]/30",
  append:
    "bg-[#653F84]/12 text-[#653F84] dark:bg-purple-500/20 dark:text-purple-200 border border-[#653F84]/30",
  new_draft: "bg-background text-muted-foreground border border-border",
  signed: "bg-[#653F84] text-white border border-[#653F84]",
  partial:
    "bg-[#653F84]/12 text-[#653F84] dark:bg-purple-500/20 dark:text-purple-200 border border-[#653F84]/30",
  ignored:
    "bg-rose-600/12 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300 border border-rose-600/30",
  missing_rate:
    "bg-rose-600/12 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300 border border-rose-600/30",
}

export function PaymentStatusBadge({
  variant,
  label,
  className,
}: {
  variant: PaymentBadgeVariant
  label: string
  className?: string
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-[10px] px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide whitespace-nowrap",
        BADGE_CLASSES[variant],
        className,
      )}
    >
      {label}
    </span>
  )
}

interface EditableInstructorRow {
  source: CohortInstructorPayment
  included: boolean
  role: string
  sessionsCount: number
  hours: number
  rateAed: number
  totalAed: number
}

function buildEditableRows(cohort: CompletedCohortPayment): EditableInstructorRow[] {
  return cohort.instructors.map((inst) => ({
    source: inst,
    included: inst.outcome === "pending",
    role: inst.role_name,
    sessionsCount: inst.sessions_count,
    hours: inst.hours,
    rateAed: inst.rate_aed ?? 0,
    totalAed: inst.total_aed,
  }))
}

export function CohortReviewModal({
  cohort,
  batches,
  deliveryRoles,
  onClose,
  onOpenProfile,
  onSettled,
}: {
  cohort: CompletedCohortPayment | null
  batches: PaymentBatch[]
  deliveryRoles: string[]
  onClose: () => void
  onOpenProfile: (userId: string) => void
  onSettled: (res: SettleCohortPaymentResponse) => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [rows, setRows] = useState<EditableInstructorRow[]>([])
  const [batchId, setBatchId] = useState<string>("")

  useEffect(() => {
    if (!cohort) return
    setRows(buildEditableRows(cohort))
    setBatchId(batches[0]?.id ?? "")
  }, [cohort, batches])

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ["admin-payment-cohorts"] })
    qc.invalidateQueries({ queryKey: ["admin-payment-letters"] })
    qc.invalidateQueries({ queryKey: ["admin-payment-analytics"] })
    qc.invalidateQueries({ queryKey: ["admin-payment-batches"] })
    qc.invalidateQueries({ queryKey: ["admin-payment-todo"] })
    qc.invalidateQueries({ queryKey: ["admin-overview"] })
    qc.invalidateQueries({ queryKey: ["instructor-payment-history"] })
  }

  const settleMutation = useMutation({
    mutationFn: () => {
      if (!cohort) throw new Error("Missing cohort")
      const pendingItems = rows.filter((r) => r.source.outcome === "pending")
      return settlePaymentCohortApi({
        cohortId: cohort.cohort_id,
        batchId: batchId || null,
        items: pendingItems.map((r) => ({
          instructor_user_id: r.source.instructor_user_id,
          action: r.included ? "add" : "ignore",
          role: r.role,
          sessions_count: r.sessionsCount,
          hours: r.hours,
          rate_aed: r.rateAed,
          compensation_aed: r.included ? r.totalAed : 0,
        })),
      })
    },
    onSuccess: (res) => {
      invalidateAll()
      const parts: string[] = []
      if (res.created_drafts > 0) parts.push(`${res.created_drafts} new draft`)
      if (res.appended_drafts > 0) parts.push(`${res.appended_drafts} appended`)
      if (res.ignored_count > 0) parts.push(`${res.ignored_count} ignored`)
      toast.success(`${res.cohort.name}: ${parts.join(", ") || "settled"}`)
      onSettled(res)
      onClose()
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to settle cohort")),
  })

  const ignoreRowMutation = useMutation({
    mutationFn: (instructorUserId?: string) =>
      ignorePaymentCohortApi({
        cohortId: cohort!.cohort_id,
        instructorUserId,
      }),
    onSuccess: (updated, instructorUserId) => {
      invalidateAll()
      if (!instructorUserId || updated.status === "settled") {
        toast.info(`${updated.name} moved to Settled`)
        onClose()
      } else {
        setRows(buildEditableRows(updated))
        toast.info("Instructor ignored for this cohort")
      }
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to ignore")),
  })

  if (!cohort) return null

  const updateRow = (
    userId: string,
    patch: Partial<Omit<EditableInstructorRow, "source">>,
    recomputeTotal = false,
  ) => {
    setRows((prev) =>
      prev.map((r) => {
        if (r.source.instructor_user_id !== userId) return r
        const next = { ...r, ...patch }
        if (recomputeTotal) {
          next.totalAed = Math.round(Math.max(0, next.sessionsCount) * Math.max(0, next.rateAed) * 100) / 100
        }
        return next
      }),
    )
  }

  const pendingRows = rows.filter((r) => r.source.outcome === "pending")
  const selectedRows = pendingRows.filter((r) => r.included)
  const selectedTotal = selectedRows.reduce((s, r) => s + (Number(r.totalAed) || 0), 0)
  const missingRateCount = selectedRows.filter((r) => r.rateAed <= 0 && r.totalAed <= 0).length
  const busy = settleMutation.isPending || ignoreRowMutation.isPending

  return (
    <Dialog open={!!cohort} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-[95vw] sm:max-w-5xl max-h-[90vh] overflow-y-auto rounded-[10px] p-5 sm:p-6">
        <DialogHeader>
          <div className="flex items-center justify-between gap-3 flex-wrap pr-8">
            <div>
              <DialogTitle className="text-lg font-extrabold text-foreground">
                {cohort.name}
              </DialogTitle>
              <div className="flex items-center gap-4 flex-wrap pt-1.5 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1.5">
                  <Layers size={13} /> {cohort.program_name}
                </span>
                {cohort.date_range && (
                  <span className="inline-flex items-center gap-1.5">
                    <Calendar size={13} /> {cohort.date_range}
                  </span>
                )}
                {cohort.location && (
                  <span className="inline-flex items-center gap-1.5">
                    <MapPin size={13} /> {cohort.location}
                  </span>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                New Draft Batch
              </span>
              <select
                value={batchId}
                onChange={(e) => setBatchId(e.target.value)}
                className="h-9 px-3 rounded-[10px] text-xs font-semibold cursor-pointer"
              >
                <option value="" className="bg-popover text-popover-foreground">
                  No batch
                </option>
                {batches.map((b) => (
                  <option key={b.id} value={b.id} className="bg-popover text-popover-foreground">
                    {b.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </DialogHeader>

        {/* Desktop Review Table */}
        <div className="hidden md:block overflow-x-auto pt-2">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-border text-left text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                <th className="py-2.5 pr-3 w-12">Pay</th>
                <th className="py-2.5 pr-3">Instructor</th>
                <th className="py-2.5 pr-3 w-44">Role</th>
                <th className="py-2.5 pr-3 w-20 text-right">Sessions</th>
                <th className="py-2.5 pr-3 w-20 text-right">Hours</th>
                <th className="py-2.5 pr-3 w-28 text-right">Rate AED</th>
                <th className="py-2.5 pr-3 w-28 text-right">Total AED</th>
                <th className="py-2.5 w-24 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/70">
              {rows.map((r) => {
                const inst = r.source
                const isPending = inst.outcome === "pending"
                const needsRate = isPending && r.included && r.rateAed <= 0 && r.totalAed <= 0

                return (
                  <tr
                    key={inst.instructor_user_id}
                    className={cn(!isPending && "opacity-65", isPending && !r.included && "opacity-55")}
                  >
                    <td className="py-2.5 pr-3 align-middle">
                      {isPending ? (
                        <input
                          type="checkbox"
                          checked={r.included}
                          onChange={(e) =>
                            updateRow(inst.instructor_user_id, { included: e.target.checked })
                          }
                          className="h-4 w-4 rounded-[10px] cursor-pointer"
                        />
                      ) : (
                        <PaymentStatusBadge
                          variant={inst.outcome === "added" ? "added" : "ignored"}
                          label={inst.outcome === "added" ? "Added" : "Ignored"}
                        />
                      )}
                    </td>
                    <td className="py-2.5 pr-3 align-middle">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <button
                            type="button"
                            onClick={() => onOpenProfile(inst.instructor_user_id)}
                            className="font-bold text-foreground hover:text-primary text-left cursor-pointer"
                          >
                            {inst.full_name}
                          </button>
                          {isPending && r.included && (
                            <PaymentStatusBadge
                              variant={inst.has_active_draft ? "append" : "new_draft"}
                              label={inst.has_active_draft ? "Appends to Draft" : "New Draft"}
                            />
                          )}
                          {needsRate && <PaymentStatusBadge variant="missing_rate" label="Rate 0" />}
                        </div>
                        <div className="flex items-center gap-2 flex-wrap text-xs text-muted-foreground">
                          <span>{inst.attendance_tag}</span>
                        </div>
                      </div>
                    </td>
                    <td className="py-2.5 pr-3 align-middle">
                      <select
                        value={r.role}
                        disabled={!isPending}
                        onChange={(e) => updateRow(inst.instructor_user_id, { role: e.target.value })}
                        className="w-full h-9 px-2.5 rounded-[10px] text-xs font-medium"
                      >
                        {[r.role, ...deliveryRoles.filter((d) => d !== r.role)].map((role) => (
                          <option key={role} value={role} className="bg-popover text-popover-foreground">
                            {role}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="py-2.5 pr-3 align-middle">
                      <input
                        type="number"
                        min={0}
                        step={1}
                        disabled={!isPending}
                        value={r.sessionsCount}
                        onChange={(e) =>
                          updateRow(
                            inst.instructor_user_id,
                            { sessionsCount: Math.max(0, Number(e.target.value) || 0) },
                            true,
                          )
                        }
                        className="w-full h-9 px-2 rounded-[10px] text-right text-sm tabular-nums"
                      />
                    </td>
                    <td className="py-2.5 pr-3 align-middle">
                      <input
                        type="number"
                        min={0}
                        step={0.5}
                        disabled={!isPending}
                        value={r.hours}
                        onChange={(e) =>
                          updateRow(inst.instructor_user_id, {
                            hours: Math.max(0, Number(e.target.value) || 0),
                          })
                        }
                        className="w-full h-9 px-2 rounded-[10px] text-right text-sm tabular-nums"
                      />
                    </td>
                    <td className="py-2.5 pr-3 align-middle">
                      <input
                        type="number"
                        min={0}
                        step={50}
                        disabled={!isPending}
                        value={r.rateAed}
                        onChange={(e) =>
                          updateRow(
                            inst.instructor_user_id,
                            { rateAed: Math.max(0, Number(e.target.value) || 0) },
                            true,
                          )
                        }
                        className={cn(
                          "w-full h-9 px-2 rounded-[10px] text-right text-sm tabular-nums",
                          needsRate && "!border-rose-600",
                        )}
                      />
                    </td>
                    <td className="py-2.5 pr-3 align-middle">
                      <input
                        type="number"
                        min={0}
                        step={50}
                        disabled={!isPending}
                        value={r.totalAed}
                        onChange={(e) =>
                          updateRow(inst.instructor_user_id, {
                            totalAed: Math.max(0, Number(e.target.value) || 0),
                          })
                        }
                        className="w-full h-9 px-2 rounded-[10px] text-right text-sm font-bold tabular-nums"
                      />
                    </td>
                    <td className="py-2.5 align-middle text-right">
                      {isPending && (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={busy}
                          onClick={() => ignoreRowMutation.mutate(inst.instructor_user_id)}
                          className="h-8 px-2.5 rounded-[10px] border-rose-600/35 text-rose-600 text-xs font-semibold"
                        >
                          <Ban size={13} className="mr-1" /> Ignore
                        </Button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Mobile Review Stack */}
        <div className="grid grid-cols-1 gap-3 md:hidden pt-2">
          {rows.map((r) => {
            const inst = r.source
            const isPending = inst.outcome === "pending"
            const needsRate = isPending && r.included && r.rateAed <= 0 && r.totalAed <= 0

            return (
              <div
                key={inst.instructor_user_id}
                className="rounded-[10px] border border-border bg-background p-3 space-y-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start gap-2.5">
                    {isPending && (
                      <input
                        type="checkbox"
                        checked={r.included}
                        onChange={(e) =>
                          updateRow(inst.instructor_user_id, { included: e.target.checked })
                        }
                        className="mt-1 h-4 w-4 rounded-[10px]"
                      />
                    )}
                    <div>
                      <button
                        type="button"
                        onClick={() => onOpenProfile(inst.instructor_user_id)}
                        className="font-bold text-sm text-foreground hover:text-primary text-left"
                      >
                        {inst.full_name}
                      </button>
                      <p className="text-xs text-muted-foreground">{inst.attendance_tag}</p>
                    </div>
                  </div>
                  {isPending ? (
                    <PaymentStatusBadge
                      variant={inst.has_active_draft ? "append" : "new_draft"}
                      label={inst.has_active_draft ? "Appends" : "New Draft"}
                    />
                  ) : (
                    <PaymentStatusBadge
                      variant={inst.outcome === "added" ? "added" : "ignored"}
                      label={inst.outcome === "added" ? "Added" : "Ignored"}
                    />
                  )}
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="col-span-2">
                    <label className="text-[11px] font-bold uppercase text-muted-foreground block mb-1">
                      Role
                    </label>
                    <select
                      value={r.role}
                      disabled={!isPending}
                      onChange={(e) => updateRow(inst.instructor_user_id, { role: e.target.value })}
                      className="w-full h-9 px-2.5 rounded-[10px] text-xs font-medium"
                    >
                      {[r.role, ...deliveryRoles.filter((d) => d !== r.role)].map((role) => (
                        <option key={role} value={role} className="bg-popover text-popover-foreground">
                          {role}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-[11px] font-bold uppercase text-muted-foreground block mb-1">
                      Sessions
                    </label>
                    <input
                      type="number"
                      min={0}
                      disabled={!isPending}
                      value={r.sessionsCount}
                      onChange={(e) =>
                        updateRow(
                          inst.instructor_user_id,
                          { sessionsCount: Math.max(0, Number(e.target.value) || 0) },
                          true,
                        )
                      }
                      className="w-full h-9 px-2 rounded-[10px] text-right text-sm tabular-nums"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-bold uppercase text-muted-foreground block mb-1">
                      Hours
                    </label>
                    <input
                      type="number"
                      min={0}
                      step={0.5}
                      disabled={!isPending}
                      value={r.hours}
                      onChange={(e) =>
                        updateRow(inst.instructor_user_id, {
                          hours: Math.max(0, Number(e.target.value) || 0),
                        })
                      }
                      className="w-full h-9 px-2 rounded-[10px] text-right text-sm tabular-nums"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-bold uppercase text-muted-foreground block mb-1">
                      Rate AED
                    </label>
                    <input
                      type="number"
                      min={0}
                      step={50}
                      disabled={!isPending}
                      value={r.rateAed}
                      onChange={(e) =>
                        updateRow(
                          inst.instructor_user_id,
                          { rateAed: Math.max(0, Number(e.target.value) || 0) },
                          true,
                        )
                      }
                      className={cn(
                        "w-full h-9 px-2 rounded-[10px] text-right text-sm tabular-nums",
                        needsRate && "!border-rose-600",
                      )}
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-bold uppercase text-muted-foreground block mb-1">
                      Total AED
                    </label>
                    <input
                      type="number"
                      min={0}
                      step={50}
                      disabled={!isPending}
                      value={r.totalAed}
                      onChange={(e) =>
                        updateRow(inst.instructor_user_id, {
                          totalAed: Math.max(0, Number(e.target.value) || 0),
                        })
                      }
                      className="w-full h-9 px-2 rounded-[10px] text-right text-sm font-bold tabular-nums"
                    />
                  </div>
                </div>

                {isPending && (
                  <div className="flex justify-end">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => ignoreRowMutation.mutate(inst.instructor_user_id)}
                      className="h-8 px-2.5 rounded-[10px] border-rose-600/35 text-rose-600 text-xs font-semibold"
                    >
                      <Ban size={13} className="mr-1" /> Ignore
                    </Button>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-4 border-t border-border">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs font-semibold text-muted-foreground">
              {selectedRows.length} selected
            </span>
            <span className="text-sm font-extrabold text-foreground tabular-nums">
              AED {selectedTotal.toLocaleString()}
            </span>
            {missingRateCount > 0 && (
              <PaymentStatusBadge variant="missing_rate" label={`${missingRateCount} rate at 0`} />
            )}
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <Button
              variant="outline"
              size="lg"
              disabled={busy}
              onClick={() => ignoreRowMutation.mutate(undefined)}
              className="h-9 px-3.5 rounded-[10px] border-rose-600/40 text-rose-600 text-xs font-bold"
            >
              <Ban size={14} className="mr-1.5" /> Ignore Cohort
            </Button>
            <Button
              size="lg"
              disabled={busy || pendingRows.length === 0}
              onClick={() => settleMutation.mutate()}
              className="h-9 px-4 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold"
            >
              <Check size={14} className="mr-1.5" />
              {settleMutation.isPending ? "Adding..." : "Add to Letters"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function SettledCohortModal({
  cohort,
  onClose,
  onOpenProfile,
  onOpenLetter,
  onRestored,
}: {
  cohort: CompletedCohortPayment | null
  onClose: () => void
  onOpenProfile: (userId: string) => void
  onOpenLetter: (letterId: string) => void
  onRestored?: (updated: CompletedCohortPayment) => void
}) {
  const qc = useQueryClient()
  const toast = useToast()

  const restoreMutation = useMutation({
    mutationFn: (instructorUserId?: string) =>
      restorePaymentCohortApi({
        cohortId: cohort!.cohort_id,
        instructorUserId,
      }),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: ["admin-payment-cohorts"] })
      qc.invalidateQueries({ queryKey: ["admin-payment-todo"] })
      qc.invalidateQueries({ queryKey: ["admin-overview"] })
      toast.success(`Restored ${updated.name} to Pending Review`)
      onRestored?.(updated)
      onClose()
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to restore cohort")),
  })

  if (!cohort) return null

  const ignoredCount = cohort.instructors.filter((i) => i.outcome === "ignored").length
  const totalAddedAed = cohort.instructors
    .filter((i) => i.outcome === "added")
    .reduce((sum, i) => sum + i.total_aed, 0)

  return (
    <Dialog open={!!cohort} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-[95vw] sm:max-w-4xl max-h-[90vh] overflow-y-auto rounded-[10px] p-5 sm:p-6">
        <DialogHeader>
          <div className="flex items-center gap-2.5 flex-wrap pr-8">
            <DialogTitle className="text-lg font-extrabold text-foreground">
              {cohort.name}
            </DialogTitle>
            <PaymentStatusBadge
              variant={cohort.settled_outcome ?? "settled"}
              label={
                cohort.settled_outcome === "ignored"
                  ? "Ignored"
                  : cohort.settled_outcome === "partial"
                    ? "Partially Added"
                    : "Added to Letters"
              }
            />
          </div>
          <div className="flex items-center gap-4 flex-wrap pt-2 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <Layers size={13} /> {cohort.program_name}
            </span>
            {cohort.date_range && (
              <span className="inline-flex items-center gap-1.5">
                <Calendar size={13} /> {cohort.date_range}
              </span>
            )}
            {cohort.location && (
              <span className="inline-flex items-center gap-1.5">
                <MapPin size={13} /> {cohort.location}
              </span>
            )}
            {cohort.settled_at && (
              <span className="inline-flex items-center gap-1.5">
                <CheckCircle2 size={13} /> Settled {new Date(cohort.settled_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </DialogHeader>

        <div className="overflow-x-auto pt-2">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-border text-left text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                <th className="py-2.5 pr-3">Instructor</th>
                <th className="py-2.5 pr-3">Role</th>
                <th className="py-2.5 pr-3 text-right">Sessions</th>
                <th className="py-2.5 pr-3 text-right">Hours</th>
                <th className="py-2.5 pr-3 text-right">Rate AED</th>
                <th className="py-2.5 pr-3 text-right">Total AED</th>
                <th className="py-2.5 pr-3">Outcome</th>
                <th className="py-2.5 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/70">
              {cohort.instructors.map((inst) => (
                <tr key={inst.instructor_user_id}>
                  <td className="py-2.5 pr-3">
                    <button
                      type="button"
                      onClick={() => {
                        onClose()
                        onOpenProfile(inst.instructor_user_id)
                      }}
                      className="font-bold text-foreground hover:text-primary text-left cursor-pointer"
                    >
                      {inst.full_name}
                    </button>
                    <p className="text-xs text-muted-foreground">{inst.email}</p>
                  </td>
                  <td className="py-2.5 pr-3 text-foreground">{inst.role_name}</td>
                  <td className="py-2.5 pr-3 text-right tabular-nums">{inst.sessions_count}</td>
                  <td className="py-2.5 pr-3 text-right tabular-nums">{inst.hours}</td>
                  <td className="py-2.5 pr-3 text-right tabular-nums">
                    {inst.rate_aed != null ? inst.rate_aed.toLocaleString() : "0"}
                  </td>
                  <td className="py-2.5 pr-3 text-right font-bold tabular-nums">
                    {inst.total_aed.toLocaleString()}
                  </td>
                  <td className="py-2.5 pr-3">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <PaymentStatusBadge
                        variant={inst.outcome === "added" ? "added" : inst.outcome === "ignored" ? "ignored" : "pending"}
                        label={inst.outcome === "added" ? "Added" : inst.outcome === "ignored" ? "Ignored" : "Pending"}
                      />
                      {inst.letter_id && (
                        <button
                          type="button"
                          onClick={() => {
                            onClose()
                            onOpenLetter(inst.letter_id!)
                          }}
                          className="inline-flex items-center gap-1 rounded-[10px] border border-border px-2 py-0.5 text-[11px] font-semibold text-foreground hover:border-primary cursor-pointer"
                        >
                          {inst.letter_reference ?? "Letter"}
                          {inst.letter_status ? ` (${inst.letter_status})` : ""}
                          <ExternalLink size={11} />
                        </button>
                      )}
                    </div>
                  </td>
                  <td className="py-2.5 text-right">
                    {inst.outcome === "ignored" && (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={restoreMutation.isPending}
                        onClick={() => restoreMutation.mutate(inst.instructor_user_id)}
                        className="h-8 px-2.5 rounded-[10px] border-border text-xs font-semibold"
                      >
                        <RotateCcw size={13} className="mr-1" /> Restore
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-4 border-t border-border">
          <span className="text-sm font-extrabold text-foreground tabular-nums">
            Billed from Cohort: AED {totalAddedAed.toLocaleString()}
          </span>
          <div className="flex items-center gap-2 flex-wrap">
            {ignoredCount > 0 && (
              <Button
                variant="outline"
                size="lg"
                disabled={restoreMutation.isPending}
                onClick={() => restoreMutation.mutate(undefined)}
                className="h-9 px-3.5 rounded-[10px] border-border text-xs font-bold"
              >
                <RotateCcw size={14} className="mr-1.5" /> Restore Ignored to Pending ({ignoredCount})
              </Button>
            )}
            <Button
              size="lg"
              onClick={onClose}
              className="h-9 px-4 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold"
            >
              Close
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
