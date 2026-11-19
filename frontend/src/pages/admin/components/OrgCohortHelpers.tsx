import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import {
  CheckCircle2, ClipboardCheck, Clock, ExternalLink, Eye, Pencil, Plus, Trash2, UserPlus, X,
} from "lucide-react"
import type { Cohort } from "@/types/sessions"
import { updateCohortApi } from "@/api/sessions/cohorts"
import { getOrganizationTeamApi, type OrgTeamMember } from "@/api/websiteEvents"
import {
  assignOrgInstructor,
  createOrgReadinessPreset,
  getOrgCohortReadiness,
  getOrgCohortStaff,
  getOrgReadinessPresets,
  setOrgCohortReadiness,
  unassignOrgInstructor,
  type OrgCohortReadiness,
  type OrgCohortStaff,
  type OrgInstructorReadiness,
  type OrgReadinessPreset,
  type OrgReadinessQuestionInput,
} from "@/api/organizationSandbox"
import {
  addOrgCohortObserverApi,
  getOrgCohortObserversApi,
  removeOrgCohortObserverApi,
  type OrgCohortObserver,
} from "@/api/organizationPrograms"
import { Button } from "@/components/ui/button"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

function ReadinessBadge({ readiness }: { readiness: OrgInstructorReadiness | null }) {
  if (!readiness) {
    return (
      <span className="inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
        Not started
      </span>
    )
  }
  const pct = Math.round(readiness.final_score || 0)
  if (readiness.passed) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
        <CheckCircle2 className="w-2.5 h-2.5" /> Passed · {pct}%
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400">
      <Clock className="w-2.5 h-2.5" />
      {readiness.status === "submitted" ? "Awaiting review" : "In progress"} · {pct}%
    </span>
  )
}

export function OrgCohortStaffingSection({
  cohortId,
  onChanged,
}: {
  cohortId: string
  onChanged?: () => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [instructorId, setInstructorId] = useState("")

  const { data: team = [] } = useQuery<OrgTeamMember[]>({
    queryKey: ["org-team-members", cohortId],
    queryFn: () => getOrganizationTeamApi({ cohort_id: cohortId }),
    enabled: Boolean(cohortId),
  })

  const { data: staff, isLoading } = useQuery<OrgCohortStaff>({
    queryKey: ["org-cohort-staff", cohortId],
    queryFn: () => getOrgCohortStaff(cohortId),
    enabled: Boolean(cohortId),
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["org-cohort-staff", cohortId] })
    void qc.invalidateQueries({ queryKey: ["sessions-sessions", cohortId] })
    onChanged?.()
  }

  const assignMut = useMutation({
    mutationFn: (userId: string) => assignOrgInstructor(cohortId, { user_id: userId }),
    onSuccess: (res) => {
      toast.success(
        res.assigned > 0
          ? `Assigned instructor to ${res.assigned} session${res.assigned === 1 ? "" : "s"}`
          : "Instructor is already assigned to all sessions"
      )
      setInstructorId("")
      invalidate()
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to assign instructor")),
  })

  const unassignMut = useMutation({
    mutationFn: (userId: string) => unassignOrgInstructor(cohortId, userId),
    onSuccess: () => {
      toast.success("Instructor unassigned from cohort")
      invalidate()
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to unassign instructor")),
  })

  const instructors = staff?.instructors ?? []
  const assignedIds = new Set(instructors.map((i) => i.user_id))
  const candidates = team.filter((m) => m.org_role === "instructor" && !assignedIds.has(m.id))

  return (
    <div className="py-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div>
          <h3 className="font-semibold text-sm text-foreground">Cohort Instructors</h3>
          <p className="text-xs text-muted-foreground">
            Assign an instructor from your organization team to all sessions in this cohort, or open an individual session to staff it separately.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <select
            value={instructorId}
            onChange={(e) => setInstructorId(e.target.value)}
            className="h-9 px-3 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:border-primary"
          >
            <option value="">Choose instructor…</option>
            {candidates.map((m) => (
              <option key={m.id} value={m.id}>
                {m.full_name}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            disabled={!instructorId || assignMut.isPending}
            onClick={() => assignMut.mutate(instructorId)}
          >
            <UserPlus className="size-3.5" /> Assign to cohort
          </Button>
        </div>
      </div>

      {candidates.length === 0 && instructors.length === 0 && (
        <p className="text-xs text-muted-foreground mb-3">
          No team members have the Instructor role yet.{" "}
          <Link to="/organization/team" className="font-semibold text-primary hover:underline">
            Add an instructor on the Team page
          </Link>
          .
        </p>
      )}

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading staffing…</p>
      ) : instructors.length === 0 ? (
        <p className="text-xs text-muted-foreground">No instructors assigned to this cohort yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground border-b border-border">
                <th className="py-2 pr-3">Instructor</th>
                <th className="py-2 pr-3">Sessions</th>
                <th className="py-2 pr-3">Attendance</th>
                <th className="py-2 pr-3">Readiness</th>
                <th className="py-2 pr-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {instructors.map((ins) => (
                <tr key={ins.user_id} className="border-b border-border/60">
                  <td className="py-2 pr-3">
                    <span className="font-medium text-foreground block">{ins.full_name}</span>
                    <span className="text-[11px] text-muted-foreground">{ins.email}</span>
                  </td>
                  <td className="py-2 pr-3 whitespace-nowrap text-muted-foreground">
                    {ins.completed_sessions} / {ins.sessions_count} completed
                  </td>
                  <td className="py-2 pr-3 whitespace-nowrap text-muted-foreground">
                    <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                      {ins.attendance_present}
                    </span>{" "}
                    present ·{" "}
                    <span className="text-destructive font-semibold">{ins.attendance_absent}</span> absent
                  </td>
                  <td className="py-2 pr-3">
                    <ReadinessBadge readiness={ins.readiness} />
                  </td>
                  <td className="py-2 pr-3 text-right whitespace-nowrap">
                    <Button
                      size="xs"
                      variant="outline"
                      disabled={unassignMut.isPending}
                      onClick={() => {
                        if (window.confirm(`Remove ${ins.full_name} from all sessions in this cohort?`)) {
                          unassignMut.mutate(ins.user_id)
                        }
                      }}
                    >
                      <Trash2 className="size-3" /> Unassign
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function OrgCohortReadinessSection({ cohortId }: { cohortId: string }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [presetDraft, setPresetDraft] = useState<string | null>(null)
  const [createPresetOpen, setCreatePresetOpen] = useState(false)

  const { data: presets = [] } = useQuery<OrgReadinessPreset[]>({
    queryKey: ["org-readiness-presets", cohortId],
    queryFn: () => getOrgReadinessPresets(cohortId),
    enabled: Boolean(cohortId),
  })

  const { data: readiness } = useQuery<OrgCohortReadiness>({
    queryKey: ["org-cohort-readiness", cohortId],
    queryFn: () => getOrgCohortReadiness(cohortId),
    enabled: Boolean(cohortId),
  })

  const saveMut = useMutation({
    mutationFn: (presetId: string | null) => setOrgCohortReadiness(cohortId, presetId),
    onSuccess: (res) => {
      toast.success(res.preset ? `Assigned "${res.preset.name}"` : "Readiness quiz cleared")
      void qc.invalidateQueries({ queryKey: ["org-cohort-readiness", cohortId] })
      void qc.invalidateQueries({ queryKey: ["org-cohort-staff", cohortId] })
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to update readiness quiz")),
  })

  const presetId = presetDraft ?? readiness?.preset?.id ?? ""

  return (
    <div className="py-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div>
          <h3 className="font-semibold text-sm flex items-center gap-2 text-foreground">
            <ClipboardCheck className="size-4 text-primary" /> Pre-Session Readiness Quiz
          </h3>
          <p className="text-xs text-muted-foreground">
            Instructors must pass this quiz before they can start a session in this cohort.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <select
            value={presetId}
            onChange={(e) => setPresetDraft(e.target.value)}
            className="h-9 px-3 rounded-xl border border-border bg-background text-xs text-foreground min-w-[220px] focus:outline-none focus:border-primary"
          >
            <option value="">No readiness quiz</option>
            {presets.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.question_count} questions){p.is_own ? " · Org" : ""}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            variant="outline"
            disabled={saveMut.isPending}
            onClick={() => saveMut.mutate(presetId || null)}
          >
            Save
          </Button>
          <Button size="sm" onClick={() => setCreatePresetOpen(true)}>
            <Plus className="size-3.5" /> Create Assessment
          </Button>
        </div>
      </div>

      {createPresetOpen && (
        <CreateOrgReadinessModal
          cohortId={cohortId}
          onClose={() => setCreatePresetOpen(false)}
          onCreated={(created) => {
            setCreatePresetOpen(false)
            setPresetDraft(created.id)
            void qc.invalidateQueries({ queryKey: ["org-readiness-presets", cohortId] })
            saveMut.mutate(created.id)
          }}
        />
      )}

      <p className="text-xs text-muted-foreground mb-3">
        Currently assigned:{" "}
        <span className="font-semibold text-foreground">
          {readiness?.preset ? readiness.preset.name : "None"}
        </span>
        {readiness?.preset?.description ? ` — ${readiness.preset.description}` : ""}
      </p>

      {!readiness || readiness.instructors.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No instructor readiness results yet. Results appear here once instructors take the quiz.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground border-b border-border">
                <th className="py-2 pr-3">Instructor</th>
                <th className="py-2 pr-3">Score</th>
                <th className="py-2 pr-3">Submitted</th>
                <th className="py-2 pr-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {readiness.instructors.map((r) => (
                <tr key={r.user_id} className="border-b border-border/60">
                  <td className="py-2 pr-3">
                    <span className="font-medium text-foreground block">{r.full_name}</span>
                    <span className="text-[11px] text-muted-foreground">{r.email}</span>
                  </td>
                  <td className="py-2 pr-3 whitespace-nowrap text-foreground font-semibold">
                    {Math.round(r.final_score || 0)}% of {r.total_questions} questions
                  </td>
                  <td className="py-2 pr-3 whitespace-nowrap text-muted-foreground">
                    {r.submitted_at ? new Date(r.submitted_at).toLocaleDateString() : "—"}
                  </td>
                  <td className="py-2 pr-3">
                    <ReadinessBadge
                      readiness={{
                        status: r.status,
                        final_score: r.final_score,
                        total_questions: r.total_questions,
                        submitted_at: r.submitted_at,
                        passed: r.passed,
                      }}
                    />
                    {r.pending_review_count > 0 && (
                      <span className="ml-2 text-[10px] text-muted-foreground">
                        {r.pending_review_count} pending review
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function CreateOrgReadinessModal({
  cohortId,
  onClose,
  onCreated,
}: {
  cohortId: string
  onClose: () => void
  onCreated: (preset: OrgReadinessPreset) => void
}) {
  const toast = useToast()
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [passingScore, setPassingScore] = useState(80)
  const [questions, setQuestions] = useState<OrgReadinessQuestionInput[]>([
    {
      prompt: "",
      question_type: "mcq",
      options: [
        { text: "", is_correct: true },
        { text: "", is_correct: false },
      ],
      explanation: "",
    },
  ])

  const mut = useMutation({
    mutationFn: () =>
      createOrgReadinessPreset({
        name: name.trim(),
        description: description.trim() || null,
        passing_score_percent: passingScore,
        cohort_id: cohortId,
        questions,
      }),
    onSuccess: (preset) => {
      toast.success(`Created "${preset.name}" and assigned it to this cohort`)
      onCreated(preset)
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to create assessment")),
  })

  const updateQuestion = (idx: number, patch: Partial<OrgReadinessQuestionInput>) => {
    setQuestions((prev) => prev.map((q, i) => (i === idx ? { ...q, ...patch } : q)))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-2xl border border-border bg-card p-6 shadow-xl space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h2 className="text-base font-bold text-foreground">Create Instructor Readiness Assessment</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Instructors assigned to this cohort must pass this assessment before starting a session.
            </p>
          </div>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground p-1">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className="text-xs font-semibold text-muted-foreground">Assessment Title *</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Lab Safety & Hardware Readiness"
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Pass Score (%)</span>
            <input
              type="number"
              min={0}
              max={100}
              value={passingScore}
              onChange={(e) => setPassingScore(Math.min(100, Math.max(0, Number(e.target.value) || 0)))}
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
            />
          </label>
        </div>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-semibold text-muted-foreground">Description (optional)</span>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What instructors should know before teaching"
            className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
          />
        </label>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-foreground">Questions ({questions.length})</span>
            <button
              type="button"
              onClick={() =>
                setQuestions((prev) => [
                  ...prev,
                  {
                    prompt: "",
                    question_type: "mcq",
                    options: [
                      { text: "", is_correct: true },
                      { text: "", is_correct: false },
                    ],
                    explanation: "",
                  },
                ])
              }
              className="inline-flex items-center gap-1 h-7 px-2.5 rounded-lg border border-border text-xs font-semibold text-primary hover:bg-muted"
            >
              <Plus className="w-3.5 h-3.5" /> Add Question
            </button>
          </div>

          {questions.map((q, qIdx) => (
            <div key={qIdx} className="rounded-xl border border-border bg-background p-3.5 space-y-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-muted-foreground">Question {qIdx + 1}</span>
                <div className="flex items-center gap-2">
                  <select
                    value={q.question_type}
                    onChange={(e) =>
                      updateQuestion(qIdx, { question_type: e.target.value as "mcq" | "written" })
                    }
                    className="h-7 px-2 rounded-lg border border-border bg-card text-xs"
                  >
                    <option value="mcq">Multiple Choice</option>
                    <option value="written">Written Answer</option>
                  </select>
                  {questions.length > 1 && (
                    <button
                      type="button"
                      onClick={() => setQuestions((prev) => prev.filter((_, i) => i !== qIdx))}
                      className="text-xs text-destructive hover:underline"
                    >
                      Remove
                    </button>
                  )}
                </div>
              </div>

              <input
                type="text"
                value={q.prompt}
                onChange={(e) => updateQuestion(qIdx, { prompt: e.target.value })}
                placeholder="Question prompt…"
                className="w-full h-9 px-3 rounded-xl border border-border bg-card text-sm focus:outline-none focus:border-primary"
              />

              {q.question_type === "mcq" && (
                <div className="space-y-1.5 pl-1">
                  {q.options.map((opt, oIdx) => (
                    <div key={oIdx} className="flex items-center gap-2">
                      <input
                        type="radio"
                        name={`q-${qIdx}-correct`}
                        checked={opt.is_correct}
                        onChange={() =>
                          updateQuestion(qIdx, {
                            options: q.options.map((o, oi) => ({ ...o, is_correct: oi === oIdx })),
                          })
                        }
                      />
                      <input
                        type="text"
                        value={opt.text}
                        onChange={(e) =>
                          updateQuestion(qIdx, {
                            options: q.options.map((o, oi) => (oi === oIdx ? { ...o, text: e.target.value } : o)),
                          })
                        }
                        placeholder={`Option ${oIdx + 1}`}
                        className="flex-1 h-8 px-2.5 rounded-lg border border-border bg-card text-xs"
                      />
                      {q.options.length > 2 && (
                        <button
                          type="button"
                          onClick={() =>
                            updateQuestion(qIdx, { options: q.options.filter((_, oi) => oi !== oIdx) })
                          }
                          className="text-xs text-muted-foreground hover:text-destructive px-1"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() =>
                      updateQuestion(qIdx, { options: [...q.options, { text: "", is_correct: false }] })
                    }
                    className="text-[11px] font-medium text-primary hover:underline"
                  >
                    + Add option
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!name.trim() || questions.some((q) => !q.prompt.trim()) || mut.isPending}
            onClick={() => mut.mutate()}
            className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50"
          >
            {mut.isPending ? "Saving..." : "Create & Assign"}
          </button>
        </div>
      </div>
    </div>
  )
}

export function OrgObserversSection({ cohortId }: { cohortId: string }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [addOpen, setAddOpen] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState("")

  const { data: observers = [], isLoading } = useQuery<OrgCohortObserver[]>({
    queryKey: ["org-cohort-observers", cohortId],
    queryFn: () => getOrgCohortObserversApi(cohortId),
    enabled: Boolean(cohortId),
  })

  const { data: team = [], isLoading: teamLoading } = useQuery<OrgTeamMember[]>({
    queryKey: ["org-team-members", cohortId],
    queryFn: () => getOrganizationTeamApi({ cohort_id: cohortId }),
    enabled: addOpen,
  })

  const addMut = useMutation({
    mutationFn: () => addOrgCohortObserverApi(cohortId, selectedUserId),
    onSuccess: () => {
      toast.success("Team member assigned as cohort observer")
      setSelectedUserId("")
      setAddOpen(false)
      void qc.invalidateQueries({ queryKey: ["org-cohort-observers", cohortId] })
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to assign observer")),
  })

  const removeMut = useMutation({
    mutationFn: (userId: string) => removeOrgCohortObserverApi(cohortId, userId),
    onSuccess: () => {
      toast.success("Observer unassigned")
      void qc.invalidateQueries({ queryKey: ["org-cohort-observers", cohortId] })
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to unassign observer")),
  })

  const existingIds = new Set(observers.map((o) => o.user_id))
  const eligibleTeam = team.filter((m) => !existingIds.has(m.id))

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-sm font-semibold text-foreground">
          Observers{observers.length > 0 ? ` (${observers.length})` : ""}
        </p>
        <button
          type="button"
          onClick={() => setAddOpen(true)}
          className="flex items-center gap-1.5 h-8 px-3 text-xs font-medium bg-[#653F84] text-white rounded-[10px] hover:opacity-90 transition-opacity cursor-pointer"
        >
          <Plus size={13} /> Add observer
        </button>
      </div>

      {isLoading ? (
        <div className="p-8 text-center text-xs text-muted-foreground">Loading observers…</div>
      ) : observers.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-10 text-center flex flex-col items-center gap-2">
          <Eye className="w-8 h-8 text-muted-foreground" />
          <h4 className="text-sm font-bold text-foreground">No observers assigned yet</h4>
          <p className="text-xs text-muted-foreground max-w-sm">
            Assign staff from your organization team to monitor progress and deliverables in observer mode.
          </p>
        </div>
      ) : (
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/40 text-muted-foreground uppercase text-[10px] tracking-wider border-b border-border">
                <tr>
                  <th className="py-3 px-4">Observer</th>
                  <th className="py-3 px-4">Email</th>
                  <th className="py-3 px-4">Phone</th>
                  <th className="py-3 px-4">Assigned On</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {observers.map((obs) => (
                  <tr key={obs.id} className="hover:bg-muted/20 transition">
                    <td className="py-3 px-4">
                      <span className="font-semibold text-foreground block">{obs.full_name}</span>
                      <span className="text-[10px] text-primary bg-primary/10 px-1.5 py-0.5 rounded font-medium inline-block mt-0.5">
                        Observer
                      </span>
                    </td>
                    <td className="py-3 px-4 text-muted-foreground">{obs.email}</td>
                    <td className="py-3 px-4 text-muted-foreground">{obs.phone || "—"}</td>
                    <td className="py-3 px-4 text-muted-foreground">
                      {obs.assigned_at ? new Date(obs.assigned_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm(`Remove ${obs.full_name} from cohort observers?`)) {
                            removeMut.mutate(obs.user_id)
                          }
                        }}
                        className="inline-flex items-center gap-1 text-xs text-destructive hover:underline"
                      >
                        <Trash2 className="w-3.5 h-3.5" /> Unassign
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {addOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div>
                <h3 className="text-base font-bold text-foreground">Add Team Observer</h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Select a member of your organization team to observe this cohort.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setAddOpen(false)}
                className="p-1 rounded-lg text-muted-foreground hover:bg-muted transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {teamLoading ? (
              <div className="py-8 text-center text-xs text-muted-foreground">Loading organization team…</div>
            ) : eligibleTeam.length === 0 ? (
              <div className="py-6 text-center space-y-2">
                <p className="text-xs text-muted-foreground">
                  {team.length === 0
                    ? "No team members found. Go to the Team tab to invite organization staff first."
                    : "All organization team members are already assigned as observers."}
                </p>
                <Link
                  to="/organization/team"
                  className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
                >
                  Manage Team Members <ExternalLink className="w-3 h-3" />
                </Link>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">Select Team Member</label>
                  <select
                    value={selectedUserId}
                    onChange={(e) => setSelectedUserId(e.target.value)}
                    className="w-full h-9 px-3 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:border-primary"
                  >
                    <option value="">-- Choose a team member --</option>
                    {eligibleTeam.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.full_name} ({m.email}) {m.is_owner ? "• Owner" : ""}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="p-3 rounded-xl border border-primary/20 bg-primary/5 text-[11px] text-muted-foreground leading-relaxed">
                  Observers can access the student portal to inspect checklists, assignments, and submissions in observer mode without being ranked or counted as competitor students.
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
                  <button
                    type="button"
                    onClick={() => setAddOpen(false)}
                    className="h-9 px-4 rounded-xl border border-border text-xs font-semibold hover:bg-muted transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={!selectedUserId || addMut.isPending}
                    onClick={() => addMut.mutate()}
                    className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50"
                  >
                    {addMut.isPending ? "Assigning..." : "Assign as Observer"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export function OrgEditCohortModal({
  cohort,
  onClose,
  onSaved,
}: {
  cohort: Cohort
  onClose: () => void
  onSaved: () => void
}) {
  const toast = useToast()
  const [name, setName] = useState(cohort.name || "")
  const [startsOn, setStartsOn] = useState(cohort.starts_on || "")
  const [endsOn, setEndsOn] = useState(cohort.ends_on || "")
  const [location, setLocation] = useState(cohort.location || "")
  const [capacity, setCapacity] = useState(cohort.capacity != null ? String(cohort.capacity) : "")
  const [checklistTitleOverride, setChecklistTitleOverride] = useState(cohort.checklist_title_override || "")
  const [isPublic, setIsPublic] = useState(cohort.visibility === "public")

  const numericCap = capacity ? Number(capacity) : null
  const capacityQuotaExceeded = Boolean(
    cohort.org_capacity_limit != null && numericCap != null && numericCap > cohort.org_capacity_limit
  )

  const mut = useMutation({
    mutationFn: () =>
      updateCohortApi(cohort.id, {
        name: name.trim(),
        starts_on: startsOn || null,
        ends_on: endsOn || null,
        location: location.trim() || null,
        capacity: numericCap,
        checklist_title_override: checklistTitleOverride.trim() || null,
        visibility: isPublic ? "public" : "private",
      }),
    onSuccess: () => {
      toast.success("Cohort details updated")
      onSaved()
      onClose()
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to update cohort")),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl border border-border bg-card p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-border pb-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
              <Pencil className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base font-bold text-foreground">Edit Cohort Details</h2>
              <p className="text-xs text-muted-foreground">Update cohort timing, capacity, and visibility settings</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Cohort Name *</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Start Date</span>
              <input
                type="date"
                value={startsOn}
                onChange={(e) => setStartsOn(e.target.value)}
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">End Date</span>
              <input
                type="date"
                value={endsOn}
                onChange={(e) => setEndsOn(e.target.value)}
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Location</span>
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="e.g. Innovation Center, Lab 3"
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Capacity (Students)</span>
              <input
                type="number"
                min={1}
                value={capacity}
                onChange={(e) => setCapacity(e.target.value)}
                className={`h-9 px-3 rounded-xl border bg-background text-sm focus:outline-none ${
                  capacityQuotaExceeded ? "border-amber-500 focus:border-amber-500" : "border-border focus:border-primary"
                }`}
              />
              {capacityQuotaExceeded && (
                <span className="text-[11px] text-amber-600 dark:text-amber-400 font-medium">
                  Your organization limit is {cohort.org_capacity_limit} students per cohort.
                </span>
              )}
            </label>
          </div>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">
              Custom Milestones Tab Label (Optional)
            </span>
            <input
              type="text"
              value={checklistTitleOverride}
              onChange={(e) => setChecklistTitleOverride(e.target.value)}
              placeholder="e.g. Competition Stages or Course Pathway"
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
            />
          </label>

          <label className="flex items-start gap-2.5 p-3 rounded-xl border border-border bg-muted/20 cursor-pointer">
            <input
              type="checkbox"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded text-primary focus:ring-primary border-border"
            />
            <div>
              <span className="text-xs font-semibold text-foreground block">
                List on Public Learning Catalog
              </span>
              <span className="text-[11px] text-muted-foreground block">
                Public cohorts appear on the public courses &amp; learning catalog.
              </span>
            </div>
          </label>
        </div>

        <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!name.trim() || capacityQuotaExceeded || mut.isPending}
            onClick={() => mut.mutate()}
            className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50"
          >
            {mut.isPending ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  )
}
