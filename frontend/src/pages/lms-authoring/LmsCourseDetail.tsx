import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "@tanstack/react-router"
import { Plus, ChevronRight, ArrowLeft } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Modal, Field, ModalActions, ConfirmDialog } from "@/pages/admin/components/common"
import {
  getCourseApi, updateCourseApi, listModulesApi, createModuleApi, deleteModuleApi,
  type AdminModule,
} from "@/api/lms_admin"

export default function LmsCourseDetail() {
  const { courseId } = useParams({ strict: false }) as { courseId: string }
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [addOpen, setAddOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<AdminModule | null>(null)

  const { data: course, isLoading: courseLoading } = useQuery({
    queryKey: ["lms-admin-course", courseId],
    queryFn: () => getCourseApi(courseId),
  })
  const { data: modules = [], isLoading: modulesLoading } = useQuery<AdminModule[]>({
    queryKey: ["lms-admin-modules", courseId],
    queryFn: () => listModulesApi(courseId),
  })

  const invalidateModules = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-modules", courseId] })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteModuleApi(id),
    onSuccess: () => { setDeleteTarget(null); invalidateModules() },
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
          title={course.title}
          description={course.description ?? ""}
          onClose={() => setEditOpen(false)}
          onSuccess={() => { queryClient.invalidateQueries({ queryKey: ["lms-admin-course", courseId] }); setEditOpen(false) }}
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

function EditCourseModal({ courseId, title: initialTitle, description: initialDescription, onClose, onSuccess }: {
  courseId: string; title: string; description: string; onClose: () => void; onSuccess: () => void
}) {
  const [title, setTitle] = useState(initialTitle)
  const [description, setDescription] = useState(initialDescription)
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () => updateCourseApi(courseId, { title: title.trim(), description: description.trim() }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to save course"),
  })

  return (
    <Modal title="Edit course" onClose={onClose}>
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
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending} disabled={!title.trim()} label="Save changes" />
      </div>
    </Modal>
  )
}
