import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus, X, GripVertical, BookOpen, Rocket, Link2, Upload, FileText, ClipboardCheck } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { getProgramsApi } from "@/api/sessions/programs"
import { getCohortsApi } from "@/api/sessions/cohorts"
import { listCoursesApi } from "@/api/lms_admin"
import { listMissionsAdminFullApi } from "@/api/missions_admin"
import {
  listLmsProgramsApi, createLmsProgramApi, getLmsProgramApi, updateLmsProgramApi,
  addLmsProgramItemApi, updateLmsProgramItemApi, deleteLmsProgramItemApi,
  getCohortProgramOverrideApi, addCohortOverrideItemApi, updateCohortOverrideItemApi, deleteCohortOverrideItemApi,
  type LmsProgram, type LmsProgramItem, type LmsProgramItemInput, type LmsProgramItemType,
} from "@/api/lms_admin"
import type { Program } from "@/types/sessions"

const ITEM_TYPES: { value: LmsProgramItemType; label: string; icon: typeof BookOpen }[] = [
  { value: "course", label: "Course", icon: BookOpen },
  { value: "mission_run", label: "Mission run", icon: Rocket },
  { value: "external_link", label: "Meeting / link", icon: Link2 },
  { value: "submission", label: "Submission", icon: Upload },
  { value: "article", label: "Article", icon: FileText },
  { value: "manual", label: "Manual check-off", icon: ClipboardCheck },
]

/** Replaces LmsCurriculum.tsx (2026-08-21) — the flat program_curriculum
 * course list is gone; a program's LMS view is now a full checklist
 * (LmsProgram/LmsProgramItem). Same nav slot (`/lms-authoring/curriculum`,
 * Sidebar's "Curriculum" entry, relabeled "Programs"). */
export default function LmsProgramAdmin() {
  const [programId, setProgramId] = useState("")
  const { data: programs = [], isLoading: programsLoading } = useQuery<Program[]>({
    queryKey: ["sessions-programs"], queryFn: getProgramsApi,
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="LMS Programs" subtitle="The checklist each program's students see in the LMS — courses, mission runs, submissions, and manual steps, in order." />

      <div className="max-w-sm">
        <select
          value={programId} onChange={(e) => setProgramId(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="">Select a program…</option>
          {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {programsLoading ? (
        <Spinner />
      ) : !programId ? (
        <EmptyState title="Pick a program" hint="Choose a program above to manage its checklist." />
      ) : (
        <ProgramChecklist key={programId} programId={programId} />
      )}
    </div>
  )
}

function ProgramChecklist({ programId }: { programId: string }) {
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<"template" | { cohortId: string }>("template")

  const { data: found = [], isLoading } = useQuery<LmsProgram[]>({
    queryKey: ["lms-program-for-program", programId],
    queryFn: () => listLmsProgramsApi(programId),
  })

  const [created, setCreated] = useState<LmsProgram | null>(null)
  const effective = created ?? found[0] ?? null

  const { data: cohorts = [] } = useQuery({
    queryKey: ["sessions-cohorts", programId], queryFn: () => getCohortsApi(programId),
  })

  const createMutation = useMutation({
    mutationFn: (name: string) => createLmsProgramApi({ program_id: programId, name }),
    onSuccess: (p) => setCreated(p),
  })

  const refresh = async () => {
    if (!effective) return
    const fresh = await getLmsProgramApi(effective.id)
    setCreated(fresh)
    void queryClient.invalidateQueries({ queryKey: ["lms-program-for-program", programId] })
  }

  if (isLoading) return <Spinner />

  if (!effective) {
    return <CreateChecklistPrompt onCreate={(name) => createMutation.mutate(name)} pending={createMutation.isPending} />
  }

  return (
    <div className="flex flex-col gap-5 max-w-3xl">
      <div className="flex items-center gap-1 border-b border-border">
        <button
          onClick={() => setTab("template")}
          className={`px-3 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors cursor-pointer ${
            tab === "template" ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          Program template
        </button>
        {cohorts.map((c) => (
          <button
            key={c.id}
            onClick={() => setTab({ cohortId: c.id })}
            className={`px-3 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors cursor-pointer whitespace-nowrap ${
              typeof tab === "object" && tab.cohortId === c.id ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {c.name} override
          </button>
        ))}
      </div>

      {tab === "template" ? (
        <ProgramTemplateEditor program={effective} onChanged={refresh} />
      ) : (
        <CohortOverrideEditor cohortId={tab.cohortId} />
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

function ProgramTemplateEditor({ program, onChanged }: { program: LmsProgram; onChanged: () => void }) {
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
          type="button"
          onClick={() => toggleCert.mutate(!program.certificate_required)}
          className={`w-10 h-6 rounded-full relative transition-colors cursor-pointer shrink-0 ${
            program.certificate_required ? "bg-primary" : "bg-muted"
          }`}
          aria-pressed={program.certificate_required}
        >
          <span
            className={`absolute top-1 left-1 w-4 h-4 rounded-full bg-white shadow-sm transition-transform ${
              program.certificate_required ? "translate-x-4" : "translate-x-0"
            }`}
          />
        </button>
      </div>

      <ChecklistItemsEditor
        items={program.items}
        onAdd={(data) => addLmsProgramItemApi(program.id, data).then(onChanged)}
        onUpdate={(itemId, data) => updateLmsProgramItemApi(program.id, itemId, data).then(onChanged)}
        onDelete={(itemId) => deleteLmsProgramItemApi(program.id, itemId).then(onChanged)}
      />
    </div>
  )
}

function CohortOverrideEditor({ cohortId }: { cohortId: string }) {
  const queryClient = useQueryClient()
  const { data: override, isLoading, error } = useQuery({
    queryKey: ["lms-cohort-override", cohortId],
    queryFn: () => getCohortProgramOverrideApi(cohortId),
    retry: false,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["lms-cohort-override", cohortId] })

  if (isLoading) return <Spinner />

  if (error || !override) {
    return (
      <div className="flex flex-col gap-4">
        <EmptyState
          title="This cohort has no checklist override"
          hint="Add an item below to start one — from that point on this cohort's checklist replaces the program's outright, never merged."
        />
        <ChecklistItemsEditor
          items={[]}
          onAdd={(data) => addCohortOverrideItemApi(cohortId, data).then(invalidate)}
          onUpdate={() => Promise.resolve()}
          onDelete={() => Promise.resolve()}
        />
      </div>
    )
  }

  return (
    <ChecklistItemsEditor
      items={override.items}
      onAdd={(data) => addCohortOverrideItemApi(cohortId, data).then(invalidate)}
      onUpdate={(itemId, data) => updateCohortOverrideItemApi(cohortId, itemId, data).then(invalidate)}
      onDelete={(itemId) => deleteCohortOverrideItemApi(cohortId, itemId).then(invalidate)}
    />
  )
}

function ChecklistItemsEditor({
  items, onAdd, onUpdate, onDelete,
}: {
  items: LmsProgramItem[]
  onAdd: (data: LmsProgramItemInput) => Promise<unknown>
  onUpdate: (itemId: string, data: LmsProgramItemInput) => Promise<unknown>
  onDelete: (itemId: string) => Promise<unknown>
}) {
  const [addingType, setAddingType] = useState<LmsProgramItemType | null>(null)

  return (
    <div className="flex flex-col gap-2">
      {items.length === 0 && addingType === null && <EmptyState title="No steps yet" />}

      {items.map((item) => (
        <ItemRow key={item.id} item={item} onUpdate={onUpdate} onDelete={onDelete} />
      ))}

      {addingType ? (
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
  item, onUpdate, onDelete,
}: {
  item: LmsProgramItem
  onUpdate: (itemId: string, data: LmsProgramItemInput) => Promise<unknown>
  onDelete: (itemId: string) => Promise<unknown>
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
      <button onClick={() => setEditing(true)} className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer shrink-0">
        Edit
      </button>
      <button
        onClick={() => onDelete(item.id)}
        className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors shrink-0 cursor-pointer"
      >
        <X size={14} />
      </button>
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
