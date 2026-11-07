import { useState } from "react"
import { Eye, Shield } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { useQuery } from "@tanstack/react-query"
import { getCohortProgramOverrideInstructorApi, getCohortLmsEditorsApi } from "@/api/lms_admin"
import { CohortOverrideEditor } from "./LmsChecklistAuthoring"
import { CohortMissionsPanel, ProgressPanel } from "./LmsProgressAndMissions"
import { LmsComponentConfigPanel } from "./LmsComponentConfigPanel"
import { CohortQuizAnalysisPanel } from "./CohortQuizAnalysisPanel"
import { LmsHintStationAuthoring } from "./LmsHintStationAuthoring"
import { ObserverTeamModal } from "@/components/lms/ObserverTeamModal"
import { CohortLmsEditorsModal } from "./CohortLmsEditorsModal"

type SubTab = "checklist" | "missions" | "components" | "hints" | "progress" | "analysis"
const SUBTAB_LABEL: Record<SubTab, string> = {
  checklist: "Checklist", missions: "Missions", components: "Components", hints: "Hints", progress: "Progress", analysis: "Analysis",
}

export function LmsCohortSection({ cohortId, cohortName }: { cohortId: string; cohortName: string }) {
  const { currentUser } = useAuth()
  const isStaff = currentUser?.role !== "instructor"
  const [subtab, setSubtab] = useState<SubTab>("checklist")
  const [showObserverModal, setShowObserverModal] = useState(false)
  const [showEditorsModal, setShowEditorsModal] = useState(false)

  const { data: instructorOverride } = useQuery({
    queryKey: ["lms-cohort-override-instructor", cohortId],
    queryFn: () => getCohortProgramOverrideInstructorApi(cohortId),
    enabled: !isStaff,
  })

  const { data: editorsData } = useQuery({
    queryKey: ["cohort-lms-editors", cohortId],
    queryFn: () => getCohortLmsEditorsApi(cohortId),
    enabled: isStaff,
  })

  const canEdit = isStaff || Boolean(instructorOverride?.can_edit)
  const editorCount = editorsData?.editors?.length ?? 0

  return (
    <div className="flex flex-col gap-5">
      {/* Clean header action row */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 bg-card border border-border rounded-xl">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-semibold text-sm text-foreground truncate">{cohortName}</span>
          <span className="text-xs text-muted-foreground whitespace-nowrap">• LMS Workspace</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {isStaff && (
            <button
              type="button"
              onClick={() => setShowEditorsModal(true)}
              className="inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-lg border border-border bg-card text-xs font-semibold text-foreground hover:bg-muted transition-colors cursor-pointer"
            >
              <Shield className="w-3.5 h-3.5" />
              Instructors {editorCount > 0 ? `(${editorCount})` : ""}
            </button>
          )}
          <button
            type="button"
            onClick={() => setShowObserverModal(true)}
            className="inline-flex items-center justify-center gap-1.5 h-8 px-3.5 rounded-lg border border-indigo-500/30 bg-indigo-500/10 text-xs font-semibold text-indigo-900 dark:text-indigo-200 hover:bg-indigo-500/20 transition-colors cursor-pointer self-start sm:self-auto shrink-0"
            title="Try this cohort as an observer to experience the full student flow"
          >
            <Eye className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
            Try as Observer
          </button>
        </div>
      </div>

      <div className="flex gap-1 border-b border-border overflow-x-auto scrollbar-none no-scrollbar">
        {(["checklist", "missions", "components", "hints", "progress", "analysis"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setSubtab(t)}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors cursor-pointer shrink-0 whitespace-nowrap ${
              subtab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
          >
            {SUBTAB_LABEL[t]}
          </button>
        ))}
      </div>

      {subtab === "checklist" && <CohortOverrideEditor cohortId={cohortId} isStaff={isStaff} readOnly={!canEdit} />}
      {subtab === "missions" && <CohortMissionsPanel cohortId={cohortId} isStaff={canEdit} />}
      {subtab === "components" && <LmsComponentConfigPanel ownerType="cohort" ownerId={cohortId} isStaff={canEdit} />}
      {subtab === "hints" && (
        <LmsHintStationAuthoring programId="" scope={{ cohortId, cohortName }} />
      )}
      {subtab === "progress" && <ProgressPanel cohortId={cohortId} scopeLabel={cohortName} />}
      {subtab === "analysis" && <CohortQuizAnalysisPanel cohortId={cohortId} />}

      <ObserverTeamModal
        cohortId={cohortId}
        cohortName={cohortName}
        open={showObserverModal}
        onClose={() => setShowObserverModal(false)}
      />

      {isStaff && (
        <CohortLmsEditorsModal
          cohortId={cohortId}
          cohortName={cohortName}
          open={showEditorsModal}
          onClose={() => setShowEditorsModal(false)}
        />
      )}
    </div>
  )
}
