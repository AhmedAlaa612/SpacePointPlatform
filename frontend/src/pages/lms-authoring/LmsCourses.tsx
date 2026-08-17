import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Plus, ChevronRight } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Modal, Field, ModalActions, ConfirmDialog } from "@/pages/admin/components/common"
import {
  listCoursesApi, createCourseApi, publishCourseApi, unpublishCourseApi, deleteCourseApi,
  listInstructorOptionsApi,
  type AdminCourse, type CourseKind, type CourseLevel,
} from "@/api/lms_admin"

/** LMS course authoring (LM1-13) — the LM1-5 admin API's course list. Own
 * page, not bolted onto Cohorts.tsx (105 KB, three stale-prop bugs). */
export default function LmsCourses() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<AdminCourse | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const { data: courses = [], isLoading } = useQuery<AdminCourse[]>({
    queryKey: ["lms-admin-courses"],
    queryFn: listCoursesApi,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-courses"] })

  const publishMutation = useMutation({
    mutationFn: (course: AdminCourse) =>
      course.is_published ? unpublishCourseApi(course.id) : publishCourseApi(course.id),
    onSuccess: invalidate,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteCourseApi(id),
    onSuccess: () => { setDeleteError(null); setDeleteTarget(null); invalidate() },
    onError: (e: any) => setDeleteError(e?.response?.data?.detail ?? "Failed to delete course"),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="LMS"
        subtitle="Author course content — modules, lessons, quizzes, flashcards, video."
        action={
          <button
            onClick={() => setCreateOpen(true)}
            className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
          >
            <Plus size={14} /> New course
          </button>
        }
      />

      {courses.length === 0 ? (
        <EmptyState title="No courses yet" hint="Create one to start building content." />
      ) : (
        <div className="flex flex-col gap-2">
          {courses.map((course) => (
            <div
              key={course.id}
              onClick={() => void navigate({ to: `/lms-authoring/courses/${course.id}` })}
              className="flex items-center gap-4 p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors cursor-pointer"
            >
              <div className="w-16 h-16 rounded-xl bg-muted shrink-0 overflow-hidden flex items-center justify-center text-[10px] text-muted-foreground">
                {course.image_url ? (
                  <img src={course.image_url} alt="" className="w-full h-full object-cover" />
                ) : "No image"}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-sm font-medium text-foreground truncate">{course.title}</p>
                  <span
                    className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                      course.is_published ? "bg-green-500/15 text-green-600 dark:text-green-400" : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {course.is_published ? "Published" : "Draft"}
                  </span>
                  {course.kind === "mission" && (
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-primary/10 text-primary">Mission</span>
                  )}
                  {course.level && (
                    <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-muted text-muted-foreground capitalize">{course.level}</span>
                  )}
                  {course.track && <span className="text-xs text-muted-foreground">{course.track}</span>}
                </div>
                {course.description && <p className="text-xs text-muted-foreground truncate">{course.description}</p>}
                {course.instructor_name && <p className="text-xs text-muted-foreground mt-0.5">Instructor: {course.instructor_name}</p>}
              </div>
              <div className="flex items-center gap-1 flex-shrink-0 ml-3" onClick={(e) => e.stopPropagation()}>
                <button
                  onClick={() => publishMutation.mutate(course)}
                  disabled={publishMutation.isPending}
                  className="h-8 px-3 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-muted transition-colors disabled:opacity-50"
                >
                  {course.is_published ? "Unpublish" : "Publish"}
                </button>
                <button
                  onClick={() => setDeleteTarget(course)}
                  className="h-8 px-3 rounded-lg text-xs font-medium text-red-600 hover:bg-red-500/10 transition-colors"
                >
                  Delete
                </button>
                <ChevronRight size={16} className="text-muted-foreground ml-1" />
              </div>
            </div>
          ))}
        </div>
      )}

      {createOpen && (
        <CreateCourseModal
          onClose={() => setCreateOpen(false)}
          onSuccess={(course) => { invalidate(); setCreateOpen(false); void navigate({ to: `/lms-authoring/courses/${course.id}` }) }}
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          title={`Delete "${deleteTarget.title}"?`}
          description="Only possible if no student has ever enrolled. Unpublish it instead if you just want it hidden."
          confirmLabel="Delete"
          destructive
          pending={deleteMutation.isPending}
          error={deleteError}
          onCancel={() => { setDeleteTarget(null); setDeleteError(null) }}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
        />
      )}
    </div>
  )
}

function CreateCourseModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: (course: AdminCourse) => void }) {
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [kind, setKind] = useState<CourseKind>("course")
  const [level, setLevel] = useState<CourseLevel | "">("")
  const [track, setTrack] = useState("")
  const [outcomes, setOutcomes] = useState<string[]>([""])
  const [instructorId, setInstructorId] = useState("")
  const [instructorTitle, setInstructorTitle] = useState("")
  const [error, setError] = useState("")

  const { data: instructors = [] } = useQuery({ queryKey: ["lms-admin-instructors"], queryFn: listInstructorOptionsApi })

  const mutation = useMutation({
    mutationFn: () => createCourseApi({
      title: title.trim(), description: description.trim() || undefined, kind,
      level: level || undefined, track: track.trim() || undefined,
      outcomes: outcomes.map((o) => o.trim()).filter(Boolean),
      instructor_id: instructorId || undefined, instructor_title: instructorTitle.trim() || undefined,
    }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to create course"),
  })

  return (
    <Modal title="New course" onClose={onClose} maxWidth="sm:max-w-xl max-w-xl">
      <div className="flex flex-col gap-3">
        <Field label="Title">
          <input
            value={title} onChange={(e) => setTitle(e.target.value)} placeholder="CubeSat Basics" autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Description (optional)">
          <textarea
            value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
            className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors resize-none"
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Kind">
            <select
              value={kind} onChange={(e) => setKind(e.target.value as CourseKind)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              <option value="course">Course</option>
              <option value="mission">Mission (Phase 2)</option>
            </select>
          </Field>
          <Field label="Level (optional)">
            <select
              value={level} onChange={(e) => setLevel(e.target.value as CourseLevel | "")}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              <option value="">—</option>
              <option value="beginner">Beginner</option>
              <option value="intermediate">Intermediate</option>
              <option value="advanced">Advanced</option>
            </select>
          </Field>
        </div>
        <Field label="Track (optional)">
          <input
            value={track} onChange={(e) => setTrack(e.target.value)} placeholder="Spacecraft systems"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="What you'll be able to do (optional)">
          <div className="flex flex-col gap-2">
            {outcomes.map((o, i) => (
              <div key={i} className="flex gap-2">
                <input
                  value={o} placeholder="Explain a power budget"
                  onChange={(e) => setOutcomes((prev) => prev.map((x, idx) => (idx === i ? e.target.value : x)))}
                  className="flex-1 h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                />
                <button
                  onClick={() => setOutcomes((prev) => prev.filter((_, idx) => idx !== i))}
                  disabled={outcomes.length === 1}
                  className="h-9 px-3 text-xs text-red-600 hover:bg-red-500/10 rounded-lg transition-colors disabled:opacity-30"
                >
                  Remove
                </button>
              </div>
            ))}
            <button
              onClick={() => setOutcomes((prev) => [...prev, ""])}
              className="h-8 px-3 border border-dashed border-border rounded-xl text-xs font-medium text-muted-foreground hover:bg-muted transition-colors w-fit"
            >
              + Add outcome
            </button>
          </div>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Instructor (optional)">
            <select
              value={instructorId} onChange={(e) => setInstructorId(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              <option value="">—</option>
              {instructors.map((i) => <option key={i.id} value={i.id}>{i.full_name}</option>)}
            </select>
          </Field>
          <Field label="Instructor title (optional)">
            <input
              value={instructorTitle} onChange={(e) => setInstructorTitle(e.target.value)} placeholder="Lead Systems Engineer"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
        </div>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending} disabled={!title.trim()} label="Create course" />
      </div>
    </Modal>
  )
}
