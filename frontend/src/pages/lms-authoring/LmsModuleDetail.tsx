import { useRef, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useParams } from "@tanstack/react-router"
import {
  Plus, Pencil, ArrowLeft, ArrowUp, ArrowDown, FileText, HelpCircle, Layers, Video as VideoIcon, Loader2,
  StickyNote, MessageCircleQuestion,
} from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Modal, Field, ModalActions, ConfirmDialog } from "@/pages/admin/components/common"
import {
  listItemsApi, createItemApi, updateItemApi, deleteItemApi, uploadVideoApi, reorderItemsApi,
  listCheckpointsApi, createCheckpointApi, updateCheckpointApi, deleteCheckpointApi,
  getModuleApi, updateModuleApi,
  type AdminItem, type ModuleItemKind, type AdminQuizQuestion, type VideoTranscodeStatus,
  type AdminCheckpoint, type CheckpointKind, type CheckpointQuestionType, type AdminQuizOption,
  type AdminModule,
} from "@/api/lms_admin"

const KIND_ICON: Record<ModuleItemKind, React.ComponentType<{ size?: number; className?: string }>> = {
  text: FileText, quiz: HelpCircle, flashcards: Layers, video: VideoIcon,
}
const KIND_LABEL: Record<ModuleItemKind, string> = {
  text: "Text", quiz: "Quiz", flashcards: "Flashcards", video: "Video",
}

const IN_FLIGHT_STATUSES = new Set<VideoTranscodeStatus>(["pending", "processing"])

function videoStatus(item: AdminItem): VideoTranscodeStatus | null {
  return item.kind === "video" && "transcode_status" in item.content ? item.content.transcode_status : null
}

/** Pending/processing videos flip to ready/failed off-band (the ARQ worker
 * transcodes async) — poll while any are in flight so the author sees it
 * happen instead of guessing or reloading the page. */
function VideoStatusBadge({ status }: { status: VideoTranscodeStatus | null }) {
  if (status === null) return null
  const styles: Record<VideoTranscodeStatus, string> = {
    pending: "bg-muted text-muted-foreground",
    processing: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
    ready: "bg-green-500/15 text-green-600 dark:text-green-400",
    failed: "bg-red-500/15 text-red-600 dark:text-red-400",
  }
  const labels: Record<VideoTranscodeStatus, string> = {
    pending: "Pending", processing: "Processing", ready: "Ready", failed: "Failed",
  }
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full ${styles[status]}`}>
      {IN_FLIGHT_STATUSES.has(status) && <Loader2 size={10} className="animate-spin" />}
      {labels[status]}
    </span>
  )
}

export default function LmsModuleDetail() {
  const { moduleId } = useParams({ strict: false }) as { moduleId: string }
  const queryClient = useQueryClient()
  const [addKind, setAddKind] = useState<ModuleItemKind | null>(null)
  const [editItem, setEditItem] = useState<AdminItem | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AdminItem | null>(null)
  const [uploadTarget, setUploadTarget] = useState<AdminItem | null>(null)
  const [checkpointTarget, setCheckpointTarget] = useState<AdminItem | null>(null)
  const [editModuleOpen, setEditModuleOpen] = useState(false)

  const { data: module } = useQuery<AdminModule>({
    queryKey: ["lms-admin-module", moduleId],
    queryFn: () => getModuleApi(moduleId),
  })

  const { data: items = [], isLoading } = useQuery<AdminItem[]>({
    queryKey: ["lms-admin-items", moduleId],
    queryFn: () => listItemsApi(moduleId),
    refetchInterval: (query) => {
      const inFlight = (query.state.data ?? []).some((i) => {
        const status = videoStatus(i)
        return status !== null && IN_FLIGHT_STATUSES.has(status)
      })
      return inFlight ? 4000 : false
    },
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-items", moduleId] })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteItemApi(id),
    onSuccess: () => { setDeleteTarget(null); invalidate() },
  })

  const reorderMutation = useMutation({
    mutationFn: (itemIds: string[]) => reorderItemsApi(moduleId, itemIds),
    onSuccess: (rows) => queryClient.setQueryData(["lms-admin-items", moduleId], rows),
  })

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= items.length || reorderMutation.isPending) return
    const ids = items.map((i) => i.id)
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    reorderMutation.mutate(ids)
  }

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <button
        onClick={() => window.history.back()}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors w-fit"
      >
        <ArrowLeft size={14} /> Back
      </button>

      <PageHeader
        title={module ? module.title : "Module items"}
        subtitle="Add lessons in the order students should see them."
        action={
          <div className="flex gap-2">
            {module && (
              <button
                onClick={() => setEditModuleOpen(true)}
                className="flex items-center gap-1.5 h-9 px-3 border border-border rounded-xl text-xs font-medium text-foreground hover:bg-muted transition-colors"
              >
                <Pencil size={12} /> Rename
              </button>
            )}
            {(["text", "flashcards", "quiz", "video"] as ModuleItemKind[]).map((kind) => (
              <button
                key={kind}
                onClick={() => setAddKind(kind)}
                className="flex items-center gap-1.5 h-9 px-3 border border-border rounded-xl text-xs font-medium text-foreground hover:bg-muted transition-colors"
              >
                <Plus size={12} /> {KIND_LABEL[kind]}
              </button>
            ))}
          </div>
        }
      />

      {items.length === 0 ? (
        <EmptyState title="No items yet" hint="Add text, a quiz, flashcards, or a video." />
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((item, index) => {
            const Icon = KIND_ICON[item.kind]
            return (
              <div
                key={item.id}
                className="flex items-center justify-between p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="flex flex-col shrink-0">
                    <button
                      onClick={() => move(index, -1)}
                      disabled={index === 0 || reorderMutation.isPending}
                      className="text-muted-foreground hover:text-foreground disabled:opacity-25 transition-colors"
                      title="Move up"
                    >
                      <ArrowUp size={14} />
                    </button>
                    <button
                      onClick={() => move(index, 1)}
                      disabled={index === items.length - 1 || reorderMutation.isPending}
                      className="text-muted-foreground hover:text-foreground disabled:opacity-25 transition-colors"
                      title="Move down"
                    >
                      <ArrowDown size={14} />
                    </button>
                  </div>
                  <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                    <Icon size={16} className="text-primary" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {item.position}. {item.title ?? KIND_LABEL[item.kind]}
                    </p>
                    <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                      {KIND_LABEL[item.kind]}
                      {!item.is_required && " · optional"}
                      {item.kind === "video" && <VideoStatusBadge status={videoStatus(item)} />}
                    </p>
                    {item.kind === "video" && "transcode_error" in item.content && item.content.transcode_error && (
                      <p className="text-xs text-red-500 mt-0.5">{item.content.transcode_error}</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0 ml-3">
                  {item.kind === "video" && (
                    <button
                      onClick={() => setCheckpointTarget(item)}
                      className="h-8 px-3 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-muted transition-colors"
                    >
                      Checkpoints
                    </button>
                  )}
                  {item.kind === "video" && (
                    <button
                      onClick={() => setUploadTarget(item)}
                      className="h-8 px-3 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-muted transition-colors"
                    >
                      {videoStatus(item) === "ready" ? "Replace video" : "Upload video"}
                    </button>
                  )}
                  {item.kind !== "video" && (
                    <button
                      onClick={() => setEditItem(item)}
                      className="h-8 px-3 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-muted transition-colors"
                    >
                      Edit
                    </button>
                  )}
                  <button
                    onClick={() => setDeleteTarget(item)}
                    className="h-8 px-3 rounded-lg text-xs font-medium text-red-600 hover:bg-red-500/10 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {editModuleOpen && module && (
        <EditModuleModal
          module={module}
          onClose={() => setEditModuleOpen(false)}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ["lms-admin-module", moduleId] })
            setEditModuleOpen(false)
          }}
        />
      )}
      {addKind && (
        <ItemEditorModal
          moduleId={moduleId}
          kind={addKind}
          onClose={() => setAddKind(null)}
          onSuccess={() => { invalidate(); setAddKind(null) }}
        />
      )}
      {editItem && (
        <ItemEditorModal
          moduleId={moduleId}
          kind={editItem.kind}
          item={editItem}
          onClose={() => setEditItem(null)}
          onSuccess={() => { invalidate(); setEditItem(null) }}
        />
      )}
      {uploadTarget && (
        <VideoUploadModal item={uploadTarget} onClose={() => setUploadTarget(null)} onSuccess={() => { invalidate(); setUploadTarget(null) }} />
      )}
      {checkpointTarget && (
        <CheckpointsModal item={checkpointTarget} onClose={() => setCheckpointTarget(null)} />
      )}
      {deleteTarget && (
        <ConfirmDialog
          title={`Delete "${deleteTarget.title ?? KIND_LABEL[deleteTarget.kind]}"?`}
          description="Deletes any student progress on this item too."
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

function EditModuleModal({ module, onClose, onSuccess }: {
  module: AdminModule; onClose: () => void; onSuccess: () => void
}) {
  const [title, setTitle] = useState(module.title)
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () => updateModuleApi(module.id, { title: title.trim() }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to rename module"),
  })

  return (
    <Modal title="Rename module" onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="Title">
          <input
            value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending} disabled={!title.trim()} label="Save" />
      </div>
    </Modal>
  )
}

// ── item editor: dispatches to the right form by kind ───────────────────

function ItemEditorModal({ moduleId, kind, item, onClose, onSuccess }: {
  moduleId: string; kind: ModuleItemKind; item?: AdminItem; onClose: () => void; onSuccess: () => void
}) {
  if (kind === "video") {
    // Video content is always {} — real state lives in module_videos, set by
    // the upload endpoint. Creating the item is enough; upload happens after.
    return <VideoItemModal moduleId={moduleId} item={item} onClose={onClose} onSuccess={onSuccess} />
  }
  if (kind === "text") return <TextItemModal moduleId={moduleId} item={item} onClose={onClose} onSuccess={onSuccess} />
  if (kind === "flashcards") return <FlashcardsItemModal moduleId={moduleId} item={item} onClose={onClose} onSuccess={onSuccess} />
  return <QuizItemModal moduleId={moduleId} item={item} onClose={onClose} onSuccess={onSuccess} />
}

function VideoItemModal({ moduleId, item, onClose, onSuccess }: {
  moduleId: string; item?: AdminItem; onClose: () => void; onSuccess: () => void
}) {
  const [title, setTitle] = useState(item?.title ?? "")
  const [isRequired, setIsRequired] = useState(item?.is_required ?? true)
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () =>
      item
        ? updateItemApi(item.id, { title: title.trim() || undefined, is_required: isRequired })
        : createItemApi(moduleId, { kind: "video", title: title.trim() || undefined, is_required: isRequired, content: {} }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail?.toString?.() ?? "Failed to save item"),
  })

  return (
    <Modal title={item ? "Edit video" : "Add video"} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="Title (optional)">
          <input
            value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
          <input type="checkbox" checked={isRequired} onChange={(e) => setIsRequired(e.target.checked)} />
          Mandatory (blocks the next module until watched)
        </label>
        {!item && <p className="text-xs text-muted-foreground">Upload the actual video file from the module list after creating this item.</p>}
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending} disabled={false} label={item ? "Save changes" : "Add video"} />
      </div>
    </Modal>
  )
}

function VideoUploadModal({ item, onClose, onSuccess }: { item: AdminItem; onClose: () => void; onSuccess: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState("")
  const [result, setResult] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  const abortRef = useRef<AbortController | null>(null)

  const mutation = useMutation({
    mutationFn: () => {
      const controller = new AbortController()
      abortRef.current = controller
      setProgress(0)
      return uploadVideoApi(item.id, file!, { signal: controller.signal, onProgress: setProgress })
    },
    onSuccess: (res) => setResult(`Uploaded — status: ${res.transcode_status}. Transcoding will run in the background.`),
    onError: (e: any) => {
      abortRef.current = null
      if (e?.code === "ERR_CANCELED") { setError(""); return }
      setError(e?.response?.data?.detail ?? "Upload failed")
    },
  })

  const cancel = () => {
    abortRef.current?.abort()
    abortRef.current = null
  }

  return (
    <Modal title={`Upload video — ${item.title ?? "Video"}`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="Video file (MP4, up to 2GB)">
          <input
            type="file" accept="video/*"
            disabled={mutation.isPending}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="w-full text-sm text-foreground file:mr-3 file:h-9 file:px-3 file:rounded-lg file:border-0 file:bg-primary file:text-primary-foreground file:text-sm file:cursor-pointer disabled:opacity-50"
          />
        </Field>
        {mutation.isPending && (
          <div className="flex flex-col gap-1.5">
            <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
              <div className="h-full bg-primary transition-[width] duration-150" style={{ width: `${progress}%` }} />
            </div>
            <p className="text-xs text-muted-foreground">Uploading — {progress}%</p>
          </div>
        )}
        {result && <p className="text-xs text-primary">{result}</p>}
        {error && <p className="text-xs text-red-500">{error}</p>}
        {result ? (
          <button onClick={() => { onSuccess() }} className="h-10 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors">
            Done
          </button>
        ) : mutation.isPending ? (
          <button
            onClick={cancel}
            className="h-10 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
          >
            Cancel upload
          </button>
        ) : (
          <ModalActions onCancel={onClose} onConfirm={() => mutation.mutate()} loading={false} disabled={!file} label="Upload" />
        )}
      </div>
    </Modal>
  )
}

function TextItemModal({ moduleId, item, onClose, onSuccess }: {
  moduleId: string; item?: AdminItem; onClose: () => void; onSuccess: () => void
}) {
  const existingBody = item && "body" in item.content ? item.content.body : ""
  const [title, setTitle] = useState(item?.title ?? "")
  const [body, setBody] = useState(existingBody)
  const [isRequired, setIsRequired] = useState(item?.is_required ?? true)
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () =>
      item
        ? updateItemApi(item.id, { title: title.trim() || undefined, is_required: isRequired, content: { body } })
        : createItemApi(moduleId, { kind: "text", title: title.trim() || undefined, is_required: isRequired, content: { body } }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail?.toString?.() ?? "Failed to save item"),
  })

  return (
    <Modal title={item ? "Edit text" : "Add text"} onClose={onClose} maxWidth="sm:max-w-xl max-w-xl">
      <div className="flex flex-col gap-3">
        <Field label="Title (optional)">
          <input
            value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Body">
          <textarea
            value={body} onChange={(e) => setBody(e.target.value)} rows={8}
            className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors resize-none"
          />
        </Field>
        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
          <input type="checkbox" checked={isRequired} onChange={(e) => setIsRequired(e.target.checked)} />
          Mandatory
        </label>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending} disabled={!body.trim()} label={item ? "Save changes" : "Add text"} />
      </div>
    </Modal>
  )
}

function FlashcardsItemModal({ moduleId, item, onClose, onSuccess }: {
  moduleId: string; item?: AdminItem; onClose: () => void; onSuccess: () => void
}) {
  const existing = item && "cards" in item.content ? item.content : null
  const [title, setTitle] = useState(item?.title ?? existing?.title ?? "")
  const [cards, setCards] = useState(existing?.cards?.length ? existing.cards : [{ term: "", definition: "" }])
  const [isRequired, setIsRequired] = useState(item?.is_required ?? false)
  const [error, setError] = useState("")

  const validCards = cards.filter((c) => c.term.trim() && c.definition.trim())

  const mutation = useMutation({
    mutationFn: () => {
      const content = { title: title.trim() || null, cards: validCards }
      return item
        ? updateItemApi(item.id, { title: title.trim() || undefined, is_required: isRequired, content })
        : createItemApi(moduleId, { kind: "flashcards", title: title.trim() || undefined, is_required: isRequired, content })
    },
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail?.toString?.() ?? "Failed to save item"),
  })

  return (
    <Modal title={item ? "Edit flashcards" : "Add flashcards"} onClose={onClose} maxWidth="sm:max-w-xl max-w-xl">
      <div className="flex flex-col gap-3">
        <Field label="Title (optional)">
          <input
            value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Cards">
          <div className="flex flex-col gap-2">
            {cards.map((card, i) => (
              <div key={i} className="flex gap-2">
                <input
                  value={card.term} placeholder="Term"
                  onChange={(e) => setCards((prev) => prev.map((c, idx) => (idx === i ? { ...c, term: e.target.value } : c)))}
                  className="flex-1 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                />
                <input
                  value={card.definition} placeholder="Definition"
                  onChange={(e) => setCards((prev) => prev.map((c, idx) => (idx === i ? { ...c, definition: e.target.value } : c)))}
                  className="flex-1 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                />
                <button
                  onClick={() => setCards((prev) => prev.filter((_, idx) => idx !== i))}
                  disabled={cards.length === 1}
                  className="h-10 px-3 text-xs text-red-600 hover:bg-red-500/10 rounded-lg transition-colors disabled:opacity-30"
                >
                  Remove
                </button>
              </div>
            ))}
            <button
              onClick={() => setCards((prev) => [...prev, { term: "", definition: "" }])}
              className="h-9 px-3 border border-dashed border-border rounded-xl text-xs font-medium text-muted-foreground hover:bg-muted transition-colors w-fit"
            >
              + Add card
            </button>
          </div>
        </Field>
        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
          <input type="checkbox" checked={isRequired} onChange={(e) => setIsRequired(e.target.checked)} />
          Mandatory
        </label>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending} disabled={validCards.length === 0} label={item ? "Save changes" : "Add flashcards"} />
      </div>
    </Modal>
  )
}

function QuizItemModal({ moduleId, item, onClose, onSuccess }: {
  moduleId: string; item?: AdminItem; onClose: () => void; onSuccess: () => void
}) {
  const existing = item && "questions" in item.content ? item.content : null
  const [title, setTitle] = useState(item?.title ?? "")
  const [passThreshold, setPassThreshold] = useState(existing?.pass_threshold ?? 0)
  const [isRequired, setIsRequired] = useState(item?.is_required ?? true)
  const [questions, setQuestions] = useState<AdminQuizQuestion[]>(
    existing?.questions?.length
      ? existing.questions
      : [{ prompt: "", explanation: "", options: [{ text: "", is_correct: true }, { text: "", is_correct: false }] }],
  )
  const [error, setError] = useState("")

  const updateQuestion = (qi: number, patch: Partial<AdminQuizQuestion>) =>
    setQuestions((prev) => prev.map((q, idx) => (idx === qi ? { ...q, ...patch } : q)))

  const updateOption = (qi: number, oi: number, patch: Partial<{ text: string; is_correct: boolean }>) =>
    setQuestions((prev) =>
      prev.map((q, idx) => idx !== qi ? q : { ...q, options: q.options.map((o, oidx) => (oidx === oi ? { ...o, ...patch } : o)) }),
    )

  const valid = questions.every((q) => q.prompt.trim() && q.options.filter((o) => o.text.trim()).length >= 2 && q.options.some((o) => o.is_correct))

  const mutation = useMutation({
    mutationFn: () => {
      const content = {
        pass_threshold: passThreshold,
        questions: questions.map((q) => ({ ...q, options: q.options.filter((o) => o.text.trim()) })),
      }
      return item
        ? updateItemApi(item.id, { title: title.trim() || undefined, is_required: isRequired, content })
        : createItemApi(moduleId, { kind: "quiz", title: title.trim() || undefined, is_required: isRequired, content })
    },
    onSuccess,
    onError: (e: any) => setError(JSON.stringify(e?.response?.data?.detail) ?? "Failed to save item"),
  })

  return (
    <Modal title={item ? "Edit quiz" : "Add quiz"} onClose={onClose} maxWidth="sm:max-w-2xl max-w-2xl">
      <div className="flex flex-col gap-4">
        <Field label="Title (optional)">
          <input
            value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Pass threshold (0 = any grade passes)">
          <input
            type="number" min={0} max={100} value={passThreshold}
            onChange={(e) => setPassThreshold(Number(e.target.value))}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>

        <div className="flex flex-col gap-3">
          {questions.map((q, qi) => (
            <div key={qi} className="p-3 border border-border rounded-xl flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">Question {qi + 1}</span>
                <button
                  onClick={() => setQuestions((prev) => prev.filter((_, idx) => idx !== qi))}
                  disabled={questions.length === 1}
                  className="text-xs text-red-600 hover:bg-red-500/10 rounded px-2 py-0.5 transition-colors disabled:opacity-30"
                >
                  Remove
                </button>
              </div>
              <input
                value={q.prompt} placeholder="Question prompt"
                onChange={(e) => updateQuestion(qi, { prompt: e.target.value })}
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
              <input
                value={q.explanation ?? ""} placeholder="Explanation shown after a wrong answer (optional)"
                onChange={(e) => updateQuestion(qi, { explanation: e.target.value })}
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
              <div className="flex flex-col gap-1.5">
                {q.options.map((opt, oi) => (
                  <div key={oi} className="flex items-center gap-2">
                    <input
                      type="checkbox" checked={opt.is_correct} title="Correct answer"
                      onChange={(e) => updateOption(qi, oi, { is_correct: e.target.checked })}
                    />
                    <input
                      value={opt.text} placeholder={`Option ${oi + 1}`}
                      onChange={(e) => updateOption(qi, oi, { text: e.target.value })}
                      className="flex-1 h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                    />
                    <button
                      onClick={() => updateQuestion(qi, { options: q.options.filter((_, idx) => idx !== oi) })}
                      disabled={q.options.length <= 2}
                      className="text-xs text-red-600 hover:bg-red-500/10 rounded px-2 py-1 transition-colors disabled:opacity-30"
                    >
                      Remove
                    </button>
                  </div>
                ))}
                <button
                  onClick={() => updateQuestion(qi, { options: [...q.options, { text: "", is_correct: false }] })}
                  className="h-8 px-3 border border-dashed border-border rounded-xl text-xs font-medium text-muted-foreground hover:bg-muted transition-colors w-fit"
                >
                  + Add option
                </button>
              </div>
            </div>
          ))}
          <button
            onClick={() => setQuestions((prev) => [...prev, { prompt: "", explanation: "", options: [{ text: "", is_correct: true }, { text: "", is_correct: false }] }])}
            className="h-9 px-3 border border-dashed border-border rounded-xl text-xs font-medium text-muted-foreground hover:bg-muted transition-colors w-fit"
          >
            + Add question
          </button>
        </div>

        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
          <input type="checkbox" checked={isRequired} onChange={(e) => setIsRequired(e.target.checked)} />
          Mandatory
        </label>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending} disabled={!valid} label={item ? "Save changes" : "Add quiz"} />
      </div>
    </Modal>
  )
}

// ── video checkpoints (timeline notes + mid-video quizzes) ─────────────────

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, "0")}`
}

function checkpointPreview(c: AdminCheckpoint): string {
  if (c.kind === "note") return "body" in c.content ? c.content.body : ""
  return "prompt" in c.content ? c.content.prompt : ""
}

function CheckpointsModal({ item, onClose }: { item: AdminItem; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [formTarget, setFormTarget] = useState<AdminCheckpoint | "new" | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AdminCheckpoint | null>(null)

  const queryKey = ["lms-admin-checkpoints", item.id]
  const { data: checkpoints = [], isLoading } = useQuery<AdminCheckpoint[]>({
    queryKey, queryFn: () => listCheckpointsApi(item.id),
  })
  const invalidate = () => queryClient.invalidateQueries({ queryKey })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteCheckpointApi(id),
    onSuccess: () => { setDeleteTarget(null); invalidate() },
  })

  const sorted = [...checkpoints].sort((a, b) => a.start_seconds - b.start_seconds)

  return (
    <Modal title={`Checkpoints — ${item.title ?? "Video"}`} onClose={onClose} maxWidth="sm:max-w-xl max-w-xl">
      <div className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">
          A note is a banner shown for a time range without stopping playback. A quiz pauses
          the video at a single moment until answered or skipped.
        </p>
        {isLoading ? (
          <Spinner />
        ) : sorted.length === 0 ? (
          <EmptyState title="No checkpoints yet" hint="Add a note or a quiz tied to a moment in this video." />
        ) : (
          <div className="flex flex-col gap-2">
            {sorted.map((c) => (
              <div
                key={c.id}
                className="flex items-center gap-3 p-3 bg-card border border-border rounded-xl"
              >
                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 text-primary">
                  {c.kind === "note" ? <StickyNote size={14} /> : <MessageCircleQuestion size={14} />}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-mono text-muted-foreground">
                    {formatTime(c.start_seconds)}
                    {c.kind === "note" && c.end_seconds != null && ` – ${formatTime(c.end_seconds)}`}
                  </p>
                  <p className="text-sm text-foreground truncate">{checkpointPreview(c)}</p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => setFormTarget(c)}
                    className="h-8 px-3 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-muted transition-colors"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => setDeleteTarget(c)}
                    className="h-8 px-3 rounded-lg text-xs font-medium text-red-600 hover:bg-red-500/10 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
        <button
          onClick={() => setFormTarget("new")}
          className="h-9 px-3 border border-dashed border-border rounded-xl text-xs font-medium text-muted-foreground hover:bg-muted transition-colors w-fit"
        >
          <Plus size={12} className="inline -mt-0.5 mr-1" /> Add checkpoint
        </button>
        <ModalActions onCancel={onClose} onConfirm={onClose} loading={false} disabled={false} label="Done" />
      </div>

      {formTarget && (
        <CheckpointFormModal
          videoItemId={item.id}
          checkpoint={formTarget === "new" ? undefined : formTarget}
          onClose={() => setFormTarget(null)}
          onSuccess={() => { invalidate(); setFormTarget(null) }}
        />
      )}
      {deleteTarget && (
        <ConfirmDialog
          title="Delete this checkpoint?"
          description="Students won't see it on the video timeline anymore."
          confirmLabel="Delete"
          destructive
          pending={deleteMutation.isPending}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
        />
      )}
    </Modal>
  )
}

function CheckpointFormModal({ videoItemId, checkpoint, onClose, onSuccess }: {
  videoItemId: string; checkpoint?: AdminCheckpoint; onClose: () => void; onSuccess: () => void
}) {
  const existingNoteBody = checkpoint && "body" in checkpoint.content ? checkpoint.content.body : ""
  const existingQuiz = checkpoint && "question_type" in checkpoint.content ? checkpoint.content : null

  // Kind is immutable once created (matches the backend — VideoCheckpointUpdate has no `kind`).
  const [kind, setKind] = useState<CheckpointKind>(checkpoint?.kind ?? "note")
  const [startSeconds, setStartSeconds] = useState(String(checkpoint?.start_seconds ?? 0))
  const [endSeconds, setEndSeconds] = useState(
    checkpoint?.end_seconds != null ? String(checkpoint.end_seconds) : "",
  )
  const [body, setBody] = useState(existingNoteBody)
  const [questionType, setQuestionType] = useState<CheckpointQuestionType>(existingQuiz?.question_type ?? "mcq")
  const [prompt, setPrompt] = useState(existingQuiz?.prompt ?? "")
  const [explanation, setExplanation] = useState(existingQuiz?.explanation ?? "")
  const [options, setOptions] = useState<AdminQuizOption[]>(
    existingQuiz?.options?.length ? existingQuiz.options : [{ text: "", is_correct: false }, { text: "", is_correct: false }],
  )
  const [error, setError] = useState("")

  const setOptionCorrect = (index: number, checked: boolean) => {
    setOptions((prev) =>
      prev.map((o, i) => {
        if (i !== index) return questionType === "mcq" ? { ...o, is_correct: false } : o
        return { ...o, is_correct: checked }
      }),
    )
  }

  const valid = kind === "note"
    ? body.trim() && endSeconds.trim() && Number(endSeconds) > Number(startSeconds)
    : questionType === "open"
      ? prompt.trim()
      : prompt.trim() && options.filter((o) => o.text.trim()).length >= 2 && options.some((o) => o.is_correct)

  const mutation = useMutation({
    mutationFn: () => {
      const content = kind === "note"
        ? { body: body.trim() }
        : questionType === "open"
          ? { question_type: "open", prompt: prompt.trim() }
          : {
            question_type: questionType, prompt: prompt.trim(), explanation: explanation.trim() || null,
            options: options.filter((o) => o.text.trim()),
          }
      const payload = {
        start_seconds: Number(startSeconds),
        end_seconds: kind === "note" ? Number(endSeconds) : null,
        content,
      }
      return checkpoint
        ? updateCheckpointApi(checkpoint.id, payload)
        : createCheckpointApi(videoItemId, { ...payload, kind })
    },
    onSuccess,
    onError: (e: any) => setError(JSON.stringify(e?.response?.data?.detail) ?? "Failed to save checkpoint"),
  })

  return (
    <Modal title={checkpoint ? "Edit checkpoint" : "Add checkpoint"} onClose={onClose} maxWidth="sm:max-w-lg max-w-lg">
      <div className="flex flex-col gap-3">
        {!checkpoint && (
          <Field label="Type">
            <div className="flex gap-2">
              {(["note", "quiz"] as CheckpointKind[]).map((k) => (
                <button
                  key={k}
                  onClick={() => setKind(k)}
                  className={`flex-1 h-10 rounded-xl text-sm font-medium border transition-colors capitalize ${
                    kind === k ? "border-primary bg-primary/10 text-primary" : "border-border text-foreground hover:bg-muted"
                  }`}
                >
                  {k}
                </button>
              ))}
            </div>
          </Field>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Start (seconds)">
            <input
              type="number" min={0} value={startSeconds} autoFocus
              onChange={(e) => setStartSeconds(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          {kind === "note" && (
            <Field label="End (seconds)">
              <input
                type="number" min={0} value={endSeconds}
                onChange={(e) => setEndSeconds(e.target.value)}
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </Field>
          )}
        </div>

        {kind === "note" ? (
          <Field label="Note text">
            <textarea
              value={body} onChange={(e) => setBody(e.target.value)} rows={3}
              placeholder="Shown as a banner over the video during this window"
              className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors resize-none"
            />
          </Field>
        ) : (
          <>
            <Field label="Question type">
              <select
                value={questionType} onChange={(e) => setQuestionType(e.target.value as CheckpointQuestionType)}
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
              >
                <option value="mcq">Multiple choice (one answer)</option>
                <option value="multiselect">Multiple choice (select all)</option>
                <option value="open">Open question (not graded)</option>
              </select>
            </Field>
            <Field label="Prompt">
              <input
                value={prompt} onChange={(e) => setPrompt(e.target.value)}
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </Field>
            {questionType !== "open" && (
              <>
                <Field label="Explanation shown after answering (optional)">
                  <input
                    value={explanation} onChange={(e) => setExplanation(e.target.value)}
                    className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                  />
                </Field>
                <Field label={questionType === "mcq" ? "Options (pick one correct)" : "Options (pick any number correct)"}>
                  <div className="flex flex-col gap-1.5">
                    {options.map((opt, oi) => (
                      <div key={oi} className="flex items-center gap-2">
                        <input
                          type={questionType === "mcq" ? "radio" : "checkbox"}
                          name="checkpoint-correct"
                          checked={opt.is_correct} title="Correct answer"
                          onChange={(e) => setOptionCorrect(oi, e.target.checked)}
                        />
                        <input
                          value={opt.text} placeholder={`Option ${oi + 1}`}
                          onChange={(e) => setOptions((prev) => prev.map((o, i) => (i === oi ? { ...o, text: e.target.value } : o)))}
                          className="flex-1 h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                        />
                        <button
                          onClick={() => setOptions((prev) => prev.filter((_, i) => i !== oi))}
                          disabled={options.length <= 2}
                          className="text-xs text-red-600 hover:bg-red-500/10 rounded px-2 py-1 transition-colors disabled:opacity-30"
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                    <button
                      onClick={() => setOptions((prev) => [...prev, { text: "", is_correct: false }])}
                      className="h-8 px-3 border border-dashed border-border rounded-xl text-xs font-medium text-muted-foreground hover:bg-muted transition-colors w-fit"
                    >
                      + Add option
                    </button>
                  </div>
                </Field>
              </>
            )}
          </>
        )}

        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending}
          disabled={!valid} label={checkpoint ? "Save changes" : "Add checkpoint"}
        />
      </div>
    </Modal>
  )
}
