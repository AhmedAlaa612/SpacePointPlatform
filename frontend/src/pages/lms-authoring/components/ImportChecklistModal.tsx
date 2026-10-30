import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  BookOpen,
  Calendar,
  Check,
  ClipboardCheck,
  Copy,
  FileText,
  Flag,
  Gamepad2,
  HelpCircle,
  Layers,
  Link2,
  ListChecks,
  Loader2,
  Lock,
  Plus,
  Rocket,
  Search,
  Upload,
  Users,
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
import { getCohortsApi } from "@/api/sessions/cohorts"
import {
  getLmsProgramApi,
  getCohortProgramOverrideApi,
  listLmsProgramsApi,
  importCohortOverrideItemsApi,
  type LmsProgramItem,
  type LmsProgramItemType,
} from "@/api/lms_admin"
import { errorDetail } from "./LmsChecklistShared"
import type { Cohort, Program } from "@/types/sessions"

const TYPE_ICONS: Record<LmsProgramItemType, typeof BookOpen> = {
  course: BookOpen,
  mission_run: Rocket,
  arcade_game: Gamepad2,
  external_link: Link2,
  submission: Upload,
  pdf: FileText,
  manual: ClipboardCheck,
  session: Calendar,
  quiz: HelpCircle,
  team_setup: Users,
  checkpoint: Flag,
}

const TYPE_LABELS: Record<LmsProgramItemType, string> = {
  course: "Course",
  mission_run: "Mission Run",
  arcade_game: "Arcade Game",
  external_link: "Link",
  submission: "Submission",
  pdf: "PDF",
  manual: "Manual Check",
  session: "Session",
  quiz: "Quiz",
  team_setup: "Team Setup",
  checkpoint: "Checkpoint",
}

interface SourceSelection {
  type: "program" | "cohort"
  id: string
  label: string
}

export function ImportChecklistModal({
  open,
  onClose,
  targetCohortId,
  targetProgramId,
  onSuccess,
}: {
  open: boolean
  onClose: () => void
  targetCohortId: string
  targetProgramId?: string
  onSuccess?: () => void
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
      setSelectedItemIds(new Set())
      setReplaceExisting(false)
      setSearchItemFilter("")
    }
  }, [open, targetProgramId])

  // ── Program LMS Template Query ─────────────────────────────────────────────
  const { data: lmsPrograms = [], isLoading: loadingLmsTemplate } = useQuery({
    queryKey: ["lms-programs-for-prog", selectedProgramId],
    queryFn: () => listLmsProgramsApi(selectedProgramId),
    enabled: open && !!selectedProgramId,
  })
  const defaultTemplate = lmsPrograms[0] || null

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
    setSelectedItemIds(new Set())
  }

  // ── Source Items Queries ───────────────────────────────────────────────────
  const isProgramSource = source?.type === "program"
  const isCohortSource = source?.type === "cohort"

  const { data: templateData, isLoading: loadingTemplateItems } = useQuery({
    queryKey: ["lms-program-detail", source?.id],
    queryFn: () => getLmsProgramApi(source!.id),
    enabled: open && isProgramSource && !!source?.id,
  })

  const { data: cohortOverride, isLoading: loadingCohortItems } = useQuery({
    queryKey: ["lms-cohort-override-preview", source?.id],
    queryFn: () => getCohortProgramOverrideApi(source!.id),
    enabled: open && isCohortSource && !!source?.id,
  })

  const sourceItems: LmsProgramItem[] = useMemo(() => {
    if (isProgramSource) return templateData?.items || []
    if (isCohortSource) return cohortOverride?.items || []
    return []
  }, [isProgramSource, isCohortSource, templateData, cohortOverride])

  const isLoadingItems = (isProgramSource && loadingTemplateItems) || (isCohortSource && loadingCohortItems)

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
        (item.description && item.description.toLowerCase().includes(q)) ||
        item.item_type.toLowerCase().includes(q)
    )
  }, [sourceItems, searchItemFilter])

  // ── Import Mutation ────────────────────────────────────────────────────────
  const importMutation = useMutation({
    mutationFn: () => {
      if (!source || selectedItemIds.size === 0) {
        throw new Error("Please select at least one checklist item to import.")
      }
      return importCohortOverrideItemsApi(targetCohortId, {
        source_type: source.type,
        source_id: source.id,
        item_ids: Array.from(selectedItemIds),
        replace_existing: replaceExisting,
      })
    },
    onSuccess: () => {
      toast.success(
        replaceExisting
          ? `Checklist replaced with ${selectedItemIds.size} imported items!`
          : `Successfully imported ${selectedItemIds.size} checklist items!`
      )
      void queryClient.invalidateQueries({ queryKey: ["lms-cohort-override", targetCohortId] })
      onSuccess?.()
      onClose()
    },
    onError: (err: unknown) => {
      toast.error(errorDetail(err, "Failed to import checklist items"))
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
              <span>Clone & Import Checklist</span>
            </div>
            <DialogTitle className="text-base sm:text-lg font-bold">Import Checklist Items</DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Select a program, pick its default template or one of its cohorts, then multiselect
              the checklist items you want to carry over to this active cohort.
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

          {/* ── 2. Select Source (Default Template or Cohort) ─────────────── */}
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground block">
              2. Choose Source (Default Template or Cohort)
            </label>

            {loadingLmsTemplate || loadingCohorts ? (
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
                    if (defaultTemplate) {
                      setSource({
                        type: "program",
                        id: defaultTemplate.id,
                        label: `${currentProgram?.name ?? "Program"} Default Template`,
                      })
                    }
                  }}
                  disabled={!defaultTemplate}
                  className={`flex items-start gap-3 p-3 rounded-xl border text-left transition-all cursor-pointer ${
                    !defaultTemplate
                      ? "opacity-50 border-dashed border-border bg-muted/20 cursor-not-allowed"
                      : source?.type === "program" && source.id === defaultTemplate.id
                      ? "border-primary bg-primary/5 ring-1 ring-primary"
                      : "border-border bg-card hover:border-primary/50 hover:bg-muted/30"
                  }`}
                >
                  <div
                    className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                      source?.type === "program" && source.id === defaultTemplate?.id
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    <ListChecks className="w-4 h-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-semibold text-foreground truncate">
                        Default Template
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-primary/10 text-primary">
                        Template
                      </span>
                    </div>
                    <span className="text-[11px] text-muted-foreground block truncate mt-0.5">
                      {defaultTemplate
                        ? "Inherited program baseline checklist"
                        : "No template configured for this program"}
                    </span>
                  </div>
                </button>

                {/* Option B: Cohorts of this Program */}
                {cohorts.map((c) => {
                  const isCurrent = c.id === targetCohortId
                  const isSelected = source?.type === "cohort" && source.id === c.id

                  return (
                    <button
                      key={c.id}
                      type="button"
                      disabled={isCurrent}
                      onClick={() => {
                        setSource({
                          type: "cohort",
                          id: c.id,
                          label: c.name,
                        })
                      }}
                      className={`flex items-start gap-3 p-3 rounded-xl border text-left transition-all ${
                        isCurrent
                          ? "opacity-40 border-dashed border-border bg-muted/10 cursor-not-allowed"
                          : isSelected
                          ? "border-primary bg-primary/5 ring-1 ring-primary cursor-pointer"
                          : "border-border bg-card hover:border-primary/50 hover:bg-muted/30 cursor-pointer"
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
                          {isCurrent ? (
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
                          {isCurrent
                            ? "Current target cohort (cannot import into itself)"
                            : c.starts_on
                            ? `Starts: ${c.starts_on}`
                            : "Cohort checklist items"}
                        </span>
                      </div>
                    </button>
                  )
                })}
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
                    From source: <strong className="text-foreground">{source.label}</strong> (
                    {sourceItems.length} total item{sourceItems.length === 1 ? "" : "s"})
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

              {isLoadingItems ? (
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
                  {sourceItems.length > 5 && (
                    <div className="relative">
                      <Search className="w-3.5 h-3.5 absolute left-3 top-3 text-muted-foreground" />
                      <input
                        type="text"
                        placeholder="Search items by title or type…"
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
                        const Icon = TYPE_ICONS[item.item_type] || BookOpen
                        const typeLabel = TYPE_LABELS[item.item_type] || item.item_type

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
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-muted text-muted-foreground">
                                  <Icon className="w-3 h-3" />
                                  {typeLabel}
                                </span>
                                {item.scope === "team" && (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-500/10 text-blue-600 dark:text-blue-400">
                                    Team
                                  </span>
                                )}
                                {item.gated && (
                                  <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400">
                                    <Lock className="w-2.5 h-2.5" /> Gated
                                  </span>
                                )}
                                {item.optional && (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-muted text-muted-foreground">
                                    Optional
                                  </span>
                                )}
                              </div>
                              {item.description && (
                                <p className="text-[11px] text-muted-foreground line-clamp-2 mt-0.5 break-words">
                                  {item.description}
                                </p>
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
                          name="import-mode"
                          checked={!replaceExisting}
                          onChange={() => setReplaceExisting(false)}
                          className="mt-0.5 text-primary focus:ring-primary"
                        />
                        <div>
                          <span className="text-xs font-semibold text-foreground block">
                            Append to Checklist
                          </span>
                          <span className="text-[11px] text-muted-foreground block">
                            Keeps existing cohort items and adds the selected items to the end.
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
                          name="import-mode"
                          checked={replaceExisting}
                          onChange={() => setReplaceExisting(true)}
                          className="mt-0.5 text-destructive focus:ring-destructive"
                        />
                        <div>
                          <span className="text-xs font-semibold text-destructive block">
                            Replace Checklist
                          </span>
                          <span className="text-[11px] text-muted-foreground block">
                            Replaces all current items in this cohort with the selected items.
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
                Warning: Will overwrite existing items in active cohort
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
