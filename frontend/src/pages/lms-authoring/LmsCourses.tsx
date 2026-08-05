import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Plus, ChevronRight } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Modal, Field, ModalActions, ConfirmDialog } from "@/pages/admin/components/common"
import {
  listCoursesApi, createCourseApi, publishCourseApi, unpublishCourseApi, deleteCourseApi,
  type AdminCourse, type CourseKind,
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
        title="LMS Courses"
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
              className="flex items-center justify-between p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors cursor-pointer"
            >
              <div className="min-w-0">
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
                </div>
                {course.description && <p className="text-xs text-muted-foreground truncate">{course.description}</p>}
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
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () => createCourseApi({ title: title.trim(), description: description.trim() || undefined, kind }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to create course"),
  })

  return (
    <Modal title="New course" onClose={onClose}>
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
        <Field label="Kind">
          <select
            value={kind} onChange={(e) => setKind(e.target.value as CourseKind)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
          >
            <option value="course">Course</option>
            <option value="mission">Mission (Phase 2)</option>
          </select>
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending} disabled={!title.trim()} label="Create course" />
      </div>
    </Modal>
  )
}
