import { useRef, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "@tanstack/react-router"
import { isAxiosError } from "axios"
import { ArrowLeft, ImagePlus, Plus, X } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Modal, Field, ModalActions, ConfirmDialog } from "@/pages/admin/components/common"
import {
  getLearningPathApi, updateLearningPathApi, uploadLearningPathImageApi, deleteLearningPathApi,
  listCoursesApi, listLearningPathStepsApi, addLearningPathStepApi, removeLearningPathStepApi,
  type AdminLearningPath, type LearningPathStepEntry,
} from "@/api/lms_admin"

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

/** LMS learning-path authoring detail (LMS redesign, 2026-08-08) — edit
 * title/description/cover, publish/unpublish, delete, and the ordered step
 * list. Step add/remove mirrors LmsProgramAdmin.tsx's item-list UI, scoped
 * directly to this one path instead of a program picker. */
export default function LmsLearningPathDetail() {
  const { pathId } = useParams({ strict: false }) as { pathId: string }
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [editOpen, setEditOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [imageError, setImageError] = useState("")
  const [addingCourseId, setAddingCourseId] = useState("")
  const [addError, setAddError] = useState("")
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: path, isLoading: pathLoading } = useQuery({
    queryKey: ["lms-admin-learning-path", pathId],
    queryFn: () => getLearningPathApi(pathId),
  })
  const { data: courses = [] } = useQuery({ queryKey: ["lms-admin-courses"], queryFn: listCoursesApi })
  const { data: steps = [], isLoading: stepsLoading } = useQuery<LearningPathStepEntry[]>({
    queryKey: ["lms-admin-learning-path-steps", pathId],
    queryFn: () => listLearningPathStepsApi(pathId),
  })

  const invalidatePath = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-learning-path", pathId] })
  const invalidateSteps = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-learning-path-steps", pathId] })

  const publishMutation = useMutation({
    mutationFn: () => updateLearningPathApi(pathId, { is_published: !path?.is_published }),
    onSuccess: invalidatePath,
  })

  const imageMutation = useMutation({
    mutationFn: (file: File) => uploadLearningPathImageApi(pathId, file),
    onSuccess: () => { setImageError(""); invalidatePath() },
    onError: (e: unknown) => setImageError(errorDetail(e, "Failed to upload image")),
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteLearningPathApi(pathId),
    onSuccess: () => void navigate({ to: "/lms-authoring/learning-paths" }),
    onError: (e: unknown) => setDeleteError(errorDetail(e, "Failed to delete learning path")),
  })

  const addStepMutation = useMutation({
    mutationFn: (courseId: string) => addLearningPathStepApi(pathId, { course_id: courseId }),
    onSuccess: () => { setAddError(""); setAddingCourseId(""); invalidateSteps() },
    onError: (e: unknown) => setAddError(errorDetail(e, "Failed to add course")),
  })
  const removeStepMutation = useMutation({
    mutationFn: (courseId: string) => removeLearningPathStepApi(pathId, courseId),
    onSuccess: invalidateSteps,
  })

  if (pathLoading || stepsLoading || !path) return <Spinner />

  const coursesById = Object.fromEntries(courses.map((c) => [c.id, c]))
  const availableCourses = courses.filter((c) => !steps.some((s) => s.course_id === c.id))

  return (
    <div className="flex flex-col gap-6">
      <button
        onClick={() => void navigate({ to: "/lms-authoring/learning-paths" })}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors w-fit"
      >
        <ArrowLeft size={14} /> Learning paths
      </button>

      <div className="flex items-start gap-5">
        <button
          onClick={() => fileInputRef.current?.click()}
          className="group relative w-32 h-32 sm:w-40 sm:h-40 shrink-0 rounded-2xl bg-muted overflow-hidden cursor-pointer ring-1 ring-border"
          title="Upload cover image"
        >
          {path.image_url ? (
            <img src={path.image_url} alt="" className="w-full h-full object-cover" />
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
            title={path.title}
            subtitle={path.description ?? undefined}
            action={
              <div className="flex gap-2">
                <button
                  onClick={() => setEditOpen(true)}
                  className="h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
                >
                  Edit
                </button>
                <button
                  onClick={() => publishMutation.mutate()}
                  disabled={publishMutation.isPending}
                  className="h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
                >
                  {path.is_published ? "Unpublish" : "Publish"}
                </button>
                <button
                  onClick={() => setDeleteOpen(true)}
                  className="h-9 px-4 rounded-xl text-sm font-medium text-red-600 hover:bg-red-500/10 transition-colors"
                >
                  Delete
                </button>
              </div>
            }
          />
          <div className="flex items-center gap-2">
            <span
              className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                path.is_published ? "bg-green-500/15 text-green-600 dark:text-green-400" : "bg-muted text-muted-foreground"
              }`}
            >
              {path.is_published ? "Published" : "Draft"}
            </span>
            {path.price_cents != null && (
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                Bundle · {(path.price_cents / 100).toLocaleString(undefined, { style: "currency", currency: path.currency.toUpperCase() })}
              </span>
            )}
          </div>
          {imageError && <p className="text-xs text-red-500 mt-2">{imageError}</p>}
        </div>
      </div>

      <div className="flex flex-col gap-3 max-w-2xl">
        <h2 className="text-sm font-semibold text-foreground">Steps (in order)</h2>
        {steps.length === 0 ? (
          <EmptyState title="No courses in this path yet" />
        ) : (
          <div className="flex flex-col gap-2">
            {steps.map((step) => (
              <div key={step.id} className="flex items-center justify-between p-3 bg-card border border-border rounded-xl">
                <span className="text-sm text-foreground">
                  {step.position}. {coursesById[step.course_id]?.title ?? step.course_id}
                  {coursesById[step.course_id]?.kind === "mission" && (
                    <span className="ml-2 text-xs font-semibold px-2 py-0.5 rounded-full bg-primary/10 text-primary">Mission</span>
                  )}
                </span>
                <button
                  onClick={() => removeStepMutation.mutate(step.course_id)}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        )}

        {availableCourses.length > 0 && (
          <div className="flex gap-2">
            <select
              value={addingCourseId} onChange={(e) => setAddingCourseId(e.target.value)}
              className="flex-1 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              <option value="">Add a course…</option>
              {availableCourses.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
            </select>
            <button
              onClick={() => addingCourseId && addStepMutation.mutate(addingCourseId)}
              disabled={!addingCourseId || addStepMutation.isPending}
              className="flex items-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors disabled:opacity-50"
            >
              <Plus size={14} /> Add
            </button>
          </div>
        )}
        {addError && <p className="text-xs text-red-500">{addError}</p>}
      </div>

      {editOpen && (
        <EditPathModal
          path={path}
          onClose={() => setEditOpen(false)}
          onSuccess={() => { invalidatePath(); setEditOpen(false) }}
        />
      )}

      {deleteOpen && (
        <ConfirmDialog
          title={`Delete "${path.title}"?`}
          description="This removes the curated grouping only — it never touches the courses inside it or any student's enrollment/progress."
          confirmLabel="Delete"
          destructive
          pending={deleteMutation.isPending}
          error={deleteError}
          onCancel={() => { setDeleteOpen(false); setDeleteError(null) }}
          onConfirm={() => deleteMutation.mutate()}
        />
      )}
    </div>
  )
}

function EditPathModal({
  path, onClose, onSuccess,
}: { path: AdminLearningPath; onClose: () => void; onSuccess: () => void }) {
  const [title, setTitle] = useState(path.title)
  const [description, setDescription] = useState(path.description ?? "")
  const [priceDollars, setPriceDollars] = useState(
    path.price_cents != null ? String(path.price_cents / 100) : ""
  )
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () => updateLearningPathApi(path.id, {
      title: title.trim(), description: description.trim() || undefined,
      price_cents: priceDollars.trim() ? Math.round(Number(priceDollars) * 100) : null,
    }),
    onSuccess,
    onError: (e: unknown) => setError(errorDetail(e, "Failed to update learning path")),
  })

  return (
    <Modal title="Edit learning path" onClose={onClose} maxWidth="sm:max-w-xl max-w-xl">
      <div className="flex flex-col gap-3">
        <Field label="Title">
          <input
            value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Description (optional)">
          <textarea
            value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
            className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors resize-none"
          />
        </Field>
        <Field label="Bundle price, USD (optional)">
          <input
            value={priceDollars} onChange={(e) => setPriceDollars(e.target.value)}
            type="number" min="0" step="0.01" placeholder="Leave blank — not sold as a bundle"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
          <p className="text-[11px] text-muted-foreground mt-1">
            When set, students can buy every course in this path at once via Stripe Checkout — regardless of
            each course's own access mode. Leave blank to keep the free self-enrol "Start" behavior only.
          </p>
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending}
          disabled={!title.trim() || (priceDollars.trim() !== "" && !(Number(priceDollars) > 0))}
          label="Save changes"
        />
      </div>
    </Modal>
  )
}
