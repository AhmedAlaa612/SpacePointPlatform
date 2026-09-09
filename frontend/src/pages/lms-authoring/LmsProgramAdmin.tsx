import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
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
import { ProgramMissionsPanel, CohortMissionsPanel, ProgressPanel, ReviewScopePanel } from "./components/LmsProgressAndMissions"

type Scope = "program" | { cohortId: string; cohortName: string }
type SubTab = "checklist" | "missions" | "progress" | "review"
const SUBTAB_LABEL: Record<SubTab, string> = {
  checklist: "Checklist", missions: "Missions", progress: "Progress", review: "Review",
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

  const { data: staffPrograms = [], isLoading: staffProgramsLoading } = useQuery<Program[]>({
    queryKey: ["sessions-programs"], queryFn: getProgramsApi, enabled: isStaff,
  })
  const { data: myPrograms = [], isLoading: myProgramsLoading } = useQuery<LmsProgram[]>({
    queryKey: ["my-reachable-lms-programs"], queryFn: getMyReachableProgramsApi, enabled: !isStaff,
  })

  const [programId, setProgramId] = useState("")
  const programsLoading = isStaff ? staffProgramsLoading : myProgramsLoading
  const preloadedProgram = !isStaff ? myPrograms.find((p) => p.program_id === programId) : undefined

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Programs"
        subtitle="Each program's checklist, mission runs, and student progress — pick a cohort to see its own overridden checklist, gated missions, and submissions."
      />

      <div className="max-w-sm">
        <select
          value={programId} onChange={(e) => setProgramId(e.target.value)}
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
  const [scope, setScope] = useState<Scope>("program")
  const [subtab, setSubtab] = useState<SubTab>("checklist")

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

  // Instructors don't get a "Program" scope at all — they land straight on
  // their own cohort (operator ask, 2026-08-23), never the master template.
  useEffect(() => {
    if (!isStaff && scope === "program" && cohorts.length > 0) {
      setScope({ cohortId: cohorts[0].id, cohortName: cohorts[0].name })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStaff, scope, cohorts.length])

  const createMutation = useMutation({
    mutationFn: (name: string) => createLmsProgramApi({ program_id: programId, name }),
    onSuccess: (p) => setCreated(p),
  })

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
      <div className="flex items-center gap-1 border-b border-border overflow-x-auto">
        {isStaff && (
          <button
            onClick={() => setScope("program")}
            className={`px-3 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors cursor-pointer whitespace-nowrap ${
              scope === "program" ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            Program
          </button>
        )}
        {cohorts.map((c) => (
          <button
            key={c.id}
            onClick={() => setScope({ cohortId: c.id, cohortName: c.name })}
            className={`px-3 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors cursor-pointer whitespace-nowrap ${
              typeof scope === "object" && scope.cohortId === c.id ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {c.name}
          </button>
        ))}
      </div>

      <div className="flex gap-1 border-b border-border">
        {(["checklist", "missions", "progress", "review"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setSubtab(t)}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
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
      {subtab === "progress" && (
        scope === "program"
          ? <ProgressPanel lmsProgramId={effective.id} scopeLabel="every cohort using this program" />
          : <ProgressPanel cohortId={scope.cohortId} scopeLabel={scope.cohortName} />
      )}
      {subtab === "review" && (
        scope === "program"
          ? <EmptyState title="Pick a cohort to review submissions" hint="A mission run's review queue is always cohort-scoped." />
          : <ReviewScopePanel cohortId={scope.cohortId} />
      )}
    </div>
  )
}
