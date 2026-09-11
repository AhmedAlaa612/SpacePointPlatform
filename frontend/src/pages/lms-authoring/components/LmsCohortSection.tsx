import { useState } from "react"
import { Eye, ExternalLink } from "lucide-react"
import { getCohortProgramOverrideApi, createPreviewAssignmentApi } from "@/api/lms_admin"
import { CohortOverrideEditor } from "./LmsChecklistAuthoring"
import { CohortMissionsPanel, ProgressPanel, ReviewScopePanel } from "./LmsProgressAndMissions"
import { LmsComponentConfigPanel } from "./LmsComponentConfigPanel"

type SubTab = "checklist" | "missions" | "components" | "progress" | "review"
const SUBTAB_LABEL: Record<SubTab, string> = {
  checklist: "Checklist", missions: "Missions", components: "Components", progress: "Progress", review: "Review",
}

/** The cohort-scope quarter of `LmsProgramAdmin.tsx`'s own workspace
 * (checklist override / missions / progress / review), embedded directly
 * into `CohortDetail.tsx`'s "LMS" tab (2026-09) so ops manages a cohort's
 * checklist and student progress without leaving the cohort page. Always
 * ops-only (this page is `/operations/cohorts/...`), so `isStaff`/`readOnly`
 * are hardcoded rather than threaded in as props, unlike the standalone
 * page which also serves instructors. */
export function LmsCohortSection({ cohortId, cohortName }: { cohortId: string; cohortName: string }) {
  const [subtab, setSubtab] = useState<SubTab>("checklist")

  const handlePreview = async () => {
    try {
      const eff = await getCohortProgramOverrideApi(cohortId)
      const res = await createPreviewAssignmentApi(eff.lms_program_id, cohortId)
      window.open(`/learn/checklists/${res.assignment_id}`, "_blank")
    } catch (e) {
      console.error("Failed to open preview assignment", e)
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border">
        <div className="flex gap-1 overflow-x-auto scrollbar-none no-scrollbar">
          {(["checklist", "missions", "components", "progress", "review"] as const).map((t) => (
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

        <button
          onClick={handlePreview}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 mb-1 sm:mb-0 text-xs font-semibold rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors border border-primary/25 shrink-0 cursor-pointer self-start sm:self-center"
          title="Open identical student checklist in sandbox mode to test steps, submissions, and gating"
        >
          <Eye size={13} />
          <span>Preview as Student</span>
          <ExternalLink size={11} className="opacity-70" />
        </button>
      </div>

      {subtab === "checklist" && <CohortOverrideEditor cohortId={cohortId} isStaff readOnly={false} />}
      {subtab === "missions" && <CohortMissionsPanel cohortId={cohortId} isStaff />}
      {subtab === "components" && <LmsComponentConfigPanel ownerType="cohort" ownerId={cohortId} isStaff />}
      {subtab === "progress" && <ProgressPanel cohortId={cohortId} scopeLabel={cohortName} />}
      {subtab === "review" && <ReviewScopePanel cohortId={cohortId} />}
    </div>
  )
}
