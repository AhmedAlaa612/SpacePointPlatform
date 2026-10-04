import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useSearch } from "@tanstack/react-router"
import { Eye } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { useAuth } from "@/context/AuthContext"
import { getProgramsApi } from "@/api/sessions/programs"
import { getCohortsApi } from "@/api/sessions/cohorts"
import {
  listLmsProgramsApi, createLmsProgramApi, getLmsProgramApi, getMyReachableProgramsApi,
  type LmsProgram,
} from "@/api/lms_admin"
import { myInstructorCohortsApi, type InstructorCohort } from "@/api/missionsInstructor"
import type { Program } from "@/types/sessions"
import { CreateChecklistPrompt, ProgramTemplateEditor, CohortOverrideEditor } from "./components/LmsChecklistAuthoring"
import { ProgramMissionsPanel, CohortMissionsPanel, ProgressPanel } from "./components/LmsProgressAndMissions"
import { CohortQuizAnalysisPanel } from "./components/CohortQuizAnalysisPanel"
import { LmsComponentConfigPanel } from "./components/LmsComponentConfigPanel"
import { ObserverTeamModal } from "@/components/lms/ObserverTeamModal"

type Scope = "program" | { cohortId: string; cohortName: string }
type SubTab = "checklist" | "missions" | "components" | "progress" | "analysis"
const SUBTAB_LABEL: Record<SubTab, string> = {
  checklist: "Checklist", missions: "Missions", components: "Components", progress: "Progress", analysis: "Analysis",
}

/** The one LMS Programs page (2026-08-22 merge) — absorbs what used to be
 * the separate Cohort Missions page. Operator's own framing: pick a
 * program, see its template + mission runs + student progress/submissions;
 * pick a cohort and the same four views switch into that cohort's own
 * scope (override checklist, gated missions, cohort-only roster/review).
 * Instructors get the same page, restricted to their own programs/cohorts
 * (`getMyReachableProgramsApi`/`myInstructorCohortsApi`, both already
 * scoped server-side the same way `/missions/instructor/*` always has
 * been) and read-only on the checklist itself — editing the template or a
 * cohort's override stays ops-only, same boundary as before this merge.
 * Replaces `LmsCurriculum.tsx` (2026-08-21) and `CohortMissions.tsx`
 * (2026-08-17, removed entirely by this change).
 *
 * The actual checklist/progress/missions/review components live in
 * `./components/LmsChecklistAuthoring.tsx` and
 * `./components/LmsProgressAndMissions.tsx` (extracted 2026-09) so
 * `CohortDetail.tsx`, `SessionDetail.tsx`, and the Program/Cohort wizards
 * can reuse them directly instead of ops/instructors having to leave for
 * this standalone page. */
export default function LmsProgramAdmin() {
  const { currentUser } = useAuth()
  const isStaff = currentUser?.role !== "instructor"
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as {
    programId?: string
    cohortId?: string
    tab?: SubTab
  }

  const { data: staffPrograms = [], isLoading: staffProgramsLoading } = useQuery<Program[]>({
    queryKey: ["sessions-programs"], queryFn: getProgramsApi, enabled: isStaff,
  })
  const { data: myPrograms = [], isLoading: myProgramsLoading } = useQuery<LmsProgram[]>({
    queryKey: ["my-reachable-lms-programs"], queryFn: getMyReachableProgramsApi, enabled: !isStaff,
  })

  const programId = search.programId ?? ""
  const programsLoading = isStaff ? staffProgramsLoading : myProgramsLoading
  const preloadedProgram = !isStaff ? myPrograms.find((p) => p.program_id === programId) : undefined

  // Auto-select if instructor only has one reachable program
  useEffect(() => {
    if (!isStaff && !programId && myPrograms.length === 1 && myPrograms[0]?.program_id) {
      void navigate({
        to: "/lms-authoring/curriculum",
        search: {
          ...search,
          programId: myPrograms[0].program_id,
        } as never,
        replace: true,
      })
    }
  }, [isStaff, programId, myPrograms, search, navigate])

  const handleProgramChange = (newProgramId: string) => {
    void navigate({
      to: "/lms-authoring/curriculum",
      search: {
        programId: newProgramId || undefined,
        cohortId: undefined, // reset cohort when program changes
        tab: search.tab,
      } as never,
    })
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Programs"
        subtitle="Each program's checklist, mission runs, and student progress — pick a cohort to see its own overridden checklist, gated missions, and submissions."
      />

      <div className="max-w-sm">
        <select
          value={programId} onChange={(e) => handleProgramChange(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="">Select a program…</option>
          {isStaff
            ? staffPrograms.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)
            : myPrograms.map((p) => <option key={p.id} value={p.program_id ?? ""}>{p.name}</option>)}
        </select>
      </div>

      {programsLoading ? (
        <Spinner />
      ) : !programId ? (
        <EmptyState
          title="Pick a program"
          hint={isStaff ? "Choose a program above to manage its checklist, missions, and student progress." : "Only programs attached to your own cohorts show up here."}
        />
      ) : (
        <ProgramWorkspace key={programId} programId={programId} isStaff={isStaff} preloadedProgram={preloadedProgram} />
      )}
    </div>
  )
}

function ProgramWorkspace({
  programId, isStaff, preloadedProgram,
}: { programId: string; isStaff: boolean; preloadedProgram?: LmsProgram }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as {
    programId?: string
    cohortId?: string
    tab?: SubTab
  }

  const VALID_SUBTABS: SubTab[] = ["checklist", "missions", "components", "progress", "analysis"]
  const rawTab = search.tab as SubTab | undefined
  const subtab: SubTab = (rawTab && VALID_SUBTABS.includes(rawTab)) ? rawTab : "checklist"

  const setSubtab = (t: SubTab) => {
    void navigate({
      to: "/lms-authoring/curriculum",
      search: {
        ...search,
        programId,
        tab: t,
      } as never,
      replace: true,
    })
  }

  const { data: found = [], isLoading } = useQuery<LmsProgram[]>({
    queryKey: ["lms-program-for-program", programId], queryFn: () => listLmsProgramsApi(programId),
    enabled: isStaff,
  })
  const [created, setCreated] = useState<LmsProgram | null>(null)
  const effective = created ?? (isStaff ? found[0] : preloadedProgram) ?? null

  const { data: staffCohorts = [] } = useQuery({
    queryKey: ["sessions-cohorts", programId], queryFn: () => getCohortsApi(programId), enabled: isStaff,
  })
  const { data: instructorCohorts = [] } = useQuery<InstructorCohort[]>({
    queryKey: ["instructor-cohorts"], queryFn: myInstructorCohortsApi, enabled: !isStaff,
  })
  const cohorts = isStaff
    ? staffCohorts.map((c) => ({ id: c.id, name: c.name }))
    : instructorCohorts.filter((c) => c.program_id === programId).map((c) => ({ id: c.id, name: c.name }))

  const matchingCohort = search.cohortId ? cohorts.find((c) => c.id === search.cohortId) : undefined

  const scope: Scope = useMemo(() => {
    if (matchingCohort) {
      return { cohortId: matchingCohort.id, cohortName: matchingCohort.name }
    }
    if (search.cohortId) {
      return { cohortId: search.cohortId, cohortName: "Cohort" }
    }
    if (!isStaff && cohorts.length > 0) {
      return { cohortId: cohorts[0].id, cohortName: cohorts[0].name }
    }
    return "program"
  }, [matchingCohort, search.cohortId, isStaff, cohorts])

  // Instructors don't get a "Program" scope at all — they land straight on
  // their own cohort (operator ask, 2026-08-23), never the master template.
  useEffect(() => {
    if (!isStaff && !search.cohortId && cohorts.length > 0) {
      void navigate({
        to: "/lms-authoring/curriculum",
        search: {
          ...search,
          programId,
          cohortId: cohorts[0].id,
        } as never,
        replace: true,
      })
    }
  }, [isStaff, search.cohortId, cohorts, programId, search, navigate])

  const createMutation = useMutation({
    mutationFn: (name: string) => createLmsProgramApi({ program_id: programId, name }),
    onSuccess: (p) => setCreated(p),
  })

  // Observer mode (2026-10) — 1-click staff authoring access ("Try as
  // Observer"): creates/reuses the caller's own mode='observer' assignment
  // for the viewed cohort, then lands on the real student board.
  const [showObserverModal, setShowObserverModal] = useState(false)

  const refresh = async () => {
    if (isStaff && effective) {
      const fresh = await getLmsProgramApi(effective.id)
      setCreated(fresh)
      void queryClient.invalidateQueries({ queryKey: ["lms-program-for-program", programId] })
    } else {
      void queryClient.invalidateQueries({ queryKey: ["my-reachable-lms-programs"] })
    }
  }

  if (isStaff && isLoading) return <Spinner />

  if (!effective) {
    if (!isStaff) {
      return <EmptyState title="This program has no LMS checklist yet" hint="Ask ops to create one — instructors can't start a program's checklist from scratch." />
    }
    return <CreateChecklistPrompt onCreate={(name) => createMutation.mutate(name)} pending={createMutation.isPending} />
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-1 border-b border-border overflow-x-auto scrollbar-none no-scrollbar">
        {isStaff && (
          <button
            onClick={() => void navigate({
              to: "/lms-authoring/curriculum",
              search: {
                ...search,
                programId,
                cohortId: undefined,
              } as never,
              replace: true,
            })}
            className={`px-3 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors cursor-pointer shrink-0 whitespace-nowrap ${
              scope === "program" ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            Program
          </button>
        )}
        {cohorts.map((c) => (
          <button
            key={c.id}
            onClick={() => void navigate({
              to: "/lms-authoring/curriculum",
              search: {
                ...search,
                programId,
                cohortId: c.id,
              } as never,
              replace: true,
            })}
            className={`px-3 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors cursor-pointer shrink-0 whitespace-nowrap ${
              typeof scope === "object" && scope.cohortId === c.id ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {c.name}
          </button>
        ))}
      </div>

      {typeof scope === "object" && (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 p-3.5 bg-card border border-border rounded-xl">
          <div className="flex items-center gap-2 min-w-0">
            <span className="font-semibold text-sm text-foreground truncate">{scope.cohortName}</span>
            <span className="text-xs text-muted-foreground whitespace-nowrap">• Cohort LMS Workspace</span>
          </div>
          <button
            type="button"
            onClick={() => setShowObserverModal(true)}
            className="inline-flex items-center justify-center gap-1.5 h-8 px-3.5 rounded-lg border border-indigo-500/30 bg-indigo-500/10 text-xs font-semibold text-indigo-900 dark:text-indigo-200 hover:bg-indigo-500/20 transition-colors cursor-pointer self-start sm:self-auto shrink-0"
            title="Open this cohort's student board as an observer to try every item yourself"
          >
            <Eye className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
            Try as Observer
          </button>
        </div>
      )}

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

      {subtab === "checklist" && (
        scope === "program"
          ? <ProgramTemplateEditor program={effective} onChanged={refresh} readOnly={!isStaff} />
          : <CohortOverrideEditor cohortId={scope.cohortId} isStaff={isStaff} readOnly={!isStaff} />
      )}
      {subtab === "missions" && (
        scope === "program"
          ? <ProgramMissionsPanel program={effective} onChanged={refresh} readOnly={!isStaff} />
          : <CohortMissionsPanel cohortId={scope.cohortId} isStaff={isStaff} />
      )}
      {subtab === "components" && (
        scope === "program"
          ? <LmsComponentConfigPanel ownerType="program" ownerId={effective.id} isStaff={isStaff} />
          : <LmsComponentConfigPanel ownerType="cohort" ownerId={scope.cohortId} isStaff={isStaff} />
      )}
      {subtab === "progress" && (
        scope === "program"
          ? <ProgressPanel lmsProgramId={effective.id} scopeLabel="every cohort using this program" />
          : <ProgressPanel cohortId={scope.cohortId} scopeLabel={scope.cohortName} />
      )}
      {subtab === "analysis" && (
        scope === "program"
          ? <EmptyState title="Pick a cohort to view quiz analysis" hint="Quiz attempts and topic mastery are cohort-scoped. Select a cohort tab above." />
          : <CohortQuizAnalysisPanel cohortId={scope.cohortId} />
      )}

      {typeof scope === "object" && (
        <ObserverTeamModal
          cohortId={scope.cohortId}
          cohortName={scope.cohortName}
          open={showObserverModal}
          onClose={() => setShowObserverModal(false)}
        />
      )}
    </div>
  )
}
