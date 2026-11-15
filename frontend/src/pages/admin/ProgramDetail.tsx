import { useState, useMemo } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link, useParams, useNavigate } from "@tanstack/react-router"
import {
  ArrowLeft,
  Plus,
  Pencil,
  Trash2,
  Calendar,
  MapPin,
  Users,
  ChevronRight,
  ChevronDown,
  ArrowRight,
} from "lucide-react"
import type {
  Program,
  ProgramType,
  PricingModel,
  CompletionRuleType,
  Cohort,
  CohortStatus,
} from "@/types/sessions"
import {
  getProgramApi,
  updateProgramApi,
  deleteProgramApi,
} from "@/api/sessions/programs"
import { getCohortsApi, deleteCohortApi } from "@/api/sessions/cohorts"
import { Modal, Spinner } from "@/pages/admin/components/common"
import { SubCard } from "@/components/ui/primitives"
import { ProgramRolesPanel } from "@/pages/admin/components/ProgramRolesPanel"
import { ProgramAssessmentDefaultPanel } from "@/pages/admin/components/ProgramAssessmentDefaultPanel"
import { PreSessionQuizAssignmentBar } from "@/pages/admin/components/PreSessionQuizAssignmentBar"
import { MaterialsPanel } from "@/pages/admin/components/MaterialsPanel"
import { ProgramCertificateStudioModal } from "@/pages/admin/components/ProgramCertificateStudioModal"
import { ProgramLmsSection } from "@/pages/admin/components/ProgramLmsSection"
import { CohortModal } from "@/pages/admin/Cohorts"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

const PROGRAM_TYPES: ProgramType[] = ["workshop", "course", "info_session", "competition"]
const PRICING_MODELS: PricingModel[] = ["paid", "free"]

const PROGRAM_TYPE_LABEL: Record<ProgramType, string> = {
  workshop: "Workshop",
  course: "Course",
  info_session: "Info session",
  competition: "Competition",
}

const PRICING_MODEL_LABEL: Record<PricingModel, string> = {
  paid: "Paid",
  free: "Free",
}

type ProgramTab =
  | "cohorts"
  | "instructors"
  | "lms"
  | "certificates"

const TABS: { key: ProgramTab; label: string }[] = [
  { key: "cohorts", label: "Cohorts & Materials" },
  { key: "instructors", label: "Instructors" },
  { key: "lms", label: "LMS Authoring" },
  { key: "certificates", label: "Certificates" },
]

type InstructorSubTab = "roles" | "assessment" | "prequiz"

function CounterChip({
  label,
  value,
  onClick,
}: {
  label: string
  value: React.ReactNode
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center justify-center gap-1.5 h-9 px-4 rounded-[10px] border-2 border-solid border-[#D7D2CB] bg-transparent text-white hover:bg-white/10 text-sm transition-colors cursor-pointer"
    >
      <span className="font-semibold tabular-nums leading-none flex items-center">{value}</span>
      <span className="text-xs text-white/75 leading-none flex items-center">{label}</span>
    </button>
  )
}

export default function ProgramDetail() {
  const { programId } = useParams({ strict: false }) as { programId: string }
  const navigate = useNavigate()
  const toast = useToast()
  const queryClient = useQueryClient()

  const [activeTab, setActiveTab] = useState<ProgramTab>("cohorts")
  const [instructorSub, setInstructorSub] = useState<InstructorSubTab>("roles")
  const [editingCohort, setEditingCohort] = useState<Cohort | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [expandedPast, setExpandedPast] = useState(false)

  // Query Program
  const { data: program, isLoading: programLoading } = useQuery<Program>({
    queryKey: ["sessions-program", programId],
    queryFn: () => getProgramApi(programId),
  })

  // Query Cohorts of this Program
  const { data: allCohorts = [], isLoading: cohortsLoading } = useQuery<Cohort[]>({
    queryKey: ["sessions-cohorts"],
    queryFn: () => getCohortsApi(),
  })

  const cohorts = useMemo(
    () =>
      allCohorts.filter((c) => {
        if (c.program_id !== programId) return false
        const statusStr = String(c.status).toLowerCase()
        const normName = c.name.trim().toLowerCase()
        return statusStr !== "draft" && !normName.startsWith("[template]") && normName !== "template"
      }),
    [allCohorts, programId]
  )

  const runningCohorts = useMemo(
    () => cohorts.filter((c) => c.status === "running"),
    [cohorts]
  )
  const openCohorts = useMemo(
    () => cohorts.filter((c) => c.status === "registration_open" || c.status === "planned"),
    [cohorts]
  )
  const pastCohorts = useMemo(
    () => cohorts.filter((c) => c.status === "completed" || c.status === "cancelled"),
    [cohorts]
  )

  // Program Delete Mutation
  const deleteMutation = useMutation({
    mutationFn: () => deleteProgramApi(programId),
    onSuccess: () => {
      toast.success("Program deleted")
      queryClient.invalidateQueries({ queryKey: ["sessions-programs"] })
      navigate({ to: "/operations/programs" })
    },
    onError: (e: unknown) =>
      toast.error(getErrorMessage(e, "Failed to delete program")),
  })

  // Cohort Delete Mutation
  const deleteCohortMutation = useMutation({
    mutationFn: deleteCohortApi,
    onSuccess: () => {
      toast.success("Cohort deleted")
      queryClient.invalidateQueries({ queryKey: ["sessions-cohorts"] })
    },
    onError: (e: unknown) =>
      toast.error(getErrorMessage(e, "Failed to delete cohort")),
  })

  if (programLoading || cohortsLoading) return <Spinner />

  if (!program) {
    return (
      <div className="p-8 text-center max-w-xl mx-auto">
        <p className="text-base font-bold text-foreground">Program not found</p>
        <Link
          to="/operations/programs"
          className="mt-3 inline-flex items-center gap-1.5 text-sm font-bold text-primary hover:underline"
        >
          <ArrowLeft size={14} /> Back to Programs
        </Link>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5 sp-wireframe">
      <div className="sp-wireframe-header relative overflow-hidden -mx-4 -mt-4 sm:-mx-6 sm:-mt-6 lg:-mx-10 lg:-mt-10 px-4 sm:px-6 lg:px-10 pt-5 bg-[#231134] text-white">
        <img
          src="/space-logo-white.png"
          alt=""
          aria-hidden="true"
          className="pointer-events-none select-none absolute bottom-0 right-6 w-48 sm:w-64 opacity-10"
        />

        <div className="relative z-10">
          <Link
            to="/operations/programs"
            className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-white/75 hover:text-white transition-colors mb-4"
          >
            <ArrowLeft size={14} /> Programs
          </Link>

          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="min-w-0 space-y-3">
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-2xl font-bold tracking-tight text-white">
                  {program.name}
                </h1>
                {!program.active && (
                  <span className="px-2.5 py-0.5 rounded-[10px] text-xs font-semibold bg-[#4b3b5c] text-white">
                    Inactive
                  </span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-white/85">
                <div className="inline-flex items-center gap-1.5">
                  <span className="text-white/55">Code:</span>
                  <span className="font-medium text-white">{program.code}</span>
                </div>
                <div className="inline-flex items-center gap-1.5">
                  <span className="text-white/55">Type:</span>
                  <span className="font-medium text-white">{PROGRAM_TYPE_LABEL[program.program_type]}</span>
                </div>
                <div className="inline-flex items-center gap-1.5">
                  <span className="text-white/55">Pricing:</span>
                  <span className="font-medium text-white">
                    {program.pricing_model === "free"
                      ? "Free"
                      : program.price != null
                        ? `${program.price} AED`
                        : "Paid"}
                  </span>
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-2 shrink-0 sm:min-w-[210px]">
              <Link
                to="/operations/cohorts/new"
                search={{ programId: program.id }}
                className="flex items-center justify-center gap-1.5 w-full h-9 px-4 rounded-[10px] bg-[#653F84] border-0 text-sm font-medium text-white hover:opacity-90 transition-opacity cursor-pointer"
              >
                <Plus size={14} /> Add Cohort
              </Link>

              <div className={`grid gap-2 ${cohorts.length === 0 ? "grid-cols-2" : "grid-cols-1"}`}>
                <button
                  type="button"
                  onClick={() => setEditOpen(true)}
                  className="flex items-center justify-center gap-1.5 h-9 px-3 bg-transparent border-2 border-solid border-[#D7D2CB] rounded-[10px] text-xs font-medium text-white hover:bg-white/10 transition-colors cursor-pointer"
                >
                  <Pencil size={13} /> Edit
                </button>
                {cohorts.length === 0 && (
                  <button
                    type="button"
                    onClick={() => {
                      if (confirm(`Delete the program "${program.name}"?`)) {
                        deleteMutation.mutate()
                      }
                    }}
                    disabled={deleteMutation.isPending}
                    className="flex items-center justify-center gap-1.5 h-9 px-3 bg-transparent border-2 border-solid border-[#D7D2CB] rounded-[10px] text-xs font-medium text-rose-300 hover:bg-rose-500/15 transition-colors shrink-0 disabled:opacity-50 cursor-pointer"
                  >
                    <Trash2 size={13} /> Delete
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 mt-5 pb-4">
            <CounterChip
              label="Cohorts"
              value={cohorts.length}
              onClick={() => setActiveTab("cohorts")}
            />
            <CounterChip
              label="Running"
              value={runningCohorts.length}
              onClick={() => setActiveTab("cohorts")}
            />
            <CounterChip
              label="Open"
              value={openCohorts.length}
              onClick={() => setActiveTab("cohorts")}
            />
          </div>

          <div
            className="flex items-center gap-1 border-b border-white/15 overflow-x-auto scrollbar-none no-scrollbar"
            role="tablist"
          >
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={activeTab === t.key}
                onClick={() => setActiveTab(t.key)}
                className={`h-9 px-3 -mb-px border-b-2 text-sm font-medium transition-colors shrink-0 whitespace-nowrap cursor-pointer ${activeTab === t.key
                  ? "border-[#D7D2CB] text-white"
                  : "border-transparent text-white/70 hover:text-white"
                  }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── TAB 1: COHORTS & MATERIALS ─────────────────────────────── */}
      {activeTab === "cohorts" && (
        <div className="space-y-6">
          {cohorts.length === 0 ? (
            <div className="p-12 text-center rounded-[10px] border border-dashed border-border bg-card">
              <p className="text-base font-bold text-foreground">No cohorts scheduled</p>
              <Link
                to="/operations/cohorts/new"
                search={{ programId: program.id }}
                className="mt-3 inline-flex items-center gap-1.5 h-9 px-4 rounded-[10px] bg-primary text-primary-foreground text-sm font-bold hover:opacity-90 transition-colors cursor-pointer"
              >
                <Plus size={15} /> Launch First Cohort
              </Link>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Running */}
              {runningCohorts.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" />
                    <h3 className="text-xs font-extrabold uppercase tracking-wider text-muted-foreground">
                      Running Now ({runningCohorts.length})
                    </h3>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {runningCohorts.map((c) => (
                      <CohortDetailCard
                        key={c.id}
                        cohort={c}
                        onEdit={() => setEditingCohort(c)}
                        onDelete={() => {
                          if (confirm(`Delete cohort "${c.name}"?`)) {
                            deleteCohortMutation.mutate(c.id)
                          }
                        }}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Open & Upcoming */}
              {openCohorts.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="w-2.5 h-2.5 rounded-full bg-primary inline-block" />
                    <h3 className="text-xs font-extrabold uppercase tracking-wider text-muted-foreground">
                      Registration Open & Upcoming ({openCohorts.length})
                    </h3>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {openCohorts.map((c) => (
                      <CohortDetailCard
                        key={c.id}
                        cohort={c}
                        onEdit={() => setEditingCohort(c)}
                        onDelete={() => {
                          if (confirm(`Delete cohort "${c.name}"?`)) {
                            deleteCohortMutation.mutate(c.id)
                          }
                        }}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Past & Completed */}
              {pastCohorts.length > 0 && (
                <div className="pt-2 border-t border-border">
                  <button
                    type="button"
                    onClick={() => setExpandedPast((v) => !v)}
                    className="inline-flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                  >
                    <span className="w-2.5 h-2.5 rounded-full bg-muted-foreground/60 inline-block" />
                    <span>Past & Completed ({pastCohorts.length} Cohorts)</span>
                    {expandedPast ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </button>

                  {expandedPast && (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mt-3">
                      {pastCohorts.map((c) => (
                        <CohortDetailCard
                          key={c.id}
                          cohort={c}
                          onEdit={() => setEditingCohort(c)}
                          onDelete={() => {
                            if (confirm(`Delete cohort "${c.name}"?`)) {
                              deleteCohortMutation.mutate(c.id)
                            }
                          }}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          <div className="rounded-[10px] border border-border bg-card p-6">
            <MaterialsPanel owner={{ program_id: program.id }} />
          </div>
        </div>
      )}

      {/* ── TAB 2: INSTRUCTORS (ROLES & ASSESSMENT GATE) ────────────── */}
      {activeTab === "instructors" && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-1.5 flex-wrap">
            {(
              [
                ["roles", "Roles & Staffing"],
                ["assessment", "Assessment Gate"],
                ["prequiz", "Pre-Session Quiz"],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                type="button"
                onClick={() => setInstructorSub(k)}
                className={`h-9 px-3.5 rounded-[10px] border text-sm font-medium transition-colors cursor-pointer ${instructorSub === k
                  ? "bg-primary/10 border-primary/40 text-primary font-semibold"
                  : "border-border bg-card text-muted-foreground hover:text-foreground"
                  }`}
              >
                {label}
              </button>
            ))}
          </div>

          {instructorSub === "roles" && (
            <div className="rounded-[10px] border border-border bg-card p-6">
              <ProgramRolesPanel program={program} />
            </div>
          )}

          {instructorSub === "assessment" && (
            <div className="rounded-[10px] border border-border bg-card p-6">
              <ProgramAssessmentDefaultPanel
                program={program}
                onUpdated={() =>
                  queryClient.invalidateQueries({ queryKey: ["sessions-program", programId] })
                }
              />
            </div>
          )}

          {instructorSub === "prequiz" && (
            <div className="rounded-[10px] border border-border bg-card p-6">
              <PreSessionQuizAssignmentBar scope="programs" ownerId={program.id} />
            </div>
          )}
        </div>
      )}

      {/* ── TAB 3: LMS AUTHORING ───────────────────────────────────── */}
      {activeTab === "lms" && <ProgramLmsSection program={program} />}

      {/* ── TAB 4: CERTIFICATES ────────────────────────────────────── */}
      {activeTab === "certificates" && (
        <ProgramCertificateStudioModal
          program={program}
          embedded
          onUpdated={() => {
            queryClient.invalidateQueries({ queryKey: ["sessions-program", programId] })
          }}
        />
      )}

      {/* ── MODALS ─────────────────────────────────────────────────── */}
      {editingCohort && (
        <CohortModal
          programs={[program]}
          cohort={editingCohort}
          onClose={() => setEditingCohort(null)}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ["sessions-cohorts"] })
            setEditingCohort(null)
          }}
        />
      )}

      {editOpen && (
        <Modal
          title="Edit Program"
          onClose={() => setEditOpen(false)}
          maxWidth="max-w-2xl"
        >
          <ProgramSetupForm
            program={program}
            onSuccess={() => setEditOpen(false)}
          />
        </Modal>
      )}
    </div>
  )
}

/* ── COHORT CARD (Inside Program Detail) ─────────────────────────── */
function CohortDetailCard({
  cohort: c,
  onEdit,
  onDelete,
}: {
  cohort: Cohort
  onEdit: () => void
  onDelete: () => void
}) {
  const registered = c.registrations_count ?? 0
  const fillPct = c.capacity ? Math.min(100, Math.round((registered / c.capacity) * 100)) : null
  const unstaffed = c.unstaffed_count ?? 0

  return (
    <SubCard className="flex flex-col justify-between gap-3">
      <div>
        <div className="flex items-start justify-between gap-2 mb-2">
          <Link
            to="/operations/cohorts/$cohortId"
            params={{ cohortId: c.id }}
            search={{ from: `/operations/programs/${c.program_id}` } as never}
            className="text-sm font-bold text-foreground hover:text-primary transition-colors truncate block"
          >
            {c.name}
          </Link>
          <CohortStatusBadge status={c.status} />
        </div>

        {unstaffed > 0 && (
          <div className="mb-2">
            <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-rose-500 text-white">
              {unstaffed} unstaffed
            </span>
          </div>
        )}

        <div className="space-y-1.5 text-xs text-muted-foreground mt-2">
          <div className="flex items-center gap-1.5 truncate">
            <Calendar size={13} className="shrink-0" />
            <span className="truncate">
              {c.starts_on
                ? `${c.starts_on}${c.ends_on && c.ends_on !== c.starts_on ? ` – ${c.ends_on}` : ""}`
                : "Dates unassigned"}
            </span>
          </div>

          <div className="flex items-center gap-1.5 truncate">
            <MapPin size={13} className="shrink-0" />
            <span className="truncate">{c.location_name ?? c.location ?? "Venue unassigned"}</span>
          </div>

          <div className="flex items-center gap-1.5 truncate">
            <Users size={13} className="shrink-0" />
            <span className="truncate">
              {registered}
              {c.capacity != null ? ` / ${c.capacity}` : ""} Registered
            </span>
          </div>
        </div>

        {fillPct != null && (
          <div className="mt-2.5">
            <div className="h-1.5 w-full rounded-[10px] bg-muted overflow-hidden">
              <div
                className={`h-full rounded-[10px] ${fillPct >= 100 ? "bg-rose-500" : "bg-primary"
                  }`}
                style={{ width: `${fillPct}%` }}
              />
            </div>
          </div>
        )}
      </div>

      <div className="pt-3 border-t border-border flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <button
            onClick={onEdit}
            className="p-1 rounded-[10px] text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            title="Edit Cohort"
          >
            <Pencil size={13} />
          </button>
          <button
            onClick={onDelete}
            className="p-1 rounded-[10px] text-muted-foreground hover:text-rose-600 hover:bg-rose-500/10 transition-colors"
            title="Delete Cohort"
          >
            <Trash2 size={13} />
          </button>
        </div>

        <Link
          to="/operations/cohorts/$cohortId"
          params={{ cohortId: c.id }}
          search={{ from: `/operations/programs/${c.program_id}` } as never}
          className="text-xs font-bold text-primary hover:underline inline-flex items-center gap-1"
        >
          Manage <ArrowRight size={12} />
        </Link>
      </div>
    </SubCard>
  )
}

function CohortStatusBadge({ status }: { status: CohortStatus }) {
  if (status === "running") {
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-emerald-600 text-white">
        Running
      </span>
    )
  }
  if (status === "registration_open") {
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-primary text-white">
        Registration Open
      </span>
    )
  }
  if (status === "planned") {
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-muted text-white">
        Planned
      </span>
    )
  }
  if (status === "completed") {
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-foreground text-white">
        Completed
      </span>
    )
  }
  return (
    <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-rose-600 text-white">
      Cancelled
    </span>
  )
}

/* ── PROGRAM SETUP & DEFAULTS FORM ───────────────────────────────── */
function ProgramSetupForm({
  program,
  onSuccess,
}: {
  program: Program
  onSuccess?: () => void
}) {
  const toast = useToast()
  const queryClient = useQueryClient()

  const [code, setCode] = useState(program.code)
  const [name, setName] = useState(program.name)
  const [programType, setProgramType] = useState<ProgramType>(program.program_type)
  const [pricingModel, setPricingModel] = useState<PricingModel>(program.pricing_model)
  const [price, setPrice] = useState(program.price != null ? String(program.price) : "")
  const [durationHours, setDurationHours] = useState(
    program.duration_hours != null ? String(program.duration_hours) : ""
  )
  const [defaultCapacity, setDefaultCapacity] = useState(
    program.default_capacity != null ? String(program.default_capacity) : ""
  )
  const [description, setDescription] = useState(program.description ?? "")
  const [active, setActive] = useState(program.active)
  const [completionRuleType, setCompletionRuleType] = useState<CompletionRuleType>(
    program.completion_rule_type
  )
  const [completionRuleValue, setCompletionRuleValue] = useState(
    String(program.completion_rule_value)
  )
  const [posterTemplateUrl, setPosterTemplateUrl] = useState(
    program.poster_template_url ?? ""
  )
  const [keepCourseAccessAfterCompletion, setKeepCourseAccessAfterCompletion] = useState(
    program.keep_course_access_after_completion
  )
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () =>
      updateProgramApi(program.id, {
        code: code.trim(),
        name: name.trim(),
        program_type: programType,
        pricing_model: pricingModel,
        description: description.trim() || null,
        price: price.trim() ? Number(price) : null,
        duration_hours: durationHours.trim() ? Number(durationHours) : null,
        default_capacity: defaultCapacity.trim() ? Number(defaultCapacity) : null,
        active,
        completion_rule_type: completionRuleType,
        completion_rule_value: completionRuleValue.trim()
          ? Number(completionRuleValue)
          : undefined,
        poster_template_url: posterTemplateUrl.trim() || null,
        keep_course_access_after_completion: keepCourseAccessAfterCompletion,
      }),
    onSuccess: () => {
      setError("")
      toast.success("Program defaults updated")
      queryClient.invalidateQueries({ queryKey: ["sessions-program", program.id] })
      queryClient.invalidateQueries({ queryKey: ["sessions-programs"] })
      onSuccess?.()
    },
    onError: (e: unknown) =>
      setError(getErrorMessage(e, "Failed to update program defaults")),
  })

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        mutation.mutate()
      }}
      className="space-y-6 max-w-2xl"
    >
      <div>
        <h2 className="text-lg font-bold text-foreground">Blueprint Defaults</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          New cohorts generated under this program inherit these default parameters.
        </p>
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
            Program Code
          </label>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
            className="w-full h-10 px-3.5 rounded-[10px] border border-border bg-background text-foreground text-sm font-medium focus:outline-none focus:border-primary transition-colors"
          />
        </div>

        <div>
          <label className="block text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
            Program Name
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="w-full h-10 px-3.5 rounded-[10px] border border-border bg-background text-foreground text-sm font-medium focus:outline-none focus:border-primary transition-colors"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
              Type
            </label>
            <select
              value={programType}
              onChange={(e) => setProgramType(e.target.value as ProgramType)}
              className="w-full h-10 px-3 rounded-[10px] border border-border bg-background text-foreground text-sm font-medium focus:outline-none focus:border-primary cursor-pointer"
            >
              {PROGRAM_TYPES.map((t) => (
                <option key={t} value={t}>
                  {PROGRAM_TYPE_LABEL[t]}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
              Pricing Model
            </label>
            <select
              value={pricingModel}
              onChange={(e) => setPricingModel(e.target.value as PricingModel)}
              className="w-full h-10 px-3 rounded-[10px] border border-border bg-background text-foreground text-sm font-medium focus:outline-none focus:border-primary cursor-pointer"
            >
              {PRICING_MODELS.map((m) => (
                <option key={m} value={m}>
                  {PRICING_MODEL_LABEL[m]}
                </option>
              ))}
            </select>
          </div>
        </div>

        {pricingModel !== "free" && (
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
              Price (AED)
            </label>
            <input
              type="number"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="250"
              className="w-full h-10 px-3.5 rounded-[10px] border border-border bg-background text-foreground text-sm font-medium focus:outline-none focus:border-primary transition-colors"
            />
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
              Default Capacity
            </label>
            <input
              type="number"
              value={defaultCapacity}
              onChange={(e) => setDefaultCapacity(e.target.value)}
              placeholder="24"
              className="w-full h-10 px-3.5 rounded-[10px] border border-border bg-background text-foreground text-sm font-medium focus:outline-none focus:border-primary transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
              Default Session Duration (hrs)
            </label>
            <input
              type="number"
              step="0.5"
              min="0"
              value={durationHours}
              onChange={(e) => setDurationHours(e.target.value)}
              placeholder="e.g. 2"
              className="w-full h-10 px-3.5 rounded-[10px] border border-border bg-background text-foreground text-sm font-medium focus:outline-none focus:border-primary transition-colors"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
            Requirement
          </label>
          <div className="flex gap-2">
            <select
              value={completionRuleType}
              onChange={(e) =>
                setCompletionRuleType(e.target.value as CompletionRuleType)
              }
              className="w-28 h-10 px-2 rounded-[10px] border border-border bg-background text-foreground text-xs font-medium focus:outline-none focus:border-primary cursor-pointer"
            >
              <option value="percentage">%</option>
              <option value="session_count">Sessions</option>
            </select>
            <input
              type="number"
              value={completionRuleValue}
              onChange={(e) => setCompletionRuleValue(e.target.value)}
              className="flex-1 h-10 px-3 rounded-[10px] border border-border bg-background text-foreground text-sm font-medium focus:outline-none focus:border-primary"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
            Poster Template Link
          </label>
          <input
            type="url"
            value={posterTemplateUrl}
            onChange={(e) => setPosterTemplateUrl(e.target.value)}
            placeholder="https://canva.com/design/..."
            className="w-full h-10 px-3.5 rounded-[10px] border border-border bg-background text-foreground text-sm font-medium focus:outline-none focus:border-primary transition-colors"
          />
        </div>

        <div>
          <label className="block text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
            Description
          </label>
          <textarea
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Program overview and objectives..."
            className="w-full p-3 rounded-[10px] border border-border bg-background text-foreground text-sm font-medium focus:outline-none focus:border-primary resize-none transition-colors"
          />
        </div>

        <div className="flex items-center gap-6 pt-2">
          <label className="flex items-center gap-2 text-sm font-bold text-foreground cursor-pointer select-none">
            <input
              type="checkbox"
              checked={keepCourseAccessAfterCompletion}
              onChange={(e) => setKeepCourseAccessAfterCompletion(e.target.checked)}
              className="rounded-[4px] accent-primary"
            />
            Keep course access after completion
          </label>

          <label className="flex items-center gap-2 text-sm font-bold text-foreground cursor-pointer select-none">
            <input
              type="checkbox"
              checked={active}
              onChange={(e) => setActive(e.target.checked)}
              className="rounded-[4px] accent-primary"
            />
            Active
          </label>
        </div>
      </div>

      {error && (
        <p className="p-3 rounded-[10px] text-sm font-medium bg-rose-500/15 text-rose-600 dark:text-rose-400 border border-rose-500/30">
          {error}
        </p>
      )}

      <div className="pt-4 border-t border-border">
        <button
          type="submit"
          disabled={mutation.isPending || !code.trim() || !name.trim()}
          className="h-10 px-6 rounded-[10px] bg-primary text-primary-foreground text-sm font-bold hover:opacity-90 transition-colors disabled:opacity-50"
        >
          {mutation.isPending ? "Saving..." : "Save Blueprint Defaults"}
        </button>
      </div>
    </form>
  )
}
