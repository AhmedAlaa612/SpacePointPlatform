import { useState } from "react"
import { ProgressPanel } from "@/pages/lms-authoring/components/LmsProgressAndMissions"
import { CohortQuizAnalysisPanel } from "@/pages/lms-authoring/components/CohortQuizAnalysisPanel"
import { CompetitionAnalysisTab } from "@/pages/admin/components/CompetitionAnalysis"

type ScopeSubTab = "individual" | "teams"

const SCOPE_TABS: { key: ScopeSubTab; label: string }[] = [
  { key: "individual", label: "Individual" },
  { key: "teams", label: "Teams" },
]

function ScopeToggle({
  value,
  onChange,
}: {
  value: ScopeSubTab
  onChange: (next: ScopeSubTab) => void
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {SCOPE_TABS.map((t) => (
        <button
          key={t.key}
          type="button"
          onClick={() => onChange(t.key)}
          className={`h-9 px-3.5 rounded-[10px] border text-sm font-medium transition-colors cursor-pointer ${
            value === t.key
              ? "bg-primary/10 border-primary/40 text-primary font-semibold"
              : "bg-background border-border text-muted-foreground hover:text-foreground hover:bg-muted"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

/** Cohort Progress view with Individual and Teams scope toggle. */
export function CohortProgressPanel({
  cohortId,
  cohortName,
}: {
  cohortId: string
  cohortName: string
}) {
  const [scope, setScope] = useState<ScopeSubTab>("individual")

  return (
    <div className="flex flex-col gap-5">
      <ScopeToggle value={scope} onChange={setScope} />
      {scope === "individual" && <ProgressPanel cohortId={cohortId} scopeLabel={cohortName} />}
      {scope === "teams" && <CompetitionAnalysisTab cohortId={cohortId} view="progress" />}
    </div>
  )
}

/** Cohort Analysis view with Individual and Teams scope toggle. */
export function CohortAnalysisPanel({ cohortId }: { cohortId: string }) {
  const [scope, setScope] = useState<ScopeSubTab>("individual")

  return (
    <div className="flex flex-col gap-5">
      <ScopeToggle value={scope} onChange={setScope} />
      {scope === "individual" && <CohortQuizAnalysisPanel cohortId={cohortId} />}
      {scope === "teams" && <CompetitionAnalysisTab cohortId={cohortId} view="analysis" />}
    </div>
  )
}
