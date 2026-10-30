/** Program Roles & Default Days/Checklists Template (V2 Upgrade)
 *
 *  - Box Day Selector: Pre-Workshop (General) + Day 1..N template days + "+ Add Day"
 *  - Day Editor: inline title & duration editing, day deletion
 *  - Reorderable Checklist Items: GripVertical drag-and-drop, OrderNumberInput, Up/Down controls
 *  - Role Customization: General vs Lead Facilitator vs Facilitator etc.
 *  - Role Rates & Openings: clean sub-tab for setting platform/program role defaults
 */
import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ChevronDown,
  ChevronUp,
  ClipboardCheck,
  ExternalLink,
  Eye,
  FileText,
  GripVertical,
  ImageIcon,
  Link2,
  Plus,
  Trash2,
  X,
} from "lucide-react"
import type { Program } from "@/types/sessions"
import {
  getDeliveryRolesApi,
  getProgramOpeningsApi,
  setProgramOpeningsApi,
  getMaterialsApi,
  type Material,
  type MaterialOwner,
} from "@/api/sessions/openings"
import {
  getProgramTemplateApi,
  addProgramTemplateDayApi,
  updateProgramTemplateDayApi,
  deleteProgramTemplateDayApi,
} from "@/api/sessions/programs"
import { listChecklistItemsApi, setChecklistItemsApi, type ChecklistScope } from "@/api/sessions/day"
import {
  OrderNumberInput,
  toDraftLines,
  type ChecklistDraftLine,
} from "@/pages/admin/components/CohortRolesPanel"
import { useToast } from "@/components/ui/toast"
import { cn, ensureAbsoluteUrl, getErrorMessage } from "@/lib/utils"
import { MediaPreviewModal } from "@/components/media/MediaPreviewModal"
import { ChecklistAttachmentPicker } from "./ChecklistAttachmentPicker"
import { PreSessionQuizAssignmentBar } from "./PreSessionQuizAssignmentBar"

interface RoleDraft {
  role_id: string
  slots: number
  amount_aed: string
  notes: string
  responsibilities_override: string
  existing: boolean
}

/** Reorderable checklist items list with drag-and-drop & order numbers */
function ProgramChecklistList({
  rows,
  onChange,
  availableMaterials = [],
  owner,
  onMaterialUploaded,
}: {
  rows: ChecklistDraftLine[]
  onChange: (updated: ChecklistDraftLine[]) => void
  availableMaterials?: Material[]
  owner?: MaterialOwner
  onMaterialUploaded?: (mat: Material) => void
}) {
  const toast = useToast()
  const [dragKey, setDragKey] = useState<string | null>(null)
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set())
  const [previewMedia, setPreviewMedia] = useState<{
    title: string
    type: "pdf" | "video"
    url: string
  } | null>(null)

  const toggleExpanded = (key: string, hasSubs: boolean, rowIndex: number) => {
    setExpandedKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
        if (!hasSubs) {
          const current = [...rows]
          const existingSubs = current[rowIndex].sub_items ?? []
          if (existingSubs.length === 0) {
            current[rowIndex] = {
              ...current[rowIndex],
              sub_items: [
                {
                  id: `sub-${Date.now()}-0`,
                  title: "",
                  is_required: true,
                },
              ],
            }
            onChange(current)
          }
        }
      }
      return next
    })
  }

  const dropOnto = (targetKey: string) => {
    if (!dragKey || dragKey === targetKey) {
      setDragKey(null)
      return
    }
    const current = [...rows]
    const from = current.findIndex((x) => x.key === dragKey)
    const to = current.findIndex((x) => x.key === targetKey)
    setDragKey(null)
    if (from === -1 || to === -1) return
    const [moved] = current.splice(from, 1)
    current.splice(to, 0, moved)
    onChange(current)
  }

  const moveToPosition = (itemKey: string, targetPos: number) => {
    if (!Number.isFinite(targetPos)) return
    const current = [...rows]
    const from = current.findIndex((x) => x.key === itemKey)
    if (from === -1) return
    const clamped = Math.min(Math.max(Math.round(targetPos), 1), current.length)
    if (clamped - 1 === from) return
    const [moved] = current.splice(from, 1)
    current.splice(clamped - 1, 0, moved)
    onChange(current)
  }

  const moveUp = (index: number) => {
    if (index <= 0) return
    const current = [...rows]
    const [moved] = current.splice(index, 1)
    current.splice(index - 1, 0, moved)
    onChange(current)
  }

  const moveDown = (index: number) => {
    if (index >= rows.length - 1) return
    const current = [...rows]
    const [moved] = current.splice(index, 1)
    current.splice(index + 1, 0, moved)
    onChange(current)
  }

  if (rows.length === 0) {
    return (
      <div className="py-7 text-center text-xs text-muted-foreground border border-dashed border-border rounded-xl">
        No checklist items yet for this template day. Click &ldquo;Add item&rdquo; below.
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {rows.map((line, i) => (
        <div
          key={line.key}
          draggable
          onDragStart={() => setDragKey(line.key)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault()
            dropOnto(line.key)
          }}
          onDragEnd={() => setDragKey(null)}
          className={`flex flex-col sm:flex-row sm:items-start gap-2 p-2.5 sm:p-2 bg-card border rounded-xl transition-all ${
            dragKey === line.key
              ? "opacity-40 border-primary ring-1 ring-primary/40"
              : "border-border hover:border-border/80"
          }`}
        >
          {/* Top bar on mobile / Reorder controls on desktop */}
          <div className="flex items-center justify-between sm:justify-start gap-1.5 shrink-0 sm:pt-1 flex-wrap">
            <div className="flex items-center gap-1 shrink-0 text-muted-foreground" title="Drag to reorder">
              <GripVertical
                size={15}
                className="cursor-grab active:cursor-grabbing hover:text-foreground shrink-0"
              />
              <OrderNumberInput
                value={i + 1}
                totalCount={rows.length}
                onCommit={(pos) => moveToPosition(line.key, pos)}
              />
            </div>

            <div className="flex items-center gap-0.5 shrink-0">
              <button
                type="button"
                onClick={() => moveUp(i)}
                disabled={i === 0}
                title="Move up"
                className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-20 transition-colors cursor-pointer"
              >
                <ChevronUp size={13} />
              </button>
              <button
                type="button"
                onClick={() => moveDown(i)}
                disabled={i === rows.length - 1}
                title="Move down"
                className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-20 transition-colors cursor-pointer"
              >
                <ChevronDown size={13} />
              </button>
            </div>

            {/* Mobile-only action buttons in top row */}
            <div className="flex items-center gap-1 sm:hidden flex-wrap">
              <button
                type="button"
                onClick={() => toggleExpanded(line.key, (line.sub_items?.length || 0) > 0, i)}
                className={cn(
                  "h-6 px-1.5 rounded text-[11px] font-medium border flex items-center gap-0.5 shrink-0 cursor-pointer",
                  (line.sub_items?.length || 0) > 0
                    ? "border-primary/40 text-primary bg-primary/10"
                    : "border-border text-muted-foreground"
                )}
                title={(line.sub_items?.length || 0) > 0 ? "Edit sub-topics" : "Add sub-topics"}
              >
                <span>{(line.sub_items?.length || 0) > 0 ? `Subs (${line.sub_items!.length})` : "+ Subs"}</span>
              </button>
              <label className="flex items-center gap-1 text-[11px] text-muted-foreground cursor-pointer select-none px-1.5 py-0.5 rounded-md hover:bg-muted/50">
                <input
                  type="checkbox"
                  checked={line.is_required}
                  onChange={(e) =>
                    onChange(rows.map((r, j) => (j === i ? { ...r, is_required: e.target.checked } : r)))
                  }
                  className="rounded border-border text-primary focus:ring-primary size-3"
                />
                <span>Req</span>
              </label>
              <label className="flex items-center gap-1 text-[11px] text-muted-foreground cursor-pointer select-none px-1.5 py-0.5 rounded-md hover:bg-muted/50">
                <input
                  type="checkbox"
                  checked={line.requires_proof}
                  onChange={(e) =>
                    onChange(rows.map((r, j) => (j === i ? { ...r, requires_proof: e.target.checked } : r)))
                  }
                  className="rounded border-border text-primary focus:ring-primary size-3"
                />
                <span>Photo</span>
              </label>
              <button
                type="button"
                onClick={() => onChange(rows.filter((_, j) => j !== i))}
                className="p-1 text-muted-foreground hover:text-red-500 hover:bg-red-500/10 rounded transition-colors shrink-0 cursor-pointer"
                aria-label="Remove item"
              >
                <Trash2 size={13} />
              </button>
            </div>
          </div>

          {/* Description input + Attached References tags + Picker + Sub-topics */}
          <div className="flex flex-col gap-1.5 flex-1 min-w-0 w-full">
            <input
              value={line.title}
              placeholder="Checklist item description… (supports [Links](url))"
              onChange={(e) =>
                onChange(rows.map((r, j) => (j === i ? { ...r, title: e.target.value } : r)))
              }
              className="w-full h-8 px-2.5 border border-border bg-background text-foreground rounded-lg text-xs sm:text-sm focus:outline-none focus:border-primary transition-colors"
            />

            {/* Attached References Pills + Attach button */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {(line.attachments ?? []).map((att, attIdx) => {
                const targetMat = att.material_id ? availableMaterials.find((m) => m.id === att.material_id) : null
                const resolvedUrl = att.url || targetMat?.url
                const isPdf = Boolean(
                  (resolvedUrl && (resolvedUrl.toLowerCase().endsWith(".pdf") || resolvedUrl.toLowerCase().includes(".pdf"))) ||
                  (att.title && att.title.toLowerCase().endsWith(".pdf")) ||
                  (targetMat?.filename && targetMat.filename.toLowerCase().endsWith(".pdf"))
                )
                const isFile = Boolean(att.is_file || targetMat?.filename || isPdf)

                const handleView = (e: React.MouseEvent) => {
                  e.preventDefault()
                  e.stopPropagation()
                  if (!resolvedUrl) {
                    toast.error("No link or file URL available for this reference")
                    return
                  }
                  if (isPdf) {
                    setPreviewMedia({
                      title: att.title || targetMat?.title || "Document Preview",
                      type: "pdf",
                      url: ensureAbsoluteUrl(resolvedUrl),
                    })
                  } else {
                    window.open(ensureAbsoluteUrl(resolvedUrl), "_blank", "noopener,noreferrer")
                  }
                }

                return (
                  <div
                    key={att.id || attIdx}
                    className={cn(
                      "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium border transition-colors group max-w-full",
                      isFile
                        ? "bg-primary/10 text-primary border-primary/20"
                        : "bg-muted text-foreground border-border"
                    )}
                  >
                    {isFile ? (
                      <FileText size={11} className="shrink-0 text-primary" />
                    ) : (
                      <Link2 size={11} className="shrink-0 text-muted-foreground" />
                    )}

                    {/* Clickable title */}
                    <button
                      type="button"
                      onClick={handleView}
                      className="truncate max-w-[120px] sm:max-w-xs hover:underline cursor-pointer text-left font-medium"
                      title={resolvedUrl ? `View item: ${resolvedUrl}` : "View item"}
                    >
                      {att.title || att.url || "Reference"}
                    </button>

                    {/* Distinct View Item button */}
                    <button
                      type="button"
                      onClick={handleView}
                      className={cn(
                        "inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold transition-colors cursor-pointer",
                        isFile
                          ? "bg-primary/20 hover:bg-primary/30 text-primary"
                          : "bg-background/90 hover:bg-background text-foreground/80 hover:text-foreground border border-border/60"
                      )}
                      title="View item"
                    >
                      <Eye size={10} className="shrink-0" />
                      <span>View</span>
                      <ExternalLink size={9} className="shrink-0 opacity-70" />
                    </button>

                    {/* Remove Reference */}
                    <button
                      type="button"
                      onClick={() => {
                        const nextAtts = (line.attachments ?? []).filter((_, idx) => idx !== attIdx)
                        onChange(rows.map((r, j) => (j === i ? { ...r, attachments: nextAtts } : r)))
                      }}
                      className="ml-0.5 text-muted-foreground hover:text-red-500 cursor-pointer p-0.5"
                      title="Remove reference"
                    >
                      <X size={11} />
                    </button>
                  </div>
                )
              })}

              <ChecklistAttachmentPicker
                availableMaterials={availableMaterials}
                owner={owner}
                onMaterialUploaded={onMaterialUploaded}
                onAdd={(newAtt) => {
                  const nextAtts = [...(line.attachments ?? []), newAtt]
                  onChange(rows.map((r, j) => (j === i ? { ...r, attachments: nextAtts } : r)))
                }}
              />
            </div>

            {/* Sub-topics list (indented, matching Judging Criteria style) */}
            {expandedKeys.has(line.key) && (
              <div className="w-full mt-1.5 pt-2 border-t border-border/60 flex flex-col gap-2 pl-1 sm:pl-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                    <span className="text-primary font-bold">↳</span> Sub-topics / Checklist steps
                  </span>
                  {(line.sub_items ?? []).length > 0 && (
                    <span className="text-[10px] text-muted-foreground">
                      {(line.sub_items ?? []).length} sub-topic{(line.sub_items ?? []).length === 1 ? "" : "s"}
                    </span>
                  )}
                </div>

                {(line.sub_items ?? []).map((sub, subIdx) => (
                  <div key={sub.id || subIdx} className="flex items-center gap-2 pl-1">
                    <span className="text-muted-foreground text-xs w-3 shrink-0">↳</span>
                    <input
                      value={sub.title}
                      placeholder="Sub-topic description…"
                      onChange={(e) => {
                        const nextSubs = (line.sub_items ?? []).map((s, idx) =>
                          idx === subIdx ? { ...s, title: e.target.value } : s
                        )
                        onChange(rows.map((r, j) => (j === i ? { ...r, sub_items: nextSubs } : r)))
                      }}
                      className="flex-1 min-w-0 h-7 px-2.5 border border-border bg-background text-foreground rounded-lg text-xs focus:outline-none focus:border-primary transition-colors"
                    />
                    <label className="flex items-center gap-1 text-[11px] text-muted-foreground cursor-pointer select-none px-1.5 py-0.5 rounded hover:bg-muted/50 shrink-0">
                      <input
                        type="checkbox"
                        checked={sub.is_required !== false}
                        onChange={(e) => {
                          const nextSubs = (line.sub_items ?? []).map((s, idx) =>
                            idx === subIdx ? { ...s, is_required: e.target.checked } : s
                          )
                          onChange(rows.map((r, j) => (j === i ? { ...r, sub_items: nextSubs } : r)))
                        }}
                        className="rounded border-border text-primary focus:ring-primary size-3"
                      />
                      <span className="hidden sm:inline">Required</span>
                      <span className="sm:hidden">Req</span>
                    </label>
                    <button
                      type="button"
                      onClick={() => {
                        const nextSubs = (line.sub_items ?? []).filter((_, idx) => idx !== subIdx)
                        onChange(rows.map((r, j) => (j === i ? { ...r, sub_items: nextSubs } : r)))
                      }}
                      className="p-1 text-muted-foreground hover:text-red-500 hover:bg-red-500/10 rounded transition-colors shrink-0 cursor-pointer"
                      title="Remove sub-topic"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}

                <button
                  type="button"
                  onClick={() => {
                    const nextSubs = [
                      ...(line.sub_items ?? []),
                      {
                        id: `sub-${Date.now()}-${(line.sub_items ?? []).length}`,
                        title: "",
                        is_required: true,
                      },
                    ]
                    onChange(rows.map((r, j) => (j === i ? { ...r, sub_items: nextSubs } : r)))
                  }}
                  className="self-start flex items-center gap-1 text-xs font-medium text-primary hover:opacity-80 pl-4 py-0.5 cursor-pointer"
                >
                  <Plus size={12} /> Add sub-topic
                </button>
              </div>
            )}
          </div>

          {/* Desktop-only Right section: Subs, Required, Photo, and Delete */}
          <div className="hidden sm:flex items-center justify-end gap-1.5 shrink-0 sm:pt-1">
            <button
              type="button"
              onClick={() => toggleExpanded(line.key, (line.sub_items?.length || 0) > 0, i)}
              title={(line.sub_items?.length || 0) > 0 ? "Edit sub-topics" : "Add sub-topics"}
              className={cn(
                "h-7 px-2 rounded-lg text-xs font-medium border transition-colors flex items-center gap-1 shrink-0 cursor-pointer",
                (line.sub_items?.length || 0) > 0
                  ? "border-primary/40 text-primary bg-primary/10"
                  : "border-border text-muted-foreground hover:text-foreground hover:bg-muted/50"
              )}
            >
              <Plus size={11} />
              <span>{(line.sub_items?.length || 0) > 0 ? `Subs (${line.sub_items!.length})` : "+ Subs"}</span>
            </button>

            <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer whitespace-nowrap select-none px-1.5 py-1 rounded-md hover:bg-muted/50">
              <input
                type="checkbox"
                checked={line.is_required}
                onChange={(e) =>
                  onChange(rows.map((r, j) => (j === i ? { ...r, is_required: e.target.checked } : r)))
                }
                className="rounded border-border text-primary focus:ring-primary"
              />
              <span>Required</span>
            </label>

            <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer whitespace-nowrap select-none px-1.5 py-1 rounded-md hover:bg-muted/50">
              <input
                type="checkbox"
                checked={line.requires_proof}
                onChange={(e) =>
                  onChange(rows.map((r, j) => (j === i ? { ...r, requires_proof: e.target.checked } : r)))
                }
                className="rounded border-border text-primary focus:ring-primary"
              />
              <ImageIcon size={13} />
              <span>Photo</span>
            </label>

            <button
              type="button"
              onClick={() => onChange(rows.filter((_, j) => j !== i))}
              className="p-1.5 text-muted-foreground hover:text-red-500 hover:bg-red-500/10 rounded-lg transition-colors shrink-0 cursor-pointer"
              aria-label="Remove item"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      ))}

      <MediaPreviewModal
        open={!!previewMedia}
        onClose={() => setPreviewMedia(null)}
        title={previewMedia?.title ?? "Document preview"}
        type={previewMedia?.type ?? "pdf"}
        url={previewMedia?.url}
      />
    </div>
  )
}

/** Program Day Checklist Editor */
function ProgramDayChecklistEditor({
  scope,
  ownerId,
  programId,
  roleId,
  roleName,
  dayTitle,
  targetAudience = "instructor",
}: {
  scope: ChecklistScope
  ownerId: string
  programId: string
  roleId: string | null
  roleName: string
  dayTitle: string
  targetAudience?: "instructor" | "internal"
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [draft, setDraft] = useState<ChecklistDraftLine[] | null>(null)
  const [error, setError] = useState("")

  const audienceKey = targetAudience === "internal" ? "internal" : (roleId ?? "general")
  const queryKey = ["checklist-items", scope, ownerId, audienceKey]
  const { data: items = [], isLoading } = useQuery({
    queryKey,
    queryFn: () => listChecklistItemsApi(scope, ownerId, roleId, targetAudience),
  })

  // Load materials available for attaching
  const { data: availableMaterials = [] } = useQuery({
    queryKey: ["materials-for-program-checklist", programId],
    queryFn: () => getMaterialsApi({ program_id: programId }),
  })

  useEffect(() => {
    setDraft(null)
    setError("")
  }, [scope, ownerId, roleId, targetAudience])

  useEffect(() => {
    if (draft !== null || isLoading) return
    setDraft(toDraftLines(items))
  }, [isLoading, items, draft])

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = (draft ?? []).map((l, i) => ({
        title: l.title,
        description: l.description,
        requires_proof: l.requires_proof,
        is_required: l.is_required,
        material_id: l.material_id,
        link_url: l.link_url,
        attachments: l.attachments ?? [],
        sub_items: l.sub_items ?? [],
        sort_order: i + 1,
      }))
      return setChecklistItemsApi(scope, ownerId, payload, roleId, targetAudience)
    },
    onSuccess: () => {
      toast.success(`${dayTitle} checklist saved`)
      setError("")
      qc.invalidateQueries({ queryKey })
    },
    onError: (e: any) => setError(getErrorMessage(e, "Could not save checklist")),
  })

  const rows = draft ?? []

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-foreground">{dayTitle}</span>
          <span className="text-xs text-muted-foreground">· {roleName}</span>
          <span className="px-2 py-0.5 rounded-full text-[11px] font-medium border bg-primary/10 text-primary border-primary/20 shrink-0">
            {rows.length} item{rows.length === 1 ? "" : "s"}
          </span>
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            type="button"
            onClick={() =>
              setDraft([
                ...rows,
                {
                  key: `new-${Date.now()}-${rows.length}`,
                  title: "",
                  requires_proof: false,
                  is_required: true,
                },
              ])
            }
            className="flex items-center gap-1 h-8 px-2.5 border border-dashed border-border rounded-lg text-xs font-medium text-foreground hover:border-primary/50 hover:bg-primary/5 transition-colors cursor-pointer"
          >
            <Plus size={13} /> Add item
          </button>

          <button
            type="button"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || isLoading}
            className="flex items-center gap-1 h-8 px-3.5 bg-primary text-primary-foreground rounded-lg text-xs font-semibold hover:opacity-90 disabled:opacity-50 transition-opacity cursor-pointer shadow-sm"
          >
            {saveMutation.isPending ? "Saving…" : "Save checklist"}
          </button>
        </div>
      </div>

      {error && <p className="text-xs text-red-500 bg-red-500/10 p-2 rounded-lg">{error}</p>}

      {isLoading ? (
        <div className="py-8 text-center text-xs text-muted-foreground">Loading checklist…</div>
      ) : (
        <ProgramChecklistList
          rows={rows}
          onChange={setDraft}
          availableMaterials={availableMaterials}
          owner={{ program_id: programId }}
          onMaterialUploaded={() => {
            qc.invalidateQueries({ queryKey: ["materials-for-program-checklist"] })
          }}
        />
      )}
    </div>
  )
}

/** Main ProgramRolesPanel */
export function ProgramRolesPanel({ program }: { program: Program }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [activeTab, setActiveTab] = useState<"days" | "rates">("days")
  const [selectedDayId, setSelectedDayId] = useState<string>("default")
  const [activeRoleId, setActiveRoleId] = useState<string | null>(null)
  const [isInternalChecklist, setIsInternalChecklist] = useState(false)
  const [dayTitleInput, setDayTitleInput] = useState("")
  const [dayDurationInput, setDayDurationInput] = useState("")

  // 1. Roles
  const { data: roles = [], isLoading: rolesLoading } = useQuery({
    queryKey: ["delivery-roles"],
    queryFn: () => getDeliveryRolesApi(),
  })
  const { data: openings = [], isLoading: openingsLoading } = useQuery({
    queryKey: ["program-openings-defaults", program.id],
    queryFn: () => getProgramOpeningsApi(program.id),
  })

  // 2. Program Template Days
  const { data: template, isLoading: templateLoading } = useQuery({
    queryKey: ["program-template", program.id],
    queryFn: () => getProgramTemplateApi(program.id),
  })

  const templateSessions = template?.sessions ?? []
  const isDefaultSelected = selectedDayId === "default"
  const selectedSession = !isDefaultSelected
    ? templateSessions.find((s) => s.id === selectedDayId)
    : null

  // Keep title/duration input in sync with selected session
  useEffect(() => {
    if (selectedSession) {
      setDayTitleInput(selectedSession.title || "")
      setDayDurationInput(selectedSession.duration_hours != null ? String(selectedSession.duration_hours) : "4")
    }
  }, [selectedSession])

  // If selected session was deleted or doesn't exist, fall back to "default" or first session
  useEffect(() => {
    if (!isDefaultSelected && !selectedSession && templateSessions.length > 0) {
      setSelectedDayId("default")
    }
  }, [isDefaultSelected, selectedSession, templateSessions])

  // Mutations for adding/updating/deleting template days
  const addDayMutation = useMutation({
    mutationFn: () =>
      addProgramTemplateDayApi(program.id, {
        title: `Day ${templateSessions.length + 1}`,
        duration_hours: (program as any).duration_hours ? Number((program as any).duration_hours) : 4.0,
      }),
    onSuccess: (newDay) => {
      toast.success(`Added ${newDay.title || "new day"}`)
      qc.invalidateQueries({ queryKey: ["program-template", program.id] })
      setSelectedDayId(newDay.id)
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Could not add day")),
  })

  const updateDayMutation = useMutation({
    mutationFn: (data: { title?: string; duration_hours?: number }) =>
      updateProgramTemplateDayApi(program.id, selectedDayId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["program-template", program.id] })
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Could not update day")),
  })

  const deleteDayMutation = useMutation({
    mutationFn: (sessId: string) => deleteProgramTemplateDayApi(program.id, sessId),
    onSuccess: () => {
      toast.success("Day deleted from template")
      qc.invalidateQueries({ queryKey: ["program-template", program.id] })
      setSelectedDayId("default")
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Could not delete day")),
  })

  // 3. Roles rates draft
  const [ratesDraft, setRatesDraft] = useState<RoleDraft[] | null>(null)
  const [ratesError, setRatesError] = useState("")

  const toRatesDraft = () =>
    roles
      .filter((r) => r.is_active)
      .map((r) => {
        const o = openings.find((x) => x.role_id === r.id)
        return {
          role_id: r.id,
          slots: o?.slots ?? 1,
          amount_aed: o?.amount_aed != null ? String(o.amount_aed) : "",
          notes: o?.notes ?? "",
          responsibilities_override:
            o?.responsibilities_override ?? o?.role_description ?? r.description ?? "",
          existing: o != null,
        }
      })

  useEffect(() => {
    if (roles.length && !openingsLoading) setRatesDraft(toRatesDraft())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roles, openings, openingsLoading])

  const saveRatesMutation = useMutation({
    mutationFn: () =>
      setProgramOpeningsApi({
        programId: program.id,
        openings: (ratesDraft ?? [])
          .filter(
            (d) =>
              d.existing ||
              d.amount_aed !== "" ||
              d.notes ||
              d.responsibilities_override ||
              d.slots !== 1,
          )
          .map((d) => ({
            role_id: d.role_id,
            slots: d.slots,
            amount_aed: d.amount_aed === "" ? null : Number(d.amount_aed),
            notes: d.notes || null,
            responsibilities_override: d.responsibilities_override || null,
          })),
      }),
    onSuccess: () => {
      toast.success("Roles saved")
      setRatesError("")
      qc.invalidateQueries({ queryKey: ["program-openings-defaults", program.id] })
    },
    onError: (e: any) => setRatesError(getErrorMessage(e, "Could not save roles")),
  })

  if (rolesLoading || templateLoading) {
    return <p className="text-xs text-muted-foreground py-2">Loading program template…</p>
  }

  const selectedDayIndex = selectedSession
    ? templateSessions.findIndex((s) => s.id === selectedSession.id)
    : -1

  const activeDayTitle = isDefaultSelected
    ? "Pre-Workshop / General"
    : selectedSession?.title || `Day ${selectedDayIndex + 1}`

  const activeRoleName = isInternalChecklist
    ? "Internal Checklist"
    : activeRoleId
      ? roles.find((r) => r.id === activeRoleId)?.name || "Role"
      : "All Roles (General)"

  return (
    <div className="flex flex-col gap-4 py-1">
      {/* Sub-tab navigation: Default Days & Checklists vs Role Rates & Slots */}
      <div className="flex items-center gap-1.5 border-b border-border pb-2.5">
        <button
          type="button"
          onClick={() => setActiveTab("days")}
          className={cn(
            "h-8 px-3.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer",
            activeTab === "days"
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground hover:bg-muted",
          )}
        >
          Default Days &amp; Checklists
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("rates")}
          className={cn(
            "h-8 px-3.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer",
            activeTab === "rates"
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground hover:bg-muted",
          )}
        >
          Role Rates &amp; Slots
        </button>
      </div>

      {activeTab === "days" ? (
        <div className="flex flex-col gap-4">
          {/* 1. Box Day Selector Cards */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Program Template Days
              </span>
              <span className="text-xs text-muted-foreground">
                {templateSessions.length} day{templateSessions.length === 1 ? "" : "s"} defined (cohorts inherit these)
              </span>
            </div>

            <div className="flex items-stretch gap-2 overflow-x-auto pb-1 scrollbar-none no-scrollbar">
              {/* Pre-Workshop Card */}
              <button
                type="button"
                onClick={() => setSelectedDayId("default")}
                className={cn(
                  "flex flex-col justify-between min-w-[130px] sm:min-w-[150px] p-2.5 rounded-xl border text-left transition-all shrink-0 cursor-pointer",
                  isDefaultSelected
                    ? "border-primary bg-primary/10 shadow-sm ring-1 ring-primary/30"
                    : "border-border bg-card hover:bg-muted/50 hover:border-border/80",
                )}
              >
                <div>
                  <span
                    className={cn(
                      "text-[10px] font-bold uppercase tracking-wider",
                      isDefaultSelected ? "text-primary" : "text-muted-foreground",
                    )}
                  >
                    Pre-Workshop
                  </span>
                  <p className="text-xs sm:text-sm font-semibold text-foreground truncate mt-0.5">
                    General Default
                  </p>
                </div>
                <span className="text-[11px] text-muted-foreground mt-2 truncate">
                  All days fallback
                </span>
              </button>

              {/* Template Day Cards */}
              {templateSessions.map((session, idx) => {
                const isSelected = selectedDayId === session.id
                const dayLabel = `Day ${idx + 1}`

                return (
                  <button
                    key={session.id}
                    type="button"
                    onClick={() => setSelectedDayId(session.id)}
                    className={cn(
                      "flex flex-col justify-between min-w-[130px] sm:min-w-[150px] p-2.5 rounded-xl border text-left transition-all shrink-0 cursor-pointer",
                      isSelected
                        ? "border-primary bg-primary/10 shadow-sm ring-1 ring-primary/30"
                        : "border-border bg-card hover:bg-muted/50 hover:border-border/80",
                    )}
                  >
                    <div className="w-full">
                      <div className="flex items-center justify-between w-full">
                        <span
                          className={cn(
                            "text-[10px] font-bold uppercase tracking-wider",
                            isSelected ? "text-primary" : "text-muted-foreground",
                          )}
                        >
                          {dayLabel}
                        </span>
                        {session.duration_hours && (
                          <span className="text-[10px] text-muted-foreground">
                            {session.duration_hours}h
                          </span>
                        )}
                      </div>
                      <p className="text-xs sm:text-sm font-semibold text-foreground truncate mt-0.5">
                        {session.title || dayLabel}
                      </p>
                    </div>
                    <span className="text-[11px] text-muted-foreground mt-2 truncate">
                      Template day
                    </span>
                  </button>
                )
              })}

              {/* + Add Day Button Card */}
              <button
                type="button"
                onClick={() => addDayMutation.mutate()}
                disabled={addDayMutation.isPending}
                className="flex flex-col items-center justify-center min-w-[100px] p-2.5 rounded-xl border border-dashed border-border hover:border-primary/60 hover:bg-primary/5 text-muted-foreground hover:text-foreground transition-all shrink-0 cursor-pointer"
                title="Add a default day to this program template"
              >
                <Plus size={16} className="mb-1 text-primary" />
                <span className="text-xs font-medium">Add Day</span>
              </button>
            </div>
          </div>

          {/* 2. Day Settings (Title & Duration) */}
          {!isDefaultSelected && selectedSession && (
            <div className="flex flex-col sm:flex-row sm:items-center gap-2.5 p-2.5 bg-muted/40 border border-border rounded-xl">
              <div className="flex-1 min-w-0 w-full sm:w-auto">
                <label className="text-[10px] font-semibold uppercase text-muted-foreground block mb-0.5">
                  Day Title
                </label>
                <input
                  type="text"
                  value={dayTitleInput}
                  onChange={(e) => setDayTitleInput(e.target.value)}
                  onBlur={() => {
                    const trimmed = dayTitleInput.trim()
                    if (trimmed && trimmed !== selectedSession.title) {
                      updateDayMutation.mutate({ title: trimmed })
                    }
                  }}
                  placeholder="e.g. SatKit Assembly & Sensors"
                  className="w-full h-8 px-2.5 bg-background border border-border rounded-lg text-xs font-medium text-foreground focus:outline-none focus:border-primary transition-colors"
                />
              </div>

              <div className="flex items-center gap-2 w-full sm:w-auto justify-between sm:justify-start">
                <div className="w-28 sm:w-24">
                  <label className="text-[10px] font-semibold uppercase text-muted-foreground block mb-0.5">
                    Duration (hrs)
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    min="0.5"
                    value={dayDurationInput}
                    onChange={(e) => setDayDurationInput(e.target.value)}
                    onBlur={() => {
                      const parsed = parseFloat(dayDurationInput)
                      if (parsed > 0 && parsed !== selectedSession.duration_hours) {
                        updateDayMutation.mutate({ duration_hours: parsed })
                      }
                    }}
                    className="w-full h-8 px-2 bg-background border border-border rounded-lg text-xs font-medium text-foreground focus:outline-none focus:border-primary transition-colors"
                  />
                </div>

                <div className="flex items-end self-end">
                  <button
                    type="button"
                    onClick={() => {
                      if (confirm(`Delete "${selectedSession.title || `Day ${selectedDayIndex + 1}`}" from this program template?`)) {
                        deleteDayMutation.mutate(selectedSession.id)
                      }
                    }}
                    disabled={deleteDayMutation.isPending || templateSessions.length <= 1}
                    className="h-8 px-2.5 text-xs text-muted-foreground hover:text-red-500 hover:bg-red-500/10 border border-border rounded-lg transition-colors disabled:opacity-30 cursor-pointer flex items-center gap-1"
                    title={templateSessions.length <= 1 ? "Program must have at least one day" : "Delete this day"}
                  >
                    <Trash2 size={13} />
                    <span>Delete Day</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* 3. Role Selector Pills */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none no-scrollbar">
            <button
              type="button"
              onClick={() => {
                setIsInternalChecklist(false)
                setActiveRoleId(null)
              }}
              className={cn(
                "h-7 px-3 rounded-full text-xs font-medium transition-colors shrink-0 cursor-pointer",
                !isInternalChecklist && activeRoleId === null
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted",
              )}
            >
              All Roles (General)
            </button>
            {roles
              .filter((r) => r.is_active)
              .map((role) => {
                const isRoleActive = !isInternalChecklist && activeRoleId === role.id
                return (
                  <button
                    key={role.id}
                    type="button"
                    onClick={() => {
                      setIsInternalChecklist(false)
                      setActiveRoleId(role.id)
                    }}
                    className={cn(
                      "h-7 px-3 rounded-full text-xs font-medium transition-colors shrink-0 cursor-pointer",
                      isRoleActive
                        ? "bg-primary text-primary-foreground shadow-sm"
                        : "bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted",
                    )}
                  >
                    {role.name}
                  </button>
                )
              })}
            <button
              type="button"
              onClick={() => {
                setIsInternalChecklist(true)
                setActiveRoleId(null)
              }}
              className={cn(
                "h-7 px-3 rounded-full text-xs font-medium transition-colors shrink-0 cursor-pointer flex items-center gap-1.5 border border-dashed",
                isInternalChecklist
                  ? "bg-primary text-primary-foreground border-transparent shadow-sm"
                  : "border-border text-muted-foreground hover:text-foreground hover:bg-muted",
              )}
            >
              <ClipboardCheck size={12} />
              Internal Checklist
            </button>
          </div>

          {/* 3.5. Pre-Session Quiz Preset Assignment (Program / Template Session) */}
          <PreSessionQuizAssignmentBar
            scope={isDefaultSelected ? "programs" : "sessions"}
            ownerId={isDefaultSelected ? program.id : selectedDayId}
            dayTitle={activeDayTitle}
          />

          {/* 4. Active Day & Role Checklist Editor */}
          <div className="p-3 sm:p-4 rounded-xl border border-border bg-card/60">
            <ProgramDayChecklistEditor
              scope={isDefaultSelected ? "programs" : "sessions"}
              ownerId={isDefaultSelected ? program.id : selectedDayId}
              programId={program.id}
              roleId={activeRoleId}
              roleName={activeRoleName}
              dayTitle={activeDayTitle}
              targetAudience={isInternalChecklist ? "internal" : "instructor"}
            />
          </div>
        </div>
      ) : (
        /* Role Rates & Slots Tab */
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-foreground">Program Default Rates &amp; Openings</p>
              <p className="text-xs text-muted-foreground">
                Copied into every new cohort created from this program template.
              </p>
            </div>
            <button
              type="button"
              onClick={() => saveRatesMutation.mutate()}
              disabled={saveRatesMutation.isPending}
              className="h-8 px-4 bg-primary text-primary-foreground text-xs font-semibold rounded-lg hover:opacity-90 disabled:opacity-40 transition-colors shadow-sm cursor-pointer"
            >
              {saveRatesMutation.isPending ? "Saving…" : "Save roles"}
            </button>
          </div>

          {ratesError && <p className="text-xs text-red-500 bg-red-500/10 p-2 rounded-lg">{ratesError}</p>}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {(ratesDraft ?? []).map((d, i) => {
              const role = roles.find((r) => r.id === d.role_id)
              if (!role) return null

              return (
                <div key={d.role_id} className="border border-border rounded-xl p-3 bg-card flex flex-col gap-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-foreground">{role.name}</span>
                    <span className="text-xs text-muted-foreground">
                      Platform Default: {role.default_rate_aed != null ? `${role.default_rate_aed} AED` : "None"}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <label className="flex flex-col gap-1">
                      <span className="text-[10px] font-semibold uppercase text-muted-foreground">
                        Rate (AED)
                      </span>
                      <input
                        type="number"
                        min={0}
                        placeholder={role.default_rate_aed != null ? String(role.default_rate_aed) : "0"}
                        value={d.amount_aed}
                        onChange={(e) =>
                          setRatesDraft(
                            (ratesDraft ?? []).map((x, j) =>
                              j === i ? { ...x, amount_aed: e.target.value } : x,
                            ),
                          )
                        }
                        className="h-8 px-2 border border-border bg-background text-foreground rounded-lg text-xs tabular-nums focus:outline-none focus:border-primary transition-colors"
                      />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-[10px] font-semibold uppercase text-muted-foreground">
                        Slots
                      </span>
                      <input
                        type="number"
                        min={1}
                        value={d.slots}
                        onChange={(e) =>
                          setRatesDraft(
                            (ratesDraft ?? []).map((x, j) =>
                              j === i ? { ...x, slots: Math.max(1, Number(e.target.value) || 1) } : x,
                            ),
                          )
                        }
                        className="h-8 px-2 border border-border bg-background text-foreground rounded-lg text-xs tabular-nums focus:outline-none focus:border-primary transition-colors"
                      />
                    </label>
                  </div>

                  <label className="flex flex-col gap-1">
                    <span className="text-[10px] font-semibold uppercase text-muted-foreground">
                      Responsibilities override
                    </span>
                    <textarea
                      rows={2}
                      placeholder={role.description || "Role description…"}
                      value={d.responsibilities_override}
                      onChange={(e) =>
                        setRatesDraft(
                          (ratesDraft ?? []).map((x, j) =>
                            j === i ? { ...x, responsibilities_override: e.target.value } : x,
                          ),
                        )
                      }
                      className="px-2 py-1.5 border border-border bg-background text-foreground rounded-lg text-xs resize-y focus:outline-none focus:border-primary transition-colors"
                    />
                  </label>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
