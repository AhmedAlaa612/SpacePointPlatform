import { useRef, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "@tanstack/react-router"
import { isAxiosError } from "axios"
import { ArrowLeft, ImagePlus, Plus, X, Crop } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Modal, Field, ModalActions, ConfirmDialog } from "@/pages/admin/components/common"
import { ImageCropModal } from "@/components/ui/ImageCropModal"
import {
  getLearningPathApi, updateLearningPathApi, submitLearningPathForReviewApi, uploadLearningPathImageApi, deleteLearningPathApi,
  listCoursesApi, listLearningPathStepsApi, addLearningPathStepApi, removeLearningPathStepApi,
  bulkGrantLearningPathEnrollmentApi,
  listLearningPathRosterApi, grantLearningPathEnrollmentApi, revokeLearningPathEnrollmentApi,
  type AdminLearningPath, type LearningPathStepEntry, type BulkGrantResult,
} from "@/api/lms_admin"
import { AssignPanel } from "@/pages/lms-authoring/components/AssignPanel"
import { useAuth } from "@/context/AuthContext"
import { useToast } from "@/components/ui/toast"

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
  const toast = useToast()
  const { user, activeRole } = useAuth()
  const cannotPublish = activeRole === "lms_author" && !user?.author_can_publish
  const canViewAudit = activeRole === "admin" || activeRole === "operations"
  const canManageAssignedAccess = activeRole !== "lms_author" || !!user?.author_scope_all

  const [editOpen, setEditOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [imageError, setImageError] = useState("")
  const [cropSrc, setCropSrc] = useState<string | null>(null)
  const [cropOpen, setCropOpen] = useState(false)
  const [addingCourseId, setAddingCourseId] = useState("")
  const [addError, setAddError] = useState("")
  const [submittedForReview, setSubmittedForReview] = useState(false)

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
  const { data: roster = [], isLoading: rosterLoading } = useQuery({
    queryKey: ["lms-admin-learning-path-roster", pathId],
    queryFn: () => listLearningPathRosterApi(pathId),
    enabled: canManageAssignedAccess,
  })

  const invalidatePath = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-learning-path", pathId] })
  const invalidateSteps = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-learning-path-steps", pathId] })
  const invalidateRoster = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-learning-path-roster", pathId] })

  const [bulkResult, setBulkResult] = useState<BulkGrantResult | null>(null)
  const [assignError, setAssignError] = useState("")
  const grantMutation = useMutation({
    mutationFn: (userId: string) => grantLearningPathEnrollmentApi(pathId, userId),
    onSuccess: () => { setAssignError(""); invalidateRoster() },
    onError: (e: unknown) => setAssignError(errorDetail(e, "Couldn't grant access")),
  })
  const bulkGrantMutation = useMutation({
    mutationFn: (role: string) => bulkGrantLearningPathEnrollmentApi(pathId, { role }),
    onSuccess: (result) => { setAssignError(""); setBulkResult(result); invalidateRoster() },
    onError: (e: unknown) => setAssignError(errorDetail(e, "Couldn't grant access")),
  })
  const revokeMutation = useMutation({
    mutationFn: (userId: string) => revokeLearningPathEnrollmentApi(pathId, userId),
    onSuccess: () => { setAssignError(""); invalidateRoster() },
    onError: (e: unknown) => setAssignError(errorDetail(e, "Couldn't revoke access")),
  })

  const publishMutation = useMutation({
    mutationFn: () => updateLearningPathApi(pathId, { is_published: !path?.is_published }),
    onSuccess: invalidatePath,
    onError: (e: unknown) => toast.error(errorDetail(e, "Failed to update publish status")),
  })

  const submitReviewMutation = useMutation({
    mutationFn: () => submitLearningPathForReviewApi(pathId),
    onSuccess: (res) => {
      setSubmittedForReview(true)
      toast.success(res.message || "Learning path submitted for review! An administrator will review your learning path.")
    },
    onError: (e: unknown) => toast.error(errorDetail(e, "Failed to submit for review")),
  })


  const imageMutation = useMutation({
    mutationFn: (file: File) => uploadLearningPathImageApi(pathId, file),
    onSuccess: () => {
      setImageError("")
      invalidatePath()
      setCropOpen(false)
      setCropSrc(null)
    },
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

      <div className="flex flex-col sm:flex-row items-start gap-5">
        <div className="flex flex-col gap-1.5 shrink-0 w-full sm:w-auto">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="group relative w-full max-w-xs sm:w-52 sm:h-32 rounded-2xl bg-muted overflow-hidden cursor-pointer ring-1 ring-border aspect-video"
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
          {path.image_url && (
            <button
              type="button"
              onClick={() => {
                setCropSrc(path.image_url!)
                setCropOpen(true)
              }}
              className="text-xs text-primary hover:underline flex items-center justify-center gap-1 cursor-pointer"
            >
              <Crop size={12} />
              <span>Crop current</span>
            </button>
          )}
          {imageError && <p className="text-xs text-red-500 max-w-[208px]">{imageError}</p>}
        </div>
        <input
          ref={fileInputRef} type="file" accept="image/*" className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) {
              const reader = new FileReader()
              reader.onload = () => {
                setCropSrc(reader.result as string)
                setCropOpen(true)
              }
              reader.readAsDataURL(f)
            }
            e.currentTarget.value = ""
          }}
        />

        <div className="flex-1 min-w-0 w-full">
          <PageHeader
            title={path.title}
            subtitle={path.description ?? undefined}
            action={
              <div className="flex gap-2 items-center flex-wrap">
                <button
                  onClick={() => setEditOpen(true)}
                  className="h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
                >
                  Edit
                </button>
                {cannotPublish ? (
                  path.is_published ? (
                    <span
                      title="Published and visible in catalog"
                      className="h-9 px-3 border border-border rounded-xl text-xs font-medium text-green-600 dark:text-green-400 flex items-center select-none"
                    >
                      Published
                    </span>
                  ) : (
                    <button
                      onClick={() => submitReviewMutation.mutate()}
                      disabled={submitReviewMutation.isPending || submittedForReview}
                      className="h-9 px-4 border border-amber-500/40 rounded-xl text-sm font-medium text-amber-600 dark:text-amber-400 hover:bg-amber-500/10 transition-colors cursor-pointer disabled:opacity-60 flex items-center gap-1.5"
                      title="Submit this learning path to administrators for review and publishing"
                    >
                      {submittedForReview ? "Submitted for review" : "Submit for review"}
                    </button>
                  )
                ) : (
                  <button
                    onClick={() => publishMutation.mutate()}
                    disabled={publishMutation.isPending}
                    className="h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
                  >
                    {path.is_published ? "Unpublish" : "Publish"}
                  </button>
                )}

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
            {canViewAudit && (path.created_by_name || path.created_at) && (
              <span className="text-xs text-muted-foreground">

                {path.created_by_name && (
                  <>Created by <span className="text-foreground/90 font-medium">{path.created_by_name}</span></>
                )}
                {path.created_by_name && path.created_at && " · "}
                {path.created_at && (
                  <span>{new Date(path.created_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}</span>
                )}
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

      {canManageAssignedAccess && (
        <>
          <AssignPanel
            // A path grant is N course Enrollment rows, not one row of its own
            // (see LearningPathRosterRow's own docstring) — `id` is the user_id
            // itself, not a synthetic per-grant id like the course/mission
            // version has. onRevoke below gets that same user_id back and
            // passes it straight to revokeLearningPathEnrollmentApi.
            roster={roster.map((r) => ({
              id: r.user_id, userId: r.user_id, name: r.student_name, email: r.student_email, status: r.status,
            }))}
            isLoading={rosterLoading}
            onGrant={(userId) => grantMutation.mutate(userId)}
            onBulkGrant={(role) => bulkGrantMutation.mutate(role)}
            onRevoke={(userId) => revokeMutation.mutate(userId)}
            grantPending={grantMutation.isPending}
            bulkPending={bulkGrantMutation.isPending}
            revokePending={revokeMutation.isPending}
            bulkResult={bulkResult}
          />
          {assignError && <p className="text-xs text-red-500 max-w-2xl">{assignError}</p>}
        </>
      )}

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

      {cropSrc && (
        <ImageCropModal
          isOpen={cropOpen}
          onClose={() => {
            if (!imageMutation.isPending) {
              setCropOpen(false)
              setCropSrc(null)
            }
          }}
          imageSrc={cropSrc}
          title="Crop Learning Path Cover"
          aspect={16 / 9}
          showPreview={false}
          isUploading={imageMutation.isPending}
          onCropComplete={async (croppedFile) => {
            await imageMutation.mutateAsync(croppedFile)
          }}
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
  const [accessMode, setAccessMode] = useState<"open" | "invite" | "paid">(path.access_mode)
  const [priceDollars, setPriceDollars] = useState(
    path.price_cents != null ? String(path.price_cents / 100) : ""
  )
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () => updateLearningPathApi(path.id, {
      title: title.trim(), description: description.trim() || undefined,
      access_mode: accessMode,
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
        <Field label="Access">
          <select
            value={accessMode} onChange={(e) => setAccessMode(e.target.value as "open" | "invite" | "paid")}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
          >
            <option value="open">Open — anyone self-starts</option>
            <option value="invite">Invite-only — admin grant only</option>
            <option value="paid">Paid — Stripe Checkout</option>
          </select>
          <p className="text-[11px] text-muted-foreground mt-1">
            Invite-only paths are hidden from the catalog entirely until a student is granted access.
          </p>
        </Field>
        <Field label="Bundle price, USD (optional)">
          <input
            value={priceDollars} onChange={(e) => setPriceDollars(e.target.value)}
            type="number" min="0" step="0.01" placeholder="Leave blank — not sold as a bundle"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
          <p className="text-[11px] text-muted-foreground mt-1">
            When set, students can buy every course in this path at once via Stripe Checkout — regardless of
            each course's own access mode. Leave blank to keep the free self-enroll "Start" behavior only.
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
