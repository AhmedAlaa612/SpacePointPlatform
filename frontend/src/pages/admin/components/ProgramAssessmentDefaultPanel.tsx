/** A program's default instructor-assessment config (2026-09-13) — same
 *  copy-not-inheritance shape as `ProgramRolesPanel`'s role template:
 *  `create_cohort` seeds a brand-new cohort's own `AssessmentCohortAssignment`
 *  from this once, at creation. Editing this afterwards never reaches a
 *  cohort that already exists — ops overrides or clears the seeded copy per
 *  cohort from that cohort's own Assessment tab (`AssessmentAssignmentPanel`,
 *  also reused directly in the Cohort Wizard's Staffing step), same place
 *  that's always lived.
 */
import { useState } from "react"
import { Link } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Spinner } from "@/components/ui/primitives"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"
import type { Program } from "@/types/sessions"
import { listAssessmentConfigsApi } from "@/api/instructor_assessment"
import { updateProgramApi } from "@/api/sessions/programs"

const NONE = "__none__"

export function ProgramAssessmentDefaultPanel({ program, onUpdated }: {
  program: Program
  /** Programs.tsx and the Program Wizard each hold their own copy of
   *  `program` in local state — unlike the role template, this field lives
   *  directly on the Program row, so a caller that needs the fresh value
   *  (the wizard's Review step, in particular) has to be told about it. */
  onUpdated?: (program: Program) => void
}) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [pendingConfigId, setPendingConfigId] = useState<string | null>(null)

  const { data: configs = [], isLoading } = useQuery({
    queryKey: ["assessment-configs"],
    queryFn: listAssessmentConfigsApi,
  })

  const mutation = useMutation({
    mutationFn: (configId: string | null) =>
      updateProgramApi(program.id, { default_assessment_config_id: configId }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["sessions-programs"] })
      onUpdated?.(updated)
    },
    onError: (e: any) => {
      toast.error(getErrorMessage(e, "Failed to update the assessment default"))
      setPendingConfigId(null)
    },
  })

  if (isLoading) return <Spinner />

  const currentValue = pendingConfigId ?? program.default_assessment_config_id ?? NONE
  const currentConfig = configs.find((c) => c.id === currentValue)

  return (
    <div className="flex flex-col gap-3">
      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground block">
            Default instructor assessment
          </label>
          <Link to="/instructors/admin/assessment-questions" className="text-xs text-primary hover:underline">
            Manage question bank →
          </Link>
        </div>
        <select
          value={currentValue}
          onChange={(e) => {
            const value = e.target.value
            setPendingConfigId(value)
            mutation.mutate(value === NONE ? null : value)
          }}
          className="w-full max-w-md h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
        >
          <option value={NONE}>None — new cohorts start with no assessment gate</option>
          {configs.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
      </div>

      <p className="text-xs text-muted-foreground max-w-md">
        {currentConfig
          ? <>Every new cohort of this program starts requiring <strong className="text-foreground">{currentConfig.name}</strong> before instructors can apply — a one-time copy at creation, not a live link. </>
          : "A one-time copy at creation, not a live link. "}
        Editing this later never reaches a cohort that already exists; override or clear it per cohort from that
        cohort's own Assessment tab.
      </p>
    </div>
  )
}
