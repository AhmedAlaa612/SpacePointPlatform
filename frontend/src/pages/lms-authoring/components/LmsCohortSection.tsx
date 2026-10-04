import { useState } from "react"
import { Eye } from "lucide-react"
import { CohortOverrideEditor } from "./LmsChecklistAuthoring"
import { CohortMissionsPanel, ProgressPanel } from "./LmsProgressAndMissions"
import { LmsComponentConfigPanel } from "./LmsComponentConfigPanel"
import { CohortQuizAnalysisPanel } from "./CohortQuizAnalysisPanel"
import { ObserverTeamModal } from "@/components/lms/ObserverTeamModal"

type SubTab = "checklist" | "missions" | "components" | "progress" | "analysis"
const SUBTAB_LABEL: Record<SubTab, string> = {
  checklist: "Checklist", missions: "Missions", components: "Components", progress: "Progress", analysis: "Analysis",
}

/** The cohort-scope quarter of `LmsProgramAdmin.tsx`'s own workspace
 * (checklist override / missions / progress / analysis), embedded directly
 * into `CohortDetail.tsx`'s "LMS" tab (2026-09) so ops manages a cohort's
 * checklist and student progress without leaving the cohort page. Always
 * ops-only (this page is `/operations/cohorts/...`), so `isStaff`/`readOnly`
 * are hardcoded rather than threaded in as props, unlike the standalone
 * page which also serves instructors. */
export function LmsCohortSection({ cohortId, cohortName }: { cohortId: string; cohortName: string }) {
  const [subtab, setSubtab] = useState<SubTab>("checklist")
  const [showObserverModal, setShowObserverModal] = useState(false)

  return (
    <div className="flex flex-col gap-5">
      {/* Dedicated clean header action row for mobile & desktop */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 bg-card border border-border rounded-xl">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-semibold text-sm text-foreground truncate">{cohortName}</span>
          <span className="text-xs text-muted-foreground whitespace-nowrap">• LMS Workspace</span>
        </div>
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

      <div className="flex gap-1 border-b border-border overflow-x-auto scrollbar-none no-scrollbar">
        {(["checklist", "missions", "components", "progress", "analysis"] as const).map((t) => (
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

      {subtab === "checklist" && <CohortOverrideEditor cohortId={cohortId} isStaff readOnly={false} />}
      {subtab === "missions" && <CohortMissionsPanel cohortId={cohortId} isStaff />}
      {subtab === "components" && <LmsComponentConfigPanel ownerType="cohort" ownerId={cohortId} isStaff />}
      {subtab === "progress" && <ProgressPanel cohortId={cohortId} scopeLabel={cohortName} />}
      {subtab === "analysis" && <CohortQuizAnalysisPanel cohortId={cohortId} />}

      <ObserverTeamModal
        cohortId={cohortId}
        cohortName={cohortName}
        open={showObserverModal}
        onClose={() => setShowObserverModal(false)}
      />
    </div>
  )
}
