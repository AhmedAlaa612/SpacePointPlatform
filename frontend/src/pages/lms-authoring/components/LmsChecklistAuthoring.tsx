import { Fragment, useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, X, GripVertical, ImagePlus, Users, Crop, ExternalLink } from "lucide-react"
import { EmptyState, Spinner } from "@/components/ui/primitives"
import { ImageCropModal } from "@/components/ui/ImageCropModal"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { VideoPlayer } from "@/components/video/VideoPlayer"
import { useToast } from "@/components/ui/toast"
import { ensureAbsoluteUrl } from "@/lib/utils"
import { getSessionsApi } from "@/api/sessions/cohorts"
import { listCoursesApi } from "@/api/lms_admin"
import { listMissionsAdminFullApi } from "@/api/missions_admin"
import { listCohortQuizTemplatesApi } from "@/api/cohort_quiz"
import {
  updateLmsProgramApi, uploadLmsProgramImageApi, updateCohortPosterTemplateApi,
  addLmsProgramItemApi, updateLmsProgramItemApi, deleteLmsProgramItemApi, reorderLmsProgramItemsApi,
  getCohortProgramOverrideApi, addCohortOverrideItemApi, updateCohortOverrideItemApi, deleteCohortOverrideItemApi,
  reorderCohortOverrideItemsApi, getCohortProgramOverrideInstructorApi, resyncCohortProgramAssignmentsApi,
  uploadLmsProgramItemPdfApi, deleteLmsProgramItemPdfApi,
  uploadLmsProgramItemGuidelineVideoApi, deleteLmsProgramItemGuidelineVideoApi,
  getLmsProgramItemGuidelineVideoUrlApi,
  MISSION_STEP_KEYS,
  type LmsProgram, type LmsProgramItem, type LmsProgramItemInput, type LmsProgramItemType,
} from "@/api/lms_admin"
import { errorDetail, toDatetimeLocalValue, itemToInput, ITEM_TYPES, TEAM_SCOPABLE_TYPES, ITEM_TYPE_META, PHASE_PICKER_KEYS } from "./LmsChecklistShared"

/** Authoring-side preview for an uploaded guideline video — the same
 * resolve-fresh-on-open posture the Library/training players already use.
 * Polls while the upload is still transcoding, since a facilitator can open
 * this right after uploading, well before the encode finishes. */
export function GuidelineVideoPreview({ itemId, title }: { itemId: string; title: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["lms-admin-guideline-video", itemId],
    queryFn: () => getLmsProgramItemGuidelineVideoUrlApi(itemId),
    refetchInterval: (q) => {
      const status = q.state.data?.video_info?.status
      return status && status !== "ready" && status !== "failed" ? 4000 : false
    },
  })

  if (isLoading) return <p className="text-sm text-muted-foreground py-6">Loading video…</p>
  if (isError || !data?.video_info) return <p className="text-sm text-destructive py-6">Couldn't load this video.</p>
  return <VideoPlayer info={data.video_info} title={title} autoPlay className="w-full aspect-video rounded-lg bg-black" />
}

export function CreateChecklistPrompt({ onCreate, pending }: { onCreate: (name: string) => void; pending: boolean }) {
  const [name, setName] = useState("")
  return (
    <div className="flex flex-col gap-3 max-w-sm">
      <EmptyState title="This program has no LMS checklist yet" hint="Give it a name to create one." />
      <input
        value={name} onChange={(e) => setName(e.target.value)} placeholder="Checklist name"
        className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
      />
      <button
        onClick={() => name.trim() && onCreate(name.trim())}
        disabled={!name.trim() || pending}
        className="flex items-center justify-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors disabled:opacity-50"
      >
        <Plus size={14} /> Create checklist
      </button>
    </div>
  )
}

export function ProgramTemplateEditor({
  program, onChanged, readOnly,
}: { program: LmsProgram; onChanged: () => void; readOnly: boolean }) {
  const toggleCert = useMutation({
    mutationFn: (value: boolean) => updateLmsProgramApi(program.id, { certificate_required: value }),
    onSuccess: onChanged,
  })
  const [imageError, setImageError] = useState("")
  const [cropModalOpen, setCropModalOpen] = useState(false)
  const [selectedImageForCrop, setSelectedImageForCrop] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const imageMutation = useMutation({
    mutationFn: (file: File) => uploadLmsProgramImageApi(program.id, file),
    onSuccess: () => {
      setImageError("")
      setCropModalOpen(false)
      setSelectedImageForCrop(null)
      onChanged()
    },
    onError: (e: unknown) => setImageError(errorDetail(e, "Failed to upload image")),
  })

  const handleFilePicked = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === "string") {
        setSelectedImageForCrop(reader.result)
        setCropModalOpen(true)
      }
    }
    reader.readAsDataURL(file)
    e.target.value = ""
  }

  const handleCropConfirmed = async (croppedFile: File) => {
    await imageMutation.mutateAsync(croppedFile)
  }

  const updatePosterTemplate = useMutation({
    mutationFn: (url: string | null) => updateLmsProgramApi(program.id, { poster_template_url: url }),
    onSuccess: onChanged,
  })

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start gap-4">
        <button
          onClick={() => !readOnly && fileInputRef.current?.click()}
          disabled={readOnly}
          className="group relative w-24 h-24 shrink-0 rounded-2xl bg-muted overflow-hidden ring-1 ring-border disabled:cursor-not-allowed cursor-pointer"
          title="Upload header image"
        >
          {program.image_url ? (
            <img src={program.image_url} alt="" className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center gap-1 text-muted-foreground">
              <ImagePlus size={16} />
              <span className="text-[10px]">Add header</span>
            </div>
          )}
          {!readOnly && (
            <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white text-xs font-medium">
              {imageMutation.isPending ? "Uploading..." : "Change"}
            </div>
          )}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleFilePicked}
        />
        <div className="flex flex-col gap-1 pt-1">
          <div className="text-sm font-medium">Checklist banner image</div>
          <div className="text-xs text-muted-foreground">Top banner image displayed on the student checklist roadmap</div>
          {program.image_url && !readOnly && (
            <div className="flex items-center gap-2 mt-1">
              <button
                type="button"
                onClick={() => {
                  setSelectedImageForCrop(program.image_url)
                  setCropModalOpen(true)
                }}
                className="text-xs font-medium text-primary hover:underline flex items-center gap-1 cursor-pointer"
              >
                <Crop size={12} />
                <span>Crop & Preview Banner</span>
              </button>
            </div>
          )}
          {imageError && <p className="text-xs text-red-500">{imageError}</p>}
        </div>
      </div>

      <ImageCropModal
        isOpen={cropModalOpen}
        onClose={() => {
          if (!imageMutation.isPending) {
            setCropModalOpen(false)
            setSelectedImageForCrop(null)
          }
        }}
        imageSrc={selectedImageForCrop}
        programName={program.name}
        onCropComplete={handleCropConfirmed}
        isUploading={imageMutation.isPending}
      />

      <div className="flex items-center justify-between p-3 bg-card border border-border rounded-xl">
        <div>
          <div className="text-sm font-medium">Gate certificate on this checklist</div>
          <div className="text-xs text-muted-foreground mt-0.5">Cohort certificate needs every required step done</div>
        </div>
        <button
          onClick={() => !readOnly && toggleCert.mutate(!program.certificate_required)}
          disabled={readOnly}
          className={`w-10 h-6 rounded-full relative transition-colors ${readOnly ? "cursor-not-allowed opacity-60" : "cursor-pointer"} ${program.certificate_required ? "bg-primary" : "bg-muted"}`}
        >
          <span className={`absolute left-1 top-1 w-4 h-4 rounded-full bg-white transition-transform ${program.certificate_required ? "translate-x-4" : "translate-x-0"}`} />
        </button>
      </div>

      <div className="flex flex-col gap-2 p-3 bg-card border border-border rounded-xl">
        <div className="flex items-center justify-between gap-2">
          <div>
            <div className="text-sm font-medium">Mission Poster Template URL</div>
            <div className="text-xs text-muted-foreground mt-0.5">
              Default template URL (Canva, Google Slides, Figma, etc.) shared with all cohorts unless overridden
            </div>
          </div>
          {program.poster_template_url && (
            <a
              href={ensureAbsoluteUrl(program.poster_template_url)}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-primary hover:underline flex items-center gap-1 shrink-0"
            >
              Open template <ExternalLink size={12} />
            </a>
          )}
        </div>
        {!readOnly && (
          <div className="flex items-center gap-2 mt-1">
            <input
              type="url"
              defaultValue={program.poster_template_url ?? ""}
              key={program.poster_template_url ?? ""}
              placeholder="https://canva.com/design/..."
              className="flex-1 h-9 px-3 border border-border bg-background text-foreground rounded-lg text-sm focus:outline-none focus:border-primary transition-colors"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault()
                  const val = (e.target as HTMLInputElement).value.trim()
                  updatePosterTemplate.mutate(val || null)
                }
              }}
              onBlur={(e) => {
                const val = e.target.value.trim()
                if (val !== (program.poster_template_url ?? "")) {
                  updatePosterTemplate.mutate(val || null)
                }
              }}
            />
          </div>
        )}
      </div>

      <ChecklistItemsEditor
        items={program.items}
        readOnly={readOnly}
        onAdd={(data) => addLmsProgramItemApi(program.id, data).then(onChanged)}
        onUpdate={(itemId, data) => updateLmsProgramItemApi(program.id, itemId, data).then(onChanged)}
        onDelete={(itemId) => deleteLmsProgramItemApi(program.id, itemId).then(onChanged)}
        onUploadPdf={(itemId, file) => uploadLmsProgramItemPdfApi(itemId, file).then(onChanged)}
        onRemovePdf={(itemId) => deleteLmsProgramItemPdfApi(itemId).then(onChanged)}
        onUploadGuidelineVideo={(itemId, file) => uploadLmsProgramItemGuidelineVideoApi(itemId, file).then(onChanged)}
        onRemoveGuidelineVideo={(itemId) => deleteLmsProgramItemGuidelineVideoApi(itemId).then(onChanged)}
        onReorder={(itemIds) => reorderLmsProgramItemsApi(program.id, itemIds).then(onChanged)}
      />
    </div>
  )
}

export function CohortOverrideEditor({
  cohortId,
  isStaff,
  readOnly,
  hideResync = false,
}: {
  cohortId: string
  isStaff: boolean
  readOnly: boolean
  hideResync?: boolean
}) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const { data: override, isLoading } = useQuery({
    queryKey: ["lms-cohort-override", cohortId],
    queryFn: () => (isStaff ? getCohortProgramOverrideApi(cohortId) : getCohortProgramOverrideInstructorApi(cohortId)),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["lms-cohort-override", cohortId] })

  const resyncMutation = useMutation({
    mutationFn: () => resyncCohortProgramAssignmentsApi(cohortId),
    onSuccess: (r) => toast.success(
      r.items_added === 0 ? "Every assigned student is already caught up." : `Caught up ${r.items_added} missing checklist item${r.items_added === 1 ? "" : "s"} for already-assigned students.`,
    ),
    onError: () => toast.error("Couldn't resync students — try again."),
  })

  const updateCohortPosterMutation = useMutation({
    mutationFn: (url: string | null) => updateCohortPosterTemplateApi(cohortId, url),
    onSuccess: () => {
      toast.success("Cohort poster template updated")
      invalidate()
    },
    onError: () => toast.error("Failed to update poster template"),
  })

  if (isLoading) return <Spinner />
  if (!override) return <EmptyState title="This cohort's program has no checklist yet" />

  const effectivePosterUrl = override.poster_template_url || override.inherited_poster_template_url

  return (
    <div className="flex flex-col gap-3">
      {override.is_inherited && (
        <div className="text-xs text-muted-foreground bg-muted/50 border border-border rounded-xl px-3 py-2">
          Showing the program's own checklist — {readOnly ? "nothing has been overridden for this cohort yet." : "edit anything below to start this cohort's own override."}
        </div>
      )}
      {isStaff && !readOnly && (
        <div className="flex flex-col gap-2 p-3 bg-card border border-border rounded-xl">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="text-sm font-medium">Cohort Poster Template Override</div>
              <div className="text-xs text-muted-foreground mt-0.5">
                {override.inherited_poster_template_url
                  ? "Inheriting default template from program. Set an override for this cohort below."
                  : "Set a specific poster template for this cohort."}
              </div>
            </div>
            {effectivePosterUrl && (
              <a
                href={ensureAbsoluteUrl(effectivePosterUrl)}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-primary hover:underline flex items-center gap-1 shrink-0"
              >
                Open template <ExternalLink size={12} />
              </a>
            )}
          </div>
          <div className="flex items-center gap-2 mt-1">
            <input
              type="url"
              defaultValue={override.poster_template_url ?? ""}
              key={override.poster_template_url ?? ""}
              placeholder={override.inherited_poster_template_url ? `Inherited: ${override.inherited_poster_template_url}` : "https://canva.com/design/..."}
              className="flex-1 h-9 px-3 border border-border bg-background text-foreground rounded-lg text-sm focus:outline-none focus:border-primary transition-colors"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault()
                  const val = (e.target as HTMLInputElement).value.trim()
                  updateCohortPosterMutation.mutate(val || null)
                }
              }}
              onBlur={(e) => {
                const val = e.target.value.trim()
                if (val !== (override.poster_template_url ?? "")) {
                  updateCohortPosterMutation.mutate(val || null)
                }
              }}
            />
            {override.poster_template_url && (
              <button
                type="button"
                onClick={() => updateCohortPosterMutation.mutate(null)}
                className="text-xs text-muted-foreground hover:text-foreground px-2 py-1 cursor-pointer"
              >
                Clear override
              </button>
            )}
          </div>
        </div>
      )}
      {isStaff && !readOnly && !hideResync && (
        <div className="flex items-center justify-between gap-3 text-xs bg-muted/30 border border-border rounded-xl px-3 py-2">
          <span className="text-muted-foreground">
            Added a step and an already-assigned student isn't seeing it? New items backfill automatically now — this catches up anything added before that.
          </span>
          <button
            onClick={() => resyncMutation.mutate()}
            disabled={resyncMutation.isPending}
            className="shrink-0 h-7 px-3 rounded-full border border-border text-xs font-medium text-foreground hover:border-primary/50 hover:bg-primary/5 transition-colors disabled:opacity-50 cursor-pointer"
          >
            {resyncMutation.isPending ? "Resyncing…" : "Resync students"}
          </button>
        </div>
      )}
      <ChecklistItemsEditor
        items={override.items}
        readOnly={readOnly}
        cohortId={cohortId}
        onAdd={(data) => addCohortOverrideItemApi(cohortId, data).then(invalidate)}
        onUpdate={(itemId, data) => updateCohortOverrideItemApi(cohortId, itemId, data).then(invalidate)}
        onDelete={(itemId) => deleteCohortOverrideItemApi(cohortId, itemId).then(invalidate)}
        onUploadPdf={(itemId, file) => uploadLmsProgramItemPdfApi(itemId, file).then(invalidate)}
        onRemovePdf={(itemId) => deleteLmsProgramItemPdfApi(itemId).then(invalidate)}
        onUploadGuidelineVideo={(itemId, file) => uploadLmsProgramItemGuidelineVideoApi(itemId, file).then(invalidate)}
        onRemoveGuidelineVideo={(itemId) => deleteLmsProgramItemGuidelineVideoApi(itemId).then(invalidate)}
        onReorder={(itemIds) => reorderCohortOverrideItemsApi(cohortId, itemIds).then(invalidate)}
      />
    </div>
  )
}

export function ChecklistItemsEditor({
  items, onAdd, onUpdate, onDelete, onUploadPdf, onRemovePdf, onUploadGuidelineVideo, onRemoveGuidelineVideo,
  onReorder, readOnly, cohortId,
}: {
  items: LmsProgramItem[]
  onAdd: (data: LmsProgramItemInput) => Promise<unknown>
  onUpdate: (itemId: string, data: LmsProgramItemInput) => Promise<unknown>
  onDelete: (itemId: string) => Promise<unknown>
  onUploadPdf: (itemId: string, file: File) => Promise<unknown>
  onRemovePdf: (itemId: string) => Promise<unknown>
  onUploadGuidelineVideo: (itemId: string, file: File) => Promise<unknown>
  onRemoveGuidelineVideo: (itemId: string) => Promise<unknown>
  onReorder: (itemIds: string[]) => Promise<unknown>
  readOnly: boolean
  // Present only when this editor is scoped to one concrete cohort (the
  // cohort-override editor) — lets ItemForm offer a "prefill from an
  // existing session" picker for a `session` item. A program template can
  // span many cohorts with different session dates, so it's omitted there.
  cohortId?: string
}) {
  const [addingType, setAddingType] = useState<LmsProgramItemType | null>(null)
  // Individual vs. team is picked here, at add time, not toggled afterward —
  // a submission item's scope is locked server-side once created (flipping
  // it later silently orphans anything already submitted, since the two
  // scopes read/write completely different tables). Only matters when
  // addingType is "submission"; ItemForm ignores it for every other type.
  const [addingSubmissionScope, setAddingSubmissionScope] = useState<"individual" | "team">("individual")
  const [dragId, setDragId] = useState<string | null>(null)
  // Optimistic id order while a drag is in flight (or just settled) so the
  // row doesn't visually snap back before the parent's refetch lands —
  // cleared once the reorder call resolves, at which point `items` itself
  // should already reflect the new order.
  const [order, setOrder] = useState<string[] | null>(null)
  const [reordering, setReordering] = useState(false)
  const displayItems = order
    ? order.map((id) => items.find((i) => i.id === id)).filter((i): i is LmsProgramItem => !!i)
    : items

  const applyNewOrder = (ids: string[]) => {
    setOrder(ids)
    setReordering(true)
    void onReorder(ids).then(() => setOrder(null)).catch(() => setOrder(null)).finally(() => setReordering(false))
  }

  const dropOnto = (targetId: string) => {
    if (!dragId || dragId === targetId) { setDragId(null); return }
    const ids = displayItems.map((i) => i.id)
    const from = ids.indexOf(dragId)
    const to = ids.indexOf(targetId)
    setDragId(null)
    if (from === -1 || to === -1) return
    ids.splice(to, 0, ids.splice(from, 1)[0])
    applyNewOrder(ids)
  }

  // Order-number field (mobile-friendly alternative to drag-and-drop) —
  // computes the full id list for the typed 1-based position and reuses
  // the same single-transaction `onReorder` call, so no backend change is
  // needed. Out-of-range values clamp, same-position is a no-op.
  const moveToPosition = (itemId: string, targetPos: number) => {
    if (!Number.isFinite(targetPos)) return
    const ids = displayItems.map((i) => i.id)
    const from = ids.indexOf(itemId)
    if (from === -1) return
    const clamped = Math.min(Math.max(Math.round(targetPos), 1), ids.length)
    if (clamped - 1 === from) return
    ids.splice(clamped - 1, 0, ids.splice(from, 1)[0])
    applyNewOrder(ids)
  }

  // Roadmap board (2026-09) — every checkpoint_label already used on this
  // checklist, offered as a datalist so authoring a run of tiles for the
  // same checkpoint doesn't drift on a typo. Order-preserving, deduped.
  const checkpointLabels = Array.from(new Set(items.map((i) => i.checkpoint_label).filter((l): l is string => !!l)))

  const [previewItem, setPreviewItem] = useState<LmsProgramItem | null>(null)

  const [gatingAll, setGatingAll] = useState(false)
  const gateEverything = async () => {
    setGatingAll(true)
    try {
      for (const item of items) {
        if (!item.gated) await onUpdate(item.id, { ...itemToInput(item), gated: true })
      }
    } finally {
      setGatingAll(false)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {!readOnly && items.length > 1 && (
        <div className="flex justify-end">
          <button
            onClick={() => void gateEverything()}
            disabled={gatingAll || items.every((i) => i.gated)}
            className="h-7 px-3 rounded-full border border-dashed border-border text-xs font-medium text-muted-foreground hover:border-primary/50 hover:text-foreground transition-colors disabled:opacity-50 cursor-pointer"
          >
            {gatingAll ? "Gating…" : "Gate everything in order"}
          </button>
        </div>
      )}

      {displayItems.length === 0 && addingType === null && <EmptyState title="No steps yet" />}

      {displayItems.map((item, index) => (
        <ItemRow
          key={item.id} item={item} index={index + 1} totalCount={displayItems.length}
          onUpdate={onUpdate} onDelete={onDelete}
          onUploadPdf={onUploadPdf} onRemovePdf={onRemovePdf}
          onUploadGuidelineVideo={onUploadGuidelineVideo} onRemoveGuidelineVideo={onRemoveGuidelineVideo}
          onPreviewGuidelineVideo={() => setPreviewItem(item)}
          readOnly={readOnly}
          cohortId={cohortId} checkpointLabels={checkpointLabels}
          draggable={!readOnly}
          isDragging={dragId === item.id}
          onDragStartRow={() => setDragId(item.id)}
          onDropRow={() => dropOnto(item.id)}
          onDragEndRow={() => setDragId(null)}
          onMoveToPosition={readOnly ? undefined : (pos) => moveToPosition(item.id, pos)}
          reorderBusy={reordering}
        />
      ))}

      <Dialog open={!!previewItem} onOpenChange={(open) => !open && setPreviewItem(null)}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader><DialogTitle>{previewItem?.title}</DialogTitle></DialogHeader>
          {previewItem && <GuidelineVideoPreview itemId={previewItem.id} title={previewItem.title} />}
        </DialogContent>
      </Dialog>

      {readOnly ? null : addingType ? (
        <ItemForm
          itemType={addingType}
          initialScope={addingType === "submission" ? addingSubmissionScope : undefined}
          cohortId={cohortId} checkpointLabels={checkpointLabels}
          onCancel={() => setAddingType(null)}
          onSave={async (data) => { await onAdd(data); setAddingType(null) }}
        />
      ) : (
        <div className="flex flex-col gap-2 pt-2">
          <div className="text-xs font-semibold text-muted-foreground">Add a step</div>
          <div className="flex flex-wrap gap-2">
            {ITEM_TYPES.map(({ value, label, icon: Icon }) => {
              const addStepButtonCls = "flex items-center gap-1.5 h-8 px-3 rounded-full border border-dashed border-border text-xs font-medium text-foreground hover:border-primary/50 hover:bg-primary/5 transition-colors cursor-pointer"
              // Individual vs. team submission are two distinct buttons here
              // (not one "Submission" button + a scope checkbox in the form)
              // because the scope can't be changed once the item exists —
              // picking wrong and fixing it later isn't possible, so the
              // choice has to be explicit at this step.
              if (value === "submission") {
                return (
                  <Fragment key={value}>
                    <button
                      onClick={() => { setAddingSubmissionScope("individual"); setAddingType("submission") }}
                      className={addStepButtonCls}
                    >
                      <Icon size={13} /> Individual Submission
                    </button>
                    <button
                      onClick={() => { setAddingSubmissionScope("team"); setAddingType("submission") }}
                      className={addStepButtonCls}
                    >
                      <Users size={13} /> Team Submission
                    </button>
                  </Fragment>
                )
              }
              return (
                <button key={value} onClick={() => setAddingType(value)} className={addStepButtonCls}>
                  <Icon size={13} /> {label}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

/** Editable 1-based order number — the mobile-friendly alternative to
 * drag-and-drop. Commits on blur/Enter, reverts on Escape or invalid input. */
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
      aria-label="Step order number"
      title={`Step order (1–${totalCount}) — type a number to move this step`}
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
      className="w-11 h-7 px-1 border border-border bg-background text-foreground rounded-lg text-xs font-semibold text-center focus:outline-none focus:border-primary transition-colors disabled:opacity-50 shrink-0"
    />
  )
}

export function ItemRow({
  item, index, totalCount, onUpdate, onDelete, onUploadPdf, onRemovePdf, onUploadGuidelineVideo, onRemoveGuidelineVideo,
  onPreviewGuidelineVideo,
  readOnly, cohortId, checkpointLabels,
  draggable, isDragging, onDragStartRow, onDropRow, onDragEndRow,
  onMoveToPosition, reorderBusy,
}: {
  item: LmsProgramItem
  index?: number
  totalCount?: number
  onUpdate: (itemId: string, data: LmsProgramItemInput) => Promise<unknown>
  onDelete: (itemId: string) => Promise<unknown>
  // Optional — the mission-run-only list (ProgramMissionsPanel) never
  // renders a `pdf`/video-guideline item, so it has nothing to wire these to.
  onUploadPdf?: (itemId: string, file: File) => Promise<unknown>
  onRemovePdf?: (itemId: string) => Promise<unknown>
  onUploadGuidelineVideo?: (itemId: string, file: File) => Promise<unknown>
  onRemoveGuidelineVideo?: (itemId: string) => Promise<unknown>
  onPreviewGuidelineVideo?: () => void
  readOnly: boolean
  cohortId?: string
  checkpointLabels?: string[]
  draggable?: boolean
  isDragging?: boolean
  onDragStartRow?: () => void
  onDropRow?: () => void
  onDragEndRow?: () => void
  onMoveToPosition?: (pos: number) => void
  reorderBusy?: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [pdfBusy, setPdfBusy] = useState(false)
  const pdfInputRef = useRef<HTMLInputElement>(null)
  const [videoBusy, setVideoBusy] = useState(false)
  const videoInputRef = useRef<HTMLInputElement>(null)
  const meta = ITEM_TYPE_META[item.item_type]
  const Icon = meta.icon
  // A `pdf`-type item's own upload IS its guideline even when
  // guideline_kind isn't separately set — see services/lms/program.py's
  // note on this reuse (one file, one upload control either way).
  const showsPdfUpload = item.item_type === "pdf" || item.guideline_kind === "pdf"
  const showsVideoUpload = item.guideline_kind === "video"

  if (editing) {
    return (
      <ItemForm
        itemType={item.item_type}
        initial={item}
        cohortId={cohortId} checkpointLabels={checkpointLabels}
        onCancel={() => setEditing(false)}
        onSave={async (data) => { await onUpdate(item.id, data); setEditing(false) }}
      />
    )
  }

  return (
    <div
      draggable={draggable}
      onDragStart={draggable ? () => onDragStartRow?.() : undefined}
      onDragOver={draggable ? (e) => e.preventDefault() : undefined}
      onDrop={draggable ? (e) => { e.preventDefault(); onDropRow?.() } : undefined}
      onDragEnd={draggable ? () => onDragEndRow?.() : undefined}
      className={`flex flex-col sm:flex-row sm:items-center gap-3 p-3 bg-card border rounded-xl transition-colors ${
        isDragging ? "opacity-40 border-primary" : "border-border"
      } ${draggable ? "cursor-grab active:cursor-grabbing" : ""}`}
    >
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <GripVertical size={14} className="text-muted-foreground shrink-0 hidden sm:block" />
        {onMoveToPosition && totalCount && totalCount > 1 ? (
          <OrderNumberInput
            value={index ?? item.position}
            totalCount={totalCount}
            disabled={reorderBusy}
            onCommit={onMoveToPosition}
          />
        ) : (
          <span className="text-xs font-semibold text-muted-foreground w-5 text-center shrink-0">{index ?? item.position}</span>
        )}
        <div className="w-7 h-7 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0 text-primary">
          <Icon size={13} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-sm font-medium truncate">{item.title}</span>
            {item.scope === "team" && <span className="text-[10px] font-semibold uppercase text-primary border border-primary/30 bg-primary/5 rounded px-1.5 py-0.5">team</span>}
            {item.optional && <span className="text-[10px] font-semibold uppercase text-muted-foreground border border-border rounded px-1.5 py-0.5">optional</span>}
            {item.requires_confirmation && <span className="text-[10px] font-semibold uppercase text-primary border border-primary/30 rounded px-1.5 py-0.5">needs confirmation</span>}
            {item.gated && <span className="text-[10px] font-semibold uppercase text-primary border border-primary/30 bg-primary/5 rounded px-1.5 py-0.5">gated</span>}
            {item.mission_step_key && (
              <span className="text-[10px] font-semibold uppercase text-muted-foreground border border-border rounded px-1.5 py-0.5">
                {MISSION_STEP_KEYS.find((s) => s.value === item.mission_step_key)?.label ?? item.mission_step_key}
              </span>
            )}
            {item.guideline_kind && (
              <span className="text-[10px] font-semibold uppercase text-muted-foreground border border-border rounded px-1.5 py-0.5">guideline: {item.guideline_kind}</span>
            )}
            {item.item_type === "pdf" && !item.has_pdf && (
              <span className="text-[10px] font-semibold uppercase text-amber-600 dark:text-amber-500 border border-amber-500/30 rounded px-1.5 py-0.5">no PDF uploaded</span>
            )}
            {item.item_type === "quiz" && (
              item.cohort_quiz_question_count ? (
                <span className="text-[10px] font-semibold uppercase text-muted-foreground border border-border rounded px-1.5 py-0.5">
                  {item.cohort_quiz_question_count} question{item.cohort_quiz_question_count === 1 ? "" : "s"}
                </span>
              ) : (
                <span className="text-[10px] font-semibold uppercase text-amber-600 dark:text-amber-500 border border-amber-500/30 rounded px-1.5 py-0.5">no questions</span>
              )
            )}
          </div>
          {item.checkpoint_label && <div className="text-xs text-muted-foreground">{item.checkpoint_label}</div>}
          <div className="text-xs text-muted-foreground">{meta.label}</div>
        </div>
      </div>
      {!readOnly && (
        <div className="flex items-center gap-2 flex-wrap pl-8 sm:pl-0 sm:shrink-0">
          {showsPdfUpload && (
            <>
              <input
                ref={pdfInputRef} type="file" accept="application/pdf" className="hidden"
                onChange={async (e) => {
                  const file = e.target.files?.[0]
                  e.target.value = ""
                  if (!file) return
                  setPdfBusy(true)
                  try { await onUploadPdf?.(item.id, file) } finally { setPdfBusy(false) }
                }}
              />
              <button
                onClick={() => pdfInputRef.current?.click()}
                disabled={pdfBusy}
                className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer shrink-0 whitespace-nowrap disabled:opacity-50"
              >
                {pdfBusy ? "Uploading…" : item.has_pdf ? "Replace PDF" : "Upload PDF"}
              </button>
              {item.has_pdf && (
                <button
                  onClick={async () => { setPdfBusy(true); try { await onRemovePdf?.(item.id) } finally { setPdfBusy(false) } }}
                  disabled={pdfBusy}
                  className="text-xs font-medium text-muted-foreground hover:text-red-600 transition-colors cursor-pointer shrink-0 whitespace-nowrap disabled:opacity-50"
                >
                  Remove PDF
                </button>
              )}
            </>
          )}
          {showsVideoUpload && (
            <>
              <input
                ref={videoInputRef} type="file" accept="video/*" className="hidden"
                onChange={async (e) => {
                  const file = e.target.files?.[0]
                  e.target.value = ""
                  if (!file) return
                  setVideoBusy(true)
                  try { await onUploadGuidelineVideo?.(item.id, file) } finally { setVideoBusy(false) }
                }}
              />
              <button
                onClick={() => videoInputRef.current?.click()}
                disabled={videoBusy}
                className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer shrink-0 whitespace-nowrap disabled:opacity-50"
              >
                {videoBusy ? "Uploading…" : item.guideline_video_uploaded ? "Replace video" : "Upload video"}
              </button>
              {item.guideline_video_uploaded && (
                <>
                  <button
                    onClick={() => onPreviewGuidelineVideo?.()}
                    className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer shrink-0 whitespace-nowrap"
                  >
                    Preview
                  </button>
                  <button
                    onClick={async () => { setVideoBusy(true); try { await onRemoveGuidelineVideo?.(item.id) } finally { setVideoBusy(false) } }}
                    disabled={videoBusy}
                    className="text-xs font-medium text-muted-foreground hover:text-red-600 transition-colors cursor-pointer shrink-0 whitespace-nowrap disabled:opacity-50"
                  >
                    Remove video
                  </button>
                </>
              )}
            </>
          )}
          <button onClick={() => setEditing(true)} className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer shrink-0 whitespace-nowrap">
            Edit
          </button>
          <button
            onClick={() => onDelete(item.id)}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors shrink-0 cursor-pointer"
          >
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  )
}

export function ItemForm({
  itemType, initial, initialScope, cohortId, checkpointLabels, onCancel, onSave,
}: {
  itemType: LmsProgramItemType
  initial?: LmsProgramItem
  // Only meaningful for a brand-new "submission" item (which button on the
  // "Add a step" row was clicked) — ignored once `initial` is set, since an
  // existing item's scope is locked and always comes from `initial.scope`.
  initialScope?: "individual" | "team"
  // Present only when authoring on one concrete cohort's checklist —
  // powers the "prefill from an existing session" picker for a `session`
  // item. See ChecklistItemsEditor's own comment on why a program
  // template never passes this.
  cohortId?: string
  // Every checkpoint_label already used on this checklist — offered as a
  // datalist so a run of tiles for the same checkpoint doesn't drift on a
  // typo (Roadmap board, 2026-09).
  checkpointLabels?: string[]
  onCancel: () => void
  onSave: (data: LmsProgramItemInput) => Promise<void>
}) {
  const [title, setTitle] = useState(initial?.title ?? "")
  const [description, setDescription] = useState(initial?.description ?? "")
  const [optional, setOptional] = useState(initial?.optional ?? false)
  const [requiresConfirmation, setRequiresConfirmation] = useState(initial?.requires_confirmation ?? false)
  const [teamScoped, setTeamScoped] = useState(initial ? initial.scope === "team" : initialScope === "team")
  // Submission scope is locked at creation (server-side too — see
  // guard_locked_submission_scope) so it never shows as an editable
  // checkbox, only as a fixed label.
  const submissionScopeLocked = itemType === "submission"
  const [courseId, setCourseId] = useState(initial?.course_id ?? "")
  const [missionId, setMissionId] = useState(initial?.mission_id ?? "")
  const [variantId, setVariantId] = useState(initial?.variant_id ?? "")
  const [externalUrl, setExternalUrl] = useState(initial?.external_url ?? "")
  const [submissionPrompt, setSubmissionPrompt] = useState(initial?.submission_prompt ?? "")
  const [deadlineAt, setDeadlineAt] = useState(toDatetimeLocalValue(initial?.deadline_at))
  const [sessionDate, setSessionDate] = useState(initial?.session_date ?? "")
  const [sessionStartsAt, setSessionStartsAt] = useState(initial?.session_starts_at?.slice(0, 5) ?? "")
  const [sessionLocation, setSessionLocation] = useState(initial?.session_location ?? "")
  const [sessionMeetingUrl, setSessionMeetingUrl] = useState(initial?.session_meeting_url ?? "")
  const [prefillSessionId, setPrefillSessionId] = useState("")
  // ── Roadmap board (2026-09) ──────────────────────────────────────────
  const [missionStepKey, setMissionStepKey] = useState(initial?.mission_step_key ?? "")
  const [gated, setGated] = useState(initial?.gated ?? false)
  const [guidelineKind, setGuidelineKind] = useState<"" | "pdf" | "link" | "video">(initial?.guideline_kind ?? "")
  const [guidelineUrl, setGuidelineUrl] = useState(initial?.guideline_url ?? "")
  // A `video` guideline supports the same two paths a course lesson video
  // does — self-host (upload, transcoded to HLS) or a plain embeddable
  // link (YouTube, Vimeo, anything else with a public embed URL) — but
  // used to only ever surface the link field here, with a label
  // ("Video (YouTube/Vimeo)") that read as embed-only even though the
  // "Upload video" button on the item's own row (after saving) always
  // worked too. This toggle makes both paths visible up front instead of
  // one being a hidden feature. Defaults to whichever this item already
  // has: an existing embed URL means "embed", anything else (including a
  // brand-new item) means "upload".
  const [videoMode, setVideoMode] = useState<"upload" | "embed">(
    initial?.guideline_kind === "video" && initial?.guideline_url ? "embed" : "upload",
  )
  const [checkpointLabel, setCheckpointLabel] = useState(initial?.checkpoint_label ?? "")
  const [cohortQuizTemplateId, setCohortQuizTemplateId] = useState(initial?.cohort_quiz_template_id ?? "")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  const { data: courses = [] } = useQuery({ queryKey: ["lms-admin-courses"], queryFn: listCoursesApi, enabled: itemType === "course" })
  const { data: missions = [] } = useQuery({ queryKey: ["missions-admin-full"], queryFn: listMissionsAdminFullApi, enabled: itemType === "mission_run" })
  const { data: quizTemplates = [] } = useQuery({
    queryKey: ["cohort-quiz-templates"], queryFn: listCohortQuizTemplatesApi, enabled: itemType === "quiz",
  })
  const selectedMission = missions.find((m) => m.id === missionId)
  const { data: cohortSessions = [] } = useQuery({
    queryKey: ["cohort-sessions-for-prefill", cohortId],
    queryFn: () => getSessionsApi(cohortId as string),
    enabled: itemType === "session" && !!cohortId,
  })

  const applySessionPrefill = (sessionId: string) => {
    setPrefillSessionId(sessionId)
    const session = cohortSessions.find((s) => s.id === sessionId)
    if (!session) return
    if (!title.trim() && session.title) setTitle(session.title)
    setSessionDate(session.meeting_date)
    setSessionStartsAt(session.starts_at?.slice(0, 5) ?? "")
    setSessionLocation(session.effective_location_name ?? "")
  }

  // Falls back to `initial.mission_kind` (already known from the list this
  // item came from) rather than only `selectedMission?.kind` — the
  // `missions-admin-full` query can still be loading (or briefly fail) when
  // an existing item's Save is clicked, and `selectedMission` would then be
  // `undefined` for a mission that's actually still Design, silently
  // wiping a correctly-set `missionStepKey` down at line ~810 below.
  const isDesignMission = itemType === "mission_run" && (selectedMission
    ? selectedMission.kind === "design"
    : initial?.mission_id === missionId && initial?.mission_kind === "design")

  const save = async () => {
    setError("")
    if (!title.trim()) { setError("Title is required"); return }
    if (itemType === "course" && !courseId) { setError("Pick a course"); return }
    if (itemType === "mission_run" && !missionId) { setError("Pick a mission"); return }
    if (itemType === "external_link" && !externalUrl.trim()) { setError("A link is required"); return }
    if (itemType === "submission" && !externalUrl.trim() && !submissionPrompt.trim()) { setError("Add a link or a submission prompt"); return }
    if (itemType === "quiz" && !cohortQuizTemplateId) { setError("Pick a quiz template"); return }
    if (guidelineKind === "link" && !guidelineUrl.trim()) { setError("A link guideline needs a URL"); return }
    if (guidelineKind === "video" && videoMode === "embed" && !guidelineUrl.trim()) {
      setError("Add an embed link, or switch to Upload"); return
    }

    setSaving(true)
    try {
      await onSave({
        item_type: itemType,
        title: title.trim(),
        description: description.trim() || null,
        optional,
        requires_confirmation: requiresConfirmation,
        scope: TEAM_SCOPABLE_TYPES.has(itemType) && teamScoped ? "team" : "individual",
        course_id: itemType === "course" ? courseId : null,
        mission_id: itemType === "mission_run" ? missionId : null,
        variant_id: itemType === "mission_run" ? (variantId || null) : null,
        external_url: (itemType === "external_link" || itemType === "submission") ? (externalUrl.trim() || null) : null,
        submission_prompt: itemType === "submission" ? (submissionPrompt.trim() || null) : null,
        deadline_at: itemType === "submission" && deadlineAt ? new Date(deadlineAt).toISOString() : null,
        session_date: itemType === "session" ? (sessionDate || null) : null,
        session_starts_at: itemType === "session" ? (sessionStartsAt || null) : null,
        session_location: itemType === "session" ? (sessionLocation.trim() || null) : null,
        session_meeting_url: itemType === "session" ? (sessionMeetingUrl.trim() || null) : null,
        cohort_quiz_template_id: itemType === "quiz" ? cohortQuizTemplateId : null,
        mission_step_key: isDesignMission && missionStepKey ? missionStepKey : null,
        gated,
        guideline_kind: guidelineKind || null,
        guideline_url: guidelineKind === "link" ? (guidelineUrl.trim() || null)
          : guidelineKind === "video" && videoMode === "embed" ? (guidelineUrl.trim() || null)
          : null,
        checkpoint_label: checkpointLabel.trim() || null,
      })
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === "string" ? detail : "Failed to save")
    } finally {
      setSaving(false)
    }
  }

  const inputCls = "w-full h-9 px-3 border border-border bg-background text-foreground rounded-lg text-sm focus:outline-none focus:border-primary transition-colors"

  return (
    <div className="flex flex-col gap-2.5 p-4 border border-primary/30 bg-primary/5 rounded-xl">
      <div className="text-xs font-semibold text-primary">
        {submissionScopeLocked ? (teamScoped ? "Team Submission" : "Individual Submission") : ITEM_TYPE_META[itemType].label}
      </div>
      <input
        value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" className={inputCls}
        maxLength={255}
      />
      <textarea
        value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description (optional)"
        rows={2} className={`${inputCls} h-auto py-2 resize-none`}
      />

      {itemType === "course" && (
        <select value={courseId} onChange={(e) => setCourseId(e.target.value)} className={`${inputCls} cursor-pointer`}>
          <option value="">Select a course…</option>
          {courses.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
        </select>
      )}

      {itemType === "mission_run" && (
        <>
          <select
            value={missionId} onChange={(e) => { setMissionId(e.target.value); setVariantId("") }}
            className={`${inputCls} cursor-pointer`}
          >
            <option value="">Select a mission…</option>
            {missions.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}
          </select>
          {selectedMission && selectedMission.variants.length > 0 && (
            <select value={variantId} onChange={(e) => setVariantId(e.target.value)} className={`${inputCls} cursor-pointer`}>
              <option value="">Easiest variant (default)</option>
              {selectedMission.variants.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
            </select>
          )}
          {isDesignMission && (
            <div className="flex flex-col gap-1">
              <label className="text-[11px] font-medium text-muted-foreground">Which part of the mission?</label>
              <select value={missionStepKey} onChange={(e) => setMissionStepKey(e.target.value)} className={`${inputCls} cursor-pointer`}>
                <option value="">Whole mission</option>
                {PHASE_PICKER_KEYS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
              <span className="text-[11px] text-muted-foreground">
                A specific phase deep-links straight into that step of Madar and clears once it's valid there — you
                can still add the full mission as its own step too.
              </span>
            </div>
          )}
        </>
      )}

      {itemType === "external_link" && (
        <input value={externalUrl} onChange={(e) => setExternalUrl(e.target.value)} placeholder="https://…" className={inputCls} />
      )}

      {itemType === "pdf" && !initial && (
        <p className="text-xs text-muted-foreground">Upload the PDF after saving this step — see the "Upload PDF" button on its row.</p>
      )}

      {itemType === "session" && (
        <>
          {!!cohortId && cohortSessions.length > 0 && (
            <select
              value={prefillSessionId} onChange={(e) => applySessionPrefill(e.target.value)}
              className={`${inputCls} cursor-pointer`}
            >
              <option value="">Prefill from an existing session…</option>
              {cohortSessions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title || "Untitled session"} — {s.meeting_date}
                </option>
              ))}
            </select>
          )}
          <div className="flex gap-2.5">
            <input
              type="date" value={sessionDate} onChange={(e) => setSessionDate(e.target.value)}
              className={inputCls}
            />
            <input
              type="time" value={sessionStartsAt} onChange={(e) => setSessionStartsAt(e.target.value)}
              className={inputCls}
            />
          </div>
          <input
            value={sessionLocation} onChange={(e) => setSessionLocation(e.target.value)}
            placeholder="Location" className={inputCls}
          />
          <input
            value={sessionMeetingUrl} onChange={(e) => setSessionMeetingUrl(e.target.value)}
            placeholder="Meeting link (optional) — https://…" className={inputCls}
          />
        </>
      )}

      {itemType === "submission" && (
        <>
          <input value={externalUrl} onChange={(e) => setExternalUrl(e.target.value)} placeholder="Reference link (optional)" className={inputCls} />
          <textarea
            value={submissionPrompt} onChange={(e) => setSubmissionPrompt(e.target.value)} placeholder="What should the student submit back?"
            rows={2} className={`${inputCls} h-auto py-2 resize-none`}
          />
          <div className="flex flex-col gap-1">
            <input
              type="datetime-local" value={deadlineAt} onChange={(e) => setDeadlineAt(e.target.value)}
              className={inputCls}
            />
            <span className="text-[11px] text-muted-foreground">
              Deadline (optional). Leave blank for no deadline. After it passes, students can no longer submit or
              replace a link; already-submitted content and confirmation are unaffected.
            </span>
          </div>
        </>
      )}

      {itemType === "quiz" && (
        <div className="flex flex-col gap-1">
          <select
            value={cohortQuizTemplateId} onChange={(e) => setCohortQuizTemplateId(e.target.value)}
            className={`${inputCls} cursor-pointer`}
          >
            <option value="">Select a quiz template…</option>
            {quizTemplates
              // Hide retired templates from new picks — except whichever
              // one this item already points at, so an existing (now
              // stale) selection stays visible and clearly labeled rather
              // than silently vanishing from the list.
              .filter((t) => t.is_active || t.id === cohortQuizTemplateId)
              .map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.question_count} question{t.question_count === 1 ? "" : "s"}){!t.is_active ? " — retired" : ""}
                </option>
              ))}
          </select>
          <span className="text-[11px] text-muted-foreground">
            Every student on this checklist gets the exact same, fixed question set — build/edit templates on the
            Quiz Bank page.
          </span>
        </div>
      )}

      {/* Roadmap board (2026-09) — checkpoint grouping + the task drawer's
          guideline step. Shown for every item type, not just design phases:
          any tile can carry a guideline before its own work/submit steps. */}
      <div className="flex flex-col gap-1.5 pt-1 border-t border-border/60">
        <label className="text-[11px] font-medium text-muted-foreground">Checkpoint (optional)</label>
        <input
          value={checkpointLabel} onChange={(e) => setCheckpointLabel(e.target.value)}
          placeholder="e.g. Checkpoint 1 — Learn & plan" className={inputCls}
          list="checkpoint-label-options"
        />
        {checkpointLabels && checkpointLabels.length > 0 && (
          <datalist id="checkpoint-label-options">
            {checkpointLabels.map((label) => <option key={label} value={label} />)}
          </datalist>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] font-medium text-muted-foreground">Guideline (optional)</label>
        <select
          value={guidelineKind} onChange={(e) => setGuidelineKind(e.target.value as "" | "pdf" | "link" | "video")}
          className={`${inputCls} cursor-pointer`}
        >
          <option value="">No guideline</option>
          <option value="pdf">PDF</option>
          <option value="link">Link</option>
          <option value="video">Video</option>
        </select>
        {guidelineKind === "pdf" && (
          <p className="text-xs text-muted-foreground">
            {initial ? "Upload the PDF on this step's row after saving." : "Upload the PDF after saving this step — see the \"Upload PDF\" button on its row."}
          </p>
        )}
        {guidelineKind === "link" && (
          <input
            value={guidelineUrl} onChange={(e) => setGuidelineUrl(e.target.value)}
            placeholder="https://…"
            className={inputCls}
          />
        )}
        {guidelineKind === "video" && (
          <>
            <div className="flex gap-1.5">
              {(["upload", "embed"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setVideoMode(mode)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium border cursor-pointer transition-colors ${
                    videoMode === mode ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:border-primary/40"
                  }`}
                >
                  {mode === "upload" ? "Upload a file" : "Embed a link"}
                </button>
              ))}
            </div>
            {videoMode === "upload" ? (
              <p className="text-xs text-muted-foreground">
                {initial ? "Upload the video on this step's row after saving." : "Upload the video after saving this step — see the \"Upload video\" button on its row."}
              </p>
            ) : (
              <input
                value={guidelineUrl} onChange={(e) => setGuidelineUrl(e.target.value)}
                placeholder="https://… (YouTube, Vimeo, or any embeddable video link)"
                className={inputCls}
              />
            )}
          </>
        )}
      </div>

      <div className="flex items-center gap-4 pt-1 flex-wrap">
        <label className="flex items-center gap-1.5 text-xs text-foreground cursor-pointer">
          <input type="checkbox" checked={optional} onChange={(e) => setOptional(e.target.checked)} />
          Optional
        </label>
        <label className="flex items-center gap-1.5 text-xs text-foreground cursor-pointer">
          <input type="checkbox" checked={gated} onChange={(e) => setGated(e.target.checked)} />
          Locked until the previous task is done
        </label>
        <label className="flex items-center gap-1.5 text-xs text-foreground cursor-pointer">
          <input type="checkbox" checked={requiresConfirmation} onChange={(e) => setRequiresConfirmation(e.target.checked)} />
          Needs instructor/ops confirmation
        </label>
        {TEAM_SCOPABLE_TYPES.has(itemType) && !submissionScopeLocked && (
          <label className="flex items-center gap-1.5 text-xs text-foreground cursor-pointer">
            <input type="checkbox" checked={teamScoped} onChange={(e) => setTeamScoped(e.target.checked)} />
            Shared with the whole team (one submission per team)
          </label>
        )}
        {submissionScopeLocked && (
          <span className="text-xs text-muted-foreground">
            {teamScoped ? "Shared with the whole team — one submission per team." : "Each student submits their own."}
            {initial && " Can't be changed — delete and re-add the item to switch."}
          </span>
        )}
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      <div className="flex gap-2 pt-1">
        <button
          onClick={() => void save()} disabled={saving}
          className="h-9 px-4 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:opacity-90 transition-colors disabled:opacity-50 cursor-pointer"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        <button onClick={onCancel} className="h-9 px-3 border border-border rounded-lg text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer">
          Cancel
        </button>
      </div>
    </div>
  )
}
