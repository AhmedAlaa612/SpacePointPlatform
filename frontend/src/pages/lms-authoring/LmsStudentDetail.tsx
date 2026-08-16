import { useState } from "react"
import { isAxiosError } from "axios"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "@tanstack/react-router"
import { ArrowLeft, ChevronDown, Plus, X } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import {
  getStudentProfileApi, listUserEnrollmentsApi, grantCourseEnrollmentApi, revokeCourseEnrollmentApi,
  getStudentDesignRunsApi, type StudentDesignRun,
} from "@/api/lms_admin"
import { ItemPicker } from "@/pages/lms-authoring/components/ItemPicker"
import { AVATAR_PRESETS } from "@/components/games/avatarPresets"
import { updateUserApi } from "@/api/admin/users"

/** Student profile (2026-08-12) — nickname, programs attended, and the
 * courses they're currently on, with assign/remove in one place. This is
 * the reverse direction of `AssignPanel` (course/mission fixed, staff
 * picked) — here the student is fixed and the course is picked, so it's a
 * small dedicated section rather than forcing `AssignPanel` to be
 * bidirectional. */
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

export default function LmsStudentDetail() {
  const { userId } = useParams({ strict: false }) as { userId: string }
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [courseId, setCourseId] = useState("")
  const [nickname, setNickname] = useState<string | null>(null)
  const [identityError, setIdentityError] = useState("")
  const [expandedRuns, setExpandedRuns] = useState<Record<string, boolean>>({})

  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ["lms-admin-student-profile", userId],
    queryFn: () => getStudentProfileApi(userId),
  })
  const { data: enrollments = [], isLoading: enrollmentsLoading } = useQuery({
    queryKey: ["lms-admin-user-enrollments", userId],
    queryFn: () => listUserEnrollmentsApi(userId),
  })
  const { data: designRuns, isLoading: designRunsLoading } = useQuery({
    queryKey: ["lms-admin-student-design-runs", userId],
    queryFn: () => getStudentDesignRunsApi(userId),
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
          <EmptyState title="Not enrolled in any course" hint="Assign one below." />
        ) : (
          <div className="flex flex-col gap-2">
            {activeEnrollments.map((e) => (
              <div key={e.id} className="flex items-center justify-between p-3 bg-background border border-border rounded-xl">
                <span className="text-sm text-foreground">
                  {e.course_title ?? "Untitled course"}
                  <span className="ml-2 text-xs text-muted-foreground uppercase tracking-wide">{e.source}</span>
                </span>
                <button
                  onClick={() => revokeMutation.mutate(e.id)}
                  disabled={revokeMutation.isPending}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                  title="Remove access"
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        )}

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
                  {expanded && (
                    <div className="px-3 pb-3 border-t border-border pt-3 flex flex-col gap-3">
                      {run.design_objective && (
                        <p className="text-xs text-muted-foreground whitespace-pre-line">{run.design_objective}</p>
                      )}
                      {designRuns.step_labels.length > 0 && (
                        <div className="flex flex-wrap gap-3">
                          {designRuns.step_labels.map((step) => (
                            <div key={step.key} className="flex items-center gap-1.5">
                              <span
                                title={`${step.label}: ${run.steps?.[step.key] ? "done" : "not started"}`}
                                className={`inline-block size-2.5 rounded-full ${
                                  run.steps?.[step.key] ? "bg-emerald-500" : "bg-muted-foreground/25"}`}
                              />
                              <span className="text-xs text-muted-foreground">{step.label}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
