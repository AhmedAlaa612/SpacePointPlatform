import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import {
  Layers,
  Plus,
  Users,
  Calendar,
  Globe,
  Copy,
  ExternalLink,
  ChevronRight,
  AlertCircle,
  Pencil,
  Trash2,
  CheckCircle2,
  ListChecks,
  Trophy,
  X,
} from "lucide-react"
import { Link } from "@tanstack/react-router"
import { listLmsProgramsApi, createLmsProgramApi, getLmsProgramApi, type LmsProgram } from "@/api/lms_admin"
import { CreateChecklistPrompt, ProgramTemplateEditor } from "@/pages/lms-authoring/components/LmsChecklistAuthoring"
import { useToast } from "@/components/ui/toast"
import {
  getOrgProgramsOverviewApi,
  createOrgProgramApi,
  updateOrgProgramApi,
  deleteOrgProgramApi,
  createOrgCohortApi,
  updateOrgCohortApi,
  duplicateOrgCohortApi,
  type OrgProgramSummary,
  type OrgCohortSummary,
  type OrgQuotas,
} from "@/api/organizationPrograms"

export default function OrganizationPrograms() {
  const navigate = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()

  const [createProgramOpen, setCreateProgramOpen] = useState(false)
  const [editingProgram, setEditingProgram] = useState<OrgProgramSummary | null>(null)
  const [checklistProgram, setChecklistProgram] = useState<OrgProgramSummary | null>(null)
  const [createCohortForProgramId, setCreateCohortForProgramId] = useState<string | null>(null)
  const [duplicateTargetCohort, setDuplicateTargetCohort] = useState<OrgCohortSummary | null>(null)
  const [editingCohort, setEditingCohort] = useState<OrgCohortSummary | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ["org-programs-overview"],
    queryFn: getOrgProgramsOverviewApi,
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["org-programs-overview"] })
  }

  const deleteProgramMut = useMutation({
    mutationFn: (id: string) => deleteOrgProgramApi(id),
    onSuccess: () => {
      toast.success("Program deleted")
      invalidate()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to delete program")
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12 text-sm text-muted-foreground">
        Loading organization programs…
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="p-6 rounded-2xl border border-destructive/20 bg-destructive/5 text-destructive text-sm">
        Failed to load organization programs. Please refresh the page or contact support.
      </div>
    )
  }

  const org = data.organization || {
    id: "",
    name_latin: "Organization",
    name_arabic: null,
    org_type: "company",
    country: "AE",
    city: null,
    is_approved: true,
    can_publish_events: false,
    can_author_courses: false,
    can_publish_courses: false,
    course_scope_all: false,
    allowed_course_ids: [],
    max_events: null,
    max_programs: null,
    max_cohorts: null,
    max_students_per_cohort: null,
    max_observers_per_cohort: null,
  }
  const programs = data.programs || []
  const quotas = data.quotas || {
    programs_count: 0,
    max_programs: null,
    cohorts_count: 0,
    max_cohorts: null,
    events_count: 0,
    max_events: null,
    max_students_per_cohort: null,
    max_observers_per_cohort: null,
  }

  const programsQuotaReached =
    quotas.max_programs !== null && quotas.programs_count >= quotas.max_programs

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto pb-12">
      {/* ── Top Header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight text-foreground">
              {org.name_latin}
            </h1>
            {org.is_approved ? (
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 className="w-3 h-3" /> Approved Partner
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400">
                <AlertCircle className="w-3 h-3" /> Pending Review
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground mt-0.5">
            Host and deliver your programs, manage milestones, and track student cohorts.
          </p>
        </div>

        <button
          type="button"
          disabled={programsQuotaReached || !org.is_approved}
          onClick={() => setCreateProgramOpen(true)}
          title={!org.is_approved ? "Account under review by Operations" : undefined}
          className="inline-flex items-center justify-center gap-2 h-10 px-4 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:opacity-90 transition disabled:opacity-50"
        >
          <Plus className="w-4 h-4" /> New Program
        </button>
      </div>

      {/* ── Under Review Banner ────────────────────────────────────────────── */}
      {!org.is_approved && (
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-5 flex items-start gap-3.5">
          <AlertCircle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-foreground">
              Account Under Review
            </h3>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Your partner organization account is currently under review by SpacePoint Operations. During review, program creation and hosting limits are locked. Our operations team will verify your account and activate your hosting access shortly.
            </p>
          </div>
        </div>
      )}

      {/* ── Quotas & Access Bar ────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-xl border border-border bg-card p-3.5 flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Programs
          </span>
          <div className="flex items-baseline gap-1.5">
            <span className="text-lg font-bold text-foreground">{quotas.programs_count}</span>
            <span className="text-xs text-muted-foreground">
              / {quotas.max_programs ?? "Unlimited"}
            </span>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-3.5 flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Cohorts
          </span>
          <div className="flex items-baseline gap-1.5">
            <span className="text-lg font-bold text-foreground">{quotas.cohorts_count}</span>
            <span className="text-xs text-muted-foreground">
              / {quotas.max_cohorts ?? "Unlimited"}
            </span>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-3.5 flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Max Students / Cohort
          </span>
          <span className="text-lg font-bold text-foreground">
            {quotas.max_students_per_cohort ?? "Unlimited"}
          </span>
        </div>

        <div className="rounded-xl border border-border bg-card p-3.5 flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Max Observers / Cohort
          </span>
          <span className="text-lg font-bold text-foreground">
            {quotas.max_observers_per_cohort ?? "Unlimited"}
          </span>
        </div>
      </div>

      {/* ── Programs List ───────────────────────────────────────────────────── */}
      {programs.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-12 text-center flex flex-col items-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-primary/10 text-primary flex items-center justify-center">
            <Layers className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-foreground">No programs yet</h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-sm">
              Create your first program to start adding cohorts, training modules, and onboarding
              students.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setCreateProgramOpen(true)}
            className="mt-2 inline-flex items-center gap-1.5 h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition"
          >
            <Plus className="w-3.5 h-3.5" /> Create Program
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          {programs.map((program) => {
            const cohortsQuotaReached =
              quotas.max_cohorts !== null && quotas.cohorts_count >= quotas.max_cohorts

            return (
              <div
                key={program.id}
                className="rounded-2xl border border-border bg-card shadow-sm overflow-hidden"
              >
                {/* Program Header */}
                <div className="p-5 border-b border-border bg-muted/20 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h2 className="text-base font-bold text-foreground truncate">
                        {program.name}
                      </h2>
                      <span className="text-xs font-mono px-2 py-0.5 rounded bg-muted text-muted-foreground uppercase">
                        {program.code}
                      </span>
                      <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-primary/10 text-primary capitalize">
                        {program.program_type}
                      </span>
                    </div>
                      {program.description && (
                        <p className="text-xs text-muted-foreground mt-0.5 truncate">
                          {program.description}
                        </p>
                      )}
                      <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap pt-1">
                        <span>Capacity: <strong className="text-foreground">{program.default_capacity ? `${program.default_capacity} students` : "Unlimited"}</strong></span>
                        <span>·</span>
                        <span>Cohorts: <strong className="text-foreground">{program.cohorts.length}</strong></span>
                      </div>
                    </div>

                  <div className="flex items-center gap-2 shrink-0 flex-wrap">
                    <button
                      type="button"
                      disabled={cohortsQuotaReached}
                      onClick={() => setCreateCohortForProgramId(program.id)}
                      className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50"
                    >
                      <Plus className="w-3.5 h-3.5" /> Add Cohort
                    </button>
                    <button
                      type="button"
                      onClick={() => setChecklistProgram(program)}
                      className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-lg border border-border bg-background text-xs font-semibold text-foreground hover:bg-muted transition"
                      title="Manage Default LMS Checklist Template"
                    >
                      <ListChecks className="w-3.5 h-3.5 text-primary" /> Checklist Template
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditingProgram(program)}
                      className="inline-flex items-center gap-1 h-8 px-2.5 rounded-lg border border-border bg-background text-xs font-medium text-foreground hover:bg-muted transition"
                    >
                      <Pencil className="w-3.5 h-3.5" /> Edit
                    </button>
                    {program.cohorts.length === 0 && (
                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm(`Delete program "${program.name}"?`)) {
                            deleteProgramMut.mutate(program.id)
                          }
                        }}
                        className="inline-flex items-center justify-center h-8 w-8 rounded-lg border border-border bg-background text-muted-foreground hover:text-destructive transition"
                        title="Delete Program"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>

                {/* Cohorts List */}
                <div className="p-4 sm:p-5">
                  {program.cohorts.length === 0 ? (
                    <div className="py-6 text-center text-xs text-muted-foreground">
                      No cohorts added under this program yet.
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                      {program.cohorts.map((cohort) => (
                        <div
                          key={cohort.id}
                          className="rounded-xl border border-border bg-background p-4 flex flex-col justify-between gap-3 hover:border-primary/40 transition group"
                        >
                          <div>
                            <div className="flex items-start justify-between gap-2">
                              <div>
                                <div className="flex items-center gap-1.5">
                                  <h3 className="text-sm font-bold text-foreground group-hover:text-primary transition">
                                    {cohort.name}
                                  </h3>
                                  <button
                                    type="button"
                                    onClick={() => setEditingCohort(cohort)}
                                    title="Edit Cohort Details"
                                    className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition"
                                  >
                                    <Pencil className="w-3 h-3" />
                                  </button>
                                </div>
                                <span className="text-[11px] font-mono text-muted-foreground">
                                  {cohort.code}
                                </span>
                              </div>
                              <div className="flex items-center gap-1.5">
                                {cohort.is_public && (
                                  <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                                    <Globe className="w-2.5 h-2.5" /> Public
                                  </span>
                                )}
                              </div>
                            </div>

                            <div className="grid grid-cols-2 gap-2 mt-3 text-xs text-muted-foreground">
                              <div className="flex items-center gap-1.5 truncate">
                                <Calendar className="w-3.5 h-3.5 shrink-0" />
                                <span className="truncate">
                                  {cohort.start_date} – {cohort.end_date}
                                </span>
                              </div>
                              <div className="flex items-center gap-1.5">
                                <Users className="w-3.5 h-3.5 shrink-0" />
                                <span>
                                  {cohort.active_students_count} / {cohort.capacity} students
                                </span>
                              </div>
                            </div>

                            {cohort.linked_event_slug && (
                              <div className="mt-2.5 pt-2 border-t border-border flex items-center justify-between text-[11px]">
                                <span className="text-muted-foreground">Landing Page:</span>
                                <a
                                  href={`/events/${org.country || "ae"}/${cohort.linked_event_slug}`}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-primary hover:underline inline-flex items-center gap-1 font-medium"
                                >
                                  View Page <ExternalLink className="w-2.5 h-2.5" />
                                </a>
                              </div>
                            )}
                          </div>

                          <div className="flex items-center justify-between pt-2 border-t border-border gap-2">
                            <div className="flex items-center gap-1.5">
                              <button
                                type="button"
                                onClick={() => setEditingCohort(cohort)}
                                title="Edit cohort details"
                                className="inline-flex items-center gap-1 h-7 px-2 rounded-lg border border-border text-[11px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition"
                              >
                                <Pencil className="w-3 h-3" /> Edit
                              </button>
                              <button
                                type="button"
                                onClick={() => setDuplicateTargetCohort(cohort)}
                                title="Duplicate cohort structure & curriculum"
                                className="inline-flex items-center gap-1 h-7 px-2 rounded-lg border border-border text-[11px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition"
                              >
                                <Copy className="w-3 h-3" /> Duplicate
                              </button>
                              {program.program_type === "competition" && (
                                <Link
                                  to="/organization/programs/$cohortId/judging"
                                  params={{ cohortId: cohort.id }}
                                  className="inline-flex items-center gap-1 h-7 px-2 rounded-lg border border-primary/30 bg-primary/5 text-primary text-[11px] font-semibold hover:bg-primary/15 transition"
                                  title="Competition Judging, Roster, Rubric & Leaderboard"
                                >
                                  <Trophy className="w-3 h-3" /> Judging
                                </Link>
                              )}
                            </div>

                            <button
                              type="button"
                              onClick={() =>
                                void navigate({
                                  to: "/organization/programs/$cohortId",
                                  params: { cohortId: cohort.id },
                                })
                              }
                              className="inline-flex items-center gap-1 h-7 px-2.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 text-xs font-semibold transition"
                            >
                              Manage <ChevronRight className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ── Create Program Modal ────────────────────────────────────────────── */}
      {createProgramOpen && (
        <CreateProgramModal
          onClose={() => setCreateProgramOpen(false)}
          onSuccess={() => {
            setCreateProgramOpen(false)
            invalidate()
          }}
        />
      )}

      {/* ── Edit Program Modal ──────────────────────────────────────────────── */}
      {editingProgram && (
        <EditProgramModal
          program={editingProgram}
          onClose={() => setEditingProgram(null)}
          onSuccess={() => {
            setEditingProgram(null)
            invalidate()
          }}
        />
      )}

      {/* ── Create Cohort Modal ─────────────────────────────────────────────── */}
      {createCohortForProgramId && (
        <CreateCohortModal
          programId={createCohortForProgramId}
          quotas={quotas}
          onClose={() => setCreateCohortForProgramId(null)}
          onSuccess={() => {
            setCreateCohortForProgramId(null)
            invalidate()
          }}
        />
      )}

      {/* ── Duplicate Cohort Modal ──────────────────────────────────────────── */}
      {duplicateTargetCohort && (
        <DuplicateCohortModal
          sourceCohort={duplicateTargetCohort}
          quotas={quotas}
          onClose={() => setDuplicateTargetCohort(null)}
          onSuccess={() => {
            setDuplicateTargetCohort(null)
            invalidate()
          }}
        />
      )}

      {/* ── Edit Cohort Modal ──────────────────────────────────────────────── */}
      {editingCohort && (
        <EditCohortModal
          cohort={editingCohort}
          quotas={quotas}
          onClose={() => setEditingCohort(null)}
          onSuccess={() => {
            setEditingCohort(null)
            invalidate()
          }}
        />
      )}

      {/* ── LMS Checklist Template Modal ────────────────────────────────────── */}
      {checklistProgram && (
        <ProgramChecklistModal
          program={checklistProgram}
          onClose={() => setChecklistProgram(null)}
        />
      )}
    </div>
  )
}

// ── Modals ───────────────────────────────────────────────────────────────────

function ProgramChecklistModal({
  program,
  onClose,
}: {
  program: OrgProgramSummary
  onClose: () => void
}) {
  const qc = useQueryClient()
  const { data: found = [], isLoading } = useQuery<LmsProgram[]>({
    queryKey: ["lms-program-for-program", program.id],
    queryFn: () => listLmsProgramsApi(program.id),
  })
  const [created, setCreated] = useState<LmsProgram | null>(null)
  const effective = created ?? found[0] ?? null

  const createMutation = useMutation({
    mutationFn: (name: string) => createLmsProgramApi({ program_id: program.id, name }),
    onSuccess: (p) => setCreated(p),
  })

  const refresh = async () => {
    if (effective) {
      const fresh = await getLmsProgramApi(effective.id)
      setCreated(fresh)
      void qc.invalidateQueries({ queryKey: ["lms-program-for-program", program.id] })
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-2xl border border-border bg-card p-6 shadow-2xl flex flex-col gap-4">
        <div className="flex items-center justify-between pb-3 border-b border-border">
          <div>
            <h2 className="text-base font-bold text-foreground">
              Checklist Template — {program.name}
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Default milestones, tasks, and courses inherited by every new cohort of this program.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {isLoading ? (
          <div className="py-12 text-center text-xs text-muted-foreground">
            Loading checklist template…
          </div>
        ) : !effective ? (
          <CreateChecklistPrompt
            onCreate={(name) => createMutation.mutate(name)}
            pending={createMutation.isPending}
          />
        ) : (
          <ProgramTemplateEditor program={effective} onChanged={refresh} readOnly={false} />
        )}
      </div>
    </div>
  )
}

function CreateProgramModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  const [name, setName] = useState("")
  const [code, setCode] = useState("")
  const [programType, setProgramType] = useState("competition")
  const [defaultCapacity, setDefaultCapacity] = useState("50")
  const [keepCourseAccessAfterCompletion, setKeepCourseAccessAfterCompletion] = useState(true)
  const [description, setDescription] = useState("")

  const mut = useMutation({
    mutationFn: () =>
      createOrgProgramApi({
        name: (name || "").trim(),
        code: (code || "").trim().toUpperCase(),
        program_type: programType,
        default_capacity: defaultCapacity ? parseInt(defaultCapacity, 10) : undefined,
        pricing_model: "free",
        price: undefined,
        completion_rule_type: "percentage",
        completion_rule_value: 0,
        keep_course_access_after_completion: keepCourseAccessAfterCompletion,
        description: (description || "").trim() || undefined,
      }),
    onSuccess: () => {
      toast.success("Program created!")
      onSuccess()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to create program")
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl border border-border bg-card p-6 shadow-xl space-y-4">
        <h2 className="text-base font-bold text-foreground">Create New Program</h2>

        <div className="space-y-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Program Name *</span>
            <input
              type="text"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                if (!code) {
                  setCode(
                    e.target.value
                      .replace(/[^a-zA-Z0-9]/g, "")
                      .slice(0, 8)
                      .toUpperCase()
                  )
                }
              }}
              placeholder="e.g. Space Innovation Challenge"
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
            />
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Program Code *</span>
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                placeholder="SIC-2026"
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm font-mono focus:outline-none focus:border-primary"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Type</span>
              <select
                value={programType}
                onChange={(e) => setProgramType(e.target.value)}
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              >
                <option value="competition">Competition</option>
                <option value="course">Course</option>
                <option value="workshop">Workshop</option>
                <option value="info_session">Info Session</option>
                <option value="internship">Internship</option>
              </select>
            </label>
          </div>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Default Capacity (Students)</span>
            <input
              type="number"
              min={1}
              value={defaultCapacity}
              onChange={(e) => setDefaultCapacity(e.target.value)}
              placeholder="50"
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Description</span>
            <textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief summary and objectives of this program..."
              className="p-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary resize-none"
            />
          </label>

          <label className="flex items-center gap-2 cursor-pointer text-xs font-medium text-foreground pt-1">
            <input
              type="checkbox"
              checked={keepCourseAccessAfterCompletion}
              onChange={(e) => setKeepCourseAccessAfterCompletion(e.target.checked)}
              className="h-4 w-4 rounded text-primary focus:ring-primary border-border"
            />
            Keep student course access active after program completion
          </label>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!(name || "").trim() || !(code || "").trim() || mut.isPending}
            onClick={() => mut.mutate()}
            className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50"
          >
            {mut.isPending ? "Creating..." : "Create Program"}
          </button>
        </div>
      </div>
    </div>
  )
}

function EditProgramModal({
  program,
  onClose,
  onSuccess,
}: {
  program: OrgProgramSummary
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  const [name, setName] = useState(program.name || "")
  const [programType, setProgramType] = useState(program.program_type || "competition")
  const [defaultCapacity, setDefaultCapacity] = useState(program.default_capacity ? String(program.default_capacity) : "50")
  const [keepCourseAccessAfterCompletion, setKeepCourseAccessAfterCompletion] = useState(
    program.keep_course_access_after_completion ?? true
  )
  const [description, setDescription] = useState(program.description || "")

  const mut = useMutation({
    mutationFn: () =>
      updateOrgProgramApi(program.id, {
        name: (name || "").trim(),
        program_type: programType,
        default_capacity: defaultCapacity ? parseInt(defaultCapacity, 10) : undefined,
        pricing_model: "free",
        price: undefined,
        keep_course_access_after_completion: keepCourseAccessAfterCompletion,
        description: (description || "").trim() || undefined,
      }),
    onSuccess: () => {
      toast.success("Program updated!")
      onSuccess()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to update program")
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl border border-border bg-card p-6 shadow-xl space-y-4">
        <h2 className="text-base font-bold text-foreground">Edit Program</h2>

        <div className="space-y-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Program Name *</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
            />
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Type</span>
              <select
                value={programType}
                onChange={(e) => setProgramType(e.target.value)}
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              >
                <option value="competition">Competition</option>
                <option value="course">Course</option>
                <option value="workshop">Workshop</option>
                <option value="info_session">Info Session</option>
                <option value="internship">Internship</option>
              </select>
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Default Capacity (Students)</span>
              <input
                type="number"
                min={1}
                value={defaultCapacity}
                onChange={(e) => setDefaultCapacity(e.target.value)}
                placeholder="50"
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>
          </div>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Description</span>
            <textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="p-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary resize-none"
            />
          </label>

          <label className="flex items-center gap-2 cursor-pointer text-xs font-medium text-foreground pt-1">
            <input
              type="checkbox"
              checked={keepCourseAccessAfterCompletion}
              onChange={(e) => setKeepCourseAccessAfterCompletion(e.target.checked)}
              className="h-4 w-4 rounded text-primary focus:ring-primary border-border"
            />
            Keep student course access active after program completion
          </label>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!(name || "").trim() || mut.isPending}
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

function CreateCohortModal({
  programId,
  quotas,
  onClose,
  onSuccess,
}: {
  programId: string
  quotas: OrgQuotas
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  const today = new Date().toISOString().split("T")[0]

  const [name, setName] = useState("")
  const [code, setCode] = useState("")
  const [startDate, setStartDate] = useState(today)
  const [endDate, setEndDate] = useState(today)
  const [location, setLocation] = useState("")
  const [capacity, setCapacity] = useState("50")
  const [isPublic, setIsPublic] = useState(false)

  const capacityNum = parseInt(capacity, 10) || 0
  const capacityExceeded =
    quotas.max_students_per_cohort !== null && capacityNum > quotas.max_students_per_cohort

  const mut = useMutation({
    mutationFn: () =>
      createOrgCohortApi({
        program_id: programId,
        name: name.trim(),
        code: code.trim().toUpperCase(),
        start_date: startDate,
        end_date: endDate,
        location: location.trim() || undefined,
        capacity: capacityNum,
        is_public: isPublic,
      }),
    onSuccess: () => {
      toast.success("Cohort created!")
      onSuccess()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to create cohort")
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-xl space-y-4">
        <h2 className="text-base font-bold text-foreground">Create New Cohort</h2>

        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Cohort Name *</span>
              <input
                type="text"
                value={name}
                onChange={(e) => {
                  setName(e.target.value)
                  if (!code) {
                    setCode(
                      e.target.value
                        .replace(/[^a-zA-Z0-9]/g, "")
                        .slice(0, 8)
                        .toUpperCase()
                    )
                  }
                }}
                placeholder="Spring 2026"
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Cohort Code *</span>
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                placeholder="SP26-C1"
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm font-mono focus:outline-none focus:border-primary"
              />
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Start Date *</span>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">End Date *</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
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
                placeholder="Virtual / Main Campus"
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Capacity (Students)</span>
              <input
                type="number"
                min="1"
                value={capacity}
                onChange={(e) => setCapacity(e.target.value)}
                className={`h-9 px-3 rounded-xl border bg-background text-sm focus:outline-none transition ${
                  capacityExceeded ? "border-destructive text-destructive" : "border-border"
                }`}
              />
            </label>
          </div>

          {capacityExceeded && (
            <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-2.5 text-xs text-destructive">
              Your limit is {quotas.max_students_per_cohort} students per cohort. Talk to the
              SpacePoint team to request a higher limit.
            </div>
          )}

          <label className="flex items-start gap-2.5 p-3 rounded-xl border border-border bg-muted/20 cursor-pointer">
            <input
              type="checkbox"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded text-primary focus:ring-primary border-border"
            />
            <div>
              <span className="text-xs font-semibold text-foreground block">
                List on SpacePoint Public Catalog
              </span>
              <span className="text-[11px] text-muted-foreground block">
                Allows students outside your private enrollment to discover and register for this
                cohort.
              </span>
            </div>
          </label>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!name.trim() || !code.trim() || capacityExceeded || mut.isPending}
            onClick={() => mut.mutate()}
            className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50"
          >
            {mut.isPending ? "Creating..." : "Create Cohort"}
          </button>
        </div>
      </div>
    </div>
  )
}

function DuplicateCohortModal({
  sourceCohort,
  quotas,
  onClose,
  onSuccess,
}: {
  sourceCohort: OrgCohortSummary
  quotas: OrgQuotas
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  const today = new Date().toISOString().split("T")[0]

  const [name, setName] = useState(`${sourceCohort.name} (Copy)`)
  const [code, setCode] = useState(`${sourceCohort.code}-2`)
  const [startDate, setStartDate] = useState(today)
  const [endDate, setEndDate] = useState(today)
  const [capacity, setCapacity] = useState(String(sourceCohort.capacity || 50))
  const [isPublic, setIsPublic] = useState(sourceCohort.is_public)
  const [duplicateCurriculum, setDuplicateCurriculum] = useState(true)

  const capacityNum = parseInt(capacity, 10) || 0
  const capacityExceeded =
    quotas.max_students_per_cohort !== null && capacityNum > quotas.max_students_per_cohort

  const mut = useMutation({
    mutationFn: () =>
      duplicateOrgCohortApi(sourceCohort.id, {
        name: name.trim(),
        code: code.trim().toUpperCase(),
        start_date: startDate,
        end_date: endDate,
        capacity: capacityNum,
        is_public: isPublic,
        duplicate_curriculum: duplicateCurriculum,
      }),
    onSuccess: () => {
      toast.success("Cohort duplicated successfully!")
      onSuccess()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to duplicate cohort")
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-xl space-y-4">
        <div>
          <h2 className="text-base font-bold text-foreground">Duplicate Cohort</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Cloning from <strong>{sourceCohort.name}</strong> ({sourceCohort.code})
          </p>
        </div>

        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">New Cohort Name *</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">New Cohort Code *</span>
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm font-mono focus:outline-none focus:border-primary"
              />
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Start Date *</span>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">End Date *</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>
          </div>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Capacity (Students)</span>
            <input
              type="number"
              min="1"
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
              className={`h-9 px-3 rounded-xl border bg-background text-sm focus:outline-none transition ${
                capacityExceeded ? "border-destructive text-destructive" : "border-border"
              }`}
            />
          </label>

          {capacityExceeded && (
            <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-2.5 text-xs text-destructive">
              Your limit is {quotas.max_students_per_cohort} students per cohort. Talk to the
              SpacePoint team to request a higher limit.
            </div>
          )}

          <label className="flex items-start gap-2.5 p-3 rounded-xl border border-border bg-muted/20 cursor-pointer">
            <input
              type="checkbox"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded text-primary focus:ring-primary border-border"
            />
            <div>
              <span className="text-xs font-semibold text-foreground block">
                List on SpacePoint Public Catalog
              </span>
              <span className="text-[11px] text-muted-foreground block">
                Public cohorts appear on SpacePoint's public learning catalog.
              </span>
            </div>
          </label>

          <label className="flex items-start gap-2.5 p-3 rounded-xl border border-border bg-muted/20 cursor-pointer">
            <input
              type="checkbox"
              checked={duplicateCurriculum}
              onChange={(e) => setDuplicateCurriculum(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded text-primary focus:ring-primary border-border"
            />
            <div>
              <span className="text-xs font-semibold text-foreground block">
                Copy Milestones & Learning Modules
              </span>
              <span className="text-[11px] text-muted-foreground block">
                Replicates all checklist items and module attachments into the new cohort.
              </span>
            </div>
          </label>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!name.trim() || !code.trim() || capacityExceeded || mut.isPending}
            onClick={() => mut.mutate()}
            className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50"
          >
            {mut.isPending ? "Duplicating..." : "Duplicate Cohort"}
          </button>
        </div>
      </div>
    </div>
  )
}

function EditCohortModal({
  cohort,
  quotas,
  onClose,
  onSuccess,
}: {
  cohort: OrgCohortSummary
  quotas: OrgQuotas
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  const [name, setName] = useState(cohort.name || "")
  const [code, setCode] = useState(cohort.code || cohort.name || "")
  const [startDate, setStartDate] = useState(cohort.start_date || "")
  const [endDate, setEndDate] = useState(cohort.end_date || "")
  const [location, setLocation] = useState(cohort.location || "")
  const [capacity, setCapacity] = useState(String(cohort.capacity ?? 50))
  const [isPublic, setIsPublic] = useState(Boolean(cohort.is_public))
  const [checklistTitleOverride, setChecklistTitleOverride] = useState(
    cohort.checklist_title_override || ""
  )

  const capacityNum = parseInt(capacity, 10) || 0
  const capacityExceeded =
    quotas.max_students_per_cohort !== null && capacityNum > quotas.max_students_per_cohort

  const mut = useMutation({
    mutationFn: () =>
      updateOrgCohortApi(cohort.id, {
        name: (name || "").trim(),
        code: (code || "").trim().toUpperCase(),
        start_date: startDate,
        end_date: endDate,
        location: (location || "").trim() || undefined,
        capacity: capacityNum || cohort.capacity,
        is_public: isPublic,
        checklist_title_override: (checklistTitleOverride || "").trim() || null,
      }),
    onSuccess: () => {
      toast.success("Cohort details updated!")
      onSuccess()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to update cohort")
    },
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
              <p className="text-xs text-muted-foreground">Update cohort timing, capacity, and catalog settings</p>
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
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Cohort Name *</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Cohort Code *</span>
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm font-mono focus:outline-none focus:border-primary"
              />
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Start Date</span>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">End Date</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
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
                  capacityExceeded ? "border-amber-500 focus:border-amber-500" : "border-border focus:border-primary"
                }`}
              />
            </label>
          </div>

          {capacityExceeded && (
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-2.5 text-xs text-amber-600 dark:text-amber-400">
              Your organization limit is {quotas.max_students_per_cohort} students per cohort. Talk to the
              SpacePoint team to request a higher limit.
            </div>
          )}

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
                List on SpacePoint Public Catalog
              </span>
              <span className="text-[11px] text-muted-foreground block">
                Public cohorts appear on SpacePoint's public learning catalog.
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
            disabled={!name.trim() || !code.trim() || capacityExceeded || mut.isPending}
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
