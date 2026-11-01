import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  Camera,
  Check,
  Copy,
  Layers,
  ListChecks,
  Loader2,
  Paperclip,
  Plus,
  Search,
} from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useToast } from "@/components/ui/toast"
import { getProgramsApi } from "@/api/sessions/programs"
import { getCohortsApi, getSessionsApi } from "@/api/sessions/cohorts"
import {
  listChecklistItemsApi,
  importChecklistItemsApi,
  type ChecklistScope,
} from "@/api/sessions/day"
import type { ChecklistItem, Cohort, Program, Session } from "@/types/sessions"
import type { DeliveryRole } from "@/api/sessions/openings"
import { getErrorMessage } from "@/lib/utils"

interface SourceSelection {
  scope: ChecklistScope
  ownerId: string
  label: string
  subLabel?: string
  cohortId?: string
}

export function ImportInstructorChecklistModal({
  open,
  onClose,
  targetScope,
  targetOwnerId,
  targetProgramId,
  targetCohortId,
  targetRoleId,
  targetAudience = "instructor",
  roles = [],
  onImportSuccess,
}: {
  open: boolean
  onClose: () => void
  targetScope: ChecklistScope
  targetOwnerId: string
  targetProgramId?: string
  targetCohortId?: string
  targetRoleId?: string | null
  targetAudience?: "instructor" | "internal"
  roles?: DeliveryRole[]
  onImportSuccess?: (items: ChecklistItem[], replace: boolean) => void
}) {
  const toast = useToast()
  const queryClient = useQueryClient()

  // ── Programs Query ────────────────────────────────────────────────────────
  const { data: programs = [], isLoading: loadingPrograms } = useQuery<Program[]>({
    queryKey: ["sessions-programs"],
    queryFn: getProgramsApi,
    enabled: open,
  })

  const [selectedProgramId, setSelectedProgramId] = useState<string>(targetProgramId || "")
  const [source, setSource] = useState<SourceSelection | null>(null)
  const [selectedCohortSessionId, setSelectedCohortSessionId] = useState<string>("default")
  const [sourceRoleId, setSourceRoleId] = useState<string | null>(targetRoleId || null)
  const [selectedItemIds, setSelectedItemIds] = useState<Set<string>>(new Set())
  const [replaceExisting, setReplaceExisting] = useState<boolean>(false)
  const [searchItemFilter, setSearchItemFilter] = useState<string>("")

  // Default to targetProgramId or first program if not set, and reset state on open
  useEffect(() => {
    if (open) {
      if (targetProgramId) {
        setSelectedProgramId(targetProgramId)
      } else if (programs.length > 0 && !selectedProgramId) {
        setSelectedProgramId(programs[0].id)
      }
      setSource(null)
      setSelectedCohortSessionId("default")
      setSourceRoleId(targetRoleId || null)
      setSelectedItemIds(new Set())
      setReplaceExisting(false)
      setSearchItemFilter("")
    }
  }, [open, targetProgramId, targetRoleId])

  // ── Program Cohorts Query ──────────────────────────────────────────────────
  const { data: cohorts = [], isLoading: loadingCohorts } = useQuery<Cohort[]>({
    queryKey: ["sessions-cohorts-for-prog", selectedProgramId],
    queryFn: () => getCohortsApi(selectedProgramId),
    enabled: open && !!selectedProgramId,
  })

  // When program changes, reset source and selection
  const handleProgramChange = (progId: string) => {
    setSelectedProgramId(progId)
    setSource(null)
    setSelectedCohortSessionId("default")
    setSelectedItemIds(new Set())
  }

  // ── Sessions Query for selected source cohort ──────────────────────────────
  const selectedCohortId = source?.cohortId || (source?.scope === "cohorts" ? source.ownerId : null)
  const { data: sourceCohortSessions = [] } = useQuery<Session[]>({
    queryKey: ["sessions-for-cohort-import", selectedCohortId],
    queryFn: () => getSessionsApi(selectedCohortId!),
    enabled: open && !!selectedCohortId,
  })

  const sortedSessions = useMemo(() => {
    return [...sourceCohortSessions].sort((a, b) => {
      const d = a.meeting_date.localeCompare(b.meeting_date)
      return d !== 0 ? d : (a.starts_at || "").localeCompare(b.starts_at || "")
    })
  }, [sourceCohortSessions])

  // Effective source scope and owner id
  const effectiveSource = useMemo<{ scope: ChecklistScope; ownerId: string } | null>(() => {
    if (!source) return null
    if (source.scope === "programs") {
      return { scope: "programs", ownerId: source.ownerId }
    }
    if (source.cohortId) {
      if (selectedCohortSessionId === "default") {
        return { scope: "cohorts", ownerId: source.cohortId }
      }
      return { scope: "sessions", ownerId: selectedCohortSessionId }
    }
    return { scope: source.scope, ownerId: source.ownerId }
  }, [source, selectedCohortSessionId])

  // ── Source Items Query ─────────────────────────────────────────────────────
  const { data: sourceItems = [], isLoading: loadingItems } = useQuery<ChecklistItem[]>({
    queryKey: [
      "checklist-items-for-import",
      effectiveSource?.scope,
      effectiveSource?.ownerId,
      sourceRoleId,
      targetAudience,
    ],
    queryFn: async () => {
      if (!effectiveSource) return []
      try {
        const items = await listChecklistItemsApi(
          effectiveSource.scope,
          effectiveSource.ownerId,
          sourceRoleId,
          targetAudience
        )
        if (items.length > 0) return items

        // If cohort has no items saved, try falling back to program checklist
        if (effectiveSource.scope === "cohorts" && selectedProgramId) {
          const progItems = await listChecklistItemsApi(
            "programs",
            selectedProgramId,
            sourceRoleId,
            targetAudience
          )
          if (progItems.length > 0) return progItems
        }
        // If session has no items saved, try falling back to cohort default
        if (effectiveSource.scope === "sessions" && selectedCohortId) {
          const cohortItems = await listChecklistItemsApi(
            "cohorts",
            selectedCohortId,
            sourceRoleId,
            targetAudience
          )
          if (cohortItems.length > 0) return cohortItems
          if (selectedProgramId) {
            return await listChecklistItemsApi(
              "programs",
              selectedProgramId,
              sourceRoleId,
              targetAudience
            )
          }
        }
        return []
      } catch {
        return []
      }
    },
    enabled: open && !!effectiveSource,
  })

  // Automatically select all items when source items load
  useEffect(() => {
    if (sourceItems.length > 0) {
      setSelectedItemIds(new Set(sourceItems.map((i) => i.id)))
    } else {
      setSelectedItemIds(new Set())
    }
  }, [sourceItems])

  // Toggle single item selection
  const toggleItem = (id: string) => {
    setSelectedItemIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // Select all / Deselect all
  const selectAll = () => {
    setSelectedItemIds(new Set(sourceItems.map((i) => i.id)))
  }

  const deselectAll = () => {
    setSelectedItemIds(new Set())
  }

  // Filtered source items based on search input
  const filteredItems = useMemo(() => {
    if (!searchItemFilter.trim()) return sourceItems
    const q = searchItemFilter.toLowerCase()
    return sourceItems.filter(
      (item) =>
        item.title.toLowerCase().includes(q) ||
        (item.description && item.description.toLowerCase().includes(q))
    )
  }, [sourceItems, searchItemFilter])

  // ── Import Mutation ────────────────────────────────────────────────────────
  const importMutation = useMutation({
    mutationFn: () => {
      if (!effectiveSource || selectedItemIds.size === 0) {
        throw new Error("Please select at least one checklist item to import.")
      }
      return importChecklistItemsApi(targetScope, targetOwnerId, {
        source_scope: effectiveSource.scope,
        source_owner_id: effectiveSource.ownerId,
        source_role_id: sourceRoleId,
        source_target_audience: targetAudience,
        item_ids: Array.from(selectedItemIds),
        replace_existing: replaceExisting,
        role_id: targetRoleId,
        target_audience: targetAudience,
      })
    },
    onSuccess: (importedItems) => {
      toast.success(
        replaceExisting
          ? `Checklist replaced with ${selectedItemIds.size} imported items!`
          : `Successfully imported ${selectedItemIds.size} checklist items!`
      )
      void queryClient.invalidateQueries({
        queryKey: ["checklist-items", targetScope, targetOwnerId],
      })
      void queryClient.invalidateQueries({ queryKey: ["checklist-items"] })
      onImportSuccess?.(importedItems, replaceExisting)
      onClose()
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, "Failed to import checklist items"))
    },
  })

  const currentProgram = programs.find((p) => p.id === selectedProgramId)

  return (
    <Dialog open={open} onOpenChange={(val) => !val && onClose()}>
      <DialogContent className="w-full max-w-[calc(100%-1rem)] sm:max-w-3xl max-h-[92vh] flex flex-col p-0 overflow-hidden bg-background text-foreground border border-border">
        {/* Modal Header */}
        <div className="p-4 sm:p-5 pr-12 border-b border-border bg-card">
          <DialogHeader>
            <div className="flex items-center gap-2 text-primary text-xs font-semibold uppercase tracking-wider">
              <Copy className="w-3.5 h-3.5" />
              <span>Clone & Import Instructor Checklist</span>
            </div>
            <DialogTitle className="text-base sm:text-lg font-bold">
              Import Instructor Checklist Items
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Select a program, pick its default delivery checklist or one of its cohorts, then
              multiselect the checklist items you want to carry over to this active instructor checklist.
            </DialogDescription>
          </DialogHeader>
        </div>

        {/* Modal Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-5">
          {/* ── 1. Select Program ────────────────────────────────────────── */}
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center justify-between">
              <span>1. Select Program</span>
              {currentProgram && (
                <span className="text-[11px] font-normal normal-case text-muted-foreground">
                  {cohorts.length} cohort{cohorts.length === 1 ? "" : "s"} available
                </span>
              )}
            </label>
            <select
              value={selectedProgramId}
              onChange={(e) => handleProgramChange(e.target.value)}
              disabled={loadingPrograms}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm font-medium focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              {programs.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} {p.is_competition ? "(Competition)" : ""}
                </option>
              ))}
            </select>
          </div>

          {/* ── 2. Select Source (Program Template or Cohort) ─────────────── */}
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground block">
              2. Choose Source (Program Template or Cohort)
            </label>

            {loadingCohorts ? (
              <div className="flex items-center justify-center p-6 border border-border rounded-xl bg-card">
                <Loader2 className="w-5 h-5 text-primary animate-spin mr-2" />
                <span className="text-xs text-muted-foreground">Loading templates & cohorts…</span>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-h-48 sm:max-h-56 overflow-y-auto pr-1">
                {/* Option A: Program's Default Template */}
                <button
                  type="button"
                  onClick={() => {
                    if (selectedProgramId) {
                      setSource({
                        scope: "programs",
                        ownerId: selectedProgramId,
                        label: `${currentProgram?.name ?? "Program"} Default Checklist`,
                        subLabel: "Program delivery checklist template",
                      })
                      setSelectedCohortSessionId("default")
                    }
                  }}
                  className={`flex items-start gap-3 p-3 rounded-xl border text-left transition-all cursor-pointer ${
                    source?.scope === "programs" && source.ownerId === selectedProgramId
                      ? "border-primary bg-primary/5 ring-1 ring-primary"
                      : "border-border bg-card hover:border-primary/50 hover:bg-muted/30"
                  }`}
                >
                  <div
                    className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                      source?.scope === "programs" && source.ownerId === selectedProgramId
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    <ListChecks className="w-4 h-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-semibold text-foreground truncate">
                        Program Default
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-primary/10 text-primary">
                        Template
                      </span>
                    </div>
                    <span className="text-[11px] text-muted-foreground block truncate mt-0.5">
                      Program delivery checklist template
                    </span>
                  </div>
                </button>

                {/* Option B: Cohorts of this Program */}
                {cohorts.map((c) => {
                  const isCurrentCohort =
                    targetCohortId === c.id ||
                    (targetScope === "cohorts" && targetOwnerId === c.id)
                  const isSelected = source?.cohortId === c.id || source?.ownerId === c.id

                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => {
                        setSource({
                          scope: "cohorts",
                          ownerId: c.id,
                          cohortId: c.id,
                          label: c.name,
                          subLabel: c.starts_on ? `Starts: ${c.starts_on}` : "Cohort delivery checklist",
                        })
                        setSelectedCohortSessionId("default")
                      }}
                      className={`flex items-start gap-3 p-3 rounded-xl border text-left transition-all cursor-pointer ${
                        isSelected
                          ? "border-primary bg-primary/5 ring-1 ring-primary"
                          : "border-border bg-card hover:border-primary/50 hover:bg-muted/30"
                      }`}
                    >
                      <div
                        className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                          isSelected
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted text-muted-foreground"
                        }`}
                      >
                        <Layers className="w-4 h-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-semibold text-foreground truncate">
                            {c.name}
                          </span>
                          {isCurrentCohort ? (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400">
                              Active Cohort
                            </span>
                          ) : (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-muted text-muted-foreground uppercase">
                              {c.status || "Cohort"}
                            </span>
                          )}
                        </div>
                        <span className="text-[11px] text-muted-foreground block truncate mt-0.5">
                          {c.starts_on ? `Starts: ${c.starts_on}` : "Cohort delivery checklist"}
                        </span>
                      </div>
                    </button>
                  )
                })}
              </div>
            )}

            {/* Optional Sub-selector for Cohort Sessions / Days */}
            {source && source.cohortId && sortedSessions.length > 0 && (
              <div className="mt-3 p-3 border border-border rounded-xl bg-card space-y-2">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground block">
                  Select Day from {source.label}:
                </span>
                <div className="flex flex-wrap gap-1.5">
                  <button
                    type="button"
                    onClick={() => setSelectedCohortSessionId("default")}
                    className={`h-7 px-3 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                      selectedCohortSessionId === "default"
                        ? "bg-primary text-primary-foreground font-semibold"
                        : "border border-border bg-background text-foreground hover:bg-muted"
                    }`}
                  >
                    Pre-Workshop / Default
                  </button>
                  {sortedSessions.map((s, idx) => {
                    const isSelectedSession = selectedCohortSessionId === s.id
                    return (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => setSelectedCohortSessionId(s.id)}
                        className={`h-7 px-3 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                          isSelectedSession
                            ? "bg-primary text-primary-foreground font-semibold"
                            : "border border-border bg-background text-foreground hover:bg-muted"
                        }`}
                      >
                        Day {idx + 1}
                        {s.title ? `: ${s.title}` : ""}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Optional Role Filter for Source if Roles Available */}
            {source && roles.length > 0 && (
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <span className="text-xs text-muted-foreground shrink-0">Source Role:</span>
                <select
                  value={sourceRoleId || ""}
                  onChange={(e) => setSourceRoleId(e.target.value ? e.target.value : null)}
                  className="h-8 px-2.5 max-w-full border border-border bg-card text-foreground rounded-lg text-xs focus:outline-none focus:border-primary transition-colors cursor-pointer"
                >
                  <option value="">General / All Roles</option>
                  {roles.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* ── 3. Multiselect Items from Source ─────────────────────────── */}
          {source && (
            <div className="space-y-3 pt-2 border-t border-border">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground block">
                    3. Select Checklist Items to Carry Over
                  </label>
                  <span className="text-xs text-muted-foreground">
                    From source: <strong className="text-foreground">{source.label}</strong>
                    {selectedCohortSessionId !== "default"
                      ? ` (${
                          sortedSessions.find((s) => s.id === selectedCohortSessionId)?.title
                            ? `Day: ${
                                sortedSessions.find((s) => s.id === selectedCohortSessionId)?.title
                              }`
                            : "Selected Day"
                        })`
                      : ""}{" "}
                    ({sourceItems.length} total item{sourceItems.length === 1 ? "" : "s"})
                  </span>
                </div>

                {sourceItems.length > 0 && (
                  <div className="flex items-center gap-2 self-start sm:self-auto">
                    <button
                      type="button"
                      onClick={selectAll}
                      className="text-xs font-medium text-primary hover:underline px-1 py-0.5 cursor-pointer"
                    >
                      Select All
                    </button>
                    <span className="text-muted-foreground">•</span>
                    <button
                      type="button"
                      onClick={deselectAll}
                      className="text-xs font-medium text-muted-foreground hover:text-foreground px-1 py-0.5 cursor-pointer"
                    >
                      Deselect All
                    </button>
                  </div>
                )}
              </div>

              {loadingItems ? (
                <div className="flex items-center justify-center p-8 border border-border rounded-xl bg-card">
                  <Loader2 className="w-5 h-5 text-primary animate-spin mr-2" />
                  <span className="text-xs text-muted-foreground">Loading checklist items…</span>
                </div>
              ) : sourceItems.length === 0 ? (
                <div className="text-center p-8 border border-dashed border-border rounded-xl bg-muted/20 text-muted-foreground text-xs">
                  This source doesn't have any checklist items to import.
                </div>
              ) : (
                <>
                  {/* Search box for filtering items if there are many */}
                  {sourceItems.length > 4 && (
                    <div className="relative">
                      <Search className="w-3.5 h-3.5 absolute left-3 top-3 text-muted-foreground" />
                      <input
                        type="text"
                        placeholder="Search items by title or description…"
                        value={searchItemFilter}
                        onChange={(e) => setSearchItemFilter(e.target.value)}
                        className="w-full h-9 pl-9 pr-3 border border-border bg-card text-foreground rounded-lg text-xs focus:outline-none focus:border-primary transition-colors"
                      />
                    </div>
                  )}

                  {/* Items list with checkboxes */}
                  <div className="max-h-52 sm:max-h-64 overflow-y-auto space-y-1.5 p-1 border border-border rounded-xl bg-card/50">
                    {filteredItems.length === 0 ? (
                      <div className="text-center p-4 text-xs text-muted-foreground">
                        No items match "{searchItemFilter}"
                      </div>
                    ) : (
                      filteredItems.map((item, index) => {
                        const isChecked = selectedItemIds.has(item.id)
                        const hasAttachments = (item.attachments?.length || 0) > 0
                        const hasSubs = (item.sub_items?.length || 0) > 0

                        return (
                          <div
                            key={item.id}
                            onClick={() => toggleItem(item.id)}
                            className={`flex items-start gap-2.5 sm:gap-3 p-2.5 rounded-lg border transition-all cursor-pointer ${
                              isChecked
                                ? "border-primary/40 bg-primary/5"
                                : "border-border/60 hover:bg-muted/40 hover:border-border"
                            }`}
                          >
                            <button
                              type="button"
                              className={`mt-0.5 w-4 h-4 rounded flex items-center justify-center transition-colors shrink-0 ${
                                isChecked
                                  ? "bg-primary text-primary-foreground"
                                  : "border border-border bg-background"
                              }`}
                            >
                              {isChecked && <Check className="w-3 h-3 stroke-[3]" />}
                            </button>

                            <div className="w-5 text-center text-xs font-semibold tabular-nums text-muted-foreground shrink-0 mt-0.5">
                              {index + 1}
                            </div>

                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-1.5">
                                <span className="text-xs font-semibold text-foreground break-words">
                                  {item.title}
                                </span>
                                {item.is_required ? (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                                    Required
                                  </span>
                                ) : (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-muted text-muted-foreground">
                                    Optional
                                  </span>
                                )}
                                {item.requires_proof && (
                                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400">
                                    <Camera className="w-3 h-3" /> Photo Proof
                                  </span>
                                )}
                                {hasAttachments && item.attachments && (
                                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-500/10 text-blue-600 dark:text-blue-400">
                                    <Paperclip className="w-3 h-3" /> {item.attachments.length} attachment
                                    {item.attachments.length === 1 ? "" : "s"}
                                  </span>
                                )}
                                {hasSubs && item.sub_items && (
                                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                                    <ListChecks className="w-3 h-3" /> {item.sub_items.length} sub-topic
                                    {item.sub_items.length === 1 ? "" : "s"}
                                  </span>
                                )}
                              </div>
                              {item.description && (
                                <p className="text-[11px] text-muted-foreground line-clamp-2 mt-0.5 break-words">
                                  {item.description}
                                </p>
                              )}
                              {hasSubs && item.sub_items && (
                                <div className="mt-1 flex flex-wrap gap-1">
                                  {item.sub_items.map((sub, sIdx) => (
                                    <span
                                      key={sub.id || sIdx}
                                      className="text-[10px] text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded"
                                    >
                                      ↳ {sub.title}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        )
                      })
                    )}
                  </div>

                  {/* Mode Selector: Append vs Replace */}
                  <div className="pt-2">
                    <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground block mb-1.5">
                      Import Mode
                    </label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      <label
                        className={`flex items-start gap-2.5 p-3 rounded-xl border cursor-pointer transition-colors ${
                          !replaceExisting
                            ? "border-primary bg-primary/5 ring-1 ring-primary"
                            : "border-border bg-card hover:bg-muted/20"
                        }`}
                      >
                        <input
                          type="radio"
                          name="import-mode-instructor"
                          checked={!replaceExisting}
                          onChange={() => setReplaceExisting(false)}
                          className="mt-0.5 text-primary focus:ring-primary"
                        />
                        <div>
                          <span className="text-xs font-semibold text-foreground block">
                            Append to Checklist
                          </span>
                          <span className="text-[11px] text-muted-foreground block">
                            Keeps existing checklist items and adds the selected items to the end.
                          </span>
                        </div>
                      </label>

                      <label
                        className={`flex items-start gap-2.5 p-3 rounded-xl border cursor-pointer transition-colors ${
                          replaceExisting
                            ? "border-destructive bg-destructive/5 ring-1 ring-destructive"
                            : "border-border bg-card hover:bg-muted/20"
                        }`}
                      >
                        <input
                          type="radio"
                          name="import-mode-instructor"
                          checked={replaceExisting}
                          onChange={() => setReplaceExisting(true)}
                          className="mt-0.5 text-destructive focus:ring-destructive"
                        />
                        <div>
                          <span className="text-xs font-semibold text-destructive block">
                            Replace Checklist
                          </span>
                          <span className="text-[11px] text-muted-foreground block">
                            Replaces all current items in this checklist with the selected items.
                          </span>
                        </div>
                      </label>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="p-3.5 sm:p-4 border-t border-border bg-muted/20 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground self-start sm:self-auto">
            {replaceExisting ? (
              <span className="text-destructive font-medium flex items-center gap-1 text-[11px] sm:text-xs break-words">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                Warning: Will overwrite existing items in active checklist
              </span>
            ) : source ? (
              <span>
                <strong>{selectedItemIds.size}</strong> of {sourceItems.length} item
                {sourceItems.length === 1 ? "" : "s"} selected
              </span>
            ) : (
              <span>Pick a source to view items</span>
            )}
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <button
              type="button"
              onClick={onClose}
              disabled={importMutation.isPending}
              className="flex-1 sm:flex-none h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition-colors cursor-pointer text-center"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => importMutation.mutate()}
              disabled={!source || selectedItemIds.size === 0 || importMutation.isPending}
              className={`flex-1 sm:flex-none h-9 px-4 rounded-xl text-xs font-semibold transition-all inline-flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
                replaceExisting
                  ? "bg-destructive text-destructive-foreground hover:opacity-90"
                  : "bg-primary text-primary-foreground hover:opacity-90"
              }`}
            >
              {importMutation.isPending ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Importing…
                </>
              ) : replaceExisting ? (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  Replace Checklist ({selectedItemIds.size})
                </>
              ) : (
                <>
                  <Plus className="w-3.5 h-3.5" />
                  Import {selectedItemIds.size} Item{selectedItemIds.size === 1 ? "" : "s"}
                </>
              )}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
