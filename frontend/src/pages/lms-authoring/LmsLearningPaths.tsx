import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { isAxiosError } from "axios"
import { Plus, ChevronRight } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Modal, Field, ModalActions } from "@/pages/admin/components/common"
import { listLearningPathsApi, createLearningPathApi, type AdminLearningPath } from "@/api/lms_admin"
import { useAuth } from "@/context/AuthContext"

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

/** LMS learning-path authoring (LMS redesign, 2026-08-08) — the list view,
 * mirroring LmsCourses.tsx. Step ordering + publish + image live on the
 * detail page (LmsLearningPathDetail.tsx), same split as courses/modules. */
export default function LmsLearningPaths() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { activeRole } = useAuth()
  const canViewAudit = activeRole === "admin" || activeRole === "operations"
  const [createOpen, setCreateOpen] = useState(false)


  const { data: paths = [], isLoading } = useQuery<AdminLearningPath[]>({
    queryKey: ["lms-admin-learning-paths"],
    queryFn: listLearningPathsApi,
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="LMS Learning Paths"
        subtitle="Curated, ordered course sequences students can start as one unit."
        action={
          <button
            onClick={() => setCreateOpen(true)}
            className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
          >
            <Plus size={14} /> New path
          </button>
        }
      />

      {paths.length === 0 ? (
        <EmptyState title="No learning paths yet" hint="Create one to start grouping courses into a sequence." />
      ) : (
        <div className="flex flex-col gap-2">
          {paths.map((path) => (
            <div
              key={path.id}
              onClick={() => void navigate({ to: `/lms-authoring/learning-paths/${path.id}` })}
              className="flex items-center gap-4 p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors cursor-pointer"
            >
              <div className="w-16 h-16 rounded-xl bg-muted shrink-0 overflow-hidden flex items-center justify-center text-[10px] text-muted-foreground">
                {path.image_url ? <img src={path.image_url} alt="" className="w-full h-full object-cover" /> : "No image"}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-sm font-medium text-foreground truncate">{path.title}</p>
                  <span
                    className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                      path.is_published ? "bg-green-500/15 text-green-600 dark:text-green-400" : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {path.is_published ? "Published" : "Draft"}
                  </span>
                  {path.access_mode !== "open" && (
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                      {path.access_mode === "paid" ? "Paid" : "Invite-only"}
                    </span>
                  )}
                </div>
                {path.description && <p className="text-xs text-muted-foreground truncate">{path.description}</p>}
                {canViewAudit && (path.created_by_name || path.created_at) && (
                  <div className="flex items-center gap-2 text-[11px] text-muted-foreground mt-1 flex-wrap">

                    {path.created_by_name && (
                      <span>Created by <span className="text-foreground/80 font-medium">{path.created_by_name}</span></span>
                    )}
                    {path.created_by_name && path.created_at && <span>•</span>}
                    {path.created_at && (
                      <span>{new Date(path.created_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}</span>
                    )}
                  </div>
                )}
              </div>

              <ChevronRight size={16} className="text-muted-foreground ml-1 shrink-0" />
            </div>
          ))}
        </div>
      )}

      {createOpen && (
        <CreatePathModal
          onClose={() => setCreateOpen(false)}
          onSuccess={(path) => {
            void queryClient.invalidateQueries({ queryKey: ["lms-admin-learning-paths"] })
            setCreateOpen(false)
            void navigate({ to: `/lms-authoring/learning-paths/${path.id}` })
          }}
        />
      )}
    </div>
  )
}

function CreatePathModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: (path: AdminLearningPath) => void }) {
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [accessMode, setAccessMode] = useState<"open" | "invite" | "paid">("open")
  const [priceDollars, setPriceDollars] = useState("")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () => createLearningPathApi({
      title: title.trim(), description: description.trim() || undefined,
      access_mode: accessMode,
      price_cents: accessMode === "paid" && priceDollars.trim() ? Math.round(Number(priceDollars) * 100) : undefined,
    }),
    onSuccess,
    onError: (e: unknown) => setError(errorDetail(e, "Failed to create learning path")),
  })

  return (
    <Modal title="New learning path" onClose={onClose} maxWidth="sm:max-w-xl max-w-xl">
      <div className="flex flex-col gap-3">
        <Field label="Title">
          <input
            value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Space Science Foundations" autoFocus
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
          <Field label="Access">
            <select
              value={accessMode} onChange={(e) => setAccessMode(e.target.value as "open" | "invite" | "paid")}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              <option value="open">Open — anyone self-starts</option>
              <option value="invite">Invite-only — admin grant only</option>
              <option value="paid">Paid — Stripe Checkout</option>
            </select>
          </Field>
          {accessMode === "paid" && (
            <Field label="Bundle price (USD)">
              <input
                value={priceDollars} onChange={(e) => setPriceDollars(e.target.value)}
                type="number" min="0" step="0.01" placeholder="49.00"
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </Field>
          )}
        </div>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending}
          disabled={!title.trim() || (accessMode === "paid" && !(Number(priceDollars) > 0))}
          label="Create path"
        />
      </div>
    </Modal>
  )
}
