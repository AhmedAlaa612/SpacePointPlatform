import { useEffect, useState } from "react"
import { ExternalLink, Eye, Shield } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  getCohortProgramOverrideApi,
  getCohortProgramOverrideInstructorApi,
  getCohortLmsEditorsApi,
  updateCohortPosterTemplateApi,
} from "@/api/lms_admin"
import { getCohortApi, updateCohortApi } from "@/api/sessions/cohorts"
import { useToast } from "@/components/ui/toast"
import { ensureAbsoluteUrl } from "@/lib/utils"
import { CohortOverrideEditor } from "./LmsChecklistAuthoring"
import { CohortMissionsPanel } from "./LmsProgressAndMissions"
import { LmsComponentConfigPanel } from "./LmsComponentConfigPanel"
import { CohortProgressPanel, CohortAnalysisPanel } from "@/pages/admin/components/CohortProgressAnalysisPanel"
import { LmsHintStationAuthoring } from "./LmsHintStationAuthoring"
import { ObserverTeamModal } from "@/components/lms/ObserverTeamModal"
import { SubmissionWindowsModal } from "@/components/competitions/SubmissionWindowsModal"
import { CohortLmsEditorsModal } from "./CohortLmsEditorsModal"

type SubTab = "checklist" | "missions" | "components" | "hints" | "windows" | "progress" | "analysis"
const SUBTAB_LABEL: Record<SubTab, string> = {
  checklist: "Checklist",
  missions: "Missions",
  components: "Components",
  hints: "Hints",
  windows: "Submission Windows",
  progress: "Progress",
  analysis: "Analysis",
}

export function LmsCohortSection({
  cohortId,
  cohortName,
  mode = "all",
}: {
  cohortId: string
  cohortName: string
  mode?: "all" | "authoring"
}) {
  const { currentUser } = useAuth()
  const toast = useToast()
  const queryClient = useQueryClient()
  const isStaff = currentUser?.role !== "instructor"
  const [subtab, setSubtab] = useState<SubTab>("checklist")
  const [showObserverModal, setShowObserverModal] = useState(false)
  const [showEditorsModal, setShowEditorsModal] = useState(false)

  const visibleSubtabs: SubTab[] =
    mode === "authoring"
      ? ["checklist", "missions", "components", "hints", "windows"]
      : ["checklist", "missions", "components", "hints", "windows", "progress", "analysis"]

  const { data: instructorOverride } = useQuery({
    queryKey: ["lms-cohort-override-instructor", cohortId],
    queryFn: () => getCohortProgramOverrideInstructorApi(cohortId),
    enabled: !isStaff,
  })

  const { data: staffOverride } = useQuery({
    queryKey: ["lms-cohort-override", cohortId],
    queryFn: () => getCohortProgramOverrideApi(cohortId),
    enabled: isStaff,
  })

  const { data: cohortData } = useQuery({
    queryKey: ["cohort-detail", cohortId],
    queryFn: () => getCohortApi(cohortId),
    enabled: isStaff,
  })

  const { data: editorsData } = useQuery({
    queryKey: ["cohort-lms-editors", cohortId],
    queryFn: () => getCohortLmsEditorsApi(cohortId),
    enabled: isStaff,
  })

  const canEdit = isStaff || Boolean(instructorOverride?.can_edit)
  const editorCount = editorsData?.editors?.length ?? 0

  const storedOverride = cohortData?.checklist_title_override ?? null
  const defaultTitle = cohortData?.program_name && cohortData
    ? `${cohortData.program_name} — ${cohortData.name}`
    : cohortData?.name ?? cohortName
  const [titleValue, setTitleValue] = useState(defaultTitle)
  useEffect(() => {
    setTitleValue(storedOverride ?? defaultTitle)
  }, [storedOverride, defaultTitle])

  const updateTitleMutation = useMutation({
    mutationFn: (val: string | null) => updateCohortApi(cohortId, { checklist_title_override: val }),
    onSuccess: (_data, val) => {
      toast.success(val === null ? "Title reset to default" : "LMS title saved")
      void queryClient.invalidateQueries({ queryKey: ["cohort-detail", cohortId] })
      void queryClient.invalidateQueries({ queryKey: ["lms-cohort-override", cohortId] })
    },
    onError: () => toast.error("Failed to update LMS title"),
  })

  const saveTitle = () => {
    const val = titleValue.trim() || null
    const target = val && defaultTitle && val === defaultTitle ? null : val
    if (target === storedOverride) return
    updateTitleMutation.mutate(target)
  }

  const updatePosterMutation = useMutation({
    mutationFn: (url: string | null) => updateCohortPosterTemplateApi(cohortId, url),
    onSuccess: () => {
      toast.success("Poster link updated")
      void queryClient.invalidateQueries({ queryKey: ["lms-cohort-override", cohortId] })
    },
    onError: () => toast.error("Failed to update poster link"),
  })

  const effectivePosterUrl = staffOverride?.poster_template_url || staffOverride?.inherited_poster_template_url

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 p-3.5 bg-card border border-border rounded-[10px]">
        {isStaff ? (
          <div className="flex flex-col sm:flex-row sm:items-center gap-2.5 flex-1 min-w-0">
            <div className="flex items-center gap-1.5 flex-1 min-w-0">
              <input
                type="text"
                value={titleValue}
                onChange={(e) => setTitleValue(e.target.value)}
                onBlur={saveTitle}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); saveTitle() } }}
                disabled={updateTitleMutation.isPending}
                placeholder="LMS Cohort Title"
                aria-label="LMS Cohort Title"
                className="flex-1 min-w-0 h-9 px-3 border border-border bg-background text-foreground rounded-[10px] text-sm font-medium focus:outline-none focus:border-primary"
              />
              <button
                type="button"
                onClick={saveTitle}
                disabled={updateTitleMutation.isPending || titleValue.trim() === (storedOverride ?? defaultTitle)}
                className="h-9 px-3 bg-primary text-primary-foreground text-xs font-semibold rounded-[10px] hover:opacity-90 disabled:opacity-40 cursor-pointer shrink-0"
              >
                Save
              </button>
            </div>
            <div className="flex items-center gap-1.5 flex-1 min-w-0">
              <input
                type="url"
                defaultValue={staffOverride?.poster_template_url ?? ""}
                key={staffOverride?.poster_template_url ?? "poster"}
                placeholder={staffOverride?.inherited_poster_template_url || "Poster template URL"}
                aria-label="Poster template URL"
                className="flex-1 min-w-0 h-9 px-3 border border-border bg-background text-foreground rounded-[10px] text-sm focus:outline-none focus:border-primary"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault()
                    const val = (e.target as HTMLInputElement).value.trim()
                    updatePosterMutation.mutate(val || null)
                  }
                }}
                onBlur={(e) => {
                  const val = e.target.value.trim()
                  if (val !== (staffOverride?.poster_template_url ?? "")) {
                    updatePosterMutation.mutate(val || null)
                  }
                }}
              />
              {effectivePosterUrl && (
                <a
                  href={ensureAbsoluteUrl(effectivePosterUrl)}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 h-9 px-3 border border-border rounded-[10px] text-xs font-medium text-primary hover:bg-muted shrink-0"
                >
                  Poster <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}
            </div>
          </div>
        ) : (
          <span className="font-semibold text-sm text-foreground truncate">{cohortName}</span>
        )}
        <div className="flex items-center gap-2 shrink-0">
          {isStaff && (
            <button
              type="button"
              onClick={() => setShowEditorsModal(true)}
              className="inline-flex items-center justify-center gap-1.5 h-9 px-3 rounded-[10px] border border-border bg-card text-xs font-semibold text-foreground hover:bg-muted transition-colors cursor-pointer"
            >
              <Shield className="w-3.5 h-3.5" />
              Instructors {editorCount > 0 ? `(${editorCount})` : ""}
            </button>
          )}
          <button
            type="button"
            onClick={() => setShowObserverModal(true)}
            className="inline-flex items-center justify-center gap-1.5 h-9 px-3.5 rounded-[10px] border border-primary/30 bg-primary/10 text-xs font-semibold text-primary hover:bg-primary/20 transition-colors cursor-pointer shrink-0"
          >
            <Eye className="w-3.5 h-3.5" />
            Try as Observer
          </button>
        </div>
      </div>

      <div className="flex gap-1 border-b border-border overflow-x-auto scrollbar-none no-scrollbar">
        {visibleSubtabs.map((t) => (
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
      {subtab === "components" && <LmsComponentConfigPanel ownerType="cohort" ownerId={cohortId} isStaff={isStaff} />}
      {subtab === "hints" && (
        <LmsHintStationAuthoring programId="" scope={{ cohortId, cohortName }} />
      )}
      {subtab === "windows" && <SubmissionWindowsModal cohortId={cohortId} embedded />}
      {subtab === "progress" && <CohortProgressPanel cohortId={cohortId} cohortName={cohortName} />}
      {subtab === "analysis" && <CohortAnalysisPanel cohortId={cohortId} />}

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
