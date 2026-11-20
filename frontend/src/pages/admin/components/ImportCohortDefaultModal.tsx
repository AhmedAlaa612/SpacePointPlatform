import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, ArrowRight, Download, Layers, ListChecks, Loader2 } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useToast } from "@/components/ui/toast"
import { getProgramsApi, getProgramTemplateApi, type ProgramTemplate } from "@/api/sessions/programs"
import { getCohortsApi, getSessionsApi } from "@/api/sessions/cohorts"
import {
  importCohortDefaultsApi,
  type CohortChecklistsSummary,
  type SessionChecklistSummary,
} from "@/api/sessions/day"
import type { Cohort, Program, Session } from "@/types/sessions"
import { cn, getErrorMessage } from "@/lib/utils"

const EMPTY_PROGRAMS: Program[] = []
const EMPTY_COHORTS: Cohort[] = []
const EMPTY_SESSIONS: Session[] = []

function compareSessionsChronologically(a: Session, b: Session) {
  const d = a.meeting_date.localeCompare(b.meeting_date)
  if (d !== 0) return d
  const s = (a.starts_at || "").localeCompare(b.starts_at || "")
  if (s !== 0) return s
  return (a.created_at || "").localeCompare(b.created_at || "")
}

function formatShortDate(iso: string) {
  const d = new Date(iso + "T00:00:00")
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric" })
}

export function ImportCohortDefaultModal({
  open,
  onClose,
  cohort,
  sessions,
  summary,
  isOrgScope = false,
  onSuccess,
}: {
  open: boolean
  onClose: () => void
  cohort: Cohort
  sessions: Session[]
  summary?: CohortChecklistsSummary
  isOrgScope?: boolean
  onSuccess: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={(val) => !val && onClose()}>
      <DialogContent className="w-full max-w-[calc(100%-1rem)] sm:max-w-2xl max-h-[92vh] flex flex-col p-0 overflow-hidden bg-background text-foreground border border-border">
        {open && (
          <ImportCohortDefaultBody
            cohort={cohort}
            sessions={sessions}
            summary={summary}
            isOrgScope={isOrgScope}
            onClose={onClose}
            onSuccess={onSuccess}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function ImportCohortDefaultBody({
  cohort,
  sessions,
  summary,
  isOrgScope,
  onClose,
  onSuccess,
}: {
  cohort: Cohort
  sessions: Session[]
  summary?: CohortChecklistsSummary
  isOrgScope: boolean
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  const qc = useQueryClient()

  const sortedTargetSessions = useMemo(
    () => [...sessions].sort(compareSessionsChronologically),
    [sessions],
  )

  const summaryBySessionId = useMemo(() => {
    const map = new Map<string, SessionChecklistSummary>()
    for (const s of summary?.sessions ?? []) map.set(s.session_id, s)
    return map
  }, [summary])

  const [sourceType, setSourceType] = useState<"program" | "cohort">("program")
  const [selectedProgramId, setSelectedProgramId] = useState<string>(cohort.program_id)
  const [selectedSourceCohortId, setSelectedSourceCohortId] = useState<string>("")
  const [includeInstructor, setIncludeInstructor] = useState(true)
  const [includeInternal, setIncludeInternal] = useState(true)
  const [includePreWorkshop, setIncludePreWorkshop] = useState(true)
  const [includeTitles, setIncludeTitles] = useState(
    () => !sessions.some((s) => Boolean(s.title?.trim())),
  )
  const [mode, setMode] = useState<"replace" | "fill_empty">("replace")
  const [createMissingSessions, setCreateMissingSessions] = useState(true)
  const [manualMappings, setManualMappings] = useState<{
    sourceKey: string
    map: Record<string, string>
  }>({ sourceKey: "", map: {} })

  const { data: rawPrograms, isLoading: loadingPrograms } = useQuery<Program[]>({
    queryKey: ["sessions-programs"],
    queryFn: getProgramsApi,
    enabled: !isOrgScope,
  })
  const programs = rawPrograms ?? EMPTY_PROGRAMS

  const effectiveProgramId = isOrgScope ? cohort.program_id : selectedProgramId || cohort.program_id

  const { data: programTemplate, isLoading: loadingTemplate } = useQuery<ProgramTemplate>({
    queryKey: ["program-template-for-cohort-import", effectiveProgramId],
    queryFn: () => getProgramTemplateApi(effectiveProgramId),
    enabled: sourceType === "program" && !!effectiveProgramId,
  })

  const { data: rawCohorts, isLoading: loadingCohorts } = useQuery<Cohort[]>({
    queryKey: ["sessions-cohorts-for-default-import", effectiveProgramId],
    queryFn: () => getCohortsApi(effectiveProgramId),
    enabled: !isOrgScope && sourceType === "cohort" && !!effectiveProgramId,
  })
  const eligibleCohorts = useMemo(
    () =>
      (rawCohorts ?? EMPTY_COHORTS).filter((c) => {
        if (c.id === cohort.id) return false
        const statusStr = String(c.status).toLowerCase()
        const normName = c.name.trim().toLowerCase()
        return statusStr !== "draft" && !normName.startsWith("[template]") && normName !== "template"
      }),
    [rawCohorts, cohort.id],
  )

  const effectiveSourceCohortId = useMemo(() => {
    if (sourceType !== "cohort") return ""
    if (selectedSourceCohortId && eligibleCohorts.some((c) => c.id === selectedSourceCohortId)) {
      return selectedSourceCohortId
    }
    return eligibleCohorts[0]?.id ?? ""
  }, [sourceType, selectedSourceCohortId, eligibleCohorts])

  const { data: rawSourceSessions, isLoading: loadingSourceSessions } = useQuery<Session[]>({
    queryKey: ["sessions-for-cohort-default-import", effectiveSourceCohortId],
    queryFn: () => getSessionsApi(effectiveSourceCohortId),
    enabled: !isOrgScope && sourceType === "cohort" && !!effectiveSourceCohortId,
  })

  const sourceDays = useMemo(() => {
    if (sourceType === "program") {
      return (programTemplate?.sessions ?? []).map((s, idx) => ({
        id: s.id,
        label: `Day ${s.day_number || idx + 1}${s.title ? `: ${s.title}` : ""}`,
      }))
    }
    const sorted = [...(rawSourceSessions ?? EMPTY_SESSIONS)].sort(compareSessionsChronologically)
    return sorted.map((s, idx) => ({
      id: s.id,
      label: `Day ${idx + 1}${s.title ? `: ${s.title}` : ""} (${formatShortDate(s.meeting_date)})`,
    }))
  }, [sourceType, programTemplate, rawSourceSessions])

  const currentMappingKey = `${sourceType}:${effectiveProgramId}:${effectiveSourceCohortId}:${sourceDays.map((d) => d.id).join(",")}`

  const effectiveMappings = useMemo(() => {
    const activeOverrides = manualMappings.sourceKey === currentMappingKey ? manualMappings.map : {}
    const out: Record<string, string> = {}
    sortedTargetSessions.forEach((t, idx) => {
      out[t.id] = Object.prototype.hasOwnProperty.call(activeOverrides, t.id)
        ? activeOverrides[t.id]
        : (sourceDays[idx]?.id ?? "")
    })
    return out
  }, [manualMappings, currentMappingKey, sortedTargetSessions, sourceDays])

  const mappedTargetSummaries = useMemo(() => {
    if (mode !== "replace") return []
    return sortedTargetSessions
      .filter((s) => Boolean(effectiveMappings[s.id]))
      .map((s) => summaryBySessionId.get(s.id))
      .filter((s): s is SessionChecklistSummary => Boolean(s))
  }, [mode, sortedTargetSessions, effectiveMappings, summaryBySessionId])

  const hasApprovedConflict =
    mode === "replace" &&
    includeInstructor &&
    mappedTargetSummaries.some((s) => Boolean(s.has_approved_instructor_day))

  const hasProgressWarning =
    mode === "replace" &&
    mappedTargetSummaries.some(
      (s) =>
        (includeInstructor && s.has_instructor_progress) ||
        (includeInternal && s.has_internal_progress),
    )

  const resetAutoMap = () => {
    setManualMappings({ sourceKey: currentMappingKey, map: {} })
  }

  const importMutation = useMutation({
    mutationFn: () => {
      if (!includeInstructor && !includeInternal) {
        throw new Error("Select at least one checklist audience (Instructors or Internal).")
      }
      if (sourceType === "cohort" && !effectiveSourceCohortId) {
        throw new Error("Select a source cohort to import from.")
      }
      return importCohortDefaultsApi(cohort.id, {
        source_type: sourceType,
        source_id: sourceType === "program" ? effectiveProgramId : effectiveSourceCohortId,
        include_instructor: includeInstructor,
        include_internal: includeInternal,
        include_pre_workshop: includePreWorkshop,
        include_titles: includeTitles,
        mode,
        day_mappings:
          sortedTargetSessions.length > 0
            ? sortedTargetSessions.map((s) => ({
              target_session_id: s.id,
              source_session_id: effectiveMappings[s.id] || null,
            }))
            : null,
        create_missing_sessions: sortedTargetSessions.length === 0 ? createMissingSessions : false,
      })
    },
    onSuccess: async (res) => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["checklist-items"] }),
        qc.invalidateQueries({ queryKey: ["cohort-checklists-summary", cohort.id] }),
        qc.invalidateQueries({ queryKey: ["sessions-sessions", cohort.id] }),
        qc.invalidateQueries({ queryKey: ["wizard-sessions", cohort.id] }),
        qc.invalidateQueries({ queryKey: ["session-internal-checklist"] }),
      ])
      const totalItems = res.imported_pre_workshop_count + res.imported_session_items_count
      const parts = [`Imported ${totalItems} checklist item${totalItems === 1 ? "" : "s"}`]
      if (res.sessions_created > 0) parts.push(`created ${res.sessions_created} session${res.sessions_created === 1 ? "" : "s"}`)
      else if (res.sessions_updated > 0) parts.push(`updated ${res.sessions_updated} day${res.sessions_updated === 1 ? "" : "s"}`)
      toast.success(parts.join(" · "))
      onSuccess()
      onClose()
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, "Could not import default checklists"))
    },
  })

  const loadingSource =
    (sourceType === "program" && loadingTemplate) ||
    (sourceType === "cohort" && (loadingCohorts || loadingSourceSessions))

  const internalLabel = isOrgScope ? "Operational" : "Internal team"

  return (
    <>
      <div className="p-4 sm:p-5 pr-12 border-b border-border bg-card">
        <DialogHeader>
          <div className="flex items-center gap-2 text-primary text-xs font-semibold uppercase tracking-wider">
            <Download className="w-3.5 h-3.5" />
            <span>Bulk Import Default Checklists</span>
          </div>
          <DialogTitle className="text-base sm:text-lg font-bold">
            Import Default Days &amp; Checklists
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Copy the full Pre-Workshop and Day 1..N checklists (all Instructor roles and{" "}
            {internalLabel} team) onto this cohort so you can customize or switch days freely.
          </DialogDescription>
        </DialogHeader>
      </div>

      <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-5">
        {/* Source Selector */}
        <div className="space-y-3">
          {!isOrgScope && (
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setSourceType("program")}
                className={cn(
                  "flex items-center gap-2 p-2.5 rounded-xl border text-left transition-all cursor-pointer",
                  sourceType === "program"
                    ? "border-primary bg-primary/5 ring-1 ring-primary text-foreground"
                    : "border-border bg-card text-muted-foreground hover:bg-muted/30",
                )}
              >
                <ListChecks className="w-4 h-4 text-primary shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs font-semibold truncate">Program Default</p>
                  <p className="text-[11px] text-muted-foreground truncate">Template days &amp; roles</p>
                </div>
              </button>
              <button
                type="button"
                onClick={() => setSourceType("cohort")}
                className={cn(
                  "flex items-center gap-2 p-2.5 rounded-xl border text-left transition-all cursor-pointer",
                  sourceType === "cohort"
                    ? "border-primary bg-primary/5 ring-1 ring-primary text-foreground"
                    : "border-border bg-card text-muted-foreground hover:bg-muted/30",
                )}
              >
                <Layers className="w-4 h-4 text-primary shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs font-semibold truncate">Another Cohort</p>
                  <p className="text-[11px] text-muted-foreground truncate">Reuse a past cohort run</p>
                </div>
              </button>
            </div>
          )}

          {!isOrgScope && (
            <div className={cn("grid gap-3", sourceType === "cohort" ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-1")}>
              <label className="flex flex-col gap-1">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Program
                </span>
                <select
                  value={effectiveProgramId}
                  onChange={(e) => {
                    setSelectedProgramId(e.target.value)
                    setSelectedSourceCohortId("")
                  }}
                  disabled={loadingPrograms}
                  className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-xs font-medium focus:outline-none focus:border-primary cursor-pointer"
                >
                  {programs.length === 0 && (
                    <option value={cohort.program_id}>{cohort.program_name || "Current Program"}</option>
                  )}
                  {programs.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                      {p.id === cohort.program_id ? " (Current Program)" : ""}
                    </option>
                  ))}
                </select>
              </label>

              {sourceType === "cohort" && (
                <label className="flex flex-col gap-1">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Source Cohort
                  </span>
                  <select
                    value={effectiveSourceCohortId}
                    onChange={(e) => setSelectedSourceCohortId(e.target.value)}
                    disabled={loadingCohorts || eligibleCohorts.length === 0}
                    className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-xs font-medium focus:outline-none focus:border-primary cursor-pointer disabled:opacity-50"
                  >
                    {eligibleCohorts.length === 0 ? (
                      <option value="">No other cohorts in this program</option>
                    ) : (
                      eligibleCohorts.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                          {c.starts_on ? ` (${c.starts_on})` : ""}
                        </option>
                      ))
                    )}
                  </select>
                </label>
              )}
            </div>
          )}
        </div>

        {/* What to Include & Mode */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-border">
          <div className="space-y-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground block">
              What to Import
            </span>
            <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer select-none">
              <input
                type="checkbox"
                checked={includeInstructor}
                onChange={(e) => setIncludeInstructor(e.target.checked)}
                className="rounded border-border accent-primary"
              />
              <span>Instructor checklists (General + Role-specific)</span>
            </label>
            <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer select-none">
              <input
                type="checkbox"
                checked={includeInternal}
                onChange={(e) => setIncludeInternal(e.target.checked)}
                className="rounded border-border accent-primary"
              />
              <span>{internalLabel} checklist</span>
            </label>
            <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer select-none">
              <input
                type="checkbox"
                checked={includePreWorkshop}
                onChange={(e) => setIncludePreWorkshop(e.target.checked)}
                className="rounded border-border accent-primary"
              />
              <span>Pre-Workshop / Cohort default</span>
            </label>
            <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer select-none">
              <input
                type="checkbox"
                checked={includeTitles}
                onChange={(e) => setIncludeTitles(e.target.checked)}
                className="rounded border-border accent-primary"
              />
              <span>Update session titles from source days</span>
            </label>
          </div>

          <div className="space-y-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground block">
              Conflict Mode
            </span>
            <label
              className={cn(
                "flex items-start gap-2 p-2.5 rounded-xl border cursor-pointer transition-colors",
                mode === "replace" ? "border-primary bg-primary/5" : "border-border bg-card",
              )}
            >
              <input
                type="radio"
                name="cohort-default-import-mode"
                checked={mode === "replace"}
                onChange={() => setMode("replace")}
                className="mt-0.5 accent-primary"
              />
              <div>
                <span className="text-xs font-semibold block">Replace existing</span>
                <span className="text-[11px] text-muted-foreground block">
                  Overwrites checklists on mapped days for selected audiences.
                </span>
              </div>
            </label>
            <label
              className={cn(
                "flex items-start gap-2 p-2.5 rounded-xl border cursor-pointer transition-colors",
                mode === "fill_empty" ? "border-primary bg-primary/5" : "border-border bg-card",
              )}
            >
              <input
                type="radio"
                name="cohort-default-import-mode"
                checked={mode === "fill_empty"}
                onChange={() => setMode("fill_empty")}
                className="mt-0.5 accent-primary"
              />
              <div>
                <span className="text-xs font-semibold block">Fill empty days only</span>
                <span className="text-[11px] text-muted-foreground block">
                  Keeps any day checklists you already edited.
                </span>
              </div>
            </label>
          </div>
        </div>

        {/* Day Mapping Preview */}
        {hasApprovedConflict && (
          <div className="flex items-start gap-2 p-3 rounded-xl border border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300 text-xs">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>
              One or more mapped days already have an approved instructor report and cannot be
              replaced. Switch to &ldquo;Fill empty days only&rdquo;, skip those days below, or
              uncheck Instructor checklists.
            </span>
          </div>
        )}
        {!hasApprovedConflict && hasProgressWarning && (
          <div className="flex items-start gap-2 p-3 rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300 text-xs">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>
              Replacing existing checklists will overwrite current items and clear in-progress ticks
              on the mapped days for the selected audiences.
            </span>
          </div>
        )}

        <div className="space-y-2 pt-2 border-t border-border">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Day Mapping Preview
            </span>
            {sortedTargetSessions.length > 0 && sourceDays.length > 0 && (
              <button
                type="button"
                onClick={resetAutoMap}
                className="text-[11px] font-medium text-primary hover:underline cursor-pointer"
              >
                Auto-match in order
              </button>
            )}
          </div>

          {loadingSource ? (
            <div className="flex items-center justify-center p-6 border border-border rounded-xl bg-card text-xs text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin mr-2 text-primary" /> Loading source days…
            </div>
          ) : sortedTargetSessions.length === 0 ? (
            sourceDays.length > 0 ? (
              <div className="p-3 rounded-xl border border-border bg-card space-y-2">
                <p className="text-xs text-muted-foreground">
                  This cohort has no sessions scheduled yet.
                </p>
                <label className="flex items-center gap-2 text-xs font-medium text-foreground cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={createMissingSessions}
                    onChange={(e) => setCreateMissingSessions(e.target.checked)}
                    className="rounded border-border accent-primary"
                  />
                  <span>
                    Create {sourceDays.length} session{sourceDays.length === 1 ? "" : "s"} from source days
                  </span>
                </label>
              </div>
            ) : (
              <div className="p-3 rounded-xl border border-dashed border-border text-xs text-muted-foreground">
                No template days in this source — Pre-Workshop default items (if any) will still be imported.
              </div>
            )
          ) : sourceDays.length === 0 ? (
            <div className="p-3 rounded-xl border border-dashed border-border text-xs text-muted-foreground">
              This source has no day-level sessions defined — only Pre-Workshop defaults (if any) will be imported.
            </div>
          ) : (
            <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
              {sortedTargetSessions.map((tSess, idx) => (
                <div
                  key={tSess.id}
                  className="flex flex-col sm:flex-row sm:items-center gap-2 p-2 rounded-xl border border-border bg-card"
                >
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <span className="text-[11px] font-bold uppercase text-primary shrink-0">
                      Day {idx + 1}
                    </span>
                    <span className="text-xs font-medium text-foreground truncate">
                      {formatShortDate(tSess.meeting_date)}
                      {tSess.title ? ` · ${tSess.title}` : ""}
                    </span>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 text-muted-foreground hidden sm:block shrink-0" />
                  <select
                    value={effectiveMappings[tSess.id] ?? ""}
                    onChange={(e) => {
                      const val = e.target.value
                      setManualMappings((prev) => ({
                        sourceKey: currentMappingKey,
                        map: {
                          ...(prev.sourceKey === currentMappingKey ? prev.map : {}),
                          [tSess.id]: val,
                        },
                      }))
                    }}
                    className="h-8 px-2.5 sm:w-64 border border-border bg-background text-foreground rounded-lg text-xs focus:outline-none focus:border-primary cursor-pointer"
                  >
                    <option value="">— Skip this day —</option>
                    {sourceDays.map((sd) => (
                      <option key={sd.id} value={sd.id}>
                        {sd.label}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="p-3.5 sm:p-4 border-t border-border bg-muted/20 flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          disabled={importMutation.isPending}
          className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition-colors cursor-pointer"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => importMutation.mutate()}
          disabled={
            importMutation.isPending ||
            loadingSource ||
            hasApprovedConflict ||
            (!includeInstructor && !includeInternal) ||
            (sourceType === "cohort" && !effectiveSourceCohortId) ||
            (sortedTargetSessions.length === 0 && !createMissingSessions && !includePreWorkshop)
          }
          className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 disabled:opacity-50 transition-opacity inline-flex items-center gap-1.5 cursor-pointer"
        >
          {importMutation.isPending ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Importing…
            </>
          ) : (
            <>
              <Download className="w-3.5 h-3.5" /> Import Default
            </>
          )}
        </button>
      </div>
    </>
  )
}
