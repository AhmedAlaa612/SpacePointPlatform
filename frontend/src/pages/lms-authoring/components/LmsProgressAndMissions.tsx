import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import {
  Plus, X, BookOpen, Rocket, ChevronDown, ChevronRight, RotateCcw, Clock, CheckCircle2, XCircle,
  Award, Circle, ExternalLink, Eye, Play, Search, Users, Trash2, Gamepad2,
} from "lucide-react"
import { EmptyState, Spinner } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/pages/admin/components/common"
import { observerResetProgressApi, observerResetTeamApi, observerUnassignApi } from "@/api/lms"
import { getStudentArcadeBestAttemptApi } from "@/api/arcade"
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
  type RosterMode,
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

function AddMissionRunButton({ onSave, cohortId }: { onSave: (data: LmsProgramItemInput) => Promise<void>; cohortId?: string }) {
  const [addingScope, setAddingScope] = useState<"individual" | "team" | null>(null)
  if (addingScope) {
    return (
      <ItemForm
        itemType="mission_run" initialScope={addingScope} cohortId={cohortId}
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
                key={item.id} itemType="mission_run" initial={item} cohortId={cohortId}
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
                      key={item.id} itemType="mission_run" initial={item} cohortId={cohortId}
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
      <AddMissionRunButton cohortId={cohortId} onSave={(data) => addItem(cohortId, data).then(invalidate)} />
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

// Observer mode (2026-10) — `[Students | Observers]` segmented toggle for
// the ops Progress Panel. Participant is the default slice; observers are
// staff/tester sandboxes inspected separately.
function RosterModeToggle({ mode, onChange }: { mode: RosterMode; onChange: (m: RosterMode) => void }) {
  const btn = (active: boolean) =>
    `px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
      active ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
    }`
  return (
    <div className="flex items-center gap-1 p-1 rounded-xl border border-border bg-muted/40 w-fit">
      <button onClick={() => onChange("participant")} className={btn(mode === "participant")}>
        Students
      </button>
      <button onClick={() => onChange("observer")} className={btn(mode === "observer")}>
        Observers
      </button>
    </div>
  )
}

export function ProgressPanel({
  cohortId, lmsProgramId, scopeLabel,
}: { cohortId?: string; lmsProgramId?: string; scopeLabel: string }) {
  const [search, setSearch] = useState("")
  const [sortBy, setSortBy] = useState<"progress_desc" | "progress_asc" | "name_asc" | "name_desc">("progress_desc")
  // Observer mode (2026-10) — `[Students | Observers]` toggle. The default
  // slice is real students; observers are inspected separately so staff
  // testing never mixes into official completion data.
  const [rosterMode, setRosterMode] = useState<RosterMode>("participant")
  const queryClient = useQueryClient()
  const queryKey = cohortId
    ? ["instructor-program-progress", cohortId, rosterMode]
    : ["instructor-program-wide-progress", lmsProgramId, rosterMode]
  const { data: rows, isLoading } = useQuery({
    queryKey,
    queryFn: () => (cohortId ? getCohortProgramProgressApi(cohortId, rosterMode) : getProgramProgressApi(lmsProgramId as string, rosterMode)),
  })

  const confirmMutation = useMutation({
    mutationFn: (vars: { assignmentCohortId: string; assignmentId: string; itemId: string }) =>
      confirmChecklistItemApi(vars.assignmentCohortId, vars.assignmentId, vars.itemId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey }),
  })

  const sortedRows = useMemo(() => {
    if (!rows) return []
    let list = rows
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter((r) => r.student_name.toLowerCase().includes(q) || (r.name && r.name.toLowerCase().includes(q)))
    }
    return [...list].sort((a, b) => {
      if (sortBy === "progress_desc") {
        return (b.pct ?? 0) - (a.pct ?? 0) || (b.items_done ?? 0) - (a.items_done ?? 0) || a.student_name.localeCompare(b.student_name)
      }
      if (sortBy === "progress_asc") {
        return (a.pct ?? 0) - (b.pct ?? 0) || (a.items_done ?? 0) - (b.items_done ?? 0) || a.student_name.localeCompare(b.student_name)
      }
      if (sortBy === "name_desc") {
        return b.student_name.localeCompare(a.student_name)
      }
      return a.student_name.localeCompare(b.student_name)
    })
  }, [rows, search, sortBy])

  if (isLoading) return <Spinner />
  if (!rows || rows.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        <RosterModeToggle mode={rosterMode} onChange={setRosterMode} />
        <EmptyState
          title={rosterMode === "observer" ? "No observers testing this checklist yet" : "No students assigned this checklist yet"}
          hint={`Showing ${scopeLabel}.`}
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <RosterModeToggle mode={rosterMode} onChange={setRosterMode} />
        {rows.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap w-full sm:w-auto">
            <div className="relative w-full sm:w-64">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={rosterMode === "observer" ? "Search by observer name…" : "Search by student name…"}
                className="h-8 w-full pl-8 pr-3 border border-border bg-background text-foreground rounded-lg text-xs focus:outline-none focus:border-primary transition-colors"
              />
            </div>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              className="h-8 px-2.5 border border-border bg-background text-foreground rounded-lg text-xs font-medium cursor-pointer focus:outline-none focus:border-primary"
              aria-label="Sort individual progress"
            >
              <option value="progress_desc">Sort: Highest progress</option>
              <option value="progress_asc">Sort: Lowest progress</option>
              <option value="name_asc">Sort: Name (A-Z)</option>
              <option value="name_desc">Sort: Name (Z-A)</option>
            </select>
          </div>
        )}
      </div>

      {sortedRows.length === 0 ? (
        <p className="text-xs text-muted-foreground text-center py-6">
          {rosterMode === "observer" ? `No observers match "${search}"` : `No students match "${search}"`}
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {sortedRows.map((row) => (
            <ProgressRow
              key={row.assignment_id} row={row} cohortId={cohortId} lmsProgramId={lmsProgramId}
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
  row, cohortId, lmsProgramId, onConfirm, confirmPending,
}: {
  row: LmsProgramRosterRow
  cohortId?: string
  lmsProgramId?: string
  onConfirm: (itemId: string) => void
  confirmPending: boolean
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [confirmResetProgress, setConfirmResetProgress] = useState(false)
  const [confirmResetTeam, setConfirmResetTeam] = useState(false)
  const [confirmRevoke, setConfirmRevoke] = useState(false)

  const isObserver = row.mode === "observer"

  const resetProgressMutation = useMutation({
    mutationFn: () => observerResetProgressApi(row.assignment_id),
    onSuccess: () => {
      setConfirmResetProgress(false)
      void queryClient.invalidateQueries({ queryKey: ["assignment-items", cohortId, row.assignment_id] })
      if (cohortId) {
        void queryClient.invalidateQueries({ queryKey: ["instructor-program-progress", cohortId] })
      }
      if (lmsProgramId) {
        void queryClient.invalidateQueries({ queryKey: ["instructor-program-wide-progress", lmsProgramId] })
      }
    },
  })

  const resetTeamMutation = useMutation({
    mutationFn: () => observerResetTeamApi(row.assignment_id),
    onSuccess: () => {
      setConfirmResetTeam(false)
      void queryClient.invalidateQueries({ queryKey: ["assignment-items", cohortId, row.assignment_id] })
      if (cohortId) {
        void queryClient.invalidateQueries({ queryKey: ["instructor-program-progress", cohortId] })
        void queryClient.invalidateQueries({ queryKey: ["competitions-teams", cohortId] })
      }
      if (lmsProgramId) {
        void queryClient.invalidateQueries({ queryKey: ["instructor-program-wide-progress", lmsProgramId] })
      }
    },
  })

  const revokeMutation = useMutation({
    mutationFn: () => observerUnassignApi(row.assignment_id),
    onSuccess: () => {
      setConfirmRevoke(false)
      if (cohortId) {
        void queryClient.invalidateQueries({ queryKey: ["instructor-program-progress", cohortId] })
        void queryClient.invalidateQueries({ queryKey: ["competitions-teams", cohortId] })
      }
      if (lmsProgramId) {
        void queryClient.invalidateQueries({ queryKey: ["instructor-program-wide-progress", lmsProgramId] })
      }
    },
  })

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

        <div className="flex flex-col gap-1.5 w-full sm:w-56 md:w-60 shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-border/40">
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
          {(row.optional_total ?? 0) > 0 && (
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground">
              <span><span className="font-semibold text-foreground">{row.items_done}/{row.items_total}</span> required</span>
              <span className="text-border" aria-hidden="true">&bull;</span>
              <span><span className="font-semibold text-foreground">{row.optional_done}/{row.optional_total}</span> optional</span>
              <span className="text-border" aria-hidden="true">&bull;</span>
              <span><span className="font-semibold text-foreground">{row.all_done}/{row.all_total}</span> total</span>
            </div>
          )}
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

        {isObserver && (
          <div className="flex items-center gap-1.5 shrink-0 flex-wrap">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setConfirmResetProgress(true)}
              disabled={resetProgressMutation.isPending}
              title="Reset observer's individual checklist progress and quiz attempts"
              className="h-8 px-2.5 text-xs font-semibold text-muted-foreground hover:text-foreground cursor-pointer"
            >
              <RotateCcw size={12} className={resetProgressMutation.isPending ? "animate-spin mr-1" : "mr-1"} />
              Reset Progress
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setConfirmResetTeam(true)}
              disabled={resetTeamMutation.isPending}
              title="Reset observer team's deliverables and unlock team"
              className="h-8 px-2.5 text-xs font-semibold text-muted-foreground hover:text-foreground cursor-pointer"
            >
              <Users size={12} className={resetTeamMutation.isPending ? "animate-spin mr-1" : "mr-1"} />
              Reset Team
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setConfirmRevoke(true)}
              disabled={revokeMutation.isPending}
              title="Revoke observer access and remove from cohort"
              className="h-8 px-2.5 text-xs font-semibold text-red-500 hover:text-red-600 hover:bg-red-500/10 border-red-500/30 cursor-pointer"
            >
              <Trash2 size={12} className={revokeMutation.isPending ? "animate-spin mr-1" : "mr-1"} />
              Revoke Access
            </Button>
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

      {confirmResetProgress && (
        <ConfirmDialog
          title="Reset Observer Progress?"
          description={`Wipe ${row.student_name}'s individual checklist progress, course progress, and quiz attempts. Team deliverables remain untouched.`}
          confirmLabel="Reset Progress"
          destructive
          pending={resetProgressMutation.isPending}
          onCancel={() => setConfirmResetProgress(false)}
          onConfirm={() => resetProgressMutation.mutate()}
        />
      )}

      {confirmResetTeam && (
        <ConfirmDialog
          title="Reset Observer Team?"
          description={`Wipe shared deliverables and unlock the observer team for ${row.student_name}. Individual progress remains untouched.`}
          confirmLabel="Reset Team"
          destructive
          pending={resetTeamMutation.isPending}
          onCancel={() => setConfirmResetTeam(false)}
          onConfirm={() => resetTeamMutation.mutate()}
        />
      )}

      {confirmRevoke && (
        <ConfirmDialog
          title="Revoke Observer Access?"
          description={`Remove ${row.student_name} from this cohort, remove them from their observer team, and delete their quiz attempts and progress.`}
          confirmLabel="Revoke Access"
          destructive
          pending={revokeMutation.isPending}
          onCancel={() => setConfirmRevoke(false)}
          onConfirm={() => revokeMutation.mutate()}
        />
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
export function AssignmentItemRow({
  item, cohortId, assignmentId,
}: { item: LmsAssignmentItemDetail; cohortId?: string; assignmentId: string }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [showRun, setShowRun] = useState(false)
  const [showQuizReview, setShowQuizReview] = useState(false)
  const [showArcadeRun, setShowArcadeRun] = useState(false)
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
  const isArcadeGame = item.item_type === "arcade_game"

  const confirmMutation = useMutation({
    mutationFn: () => confirmChecklistItemApi(cohortId as string, assignmentId, item.item_id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["assignment-items", cohortId, assignmentId] })
      void queryClient.invalidateQueries({ queryKey: ["instructor-program-progress", cohortId] })
      if (cohortId) {
        void queryClient.invalidateQueries({ queryKey: ["competitions-team-analytics", cohortId] })
      }
    },
  })

  const resetMutation = useMutation({
    mutationFn: () => resetCohortQuizAttemptApi(cohortId as string, assignmentId, item.item_id),
    onSuccess: () => {
      setConfirmReset(false)
      void queryClient.invalidateQueries({ queryKey: ["assignment-items", cohortId, assignmentId] })
      void queryClient.invalidateQueries({ queryKey: ["cohort-quiz-review", cohortId, assignmentId, item.item_id] })
      void queryClient.invalidateQueries({ queryKey: ["instructor-program-progress", cohortId] })
      if (cohortId) {
        void queryClient.invalidateQueries({ queryKey: ["competitions-team-analytics", cohortId] })
      }
    },
  })

  const isDone = item.status === "done"
  const isAwaiting = item.status === "awaiting_confirmation"
  const isPoster = item.mission_step_key === "poster"
  const hasActions = Boolean(
    item.submitted_url || item.submitted_text || (item.submission_multi_link && item.submitted_links?.length)
    || canViewRun || canOpenConsole || (isQuiz && (isDone || cohortId)) || (isArcadeGame && isDone && cohortId) || isPoster || (isAwaiting && cohortId),
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

              {isArcadeGame && isDone && cohortId && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setShowArcadeRun((v) => !v)}
                  className="h-8 text-xs font-semibold gap-1.5 shrink-0"
                >
                  <Eye size={13} className="text-primary" />
                  {showArcadeRun ? "Hide run" : "View run"}
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

              {isAwaiting && cohortId && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={confirmMutation.isPending}
                  onClick={() => confirmMutation.mutate()}
                  className="h-8 text-xs font-bold border-amber-500/40 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 gap-1.5 shrink-0 cursor-pointer"
                >
                  <CheckCircle2 size={13} className={confirmMutation.isPending ? "animate-spin" : ""} />
                  Confirm
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

      {isArcadeGame && showArcadeRun && cohortId && (
        <div className="mt-1 border-2 border-border rounded-xl bg-card p-3 shadow-lg">
          <ArcadeRunReview cohortId={cohortId} assignmentId={assignmentId} itemId={item.item_id} />
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

  const isAllOpinion = result.total === 0 || (result.score === null && result.questions.every((q) => q.is_correct === null))

  return (
    <div className="border border-border rounded-lg bg-card p-3 flex flex-col gap-3">
      <div className="flex items-center gap-3 text-xs font-semibold text-foreground">
        <span>
          {isAllOpinion
            ? "Completed (Opinion / Ungraded)"
            : `${result.score ?? 0} / ${result.total} correct`}
        </span>
        {result.topic_breakdown && Object.keys(result.topic_breakdown).length > 0 && (
          <span className="text-muted-foreground font-normal">
            {Object.entries(result.topic_breakdown).map(([topic, { correct, total }]) => `${topic} ${correct}/${total}`).join(" · ")}
          </span>
        )}
      </div>
      <div className="flex flex-col gap-2">
        {result.questions.map((q, i) => {
          const isTextarea = q.question_type === "textarea"
          const isMultiselect = q.question_type === "multiselect" || q.question_type === "multiple_choice"
          const isOpinion = !isTextarea && (q.is_correct === null || (q.correct_index === null && (!q.correct_indices || q.correct_indices.length === 0)))

          const cardBorder = isTextarea
            ? "border-purple-500/30 bg-purple-500/5"
            : isOpinion
            ? "border-blue-500/30 bg-blue-500/5"
            : q.is_correct
            ? "border-border bg-background"
            : "border-red-500/30 bg-red-500/5"

          return (
            <div
              key={q.question_id}
              className={`rounded-lg border p-2.5 flex flex-col gap-1.5 ${cardBorder}`}
            >
              <div className="flex items-center gap-2 flex-wrap text-[11px]">
                <span className="font-mono text-muted-foreground">Q{i + 1}</span>
                <span className="px-1.5 py-0.5 rounded-full border border-border text-muted-foreground uppercase tracking-wide">{q.topic}</span>
                {isTextarea ? (
                  <span className="px-2 py-0.5 rounded-full bg-purple-500/15 text-purple-600 dark:text-purple-400 font-semibold border border-purple-500/30">
                    Open Response
                  </span>
                ) : isOpinion ? (
                  <span className="px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-600 dark:text-blue-400 font-semibold border border-blue-500/30">
                    {isMultiselect ? "Multiple Choice (Opinion)" : "Opinion"}
                  </span>
                ) : q.is_correct ? (
                  <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-semibold"><CheckCircle2 size={11} /> Correct</span>
                ) : (
                  <span className="flex items-center gap-1 text-red-600 dark:text-red-400 font-semibold"><XCircle size={11} /> Incorrect</span>
                )}
                {q.selected_index === null && (!q.selected_indices || q.selected_indices.length === 0) && !q.text_answer && (
                  <span className="text-muted-foreground italic">— left unanswered{q.timed_out ? " (timed out)" : ""}</span>
                )}
                {q.time_taken_seconds != null && (
                  <span className="flex items-center gap-1 text-muted-foreground ml-auto"><Clock size={11} /> {q.time_taken_seconds}s</span>
                )}
              </div>
              <p className="text-xs font-medium text-foreground">{q.prompt}</p>

              {isTextarea ? (
                <div className="p-2.5 rounded-md bg-muted/40 border border-border/70 text-xs">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-1">
                    Student Response:
                  </span>
                  {q.text_answer ? (
                    <p className="text-foreground whitespace-pre-wrap">{q.text_answer}</p>
                  ) : (
                    <p className="text-muted-foreground italic">Left unanswered.</p>
                  )}
                </div>
              ) : (
                <div className="flex flex-col gap-0.5">
                  {q.options.map((text, oi) => {
                    const isSelected = q.selected_indices && q.selected_indices.length > 0
                      ? q.selected_indices.includes(oi)
                      : q.selected_index === oi
                    const isCorrectOption = q.correct_indices && q.correct_indices.length > 0
                      ? q.correct_indices.includes(oi)
                      : q.correct_index === oi

                    let optionClass = "text-muted-foreground"
                    let label = null

                    if (isOpinion) {
                      if (isSelected) {
                        optionClass = "bg-blue-500/15 text-blue-700 dark:text-blue-300 font-medium border border-blue-500/30"
                        label = <span className="ml-1.5 text-[10px] font-semibold text-blue-600 dark:text-blue-400">(selected answer)</span>
                      }
                    } else {
                      if (isCorrectOption) {
                        optionClass = "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 font-medium"
                        label = <span className="ml-1.5 text-[10px]">(correct)</span>
                      } else if (isSelected) {
                        optionClass = "bg-red-500/10 text-red-700 dark:text-red-400"
                        label = <span className="ml-1.5 text-[10px]">(their answer)</span>
                      }
                    }

                    return (
                      <div
                        key={oi}
                        className={`px-2 py-1 rounded text-[11px] ${optionClass}`}
                      >
                        {text}
                        {label}
                      </div>
                    )
                  })}
                </div>
              )}

              {q.explanation && (
                <p className="text-[11px] text-muted-foreground border-t border-border/40 pt-1 mt-0.5">
                  <span className="font-semibold text-foreground/80">Explanation: </span>
                  {q.explanation}
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function ArcadeRunReview({
  cohortId,
  assignmentId,
  itemId,
}: {
  cohortId: string;
  assignmentId: string;
  itemId: string;
}) {
  const { data: attempt, isLoading, isError, error } = useQuery({
    queryKey: ["arcade-student-attempt", cohortId, assignmentId, itemId],
    queryFn: () => getStudentArcadeBestAttemptApi(cohortId, assignmentId, itemId),
  });

  if (isLoading) return <div className="p-3"><Spinner /></div>;
  if (isError) {
    return <p className="p-3 text-xs text-destructive">{errorDetail(error, "Couldn't load this run's detail")}</p>;
  }
  if (!attempt) return null;

  return (
    <div className="border border-border rounded-lg bg-card p-3 flex flex-col gap-3">
      <div className="flex items-center justify-between flex-wrap gap-2 text-xs font-semibold text-foreground border-b border-border/40 pb-2">
        <div className="flex items-center gap-2">
          <Gamepad2 size={15} className="text-primary" />
          <span className="font-bold">{attempt.game_title}</span>
          <span className="capitalize px-1.5 py-0.5 rounded text-[10px] bg-primary/10 text-primary border border-primary/20">
            {attempt.mode} mode
          </span>
          {attempt.passed ? (
            <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded">
              Passed
            </span>
          ) : (
            <span className="text-[10px] font-semibold text-amber-400 bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded">
              Attempt {attempt.attempt_no}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-muted-foreground">
          <span>Score: <strong className="text-foreground">{attempt.score}/100</strong></span>
          <span>Accuracy: <strong className="text-foreground">{attempt.accuracy}%</strong></span>
          <span>Time: <strong className="text-foreground">{attempt.elapsed_seconds}s</strong></span>
          {attempt.points_awarded > 0 && (
            <span className="text-amber-400">+{attempt.points_awarded} pts</span>
          )}
        </div>
      </div>
      {attempt.notes && attempt.notes.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
            Debrief Checklist
          </span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
            {attempt.notes.map((note, idx) => (
              <div
                key={idx}
                className={`flex items-start gap-2 p-2 rounded-md text-xs border ${
                  note.ok
                    ? "bg-emerald-500/5 border-emerald-500/20 text-emerald-400"
                    : "bg-red-500/5 border-red-500/20 text-red-400"
                }`}
              >
                {note.ok ? (
                  <CheckCircle2 size={13} className="shrink-0 text-emerald-400 mt-0.5" />
                ) : (
                  <X size={13} className="shrink-0 text-red-400 mt-0.5" />
                )}
                <span>{note.t}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
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
