/** Cohort Roles & Delivery Checklists (V2 Upgrade)
 *
 *  - Box Day Selector: sleek horizontal cards for Pre-Workshop (Cohort Default) + each session day.
 *  - Delivery Checklists: reorderable checklist items with GripVertical drag-and-drop, OrderNumberInput,
 *    and up/down controls (matching LMS checklist authoring).
 *  - Role Customization: filter/customize checklists per role (Lead Facilitator, Facilitator, etc.) or General.
 *  - Batch Actions: fill default for all sessions, or copy default into a single session.
 *  - Minimal text, SpacePoint brand colors (heliotrope primary, card borders, no hardcoded blues).
 */
import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Copy,
  GripVertical,
  ImageIcon,
  Plus,
  RotateCcw,
  Send,
  Trash2,
} from "lucide-react"
import type { Cohort, ChecklistItem, Session } from "@/types/sessions"
import {
  getDeliveryRolesApi,
  getCohortOpeningsApi,
  setCohortOpeningsApi,
  type DeliveryRole,
} from "@/api/sessions/openings"
import { getSessionsApi } from "@/api/sessions/cohorts"
import { listChecklistItemsApi, setChecklistItemsApi, type ChecklistScope } from "@/api/sessions/day"
import { useToast } from "@/components/ui/toast"
import { cn, getErrorMessage } from "@/lib/utils"

export type ChecklistDraftLine = {
  key: string
  title: string
  requires_proof: boolean
  is_required: boolean
}

export function toDraftLines(items: ChecklistItem[]): ChecklistDraftLine[] {
  return items.map((i) => ({
    key: i.id || `item-${Math.random().toString(36).substring(2, 9)}`,
    title: i.title,
    requires_proof: i.requires_proof,
    is_required: i.is_required,
  }))
}

/** Fallback resolution ladder:
 *  1. If scope is session -> check cohort for role, then cohort general.
 *  2. If roleId is set -> check same level general.
 *  3. Program level -> program for role, then program general.
 */
async function fetchFallbackChecklistItems(
  scope: ChecklistScope,
  ownerId: string,
  programId?: string,
  roleId?: string | null,
  cohortId?: string,
): Promise<ChecklistItem[]> {
  if (scope === "sessions" && cohortId) {
    if (roleId) {
      try {
        const cohortRole = await listChecklistItemsApi("cohorts", cohortId, roleId)
        if (cohortRole.length > 0) return cohortRole
      } catch {}
    }
    try {
      const cohortGen = await listChecklistItemsApi("cohorts", cohortId, null)
      if (cohortGen.length > 0) return cohortGen
    } catch {}
  }

  if (roleId) {
    try {
      const sameLevelGeneral = await listChecklistItemsApi(scope, ownerId, null)
      if (sameLevelGeneral.length > 0) return sameLevelGeneral
    } catch {}
  }

  if (programId) {
    if (roleId) {
      try {
        const progRole = await listChecklistItemsApi("programs", programId, roleId)
        if (progRole.length > 0) return progRole
      } catch {}
    }
    try {
      const progGeneral = await listChecklistItemsApi("programs", programId, null)
      if (progGeneral.length > 0) return progGeneral
    } catch {}
  }
  return []
}

/** Editable order number box (mobile & keyboard friendly jump-to-position) */
export function OrderNumberInput({
  value,
  totalCount,
  onCommit,
  disabled,
}: {
  value: number
  totalCount: number
  onCommit: (pos: number) => void
  disabled?: boolean
}) {
  const [text, setText] = useState(String(value))
  useEffect(() => {
    setText(String(value))
  }, [value])

  const commit = () => {
    const parsed = Number.parseInt(text, 10)
    if (!Number.isFinite(parsed) || parsed === value) {
      setText(String(value))
      return
    }
    onCommit(parsed)
    setText(String(value))
  }

  return (
    <input
      type="number"
      value={text}
      min={1}
      max={totalCount}
      inputMode="numeric"
      disabled={disabled}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur()
        if (e.key === "Escape") {
          setText(String(value))
          ;(e.target as HTMLInputElement).blur()
        }
      }}
      onClick={(e) => e.stopPropagation()}
      className="w-9 h-7 px-1 border border-border bg-background text-foreground rounded text-xs font-semibold text-center focus:outline-none focus:border-primary transition-colors disabled:opacity-50 shrink-0"
    />
  )
}

/** Reorderable checklist items list with drag-and-drop & order numbers */
function ReorderableChecklistList({
  rows,
  onChange,
}: {
  rows: ChecklistDraftLine[]
  onChange: (updated: ChecklistDraftLine[]) => void
}) {
  const [dragKey, setDragKey] = useState<string | null>(null)

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
      <div className="py-8 text-center text-xs text-muted-foreground border border-dashed border-border rounded-xl">
        No checklist items yet. Click &ldquo;Add item&rdquo; below or copy from default.
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
          className={`flex items-center gap-2 p-2 bg-card border rounded-xl transition-all ${
            dragKey === line.key
              ? "opacity-40 border-primary ring-1 ring-primary/40"
              : "border-border hover:border-border/80"
          }`}
        >
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
              className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-20 transition-colors"
            >
              <ChevronUp size={13} />
            </button>
            <button
              type="button"
              onClick={() => moveDown(i)}
              disabled={i === rows.length - 1}
              title="Move down"
              className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-20 transition-colors"
            >
              <ChevronDown size={13} />
            </button>
          </div>

          <input
            value={line.title}
            placeholder="Checklist item description…"
            onChange={(e) =>
              onChange(rows.map((r, j) => (j === i ? { ...r, title: e.target.value } : r)))
            }
            className="flex-1 min-w-[10rem] h-8 px-2.5 border border-border bg-background text-foreground rounded-lg text-xs sm:text-sm focus:outline-none focus:border-primary transition-colors"
          />

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
            className="p-1.5 text-muted-foreground hover:text-red-500 hover:bg-red-500/10 rounded-lg transition-colors shrink-0"
            aria-label="Remove item"
          >
            <Trash2 size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}

/** Active checklist bucket editor for a selected day and role */
function DayChecklistEditor({
  scope,
  ownerId,
  programId,
  cohortId,
  roleId,
  roleName,
  dayTitle,
  isDefaultScope,
  allSessions,
}: {
  scope: ChecklistScope
  ownerId: string
  programId?: string
  cohortId: string
  roleId: string | null
  roleName: string
  dayTitle: string
  isDefaultScope: boolean
  allSessions: Session[]
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [draft, setDraft] = useState<ChecklistDraftLine[] | null>(null)
  const [isInherited, setIsInherited] = useState(false)
  const [isLoadingFallback, setIsLoadingFallback] = useState(false)
  const [error, setError] = useState("")
  const [isApplyingAll, setIsApplyingAll] = useState(false)

  const queryKey = ["checklist-items", scope, ownerId, roleId ?? "general"]
  const { data: items = [], isLoading } = useQuery({
    queryKey,
    queryFn: () => listChecklistItemsApi(scope, ownerId, roleId),
  })

  // Reset draft on day/role switch
  useEffect(() => {
    setDraft(null)
    setIsInherited(false)
    setError("")
  }, [scope, ownerId, roleId])

  useEffect(() => {
    if (draft !== null || isLoading) return

    if (items.length > 0) {
      setDraft(toDraftLines(items))
      setIsInherited(false)
    } else {
      setIsLoadingFallback(true)
      fetchFallbackChecklistItems(scope, ownerId, programId, roleId, cohortId)
        .then((fb) => {
          setDraft(toDraftLines(fb))
          setIsInherited(fb.length > 0)
        })
        .catch(() => {
          setDraft([])
          setIsInherited(false)
        })
        .finally(() => setIsLoadingFallback(false))
    }
  }, [isLoading, items, draft, scope, ownerId, programId, roleId, cohortId])

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = (draft ?? []).map((l, i) => ({
        title: l.title,
        requires_proof: l.requires_proof,
        is_required: l.is_required,
        sort_order: i + 1,
      }))
      return setChecklistItemsApi(scope, ownerId, payload, roleId)
    },
    onSuccess: () => {
      toast.success(`${dayTitle} checklist saved`)
      setError("")
      setIsInherited(false)
      qc.invalidateQueries({ queryKey })
    },
    onError: (e: any) => setError(getErrorMessage(e, "Could not save checklist")),
  })

  // Copy default checklist into this session
  const handleCopyFromDefault = async () => {
    try {
      const defaultItems = await listChecklistItemsApi("cohorts", cohortId, roleId)
      if (defaultItems.length > 0) {
        setDraft(toDraftLines(defaultItems))
        setIsInherited(false)
        toast.success("Copied default checklist items")
      } else {
        const progDefault = programId
          ? await listChecklistItemsApi("programs", programId, roleId)
          : []
        if (progDefault.length > 0) {
          setDraft(toDraftLines(progDefault))
          setIsInherited(false)
          toast.success("Copied program checklist items")
        } else {
          toast.error("No default checklist found to copy")
        }
      }
    } catch {
      toast.error("Failed to copy default items")
    }
  }

  // Revert session override back to template
  const handleRevertToTemplate = async () => {
    try {
      await setChecklistItemsApi(scope, ownerId, [], roleId)
      qc.invalidateQueries({ queryKey })
      setDraft(null)
      toast.success("Reverted to inherited template")
    } catch {
      toast.error("Failed to revert checklist")
    }
  }

  // Apply default list to all sessions
  const handleApplyToAllSessions = async () => {
    if (allSessions.length === 0) {
      toast.error("No sessions in this cohort to apply to")
      return
    }
    const currentRows = draft ?? []
    if (currentRows.length === 0) {
      toast.error("Add at least one item before applying to all")
      return
    }
    setIsApplyingAll(true)
    try {
      const payload = currentRows.map((l, i) => ({
        title: l.title,
        requires_proof: l.requires_proof,
        is_required: l.is_required,
        sort_order: i + 1,
      }))
      await Promise.all(
        allSessions.map((s) => setChecklistItemsApi("sessions", s.id, payload, roleId)),
      )
      qc.invalidateQueries({ queryKey: ["checklist-items"] })
      toast.success(`Checklist applied to all ${allSessions.length} sessions`)
    } catch {
      toast.error("Failed to apply checklist to all sessions")
    } finally {
      setIsApplyingAll(false)
    }
  }

  const rows = draft ?? []
  const loading = isLoading || isLoadingFallback || draft === null

  return (
    <div className="flex flex-col gap-3">
      {/* Header bar with status badge & action buttons */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-foreground">{dayTitle}</span>
          <span className="text-xs text-muted-foreground">· {roleName}</span>
          <span
            className={cn(
              "px-2 py-0.5 rounded-full text-[11px] font-medium border shrink-0",
              isInherited || (items.length === 0 && rows.length > 0)
                ? "bg-muted text-muted-foreground border-border"
                : "bg-primary/10 text-primary border-primary/20",
            )}
          >
            {isInherited ? "Inherited" : rows.length > 0 ? `${rows.length} items` : "Empty"}
          </span>
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
          {!isDefaultScope && (
            <>
              <button
                type="button"
                onClick={handleCopyFromDefault}
                className="flex items-center gap-1 h-8 px-2.5 border border-border rounded-lg text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
                title="Copy checklist items from cohort default"
              >
                <Copy size={13} /> Copy Default
              </button>
              {!isInherited && items.length > 0 && (
                <button
                  type="button"
                  onClick={handleRevertToTemplate}
                  className="flex items-center gap-1 h-8 px-2.5 border border-border rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                  title="Clear override and revert to template inheritance"
                >
                  <RotateCcw size={13} /> Revert
                </button>
              )}
            </>
          )}

          {isDefaultScope && allSessions.length > 0 && (
            <button
              type="button"
              onClick={handleApplyToAllSessions}
              disabled={isApplyingAll || rows.length === 0}
              className="flex items-center gap-1 h-8 px-2.5 border border-border rounded-lg text-xs font-medium text-foreground hover:bg-muted disabled:opacity-50 transition-colors cursor-pointer"
              title="Apply this default checklist to all sessions in this cohort"
            >
              <Send size={13} /> {isApplyingAll ? "Applying…" : "Apply to All Days"}
            </button>
          )}

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
            disabled={saveMutation.isPending || loading}
            className="flex items-center gap-1 h-8 px-3.5 bg-primary text-primary-foreground rounded-lg text-xs font-semibold hover:opacity-90 disabled:opacity-50 transition-opacity cursor-pointer shadow-sm"
          >
            {saveMutation.isPending ? "Saving…" : "Save checklist"}
          </button>
        </div>
      </div>

      {error && <p className="text-xs text-red-500 bg-red-500/10 p-2 rounded-lg">{error}</p>}

      {loading ? (
        <div className="py-8 text-center text-xs text-muted-foreground">Loading checklist…</div>
      ) : (
        <ReorderableChecklistList rows={rows} onChange={setDraft} />
      )}
    </div>
  )
}

/** Cohort Day Checklist Manager: Box Day Selector + Role Switcher + Checklist Editor */
export function CohortDayChecklistManager({
  cohort,
  sessions,
  roles,
  initialSessionId,
}: {
  cohort: Cohort
  sessions: Session[]
  roles: DeliveryRole[]
  initialSessionId?: string
}) {
  const sortedSessions = [...sessions].sort((a, b) => {
    const d = a.meeting_date.localeCompare(b.meeting_date)
    return d !== 0 ? d : (a.starts_at || "").localeCompare(b.starts_at || "")
  })

  const [selectedDay, setSelectedDay] = useState<string>(initialSessionId || "default")
  const [activeRoleId, setActiveRoleId] = useState<string | null>(null)

  const isDefaultScope = selectedDay === "default"
  const currentSession = !isDefaultScope ? sortedSessions.find((s) => s.id === selectedDay) : null
  const currentDayIndex = currentSession
    ? sortedSessions.findIndex((s) => s.id === currentSession.id)
    : -1

  const dayTitle = isDefaultScope
    ? "Pre-Workshop / Default"
    : currentSession?.title
      ? `Day ${currentDayIndex + 1}: ${currentSession.title}`
      : `Day ${currentDayIndex + 1}`

  const activeRoleName = activeRoleId
    ? roles.find((r) => r.id === activeRoleId)?.name || "Role"
    : "All Roles (General)"

  return (
    <div className="flex flex-col gap-4">
      {/* 1. Box Day Selector Cards */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Day Selector
          </span>
          {sortedSessions.length > 0 && (
            <span className="text-xs text-muted-foreground">
              {sortedSessions.length} session{sortedSessions.length === 1 ? "" : "s"}
            </span>
          )}
        </div>

        <div className="flex items-stretch gap-2 overflow-x-auto pb-1 scrollbar-none no-scrollbar">
          {/* Pre-Workshop / General Default Card */}
          <button
            type="button"
            onClick={() => setSelectedDay("default")}
            className={cn(
              "flex flex-col justify-between min-w-[130px] sm:min-w-[150px] p-2.5 rounded-xl border text-left transition-all shrink-0 cursor-pointer",
              selectedDay === "default"
                ? "border-primary bg-primary/10 shadow-sm ring-1 ring-primary/30"
                : "border-border bg-card hover:bg-muted/50 hover:border-border/80",
            )}
          >
            <div>
              <span
                className={cn(
                  "text-[10px] font-bold uppercase tracking-wider",
                  selectedDay === "default" ? "text-primary" : "text-muted-foreground",
                )}
              >
                Pre-Workshop
              </span>
              <p className="text-xs sm:text-sm font-semibold text-foreground truncate mt-0.5">
                Cohort Default
              </p>
            </div>
            <span className="text-[11px] text-muted-foreground mt-2 truncate">
              Shared fallback
            </span>
          </button>

          {/* Session Day Cards */}
          {sortedSessions.map((session, idx) => {
            const isSelected = selectedDay === session.id
            const dayLabel = `Day ${idx + 1}`
            const dateFormatted = session.meeting_date
              ? new Date(session.meeting_date).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })
              : ""

            return (
              <button
                key={session.id}
                type="button"
                onClick={() => setSelectedDay(session.id)}
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
                    {dateFormatted && (
                      <span className="text-[10px] text-muted-foreground">{dateFormatted}</span>
                    )}
                  </div>
                  <p className="text-xs sm:text-sm font-semibold text-foreground truncate mt-0.5">
                    {session.title || dayLabel}
                  </p>
                </div>
                <span className="text-[11px] text-muted-foreground mt-2 truncate">
                  {session.title ? dateFormatted || `Session ${idx + 1}` : "Day checklist"}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* 2. Role Selector Pills */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none no-scrollbar">
        <button
          type="button"
          onClick={() => setActiveRoleId(null)}
          className={cn(
            "h-7 px-3 rounded-full text-xs font-medium transition-colors shrink-0 cursor-pointer",
            activeRoleId === null
              ? "bg-primary text-primary-foreground shadow-sm"
              : "bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted",
          )}
        >
          All Roles (General)
        </button>
        {roles
          .filter((r) => r.is_active)
          .map((role) => {
            const isRoleActive = activeRoleId === role.id
            return (
              <button
                key={role.id}
                type="button"
                onClick={() => setActiveRoleId(role.id)}
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
      </div>

      {/* 3. Active Day & Role Checklist Editor */}
      <div className="p-3 sm:p-4 rounded-xl border border-border bg-card/60">
        <DayChecklistEditor
          scope={isDefaultScope ? "cohorts" : "sessions"}
          ownerId={isDefaultScope ? cohort.id : selectedDay}
          programId={cohort.program_id}
          cohortId={cohort.id}
          roleId={activeRoleId}
          roleName={activeRoleName}
          dayTitle={dayTitle}
          isDefaultScope={isDefaultScope}
          allSessions={sortedSessions}
        />
      </div>
    </div>
  )
}

/** Legacy ChecklistSection kept for ProgramRolesPanel and backward compatibility */
export function ChecklistSection({
  scope,
  ownerId,
  programId,
  roleId,
  label,
  hint,
  large: _large = false,
  forceOpen = false,
}: {
  scope: ChecklistScope
  ownerId: string
  programId?: string
  roleId: string | null
  label: string
  hint: string
  large?: boolean
  forceOpen?: boolean
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [manualOpen, setManualOpen] = useState(false)
  const open = forceOpen || manualOpen
  const [draft, setDraft] = useState<ChecklistDraftLine[] | null>(null)
  const [isInherited, setIsInherited] = useState(false)
  const [isLoadingFallback, setIsLoadingFallback] = useState(false)
  const [error, setError] = useState("")

  const queryKey = ["checklist-items", scope, ownerId, roleId ?? "general"]
  const { data: items = [], isLoading } = useQuery({
    queryKey,
    queryFn: () => listChecklistItemsApi(scope, ownerId, roleId),
    enabled: open,
  })

  useEffect(() => {
    if (!open || draft !== null || isLoading) return

    if (items.length > 0) {
      setDraft(toDraftLines(items))
      setIsInherited(false)
    } else {
      setIsLoadingFallback(true)
      fetchFallbackChecklistItems(scope, ownerId, programId, roleId)
        .then((fb) => {
          setDraft(toDraftLines(fb))
          setIsInherited(fb.length > 0)
        })
        .catch(() => {
          setDraft([])
          setIsInherited(false)
        })
        .finally(() => setIsLoadingFallback(false))
    }
  }, [open, isLoading, items, draft, scope, ownerId, programId, roleId])

  const save = useMutation({
    mutationFn: () =>
      setChecklistItemsApi(
        scope,
        ownerId,
        (draft ?? []).map((l, i) => ({
          title: l.title,
          requires_proof: l.requires_proof,
          is_required: l.is_required,
          sort_order: i + 1,
        })),
        roleId,
      ),
    onSuccess: () => {
      toast.success(`${label} checklist saved`)
      setError("")
      setIsInherited(false)
      qc.invalidateQueries({ queryKey })
    },
    onError: (e: any) => setError(getErrorMessage(e, "Could not save this checklist")),
  })

  const rows = draft ?? []

  return (
    <div className="border border-border rounded-xl p-3 bg-card/40">
      <div className="flex items-center justify-between mb-2">
        <button
          type="button"
          onClick={() => setManualOpen(!open)}
          className="flex items-center gap-1.5 text-xs font-semibold text-foreground hover:text-primary transition-colors cursor-pointer"
        >
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <span>{label}</span>
          <span className="text-muted-foreground font-normal">
            · {rows.length} item{rows.length === 1 ? "" : "s"}
          </span>
          {isInherited && (
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-muted text-muted-foreground border border-border">
              Inherited
            </span>
          )}
        </button>
        <span className="text-[11px] text-muted-foreground">{hint}</span>
      </div>

      {open && (
        <div className="pt-2 flex flex-col gap-2.5">
          {isLoading || isLoadingFallback || draft === null ? (
            <p className="text-xs text-muted-foreground">Loading…</p>
          ) : (
            <>
              <ReorderableChecklistList rows={rows} onChange={setDraft} />
              <div className="flex items-center gap-2 pt-1">
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
                  className="h-8 px-2.5 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground border border-dashed border-border rounded-lg transition-colors cursor-pointer"
                >
                  <Plus size={12} /> Add item
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setError("")
                    save.mutate()
                  }}
                  disabled={save.isPending}
                  className="h-8 px-3.5 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:opacity-90 disabled:opacity-40 transition-colors cursor-pointer"
                >
                  {save.isPending ? "Saving…" : "Save checklist"}
                </button>
              </div>
              {error && <p className="text-xs text-red-500">{error}</p>}
            </>
          )}
        </div>
      )}
    </div>
  )
}

interface RoleDraft {
  role_id: string
  slots: number
  amount_aed: string
  notes: string
  responsibilities_override: string
  existing: boolean
}

/** Cohort rates & openings section */
function CohortRolesRatesSection({
  cohort,
  roles,
  openings,
  sessionId: _sessionId,
}: {
  cohort: Cohort
  roles: DeliveryRole[]
  openings: any[]
  sessionId?: string
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [error, setError] = useState("")
  const [draft, setDraft] = useState<RoleDraft[] | null>(null)

  const toDraft = () =>
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
    if (roles.length > 0) setDraft(toDraft())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roles, openings])

  const saveMutation = useMutation({
    mutationFn: () =>
      setCohortOpeningsApi({
        cohortId: cohort.id,
        openings: (draft ?? [])
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
      toast.success("Role rates & slots saved")
      setError("")
      qc.invalidateQueries({ queryKey: ["cohort-openings-defaults", cohort.id] })
    },
    onError: (e: any) => setError(getErrorMessage(e, "Could not save roles")),
  })

  const rows = draft ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-foreground">Role Rates & Staffing Slots</p>
          <p className="text-xs text-muted-foreground">
            Per-session pay rates and slot counts for this cohort.
          </p>
        </div>
        <button
          type="button"
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="h-8 px-4 bg-primary text-primary-foreground text-xs font-semibold rounded-lg hover:opacity-90 disabled:opacity-40 transition-colors shadow-sm cursor-pointer"
        >
          {saveMutation.isPending ? "Saving…" : "Save rates"}
        </button>
      </div>

      {error && <p className="text-xs text-red-500 bg-red-500/10 p-2 rounded-lg">{error}</p>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {rows.map((d, i) => {
          const role = roles.find((r) => r.id === d.role_id)
          if (!role) return null

          return (
            <div key={d.role_id} className="border border-border rounded-xl p-3 bg-card flex flex-col gap-2.5">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-foreground">{role.name}</span>
                <span className="text-xs text-muted-foreground">
                  Default: {role.default_rate_aed != null ? `${role.default_rate_aed} AED` : "None"}
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
                      setDraft(
                        rows.map((x, j) => (j === i ? { ...x, amount_aed: e.target.value } : x)),
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
                      setDraft(
                        rows.map((x, j) =>
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
                    setDraft(
                      rows.map((x, j) =>
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
  )
}

/** Main CohortRolesPanel export */
export function CohortRolesPanel({
  cohort,
  sessionId,
  sessions,
  large: _large = false,
}: {
  cohort: Cohort
  sessionId?: string
  sessions?: Session[]
  large?: boolean
}) {
  const [activeTab, setActiveTab] = useState<"checklists" | "rates">("checklists")

  const { data: roles = [], isLoading: rolesLoading } = useQuery({
    queryKey: ["delivery-roles"],
    queryFn: () => getDeliveryRolesApi(),
  })

  const { data: openings = [], isLoading: openingsLoading } = useQuery({
    queryKey: ["cohort-openings-defaults", cohort.id],
    queryFn: () => getCohortOpeningsApi(cohort.id),
  })

  const { data: fetchedSessions = [], isLoading: sessionsLoading } = useQuery({
    queryKey: ["sessions-sessions", cohort.id],
    queryFn: () => getSessionsApi(cohort.id),
    enabled: !sessions && !sessionId,
  })

  const allSessions = sessions ?? fetchedSessions

  if (rolesLoading || openingsLoading || (sessionsLoading && !sessions)) {
    return <p className="text-xs text-muted-foreground py-2">Loading cohort checklists & roles…</p>
  }

  return (
    <div className="flex flex-col gap-4 py-1">
      {/* Sub-navigation tabs: Checklists (default) vs Rates & Slots */}
      <div className="flex items-center gap-1.5 border-b border-border pb-2.5">
        <button
          type="button"
          onClick={() => setActiveTab("checklists")}
          className={cn(
            "h-8 px-3.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer",
            activeTab === "checklists"
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground hover:bg-muted",
          )}
        >
          Delivery Checklists
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
          Role Rates & Slots
        </button>
      </div>

      {activeTab === "checklists" ? (
        <CohortDayChecklistManager
          cohort={cohort}
          sessions={allSessions}
          roles={roles}
          initialSessionId={sessionId}
        />
      ) : (
        <CohortRolesRatesSection
          cohort={cohort}
          roles={roles}
          openings={openings}
          sessionId={sessionId}
        />
      )}
    </div>
  )
}
