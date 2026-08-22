import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Plus, X, GripVertical, BookOpen, Rocket, Link2, Upload, FileText, ClipboardCheck, ChevronDown, ChevronRight } from "lucide-react"
import { isAxiosError } from "axios"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/pages/admin/components/common"
import { useAuth } from "@/context/AuthContext"
import { getProgramsApi } from "@/api/sessions/programs"
import { getCohortsApi } from "@/api/sessions/cohorts"
import { listCoursesApi } from "@/api/lms_admin"
import { listMissionsAdminFullApi } from "@/api/missions_admin"
import {
  listLmsProgramsApi, createLmsProgramApi, getLmsProgramApi, updateLmsProgramApi,
  addLmsProgramItemApi, updateLmsProgramItemApi, deleteLmsProgramItemApi,
  getCohortProgramOverrideApi, addCohortOverrideItemApi, updateCohortOverrideItemApi, deleteCohortOverrideItemApi,
  getMyReachableProgramsApi, getProgramProgressApi, getCohortProgramProgressApi, confirmChecklistItemApi,
  getAssignmentItemsApi,
  type LmsProgram, type LmsProgramItem, type LmsProgramItemInput, type LmsProgramItemType,
  type LmsProgramRosterRow, type LmsAssignmentItemDetail,
} from "@/api/lms_admin"
import {
  myInstructorCohortsApi, instructorStepGatesApi, setInstructorStepGateApi,
  instructorStepSelectionApi, setInstructorStepSelectionApi, clearInstructorStepSelectionApi,
  instructorReviewQueueApi, instructorReviewAttemptApi, instructorOverrideAttemptApi,
  type InstructorCohort,
} from "@/api/missionsInstructor"
import { fetchMissionCatalog } from "@/api/missions"
import type { Program } from "@/types/sessions"
import type { ManagedAttempt } from "@/api/missions_manager"

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

const ITEM_TYPES: { value: LmsProgramItemType; label: string; icon: typeof BookOpen }[] = [
  { value: "course", label: "Course", icon: BookOpen },
  { value: "mission_run", label: "Mission run", icon: Rocket },
  { value: "external_link", label: "Meeting / link", icon: Link2 },
  { value: "submission", label: "Submission", icon: Upload },
  { value: "article", label: "Article", icon: FileText },
  { value: "manual", label: "Manual check-off", icon: ClipboardCheck },
]

type Scope = "program" | { cohortId: string; cohortName: string }
type SubTab = "checklist" | "missions" | "progress" | "review"
const SUBTAB_LABEL: Record<SubTab, string> = {
  checklist: "Checklist", missions: "Missions", progress: "Progress", review: "Review",
}

/** The one LMS Programs page (2026-08-22 merge) — absorbs what used to be
 * the separate Cohort Missions page. Operator's own framing: pick a
 * program, see its template + mission runs + student progress/submissions;
 * pick a cohort and the same four views switch into that cohort's own
 * scope (override checklist, gated missions, cohort-only roster/review).
 * Instructors get the same page, restricted to their own programs/cohorts
 * (`getMyReachableProgramsApi`/`myInstructorCohortsApi`, both already
 * scoped server-side the same way `/missions/instructor/*` always has
 * been) and read-only on the checklist itself — editing the template or a
 * cohort's override stays ops-only, same boundary as before this merge.
 * Replaces `LmsCurriculum.tsx` (2026-08-21) and `CohortMissions.tsx`
 * (2026-08-17, removed entirely by this change). */
export default function LmsProgramAdmin() {
  const { currentUser } = useAuth()
  const isStaff = currentUser?.role !== "instructor"

  const { data: staffPrograms = [], isLoading: staffProgramsLoading } = useQuery<Program[]>({
    queryKey: ["sessions-programs"], queryFn: getProgramsApi, enabled: isStaff,
  })
  const { data: myPrograms = [], isLoading: myProgramsLoading } = useQuery<LmsProgram[]>({
    queryKey: ["my-reachable-lms-programs"], queryFn: getMyReachableProgramsApi, enabled: !isStaff,
  })

  const [programId, setProgramId] = useState("")
  const programsLoading = isStaff ? staffProgramsLoading : myProgramsLoading
  const preloadedProgram = !isStaff ? myPrograms.find((p) => p.program_id === programId) : undefined

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Programs"
        subtitle="Each program's checklist, mission runs, and student progress — pick a cohort to see its own overridden checklist, gated missions, and submissions."
      />

      <div className="max-w-sm">
        <select
          value={programId} onChange={(e) => setProgramId(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="">Select a program…</option>
          {isStaff
            ? staffPrograms.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)
            : myPrograms.map((p) => <option key={p.id} value={p.program_id ?? ""}>{p.name}</option>)}
        </select>
      </div>

      {programsLoading ? (
        <Spinner />
      ) : !programId ? (
        <EmptyState
          title="Pick a program"
          hint={isStaff ? "Choose a program above to manage its checklist, missions, and student progress." : "Only programs attached to your own cohorts show up here."}
        />
      ) : (
        <ProgramWorkspace key={programId} programId={programId} isStaff={isStaff} preloadedProgram={preloadedProgram} />
      )}
    </div>
  )
}

function ProgramWorkspace({
  programId, isStaff, preloadedProgram,
}: { programId: string; isStaff: boolean; preloadedProgram?: LmsProgram }) {
  const queryClient = useQueryClient()
  const [scope, setScope] = useState<Scope>("program")
  const [subtab, setSubtab] = useState<SubTab>("checklist")

  const { data: found = [], isLoading } = useQuery<LmsProgram[]>({
    queryKey: ["lms-program-for-program", programId], queryFn: () => listLmsProgramsApi(programId),
    enabled: isStaff,
  })
  const [created, setCreated] = useState<LmsProgram | null>(null)
  const effective = created ?? (isStaff ? found[0] : preloadedProgram) ?? null

  const { data: staffCohorts = [] } = useQuery({
    queryKey: ["sessions-cohorts", programId], queryFn: () => getCohortsApi(programId), enabled: isStaff,
  })
  const { data: instructorCohorts = [] } = useQuery<InstructorCohort[]>({
    queryKey: ["instructor-cohorts"], queryFn: myInstructorCohortsApi, enabled: !isStaff,
  })
  const cohorts = isStaff
    ? staffCohorts.map((c) => ({ id: c.id, name: c.name }))
    : instructorCohorts.filter((c) => c.program_id === programId).map((c) => ({ id: c.id, name: c.name }))

  const createMutation = useMutation({
    mutationFn: (name: string) => createLmsProgramApi({ program_id: programId, name }),
    onSuccess: (p) => setCreated(p),
  })

  const refresh = async () => {
    if (isStaff && effective) {
      const fresh = await getLmsProgramApi(effective.id)
      setCreated(fresh)
      void queryClient.invalidateQueries({ queryKey: ["lms-program-for-program", programId] })
    } else {
      void queryClient.invalidateQueries({ queryKey: ["my-reachable-lms-programs"] })
    }
  }

  if (isStaff && isLoading) return <Spinner />

  if (!effective) {
    if (!isStaff) {
      return <EmptyState title="This program has no LMS checklist yet" hint="Ask ops to create one — instructors can't start a program's checklist from scratch." />
    }
    return <CreateChecklistPrompt onCreate={(name) => createMutation.mutate(name)} pending={createMutation.isPending} />
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-1 border-b border-border overflow-x-auto">
        <button
          onClick={() => setScope("program")}
          className={`px-3 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors cursor-pointer whitespace-nowrap ${
            scope === "program" ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          Program
        </button>
        {cohorts.map((c) => (
          <button
            key={c.id}
            onClick={() => setScope({ cohortId: c.id, cohortName: c.name })}
            className={`px-3 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors cursor-pointer whitespace-nowrap ${
              typeof scope === "object" && scope.cohortId === c.id ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {c.name}
          </button>
        ))}
      </div>

      <div className="flex gap-1 border-b border-border">
        {(["checklist", "missions", "progress", "review"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setSubtab(t)}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              subtab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
          >
            {SUBTAB_LABEL[t]}
          </button>
        ))}
      </div>

      {subtab === "checklist" && (
        scope === "program"
          ? <ProgramTemplateEditor program={effective} onChanged={refresh} readOnly={!isStaff} />
          : <CohortOverrideEditor cohortId={scope.cohortId} readOnly={!isStaff} />
      )}
      {subtab === "missions" && (
        scope === "program"
          ? <ProgramMissionsPanel items={effective.items} />
          : <CohortMissionsPanel cohortId={scope.cohortId} />
      )}
      {subtab === "progress" && (
        scope === "program"
          ? <ProgressPanel lmsProgramId={effective.id} scopeLabel="every cohort using this program" />
          : <ProgressPanel cohortId={scope.cohortId} scopeLabel={scope.cohortName} />
      )}
      {subtab === "review" && (
        scope === "program"
          ? <EmptyState title="Pick a cohort to review submissions" hint="A mission run's review queue is always cohort-scoped." />
          : <ReviewScopePanel cohortId={scope.cohortId} />
      )}
    </div>
  )
}

function CreateChecklistPrompt({ onCreate, pending }: { onCreate: (name: string) => void; pending: boolean }) {
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

function ProgramTemplateEditor({
  program, onChanged, readOnly,
}: { program: LmsProgram; onChanged: () => void; readOnly: boolean }) {
  const toggleCert = useMutation({
    mutationFn: (value: boolean) => updateLmsProgramApi(program.id, { certificate_required: value }),
    onSuccess: onChanged,
  })

  return (
    <div className="flex flex-col gap-5">
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
          <span className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${program.certificate_required ? "translate-x-5" : "translate-x-1"}`} />
        </button>
      </div>

      <ChecklistItemsEditor
        items={program.items}
        readOnly={readOnly}
        onAdd={(data) => addLmsProgramItemApi(program.id, data).then(onChanged)}
        onUpdate={(itemId, data) => updateLmsProgramItemApi(program.id, itemId, data).then(onChanged)}
        onDelete={(itemId) => deleteLmsProgramItemApi(program.id, itemId).then(onChanged)}
      />
    </div>
  )
}

function CohortOverrideEditor({ cohortId, readOnly }: { cohortId: string; readOnly: boolean }) {
  const queryClient = useQueryClient()
  const { data: override, isLoading } = useQuery({
    queryKey: ["lms-cohort-override", cohortId],
    queryFn: () => getCohortProgramOverrideApi(cohortId),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["lms-cohort-override", cohortId] })

  if (isLoading) return <Spinner />
  if (!override) return <EmptyState title="This cohort's program has no checklist yet" />

  return (
    <div className="flex flex-col gap-3">
      {override.is_inherited && (
        <div className="text-xs text-muted-foreground bg-muted/50 border border-border rounded-xl px-3 py-2">
          Showing the program's own checklist — {readOnly ? "nothing has been overridden for this cohort yet." : "edit anything below to start this cohort's own override."}
        </div>
      )}
      <ChecklistItemsEditor
        items={override.items}
        readOnly={readOnly}
        onAdd={(data) => addCohortOverrideItemApi(cohortId, data).then(invalidate)}
        onUpdate={(itemId, data) => updateCohortOverrideItemApi(cohortId, itemId, data).then(invalidate)}
        onDelete={(itemId) => deleteCohortOverrideItemApi(cohortId, itemId).then(invalidate)}
      />
    </div>
  )
}

function ChecklistItemsEditor({
  items, onAdd, onUpdate, onDelete, readOnly,
}: {
  items: LmsProgramItem[]
  onAdd: (data: LmsProgramItemInput) => Promise<unknown>
  onUpdate: (itemId: string, data: LmsProgramItemInput) => Promise<unknown>
  onDelete: (itemId: string) => Promise<unknown>
  readOnly: boolean
}) {
  const [addingType, setAddingType] = useState<LmsProgramItemType | null>(null)

  return (
    <div className="flex flex-col gap-2">
      {items.length === 0 && addingType === null && <EmptyState title="No steps yet" />}

      {items.map((item) => (
        <ItemRow key={item.id} item={item} onUpdate={onUpdate} onDelete={onDelete} readOnly={readOnly} />
      ))}

      {readOnly ? null : addingType ? (
        <ItemForm
          itemType={addingType}
          onCancel={() => setAddingType(null)}
          onSave={async (data) => { await onAdd(data); setAddingType(null) }}
        />
      ) : (
        <div className="flex flex-col gap-2 pt-2">
          <div className="text-xs font-semibold text-muted-foreground">Add a step</div>
          <div className="flex flex-wrap gap-2">
            {ITEM_TYPES.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                onClick={() => setAddingType(value)}
                className="flex items-center gap-1.5 h-8 px-3 rounded-full border border-dashed border-border text-xs font-medium text-foreground hover:border-primary/50 hover:bg-primary/5 transition-colors cursor-pointer"
              >
                <Icon size={13} /> {label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const ITEM_TYPE_META: Record<LmsProgramItemType, { label: string; icon: typeof BookOpen }> = Object.fromEntries(
  ITEM_TYPES.map((t) => [t.value, { label: t.label, icon: t.icon }]),
) as Record<LmsProgramItemType, { label: string; icon: typeof BookOpen }>

function ItemRow({
  item, onUpdate, onDelete, readOnly,
}: {
  item: LmsProgramItem
  onUpdate: (itemId: string, data: LmsProgramItemInput) => Promise<unknown>
  onDelete: (itemId: string) => Promise<unknown>
  readOnly: boolean
}) {
  const [editing, setEditing] = useState(false)
  const meta = ITEM_TYPE_META[item.item_type]
  const Icon = meta.icon

  if (editing) {
    return (
      <ItemForm
        itemType={item.item_type}
        initial={item}
        onCancel={() => setEditing(false)}
        onSave={async (data) => { await onUpdate(item.id, data); setEditing(false) }}
      />
    )
  }

  return (
    <div className="flex items-center gap-3 p-3 bg-card border border-border rounded-xl">
      <GripVertical size={14} className="text-muted-foreground shrink-0" />
      <span className="text-xs font-semibold text-muted-foreground w-5 text-center shrink-0">{item.position}</span>
      <div className="w-7 h-7 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0 text-primary">
        <Icon size={13} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-sm font-medium truncate">{item.title}</span>
          {item.optional && <span className="text-[10px] font-semibold uppercase text-muted-foreground border border-border rounded px-1.5 py-0.5">optional</span>}
          {item.requires_confirmation && <span className="text-[10px] font-semibold uppercase text-primary border border-primary/30 rounded px-1.5 py-0.5">needs confirmation</span>}
        </div>
        <div className="text-xs text-muted-foreground">{meta.label}</div>
      </div>
      {!readOnly && (
        <>
          <button onClick={() => setEditing(true)} className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer shrink-0">
            Edit
          </button>
          <button
            onClick={() => onDelete(item.id)}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors shrink-0 cursor-pointer"
          >
            <X size={14} />
          </button>
        </>
      )}
    </div>
  )
}

function ItemForm({
  itemType, initial, onCancel, onSave,
}: {
  itemType: LmsProgramItemType
  initial?: LmsProgramItem
  onCancel: () => void
  onSave: (data: LmsProgramItemInput) => Promise<void>
}) {
  const [title, setTitle] = useState(initial?.title ?? "")
  const [description, setDescription] = useState(initial?.description ?? "")
  const [optional, setOptional] = useState(initial?.optional ?? false)
  const [requiresConfirmation, setRequiresConfirmation] = useState(initial?.requires_confirmation ?? false)
  const [courseId, setCourseId] = useState(initial?.course_id ?? "")
  const [missionId, setMissionId] = useState(initial?.mission_id ?? "")
  const [variantId, setVariantId] = useState(initial?.variant_id ?? "")
  const [externalUrl, setExternalUrl] = useState(initial?.external_url ?? "")
  const [submissionPrompt, setSubmissionPrompt] = useState(initial?.submission_prompt ?? "")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  const { data: courses = [] } = useQuery({ queryKey: ["lms-admin-courses"], queryFn: listCoursesApi, enabled: itemType === "course" })
  const { data: missions = [] } = useQuery({ queryKey: ["missions-admin-full"], queryFn: listMissionsAdminFullApi, enabled: itemType === "mission_run" })
  const selectedMission = missions.find((m) => m.id === missionId)

  const save = async () => {
    setError("")
    if (!title.trim()) { setError("Title is required"); return }
    if (itemType === "course" && !courseId) { setError("Pick a course"); return }
    if (itemType === "mission_run" && !missionId) { setError("Pick a mission"); return }
    if ((itemType === "external_link" || itemType === "article") && !externalUrl.trim()) { setError("A link is required"); return }
    if (itemType === "submission" && !externalUrl.trim() && !submissionPrompt.trim()) { setError("Add a link or a submission prompt"); return }

    setSaving(true)
    try {
      await onSave({
        item_type: itemType,
        title: title.trim(),
        description: description.trim() || null,
        optional,
        requires_confirmation: requiresConfirmation,
        course_id: itemType === "course" ? courseId : null,
        mission_id: itemType === "mission_run" ? missionId : null,
        variant_id: itemType === "mission_run" ? (variantId || null) : null,
        external_url: (itemType === "external_link" || itemType === "article" || itemType === "submission") ? (externalUrl.trim() || null) : null,
        submission_prompt: itemType === "submission" ? (submissionPrompt.trim() || null) : null,
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
      <div className="text-xs font-semibold text-primary">{ITEM_TYPE_META[itemType].label}</div>
      <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" className={inputCls} />
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
        </>
      )}

      {(itemType === "external_link" || itemType === "article") && (
        <input value={externalUrl} onChange={(e) => setExternalUrl(e.target.value)} placeholder="https://…" className={inputCls} />
      )}

      {itemType === "submission" && (
        <>
          <input value={externalUrl} onChange={(e) => setExternalUrl(e.target.value)} placeholder="Reference link (optional)" className={inputCls} />
          <textarea
            value={submissionPrompt} onChange={(e) => setSubmissionPrompt(e.target.value)} placeholder="What should the student submit back?"
            rows={2} className={`${inputCls} h-auto py-2 resize-none`}
          />
        </>
      )}

      <div className="flex items-center gap-4 pt-1">
        <label className="flex items-center gap-1.5 text-xs text-foreground cursor-pointer">
          <input type="checkbox" checked={optional} onChange={(e) => setOptional(e.target.checked)} />
          Optional
        </label>
        <label className="flex items-center gap-1.5 text-xs text-foreground cursor-pointer">
          <input type="checkbox" checked={requiresConfirmation} onChange={(e) => setRequiresConfirmation(e.target.checked)} />
          Needs instructor/ops confirmation
        </label>
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

// ── Missions ─────────────────────────────────────────────────────────────
// "a tab to create special mission runs for the program and add them to the
// program checklist" (operator, 2026-08-22) — the mission_run items already
// live in the checklist (Checklist tab handles authoring them); this tab is
// where they're surfaced on their own, and where a cohort's gates/step
// selection for each one lives.

function ProgramMissionsPanel({ items }: { items: LmsProgramItem[] }) {
  const missionItems = items.filter((i) => i.item_type === "mission_run")
  if (missionItems.length === 0) {
    return <EmptyState title="No mission runs on this checklist yet" hint='Add one from the Checklist tab ("Mission run").' />
  }
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">
        Every mission run on this program's checklist. Pick a cohort to gate steps or choose which build steps apply
        for that cohort's run — gating is always cohort-specific.
      </p>
      {missionItems.map((item) => (
        <div key={item.id} className="flex items-center gap-3 p-3 bg-card border border-border rounded-xl">
          <Rocket size={16} className="text-primary shrink-0" />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium truncate">{item.title}</div>
            {item.description && <div className="text-xs text-muted-foreground truncate">{item.description}</div>}
          </div>
        </div>
      ))}
    </div>
  )
}

function CohortMissionsPanel({ cohortId }: { cohortId: string }) {
  const { data: override, isLoading } = useQuery({
    queryKey: ["lms-cohort-override", cohortId], queryFn: () => getCohortProgramOverrideApi(cohortId),
  })
  const [expanded, setExpanded] = useState<string | null>(null)

  if (isLoading) return <Spinner />
  const missionItems = (override?.items ?? []).filter((i) => i.item_type === "mission_run" && i.mission_id)
  if (missionItems.length === 0) {
    return <EmptyState title="No mission runs on this cohort's checklist" />
  }

  return (
    <div className="flex flex-col gap-2">
      {missionItems.map((item) => (
        <div key={item.id} className="border border-border rounded-xl overflow-hidden">
          <button
            onClick={() => setExpanded(expanded === item.id ? null : item.id)}
            className="w-full flex items-center gap-3 p-3 bg-card hover:bg-muted/40 transition-colors cursor-pointer text-left"
          >
            {expanded === item.id ? <ChevronDown size={14} className="shrink-0 text-muted-foreground" /> : <ChevronRight size={14} className="shrink-0 text-muted-foreground" />}
            <Rocket size={16} className="text-primary shrink-0" />
            <span className="text-sm font-medium truncate">{item.title}</span>
          </button>
          {expanded === item.id && item.mission_id && (
            <div className="p-3 border-t border-border flex flex-col gap-4 bg-background">
              <div>
                <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Steps included</div>
                <StepsTab cohortId={cohortId} missionId={item.mission_id} />
              </div>
              <div>
                <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Gates</div>
                <GatesTab cohortId={cohortId} missionId={item.mission_id} />
              </div>
            </div>
          )}
        </div>
      ))}
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

function ProgressPanel({
  cohortId, lmsProgramId, scopeLabel,
}: { cohortId?: string; lmsProgramId?: string; scopeLabel: string }) {
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

  if (isLoading) return <Spinner />
  if (!rows || rows.length === 0) {
    return <EmptyState title="No students assigned this checklist yet" hint={`Showing ${scopeLabel}.`} />
  }

  return (
    <div className="flex flex-col gap-2">
      {rows.map((row) => (
        <ProgressRow
          key={row.assignment_id} row={row} cohortId={cohortId}
          onConfirm={(itemId) => cohortId && confirmMutation.mutate({ assignmentCohortId: cohortId, assignmentId: row.assignment_id, itemId })}
          confirmPending={confirmMutation.isPending}
        />
      ))}
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

  return (
    <div className="border border-border rounded-xl overflow-hidden">
      <div className="flex items-center gap-4 p-3 bg-card">
        <button
          onClick={() => cohortId && setOpen((v) => !v)}
          className="shrink-0 text-muted-foreground"
          disabled={!cohortId}
          title={cohortId ? "Show item detail" : "Pick a cohort to see item detail"}
        >
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <button
          onClick={() => void navigate({ to: `/lms-authoring/students/${row.user_id}` })}
          className="min-w-0 flex-1 text-left hover:opacity-80 transition-opacity cursor-pointer"
        >
          <div className="text-sm font-medium text-foreground truncate underline decoration-dotted underline-offset-2">{row.student_name}</div>
          <div className="text-xs text-muted-foreground truncate">{row.name}</div>
        </button>
        <div className="flex flex-col gap-1 w-40 shrink-0">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{row.items_done}/{row.items_total}</span>
            <span>{row.pct}%</span>
          </div>
          <div className="h-1.5 rounded-full bg-muted relative overflow-hidden">
            <div className={`absolute inset-y-0 left-0 rounded-full ${row.pct === 100 ? "bg-emerald-500" : "bg-primary"}`} style={{ width: `${row.pct}%` }} />
          </div>
        </div>
        {row.certificate_required && (
          <span className={`shrink-0 text-[10px] font-semibold uppercase tracking-wide rounded-md px-2 py-1 ${
            row.certificate_earned ? "bg-emerald-500/10 text-emerald-600" : "bg-muted text-muted-foreground"}`}
          >
            {row.certificate_earned ? "Certified" : "Not certified"}
          </span>
        )}
        {row.pending_confirmations.length > 0 && (
          <div className="flex flex-wrap gap-1.5 shrink-0 max-w-[220px] justify-end">
            {row.pending_confirmations.map((p) => (
              <Button
                key={p.item_id} size="sm" variant="outline"
                disabled={confirmPending || !cohortId}
                onClick={() => onConfirm(p.item_id)}
                title={p.title}
              >
                Confirm: {p.title.length > 18 ? `${p.title.slice(0, 18)}…` : p.title}
              </Button>
            ))}
          </div>
        )}
      </div>
      {open && (
        <div className="p-3 border-t border-border bg-background flex flex-col gap-1.5">
          {itemsLoading ? <Spinner /> : (items ?? []).map((item) => (
            <div key={item.item_id} className="flex items-center gap-3 text-xs">
              <span className={`w-2 h-2 rounded-full shrink-0 ${item.status === "done" ? "bg-emerald-500" : item.status === "awaiting_confirmation" ? "bg-amber-500" : "bg-muted-foreground/30"}`} />
              <span className="flex-1 text-foreground truncate">{item.title}</span>
              <span className="text-muted-foreground shrink-0">{item.status.replace("_", " ")}</span>
              {item.submitted_url && (
                <a href={item.submitted_url} target="_blank" rel="noreferrer" className="text-primary underline shrink-0">
                  submission
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Review ───────────────────────────────────────────────────────────────
// Cohort-scoped only. Adds a mission picker (a program checklist can list
// several missions) on top of what `CohortMissions.tsx` used to do alone.

function ReviewScopePanel({ cohortId }: { cohortId: string }) {
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
  const [score, setScore] = useState("")
  const [notes, setNotes] = useState("")
  const [error, setError] = useState("")
  const [overriding, setOverriding] = useState(false)
  const [overrideReason, setOverrideReason] = useState("")

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["instructor-review-queue", cohortId, missionId] })

  const reviewMutation = useMutation({
    mutationFn: (passed: boolean) =>
      instructorReviewAttemptApi(attempt.id, { passed, score: score ? Number(score) : null, review_comment: notes || null }),
    onSuccess: () => { setError(""); invalidate() },
    onError: (e) => setError(errorDetail(e, "Couldn't submit this review")),
  })

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
      <div className="flex gap-2">
        <input
          value={score} onChange={(e) => setScore(e.target.value)} placeholder="Score (0-100)"
          className="h-8 w-28 px-2 border border-border bg-card text-foreground rounded-lg text-xs focus:outline-none focus:border-primary"
        />
        <input
          value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes (optional)"
          className="h-8 flex-1 px-2 border border-border bg-card text-foreground rounded-lg text-xs focus:outline-none focus:border-primary"
        />
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => reviewMutation.mutate(true)} disabled={reviewMutation.isPending}>Pass</Button>
        <Button size="sm" variant="destructive" onClick={() => reviewMutation.mutate(false)} disabled={reviewMutation.isPending}>Fail</Button>
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
