import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useParams } from "@tanstack/react-router"
import { Plus, ArrowLeft, FileText, HelpCircle, Layers, Video as VideoIcon } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Modal, Field, ModalActions, ConfirmDialog } from "@/pages/admin/components/common"
import {
  listItemsApi, createItemApi, updateItemApi, deleteItemApi, uploadVideoApi,
  type AdminItem, type ModuleItemKind, type AdminQuizQuestion,
} from "@/api/lms_admin"

const KIND_ICON: Record<ModuleItemKind, React.ComponentType<{ size?: number; className?: string }>> = {
  text: FileText, quiz: HelpCircle, flashcards: Layers, video: VideoIcon,
}
const KIND_LABEL: Record<ModuleItemKind, string> = {
  text: "Text", quiz: "Quiz", flashcards: "Flashcards", video: "Video",
}

export default function LmsModuleDetail() {
  const { moduleId } = useParams({ strict: false }) as { moduleId: string }
  const queryClient = useQueryClient()
  const [addKind, setAddKind] = useState<ModuleItemKind | null>(null)
  const [editItem, setEditItem] = useState<AdminItem | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AdminItem | null>(null)
  const [uploadTarget, setUploadTarget] = useState<AdminItem | null>(null)

  const { data: items = [], isLoading } = useQuery<AdminItem[]>({
    queryKey: ["lms-admin-items", moduleId],
    queryFn: () => listItemsApi(moduleId),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-items", moduleId] })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteItemApi(id),
    onSuccess: () => { setDeleteTarget(null); invalidate() },
  })

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
        title="Module items"
        subtitle="Add lessons in the order students should see them."
        action={
          <div className="flex gap-2">
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
          {items.map((item) => {
            const Icon = KIND_ICON[item.kind]
            return (
              <div
                key={item.id}
                className="flex items-center justify-between p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                    <Icon size={16} className="text-primary" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {item.position}. {item.title ?? KIND_LABEL[item.kind]}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {KIND_LABEL[item.kind]}
                      {!item.is_required && " · optional"}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0 ml-3">
                  {item.kind === "video" && (
                    <button
                      onClick={() => setUploadTarget(item)}
                      className="h-8 px-3 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-muted transition-colors"
                    >
                      Upload video
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

  const mutation = useMutation({
    mutationFn: () => uploadVideoApi(item.id, file!),
    onSuccess: (res) => setResult(`Uploaded — status: ${res.transcode_status}. Transcoding will run in the background.`),
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Upload failed"),
  })

  return (
    <Modal title={`Upload video — ${item.title ?? "Video"}`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="Video file (MP4, up to 2GB)">
          <input
            type="file" accept="video/*"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="w-full text-sm text-foreground file:mr-3 file:h-9 file:px-3 file:rounded-lg file:border-0 file:bg-primary file:text-primary-foreground file:text-sm file:cursor-pointer"
          />
        </Field>
        {result && <p className="text-xs text-primary">{result}</p>}
        {error && <p className="text-xs text-red-500">{error}</p>}
        {result ? (
          <button onClick={() => { onSuccess() }} className="h-10 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors">
            Done
          </button>
        ) : (
          <ModalActions onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending} disabled={!file} label="Upload" />
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
  const [midVideoSeconds, setMidVideoSeconds] = useState(
    existing?.mid_video_at_seconds != null ? String(existing.mid_video_at_seconds) : "",
  )
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
        mid_video_at_seconds: midVideoSeconds.trim() ? Number(midVideoSeconds) : null,
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
        <div className="flex gap-3">
          <Field label="Pass threshold (0 = any grade passes)">
            <input
              type="number" min={0} max={100} value={passThreshold}
              onChange={(e) => setPassThreshold(Number(e.target.value))}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          <Field label="Mid-video checkpoint, seconds (optional)">
            <input
              type="number" min={0} value={midVideoSeconds}
              onChange={(e) => setMidVideoSeconds(e.target.value)}
              placeholder="e.g. 90"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
        </div>

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
