import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "@tanstack/react-router"
import { ArrowLeft, Plus, X } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import {
  getStudentProfileApi, listUserEnrollmentsApi, grantCourseEnrollmentApi, revokeCourseEnrollmentApi,
} from "@/api/lms_admin"
import { ItemPicker } from "@/pages/lms-authoring/components/ItemPicker"

/** Student profile (2026-08-12) — nickname, programs attended, and the
 * courses they're currently on, with assign/remove in one place. This is
 * the reverse direction of `AssignPanel` (course/mission fixed, staff
 * picked) — here the student is fixed and the course is picked, so it's a
 * small dedicated section rather than forcing `AssignPanel` to be
 * bidirectional. */
export default function LmsStudentDetail() {
  const { userId } = useParams({ strict: false }) as { userId: string }
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [courseId, setCourseId] = useState("")

  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ["lms-admin-student-profile", userId],
    queryFn: () => getStudentProfileApi(userId),
  })
  const { data: enrollments = [], isLoading: enrollmentsLoading } = useQuery({
    queryKey: ["lms-admin-user-enrollments", userId],
    queryFn: () => listUserEnrollmentsApi(userId),
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
    </div>
  )
}
