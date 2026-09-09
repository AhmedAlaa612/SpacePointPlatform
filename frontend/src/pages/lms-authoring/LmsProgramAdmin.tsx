import { Fragment, useEffect, useRef, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Plus, X, GripVertical, BookOpen, Rocket, Link2, Upload, Users, FileText, ClipboardCheck, ChevronDown, ChevronRight, ImagePlus, Calendar, HelpCircle, RotateCcw, Clock, CheckCircle2, XCircle, Award, Circle, ExternalLink, Eye, Play } from "lucide-react"
import { isAxiosError } from "axios"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { VideoPlayer } from "@/components/video/VideoPlayer"
import { ConfirmDialog } from "@/pages/admin/components/common"
import { useAuth } from "@/context/AuthContext"
import { getProgramsApi } from "@/api/sessions/programs"
import { getCohortsApi, getSessionsApi } from "@/api/sessions/cohorts"
import { listCoursesApi } from "@/api/lms_admin"
import { listMissionsAdminFullApi } from "@/api/missions_admin"
import {
  listLmsProgramsApi, createLmsProgramApi, getLmsProgramApi, updateLmsProgramApi, uploadLmsProgramImageApi,
  addLmsProgramItemApi, updateLmsProgramItemApi, deleteLmsProgramItemApi, reorderLmsProgramItemsApi,
  getCohortProgramOverrideApi, addCohortOverrideItemApi, updateCohortOverrideItemApi, deleteCohortOverrideItemApi,
  reorderCohortOverrideItemsApi,
  getCohortProgramOverrideInstructorApi, addCohortOverrideItemInstructorApi,
  updateCohortOverrideItemInstructorApi, deleteCohortOverrideItemInstructorApi,
  getMyReachableProgramsApi, getProgramProgressApi, getCohortProgramProgressApi, confirmChecklistItemApi,
  getAssignmentItemsApi, resyncCohortProgramAssignmentsApi,
  uploadLmsProgramItemPdfApi, deleteLmsProgramItemPdfApi,
  uploadLmsProgramItemGuidelineVideoApi, deleteLmsProgramItemGuidelineVideoApi,
  getLmsProgramItemGuidelineVideoUrlApi,
  MISSION_STEP_KEYS,
  type LmsProgram, type LmsProgramItem, type LmsProgramItemInput, type LmsProgramItemType,
  type LmsProgramRosterRow, type LmsAssignmentItemDetail,
} from "@/api/lms_admin"
import {
  myInstructorCohortsApi, instructorStepGatesApi, setInstructorStepGateApi,
  instructorStepSelectionApi, setInstructorStepSelectionApi, clearInstructorStepSelectionApi,
  instructorReviewQueueApi, instructorOverrideAttemptApi,
  type InstructorCohort,
} from "@/api/missionsInstructor"
import { fetchMissionCatalog } from "@/api/missions"
import { getInstructorCohortQuizReviewApi, listCohortQuizTemplatesApi, resetCohortQuizAttemptApi } from "@/api/cohort_quiz"
import { DesignRunDetail } from "@/pages/lms-authoring/components/DesignRunDetail"
import type { Program } from "@/types/sessions"
import type { ManagedAttempt } from "@/api/missions_manager"
import { ensureAbsoluteUrl } from "@/lib/utils"
import { useToast } from "@/components/ui/toast"

/** Authoring-side preview for an uploaded guideline video — the same
 * resolve-fresh-on-open posture the Library/training players already use.
 * Polls while the upload is still transcoding, since a facilitator can open
 * this right after uploading, well before the encode finishes. */
function GuidelineVideoPreview({ itemId, title }: { itemId: string; title: string }) {
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

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

/** Stored deadline is a UTC ISO string — render it into a `datetime-local`
 * input's local-time value, same conversion direction TeacherPortal's own
 * `datetime-local` field uses in reverse (`new Date(value).toISOString()`
 * going back out on save). */
function toDatetimeLocalValue(iso: string | null | undefined): string {
  if (!iso) return ""
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ""
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Roadmap-board-safe round-trip of an existing item back into the PATCH
 * shape — the endpoint replaces every field from `model_dump()`, so a
 * partial `{ gated: true }` body would blow away the rest of the row
 * (course_id, guideline fields, etc.) back to their schema defaults. Used
 * by the "Gate everything in order" bulk action, which only means to
 * flip one field per item. */
function itemToInput(item: LmsProgramItem): LmsProgramItemInput {
  return {
    item_type: item.item_type, title: item.title, description: item.description,
    optional: item.optional, requires_confirmation: item.requires_confirmation, scope: item.scope,
    course_id: item.course_id, mission_id: item.mission_id, variant_id: item.variant_id,
    external_url: item.external_url, submission_prompt: item.submission_prompt,
    deadline_at: item.deadline_at, session_date: item.session_date, session_starts_at: item.session_starts_at,
    session_location: item.session_location, session_meeting_url: item.session_meeting_url,
    cohort_quiz_template_id: item.cohort_quiz_template_id,
    mission_step_key: item.mission_step_key, gated: item.gated, guideline_kind: item.guideline_kind,
    guideline_url: item.guideline_url, checkpoint_label: item.checkpoint_label,
  }
}

const ITEM_TYPES: { value: LmsProgramItemType; label: string; icon: typeof BookOpen }[] = [
  { value: "course", label: "Course", icon: BookOpen },
  { value: "mission_run", label: "Mission run", icon: Rocket },
  { value: "external_link", label: "Link", icon: Link2 },
  { value: "submission", label: "Submission", icon: Upload },
  { value: "pdf", label: "PDF", icon: FileText },
  { value: "manual", label: "Manual check-off", icon: ClipboardCheck },
  { value: "session", label: "Session", icon: Calendar },
  { value: "quiz", label: "Quiz", icon: HelpCircle },
]

// Mirrors the server-side rule in services/lms/program.py: only a
// link-only deliverable (nothing auto-tracked like course/mission_run)
// can be shared as one team-wide submission.
const TEAM_SCOPABLE_TYPES = new Set<LmsProgramItemType>(["submission", "external_link", "manual"])

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

  // Instructors don't get a "Program" scope at all — they land straight on
  // their own cohort (operator ask, 2026-08-23), never the master template.
  useEffect(() => {
    if (!isStaff && scope === "program" && cohorts.length > 0) {
      setScope({ cohortId: cohorts[0].id, cohortName: cohorts[0].name })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStaff, scope, cohorts.length])

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
        {isStaff && (
          <button
            onClick={() => setScope("program")}
            className={`px-3 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors cursor-pointer whitespace-nowrap ${
              scope === "program" ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            Program
          </button>
        )}
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
          : <CohortOverrideEditor cohortId={scope.cohortId} isStaff={isStaff} readOnly={!isStaff} />
      )}
      {subtab === "missions" && (
        scope === "program"
          ? <ProgramMissionsPanel program={effective} onChanged={refresh} readOnly={!isStaff} />
          : <CohortMissionsPanel cohortId={scope.cohortId} isStaff={isStaff} />
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
  const [imageError, setImageError] = useState("")
  const fileInputRef = useRef<HTMLInputElement>(null)
  const imageMutation = useMutation({
    mutationFn: (file: File) => uploadLmsProgramImageApi(program.id, file),
    onSuccess: () => { setImageError(""); onChanged() },
    onError: (e: unknown) => setImageError(errorDetail(e, "Failed to upload image")),
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
          ref={fileInputRef} type="file" accept="image/*" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) imageMutation.mutate(f) }}
        />
        <div className="flex flex-col gap-1 pt-1">
          <div className="text-sm font-medium">Checklist header image</div>
          <div className="text-xs text-muted-foreground">Shown behind the title on the student checklist page</div>
          {imageError && <p className="text-xs text-red-500">{imageError}</p>}
        </div>
      </div>

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

function CohortOverrideEditor({ cohortId, isStaff, readOnly }: { cohortId: string; isStaff: boolean; readOnly: boolean }) {
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

  if (isLoading) return <Spinner />
  if (!override) return <EmptyState title="This cohort's program has no checklist yet" />

  return (
    <div className="flex flex-col gap-3">
      {override.is_inherited && (
        <div className="text-xs text-muted-foreground bg-muted/50 border border-border rounded-xl px-3 py-2">
          Showing the program's own checklist — {readOnly ? "nothing has been overridden for this cohort yet." : "edit anything below to start this cohort's own override."}
        </div>
      )}
      {isStaff && !readOnly && (
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

function ChecklistItemsEditor({
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
  const displayItems = order
    ? order.map((id) => items.find((i) => i.id === id)).filter((i): i is LmsProgramItem => !!i)
    : items

  const dropOnto = (targetId: string) => {
    if (!dragId || dragId === targetId) { setDragId(null); return }
    const ids = displayItems.map((i) => i.id)
    const from = ids.indexOf(dragId)
    const to = ids.indexOf(targetId)
    setDragId(null)
    if (from === -1 || to === -1) return
    ids.splice(to, 0, ids.splice(from, 1)[0])
    setOrder(ids)
    void onReorder(ids).then(() => setOrder(null)).catch(() => setOrder(null))
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

      {displayItems.map((item) => (
        <ItemRow
          key={item.id} item={item} onUpdate={onUpdate} onDelete={onDelete}
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

const ITEM_TYPE_META: Record<LmsProgramItemType, { label: string; icon: typeof BookOpen }> = Object.fromEntries(
  ITEM_TYPES.map((t) => [t.value, { label: t.label, icon: t.icon }]),
) as Record<LmsProgramItemType, { label: string; icon: typeof BookOpen }>

function ItemRow({
  item, onUpdate, onDelete, onUploadPdf, onRemovePdf, onUploadGuidelineVideo, onRemoveGuidelineVideo,
  onPreviewGuidelineVideo,
  readOnly, cohortId, checkpointLabels,
  draggable, isDragging, onDragStartRow, onDropRow, onDragEndRow,
}: {
  item: LmsProgramItem
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
      className={`flex items-center gap-3 p-3 bg-card border rounded-xl transition-colors ${
        isDragging ? "opacity-40 border-primary" : "border-border"
      } ${draggable ? "cursor-grab active:cursor-grabbing" : ""}`}
    >
      <GripVertical size={14} className="text-muted-foreground shrink-0" />
      <span className="text-xs font-semibold text-muted-foreground w-5 text-center shrink-0">{item.position}</span>
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
      {!readOnly && (
        <>
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
                className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer shrink-0 disabled:opacity-50"
              >
                {pdfBusy ? "Uploading…" : item.has_pdf ? "Replace PDF" : "Upload PDF"}
              </button>
              {item.has_pdf && (
                <button
                  onClick={async () => { setPdfBusy(true); try { await onRemovePdf?.(item.id) } finally { setPdfBusy(false) } }}
                  disabled={pdfBusy}
                  className="text-xs font-medium text-muted-foreground hover:text-red-600 transition-colors cursor-pointer shrink-0 disabled:opacity-50"
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
                className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer shrink-0 disabled:opacity-50"
              >
                {videoBusy ? "Uploading…" : item.guideline_video_uploaded ? "Replace video" : "Upload video"}
              </button>
              {item.guideline_video_uploaded && (
                <>
                  <button
                    onClick={() => onPreviewGuidelineVideo?.()}
                    className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer shrink-0"
                  >
                    Preview
                  </button>
                  <button
                    onClick={async () => { setVideoBusy(true); try { await onRemoveGuidelineVideo?.(item.id) } finally { setVideoBusy(false) } }}
                    disabled={videoBusy}
                    className="text-xs font-medium text-muted-foreground hover:text-red-600 transition-colors cursor-pointer shrink-0 disabled:opacity-50"
                  >
                    Remove video
                  </button>
                </>
              )}
            </>
          )}
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

// The Roadmap board tile a design mission's phase picker offers — the
// client's own instruction: "data, link, and cost will not be used for
// this competition." MISSION_STEP_KEYS (api/lms_admin.ts) keeps the full
// backend vocabulary; this is just what the picker shows.
const PHASE_PICKER_KEYS = MISSION_STEP_KEYS.filter((s) => !["data_budget", "link_budget", "cost_budget"].includes(s.value))

function ItemForm({
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

// ── Missions ─────────────────────────────────────────────────────────────
// "a tab to create special mission runs for the program and add them to the
// program checklist" (operator, 2026-08-22) — mission_run items are still
// `LmsProgramItem` rows under the hood (Checklist tab shows the same items
// mixed in with everything else), but this tab is the dedicated place to
// add/edit them and is where a cohort's gates/step selection for each one
// lives, so authoring a mission run never requires the flat item list.

function AddMissionRunButton({ onSave }: { onSave: (data: LmsProgramItemInput) => Promise<void> }) {
  const [adding, setAdding] = useState(false)
  if (adding) {
    return <ItemForm itemType="mission_run" onCancel={() => setAdding(false)} onSave={async (data) => { await onSave(data); setAdding(false) }} />
  }
  return (
    <button
      onClick={() => setAdding(true)}
      className="flex items-center gap-1.5 h-8 px-3 rounded-full border border-dashed border-border text-xs font-medium text-foreground hover:border-primary/50 hover:bg-primary/5 transition-colors cursor-pointer w-fit"
    >
      <Plus size={13} /> Add mission run
    </button>
  )
}

function ProgramMissionsPanel({
  program, onChanged, readOnly,
}: { program: LmsProgram; onChanged: () => void; readOnly: boolean }) {
  const missionItems = program.items.filter((i) => i.item_type === "mission_run")
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">
        Every mission run on this program's checklist. Pick a cohort to gate steps or choose which build steps apply
        for that cohort's run — gating is always cohort-specific.
      </p>
      {missionItems.length === 0 && <EmptyState title="No mission runs on this checklist yet" />}
      {missionItems.map((item) => (
        <ItemRow
          key={item.id}
          item={item}
          readOnly={readOnly}
          onUpdate={(itemId, data) => updateLmsProgramItemApi(program.id, itemId, data).then(onChanged)}
          onDelete={(itemId) => deleteLmsProgramItemApi(program.id, itemId).then(onChanged)}
        />
      ))}
      {!readOnly && <AddMissionRunButton onSave={(data) => addLmsProgramItemApi(program.id, data).then(onChanged)} />}
    </div>
  )
}

function CohortMissionsPanel({ cohortId, isStaff }: { cohortId: string; isStaff: boolean }) {
  const queryClient = useQueryClient()
  const { data: override, isLoading } = useQuery({
    queryKey: ["lms-cohort-override", cohortId],
    queryFn: () => (isStaff ? getCohortProgramOverrideApi(cohortId) : getCohortProgramOverrideInstructorApi(cohortId)),
  })
  const [expanded, setExpanded] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["lms-cohort-override", cohortId] })
  // Every item here is already filtered to mission_run, and the backend's
  // own instructor-scope check restricts writes to exactly that item_type —
  // so anyone who can see this tab at all can edit every row on it, no
  // extra client-side readOnly gate needed.
  const updateItem = isStaff ? updateCohortOverrideItemApi : updateCohortOverrideItemInstructorApi
  const deleteItem = isStaff ? deleteCohortOverrideItemApi : deleteCohortOverrideItemInstructorApi
  const addItem = isStaff ? addCohortOverrideItemApi : addCohortOverrideItemInstructorApi

  if (isLoading) return <Spinner />
  const missionItems = (override?.items ?? []).filter((i) => i.item_type === "mission_run")

  return (
    <div className="flex flex-col gap-2">
      {missionItems.length === 0 && <EmptyState title="No mission runs on this cohort's checklist" />}
      {missionItems.map((item) => (
        editingId === item.id ? (
          <ItemForm
            key={item.id}
            itemType="mission_run"
            initial={item}
            onCancel={() => setEditingId(null)}
            onSave={async (data) => { await updateItem(cohortId, item.id, data).then(invalidate); setEditingId(null) }}
          />
        ) : (
          <div key={item.id} className="border border-border rounded-xl overflow-hidden">
            <div className="flex items-center gap-1 pr-2">
              <button
                onClick={() => setExpanded(expanded === item.id ? null : item.id)}
                className="flex-1 flex items-center gap-3 p-3 hover:bg-muted/40 transition-colors cursor-pointer text-left"
              >
                {expanded === item.id ? <ChevronDown size={14} className="shrink-0 text-muted-foreground" /> : <ChevronRight size={14} className="shrink-0 text-muted-foreground" />}
                <Rocket size={16} className="text-primary shrink-0" />
                <span className="text-sm font-medium truncate">{item.title}</span>
                {/* Two mission_run items can legitimately point at the same
                    mission_id while tracking different phases of it (D1) —
                    without this badge they're indistinguishable here, since
                    "Steps included"/Gates below are shared per (cohort,
                    mission) config, not per-item. Same label lookup ItemRow
                    already uses on the Checklist tab. */}
                {item.mission_step_key && (
                  <span className="text-[10px] font-semibold uppercase text-muted-foreground border border-border rounded px-1.5 py-0.5 shrink-0">
                    {MISSION_STEP_KEYS.find((s) => s.value === item.mission_step_key)?.label ?? item.mission_step_key}
                  </span>
                )}
              </button>
              <button onClick={() => setEditingId(item.id)} className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer shrink-0">
                Edit
              </button>
              <button
                onClick={() => void deleteItem(cohortId, item.id).then(invalidate)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors shrink-0 cursor-pointer"
              >
                <X size={14} />
              </button>
            </div>
            {expanded === item.id && item.mission_id && item.mission_kind === "design" && (
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
            {expanded === item.id && item.mission_id && item.mission_kind !== "design" && (
              <div className="p-3 border-t border-border text-xs text-muted-foreground bg-background">
                This is a {item.mission_kind ?? "non-design"} mission — it has no build steps or gates to configure,
                those only apply to Design missions.
              </div>
            )}
            {expanded === item.id && !item.mission_id && (
              <div className="p-3 border-t border-border text-xs text-muted-foreground bg-background">
                Save a mission for this run before gates/steps can be configured.
              </div>
            )}
          </div>
        )
      ))}
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

  // Get student initials for avatar placeholder
  const initials = (row.student_name || "S").split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2)

  return (
    <div className="border-2 border-border/80 rounded-2xl bg-card shadow-md transition-all hover:border-primary/40 overflow-hidden">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4 p-4 sm:p-5">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <button
            onClick={() => cohortId && setOpen((v) => !v)}
            className="p-2 rounded-xl bg-muted/60 hover:bg-muted text-muted-foreground transition-colors shrink-0 cursor-pointer disabled:opacity-40"
            disabled={!cohortId}
            title={cohortId ? "Show item detail" : "Pick a cohort to see item detail"}
          >
            {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </button>

          <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 text-primary font-bold flex items-center justify-center text-sm shrink-0">
            {initials}
          </div>

          <button
            onClick={() => void navigate({ to: `/lms-authoring/students/${row.user_id}` })}
            className="min-w-0 flex-1 text-left group cursor-pointer"
          >
            <div className="text-base font-bold text-foreground group-hover:text-primary transition-colors truncate">
              {row.student_name}
            </div>
            <div className="text-xs font-medium text-muted-foreground truncate flex items-center gap-1.5 mt-0.5">
              <BookOpen size={12} className="shrink-0 text-muted-foreground/70" />
              <span>{row.name}</span>
            </div>
          </button>

          {row.certificate_required && (
            <span className={`shrink-0 text-xs font-bold px-2.5 py-1 rounded-xl flex items-center gap-1.5 ${
              row.certificate_earned
                ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                : "bg-muted/80 text-muted-foreground border border-border/50"
            }`}>
              {row.certificate_earned ? (
                <>
                  <CheckCircle2 size={13} className="text-emerald-500" />
                  <span className="hidden xs:inline">Certified</span>
                </>
              ) : (
                <>
                  <Award size={13} className="text-muted-foreground/60" />
                  <span className="hidden xs:inline">Not certified</span>
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
  const [showRun, setShowRun] = useState(false)
  const [showQuizReview, setShowQuizReview] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const canViewRun = item.item_type === "mission_run" && !!item.mission_attempt_id
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

  return (
    <div className="flex flex-col gap-2">
      <div className="p-3 sm:p-3.5 rounded-xl bg-card border border-border/60 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:border-border transition-all">
        <div className="flex items-center gap-3 min-w-0 flex-1">
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

          <div className="text-sm font-semibold text-foreground flex-1 truncate">
            {item.title}
          </div>

          <span className={`text-[11px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md shrink-0 sm:hidden ${
            isDone ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : isAwaiting ? "bg-amber-500/10 text-amber-400 border border-amber-500/20" : "bg-muted text-muted-foreground border border-border/40"
          }`}>
            {item.status.replace("_", " ")}
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap shrink-0 justify-between sm:justify-start pt-2 sm:pt-0 border-t sm:border-t-0 border-border/30">
          <span className={`hidden sm:inline-block text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded-md shrink-0 ${
            isDone ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : isAwaiting ? "bg-amber-500/10 text-amber-400 border border-amber-500/20" : "bg-muted text-muted-foreground border border-border/40"
          }`}>
            {item.status.replace("_", " ")}
          </span>

          {item.submitted_url && (
            <a
              href={ensureAbsoluteUrl(item.submitted_url)}
              target="_blank"
              rel="noreferrer"
              className="h-8 px-3 rounded-lg border border-primary/30 bg-primary/10 text-primary text-xs font-bold flex items-center gap-1.5 hover:bg-primary/20 transition-colors shrink-0"
            >
              <ExternalLink size={13} /> Submission
            </a>
          )}

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
function QuizAnswersReview({ cohortId, assignmentId, itemId }: { cohortId: string; assignmentId: string; itemId: string }) {
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
