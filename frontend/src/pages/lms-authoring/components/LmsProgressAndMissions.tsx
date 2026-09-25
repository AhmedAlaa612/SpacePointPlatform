import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import {
  Plus, X, BookOpen, Rocket, ChevronDown, ChevronRight, RotateCcw, Clock, CheckCircle2, XCircle,
  Award, Circle, ExternalLink, Eye, Play, Search, Users,
} from "lucide-react"
import { EmptyState, Spinner } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/pages/admin/components/common"
import { ensureAbsoluteUrl } from "@/lib/utils"
import { DesignRunDetail } from "./DesignRunDetail"
import { fetchMissionCatalog } from "@/api/missions"
import type { ManagedAttempt } from "@/api/missions_manager"
import {
  instructorStepGatesApi, setInstructorStepGateApi,
  instructorStepSelectionApi, setInstructorStepSelectionApi, clearInstructorStepSelectionApi,
  instructorReviewQueueApi, instructorOverrideAttemptApi,
} from "@/api/missionsInstructor"
import { getInstructorCohortQuizReviewApi, resetCohortQuizAttemptApi } from "@/api/cohort_quiz"
import {
  addLmsProgramItemApi, updateLmsProgramItemApi, deleteLmsProgramItemApi,
  getCohortProgramOverrideApi, getCohortProgramOverrideInstructorApi,
  addCohortOverrideItemApi, addCohortOverrideItemInstructorApi,
  updateCohortOverrideItemApi, updateCohortOverrideItemInstructorApi,
  deleteCohortOverrideItemApi, deleteCohortOverrideItemInstructorApi,
  getProgramProgressApi, getCohortProgramProgressApi, confirmChecklistItemApi, getAssignmentItemsApi,
  MISSION_STEP_KEYS,
  type LmsProgram, type LmsProgramItem, type LmsProgramItemInput, type LmsProgramRosterRow, type LmsAssignmentItemDetail,
} from "@/api/lms_admin"
import { ItemForm, ItemRow } from "./LmsChecklistAuthoring"
import { errorDetail } from "./LmsChecklistShared"

interface MissionGroup {
  key: string
  missionId: string | null
  scope: LmsProgramItem["scope"]
  title: string
  items: LmsProgramItem[]
}

/** Groups mission_run items into one card per run. Grouped by
 * `(mission_id, scope)`, not `mission_id` alone — Phase 2 (2026-09) lets
 * the same mission have both an individual run and a team run on one
 * checklist, and those are two distinct runs (two distinct
 * MissionAttempts), not steps of the same one, even though they share a
 * mission_id. */
function groupByMission(items: LmsProgramItem[]): MissionGroup[] {
  const groups: MissionGroup[] = []
  const byRun = new Map<string, LmsProgramItem[]>()
  const ungrouped: LmsProgramItem[] = []
  for (const item of items) {
    if (item.mission_id) {
      const key = `${item.mission_id}:${item.scope}`
      const list = byRun.get(key)
      if (list) list.push(item)
      else byRun.set(key, [item])
    } else {
      ungrouped.push(item)
    }
  }
  for (const [key, groupItems] of byRun) {
    groups.push({ key, missionId: groupItems[0].mission_id, scope: groupItems[0].scope, title: groupItems[0].title, items: groupItems })
  }
  for (const item of ungrouped) {
    groups.push({ key: item.id, missionId: null, scope: item.scope, title: item.title, items: [item] })
  }
  return groups
}

// ── Missions ─────────────────────────────────────────────────────────────
// "a tab to create special mission runs for the program and add them to the
// program checklist" (operator, 2026-08-22) — mission_run items are still
// `LmsProgramItem` rows under the hood (Checklist tab shows the same items
// mixed in with everything else), but this tab is the dedicated place to
// add/edit them and is where a cohort's gates/step selection for each one
// lives, so authoring a mission run never requires the flat item list.

function AddMissionRunButton({ onSave }: { onSave: (data: LmsProgramItemInput) => Promise<void> }) {
  const [addingScope, setAddingScope] = useState<"individual" | "team" | null>(null)
  if (addingScope) {
    return (
      <ItemForm
        itemType="mission_run" initialScope={addingScope}
        onCancel={() => setAddingScope(null)}
        onSave={async (data) => { await onSave(data); setAddingScope(null) }}
      />
    )
  }
  // Individual vs. team is picked here, at add time, not toggled
  // afterward — a mission run's scope is locked server-side once created
  // (guard_locked_submission_scope), same reasoning as a submission item:
  // flipping it later would misattribute one student's personal attempt
  // as the team's shared run.
  const addButtonCls = "flex items-center gap-1.5 h-8 px-3 rounded-full border border-dashed border-border text-xs font-medium text-foreground hover:border-primary/50 hover:bg-primary/5 transition-colors cursor-pointer w-fit"
  return (
    <div className="flex flex-wrap gap-2">
      <button onClick={() => setAddingScope("individual")} className={addButtonCls}>
        <Plus size={13} /> Add individual mission run
      </button>
      <button onClick={() => setAddingScope("team")} className={addButtonCls}>
        <Users size={13} /> Add team mission run
      </button>
    </div>
  )
}

export function ProgramMissionsPanel({
  program, onChanged, readOnly,
}: { program: LmsProgram; onChanged: () => void; readOnly: boolean }) {
  const missionItems = program.items.filter((i) => i.item_type === "mission_run")
  const groups = useMemo(() => groupByMission(missionItems), [missionItems])
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null)

  const { data: catalog = [] } = useQuery({
    queryKey: ["mission-catalog-all"],
    queryFn: fetchMissionCatalog,
  })
  const catalogById = useMemo(() => new Map(catalog.map((m) => [m.id, m.title])), [catalog])

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">
        Every mission run on this program's checklist. Pick a cohort to gate steps or choose which build steps apply
        for that cohort's run — gating is always cohort-specific.
      </p>
      {missionItems.length === 0 && <EmptyState title="No mission runs on this checklist yet" />}
      {groups.map((group) =>
        group.items.length === 1 && !group.items[0].mission_step_key ? (
          <ItemRow
            key={group.items[0].id}
            item={group.items[0]}
            readOnly={readOnly}
            onUpdate={(itemId, data) => updateLmsProgramItemApi(program.id, itemId, data).then(onChanged)}
            onDelete={(itemId) => deleteLmsProgramItemApi(program.id, itemId).then(onChanged)}
          />
        ) : (
          <div key={group.key} className="border border-border rounded-xl overflow-hidden">
            <button
              onClick={() => setExpandedGroup(expandedGroup === group.key ? null : group.key)}
              className="w-full flex items-center gap-3 p-3 hover:bg-muted/40 transition-colors cursor-pointer text-left"
            >
              {expandedGroup === group.key
                ? <ChevronDown size={14} className="shrink-0 text-muted-foreground" />
                : <ChevronRight size={14} className="shrink-0 text-muted-foreground" />}
              <Rocket size={16} className="text-primary shrink-0" />
              <span className="text-sm font-medium truncate">
                {(group.missionId && catalogById.get(group.missionId)) || group.title}
              </span>
              {group.scope === "team" && (
                <span className="text-[10px] font-semibold uppercase text-primary border border-primary/30 bg-primary/10 rounded px-1.5 py-0.5 shrink-0">
                  Team
                </span>
              )}
              <span className="text-[10px] font-semibold text-muted-foreground border border-border rounded px-1.5 py-0.5 shrink-0">
                {group.items.length} {group.items.length === 1 ? "step" : "steps"}
              </span>
            </button>
            {expandedGroup === group.key && (
              <div className="p-2 border-t border-border flex flex-col gap-1.5 bg-muted/20">
                {group.items.map((item) => (
                  <ItemRow
                    key={item.id}
                    item={item}
                    readOnly={readOnly}
                    onUpdate={(itemId, data) => updateLmsProgramItemApi(program.id, itemId, data).then(onChanged)}
                    onDelete={(itemId) => deleteLmsProgramItemApi(program.id, itemId).then(onChanged)}
                  />
                ))}
              </div>
            )}
          </div>
        ),
      )}
      {!readOnly && <AddMissionRunButton onSave={(data) => addLmsProgramItemApi(program.id, data).then(onChanged)} />}
    </div>
  )
}

export function CohortMissionsPanel({ cohortId, isStaff }: { cohortId: string; isStaff: boolean }) {
  const queryClient = useQueryClient()
  const { data: override, isLoading } = useQuery({
    queryKey: ["lms-cohort-override", cohortId],
    queryFn: () => (isStaff ? getCohortProgramOverrideApi(cohortId) : getCohortProgramOverrideInstructorApi(cohortId)),
  })
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["lms-cohort-override", cohortId] })
  const updateItem = isStaff ? updateCohortOverrideItemApi : updateCohortOverrideItemInstructorApi
  const deleteItem = isStaff ? deleteCohortOverrideItemApi : deleteCohortOverrideItemInstructorApi
  const addItem = isStaff ? addCohortOverrideItemApi : addCohortOverrideItemInstructorApi

  const { data: catalog = [] } = useQuery({
    queryKey: ["mission-catalog-all"],
    queryFn: fetchMissionCatalog,
  })
  const catalogById = useMemo(() => new Map(catalog.map((m) => [m.id, m.title])), [catalog])

  if (isLoading) return <Spinner />
  const missionItems = (override?.items ?? []).filter((i) => i.item_type === "mission_run")
  const groups = groupByMission(missionItems)

  return (
    <div className="flex flex-col gap-2">
      {missionItems.length === 0 && <EmptyState title="No mission runs on this cohort's checklist" />}
      {groups.map((group) => {
        const isSingle = group.items.length === 1 && !group.items[0].mission_step_key
        const groupKey = group.key
        const isExpanded = expandedGroup === groupKey
        const missionId = group.missionId
        const missionKind = group.items[0].mission_kind

        if (isSingle) {
          const item = group.items[0]
          if (editingId === item.id) {
            return (
              <ItemForm
                key={item.id} itemType="mission_run" initial={item}
                onCancel={() => setEditingId(null)}
                onSave={async (data) => { await updateItem(cohortId, item.id, data).then(invalidate); setEditingId(null) }}
              />
            )
          }
          return (
            <div key={item.id} className="border border-border rounded-xl overflow-hidden">
              <div className="flex items-center gap-1 pr-2">
                <button
                  onClick={() => setExpandedGroup(isExpanded ? null : groupKey)}
                  className="flex-1 flex items-center gap-3 p-3 hover:bg-muted/40 transition-colors cursor-pointer text-left"
                >
                  {isExpanded ? <ChevronDown size={14} className="shrink-0 text-muted-foreground" /> : <ChevronRight size={14} className="shrink-0 text-muted-foreground" />}
                  <Rocket size={16} className="text-primary shrink-0" />
                  <span className="text-sm font-medium truncate">{item.title}</span>
                  {item.scope === "team" && (
                    <span className="text-[10px] font-semibold uppercase text-primary border border-primary/30 bg-primary/10 rounded px-1.5 py-0.5 shrink-0">
                      Team
                    </span>
                  )}
                </button>
                <button onClick={() => setEditingId(item.id)} className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer shrink-0">Edit</button>
                <button onClick={() => void deleteItem(cohortId, item.id).then(invalidate)} className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors shrink-0 cursor-pointer"><X size={14} /></button>
              </div>
              {isExpanded && missionId && missionKind === "design" && (
                <div className="p-3 border-t border-border flex flex-col gap-4 bg-background">
                  <div>
                    <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Steps included</div>
                    <StepsTab cohortId={cohortId} missionId={missionId} />
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Gates</div>
                    <GatesTab cohortId={cohortId} missionId={missionId} />
                  </div>
                </div>
              )}
              {isExpanded && missionId && missionKind !== "design" && (
                <div className="p-3 border-t border-border text-xs text-muted-foreground bg-background">
                  This is a {missionKind ?? "non-design"} mission — it has no build steps or gates to configure, those only apply to Design missions.
                </div>
              )}
              {isExpanded && !missionId && (
                <div className="p-3 border-t border-border text-xs text-muted-foreground bg-background">
                  Save a mission for this run before gates/steps can be configured.
                </div>
              )}
            </div>
          )
        }

        return (
          <div key={groupKey} className="border border-border rounded-xl overflow-hidden">
            <button
              onClick={() => setExpandedGroup(isExpanded ? null : groupKey)}
              className="w-full flex items-center gap-3 p-3 hover:bg-muted/40 transition-colors cursor-pointer text-left"
            >
              {isExpanded ? <ChevronDown size={14} className="shrink-0 text-muted-foreground" /> : <ChevronRight size={14} className="shrink-0 text-muted-foreground" />}
              <Rocket size={16} className="text-primary shrink-0" />
              <span className="text-sm font-medium truncate">
                {(missionId && catalogById.get(missionId)) || group.title}
              </span>
              {group.scope === "team" && (
                <span className="text-[10px] font-semibold uppercase text-primary border border-primary/30 bg-primary/10 rounded px-1.5 py-0.5 shrink-0">
                  Team
                </span>
              )}
              <span className="text-[10px] font-semibold text-muted-foreground border border-border rounded px-1.5 py-0.5 shrink-0">
                {group.items.length} {group.items.length === 1 ? "step" : "steps"}
              </span>
            </button>
            {isExpanded && (
              <div className="border-t border-border flex flex-col gap-0 bg-muted/20">
                {group.items.map((item) =>
                  editingId === item.id ? (
                    <ItemForm
                      key={item.id} itemType="mission_run" initial={item}
                      onCancel={() => setEditingId(null)}
                      onSave={async (data) => { await updateItem(cohortId, item.id, data).then(invalidate); setEditingId(null) }}
                    />
                  ) : (
                    <div key={item.id} className="flex items-center gap-1 pr-2 border-b border-border/50 last:border-b-0">
                      <div className="flex-1 flex items-center gap-3 p-2.5 pl-10 text-left">
                        <span className="text-sm text-foreground truncate">{item.title}</span>
                        {item.mission_step_key && (
                          <span className="text-[10px] font-semibold uppercase text-muted-foreground border border-border rounded px-1.5 py-0.5 shrink-0">
                            {MISSION_STEP_KEYS.find((s) => s.value === item.mission_step_key)?.label ?? item.mission_step_key}
                          </span>
                        )}
                      </div>
                      <button onClick={() => setEditingId(item.id)} className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer shrink-0">Edit</button>
                      <button onClick={() => void deleteItem(cohortId, item.id).then(invalidate)} className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors shrink-0 cursor-pointer"><X size={14} /></button>
                    </div>
                  ),
                )}
                {missionId && missionKind === "design" && (
                  <div className="p-3 border-t border-border flex flex-col gap-4 bg-background">
                    <div>
                      <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Steps included</div>
                      <StepsTab cohortId={cohortId} missionId={missionId} />
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Gates</div>
                      <GatesTab cohortId={cohortId} missionId={missionId} />
                    </div>
                  </div>
                )}
                {missionId && missionKind !== "design" && (
                  <div className="p-3 border-t border-border text-xs text-muted-foreground bg-background">
                    This is a {missionKind ?? "non-design"} mission — it has no build steps or gates to configure, those only apply to Design missions.
                  </div>
                )}
                {!missionId && (
                  <div className="p-3 border-t border-border text-xs text-muted-foreground bg-background">
                    Save a mission for this run before gates/steps can be configured.
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
      <AddMissionRunButton onSave={(data) => addItem(cohortId, data).then(invalidate)} />
    </div>
  )
}

/** Compositional step selection (2026-08-17) — which of the 9 Design build
 * steps even apply to this cohort's run, distinct from `GatesTab`'s
 * temporal lock/unlock below. The dependency graph is never hardcoded
 * here — it's built purely from each step's `prereqs`, as served by the
 * backend, so this can never drift from the real math. */
function StepsTab({ cohortId, missionId }: { cohortId: string; missionId: string }) {
  const queryClient = useQueryClient()
  const queryKey = ["instructor-step-selection", cohortId, missionId]
  const { data, isLoading } = useQuery({
    queryKey, queryFn: () => instructorStepSelectionApi(cohortId, missionId),
  })
  const [pendingRemoval, setPendingRemoval] = useState<{ stepKey: string; dependents: string[] } | null>(null)
  const [error, setError] = useState("")

  const putMutation = useMutation({
    mutationFn: (stepKeys: string[]) => setInstructorStepSelectionApi(cohortId, missionId, stepKeys),
    onSuccess: (next) => {
      queryClient.setQueryData(queryKey, next)
      setPendingRemoval(null)
      setError("")
    },
    onError: (err) => setError(errorDetail(err, "Couldn't update the step selection.")),
  })
  const resetMutation = useMutation({
    mutationFn: () => clearInstructorStepSelectionApi(cohortId, missionId),
    onSuccess: (next) => queryClient.setQueryData(queryKey, next),
  })

  if (isLoading) return <Spinner />
  if (!data) return null

  const labelFor = (key: string) => data.steps.find((s) => s.step_key === key)?.label ?? key
  const prereqsByKey = Object.fromEntries(data.steps.map((s) => [s.step_key, s.prereqs]))
  const includedKeys = data.steps.filter((s) => s.included).map((s) => s.step_key)

  const closure = (start: string[]): Set<string> => {
    const result = new Set<string>()
    const stack = [...start]
    while (stack.length) {
      const key = stack.pop() as string
      if (result.has(key)) continue
      result.add(key)
      stack.push(...(prereqsByKey[key] ?? []))
    }
    return result
  }

  const handleSelect = (stepKey: string) => {
    putMutation.mutate([...closure([...includedKeys, stepKey])])
  }

  const handleDeselect = (stepKey: string) => {
    const remaining = includedKeys.filter((k) => k !== stepKey)
    const dependents = remaining.filter((k) => closure([k]).has(stepKey))
    if (dependents.length > 0) {
      setPendingRemoval({ stepKey, dependents })
      return
    }
    putMutation.mutate(remaining)
  }

  const confirmRemoval = () => {
    if (!pendingRemoval) return
    const drop = new Set([pendingRemoval.stepKey, ...pendingRemoval.dependents])
    putMutation.mutate(includedKeys.filter((k) => !drop.has(k)))
  }

  return (
    <div className="flex flex-col gap-2">
      {!data.is_default && (
        <button
          onClick={() => resetMutation.mutate()}
          disabled={resetMutation.isPending}
          className="self-start h-8 px-3 rounded-lg text-xs font-medium bg-muted text-muted-foreground hover:bg-muted/70 transition-colors disabled:opacity-50"
        >
          Reset to default (all steps)
        </button>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
      {data.steps.map((s) => (
        <div key={s.step_key} className="flex items-center justify-between p-2.5 bg-card border border-border rounded-lg">
          <p className="text-sm text-foreground">{s.label}</p>
          <button
            onClick={() => (s.included ? handleDeselect(s.step_key) : handleSelect(s.step_key))}
            disabled={putMutation.isPending}
            className={`h-7 px-2.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 ${
              s.included ? "bg-emerald-500/10 text-emerald-600" : "bg-muted text-muted-foreground"}`}
          >
            {s.included ? "Included" : "Excluded"}
          </button>
        </div>
      ))}
      <p className="text-[11px] text-muted-foreground">
        Downlink counts toward completion only when Data, Link and CONOPS are all included —
        {" "}{data.downlink_included ? "currently included." : "currently excluded."}
      </p>

      {pendingRemoval && (
        <ConfirmDialog
          title="Remove dependent steps too?"
          description={
            `${labelFor(pendingRemoval.stepKey)} is required by ` +
            `${pendingRemoval.dependents.map(labelFor).join(", ")}. Removing it will also remove ` +
            `${pendingRemoval.dependents.length === 1 ? "that step" : "those steps"}.`
          }
          confirmLabel="Remove"
          destructive
          pending={putMutation.isPending}
          onCancel={() => setPendingRemoval(null)}
          onConfirm={confirmRemoval}
        />
      )}
    </div>
  )
}

function GatesTab({ cohortId, missionId }: { cohortId: string; missionId: string }) {
  const queryClient = useQueryClient()
  const { data: gates = [], isLoading } = useQuery({
    queryKey: ["instructor-step-gates", cohortId, missionId], queryFn: () => instructorStepGatesApi(cohortId, missionId),
  })
  const toggleMutation = useMutation({
    mutationFn: ({ stepKey, isUnlocked }: { stepKey: string; isUnlocked: boolean }) =>
      setInstructorStepGateApi(cohortId, missionId, stepKey, isUnlocked),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["instructor-step-gates", cohortId, missionId] }),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-2">
      {gates.map((g) => (
        <div key={g.step_key} className="flex items-center justify-between p-2.5 bg-card border border-border rounded-lg">
          <div>
            <p className="text-sm text-foreground">{g.label}</p>
            {g.updated_by_name && <p className="text-[11px] text-muted-foreground">Last set by {g.updated_by_name}</p>}
          </div>
          <button
            onClick={() => toggleMutation.mutate({ stepKey: g.step_key, isUnlocked: !g.is_unlocked })}
            disabled={toggleMutation.isPending}
            className={`h-7 px-2.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 ${
              g.is_unlocked ? "bg-emerald-500/10 text-emerald-600" : "bg-muted text-muted-foreground"}`}
          >
            {g.is_unlocked ? "Unlocked" : "Locked"}
          </button>
        </div>
      ))}
    </div>
  )
}

// ── Progress ─────────────────────────────────────────────────────────────
// Student roster — cohort- or program-wide. Clicking a student opens their
// profile; each row expands to every checklist item's real status and
// submission link, not just the ones awaiting confirmation (operator ask,
// 2026-08-22: "detailed submissions... by detailed I really mean detailed").

export function ProgressPanel({
  cohortId, lmsProgramId, scopeLabel,
}: { cohortId?: string; lmsProgramId?: string; scopeLabel: string }) {
  const [search, setSearch] = useState("")
  const queryClient = useQueryClient()
  const queryKey = cohortId ? ["instructor-program-progress", cohortId] : ["instructor-program-wide-progress", lmsProgramId]
  const { data: rows, isLoading } = useQuery({
    queryKey,
    queryFn: () => (cohortId ? getCohortProgramProgressApi(cohortId) : getProgramProgressApi(lmsProgramId as string)),
  })

  const confirmMutation = useMutation({
    mutationFn: (vars: { assignmentCohortId: string; assignmentId: string; itemId: string }) =>
      confirmChecklistItemApi(vars.assignmentCohortId, vars.assignmentId, vars.itemId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey }),
  })

  const filteredRows = useMemo(() => {
    if (!rows) return []
    if (!search.trim()) return rows
    const q = search.toLowerCase()
    return rows.filter((r) => r.student_name.toLowerCase().includes(q) || (r.name && r.name.toLowerCase().includes(q)))
  }, [rows, search])

  if (isLoading) return <Spinner />
  if (!rows || rows.length === 0) {
    return <EmptyState title="No students assigned this checklist yet" hint={`Showing ${scopeLabel}.`} />
  }

  return (
    <div className="flex flex-col gap-3">
      {rows.length > 0 && (
        <div className="relative w-full sm:w-64 self-end">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by student name…"
            className="h-8 w-full pl-8 pr-3 border border-border bg-background text-foreground rounded-lg text-xs focus:outline-none focus:border-primary transition-colors"
          />
        </div>
      )}

      {filteredRows.length === 0 ? (
        <p className="text-xs text-muted-foreground text-center py-6">No students match "{search}"</p>
      ) : (
        <div className="flex flex-col gap-3">
          {filteredRows.map((row) => (
            <ProgressRow
              key={row.assignment_id} row={row} cohortId={cohortId}
              onConfirm={(itemId) => cohortId && confirmMutation.mutate({ assignmentCohortId: cohortId, assignmentId: row.assignment_id, itemId })}
              confirmPending={confirmMutation.isPending}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function ProgressRow({
  row, cohortId, onConfirm, confirmPending,
}: { row: LmsProgramRosterRow; cohortId?: string; onConfirm: (itemId: string) => void; confirmPending: boolean }) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const { data: items, isLoading: itemsLoading } = useQuery<LmsAssignmentItemDetail[]>({
    queryKey: ["assignment-items", cohortId, row.assignment_id],
    queryFn: () => getAssignmentItemsApi(cohortId as string, row.assignment_id),
    enabled: open && !!cohortId,
  })

  // Get student initials for avatar placeholder
  const initials = (row.student_name || "S").split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2)

  return (
    <div className="shrink-0 border-2 border-border/80 rounded-2xl bg-card shadow-sm transition-all hover:border-primary/40 overflow-hidden">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4 p-3.5 sm:p-5">
        <div className="flex items-center gap-2.5 sm:gap-3 min-w-0 flex-1">
          <button
            onClick={() => cohortId && setOpen((v) => !v)}
            className="p-1.5 sm:p-2 rounded-xl bg-muted/60 hover:bg-muted text-muted-foreground transition-colors shrink-0 cursor-pointer disabled:opacity-40"
            disabled={!cohortId}
            title={cohortId ? "Show item detail" : "Pick a cohort to see item detail"}
          >
            {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </button>

          <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-primary/10 border border-primary/20 text-primary font-bold flex items-center justify-center text-xs sm:text-sm shrink-0">
            {initials}
          </div>

          <button
            onClick={() => {
              const from = typeof window !== "undefined" ? (window.location.pathname + window.location.search) : undefined
              void navigate({
                to: `/lms-authoring/students/${row.user_id}`,
                search: (from ? { from } : {}) as never,
              })
            }}
            className="min-w-0 flex-1 text-left group cursor-pointer"
          >
            <div className="text-sm sm:text-base font-bold text-foreground group-hover:text-primary transition-colors truncate">
              {row.student_name}
            </div>
            <div className="text-xs font-medium text-muted-foreground truncate flex items-center gap-1.5 mt-0.5">
              <BookOpen size={12} className="shrink-0 text-muted-foreground/70" />
              <span>{row.name}</span>
            </div>
          </button>

          {row.certificate_required && (
            <span className={`shrink-0 text-xs font-bold px-2 sm:px-2.5 py-1 rounded-xl flex items-center gap-1.5 ${
              row.certificate_earned
                ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                : "bg-muted/80 text-muted-foreground border border-border/50"
            }`}>
              {row.certificate_earned ? (
                <>
                  <CheckCircle2 size={13} className="text-emerald-500" />
                  <span className="hidden sm:inline">Certified</span>
                </>
              ) : (
                <>
                  <Award size={13} className="text-muted-foreground/60" />
                  <span className="hidden sm:inline">Not certified</span>
                </>
              )}
            </span>
          )}
        </div>

        <div className="flex flex-col gap-1.5 w-full sm:w-48 md:w-56 shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-border/40">
          <div className="flex items-center justify-between text-xs font-mono font-bold">
            <span className="text-muted-foreground">{row.items_done} / {row.items_total} completed</span>
            <span className={row.pct === 100 ? "text-emerald-500 font-extrabold" : "text-foreground"}>{row.pct}%</span>
          </div>
          <div className="h-2.5 rounded-full bg-muted p-0.5 border border-border/40 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${row.pct === 100 ? "bg-emerald-500" : "bg-primary"}`}
              style={{ width: `${row.pct}%` }}
            />
          </div>
        </div>

        {row.pending_confirmations.length > 0 && (
          <div className="flex flex-wrap gap-1.5 shrink-0 w-full sm:w-auto sm:max-w-[220px] justify-start sm:justify-end">
            {row.pending_confirmations.map((p) => (
              <Button
                key={p.item_id} size="sm" variant="outline"
                disabled={confirmPending || !cohortId}
                onClick={() => onConfirm(p.item_id)}
                title={p.title}
                className="h-8 text-xs font-bold border-amber-500/40 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
              >
                Confirm: {p.title.length > 16 ? `${p.title.slice(0, 16)}…` : p.title}
              </Button>
            ))}
          </div>
        )}
      </div>

      {open && (
        <div className="p-3 sm:p-5 border-t-2 border-border/60 bg-muted/20 flex flex-col gap-2.5">
          {itemsLoading ? (
            <div className="py-4"><Spinner /></div>
          ) : (items ?? []).length === 0 ? (
            <p className="text-xs text-muted-foreground italic py-2">No items found for this student checklist.</p>
          ) : (
            (items ?? []).map((item) => (
              <AssignmentItemRow key={item.item_id} item={item} cohortId={cohortId} assignmentId={row.assignment_id} />
            ))
          )}
        </div>
      )}
    </div>
  )
}

/** A single checklist item under a student's Progress row. A `mission_run`
 * item carries `mission_attempt_id` once the student has an attempt, so it
 * gets the same "view their run" toggle as the Review queue
 * (`DesignRunDetail`, wired 2026-08-30) instead of leaving "done" as a dead
 * end with nothing to click. A `quiz` item gets the same idea (2026-09):
 * "view answers" once submitted (per-question correct/incorrect, response
 * time, what was left unanswered), plus a "Reset" ops/instructor can use
 * any time to let the student retake it — deletes the attempt so their
 * next visit starts fresh. */
function AssignmentItemRow({
  item, cohortId, assignmentId,
}: { item: LmsAssignmentItemDetail; cohortId?: string; assignmentId: string }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [showRun, setShowRun] = useState(false)
  const [showQuizReview, setShowQuizReview] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const isMissionRun = item.item_type === "mission_run" && !!item.mission_attempt_id
  // DesignRunDetail replicates the Design wizard off a `Design` row that
  // only a design-kind attempt ever has — a Ground Station (or any other
  // non-design) run has no such row, so pointing it there just 404s
  // ("Couldn't load this run's detail."). Those get a link to the same
  // live console ops already can open from the Ground Station page.
  const canViewRun = isMissionRun && item.mission_kind === "design"
  const canOpenConsole = isMissionRun && item.mission_kind === "ground_station"
  const isQuiz = item.item_type === "quiz"

  const resetMutation = useMutation({
    mutationFn: () => resetCohortQuizAttemptApi(cohortId as string, assignmentId, item.item_id),
    onSuccess: () => {
      setConfirmReset(false)
      void queryClient.invalidateQueries({ queryKey: ["assignment-items", cohortId, assignmentId] })
      void queryClient.invalidateQueries({ queryKey: ["cohort-quiz-review", cohortId, assignmentId, item.item_id] })
      void queryClient.invalidateQueries({ queryKey: ["instructor-program-progress", cohortId] })
    },
  })

  const isDone = item.status === "done"
  const isAwaiting = item.status === "awaiting_confirmation"
  const isPoster = item.mission_step_key === "poster"
  const hasActions = Boolean(
    item.submitted_url || item.submitted_text || (item.submission_multi_link && item.submitted_links?.length)
    || canViewRun || canOpenConsole || (isQuiz && (isDone || cohortId)) || isPoster,
  )

  return (
    <div className="flex flex-col gap-2">
      <div className="p-3 sm:p-3.5 rounded-xl bg-card border border-border/60 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 sm:gap-3 hover:border-border transition-all">
        <div className="flex items-center gap-2.5 sm:gap-3 min-w-0 flex-1">
          {isDone ? (
            <div className="w-7 h-7 rounded-lg bg-emerald-500/15 text-emerald-400 flex items-center justify-center border border-emerald-500/30 shrink-0">
              <CheckCircle2 size={15} />
            </div>
          ) : isAwaiting ? (
            <div className="w-7 h-7 rounded-lg bg-amber-500/15 text-amber-400 flex items-center justify-center border border-amber-500/30 shrink-0">
              <Clock size={15} />
            </div>
          ) : (
            <div className="w-7 h-7 rounded-lg bg-muted text-muted-foreground flex items-center justify-center border border-border/50 shrink-0">
              <Circle size={15} />
            </div>
          )}

          <div className="text-sm font-medium sm:font-semibold text-foreground flex-1 min-w-0 break-words sm:truncate flex items-center gap-2">
            <span>{item.title}</span>
            {isPoster && (
              <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded border border-purple-500/30 bg-purple-500/10 text-purple-400 shrink-0">
                Poster
              </span>
            )}
          </div>

          <span className={`text-[11px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md shrink-0 sm:hidden ${
            isDone ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : isAwaiting ? "bg-amber-500/10 text-amber-400 border border-amber-500/20" : "bg-muted text-muted-foreground border border-border/40"
          }`}>
            {item.status.replace("_", " ")}
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap shrink-0 justify-end sm:justify-start">
          {hasActions && (
            <div className="flex items-center gap-2 flex-wrap shrink-0 w-full sm:w-auto pt-2 sm:pt-0 border-t sm:border-t-0 border-border/30">
              {item.submission_multi_link ? (
                item.submitted_links && item.submitted_links.length > 0 ? (
                  item.submitted_links.map((link, i) => (
                    link.text ? (
                      // Text field (2026-09-16) — no link to open, so this is
                      // a static badge; the full answer is in the title
                      // tooltip since there's no room for it inline here.
                      <span
                        key={i} title={link.text}
                        className="h-8 px-3 rounded-lg border border-border/60 bg-muted/40 text-foreground text-xs font-bold flex items-center gap-1.5 shrink-0 max-w-[200px]"
                      >
                        <span className="truncate">{link.label || `Field ${i + 1}`}: {link.text}</span>
                      </span>
                    ) : (
                      <a
                        key={i}
                        href={ensureAbsoluteUrl(link.url ?? "")}
                        target="_blank"
                        rel="noreferrer"
                        className="h-8 px-3 rounded-lg border border-primary/30 bg-primary/10 text-primary text-xs font-bold flex items-center gap-1.5 hover:bg-primary/20 transition-colors shrink-0"
                      >
                        <ExternalLink size={13} /> {link.label || `Link ${i + 1}`}
                      </a>
                    )
                  ))
                ) : (
                  <span className="h-8 px-2.5 rounded-lg border border-border/60 bg-muted/40 text-muted-foreground text-xs font-medium flex items-center gap-1.5 shrink-0">
                    No fields submitted yet
                  </span>
                )
              ) : item.submitted_url ? (
                <a
                  href={ensureAbsoluteUrl(item.submitted_url)}
                  target="_blank"
                  rel="noreferrer"
                  className="h-8 px-3 rounded-lg border border-primary/30 bg-primary/10 text-primary text-xs font-bold flex items-center gap-1.5 hover:bg-primary/20 transition-colors shrink-0"
                >
                  <ExternalLink size={13} /> {isPoster ? "View Poster" : "Submission"}
                </a>
              ) : item.submitted_text ? (
                // A plain single-field submission's own type can be text
                // (2026-09-16) — no link to open, so this is a static badge;
                // the full answer is in the title tooltip.
                <span
                  title={item.submitted_text}
                  className="h-8 px-3 rounded-lg border border-border/60 bg-muted/40 text-foreground text-xs font-bold flex items-center gap-1.5 shrink-0 max-w-[240px]"
                >
                  <span className="truncate">{item.submitted_text}</span>
                </span>
              ) : isPoster ? (
                <span className="h-8 px-2.5 rounded-lg border border-border/60 bg-muted/40 text-muted-foreground text-xs font-medium flex items-center gap-1.5 shrink-0">
                  No poster submitted yet
                </span>
              ) : null}

              {canViewRun && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setShowRun((v) => !v)}
                  className="h-8 text-xs font-semibold gap-1.5 shrink-0"
                >
                  <Play size={13} className="text-primary" />
                  {showRun ? "Hide run" : "View run"}
                </Button>
              )}

              {canOpenConsole && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void navigate({
                    to: "/learn/missions/ground-station/$attemptId",
                    params: { attemptId: item.mission_attempt_id as string },
                  })}
                  className="h-8 text-xs font-semibold gap-1.5 shrink-0"
                >
                  <Play size={13} className="text-primary" />
                  Open console
                </Button>
              )}

              {isQuiz && isDone && cohortId && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setShowQuizReview((v) => !v)}
                  className="h-8 text-xs font-semibold gap-1.5 shrink-0"
                >
                  <Eye size={13} className="text-primary" />
                  {showQuizReview ? "Hide answers" : "View answers"}
                </Button>
              )}

              {isQuiz && cohortId && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setConfirmReset(true)}
                  className="h-8 text-xs font-semibold text-muted-foreground hover:text-destructive hover:bg-destructive/10 gap-1.5 shrink-0"
                  title="Let this student retake the quiz"
                >
                  <RotateCcw size={13} /> Reset
                </Button>
              )}
            </div>
          )}

          <span className={`hidden sm:inline-block text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded-md shrink-0 ${
            isDone ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : isAwaiting ? "bg-amber-500/10 text-amber-400 border border-amber-500/20" : "bg-muted text-muted-foreground border border-border/40"
          }`}>
            {item.status.replace("_", " ")}
          </span>
        </div>
      </div>

      {canViewRun && showRun && (
        <div className="mt-1 border-2 border-border rounded-xl bg-card p-2 shadow-lg">
          <DesignRunDetail attemptId={item.mission_attempt_id as string} />
        </div>
      )}

      {isQuiz && showQuizReview && cohortId && (
        <div className="mt-1 border-2 border-border rounded-xl bg-card p-3 shadow-lg">
          <QuizAnswersReview cohortId={cohortId} assignmentId={assignmentId} itemId={item.item_id} />
        </div>
      )}

      {confirmReset && (
        <ConfirmDialog
          title="Reset this student's quiz?"
          description="This deletes their attempt (answers included) so their next visit starts a brand-new one — a fresh question order and fresh timers. This can't be undone."
          confirmLabel="Reset"
          destructive
          pending={resetMutation.isPending}
          onCancel={() => setConfirmReset(false)}
          onConfirm={() => resetMutation.mutate()}
        />
      )}

      {resetMutation.isError && (
        <p className="text-xs text-destructive mt-1 font-medium">{errorDetail(resetMutation.error, "Couldn't reset this quiz")}</p>
      )}
    </div>
  )
}

/** The ops/instructor drill-in on one student's quiz answers — per-question
 * correct/incorrect, how long they took, and what they left unanswered
 * (`selected_index: null`), all of which feeds the evaluation the same way
 * a mission run's detail does. */
export function QuizAnswersReview({ cohortId, assignmentId, itemId }: { cohortId: string; assignmentId: string; itemId: string }) {
  const { data: result, isLoading, isError, error } = useQuery({
    queryKey: ["cohort-quiz-review", cohortId, assignmentId, itemId],
    queryFn: () => getInstructorCohortQuizReviewApi(cohortId, assignmentId, itemId),
  })

  if (isLoading) return <div className="p-3"><Spinner /></div>
  if (isError) {
    return <p className="p-3 text-xs text-destructive">{errorDetail(error, "Couldn't load this student's answers")}</p>
  }
  if (!result) return null

  return (
    <div className="border border-border rounded-lg bg-card p-3 flex flex-col gap-3">
      <div className="flex items-center gap-3 text-xs font-semibold text-foreground">
        <span>{result.score} / {result.total} correct</span>
        {result.topic_breakdown && (
          <span className="text-muted-foreground font-normal">
            {Object.entries(result.topic_breakdown).map(([topic, { correct, total }]) => `${topic} ${correct}/${total}`).join(" · ")}
          </span>
        )}
      </div>
      <div className="flex flex-col gap-2">
        {result.questions.map((q, i) => (
          <div
            key={q.question_id}
            className={`rounded-lg border p-2.5 flex flex-col gap-1.5 ${
              q.is_correct ? "border-border bg-background" : "border-red-500/30 bg-red-500/5"
            }`}
          >
            <div className="flex items-center gap-2 flex-wrap text-[11px]">
              <span className="font-mono text-muted-foreground">Q{i + 1}</span>
              <span className="px-1.5 py-0.5 rounded-full border border-border text-muted-foreground uppercase tracking-wide">{q.topic}</span>
              {q.is_correct ? (
                <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-semibold"><CheckCircle2 size={11} /> Correct</span>
              ) : (
                <span className="flex items-center gap-1 text-red-600 dark:text-red-400 font-semibold"><XCircle size={11} /> Incorrect</span>
              )}
              {q.selected_index === null && (
                <span className="text-muted-foreground italic">— left unanswered{q.timed_out ? " (timed out)" : ""}</span>
              )}
              {q.time_taken_seconds != null && (
                <span className="flex items-center gap-1 text-muted-foreground ml-auto"><Clock size={11} /> {q.time_taken_seconds}s</span>
              )}
            </div>
            <p className="text-xs font-medium text-foreground">{q.prompt}</p>
            <div className="flex flex-col gap-0.5">
              {q.options.map((text, oi) => (
                <div
                  key={oi}
                  className={`px-2 py-1 rounded text-[11px] ${
                    oi === q.correct_index
                      ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 font-medium"
                      : oi === q.selected_index
                      ? "bg-red-500/10 text-red-700 dark:text-red-400"
                      : "text-muted-foreground"
                  }`}
                >
                  {text}
                  {oi === q.correct_index && <span className="ml-1.5 text-[10px]">(correct)</span>}
                  {oi === q.selected_index && oi !== q.correct_index && <span className="ml-1.5 text-[10px]">(their answer)</span>}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Review ───────────────────────────────────────────────────────────────
// Cohort-scoped only. Adds a mission picker (a program checklist can list
// several missions) on top of what `CohortMissions.tsx` used to do alone.

export function ReviewScopePanel({ cohortId }: { cohortId: string }) {
  const { data: missions = [] } = useQuery({
    queryKey: ["mission-catalog-design-only"],
    queryFn: async () => (await fetchMissionCatalog()).filter((m) => m.kind === "design"),
  })
  const [missionId, setMissionId] = useState<string | null>(null)
  const effectiveMissionId = missionId ?? missions[0]?.id ?? null

  if (missions.length === 0) return <EmptyState title="No design missions published yet" />

  return (
    <div className="flex flex-col gap-3">
      <select
        value={effectiveMissionId ?? ""}
        onChange={(e) => setMissionId(e.target.value)}
        className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm w-fit focus:outline-none focus:border-primary"
      >
        {missions.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}
      </select>
      {effectiveMissionId && <ReviewTab cohortId={cohortId} missionId={effectiveMissionId} />}
    </div>
  )
}

function ReviewAttemptRow({ attempt, cohortId, missionId }: { attempt: ManagedAttempt; cohortId: string; missionId: string }) {
  const queryClient = useQueryClient()
  const [error, setError] = useState("")
  const [overriding, setOverriding] = useState(false)
  const [overrideReason, setOverrideReason] = useState("")
  // Operator ask (2026-08-24) was "open the run and see everything there
  // with read only, just like the student view" — that landed on the
  // student profile's Mission runs list, but never here, where a reviewer
  // actually needs it before deciding Pass/Fail on a just-submitted run.
  const [showRun, setShowRun] = useState(false)

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["instructor-review-queue", cohortId, missionId] })

  const overrideMutation = useMutation({
    mutationFn: (passed: boolean) => instructorOverrideAttemptApi(attempt.id, { passed, reason: overrideReason.trim() }),
    onSuccess: () => { setError(""); setOverriding(false); setOverrideReason(""); invalidate() },
    onError: (e) => setError(errorDetail(e, "Couldn't override this attempt")),
  })

  return (
    <div className="p-4 bg-background border border-border rounded-xl flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-foreground">{attempt.student_name ?? attempt.team_name ?? "Unknown"}</p>
        <span className="text-xs text-muted-foreground">Attempt {attempt.attempt_no} · {attempt.status}</span>
      </div>
      <button
        onClick={() => setShowRun((v) => !v)}
        className="flex items-center gap-1 text-xs font-medium text-primary hover:opacity-80 transition-opacity w-fit cursor-pointer"
      >
        <ChevronDown size={13} className={`transition-transform ${showRun ? "rotate-180" : ""}`} />
        {showRun ? "Hide" : "View"} their mission run
      </button>
      {showRun && (
        <div className="border border-border rounded-lg bg-card">
          <DesignRunDetail attemptId={attempt.id} />
        </div>
      )}
      {/* Plain Pass/Fail hidden (2026-08-30 operator ask) — this mission
          kind has no instructor-decided pass/fail; a Design run grades
          itself once every step is valid (see the empty-state hint
          above). "Force pass/fail" stays as the one legitimate manual
          path — unblocking a student stuck on a mistake, not routine
          grading. */}
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => setOverriding((v) => !v)}>
          {overriding ? "Cancel override" : "Force pass/fail…"}
        </Button>
      </div>
      {overriding && (
        <div className="flex flex-col gap-2 p-3 bg-muted/40 border border-border rounded-lg">
          <p className="text-[11px] text-muted-foreground">
            Overrides this attempt's outcome regardless of its current status — use this to unblock a student stuck
            on a mistake, not as the normal review path. A reason is required.
          </p>
          <input
            value={overrideReason} onChange={(e) => setOverrideReason(e.target.value)} placeholder="Why override this attempt?"
            className="h-8 px-2 border border-border bg-card text-foreground rounded-lg text-xs focus:outline-none focus:border-primary"
          />
          <div className="flex gap-2">
            <Button size="sm" disabled={!overrideReason.trim() || overrideMutation.isPending} onClick={() => overrideMutation.mutate(true)}>
              Force pass
            </Button>
            <Button size="sm" variant="destructive" disabled={!overrideReason.trim() || overrideMutation.isPending} onClick={() => overrideMutation.mutate(false)}>
              Force fail
            </Button>
          </div>
        </div>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

function ReviewTab({ cohortId, missionId }: { cohortId: string; missionId: string }) {
  const { data: queue = [], isLoading } = useQuery({
    queryKey: ["instructor-review-queue", cohortId, missionId], queryFn: () => instructorReviewQueueApi(cohortId, missionId),
  })

  if (isLoading) return <Spinner />
  if (queue.length === 0) {
    return (
      <EmptyState
        title="Nothing in the review queue right now"
        hint='A Design mission run passes on its own once every step is valid. Use "Force pass/fail" on a specific attempt below if a student needs a manual unblock.'
      />
    )
  }
  return (
    <div className="flex flex-col gap-3">
      {queue.map((a) => <ReviewAttemptRow key={a.id} attempt={a} cohortId={cohortId} missionId={missionId} />)}
    </div>
  )
}
