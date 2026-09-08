import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2 } from "lucide-react"
import { Spinner } from "@/components/ui/primitives"
import {
  clearCohortAssessmentAssignmentApi,
  getCohortAssessmentAssignmentApi,
  listAssessmentConfigsApi,
  setCohortAssessmentAssignmentApi,
} from "@/api/instructor_assessment"

const NONE = "__none__"

/** The instructor-assessment on/off switch for a cohort (2026-09). "None"
 *  selected = no gate at all — every cohort defaults here, and the existing
 *  apply flow is completely unaffected until ops picks a config. */
export function AssessmentAssignmentPanel({ cohortId }: { cohortId: string }) {
  const queryClient = useQueryClient()
  const [pendingConfigId, setPendingConfigId] = useState<string | null>(null)

  const { data: configs = [], isLoading: configsLoading } = useQuery({
    queryKey: ["assessment-configs"],
    queryFn: listAssessmentConfigsApi,
  })
  const { data: assignment, isLoading: assignmentLoading } = useQuery({
    queryKey: ["cohort-assessment-assignment", cohortId],
    queryFn: () => getCohortAssessmentAssignmentApi(cohortId),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["cohort-assessment-assignment", cohortId] })

  const setMutation = useMutation({
    mutationFn: (configId: string) => setCohortAssessmentAssignmentApi(cohortId, configId),
    onSuccess: invalidate,
  })
  const clearMutation = useMutation({
    mutationFn: () => clearCohortAssessmentAssignmentApi(cohortId),
    onSuccess: invalidate,
  })

  if (configsLoading || assignmentLoading) return <Spinner />

  const currentValue = pendingConfigId ?? assignment?.config_id ?? NONE

  return (
    <div className="flex flex-col gap-4 py-4">
      <div>
        <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1 block">
          Assessment config
        </label>
        <select
          value={currentValue}
          onChange={(e) => {
            const value = e.target.value
            setPendingConfigId(value)
            if (value === NONE) clearMutation.mutate()
            else setMutation.mutate(value)
          }}
          className="w-full max-w-md h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
        >
          <option value={NONE}>None — no assessment required</option>
          {configs.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
      </div>

      {assignment && (
        <div className="flex items-start gap-3 max-w-md px-4 py-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30">
          <CheckCircle2 size={18} className="text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
          <p className="text-sm">
            Instructors applying to this cohort's open calls must pass <strong>{assignment.config_name}</strong> first.
          </p>
        </div>
      )}

      <p className="text-xs text-muted-foreground max-w-md">
        Applies to all calls opened on this cohort from now on. Already-registered applicants aren't retroactively required.
      </p>
    </div>
  )
}
