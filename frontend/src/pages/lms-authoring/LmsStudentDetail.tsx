import { useState } from "react"
import { isAxiosError } from "axios"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "@tanstack/react-router"
import { ArrowLeft, ChevronDown, Plus, X } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { useAuth } from "@/context/AuthContext"
import {
  getStudentProfileApi, listUserEnrollmentsApi, grantCourseEnrollmentApi, revokeCourseEnrollmentApi,
  getStudentDesignRunsApi, type StudentDesignRun,
  getStudentProfileInstructorApi, listUserEnrollmentsInstructorApi, getStudentDesignRunsInstructorApi,
  getStudentCourseProgressApi,
} from "@/api/lms_admin"
import { attemptDesignDetailApi } from "@/api/missionsInstructor"
import { ItemPicker } from "@/pages/lms-authoring/components/ItemPicker"
import { AVATAR_PRESETS } from "@/components/games/avatarPresets"
import { updateUserApi } from "@/api/admin/users"

/** Student profile (2026-08-12) — nickname, programs attended, and the
 * courses they're currently on, with assign/remove in one place. This is
 * the reverse direction of `AssignPanel` (course/mission fixed, staff
 * picked) — here the student is fixed and the course is picked, so it's a
 * small dedicated section rather than forcing `AssignPanel` to be
 * bidirectional.
 *
 * Instructor access (2026-08-22, Programs/Cohort Missions merge) — reads
 * everything the same as ops, scoped server-side to their own cohorts'
 * students; identity edits and course assign/revoke stay ops-only (those
 * hit `/admin/users` and `/lms/admin/courses/{id}/enrollments`, neither
 * widened for this), so those controls are hidden rather than disabled. */
const RUN_STATUS_STYLE: Record<StudentDesignRun["status"], string> = {
  passed: "bg-emerald-500/10 text-emerald-500",
  failed: "bg-red-500/10 text-red-500",
  submitted: "bg-amber-500/10 text-amber-600",
  in_progress: "bg-primary/10 text-primary",
  abandoned: "bg-muted text-muted-foreground",
}

const RUN_STATUS_LABEL: Record<StudentDesignRun["status"], string> = {
  passed: "Passed", failed: "Failed", submitted: "Submitted",
  in_progress: "In progress", abandoned: "Abandoned",
}

const MARGIN_TONE: Record<string, string> = {
  good: "ring-emerald-500/30 bg-emerald-500/5",
  tight: "ring-amber-500/30 bg-amber-500/5",
  fail: "ring-destructive/30 bg-destructive/5",
  incomplete: "ring-border",
}

export default function LmsStudentDetail() {
  const { userId } = useParams({ strict: false }) as { userId: string }
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { currentUser } = useAuth()
  const isStaff = currentUser?.role !== "instructor"
  const [courseId, setCourseId] = useState("")
  const [nickname, setNickname] = useState<string | null>(null)
  const [identityError, setIdentityError] = useState("")
  const [expandedRuns, setExpandedRuns] = useState<Record<string, boolean>>({})

  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ["lms-admin-student-profile", userId],
    queryFn: () => (isStaff ? getStudentProfileApi(userId) : getStudentProfileInstructorApi(userId)),
  })
  const { data: enrollments = [], isLoading: enrollmentsLoading } = useQuery({
    queryKey: ["lms-admin-user-enrollments", userId],
    queryFn: () => (isStaff ? listUserEnrollmentsApi(userId) : listUserEnrollmentsInstructorApi(userId)),
  })
  const { data: designRuns, isLoading: designRunsLoading } = useQuery({
    queryKey: ["lms-admin-student-design-runs", userId],
    queryFn: () => (isStaff ? getStudentDesignRunsApi(userId) : getStudentDesignRunsInstructorApi(userId)),
  })

  const invalidateEnrollments = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-user-enrollments", userId] })

  const enrollMutation = useMutation({
    mutationFn: (course_id: string) => grantCourseEnrollmentApi(course_id, userId),
    onSuccess: () => { setCourseId(""); invalidateEnrollments() },
  })
  const revokeMutation = useMutation({
    mutationFn: (enrollmentId: string) => revokeCourseEnrollmentApi(enrollmentId),
    onSuccess: invalidateEnrollments,
  })

  // Nickname and avatar are what a student is called in front of a class,
  // and until now only the student could change either — from inside a game
  // lobby. A generated callsign occasionally lands somewhere unusable, and
  // "ask them to open a lobby and fix it themselves" is not a moderation
  // tool.
  const saveIdentity = useMutation({
    mutationFn: (patch: { nickname?: string; avatar?: string }) => updateUserApi(userId, patch),
    onSuccess: () => {
      setIdentityError("")
      setNickname(null)
      void queryClient.invalidateQueries({ queryKey: ["lms-admin-student-profile", userId] })
      void queryClient.invalidateQueries({ queryKey: ["lms-admin-students"] })
    },
    onError: (err) => setIdentityError(
      (isAxiosError(err) && typeof err.response?.data?.detail === "string")
        ? err.response.data.detail
        : "Couldn't save that.",
    ),
  })

  if (profileLoading || !profile) return <Spinner />

  const activeEnrollments = enrollments.filter((e) => e.status === "active")

  return (
    <div className="flex flex-col gap-6">
      <button
        // `/students` declares a validateSearch (?invite_code=), so TanStack
        // requires the search object here with every key present.
        // undefined = back to the unfiltered list.
        onClick={() => void navigate({ to: "/lms-authoring/students", search: { invite_code: undefined } })}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors w-fit"
      >
        <ArrowLeft size={14} /> Students
      </button>

      <PageHeader
        title={profile.full_name}
        subtitle={profile.email}
        action={profile.nickname ? (
          <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-primary/10 text-primary">{profile.nickname}</span>
        ) : undefined}
      />

      {isStaff && (
        <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl">
          <div>
            <h3 className="text-sm font-medium text-foreground">Game identity</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              What this student is called on a leaderboard. Their real name stays a staff-only
              reveal either way.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1.5">
              <label className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Nickname</label>
              <input
                value={nickname ?? profile.nickname ?? ""}
                onChange={(e) => setNickname(e.target.value)}
                placeholder="SpaceOtter77"
                className="h-9 px-3 w-56 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </div>
            <button
              onClick={() => saveIdentity.mutate({ nickname: (nickname ?? "").trim() })}
              disabled={saveIdentity.isPending || nickname === null || !nickname.trim()}
              className="h-9 px-4 rounded-xl text-sm font-medium bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-40"
            >
              Save nickname
            </button>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Avatar</label>
            <div className="flex flex-wrap gap-1.5">
              {AVATAR_PRESETS.map((preset) => {
                const Icon = preset.icon
                const active = profile.avatar === preset.key
                return (
                  <button
                    key={preset.key}
                    onClick={() => saveIdentity.mutate({ avatar: preset.key })}
                    disabled={saveIdentity.isPending}
                    title={preset.label}
                    className={`size-10 rounded-xl border flex items-center justify-center transition-colors disabled:opacity-50 ${
                      active
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border text-muted-foreground hover:bg-muted"}`}
                  >
                    <Icon size={16} />
                  </button>
                )
              })}
            </div>
          </div>
          {identityError && <p className="text-xs text-destructive">{identityError}</p>}
        </div>
      )}

      <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl">
        <h3 className="text-sm font-medium text-foreground">Programs attended</h3>
        {profile.programs.length === 0 ? (
          <EmptyState title="No programs yet" hint="This student has no active or past registrations." />
        ) : (
          <div className="flex flex-col gap-2">
            {profile.programs.map((p) => (
              <div key={p.registration_id} className="flex items-center justify-between p-3 bg-background border border-border rounded-xl">
                <div>
                  <p className="text-sm text-foreground">{p.program_name}</p>
                  <p className="text-xs text-muted-foreground">{p.cohort_name}</p>
                </div>
                {p.starts_on && (
                  <span className="text-xs text-muted-foreground shrink-0">
                    {p.starts_on}{p.ends_on ? ` – ${p.ends_on}` : ""}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl">
        <h3 className="text-sm font-medium text-foreground">Courses</h3>

        {enrollmentsLoading ? (
          <Spinner />
        ) : activeEnrollments.length === 0 ? (
          <EmptyState title="Not enrolled in any course" hint={isStaff ? "Assign one below." : undefined} />
        ) : (
          <div className="flex flex-col gap-2">
            {activeEnrollments.map((e) => (
              <CourseProgressRow key={e.id} userId={userId} courseId={e.course_id} title={e.course_title} source={e.source} isStaff={isStaff}
                onRevoke={isStaff ? () => revokeMutation.mutate(e.id) : undefined} revokePending={revokeMutation.isPending}
              />
            ))}
          </div>
        )}

        {isStaff && (
          <div className="flex items-center gap-2 pt-1 border-t border-border">
            <ItemPicker type="course" value={courseId} onChange={setCourseId} />
            <button
              onClick={() => courseId && enrollMutation.mutate(courseId)}
              disabled={!courseId || enrollMutation.isPending}
              className="flex items-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors disabled:opacity-50"
            >
              <Plus size={14} /> Assign
            </button>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl">
        <h3 className="text-sm font-medium text-foreground">Mission runs</h3>

        {designRunsLoading ? (
          <Spinner />
        ) : !designRuns || designRuns.runs.length === 0 ? (
          <EmptyState title="No design mission runs yet" hint="This student hasn't started a design mission." />
        ) : (
          <div className="flex flex-col gap-2">
            {designRuns.runs.map((run) => {
              const expanded = !!expandedRuns[run.attempt_id]
              return (
                <div key={run.attempt_id} className="bg-background border border-border rounded-xl overflow-hidden">
                  <button
                    onClick={() => setExpandedRuns((prev) => ({ ...prev, [run.attempt_id]: !prev[run.attempt_id] }))}
                    className="w-full flex items-center justify-between p-3 text-left"
                  >
                    <div className="min-w-0">
                      <p className="text-sm text-foreground truncate">{run.design_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {run.variant_label}
                        {run.started_at && <> · {new Date(run.started_at).toLocaleDateString()}</>}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${RUN_STATUS_STYLE[run.status]}`}>
                        {RUN_STATUS_LABEL[run.status]}
                      </span>
                      <ChevronDown size={14} className={`text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`} />
                    </div>
                  </button>
                  {expanded && <DesignRunDetail attemptId={run.attempt_id} />}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

/** Real "what did they name it and what did they select" detail (operator
 * ask, 2026-08-22) — replaces the old step-dots-only expand with the same
 * component/margin data `attemptDesignDetailApi` already builds for the
 * student's own view (`/missions/instructor/attempts/{id}/design-detail`,
 * reachable by ops too — see that endpoint's docstring). */
function DesignRunDetail({ attemptId }: { attemptId: string }) {
  const { data: detail, isLoading, error } = useQuery({
    queryKey: ["lms-admin-design-run-detail", attemptId],
    queryFn: () => attemptDesignDetailApi(attemptId),
  })

  if (isLoading) return <div className="px-3 pb-3"><Spinner /></div>
  if (error || !detail) {
    return <p className="px-3 pb-3 text-xs text-muted-foreground">Couldn't load this run's detail.</p>
  }

  return (
    <div className="px-3 pb-3 border-t border-border pt-3 flex flex-col gap-4">
      {detail.design_objective && (
        <p className="text-xs text-muted-foreground whitespace-pre-line">{detail.design_objective}</p>
      )}

      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
        <span>CubeSat: {detail.selected_cubesat_size}</span>
        {detail.orbit_type && <span>Orbit: {detail.orbit_type}</span>}
        {detail.orbit_duration_min != null && <span>{detail.orbit_duration_min} min/orbit</span>}
        {detail.orbits_per_day != null && <span>{detail.orbits_per_day} orbits/day</span>}
      </div>

      {detail.components.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                <th className="text-left font-medium py-1.5 pr-3">Component</th>
                <th className="text-left font-medium py-1.5 pr-3">Subsystem</th>
                <th className="text-right font-medium py-1.5 pr-3">Qty</th>
                <th className="text-right font-medium py-1.5 pr-3">Mass (g)</th>
                <th className="text-right font-medium py-1.5 pr-3">V / mA</th>
                <th className="text-right font-medium py-1.5">Cost (AED)</th>
              </tr>
            </thead>
            <tbody>
              {detail.components.map((c) => (
                <tr key={c.id} className="border-b border-border/50 last:border-0">
                  <td className="py-1.5 pr-3 text-foreground">{c.component_name}</td>
                  <td className="py-1.5 pr-3 text-muted-foreground">{c.subsystem}</td>
                  <td className="py-1.5 pr-3 text-right text-foreground">{c.quantity}</td>
                  <td className="py-1.5 pr-3 text-right text-foreground">{c.mass_per_unit_g ?? "—"}</td>
                  <td className="py-1.5 pr-3 text-right text-foreground">
                    {c.voltage_v ?? "—"} / {c.current_ma ?? "—"}
                  </td>
                  <td className="py-1.5 text-right text-foreground">{c.cost_per_unit_aed ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {detail.dashboard.margins.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {detail.dashboard.margins.map((m) => (
            <div key={m.key} title={m.interpretation} className={`rounded-lg ring-1 px-2.5 py-1.5 text-xs ${MARGIN_TONE[m.status] ?? "ring-border"}`}>
              <span className="font-medium text-foreground">{m.label}</span>
              <span className="text-muted-foreground ml-1.5">{m.value.toFixed(1)} {m.unit}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function CourseProgressRow({
  userId, courseId, title, source, isStaff, onRevoke, revokePending,
}: {
  userId: string; courseId: string; title: string | null; source: string; isStaff: boolean
  onRevoke?: () => void; revokePending: boolean
}) {
  const [open, setOpen] = useState(false)

  return (
    <div className="bg-background border border-border rounded-xl overflow-hidden">
      <div className="flex items-center justify-between p-3">
        <button onClick={() => setOpen((v) => !v)} className="flex items-center gap-2 min-w-0 flex-1 text-left cursor-pointer">
          <ChevronDown size={13} className={`shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
          <span className="text-sm text-foreground truncate">
            {title ?? "Untitled course"}
            <span className="ml-2 text-xs text-muted-foreground uppercase tracking-wide">{source}</span>
          </span>
        </button>
        {isStaff && onRevoke && (
          <button
            onClick={onRevoke}
            disabled={revokePending}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors disabled:opacity-50 shrink-0"
            title="Remove access"
          >
            <X size={14} />
          </button>
        )}
      </div>
      {open && <CourseProgressDetail userId={userId} courseId={courseId} isStaff={isStaff} />}
    </div>
  )
}

function CourseProgressDetail({ userId, courseId, isStaff }: { userId: string; courseId: string; isStaff: boolean }) {
  const { data: progress, isLoading } = useQuery({
    queryKey: ["lms-admin-student-course-progress", userId, courseId, isStaff],
    queryFn: () => getStudentCourseProgressApi(userId, courseId, isStaff ? "admin" : "instructor"),
  })

  if (isLoading) return <div className="px-3 pb-3"><Spinner /></div>
  if (!progress) return null

  return (
    <div className="px-3 pb-3 border-t border-border pt-2 flex flex-col gap-1.5">
      {progress.modules.length === 0 ? (
        <p className="text-xs text-muted-foreground">No modules on this course.</p>
      ) : progress.modules.map((m) => (
        <div key={m.module_id} className="flex items-center gap-2 text-xs">
          <span className={`w-2 h-2 rounded-full shrink-0 ${m.mandatory_completed >= m.mandatory_total && m.mandatory_total > 0 ? "bg-emerald-500" : "bg-muted-foreground/30"}`} />
          <span className="flex-1 text-foreground truncate">{m.title ?? "Untitled module"}</span>
          <span className="text-muted-foreground shrink-0">{m.mandatory_completed}/{m.mandatory_total}</span>
          {m.locked && <span className="text-muted-foreground shrink-0">locked</span>}
        </div>
      ))}
    </div>
  )
}
