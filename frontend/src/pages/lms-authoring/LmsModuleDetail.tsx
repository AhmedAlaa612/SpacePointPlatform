import { useEffect, useRef, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useParams } from "@tanstack/react-router"
import {
  Plus, Pencil, ArrowLeft, ArrowUp, ArrowDown, FileText, HelpCircle, Layers, Video as VideoIcon, Loader2,
  StickyNote, MessageCircleQuestion, Paperclip, Upload, Image as ImageIcon, Code2, Cpu, Trash2,
} from "lucide-react"
import { EmptyState, Spinner } from "@/components/ui/primitives"
import { Modal, Field, ModalActions, ConfirmDialog } from "@/pages/admin/components/common"
import {
  listItemsApi, createItemApi, updateItemApi, deleteItemApi, uploadVideoApi, reorderItemsApi,
  listCheckpointsApi, createCheckpointApi, updateCheckpointApi, deleteCheckpointApi,
  getModuleApi, updateModuleApi, uploadAttachmentApi, getAdminAttachmentUrlApi, uploadQuizImageApi,
  type AdminItem, type ModuleItemKind, type AdminQuizQuestion, type VideoTranscodeStatus,
  type AdminCheckpoint, type CheckpointKind, type CheckpointQuestionType, type AdminQuizOption,
  type AdminModule,
} from "@/api/lms_admin"
import { resolveQuizImageUrl } from "@/api/lms"
import { MediaPreviewModal } from "@/components/media/MediaPreviewModal"
import { MarkdownToolbar } from "@/components/lms/MarkdownToolbar"
import { MarkdownContent } from "@/components/lms/MarkdownContent"
import { CodePracticeBlock } from "@/components/lms/interactive/CodePracticeBlock"
import { HardwareLabBlock } from "@/components/lms/interactive/HardwareLabBlock"
import { cn } from "@/lib/utils"

const KIND_ICON: Record<ModuleItemKind, React.ComponentType<{ size?: number; className?: string }>> = {
  text: FileText, quiz: HelpCircle, flashcards: Layers, video: VideoIcon, attachment: Paperclip,
  practice: Code2, lab: Cpu,
}
const KIND_LABEL: Record<ModuleItemKind, string> = {
  text: "Reading", quiz: "Quiz", flashcards: "Flashcards", video: "Video", attachment: "Attachment",
  practice: "Code Practice", lab: "Hardware Lab",
}

function attachmentFilename(item: AdminItem): string | null {
  return "filename" in item.content ? (item.content.filename ?? null) : null
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
  const [previewModal, setPreviewModal] = useState<{
    open: boolean
    title: string
    type: "pdf" | "video"
    url?: string | null
    itemId?: string
    videoId?: string | null
    transcodeStatus?: string | null
  }>({ open: false, title: "", type: "pdf" })
  const [previewLoadingId, setPreviewLoadingId] = useState<string | null>(null)

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

      <div className="flex flex-col gap-3 mb-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight truncate">
              {module ? module.title : "Module items"}
            </h1>
            <p className="text-sm text-muted-foreground mt-1">Add lessons in the order students should see them.</p>
          </div>
          {module && (
            <button
              onClick={() => setEditModuleOpen(true)}
              className="flex items-center gap-1.5 h-9 px-3 border border-border rounded-xl text-xs font-medium text-foreground hover:bg-muted transition-colors shrink-0"
            >
              <Pencil size={12} /> Rename
            </button>
          )}
        </div>
        {/* Scrolls horizontally on narrow screens instead of overflowing the
            page or wrapping into a cramped stack — five "Add X" buttons don't
            fit a phone's width at their natural size. */}
        <div className="flex gap-2 flex-wrap">
          {(["text", "flashcards", "quiz", "video", "attachment", "practice", "lab"] as ModuleItemKind[]).map((kind) => (
            <button
              key={kind}
              onClick={() => setAddKind(kind)}
              className="flex items-center gap-1.5 h-9 px-3 border border-border rounded-xl text-xs font-medium text-foreground hover:bg-muted transition-colors shrink-0 whitespace-nowrap"
            >
              <Plus size={12} /> {KIND_LABEL[kind]}
            </button>
          ))}
        </div>
      </div>

      {items.length === 0 ? (
        <EmptyState title="No items yet" hint="Add a reading, a quiz, flashcards, or a video." />
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((item, index) => {
            const Icon = KIND_ICON[item.kind]
            return (
              <div
                key={item.id}
                className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0 flex-1">
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
                  <div className="min-w-0 flex-1">
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
                    {item.kind === "attachment" && (
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {attachmentFilename(item) ?? "No file uploaded yet"}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1.5 flex-wrap sm:justify-end">
                  {item.kind === "video" && videoStatus(item) === "ready" && (
                    <button
                      onClick={() => setPreviewModal({
                        open: true,
                        title: item.title ?? "Video lesson",
                        type: "video",
                        itemId: item.id,
                        videoId: "video_id" in item.content ? (item.content.video_id as string) : null,
                        transcodeStatus: videoStatus(item),
                      })}
                      className="h-8 px-2.5 rounded-lg text-xs font-medium bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 transition-colors shrink-0 whitespace-nowrap"
                    >
                      Watch video
                    </button>
                  )}
                  {item.kind === "video" && (
                    <button
                      onClick={() => setCheckpointTarget(item)}
                      className="h-8 px-2.5 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-muted transition-colors shrink-0 whitespace-nowrap"
                    >
                      Checkpoints
                    </button>
                  )}
                  {item.kind === "video" && (
                    <button
                      onClick={() => setUploadTarget(item)}
                      className="h-8 px-2.5 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-muted transition-colors shrink-0 whitespace-nowrap"
                    >
                      {videoStatus(item) === "ready" ? "Replace video" : "Upload video"}
                    </button>
                  )}
                  {item.kind === "attachment" && attachmentFilename(item) && (
                    <button
                      disabled={previewLoadingId === item.id}
                      onClick={async () => {
                        setPreviewLoadingId(item.id)
                        try {
                          const res = await getAdminAttachmentUrlApi(item.id)
                          setPreviewModal({
                            open: true,
                            title: item.title ?? attachmentFilename(item) ?? "PDF Document",
                            type: "pdf",
                            url: res.url,
                          })
                        } catch {
                          alert("Failed to load PDF preview")
                        } finally {
                          setPreviewLoadingId(null)
                        }
                      }}
                      className="h-8 px-2.5 rounded-lg text-xs font-medium bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 transition-colors shrink-0 whitespace-nowrap disabled:opacity-50"
                    >
                      {previewLoadingId === item.id ? "Loading..." : "View PDF"}
                    </button>
                  )}
                  {item.kind === "attachment" && (
                    <button
                      onClick={() => setUploadTarget(item)}
                      className="h-8 px-2.5 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-muted transition-colors shrink-0 whitespace-nowrap"
                    >
                      {attachmentFilename(item) ? "Replace PDF" : "Upload PDF"}
                    </button>
                  )}
                  <button
                    onClick={() => setEditItem(item)}
                    className="h-8 px-2.5 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-muted transition-colors shrink-0 whitespace-nowrap"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => setDeleteTarget(item)}
                    className="h-8 px-2.5 rounded-lg text-xs font-medium text-red-600 hover:bg-red-500/10 transition-colors shrink-0 whitespace-nowrap"
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
      {uploadTarget && uploadTarget.kind === "video" && (
        <VideoUploadModal item={uploadTarget} onClose={() => setUploadTarget(null)} onSuccess={() => { invalidate(); setUploadTarget(null) }} />
      )}
      {uploadTarget && uploadTarget.kind === "attachment" && (
        <AttachmentUploadModal item={uploadTarget} onClose={() => setUploadTarget(null)} onSuccess={() => { invalidate(); setUploadTarget(null) }} />
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

      {previewModal.open && (
        <MediaPreviewModal
          open={previewModal.open}
          onClose={() => setPreviewModal((prev) => ({ ...prev, open: false }))}
          title={previewModal.title}
          type={previewModal.type}
          url={previewModal.url}
          itemId={previewModal.itemId}
          videoId={previewModal.videoId}
          transcodeStatus={previewModal.transcodeStatus}
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
  if (kind === "attachment") {
    // Same story as video — content is empty until the upload endpoint
    // fills it in. This modal only ever sets the title.
    return <AttachmentItemModal moduleId={moduleId} item={item} onClose={onClose} onSuccess={onSuccess} />
  }
  if (kind === "practice") return <PracticeItemModal moduleId={moduleId} item={item} onClose={onClose} onSuccess={onSuccess} />
  if (kind === "lab") return <LabItemModal moduleId={moduleId} item={item} onClose={onClose} onSuccess={onSuccess} />
  return <QuizItemModal moduleId={moduleId} item={item} onClose={onClose} onSuccess={onSuccess} />
}

function PracticeItemModal({ moduleId, item, onClose, onSuccess }: {
  moduleId: string; item?: AdminItem; onClose: () => void; onSuccess: () => void
}) {
  const practiceContent = item && "template" in item.content ? (item.content as any) : {}
  const [title, setTitle] = useState(item?.title ?? "")
  const [markdown, setMarkdown] = useState(practiceContent.markdown || practiceContent.instructions || "")
  const [template, setTemplate] = useState(practiceContent.template ?? "void setup() {\n  {{TOKEN}} = 10;\n}")
  const [maxAttempts, setMaxAttempts] = useState(practiceContent.max_attempts ?? 3)
  const [isRequired, setIsRequired] = useState(item?.is_required ?? true)
  const [hwEnabled, setHwEnabled] = useState(practiceContent.hardware_selector?.enabled ?? false)
  const [hwDefault, setHwDefault] = useState(practiceContent.hardware_selector?.default_address ?? "0x49")
  const [hwAddresses, setHwAddresses] = useState(
    (practiceContent.hardware_selector?.addresses || ["0x48", "0x49", "0x4A", "0x4B"]).join(", ")
  )
  const [activeTab, setActiveTab] = useState<"edit" | "preview">("edit")

  // Extract unique tokens from code template in order of appearance (supports {{TOKEN}}, {{token}}, {{ somthing }})
  const extractTokens = (code: string): string[] => {
    const matches = code.match(/\{\{\s*[\w-]+\s*\}\}/g)
    if (!matches) return []
    return Array.from(new Set<string>(matches))
  }

  // Initialize blanks matching the template tokens
  const [blanks, setBlanks] = useState<Array<{
    token: string; label: string; validator_pattern: string; correct_answer: string; hint: string
  }>>(() => {
    const initialTpl = practiceContent.template ?? "void setup() {\n  {{TOKEN}} = 10;\n}"
    const detected: string[] = Array.from(new Set<string>(initialTpl.match(/\{\{\s*[\w-]+\s*\}\}/g) || []))
    const existing: any[] = practiceContent.blanks || []
    const map = new Map<string, any>(existing.map((b: any) => [b.token, b]))

    if (detected.length > 0) {
      return detected.map((tok: string) => {
        const found = map.get(tok) || map.get(tok.trim())
        return {
          token: tok,
          label: (found?.label as string) || tok.replace(/[{}]/g, "").trim(),
          validator_pattern: (found?.validator_pattern as string) || "",
          correct_answer: (found?.correct_answer as string) || "",
          hint: (found?.hint as string) || "",
        }
      })
    }
    return [{ token: "{{TOKEN}}", label: "TOKEN", validator_pattern: "", correct_answer: "", hint: "" }]
  })
  const [error, setError] = useState("")

  // Auto-synchronize blanks whenever code template changes
  const handleTemplateChange = (newCode: string) => {
    setTemplate(newCode)
    const detected = extractTokens(newCode)
    setBlanks((prev) => {
      const map = new Map<string, typeof prev[0]>(prev.map((b) => [b.token, b]))
      return detected.map((tok: string) => {
        if (map.has(tok)) return map.get(tok)!
        const cleanName = tok.replace(/[{}]/g, "").trim()
        return {
          token: tok,
          label: cleanName,
          validator_pattern: "",
          correct_answer: "",
          hint: "",
        }
      })
    })
  }

  const insertBlank = () => {
    const detected = extractTokens(template)
    const nextNum = detected.length + 1
    const token = `{{BLANK_${nextNum}}}`
    handleTemplateChange(`${template} ${token}`)
  }

  const removeBlank = (tokenToRemove: string) => {
    const newTpl = template.replaceAll(tokenToRemove, "")
    handleTemplateChange(newTpl)
  }

  const updateBlank = (idx: number, patch: Partial<typeof blanks[0]>) => {
    setBlanks((prev) => prev.map((b, i) => (i === idx ? { ...b, ...patch } : b)))
  }

  const handleInsertMarkdown = (prefix: string, suffix = "", placeholder = "") => {
    setMarkdown((prev: string) => `${prev ? prev + "\n" : ""}${prefix}${placeholder}${suffix}\n`)
  }

  // Token configuration validation
  const unconfiguredBlanks = blanks.filter(
    (b) => !b.label.trim() || (!b.validator_pattern.trim() && !b.correct_answer.trim())
  )
  const isAllConfigured = blanks.length > 0 && unconfiguredBlanks.length === 0

  const mutation = useMutation({
    mutationFn: () => {
      if (unconfiguredBlanks.length > 0) {
        throw new Error(
          `Please configure all detected tokens before saving: ${unconfiguredBlanks.map((b) => b.token).join(", ")}`
        )
      }
      if (blanks.length === 0) {
        throw new Error("Add at least one {{TOKEN}} in the code template.")
      }

      const payload = {
        template,
        markdown: markdown.trim() || undefined,
        instructions: markdown.trim() || undefined,
        max_attempts: Number(maxAttempts) || 3,
        blanks: blanks.map((b) => ({
          token: b.token.trim(),
          label: b.label.trim() || undefined,
          validator_pattern: b.validator_pattern.trim() || (b.correct_answer ? `^${b.correct_answer.trim()}$` : ""),
          correct_answer: b.correct_answer.trim() || b.validator_pattern.trim(),
          hint: b.hint.trim() || undefined,
        })),
        hardware_selector: hwEnabled
          ? {
              enabled: true,
              default_address: hwDefault.trim() || "0x49",
              addresses: hwAddresses.split(",").map((s: string) => s.trim()).filter(Boolean),
            }
          : undefined,
      }
      return item
        ? updateItemApi(item.id, { title: title.trim() || undefined, is_required: isRequired, content: payload })
        : createItemApi(moduleId, { kind: "practice", title: title.trim() || undefined, is_required: isRequired, content: payload })
    },
    onSuccess,
    onError: (e: any) => setError(e?.message || e?.response?.data?.detail?.toString?.() || "Failed to save practice exercise"),
  })

  return (
    <Modal title={item ? "Edit code practice" : "Add code practice"} onClose={onClose} maxWidth="max-w-6xl sm:max-w-6xl w-full">
      <div className="flex flex-col gap-3">
        {/* Mobile Tab Toggle */}
        <div className="flex lg:hidden items-center p-1 bg-muted rounded-xl border border-border">
          <button
            type="button"
            onClick={() => setActiveTab("edit")}
            className={cn("flex-1 py-1.5 text-xs font-semibold rounded-lg transition-all", activeTab === "edit" ? "bg-card text-foreground shadow-xs" : "text-muted-foreground")}
          >
            Edit Content
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("preview")}
            className={cn("flex-1 py-1.5 text-xs font-semibold rounded-lg transition-all", activeTab === "preview" ? "bg-card text-foreground shadow-xs" : "text-muted-foreground")}
          >
            Live Student Preview
          </button>
        </div>

        {/* Responsive Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 max-h-[72vh] overflow-y-auto pr-1">
          {/* Left Column: Authoring Form */}
          <div className={cn("flex flex-col gap-4", activeTab === "preview" && "hidden lg:flex")}>
            <Field label="Lesson Title">
              <input
                value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
                placeholder="e.g. TMP102 Digital Temperature Sensor Integration"
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </Field>

            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Theory & Explanation (Markdown)</span>
                <span className="text-[11px] text-muted-foreground">Supports Headings, Images, Tables</span>
              </div>
              <MarkdownToolbar onInsert={handleInsertMarkdown} />
              <textarea
                value={markdown} onChange={(e) => setMarkdown(e.target.value)} rows={7}
                placeholder="Write the concept explanation, hardware pin details, timing notes, image URLs, or tables..."
                className="w-full px-3 py-2 font-mono text-xs border border-border bg-card text-foreground rounded-xl focus:outline-none focus:border-primary transition-colors resize-y leading-relaxed"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Starter Code Template</span>
                <button
                  type="button"
                  onClick={insertBlank}
                  className="text-xs text-primary hover:underline font-semibold flex items-center gap-1"
                >
                  <Plus size={12} /> Add Blank Token
                </button>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Type any token like <code className="text-purple-400 font-mono">{"{{SOMETHING}}"}</code> in the code below. It will automatically appear in the configuration list.
              </p>
              <textarea
                value={template} onChange={(e) => handleTemplateChange(e.target.value)} rows={5}
                className="w-full px-3 py-2 font-mono text-xs border border-border bg-[#14151a] text-gray-100 rounded-xl focus:outline-none focus:border-primary transition-colors resize-y leading-relaxed"
              />
            </div>

            {/* Dynamic Blanks Builder */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Detected Tokens ({blanks.length})
                </span>
                {unconfiguredBlanks.length > 0 ? (
                  <span className="text-[11px] text-amber-500 font-medium">
                    ⚠️ {unconfiguredBlanks.length} token(s) require configuration
                  </span>
                ) : (
                  <span className="text-[11px] text-emerald-500 font-medium">
                    ✓ All tokens configured
                  </span>
                )}
              </div>

              {blanks.length === 0 ? (
                <div className="p-4 bg-muted/20 border border-dashed border-border rounded-xl text-center text-xs text-muted-foreground">
                  No <code className="text-purple-400 font-mono">{"{{TOKEN}}"}</code> detected in template. Add one to create interactive student input blanks.
                </div>
              ) : (
                <div className="flex flex-col gap-2.5">
                  {blanks.map((blank, idx) => {
                    const isConfigured = Boolean(
                      blank.label.trim() && (blank.validator_pattern.trim() || blank.correct_answer.trim())
                    )
                    return (
                      <div
                        key={blank.token}
                        className={`p-3 border rounded-xl flex flex-col gap-2 transition-all ${
                          isConfigured
                            ? "bg-card border-border"
                            : "bg-amber-950/10 border-amber-500/40"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="px-2.5 py-1 font-mono text-xs font-bold bg-primary/10 text-primary border border-primary/20 rounded-lg">
                            {blank.token}
                          </span>
                          <input
                            value={blank.label}
                            onChange={(e) => updateBlank(idx, { label: e.target.value })}
                            placeholder="Input placeholder (e.g. Freq Hz)"
                            className="h-8 px-2.5 text-xs bg-muted border border-border rounded-lg flex-1"
                          />
                          <span
                            className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                              isConfigured
                                ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20"
                                : "bg-amber-500/10 text-amber-500 border border-amber-500/30"
                            }`}
                          >
                            {isConfigured ? "Configured" : "Required"}
                          </span>
                          <button
                            type="button"
                            onClick={() => removeBlank(blank.token)}
                            className="p-1 text-red-500 hover:bg-red-500/10 rounded"
                            title="Remove from template"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          <div>
                            <label className="text-[10px] text-muted-foreground uppercase font-mono">Validator Pattern (Regex / String)</label>
                            <input
                              value={blank.validator_pattern}
                              onChange={(e) => updateBlank(idx, { validator_pattern: e.target.value })}
                              placeholder="e.g. ^int$ or int|float"
                              className="w-full h-8 px-2 font-mono text-xs bg-muted border border-border rounded-lg"
                            />
                          </div>
                          <div>
                            <label className="text-[10px] text-muted-foreground uppercase font-mono">Auto-fill Solution Answer</label>
                            <input
                              value={blank.correct_answer}
                              onChange={(e) => updateBlank(idx, { correct_answer: e.target.value })}
                              placeholder="Revealed on 3rd attempt"
                              className="w-full h-8 px-2 font-mono text-xs bg-muted border border-border rounded-lg text-emerald-500 font-semibold"
                            />
                          </div>
                        </div>
                        <div>
                          <label className="text-[10px] text-muted-foreground uppercase font-mono">Failure Hint</label>
                          <input
                            value={blank.hint}
                            onChange={(e) => updateBlank(idx, { hint: e.target.value })}
                            placeholder="Helpful hint shown when student fails validation"
                            className="w-full h-8 px-2 text-xs bg-muted border border-border rounded-lg"
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Hardware Address Selector Settings */}
            <div className="p-3 bg-card border border-border rounded-xl flex flex-col gap-2.5">
              <label className="flex items-center gap-2 text-xs font-semibold text-foreground cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={hwEnabled}
                  onChange={(e) => setHwEnabled(e.target.checked)}
                />
                Enable I²C Hardware Address Selector Dropdown
              </label>
              {hwEnabled && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                  <div>
                    <label className="text-[10px] text-muted-foreground uppercase">Default Hex Address</label>
                    <input
                      value={hwDefault}
                      onChange={(e) => setHwDefault(e.target.value)}
                      placeholder="0x49"
                      className="w-full h-8 px-2 font-mono text-xs bg-muted border border-border rounded-lg"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-muted-foreground uppercase">Allowable Addresses (comma-separated)</label>
                    <input
                      value={hwAddresses}
                      onChange={(e) => setHwAddresses(e.target.value)}
                      placeholder="0x48, 0x49, 0x4A, 0x4B"
                      className="w-full h-8 px-2 font-mono text-xs bg-muted border border-border rounded-lg"
                    />
                  </div>
                </div>
              )}
            </div>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
                <input type="checkbox" checked={isRequired} onChange={(e) => setIsRequired(e.target.checked)} />
                Mandatory
              </label>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>Max attempts:</span>
                <input
                  type="number" min={1} max={10} value={maxAttempts}
                  onChange={(e) => setMaxAttempts(Number(e.target.value))}
                  className="w-14 h-8 px-2 border border-border bg-card rounded-lg text-xs"
                />
              </div>
            </div>
          </div>

          {/* Right Column: Live Student Preview */}
          <div className={cn("flex flex-col gap-4 bg-muted/15 border border-border/80 rounded-2xl p-4 overflow-y-auto", activeTab === "edit" && "hidden lg:flex")}>
            <div className="flex items-center justify-between pb-2 border-b border-border/60">
              <span className="text-xs font-bold uppercase tracking-wider text-primary">Live Student Preview</span>
            </div>

            <div className="p-4 bg-card/60 rounded-xl border border-border/60 overflow-hidden shadow-xs">
              <MarkdownContent content={markdown || "*No explanation text entered yet. Type above to preview in real-time.*"} />
            </div>

            <CodePracticeBlock
              content={{
                template,
                instructions: undefined,
                blanks: blanks.map((b) => ({
                  token: b.token,
                  label: b.label,
                  validator_pattern: b.validator_pattern,
                  correct_answer: b.correct_answer,
                  hint: b.hint,
                })),
                max_attempts: Number(maxAttempts) || 3,
                hardware_selector: hwEnabled
                  ? {
                      enabled: true,
                      default_address: hwDefault,
                      addresses: hwAddresses.split(",").map((s: string) => s.trim()).filter(Boolean),
                    }
                  : undefined,
              }}
              onComplete={() => {}}
            />
          </div>
        </div>

        {error && <p className="text-xs text-red-500">{error}</p>}
        {!isAllConfigured && blanks.length > 0 && (
          <p className="text-xs text-amber-500 font-medium">
            ⚠️ Every detected token must have a label and either a validator pattern or correct answer before saving.
          </p>
        )}
        <ModalActions
          onCancel={onClose}
          onConfirm={() => mutation.mutate()}
          loading={mutation.isPending}
          disabled={!template.trim() || blanks.length === 0 || !isAllConfigured}
          label={item ? "Save changes" : "Add code practice"}
        />
      </div>
    </Modal>
  )
}

function LabItemModal({ moduleId, item, onClose, onSuccess }: {
  moduleId: string; item?: AdminItem; onClose: () => void; onSuccess: () => void
}) {
  const labContent = item && "lab_type" in item.content ? (item.content as any) : {}
  const [title, setTitle] = useState(item?.title ?? "")
  const [labType, setLabType] = useState<"uart" | "i2c" | "can" | "spi">(labContent.lab_type ?? "uart")
  const [markdown, setMarkdown] = useState(labContent.markdown || labContent.instructions || "")
  const [isRequired, setIsRequired] = useState(item?.is_required ?? true)
  const [activeTab, setActiveTab] = useState<"edit" | "preview">("edit")

  // UART config
  const [leftName, setLeftName] = useState(labContent.config?.left_name ?? "Microcontroller (MCU)")
  const [leftPins, setLeftPins] = useState((labContent.config?.left_pins || ["TX", "RX", "GND"]).join(", "))
  const [rightName, setRightName] = useState(labContent.config?.right_name ?? "GPS Module")
  const [rightPins, setRightPins] = useState((labContent.config?.right_pins || ["TX", "RX", "GND"]).join(", "))

  // I2C config
  const [allowedDevices, setAllowedDevices] = useState(
    (labContent.config?.allowed_devices || ["TMP102 (0x49)", "INA219 (0x40)", "FRAM (0x50)", "OLED (0x3C)", "MPU6050 (0x68)"]).join(", ")
  )

  const [error, setError] = useState("")

  const handleInsertMarkdown = (prefix: string, suffix = "", placeholder = "") => {
    setMarkdown((prev: string) => `${prev ? prev + "\n" : ""}${prefix}${placeholder}${suffix}\n`)
  }

  const generatedConfig = {
    left_name: leftName.trim(),
    left_pins: leftPins.split(",").map((s: string) => s.trim()).filter(Boolean),
    right_name: rightName.trim(),
    right_pins: rightPins.split(",").map((s: string) => s.trim()).filter(Boolean),
    allowed_devices: allowedDevices.split(",").map((s: string) => s.trim()).filter(Boolean),
    max_devices: 5,
    bus_speed: "500 kbps",
    slave_count: 3,
  }

  const mutation = useMutation({
    mutationFn: () => {
      let config: Record<string, any> = {}
      if (labType === "uart") {
        config = {
          left_name: leftName.trim(),
          left_pins: leftPins.split(",").map((s: string) => s.trim()).filter(Boolean),
          right_name: rightName.trim(),
          right_pins: rightPins.split(",").map((s: string) => s.trim()).filter(Boolean),
        }
      } else if (labType === "i2c") {
        config = {
          allowed_devices: allowedDevices.split(",").map((s: string) => s.trim()).filter(Boolean),
          max_devices: 5,
        }
      } else if (labType === "can") {
        config = {
          bus_speed: "500 kbps",
        }
      } else if (labType === "spi") {
        config = {
          slave_count: 3,
        }
      }

      const payload = {
        lab_type: labType,
        title: title.trim() || undefined,
        markdown: markdown.trim() || undefined,
        instructions: markdown.trim() || undefined,
        config,
      }

      return item
        ? updateItemApi(item.id, { title: title.trim() || undefined, is_required: isRequired, content: payload })
        : createItemApi(moduleId, { kind: "lab", title: title.trim() || undefined, is_required: isRequired, content: payload })
    },
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail?.toString?.() ?? "Failed to save lab"),
  })

  return (
    <Modal title={item ? "Edit interactive lab" : "Add interactive lab"} onClose={onClose} maxWidth="max-w-6xl sm:max-w-6xl w-full">
      <div className="flex flex-col gap-3">
        {/* Mobile Tab Toggle */}
        <div className="flex lg:hidden items-center p-1 bg-muted rounded-xl border border-border">
          <button
            type="button"
            onClick={() => setActiveTab("edit")}
            className={cn("flex-1 py-1.5 text-xs font-semibold rounded-lg transition-all", activeTab === "edit" ? "bg-card text-foreground shadow-xs" : "text-muted-foreground")}
          >
            Edit Content
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("preview")}
            className={cn("flex-1 py-1.5 text-xs font-semibold rounded-lg transition-all", activeTab === "preview" ? "bg-card text-foreground shadow-xs" : "text-muted-foreground")}
          >
            Live Student Preview
          </button>
        </div>

        {/* Responsive Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 max-h-[72vh] overflow-y-auto pr-1">
          {/* Left Column: Authoring Form */}
          <div className={cn("flex flex-col gap-4", activeTab === "preview" && "hidden lg:flex")}>
            <Field label="Lab Type">
              <select
                value={labType}
                onChange={(e) => setLabType(e.target.value as any)}
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              >
                <option value="uart">UART Protocol (Pin Crossover Wiring Lab)</option>
                <option value="i2c">I²C Protocol (Multi-drop Bus Network Lab)</option>
                <option value="can">CAN Bus Protocol (Arbitration & Priority Simulator)</option>
                <option value="spi">SPI Protocol (Clock & Slave Select Lines Lab)</option>
              </select>
            </Field>

            <Field label="Lab Title">
              <input
                value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
                placeholder="e.g. UART Avionics Wiring Challenge"
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </Field>

            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Theory, Diagrams & Explanation (Markdown)</span>
                <span className="text-[11px] text-muted-foreground">Supports Headings, Images, Tables</span>
              </div>
              <MarkdownToolbar onInsert={handleInsertMarkdown} />
              <textarea
                value={markdown} onChange={(e) => setMarkdown(e.target.value)} rows={7}
                placeholder="Explain the hardware protocol, differential signaling, baud rates, image diagrams, or connection rules..."
                className="w-full px-3 py-2 font-mono text-xs border border-border bg-card text-foreground rounded-xl focus:outline-none focus:border-primary transition-colors resize-y leading-relaxed"
              />
            </div>

            {labType === "uart" && (
              <div className="p-3 bg-muted/30 border border-border rounded-xl flex flex-col gap-3">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">UART Pinout Configuration</span>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-[10px] text-muted-foreground uppercase">Left Device Name</label>
                    <input
                      value={leftName} onChange={(e) => setLeftName(e.target.value)}
                      className="w-full h-8 px-2 text-xs bg-card border border-border rounded-lg"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-muted-foreground uppercase">Left Pins (comma-separated)</label>
                    <input
                      value={leftPins} onChange={(e) => setLeftPins(e.target.value)}
                      className="w-full h-8 px-2 font-mono text-xs bg-card border border-border rounded-lg"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-muted-foreground uppercase">Right Peripheral Name</label>
                    <input
                      value={rightName} onChange={(e) => setRightName(e.target.value)}
                      className="w-full h-8 px-2 text-xs bg-card border border-border rounded-lg"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-muted-foreground uppercase">Right Pins (comma-separated)</label>
                    <input
                      value={rightPins} onChange={(e) => setRightPins(e.target.value)}
                      className="w-full h-8 px-2 font-mono text-xs bg-card border border-border rounded-lg"
                    />
                  </div>
                </div>
              </div>
            )}

            {labType === "i2c" && (
              <div className="p-3 bg-muted/30 border border-border rounded-xl flex flex-col gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Available Peripheral Devices</span>
                <input
                  value={allowedDevices} onChange={(e) => setAllowedDevices(e.target.value)}
                  placeholder="TMP102 (0x49), INA219 (0x40), FRAM (0x50), ..."
                  className="w-full h-8 px-2 text-xs font-mono bg-card border border-border rounded-lg"
                />
                <p className="text-[11px] text-muted-foreground">Comma-separated list of sensors students can mount on the I2C bus.</p>
              </div>
            )}

            <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
              <input type="checkbox" checked={isRequired} onChange={(e) => setIsRequired(e.target.checked)} />
              Mandatory
            </label>
          </div>

          {/* Right Column: Live Student Preview */}
          <div className={cn("flex flex-col gap-4 bg-muted/15 border border-border/80 rounded-2xl p-4 overflow-y-auto", activeTab === "edit" && "hidden lg:flex")}>
            <div className="flex items-center justify-between pb-2 border-b border-border/60">
              <span className="text-xs font-bold uppercase tracking-wider text-primary">Live Student Preview</span>
            </div>

            <div className="p-4 bg-card/60 rounded-xl border border-border/60 overflow-hidden shadow-xs">
              <MarkdownContent content={markdown || "*No protocol explanation text entered yet. Type on the left to preview.*"} />
            </div>

            <HardwareLabBlock
              content={{
                lab_type: labType,
                title,
                instructions: undefined,
                config: generatedConfig,
              }}
              onComplete={() => {}}
            />
          </div>
        </div>

        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose}
          onConfirm={() => mutation.mutate()}
          loading={mutation.isPending}
          disabled={!title.trim()}
          label={item ? "Save changes" : "Add lab"}
        />
      </div>
    </Modal>
  )
}

function AttachmentItemModal({ moduleId, item, onClose, onSuccess }: {
  moduleId: string; item?: AdminItem; onClose: () => void; onSuccess: () => void
}) {
  const [title, setTitle] = useState(item?.title ?? "")
  const [isRequired, setIsRequired] = useState(item?.is_required ?? true)
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () =>
      item
        ? updateItemApi(item.id, { title: title.trim() || undefined, is_required: isRequired })
        : createItemApi(moduleId, { kind: "attachment", title: title.trim() || undefined, is_required: isRequired, content: {} }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail?.toString?.() ?? "Failed to save item"),
  })

  return (
    <Modal title={item ? "Edit attachment" : "Add attachment"} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="Title (optional)">
          <input
            value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
          <input type="checkbox" checked={isRequired} onChange={(e) => setIsRequired(e.target.checked)} />
          Mandatory (blocks the next module until viewed)
        </label>
        {!item && <p className="text-xs text-muted-foreground">Upload the actual PDF from the module list after creating this item.</p>}
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending} disabled={false} label={item ? "Save changes" : "Add attachment"} />
      </div>
    </Modal>
  )
}

function AttachmentUploadModal({ item, onClose, onSuccess }: { item: AdminItem; onClose: () => void; onSuccess: () => void }) {
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
      return uploadAttachmentApi(item.id, file!, { signal: controller.signal, onProgress: setProgress })
    },
    onSuccess: () => setResult("Uploaded."),
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
    <Modal title={`Upload PDF — ${item.title ?? "Attachment"}`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="PDF file (up to 25MB)">
          <input
            type="file" accept="application/pdf"
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
          <button
            onClick={() => mutation.mutate()}
            disabled={!file}
            className="h-10 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
          >
            Upload
          </button>
        )}
      </div>
    </Modal>
  )
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
  const [activeTab, setActiveTab] = useState<"edit" | "preview">("edit")
  const [error, setError] = useState("")

  const handleInsertMarkdown = (prefix: string, suffix = "", placeholder = "") => {
    setBody((prev: string) => `${prev ? prev + "\n" : ""}${prefix}${placeholder}${suffix}\n`)
  }

  const mutation = useMutation({
    mutationFn: () =>
      item
        ? updateItemApi(item.id, { title: title.trim() || undefined, is_required: isRequired, content: { body } })
        : createItemApi(moduleId, { kind: "text", title: title.trim() || undefined, is_required: isRequired, content: { body } }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail?.toString?.() ?? "Failed to save item"),
  })

  return (
    <Modal title={item ? "Edit reading material" : "Add reading material"} onClose={onClose} maxWidth="max-w-6xl sm:max-w-6xl w-full">
      <div className="flex flex-col gap-3">
        {/* Mobile Tab Toggle */}
        <div className="flex lg:hidden items-center p-1 bg-muted rounded-xl border border-border">
          <button
            type="button"
            onClick={() => setActiveTab("edit")}
            className={cn("flex-1 py-1.5 text-xs font-semibold rounded-lg transition-all", activeTab === "edit" ? "bg-card text-foreground shadow-xs" : "text-muted-foreground")}
          >
            Edit Content
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("preview")}
            className={cn("flex-1 py-1.5 text-xs font-semibold rounded-lg transition-all", activeTab === "preview" ? "bg-card text-foreground shadow-xs" : "text-muted-foreground")}
          >
            Live Student Preview
          </button>
        </div>

        {/* Responsive Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 max-h-[72vh] overflow-y-auto pr-1">
          {/* Left Column: Authoring Form */}
          <div className={cn("flex flex-col gap-4", activeTab === "preview" && "hidden lg:flex")}>
            <Field label="Reading Title (optional)">
              <input
                value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
                placeholder="e.g. Welcome, Flight Software Engineer"
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </Field>

            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Reading Content (Markdown)</span>
                <span className="text-[11px] text-muted-foreground">Supports Headings, Images, Tables</span>
              </div>
              <MarkdownToolbar onInsert={handleInsertMarkdown} />
              <textarea
                value={body} onChange={(e) => setBody(e.target.value)} rows={12}
                placeholder="Write rich lesson material using Markdown... Attach images with ![alt](url) or format tables."
                className="w-full px-3 py-2 font-mono text-xs border border-border bg-card text-foreground rounded-xl focus:outline-none focus:border-primary transition-colors resize-y leading-relaxed"
              />
            </div>

            <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
              <input type="checkbox" checked={isRequired} onChange={(e) => setIsRequired(e.target.checked)} />
              Mandatory
            </label>
          </div>

          {/* Right Column: Live Student Preview */}
          <div className={cn("flex flex-col gap-4 bg-muted/15 border border-border/80 rounded-2xl p-4 overflow-y-auto", activeTab === "edit" && "hidden lg:flex")}>
            <div className="flex items-center justify-between pb-2 border-b border-border/60">
              <span className="text-xs font-bold uppercase tracking-wider text-primary">Live Student Preview</span>
              <span className="text-[10px] bg-primary/10 text-primary px-2 py-0.5 rounded-full font-mono">Real-time Parity</span>
            </div>

            <div className="p-4 sm:p-6 bg-card/60 rounded-xl border border-border/60 overflow-hidden shadow-xs">
              <MarkdownContent content={body || "*Nothing to preview yet. Start typing on the left to see the live formatted result.*"} />
            </div>

            <div className="flex justify-end opacity-70 pointer-events-none">
              <div className="px-4 py-2 bg-primary text-primary-foreground text-xs font-semibold rounded-lg flex items-center gap-1.5 shadow-xs">
                <span>Got it! (Student Button)</span>
              </div>
            </div>
          </div>
        </div>

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

function OrderNumberInput({
  value, totalCount, disabled, onCommit,
}: {
  value: number
  totalCount: number
  disabled?: boolean
  onCommit: (pos: number) => void
}) {
  const [text, setText] = useState(String(value))
  useEffect(() => { setText(String(value)) }, [value])
  const commit = () => {
    const parsed = Number.parseInt(text, 10)
    if (!Number.isFinite(parsed)) { setText(String(value)); return }
    if (parsed === value) { setText(String(value)); return }
    onCommit(parsed)
    setText(String(value))
  }
  return (
    <input
      type="number"
      aria-label="Question order number"
      title={`Question order (1–${totalCount}) — type a number to move this question`}
      value={text}
      min={1}
      max={totalCount}
      inputMode="numeric"
      disabled={disabled}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur()
        if (e.key === "Escape") { setText(String(value)); (e.target as HTMLInputElement).blur() }
      }}
      onClick={(e) => e.stopPropagation()}
      className="w-11 h-7 px-1 border border-border bg-background text-foreground rounded-lg text-xs font-mono font-bold text-center focus:outline-none focus:border-primary transition-colors disabled:opacity-50 shrink-0 cursor-pointer"
    />
  )
}

function QuizItemModal({ moduleId, item, onClose, onSuccess }: {
  moduleId: string; item?: AdminItem; onClose: () => void; onSuccess: () => void
}) {
  const existing = item && "questions" in item.content ? item.content : null
  const [title, setTitle] = useState(item?.title ?? "")
  const [passThreshold, setPassThreshold] = useState(existing?.pass_threshold ?? 0)
  const [randomCount, setRandomCount] = useState<number | null>(existing?.random_count ?? null)
  const [isRequired, setIsRequired] = useState(item?.is_required ?? true)
  const [questions, setQuestions] = useState<AdminQuizQuestion[]>(
    existing?.questions?.length
      ? existing.questions
      : [{ prompt: "", explanation: "", options: [{ text: "", is_correct: true }, { text: "", is_correct: false }] }],
  )
  const [error, setError] = useState("")
  const [uploadingIndex, setUploadingIndex] = useState<number | null>(null)
  const [uploadError, setUploadError] = useState<{ index: number; message: string } | null>(null)

  const updateQuestion = (qi: number, patch: Partial<AdminQuizQuestion>) =>
    setQuestions((prev) => prev.map((q, idx) => (idx === qi ? { ...q, ...patch } : q)))

  const updateOption = (qi: number, oi: number, patch: Partial<{ text: string; is_correct: boolean }>) =>
    setQuestions((prev) =>
      prev.map((q, idx) => idx !== qi ? q : { ...q, options: q.options.map((o, oidx) => (oidx === oi ? { ...o, ...patch } : o)) }),
    )

  const moveQuestion = (fromIndex: number, direction: -1 | 1) => {
    const target = fromIndex + direction
    if (target < 0 || target >= questions.length) return
    setQuestions((prev) => {
      const next = [...prev]
      ;[next[fromIndex], next[target]] = [next[target], next[fromIndex]]
      return next
    })
  }

  const moveToPosition = (fromIndex: number, targetPos: number) => {
    if (!Number.isFinite(targetPos)) return
    const clamped = Math.min(Math.max(Math.round(targetPos), 1), questions.length)
    if (clamped - 1 === fromIndex) return
    setQuestions((prev) => {
      const next = [...prev]
      const [itemToMove] = next.splice(fromIndex, 1)
      next.splice(clamped - 1, 0, itemToMove)
      return next
    })
  }

  const handleImageUpload = async (qi: number, file: File) => {
    setUploadingIndex(qi)
    setUploadError(null)
    try {
      const res = await uploadQuizImageApi(file)
      updateQuestion(qi, { image_url: res.url })
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || "Failed to upload image"
      setUploadError({ index: qi, message: typeof msg === "string" ? msg : "Upload failed" })
    } finally {
      setUploadingIndex(null)
    }
  }

  const valid = questions.every((q) => q.prompt.trim() && q.options.filter((o) => o.text.trim()).length >= 2 && q.options.some((o) => o.is_correct))
    && (randomCount == null || (randomCount >= 1 && randomCount <= questions.length))

  const mutation = useMutation({
    mutationFn: () => {
      const content = {
        pass_threshold: passThreshold,
        questions: questions.map((q) => ({ ...q, options: q.options.filter((o) => o.text.trim()) })),
        random_count: randomCount,
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
        <Field label={`Random questions per attempt (blank = all ${questions.length})`}>
          <input
            type="number" min={1} max={questions.length} value={randomCount ?? ""}
            onChange={(e) => setRandomCount(e.target.value === "" ? null : Number(e.target.value))}
            placeholder={`${questions.length}`}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>

        <div className="flex flex-col gap-3">
          {questions.map((q, qi) => (
            <div key={qi} className="p-3.5 border border-border rounded-2xl flex flex-col gap-2.5 bg-card/40">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <div className="flex flex-col shrink-0">
                    <button
                      type="button"
                      onClick={() => moveQuestion(qi, -1)}
                      disabled={qi === 0}
                      className="text-muted-foreground hover:text-foreground disabled:opacity-20 p-0.5 transition-colors cursor-pointer"
                      title="Move question up"
                    >
                      <ArrowUp size={12} />
                    </button>
                    <button
                      type="button"
                      onClick={() => moveQuestion(qi, 1)}
                      disabled={qi === questions.length - 1}
                      className="text-muted-foreground hover:text-foreground disabled:opacity-20 p-0.5 transition-colors cursor-pointer"
                      title="Move question down"
                    >
                      <ArrowDown size={12} />
                    </button>
                  </div>
                  <OrderNumberInput
                    value={qi + 1}
                    totalCount={questions.length}
                    onCommit={(pos) => moveToPosition(qi, pos)}
                  />
                  <span className="text-xs font-semibold text-foreground">Question {qi + 1}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setQuestions((prev) => prev.filter((_, idx) => idx !== qi))}
                  disabled={questions.length === 1}
                  className="text-xs text-red-600 hover:bg-red-500/10 rounded px-2 py-0.5 transition-colors disabled:opacity-30 cursor-pointer"
                >
                  Remove
                </button>
              </div>

              <input
                value={q.prompt} placeholder="Question prompt"
                onChange={(e) => updateQuestion(qi, { prompt: e.target.value })}
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />

              {/* Question Image Section */}
              <div className="flex flex-col gap-2 p-2.5 rounded-xl bg-muted/20 border border-border/70">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-foreground flex items-center gap-1.5">
                    <ImageIcon size={13} className="text-muted-foreground" /> Image / Diagram (optional)
                  </span>
                  {q.image_url && (
                    <button
                      type="button"
                      onClick={() => updateQuestion(qi, { image_url: undefined })}
                      className="text-[11px] text-destructive hover:underline cursor-pointer"
                    >
                      Remove image
                    </button>
                  )}
                </div>

                {q.image_url ? (
                  <div className="flex flex-col gap-2">
                    <div className="max-h-40 overflow-hidden rounded-lg border border-border bg-card/60 flex items-center justify-center p-2 relative">
                      <img
                        src={resolveQuizImageUrl(q.image_url)}
                        alt={`Question ${qi + 1} diagram`}
                        className="max-h-36 max-w-full object-contain rounded"
                        onError={(e) => {
                          (e.target as HTMLElement).classList.add("opacity-40")
                        }}
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <label className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-border bg-card hover:bg-muted text-xs font-medium text-foreground cursor-pointer transition-colors shrink-0">
                        {uploadingIndex === qi ? (
                          <>
                            <Loader2 size={12} className="animate-spin text-primary" />
                            <span>Uploading…</span>
                          </>
                        ) : (
                          <>
                            <Upload size={12} />
                            <span>Replace image</span>
                          </>
                        )}
                        <input
                          type="file"
                          accept="image/*"
                          disabled={uploadingIndex === qi}
                          className="hidden"
                          onChange={(e) => {
                            const f = e.target.files?.[0]
                            if (f) {
                              void handleImageUpload(qi, f)
                              e.target.value = ""
                            }
                          }}
                        />
                      </label>
                      <input
                        value={q.image_url}
                        placeholder="Image path or URL"
                        onChange={(e) => updateQuestion(qi, { image_url: e.target.value.trim() || undefined })}
                        className="flex-1 h-8 px-2.5 border border-border bg-card text-foreground rounded-lg text-xs font-mono focus:outline-none focus:border-primary transition-colors"
                      />
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                    <label className="inline-flex items-center justify-center gap-1.5 h-9 px-3 rounded-xl border border-primary/40 bg-primary/5 hover:bg-primary/10 text-xs font-semibold text-primary cursor-pointer transition-colors shrink-0">
                      {uploadingIndex === qi ? (
                        <>
                          <Loader2 size={13} className="animate-spin" />
                          <span>Uploading image…</span>
                        </>
                      ) : (
                        <>
                          <Upload size={13} />
                          <span>Upload image</span>
                        </>
                      )}
                      <input
                        type="file"
                        accept="image/*"
                        disabled={uploadingIndex === qi}
                        className="hidden"
                        onChange={(e) => {
                          const f = e.target.files?.[0]
                          if (f) {
                            void handleImageUpload(qi, f)
                            e.target.value = ""
                          }
                        }}
                      />
                    </label>
                    <span className="text-xs text-muted-foreground text-center sm:text-left">or link:</span>
                    <input
                      value={q.image_url ?? ""}
                      placeholder="Paste URL or /files/... path"
                      onChange={(e) => updateQuestion(qi, { image_url: e.target.value.trim() || undefined })}
                      className="flex-1 h-9 px-3 border border-border bg-card text-foreground rounded-xl text-xs focus:outline-none focus:border-primary transition-colors"
                    />
                  </div>
                )}

                {uploadError?.index === qi && (
                  <p className="text-[11px] text-destructive">{uploadError.message}</p>
                )}
              </div>

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
                      type="button"
                      onClick={() => updateQuestion(qi, { options: q.options.filter((_, idx) => idx !== oi) })}
                      disabled={q.options.length <= 2}
                      className="text-xs text-red-600 hover:bg-red-500/10 rounded px-2 py-1 transition-colors disabled:opacity-30 cursor-pointer"
                    >
                      Remove
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => updateQuestion(qi, { options: [...q.options, { text: "", is_correct: false }] })}
                  className="h-8 px-3 border border-dashed border-border rounded-xl text-xs font-medium text-muted-foreground hover:bg-muted transition-colors w-fit cursor-pointer"
                >
                  + Add option
                </button>
              </div>
            </div>
          ))}
          <button
            type="button"
            onClick={() => setQuestions((prev) => [...prev, { prompt: "", explanation: "", options: [{ text: "", is_correct: true }, { text: "", is_correct: false }] }])}
            className="h-9 px-3 border border-dashed border-border rounded-xl text-xs font-medium text-muted-foreground hover:bg-muted transition-colors w-fit cursor-pointer"
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

function secondsToParts(total: number): { h: number; m: number; s: number; ms: number } {
  const t = Math.max(0, total)
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const s = Math.floor(t % 60)
  const ms = Math.round((t - Math.floor(t)) * 1000)
  return { h, m, s, ms }
}

function partsToSeconds(h: number, m: number, s: number, ms: number): number {
  return Math.round((h * 3600 + m * 60 + s + ms / 1000) * 1000) / 1000
}

function formatTime(seconds: number): string {
  const { h, m, s, ms } = secondsToParts(seconds)
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}:${String(ms).padStart(3, "0")}`
}

function TimeFields({ label, value, onChange }: {
  label: string; value: number; onChange: (seconds: number) => void
}) {
  const { h, m, s, ms } = secondsToParts(value)
  const update = (part: "h" | "m" | "s" | "ms", raw: string) => {
    const n = Math.max(0, Number(raw) || 0)
    const next = { h, m, s, ms, [part]: n }
    onChange(partsToSeconds(next.h, next.m, next.s, next.ms))
  }
  const box = "w-full h-10 px-1 border border-border bg-card text-foreground rounded-xl text-sm text-center focus:outline-none focus:border-primary transition-colors"
  return (
    <Field label={`${label} (h:m:s:ms)`}>
      <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr_auto_1.3fr] items-center gap-1">
        <input type="number" min={0} aria-label="hours" value={h} onChange={(e) => update("h", e.target.value)} className={box} />
        <span className="text-muted-foreground">:</span>
        <input type="number" min={0} max={59} aria-label="minutes" value={m} onChange={(e) => update("m", e.target.value)} className={box} />
        <span className="text-muted-foreground">:</span>
        <input type="number" min={0} max={59} aria-label="seconds" value={s} onChange={(e) => update("s", e.target.value)} className={box} />
        <span className="text-muted-foreground">:</span>
        <input type="number" min={0} max={999} aria-label="milliseconds" value={ms} onChange={(e) => update("ms", e.target.value)} className={box} />
      </div>
    </Field>
  )
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
  const [startSeconds, setStartSeconds] = useState(checkpoint?.start_seconds ?? 0)
  const [endSeconds, setEndSeconds] = useState(checkpoint?.end_seconds ?? 0)
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
    ? body.trim() && endSeconds > startSeconds
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
        start_seconds: startSeconds,
        end_seconds: kind === "note" ? endSeconds : null,
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
          <TimeFields label="Start" value={startSeconds} onChange={setStartSeconds} />
          {kind === "note" && (
            <TimeFields label="End" value={endSeconds} onChange={setEndSeconds} />
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
