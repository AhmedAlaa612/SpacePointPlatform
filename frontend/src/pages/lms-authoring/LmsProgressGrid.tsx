import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { getProgramsApi } from "@/api/sessions/programs"
import { getCohortsApi } from "@/api/sessions/cohorts"
import { getCourseProgressApi, getMissionProgressApi, type MissionStatus } from "@/api/lms_progress_grid"
import { ItemPicker } from "@/pages/lms-authoring/components/ItemPicker"
import type { Program, Cohort } from "@/types/sessions"

const MISSION_STATUS_STYLE: Record<MissionStatus, string> = {
  passed: "bg-emerald-500/10 text-emerald-500",
  failed: "bg-red-500/10 text-red-500",
  submitted: "bg-amber-500/10 text-amber-600",
  in_progress: "bg-primary/10 text-primary",
  abandoned: "bg-muted text-muted-foreground",
}

const MISSION_STATUS_LABEL: Record<MissionStatus, string> = {
  passed: "Passed", failed: "Failed", submitted: "Submitted",
  in_progress: "In progress", abandoned: "Abandoned",
}

function CoursesProgressTab() {
  const [courseId, setCourseId] = useState("")
  const [programId, setProgramId] = useState("")
  const [cohortId, setCohortId] = useState("")

  const { data: programs = [] } = useQuery<Program[]>({ queryKey: ["sessions-programs"], queryFn: getProgramsApi })
  const { data: cohorts = [] } = useQuery<Cohort[]>({
    queryKey: ["sessions-cohorts", programId],
    queryFn: () => getCohortsApi(programId),
    enabled: !!programId,
  })
  const { data: progress, isLoading } = useQuery({
    queryKey: ["lms-admin-course-progress", courseId, cohortId],
    queryFn: () => getCourseProgressApi(courseId, cohortId || undefined),
    enabled: !!courseId,
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <ItemPicker type="course" value={courseId} onChange={setCourseId} />
        <span className="text-xs text-muted-foreground">filter by cohort:</span>
        <select
          value={programId}
          onChange={(e) => { setProgramId(e.target.value); setCohortId("") }}
          className="h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="">Any program…</option>
          {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select
          value={cohortId}
          onChange={(e) => setCohortId(e.target.value)}
          disabled={!programId}
          className="h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer disabled:opacity-50"
        >
          <option value="">Any cohort…</option>
          {cohorts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>

      {!courseId ? (
        <EmptyState title="Pick a course" hint="Choose a course above to see every enrolled student's progress." />
      ) : isLoading || !progress ? (
        <Spinner />
      ) : progress.rows.length === 0 ? (
        <EmptyState title="No enrolled students" hint="Nobody is actively enrolled in this course yet (or this cohort)." />
      ) : (
        <div className="overflow-x-auto rounded-xl ring-1 ring-border">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="text-left font-medium text-muted-foreground px-4 py-2.5">Student</th>
                <th className="text-left font-medium text-muted-foreground px-4 py-2.5">Progress</th>
              </tr>
            </thead>
            <tbody>
              {progress.rows.map((row) => (
                <tr key={row.user_id} className="border-b border-border last:border-0">
                  <td className="px-4 py-2.5 font-medium text-foreground whitespace-nowrap">{row.full_name}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <div className="w-24 h-1.5 rounded-full bg-muted overflow-hidden">
                        <div className="h-full bg-primary" style={{ width: `${row.pct}%` }} />
                      </div>
                      <span className="text-xs tabular-nums text-foreground">{row.pct}%</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function MissionsProgressTab() {
  const [missionId, setMissionId] = useState("")

  const { data: progress, isLoading } = useQuery({
    queryKey: ["lms-admin-mission-progress", missionId],
    queryFn: () => getMissionProgressApi(missionId),
    enabled: !!missionId,
  })

  return (
    <div className="flex flex-col gap-4">
      <ItemPicker type="mission" value={missionId} onChange={setMissionId} />

      {!missionId ? (
        <EmptyState title="Pick a mission" hint="Choose a mission above to see everyone who has attempted it." />
      ) : isLoading || !progress ? (
        <Spinner />
      ) : progress.rows.length === 0 ? (
        <EmptyState title="No attempts yet" hint="Nobody has attempted this mission (solo or as a team member) yet." />
      ) : (
        <div className="overflow-x-auto rounded-xl ring-1 ring-border">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="text-left font-medium text-muted-foreground px-4 py-2.5">Student</th>
                <th className="text-left font-medium text-muted-foreground px-4 py-2.5">Best attempt</th>
              </tr>
            </thead>
            <tbody>
              {progress.rows.map((row) => (
                <tr key={row.user_id} className="border-b border-border last:border-0">
                  <td className="px-4 py-2.5 font-medium text-foreground whitespace-nowrap">{row.full_name}</td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium ${MISSION_STATUS_STYLE[row.status]}`}>
                      {MISSION_STATUS_LABEL[row.status]}
                      {row.score !== null && <span className="opacity-70">· {row.score}%</span>}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/** Progress views (2026-08-12) — replaced the single cohort-first combined
 * grid with two narrower, all-students-by-default views: pick a course (or
 * a mission) and see everyone on it, rather than picking a cohort first.
 * The old `getProgressGridApi`/cohort-first grid (7B-1) still backs
 * `/lms/admin/progress-grid` for anything that needs the combined matrix,
 * but this page no longer renders it. */
export default function LmsProgressGrid() {
  const [tab, setTab] = useState<"courses" | "missions">("courses")

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Progress"
        subtitle="Pick a course or mission and see every student's progress on it."
      />

      <div className="flex gap-1 border-b border-border w-fit">
        {(["courses", "missions"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t === "courses" ? "Courses progress" : "Missions progress"}
          </button>
        ))}
      </div>

      {tab === "courses" ? <CoursesProgressTab /> : <MissionsProgressTab />}
    </div>
  )
}
