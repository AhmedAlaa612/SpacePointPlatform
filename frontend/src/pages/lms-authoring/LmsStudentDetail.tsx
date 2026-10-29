import { useState } from "react"
import { isAxiosError } from "axios"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams, useSearch } from "@tanstack/react-router"
import { ArrowLeft, ChevronDown, Copy, Check, ExternalLink, Plus, X } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { ConfirmDialog } from "@/pages/admin/components/common"
import { useAuth } from "@/context/AuthContext"
import { useToast } from "@/components/ui/toast"
import {
  getStudentProfileApi, listUserEnrollmentsApi, grantCourseEnrollmentApi, revokeCourseEnrollmentApi,
  listLearningPathsApi, grantLearningPathEnrollmentApi,
  getStudentDesignRunsApi, type StudentDesignRun,
  getStudentProfileInstructorApi, listUserEnrollmentsInstructorApi, getStudentDesignRunsInstructorApi,
  getStudentCourseProgressApi, getStudentQuizBreakdownApi, getStudentQuizBreakdownInstructorApi,
  getAssignmentItemsApi,
  updateStudentAccountApi, getStudentPasswordLinkApi,
  enrollStudentCohortApi, unenrollStudentCohortApi,
  getStudentTeamsApi, getStudentCertificatesApi, type StudentTeam,
} from "@/api/lms_admin"
import { getCohortsApi } from "@/api/sessions/cohorts"
import { getCohortTeamAnalyticsApi } from "@/api/competitions"
import { TeamAnalysisCard } from "@/pages/admin/components/CompetitionAnalysis"
import { DesignRunDetail } from "@/pages/lms-authoring/components/DesignRunDetail"
import { ItemPicker } from "@/pages/lms-authoring/components/ItemPicker"
import { AssignmentItemRow } from "@/pages/lms-authoring/components/LmsProgressAndMissions"

/** Student manage page (2026-08-12, operations revamp 2026-10) — account,
 * programs & cohorts (with live checklist, team, enroll/unenroll), learner
 * teams, certificates, courses, mission runs, quiz topics. This is the
 * reverse direction of `AssignPanel` (course fixed, staff picked) — here
 * the student is fixed and the course/cohort is picked.
 *
 * Instructor access (2026-08-22) — reads everything the same as ops,
 * scoped server-side; identity edits and course assign/revoke stay
 * ops-only, so those controls are hidden rather than disabled. */
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
  const search = useSearch({ strict: false }) as {
    invite_code?: string
    from?: string
  }
  const queryClient = useQueryClient()
  const { currentUser } = useAuth()
  const toast = useToast()
  const isStaff = currentUser?.role !== "instructor"
  const [courseId, setCourseId] = useState("")
  const [assignType, setAssignType] = useState<"course" | "path">("course")
  const [pathId, setPathId] = useState("")
  const [expandedRuns, setExpandedRuns] = useState<Record<string, boolean>>({})

  // Account management state
  const [emailVal, setEmailVal] = useState<string | null>(null)
  const [fullNameVal, setFullNameVal] = useState<string | null>(null)
  const [accountError, setAccountError] = useState("")
  const [passwordLink, setPasswordLink] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [passwordError, setPasswordError] = useState("")

  // Programs & cohorts state
  const [expandedCohortId, setExpandedCohortId] = useState<string | null>(null)
  const [unenrollTarget, setUnenrollTarget] = useState<{ cohortId: string; cohortName: string } | null>(null)
  const [unenrollError, setUnenrollError] = useState<string | null>(null)
  const [enrollCohortId, setEnrollCohortId] = useState("")
  const [enrollError, setEnrollError] = useState("")

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
  const { data: quizBreakdown, isLoading: quizBreakdownLoading } = useQuery({
    queryKey: ["lms-admin-student-quiz-breakdown", userId],
    queryFn: () => (isStaff ? getStudentQuizBreakdownApi(userId) : getStudentQuizBreakdownInstructorApi(userId)),
  })
  const { data: teams = [], isLoading: teamsLoading } = useQuery({
    queryKey: ["lms-admin-student-teams", userId],
    queryFn: () => getStudentTeamsApi(userId),
    enabled: isStaff,
  })
  const { data: certificates = [], isLoading: certsLoading } = useQuery({
    queryKey: ["lms-admin-student-certificates", userId],
    queryFn: () => getStudentCertificatesApi(userId),
    enabled: isStaff,
  })
  const { data: cohorts = [] } = useQuery({
    queryKey: ["sessions-cohorts-all"],
    queryFn: () => getCohortsApi(),
    enabled: isStaff,
  })
  const { data: paths = [] } = useQuery({
    queryKey: ["lms-admin-learning-paths"],
    queryFn: listLearningPathsApi,
    enabled: isStaff,
  })

  const invalidateProfile = () => {
    void queryClient.invalidateQueries({ queryKey: ["lms-admin-student-profile", userId] })
    void queryClient.invalidateQueries({ queryKey: ["lms-admin-students"] })
    void queryClient.invalidateQueries({ queryKey: ["lms-admin-student-teams", userId] })
  }
  const invalidateEnrollments = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-user-enrollments", userId] })

  const enrollMutation = useMutation({
    mutationFn: (course_id: string) => grantCourseEnrollmentApi(course_id, userId),
    onSuccess: () => {
      setCourseId("")
      invalidateEnrollments()
      toast.success("Course assigned successfully")
    },
    onError: (err) => toast.error(
      (isAxiosError(err) && typeof err.response?.data?.detail === "string")
        ? err.response.data.detail
        : "Couldn't assign that course.",
    ),
  })
  const pathEnrollMutation = useMutation({
    mutationFn: (id: string) => grantLearningPathEnrollmentApi(id, userId),
    onSuccess: () => {
      setPathId("")
      invalidateEnrollments()
      toast.success("Learning path courses assigned successfully")
    },
    onError: (err) => toast.error(
      (isAxiosError(err) && typeof err.response?.data?.detail === "string")
        ? err.response.data.detail
        : "Couldn't assign that learning path.",
    ),
  })
  const revokeMutation = useMutation({
    mutationFn: (enrollmentId: string) => revokeCourseEnrollmentApi(enrollmentId),
    onSuccess: invalidateEnrollments,
  })

  const accountMutation = useMutation({
    mutationFn: () => updateStudentAccountApi(userId, {
      email: (emailVal ?? profile?.email ?? "").trim(),
      full_name: (fullNameVal ?? profile?.full_name ?? "").trim() || undefined,
    }),
    onSuccess: () => {
      setAccountError("")
      setEmailVal(null)
      setFullNameVal(null)
      invalidateProfile()
    },
    onError: (err) => setAccountError(
      (isAxiosError(err) && typeof err.response?.data?.detail === "string")
        ? err.response.data.detail
        : "Couldn't save that.",
    ),
  })

  const passwordLinkMutation = useMutation({
    mutationFn: () => getStudentPasswordLinkApi(userId),
    onSuccess: (data) => {
      setPasswordError("")
      setPasswordLink(data.link)
      setCopied(false)
    },
    onError: (err) => setPasswordError(
      (isAxiosError(err) && typeof err.response?.data?.detail === "string")
        ? err.response.data.detail
        : "Couldn't generate a link.",
    ),
  })

  const enrollCohortMutation = useMutation({
    mutationFn: () => enrollStudentCohortApi(userId, enrollCohortId),
    onSuccess: () => {
      setEnrollError("")
      setEnrollCohortId("")
      setExpandedCohortId(null)
      invalidateProfile()
    },
    onError: (err) => setEnrollError(
      (isAxiosError(err) && typeof err.response?.data?.detail === "string")
        ? err.response.data.detail
        : "Couldn't enroll into that cohort.",
    ),
  })

  const unenrollMutation = useMutation({
    mutationFn: (cohortId: string) => unenrollStudentCohortApi(userId, cohortId),
    onSuccess: () => {
      setUnenrollError(null)
      setUnenrollTarget(null)
      setExpandedCohortId(null)
      invalidateProfile()
    },
    onError: (err) => setUnenrollError(
      (isAxiosError(err) && typeof err.response?.data?.detail === "string")
        ? err.response.data.detail
        : "Couldn't unenroll from that cohort.",
    ),
  })

  if (profileLoading || !profile) return <Spinner />

  const activeEnrollments = enrollments.filter((e) => e.status === "active")
  const enrolledCohortIds = new Set(profile.programs.map((p) => p.cohort_id))
  const availableCohorts = cohorts.filter((c) => !enrolledCohortIds.has(c.id))

  return (
    <div className="flex flex-col gap-6">
      <button
        onClick={() => {
          if (search.from) {
            const [path, queryString] = search.from.split("?")
            const queryParams = queryString
              ? Object.fromEntries(new URLSearchParams(queryString).entries())
              : {}
            void navigate({
              to: path as any,
              search: queryParams as never,
            })
          } else if (window.history.length > 1) {
            window.history.back()
          } else if (isStaff) {
            void navigate({ to: "/lms-authoring/students", search: { invite_code: undefined } })
          } else {
            void navigate({ to: "/lms-authoring/curriculum", search: {} as never })
          }
        }}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors w-fit cursor-pointer"
      >
        <ArrowLeft size={14} /> {search.from?.includes("curriculum") ? "Programs" : isStaff ? (profile.is_observer ? "Observers" : "Students") : "Programs"}
      </button>

      <PageHeader
        title={profile.full_name}
        subtitle={profile.email}
        action={
          <div className="flex items-center gap-2">
            {profile.is_observer && (
              <span className="text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded-full bg-violet-500/15 text-violet-500 border border-violet-500/30">
                Observer
              </span>
            )}
            {profile.nickname && (
              <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-primary/10 text-primary">{profile.nickname}</span>
            )}
          </div>
        }
      />

      {isStaff && (
        <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl">
          <div>
            <h3 className="text-sm font-medium text-foreground">Account management</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Correct the login email (duplicate-checked, synced to the linked contact) or hand them a password-set link.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1.5">
              <label className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Full name</label>
              <input
                value={fullNameVal ?? profile.full_name ?? ""}
                onChange={(e) => setFullNameVal(e.target.value)}
                placeholder="Full name"
                className="h-9 px-3 w-56 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Email</label>
              <input
                value={emailVal ?? profile.email ?? ""}
                onChange={(e) => setEmailVal(e.target.value)}
                placeholder="student@example.com"
                className="h-9 px-3 w-64 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </div>
            <button
              onClick={() => accountMutation.mutate()}
              disabled={accountMutation.isPending || (emailVal === null && fullNameVal === null)}
              className="h-9 px-4 rounded-xl text-sm font-medium bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-40"
            >
              Save account
            </button>
            <button
              onClick={() => passwordLinkMutation.mutate()}
              disabled={passwordLinkMutation.isPending}
              className="h-9 px-4 rounded-xl text-sm font-medium border border-border hover:bg-muted transition-colors disabled:opacity-50"
            >
              Get password link
            </button>
          </div>
          {accountError && <p className="text-xs text-destructive">{accountError}</p>}
          {passwordError && <p className="text-xs text-destructive">{passwordError}</p>}
          {passwordLink && (
            <div className="flex items-center gap-2 p-2.5 bg-background border border-border rounded-xl">
              <span className="flex-1 text-xs text-muted-foreground truncate font-mono">{passwordLink}</span>
              <button
                onClick={() => {
                  void navigator.clipboard.writeText(passwordLink).then(() => setCopied(true))
                }}
                className="flex items-center gap-1 h-8 px-3 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:opacity-90 transition-opacity shrink-0"
              >
                {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? "Copied" : "Copy"}
              </button>
            </div>
          )}
        </div>
      )}

      <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl">
        <h3 className="text-sm font-medium text-foreground">Programs & cohorts</h3>
        {profile.programs.length === 0 ? (
          <EmptyState title="No programs yet" hint="This learner has no active registrations or checklist assignments." />
        ) : (
          <div className="flex flex-col gap-2">
            {profile.programs.map((p) => {
              const expanded = expandedCohortId === p.cohort_id
              const isObserver = (p.mode ?? "").toLowerCase() === "observer"
              return (
                <div key={p.cohort_id} className="bg-background border border-border rounded-xl overflow-hidden">
                  <div className="flex items-center justify-between gap-2 p-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <p className="text-sm text-foreground font-medium">{p.program_name}</p>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${isObserver ? "bg-violet-500/10 text-violet-500" : "bg-emerald-500/10 text-emerald-500"}`}>
                          {isObserver ? "OBSERVER" : "STUDENT"}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground">{p.cohort_name}
                        {p.starts_on && <> · {p.starts_on}{p.ends_on ? ` – ${p.ends_on}` : ""}</>}
                      </p>
                      {p.team_name && (
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Team: <span className="font-semibold text-foreground">{p.team_name}</span>
                          {p.team_join_code && <> <span className="font-mono">(Code: {p.team_join_code})</span></>}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {p.assignment_id && (
                        <button
                          onClick={() => setExpandedCohortId(expanded ? null : p.cohort_id)}
                          className="flex items-center gap-1 h-8 px-2.5 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                          title={expanded ? "Hide checklist progress" : "Show checklist progress"}
                        >
                          <ChevronDown size={14} className={`transition-transform ${expanded ? "rotate-180" : ""}`} />
                          Checklist
                        </button>
                      )}
                      {isStaff && (
                        <button
                          onClick={() => { setUnenrollError(null); setUnenrollTarget({ cohortId: p.cohort_id, cohortName: p.cohort_name }) }}
                          className="h-8 px-2.5 rounded-lg text-xs font-medium text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors cursor-pointer"
                          title="Unenroll from cohort"
                        >
                          Unenroll
                        </button>
                      )}
                    </div>
                  </div>
                  {expanded && p.assignment_id && (
                    <CohortChecklistDetail cohortId={p.cohort_id} assignmentId={p.assignment_id} />
                  )}
                  {expanded && !p.assignment_id && (
                    <p className="px-3 pb-3 text-xs text-muted-foreground italic">No checklist assigned for this cohort yet.</p>
                  )}
                </div>
              )
            })}
          </div>
        )}
        {isStaff && (
          <div className="flex items-center gap-2 pt-2 border-t border-border">
            <select
              value={enrollCohortId}
              onChange={(e) => setEnrollCohortId(e.target.value)}
              className="h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer min-w-[220px] flex-1"
            >
              <option value="">Pick a cohort to enroll…</option>
              {availableCohorts.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            <button
              onClick={() => enrollCohortId && enrollCohortMutation.mutate()}
              disabled={!enrollCohortId || enrollCohortMutation.isPending}
              className="flex items-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors disabled:opacity-50 shrink-0"
            >
              <Plus size={14} /> Enroll in cohort
            </button>
          </div>
        )}
        {enrollError && <p className="text-xs text-destructive">{enrollError}</p>}
      </div>

      {isStaff && (
        <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl">
          <h3 className="text-sm font-medium text-foreground">Learner teams</h3>
          {teamsLoading ? (
            <Spinner />
          ) : teams.length === 0 ? (
            <EmptyState title="No teams yet" hint="This learner hasn't joined any team." />
          ) : (
            <div className="flex flex-col gap-2">
              {teams.map((t) => (
                <LearnerTeamCard key={t.team_id} team={t} />
              ))}
            </div>
          )}
        </div>
      )}

      {isStaff && (
        <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl">
          <h3 className="text-sm font-medium text-foreground">Certificates</h3>
          {certsLoading ? (
            <Spinner />
          ) : certificates.length === 0 ? (
            <EmptyState title="No certificates earned yet" hint="Course, path, and program certificates will appear here." />
          ) : (
            <div className="flex flex-col gap-2">
              {certificates.map((c) => (
                <div key={c.id} className="flex items-center justify-between gap-2 p-3 bg-background border border-border rounded-xl">
                  <div className="min-w-0">
                    <p className="text-sm text-foreground font-medium truncate">{c.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {c.type}{c.generated_at ? <> · {new Date(c.generated_at).toLocaleDateString()}</> : null}
                    </p>
                  </div>
                  {c.url ? (
                    <a
                      href={c.url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-1 h-8 px-3 rounded-lg text-xs font-medium text-primary hover:bg-primary/10 transition-colors shrink-0"
                    >
                      <ExternalLink size={13} /> View / Download
                    </a>
                  ) : (
                    <span className="text-xs text-muted-foreground italic shrink-0">No file</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl">
        <h3 className="text-sm font-medium text-foreground">Courses & learning paths</h3>

        {enrollmentsLoading ? (
          <Spinner />
        ) : activeEnrollments.length === 0 ? (
          <EmptyState title="Not enrolled in any course" hint={isStaff ? "Assign a course or learning path below." : undefined} />
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
          <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-border">
            <div className="inline-flex rounded-xl bg-muted p-0.5 text-xs font-medium shrink-0">
              <button
                type="button"
                onClick={() => { setAssignType("course"); setPathId("") }}
                className={`px-3 py-1.5 rounded-lg transition-colors cursor-pointer ${
                  assignType === "course"
                    ? "bg-background text-foreground shadow-2xs font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Course
              </button>
              <button
                type="button"
                onClick={() => { setAssignType("path"); setCourseId("") }}
                className={`px-3 py-1.5 rounded-lg transition-colors cursor-pointer ${
                  assignType === "path"
                    ? "bg-background text-foreground shadow-2xs font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Learning path
              </button>
            </div>

            {assignType === "course" ? (
              <ItemPicker type="course" value={courseId} onChange={setCourseId} />
            ) : (
              <select
                value={pathId}
                onChange={(e) => setPathId(e.target.value)}
                className="h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer min-w-[220px] flex-1"
              >
                <option value="">Select a learning path…</option>
                {paths.map((p) => (
                  <option key={p.id} value={p.id}>{p.title}</option>
                ))}
              </select>
            )}

            <button
              onClick={() => {
                if (assignType === "course" && courseId) {
                  enrollMutation.mutate(courseId)
                } else if (assignType === "path" && pathId) {
                  pathEnrollMutation.mutate(pathId)
                }
              }}
              disabled={
                (assignType === "course" && (!courseId || enrollMutation.isPending)) ||
                (assignType === "path" && (!pathId || pathEnrollMutation.isPending))
              }
              className="flex items-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors disabled:opacity-50 shrink-0 cursor-pointer"
            >
              <Plus size={14} /> Assign {assignType === "course" ? "course" : "learning path"}
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

      <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl">
        <h3 className="text-sm font-medium text-foreground">Strengths & weaknesses by topic</h3>
        <p className="text-xs text-muted-foreground -mt-2">
          Summed live across every cohort knowledge-quiz this student has submitted.
        </p>
        {quizBreakdownLoading ? (
          <Spinner />
        ) : !quizBreakdown || Object.keys(quizBreakdown.topic_breakdown).length === 0 ? (
          <EmptyState title="No quiz results yet" hint="This student hasn't submitted a cohort knowledge quiz." />
        ) : (
          <div className="flex flex-col gap-2">
            {Object.entries(quizBreakdown.topic_breakdown).map(([topic, { correct, total }]) => {
              const pct = total > 0 ? Math.round((correct / total) * 100) : 0
              return (
                <div key={topic} className="flex flex-col gap-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-foreground">{topic}</span>
                    <span className="text-muted-foreground">{correct}/{total} ({pct}%)</span>
                  </div>
                  <div className="h-2 rounded-full bg-muted overflow-hidden">
                    <div className={`h-full rounded-full ${pct >= 70 ? "bg-emerald-500" : pct >= 40 ? "bg-amber-500" : "bg-red-500"}`} style={{ width: `${pct}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {unenrollTarget && (
        <ConfirmDialog
          title="Unenroll from cohort?"
          description={`Remove this learner from "${unenrollTarget.cohortName}"? This cancels their registration, deactivates course enrollments from it, removes them from their team, and deletes the checklist assignment.`}
          confirmLabel="Unenroll"
          destructive
          pending={unenrollMutation.isPending}
          error={unenrollError}
          onCancel={() => { setUnenrollTarget(null); setUnenrollError(null) }}
          onConfirm={() => unenrollMutation.mutate(unenrollTarget.cohortId)}
        />
      )}
    </div>
  )
}

function CohortChecklistDetail({ cohortId, assignmentId }: { cohortId: string; assignmentId: string }) {
  const { data: items, isLoading } = useQuery({
    queryKey: ["assignment-items", cohortId, assignmentId],
    queryFn: () => getAssignmentItemsApi(cohortId, assignmentId),
  })

  if (isLoading) return <div className="px-3 pb-3"><Spinner /></div>
  const list = items ?? []
  if (list.length === 0) return <p className="px-3 pb-3 text-xs text-muted-foreground italic">No checklist items on this assignment.</p>

  const required = list.filter((i) => !i.optional)
  const optional = list.filter((i) => i.optional)
  const reqDone = required.filter((i) => i.status === "done").length
  const optDone = optional.filter((i) => i.status === "done").length
  const done = list.filter((i) => i.status === "done").length
  const pct = required.length > 0 ? Math.round((reqDone / required.length) * 100) : 0
  return (
    <div className="p-3 sm:p-5 border-t-2 border-border/60 bg-muted/20 flex flex-col gap-3">
      <div className="flex flex-col gap-1.5 pb-2 border-b border-border/40">
        <div className="flex items-center justify-between text-xs font-mono font-bold">
          <span className="text-muted-foreground">{reqDone} / {required.length} completed</span>
          <span className={pct === 100 ? "text-emerald-500 font-extrabold" : "text-foreground"}>{pct}%</span>
        </div>
        <div className="h-2 rounded-full bg-muted overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${pct === 100 ? "bg-emerald-500" : "bg-primary"}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        {optional.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground mt-0.5">
            <span><span className="font-semibold text-foreground">{reqDone}/{required.length}</span> required</span>
            <span className="text-border" aria-hidden="true">&bull;</span>
            <span><span className="font-semibold text-foreground">{optDone}/{optional.length}</span> optional</span>
            <span className="text-border" aria-hidden="true">&bull;</span>
            <span><span className="font-semibold text-foreground">{done}/{list.length}</span> total</span>
          </div>
        )}
      </div>
      <div className="flex flex-col gap-2">
        {list.map((item) => (
          <AssignmentItemRow key={item.item_id} item={item} cohortId={cohortId} assignmentId={assignmentId} />
        ))}
      </div>
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

function LearnerTeamCard({ team }: { team: StudentTeam }) {
  const { data: analytics, isLoading } = useQuery({
    queryKey: ["competitions-team-analytics", team.cohort_id],
    queryFn: () => getCohortTeamAnalyticsApi(team.cohort_id!, "all"),
    enabled: Boolean(team.cohort_id),
  })

  if (!team.cohort_id) {
    return (
      <div className="flex items-center justify-between gap-2 p-3 sm:p-3.5 bg-background border border-border/70 rounded-2xl">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-xl bg-primary/10 border border-primary/20 text-primary font-bold flex items-center justify-center text-xs shrink-0">
            {team.team_name.trim().slice(0, 2).toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <p className="text-sm font-semibold text-foreground truncate">{team.team_name}</p>
              {team.is_observer && (
                <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border border-indigo-500/30">
                  Observer
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground truncate mt-0.5">
              No cohort{team.join_code ? <> · Code: <span className="font-mono">{team.join_code}</span></> : null}
            </p>
          </div>
        </div>
        <span className="text-xs text-muted-foreground italic shrink-0 px-2">No cohort</span>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="p-3 sm:p-3.5 bg-background border border-border/70 rounded-2xl flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-primary/10 border border-primary/20 text-primary font-bold flex items-center justify-center text-xs shrink-0">
            {team.team_name.trim().slice(0, 2).toUpperCase()}
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <p className="text-sm font-semibold text-foreground">{team.team_name}</p>
              {team.is_observer && (
                <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border border-indigo-500/30">
                  Observer
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">{team.cohort_name ?? "Cohort"}</p>
          </div>
        </div>
        <Spinner />
      </div>
    )
  }

  const teamStats = analytics?.teams?.find((t) => t.team_id === team.team_id)
  if (!teamStats) {
    return (
      <div className="flex items-center justify-between gap-2 p-3 sm:p-3.5 bg-background border border-border/70 rounded-2xl">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-xl bg-primary/10 border border-primary/20 text-primary font-bold flex items-center justify-center text-xs shrink-0">
            {team.team_name.trim().slice(0, 2).toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <p className="text-sm font-semibold text-foreground truncate">{team.team_name}</p>
              {team.is_observer && (
                <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border border-indigo-500/30">
                  Observer
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground truncate mt-0.5">
              {team.cohort_name ?? "Cohort"}{team.join_code ? <> · Code: <span className="font-mono">{team.join_code}</span></> : null}
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <TeamAnalysisCard
      team={teamStats}
      cohortId={team.cohort_id}
      cohortName={team.cohort_name}
      joinCode={team.join_code}
    />
  )
}
