import { useState } from "react"
import { CohortOverrideEditor } from "./LmsChecklistAuthoring"
import { CohortMissionsPanel, ProgressPanel } from "./LmsProgressAndMissions"
import { LmsComponentConfigPanel } from "./LmsComponentConfigPanel"
import { CohortQuizAnalysisPanel } from "./CohortQuizAnalysisPanel"

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

  return (
    <div className="flex flex-col gap-5">
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
    </div>
  )
}
