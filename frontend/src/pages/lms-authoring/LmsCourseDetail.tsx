import { useRef, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "@tanstack/react-router"
import { Plus, ChevronRight, ArrowLeft, ImagePlus } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Modal, Field, ModalActions, ConfirmDialog } from "@/pages/admin/components/common"
import {
  getCourseApi, updateCourseApi, uploadCourseImageApi, listInstructorOptionsApi,
  listModulesApi, createModuleApi, deleteModuleApi,
  type AdminCourse, type AdminModule, type CourseLevel,
} from "@/api/lms_admin"

export default function LmsCourseDetail() {
  const { courseId } = useParams({ strict: false }) as { courseId: string }
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [addOpen, setAddOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<AdminModule | null>(null)
  const [imageError, setImageError] = useState("")
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: course, isLoading: courseLoading } = useQuery({
    queryKey: ["lms-admin-course", courseId],
    queryFn: () => getCourseApi(courseId),
  })
  const { data: modules = [], isLoading: modulesLoading } = useQuery<AdminModule[]>({
    queryKey: ["lms-admin-modules", courseId],
    queryFn: () => listModulesApi(courseId),
  })

  const invalidateModules = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-modules", courseId] })
  const invalidateCourse = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-course", courseId] })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteModuleApi(id),
    onSuccess: () => { setDeleteTarget(null); invalidateModules() },
  })

  const imageMutation = useMutation({
    mutationFn: (file: File) => uploadCourseImageApi(courseId, file),
    onSuccess: () => { setImageError(""); invalidateCourse() },
    onError: (e: any) => setImageError(e?.response?.data?.detail ?? "Failed to upload image"),
  })

  if (courseLoading || modulesLoading || !course) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <button
        onClick={() => void navigate({ to: "/lms-authoring/courses" })}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors w-fit"
      >
        <ArrowLeft size={14} /> Courses
      </button>

      <div className="flex items-start gap-5">
        <button
          onClick={() => fileInputRef.current?.click()}
          className="group relative w-32 h-32 sm:w-40 sm:h-40 shrink-0 rounded-2xl bg-muted overflow-hidden cursor-pointer ring-1 ring-border"
          title="Upload cover image"
        >
          {course.image_url ? (
            <img src={course.image_url} alt="" className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center gap-1.5 text-muted-foreground">
              <ImagePlus size={20} />
              <span className="text-[11px]">Add cover</span>
            </div>
          )}
          <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white text-xs font-medium">
            {imageMutation.isPending ? "Uploading..." : "Change"}
          </div>
        </button>
        <input
          ref={fileInputRef} type="file" accept="image/*" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) imageMutation.mutate(f) }}
        />

        <div className="flex-1 min-w-0">
          <PageHeader
            title={course.title}
            subtitle={course.description ?? undefined}
            action={
              <div className="flex gap-2">
                <button
                  onClick={() => setEditOpen(true)}
                  className="h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
                >
                  Edit
                </button>
                <button
                  onClick={() => setAddOpen(true)}
                  className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
                >
                  <Plus size={14} /> Add module
                </button>
              </div>
            }
          />
          <div className="flex items-center gap-2 flex-wrap -mt-3">
            {course.level && (
              <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-muted text-muted-foreground capitalize">{course.level}</span>
            )}
            {course.track && <span className="text-xs text-muted-foreground">{course.track}</span>}
            {course.instructor_name && (
              <span className="text-xs text-muted-foreground">Instructor: {course.instructor_name}{course.instructor_title ? ` · ${course.instructor_title}` : ""}</span>
            )}
          </div>
          {course.outcomes.length > 0 && (
            <ul className="mt-3 grid sm:grid-cols-2 gap-x-6 gap-y-1 text-xs text-muted-foreground list-disc list-inside">
              {course.outcomes.map((o, i) => <li key={i}>{o}</li>)}
            </ul>
          )}
          {imageError && <p className="text-xs text-red-500 mt-2">{imageError}</p>}
        </div>
      </div>

      {modules.length === 0 ? (
        <EmptyState title="No modules yet" hint="Add a module, then add lessons to it." />
      ) : (
        <div className="flex flex-col gap-2">
          {modules.map((module) => (
            <div
              key={module.id}
              onClick={() => void navigate({ to: `/lms-authoring/modules/${module.id}` })}
              className="flex items-center justify-between p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors cursor-pointer"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground truncate">
                  {module.position}. {module.title}
                </p>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0 ml-3" onClick={(e) => e.stopPropagation()}>
                <button
                  onClick={() => setDeleteTarget(module)}
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

      {addOpen && (
        <AddModuleModal
          courseId={courseId}
          onClose={() => setAddOpen(false)}
          onSuccess={() => { invalidateModules(); setAddOpen(false) }}
        />
      )}
      {editOpen && (
        <EditCourseModal
          courseId={courseId}
          course={course}
          onClose={() => setEditOpen(false)}
          onSuccess={() => { invalidateCourse(); setEditOpen(false) }}
        />
      )}
      {deleteTarget && (
        <ConfirmDialog
          title={`Delete module "${deleteTarget.title}"?`}
          description="Deletes every lesson inside it and any student progress on them."
          confirmLabel="Delete"
          destructive
          pending={deleteMutation.isPending}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
        />
      )}
    </div>
  )
}

function AddModuleModal({ courseId, onClose, onSuccess }: { courseId: string; onClose: () => void; onSuccess: () => void }) {
  const [title, setTitle] = useState("")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () => createModuleApi(courseId, { title: title.trim() }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to create module"),
  })

  return (
    <Modal title="Add module" onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="Title">
          <input
            value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Module 1: Orbits" autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending} disabled={!title.trim()} label="Add module" />
      </div>
    </Modal>
  )
}

function EditCourseModal({ courseId, course, onClose, onSuccess }: {
  courseId: string; course: AdminCourse; onClose: () => void; onSuccess: () => void
}) {
  const [title, setTitle] = useState(course.title)
  const [description, setDescription] = useState(course.description ?? "")
  const [level, setLevel] = useState<CourseLevel | "">(course.level ?? "")
  const [track, setTrack] = useState(course.track ?? "")
  const [outcomes, setOutcomes] = useState<string[]>(course.outcomes.length ? course.outcomes : [""])
  const [instructorId, setInstructorId] = useState(course.instructor_id ?? "")
  const [instructorTitle, setInstructorTitle] = useState(course.instructor_title ?? "")
  const [error, setError] = useState("")

  const { data: instructors = [] } = useQuery({ queryKey: ["lms-admin-instructors"], queryFn: listInstructorOptionsApi })

  const mutation = useMutation({
    mutationFn: () => updateCourseApi(courseId, {
      title: title.trim(), description: description.trim(),
      level: level || null, track: track.trim() || null,
      outcomes: outcomes.map((o) => o.trim()).filter(Boolean),
      instructor_id: instructorId || null, instructor_title: instructorTitle.trim() || null,
    }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to save course"),
  })

  return (
    <Modal title="Edit course" onClose={onClose} maxWidth="sm:max-w-xl max-w-xl">
      <div className="flex flex-col gap-3">
        <Field label="Title">
          <input
            value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Description">
          <textarea
            value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
            className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors resize-none"
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
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
          <Field label="Track (optional)">
            <input
              value={track} onChange={(e) => setTrack(e.target.value)} placeholder="Spacecraft systems"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
        </div>
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
        <ModalActions onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending} disabled={!title.trim()} label="Save changes" />
      </div>
    </Modal>
  )
}
