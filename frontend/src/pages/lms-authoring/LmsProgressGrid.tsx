import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ArrowLeft } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { getProgramsApi } from "@/api/sessions/programs"
import { getCohortsApi } from "@/api/sessions/cohorts"
import {
  getCourseProgressApi, getCoursesOverviewApi, getMissionProgressApi, getMissionsOverviewApi,
  type CourseOverviewRow, type MissionOverviewRow, type MissionStatus,
} from "@/api/lms_progress_grid"
import type { Program, Cohort } from "@/types/sessions"
import { UserProfileModal } from "@/components/UserProfileModal"

/** A name in the grid is the one place you already know exactly who you're
 * looking at, so it should be the way through to them. Without this, seeing
 * that one student is stuck meant leaving the grid, going to Users, and
 * searching for them by name. */
function StudentNameCell({ userId, name, onOpen }: {
  userId: string; name: string; onOpen: (userId: string) => void
}) {
  return (
    <td className="px-4 py-2.5 font-medium whitespace-nowrap">
      <button
        onClick={() => onOpen(userId)}
        className="text-foreground hover:text-primary hover:underline transition-colors"
        title="Open profile"
      >
        {name}
      </button>
    </td>
  )
}

function BackButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors w-fit"
    >
      <ArrowLeft size={14} /> {label}
    </button>
  )
}

function CompletionBar({ pct }: { pct: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-1.5 rounded-full bg-muted overflow-hidden">
        <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums text-foreground">{pct}%</span>
    </div>
  )
}

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

/** Courses tab — land on every course with its enrollment/completion at a
 * glance (2026-08-14), rather than a blind "pick a course" dropdown; click
 * a row to drill into the per-student table. */
function CoursesProgressTab() {
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
  const [courseId, setCourseId] = useState<string | null>(null)
  const [programId, setProgramId] = useState("")
  const [cohortId, setCohortId] = useState("")

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ["lms-admin-courses-overview"],
    queryFn: getCoursesOverviewApi,
    enabled: courseId === null,
  })
  const { data: programs = [] } = useQuery<Program[]>({
    queryKey: ["sessions-programs"], queryFn: getProgramsApi, enabled: courseId !== null,
  })
  const { data: cohorts = [] } = useQuery<Cohort[]>({
    queryKey: ["sessions-cohorts", programId],
    queryFn: () => getCohortsApi(programId),
    enabled: courseId !== null && !!programId,
  })
  const { data: progress, isLoading } = useQuery({
    queryKey: ["lms-admin-course-progress", courseId, cohortId],
    queryFn: () => getCourseProgressApi(courseId!, cohortId || undefined),
    enabled: !!courseId,
  })

  const openCourse = (row: CourseOverviewRow) => {
    setProgramId("")
    setCohortId("")
    setCourseId(row.course_id)
  }

  if (courseId === null) {
    return (
      <div className="flex flex-col gap-4">
        {overviewLoading || !overview ? (
          <Spinner />
        ) : overview.length === 0 ? (
          <EmptyState title="No courses yet" hint="Create a course to see its progress here." />
        ) : (
          <div className="overflow-x-auto rounded-xl ring-1 ring-border">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40">
                  <th className="text-left font-medium text-muted-foreground px-4 py-2.5">Course</th>
                  <th className="text-left font-medium text-muted-foreground px-4 py-2.5">Students</th>
                  <th className="text-left font-medium text-muted-foreground px-4 py-2.5">Completion rate</th>
                </tr>
              </thead>
              <tbody>
                {overview.map((row) => (
                  <tr
                    key={row.course_id}
                    onClick={() => openCourse(row)}
                    className="border-b border-border last:border-0 hover:bg-muted/20 transition-colors cursor-pointer"
                  >
                    <td className="px-4 py-2.5 font-medium text-foreground">{row.title}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">
                      {row.completed_count}/{row.enrolled_count} completed
                    </td>
                    <td className="px-4 py-2.5"><CompletionBar pct={row.completion_pct} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <BackButton label="Courses" onClick={() => setCourseId(null)} />

      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium text-foreground">
          {overview?.find((c) => c.course_id === courseId)?.title ?? "Course"}
        </span>
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

      {isLoading || !progress ? (
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
                  <StudentNameCell userId={row.user_id} name={row.full_name} onOpen={setProfileUserId} />
                  <td className="px-4 py-2.5"><CompletionBar pct={row.pct} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {profileUserId && (
        <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />
      )}
    </div>
  )
}

/** Missions tab — same shape as Courses: land on every mission with
 * attempted/passed counts, click one to drill into its per-student table
 * (with per-phase columns for kinds that have them, e.g. Design). */
function MissionsProgressTab() {
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
  const [missionId, setMissionId] = useState<string | null>(null)

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ["lms-admin-missions-overview"],
    queryFn: getMissionsOverviewApi,
    enabled: missionId === null,
  })
  const { data: progress, isLoading } = useQuery({
    queryKey: ["lms-admin-mission-progress", missionId],
    queryFn: () => getMissionProgressApi(missionId!),
    enabled: !!missionId,
  })

  if (missionId === null) {
    return (
      <div className="flex flex-col gap-4">
        {overviewLoading || !overview ? (
          <Spinner />
        ) : overview.length === 0 ? (
          <EmptyState title="No missions yet" hint="Create a mission to see its progress here." />
        ) : (
          <div className="overflow-x-auto rounded-xl ring-1 ring-border">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40">
                  <th className="text-left font-medium text-muted-foreground px-4 py-2.5">Mission</th>
                  <th className="text-left font-medium text-muted-foreground px-4 py-2.5">Kind</th>
                  <th className="text-left font-medium text-muted-foreground px-4 py-2.5">Students</th>
                  <th className="text-left font-medium text-muted-foreground px-4 py-2.5">Pass rate</th>
                </tr>
              </thead>
              <tbody>
                {overview.map((row: MissionOverviewRow) => (
                  <tr
                    key={row.mission_id}
                    onClick={() => setMissionId(row.mission_id)}
                    className="border-b border-border last:border-0 hover:bg-muted/20 transition-colors cursor-pointer"
                  >
                    <td className="px-4 py-2.5 font-medium text-foreground">{row.title}</td>
                    <td className="px-4 py-2.5 text-muted-foreground capitalize">{row.kind}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">
                      {row.passed_count}/{row.attempted_count} passed
                    </td>
                    <td className="px-4 py-2.5"><CompletionBar pct={row.completion_pct} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <BackButton label="Missions" onClick={() => setMissionId(null)} />

      {isLoading || !progress ? (
        <Spinner />
      ) : progress.rows.length === 0 ? (
        <EmptyState title="No attempts yet" hint="Nobody has attempted this mission (solo or as a team member) yet." />
      ) : (
        <div className="overflow-x-auto rounded-xl ring-1 ring-border">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="text-left font-medium text-muted-foreground px-4 py-2.5">Student</th>
                <th className="text-left font-medium text-muted-foreground px-4 py-2.5">School</th>
                <th className="text-left font-medium text-muted-foreground px-4 py-2.5">Code</th>
                <th className="text-left font-medium text-muted-foreground px-4 py-2.5">Best attempt</th>
                {/* One column per phase. A single "in progress" badge says a
                    student is somewhere in the middle; the columns say
                    where, which is the difference between knowing someone is
                    stuck and knowing what they're stuck on. */}
                {progress.has_steps && progress.step_labels.map((step) => (
                  <th key={step.key} className="font-medium text-muted-foreground px-3 py-2.5 text-center whitespace-nowrap">
                    {step.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {progress.rows.map((row) => (
                <tr key={row.user_id} className="border-b border-border last:border-0">
                  <StudentNameCell userId={row.user_id} name={row.full_name} onOpen={setProfileUserId} />
                  <td className="px-4 py-2.5 text-muted-foreground whitespace-nowrap">
                    {row.school_name ?? "—"}
                    {row.grade && <span className="text-xs"> ({row.grade})</span>}
                  </td>
                  <td className="px-4 py-2.5 whitespace-nowrap">
                    {row.invitation_code_used
                      ? <span className="text-xs font-semibold text-primary">{row.invitation_code_used}</span>
                      : <span className="text-muted-foreground">—</span>}
                  </td>
                  <td className="px-4 py-2.5 whitespace-nowrap">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium ${MISSION_STATUS_STYLE[row.status]}`}>
                      {MISSION_STATUS_LABEL[row.status]}
                      {row.score !== null && <span className="opacity-70">· {row.score}%</span>}
                    </span>
                    {row.started_at && (
                      <span className="block text-[10px] text-muted-foreground mt-0.5">
                        {new Date(row.started_at).toLocaleDateString()}
                      </span>
                    )}
                  </td>
                  {progress.has_steps && progress.step_labels.map((step) => (
                    <td key={step.key} className="px-3 py-2.5 text-center">
                      <span
                        title={`${step.label}: ${row.steps?.[step.key] ? "done" : "not started"}`}
                        className={`inline-block size-2.5 rounded-full ${
                          row.steps?.[step.key] ? "bg-emerald-500" : "bg-muted-foreground/25"}`}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {profileUserId && (
        <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />
      )}
    </div>
  )
}

/** Progress views (2026-08-12, redesigned 2026-08-14) — each tab now lands
 * on an overview of every course/mission with its enrollment/completion
 * counts, and drills into the same all-students single-item table as
 * before on click. The old `getProgressGridApi`/cohort-first grid (7B-1)
 * still backs `/lms/admin/progress-grid` for anything that needs the
 * combined matrix, but this page no longer renders it. */
export default function LmsProgressGrid() {
  const [tab, setTab] = useState<"courses" | "missions">("courses")

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Progress"
        subtitle="See every course and mission's completion at a glance, then drill into any one of them."
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
