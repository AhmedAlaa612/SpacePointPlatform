import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "@tanstack/react-router"
import {
  AlertCircle,
  ArrowRight,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Copy,
  ExternalLink,
  Globe,
  Layers,
  MapPin,
  Pencil,
  Plus,
  Search,
  SlidersHorizontal,
  Trash2,
  Users,
} from "lucide-react"

import {
  createOrgProgramApi,
  deleteOrgProgramApi,
  duplicateOrgCohortApi,
  getOrgProgramsOverviewApi,
  updateOrgProgramApi,
  type OrgCohortSummary,
  type OrgProgramSummary,
  type OrgQuotas,
} from "@/api/organizationPrograms"
import {
  OrgCohortModal,
  type OrgCohortModalEditable,
} from "@/components/organization/OrgCohortModal"
import { useToast } from "@/components/ui/toast"
import { useAuth } from "@/context/AuthContext"
import { cn, getErrorMessage } from "@/lib/utils"

const PROGRAM_TYPE_LABEL: Record<string, string> = {
  competition: "Competition",
  workshop: "Workshop",
  course: "Course",
  info_session: "Info Session",
  internship: "Internship",
}

function CohortStatusBadge({ status }: { status?: string | null }) {
  const s = (status || "planned").toLowerCase()
  if (s === "running") {
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-emerald-600 text-white shrink-0">
        Running
      </span>
    )
  }
  if (s === "registration_open") {
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-primary text-white shrink-0">
        Registration Open
      </span>
    )
  }
  if (s === "completed") {
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-foreground text-background shrink-0">
        Completed
      </span>
    )
  }
  if (s === "cancelled") {
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-rose-600 text-white shrink-0">
        Cancelled
      </span>
    )
  }
  return (
    <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-muted text-muted-foreground shrink-0">
      Planned
    </span>
  )
}

function formatCohortDates(cohort: OrgCohortSummary): string {
  const s = cohort.starts_on || cohort.start_date
  const e = cohort.ends_on || cohort.end_date
  if (!s && !e) return "Dates unassigned"
  if (s && e && s !== e) return `${s} – ${e}`
  return s || e || "Dates unassigned"
}

export default function OrganizationPrograms() {
  const navigate = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const { activeRole, activeOrgRole } = useAuth()

  useEffect(() => {
    if (activeRole !== "organization") return
    if (activeOrgRole === "instructor") {
      void navigate({ to: "/organization/my-sessions", replace: true })
    } else if (activeOrgRole === "judge") {
      void navigate({ to: "/organization/judging", replace: true })
    }
  }, [activeRole, activeOrgRole, navigate])

  const [viewMode, setViewMode] = useState<"programs" | "worklist">("programs")
  const [search, setSearch] = useState("")
  const [typeFilter, setTypeFilter] = useState("all")
  const [statusFilter, setStatusFilter] = useState("all")
  const [collapsedPrograms, setCollapsedPrograms] = useState<Record<string, boolean>>({})
  const [expandedPastByProg, setExpandedPastByProg] = useState<Record<string, boolean>>({})

  const [createProgramOpen, setCreateProgramOpen] = useState(false)
  const [editingProgram, setEditingProgram] = useState<OrgProgramSummary | null>(null)
  const [cohortModalOpen, setCohortModalOpen] = useState(false)
  const [cohortDefaultProgramId, setCohortDefaultProgramId] = useState<string | undefined>(undefined)
  const [editingCohort, setEditingCohort] = useState<OrgCohortModalEditable | null>(null)
  const [duplicateTargetCohort, setDuplicateTargetCohort] = useState<OrgCohortSummary | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ["org-programs-overview"],
    queryFn: getOrgProgramsOverviewApi,
    enabled:
      activeRole !== "organization" ||
      (activeOrgRole !== "instructor" && activeOrgRole !== "judge"),
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["org-programs-overview"] })
    void qc.invalidateQueries({ queryKey: ["sessions-cohorts"] })
  }

  const deleteProgramMut = useMutation({
    mutationFn: (id: string) => deleteOrgProgramApi(id),
    onSuccess: () => {
      toast.success("Program deleted")
      invalidate()
    },
    onError: (err) => {
      toast.error(getErrorMessage(err, "Failed to delete program"))
    },
  })

  const programs = data?.programs ?? []
  const isObserver = activeOrgRole === "observer"

  const filteredPrograms = useMemo(() => {
    const q = search.trim().toLowerCase()
    return programs
      .filter((p) => typeFilter === "all" || p.program_type === typeFilter)
      .map((p) => {
        const progMatches =
          !q ||
          p.name.toLowerCase().includes(q) ||
          p.code.toLowerCase().includes(q) ||
          p.program_type.toLowerCase().includes(q)

        const matchingCohorts = p.cohorts.filter((c) => {
          const cStatus = (c.status || "planned").toLowerCase()
          if (statusFilter !== "all" && cStatus !== statusFilter) return false
          if (!q || progMatches) return true
          return (
            c.name.toLowerCase().includes(q) ||
            (c.location_name || c.location || "").toLowerCase().includes(q) ||
            (c.variation_name || "").toLowerCase().includes(q)
          )
        })

        if (statusFilter !== "all" && matchingCohorts.length === 0) {
          return null
        }
        if (q && !progMatches && matchingCohorts.length === 0) {
          return null
        }

        return {
          ...p,
          visibleCohorts: matchingCohorts,
        }
      })
      .filter((p): p is OrgProgramSummary & { visibleCohorts: OrgCohortSummary[] } => p !== null)
  }, [programs, search, typeFilter, statusFilter])

  const worklistCohorts = useMemo(() => {
    const statusOrder: Record<string, number> = {
      running: 0,
      registration_open: 1,
      planned: 2,
      completed: 3,
      cancelled: 4,
    }
    const items = filteredPrograms.flatMap((p) =>
      p.visibleCohorts.map((c) => ({
        cohort: c,
        program: p,
      })),
    )
    items.sort((a, b) => {
      const sa = statusOrder[(a.cohort.status || "planned").toLowerCase()] ?? 9
      const sb = statusOrder[(b.cohort.status || "planned").toLowerCase()] ?? 9
      if (sa !== sb) return sa - sb
      return (a.cohort.starts_on || a.cohort.start_date || "9999").localeCompare(
        b.cohort.starts_on || b.cohort.start_date || "9999",
      )
    })
    return items
  }, [filteredPrograms])

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
  const cohortsQuotaReached =
    quotas.max_cohorts !== null && quotas.cohorts_count >= quotas.max_cohorts
  const canLaunchAnyCohort = programs.some((p) => p.can_create_cohort ?? p.is_org_owned !== false)

  const openCreateCohort = (programId?: string) => {
    setEditingCohort(null)
    setCohortDefaultProgramId(programId)
    setCohortModalOpen(true)
  }

  const openEditCohort = (c: OrgCohortSummary) => {
    setEditingCohort({
      id: c.id,
      program_id: c.program_id,
      name: c.name,
      starts_on: c.starts_on ?? c.start_date ?? null,
      ends_on: c.ends_on ?? c.end_date ?? null,
      start_date: c.start_date,
      end_date: c.end_date,
      location_id: c.location_id ?? null,
      location: c.location ?? null,
      capacity: c.capacity ?? null,
      duration_hours: c.duration_hours ?? null,
      visibility: c.visibility ?? (c.is_public ? "public" : "private"),
      is_public: c.is_public,
      status: c.status,
      variation_id: c.variation_id ?? null,
      checklist_title_override: c.checklist_title_override ?? null,
      coordinator_access_mode: c.coordinator_access_mode ?? "general",
      coordinators: c.coordinators ?? [],
    })
    setCohortDefaultProgramId(c.program_id)
    setCohortModalOpen(true)
  }

  return (
    <div className="flex flex-col gap-5 max-w-6xl mx-auto pb-12">
      {/* ── Top Header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-xl font-bold tracking-tight text-foreground">
              {org.name_latin} · Programs &amp; Cohorts
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
            Configure program defaults, launch student cohorts, and monitor both partner-run and SpacePoint-delivered cohorts.
          </p>
        </div>

        {!isObserver && (
          <div className="flex items-center gap-2 flex-wrap">
            {canLaunchAnyCohort && (
              <button
                type="button"
                disabled={cohortsQuotaReached || !org.is_approved}
                onClick={() => openCreateCohort(undefined)}
                title={!org.is_approved ? "Account under review by Operations" : undefined}
                className="inline-flex items-center justify-center gap-1.5 h-9 px-3.5 rounded-xl border border-border bg-card text-foreground text-xs font-semibold hover:bg-muted transition disabled:opacity-50 cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5 text-primary" /> New Cohort
              </button>
            )}
            <button
              type="button"
              disabled={programsQuotaReached || !org.is_approved}
              onClick={() => setCreateProgramOpen(true)}
              title={!org.is_approved ? "Account under review by Operations" : undefined}
              className="inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50 cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" /> New Program
            </button>
          </div>
        )}
      </div>

      {/* ── Under Review / Observer Banners ────────────────────────────────── */}
      {!org.is_approved && (
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-5 flex items-start gap-3.5">
          <AlertCircle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-foreground">Account Under Review</h3>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Your partner organization account is currently under review by SpacePoint Operations. During review, program creation and hosting limits are locked until verification is completed.
            </p>
          </div>
        </div>
      )}

      {isObserver && (
        <div className="rounded-2xl border border-border bg-muted/40 px-4 py-3 text-xs text-muted-foreground">
          You are viewing as an <strong className="text-foreground">Organization Observer</strong>. All program configurations and cohorts are read-only.
        </div>
      )}

      {/* ── Quotas Strip ───────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-xl border border-border bg-card p-3.5 flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Owned Programs
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
            Partner Cohorts
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

      {/* ── Filter & View Mode Controls (Matches SpacePoint Programs.tsx) ─── */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center justify-between gap-3">
        <div className="flex flex-wrap flex-1 items-center gap-2 min-w-0">
          <div className="relative w-full sm:flex-1 sm:min-w-[200px]">
            <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search program, cohort, or venue..."
              className="w-full h-10 pl-10 pr-8 rounded-[10px] border border-border bg-card text-foreground text-sm font-medium focus:outline-none focus:border-primary transition-colors"
            />
          </div>

          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="flex-1 sm:flex-none sm:w-44 shrink-0 h-10 px-3 rounded-[10px] border border-border bg-card text-foreground text-sm font-medium focus:outline-none focus:border-primary transition-colors cursor-pointer"
          >
            <option value="all">All Types</option>
            <option value="workshop">Workshop</option>
            <option value="course">Course</option>
            <option value="info_session">Info session</option>
            <option value="competition">Competition</option>
          </select>

          {viewMode === "worklist" && (
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="flex-1 sm:flex-none sm:w-44 shrink-0 h-10 px-3 rounded-[10px] border border-border bg-card text-foreground text-sm font-medium focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              <option value="all">All Statuses</option>
              <option value="running">Running</option>
              <option value="registration_open">Registration open</option>
              <option value="planned">Planned</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          )}
        </div>

        <div className="inline-flex self-start sm:self-auto shrink-0 p-1 rounded-[10px] bg-muted/60 border border-border">
          <button
            type="button"
            onClick={() => setViewMode("programs")}
            className={cn(
              "inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] text-xs font-bold transition-all cursor-pointer",
              viewMode === "programs"
                ? "bg-background text-foreground shadow-xs"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Layers className="w-3.5 h-3.5" /> Program View
          </button>
          <button
            type="button"
            onClick={() => setViewMode("worklist")}
            className={cn(
              "inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] text-xs font-bold transition-all cursor-pointer",
              viewMode === "worklist"
                ? "bg-background text-foreground shadow-xs"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" /> Cohort View
          </button>
        </div>
      </div>

      {/* ── Main Content ────────────────────────────────────────────────────── */}
      {programs.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-12 text-center flex flex-col items-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-primary/10 text-primary flex items-center justify-center">
            <Layers className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-foreground">No programs yet</h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-sm">
              Create your first program to configure default sessions, checklists, and LMS modules, or ask SpacePoint Operations to share a SpacePoint program with your organization.
            </p>
          </div>
          {!isObserver && (
            <button
              type="button"
              disabled={programsQuotaReached || !org.is_approved}
              onClick={() => setCreateProgramOpen(true)}
              className="mt-2 inline-flex items-center gap-1.5 h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50 cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" /> Create Program
            </button>
          )}
        </div>
      ) : filteredPrograms.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-10 text-center text-xs text-muted-foreground">
          No programs or cohorts match your current search/filters.
        </div>
      ) : viewMode === "worklist" ? (
        /* ── Worklist View ───────────────────────────────────────────────── */
        <div className="rounded-2xl border border-border bg-card overflow-hidden shadow-sm">
          {worklistCohorts.length === 0 ? (
            <div className="p-10 text-center text-xs text-muted-foreground">
              No cohorts match the current filters.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-border bg-muted/30 text-muted-foreground">
                    <th className="py-3 px-4 font-semibold uppercase">Cohort</th>
                    <th className="py-3 px-4 font-semibold uppercase">Program</th>
                    <th className="py-3 px-4 font-semibold uppercase">Delivery</th>
                    <th className="py-3 px-4 font-semibold uppercase">Status</th>
                    <th className="py-3 px-4 font-semibold uppercase">Dates &amp; Venue</th>
                    <th className="py-3 px-4 font-semibold uppercase">Enrolled</th>
                    <th className="py-3 px-4 text-right font-semibold uppercase">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {worklistCohorts.map(({ cohort, program }) => {
                    const venue = cohort.location_name || cohort.location || "Venue unassigned"
                    const isModeB = cohort.management_mode === "spacepoint"
                    return (
                      <tr key={cohort.id} className="hover:bg-muted/30 transition-colors">
                        <td className="py-3 px-4">
                          <Link
                            to="/organization/programs/$cohortId"
                            params={{ cohortId: cohort.id }}
                            className="font-bold text-foreground hover:text-primary transition-colors block"
                          >
                            {cohort.name}
                          </Link>
                          <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                            {cohort.variation_name && (
                              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                                {cohort.variation_name}
                              </span>
                            )}
                            {!isModeB && (cohort.unstaffed_count ?? 0) > 0 && (
                              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-rose-500 text-white">
                                {cohort.unstaffed_count} unstaffed
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <Link
                            to="/organization/programs/manage/$programId"
                            params={{ programId: program.id }}
                            className="text-foreground hover:text-primary font-medium transition-colors"
                          >
                            {program.name}
                          </Link>
                          <div className="text-[11px] text-muted-foreground font-mono">
                            {program.code}
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          {isModeB ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-violet-500/15 text-violet-600 dark:text-violet-300 border border-violet-500/30">
                              Delivered by SpacePoint
                            </span>
                          ) : (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/20">
                              Partner-run
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex flex-col items-start gap-1">
                            <CohortStatusBadge status={cohort.status} />
                            {cohort.coordinator_access_mode === "assigned" && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20">
                                Assigned ({cohort.coordinators?.length ?? 0})
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-4 text-muted-foreground">
                          <div className="flex items-center gap-1">
                            <Calendar className="w-3 h-3 shrink-0" />
                            <span>{formatCohortDates(cohort)}</span>
                          </div>
                          <div className="flex items-center gap-1 mt-0.5">
                            <MapPin className="w-3 h-3 shrink-0" />
                            <span className="truncate max-w-[180px]">{venue}</span>
                          </div>
                        </td>
                        <td className="py-3 px-4 font-medium text-foreground">
                          {cohort.active_students_count}
                          {cohort.capacity != null ? ` / ${cohort.capacity}` : ""}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className="inline-flex items-center gap-1.5">
                            {!isObserver && (
                              <button
                                type="button"
                                onClick={() => openEditCohort(cohort)}
                                className="p-1.5 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition cursor-pointer"
                                title="Edit cohort"
                              >
                                <Pencil className="w-3 h-3" />
                              </button>
                            )}
                            <Link
                              to="/organization/programs/$cohortId"
                              params={{ cohortId: cohort.id }}
                              className="inline-flex items-center gap-1 h-7 px-2.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 font-semibold transition"
                            >
                              Manage <ArrowRight className="w-3 h-3" />
                            </Link>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        /* ── Program View ────────────────────────────────────────────────── */
        <div className="space-y-5">
          {filteredPrograms.map((program) => {
            const isOrgOwnedProgram = program.is_org_owned !== false
            const canCreateUnderProg =
              !isObserver && (program.can_create_cohort ?? isOrgOwnedProgram)
            const isCollapsed = Boolean(collapsedPrograms[program.id])

            const cohortsList = program.visibleCohorts
            const runningCohorts = cohortsList.filter(
              (c) => (c.status || "planned").toLowerCase() === "running",
            )
            const openCohorts = cohortsList.filter((c) => {
              const s = (c.status || "planned").toLowerCase()
              return s === "registration_open" || s === "planned"
            })
            const pastCohorts = cohortsList.filter((c) => {
              const s = (c.status || "planned").toLowerCase()
              return s === "completed" || s === "cancelled"
            })
            const pastExpanded =
              Boolean(expandedPastByProg[program.id]) ||
              statusFilter === "completed" ||
              statusFilter === "cancelled"

            return (
              <div
                key={program.id}
                className="rounded-2xl border border-border bg-card shadow-sm overflow-hidden"
              >
                {/* Program Header */}
                <div className="p-4 sm:p-5 border-b border-border bg-muted/20 flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <button
                        type="button"
                        onClick={() =>
                          setCollapsedPrograms((prev) => ({
                            ...prev,
                            [program.id]: !prev[program.id],
                          }))
                        }
                        className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition cursor-pointer"
                        title={isCollapsed ? "Expand cohorts" : "Collapse cohorts"}
                      >
                        {isCollapsed ? (
                          <ChevronRight className="w-4 h-4" />
                        ) : (
                          <ChevronDown className="w-4 h-4" />
                        )}
                      </button>

                      <Link
                        to="/organization/programs/manage/$programId"
                        params={{ programId: program.id }}
                        className="text-base font-bold text-foreground hover:text-primary transition-colors truncate"
                      >
                        {program.name}
                      </Link>

                      <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-muted text-muted-foreground uppercase">
                        {program.code}
                      </span>
                      <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                        {PROGRAM_TYPE_LABEL[program.program_type] ?? program.program_type}
                      </span>
                      {program.active === false && (
                        <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                          Inactive
                        </span>
                      )}
                      {program.is_shared_program ? (
                        <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30">
                          Shared by SpacePoint
                        </span>
                      ) : (
                        !isOrgOwnedProgram && (
                          <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-700 dark:text-violet-300">
                            SpacePoint Program
                          </span>
                        )
                      )}
                    </div>

                    {program.description && (
                      <p className="text-xs text-muted-foreground mt-1 ml-7 line-clamp-1">
                        {program.description}
                      </p>
                    )}

                    <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap pt-1.5 ml-7">
                      <span>
                        Default Capacity:{" "}
                        <strong className="text-foreground">
                          {program.default_capacity ? `${program.default_capacity} students` : "Unlimited"}
                        </strong>
                      </span>
                      {program.duration_hours != null && (
                        <>
                          <span>·</span>
                          <span>
                            Session:{" "}
                            <strong className="text-foreground">{program.duration_hours}h</strong>
                          </span>
                        </>
                      )}
                      <span>·</span>
                      <span>
                        Cohorts: <strong className="text-foreground">{cohortsList.length}</strong>
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 flex-wrap ml-7 lg:ml-0">
                    <Link
                      to="/organization/programs/manage/$programId"
                      params={{ programId: program.id }}
                      className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-border bg-background text-xs font-semibold text-foreground hover:border-primary/50 hover:text-primary transition"
                    >
                      <SlidersHorizontal className="w-3.5 h-3.5 text-primary" />
                      {isOrgOwnedProgram && !isObserver ? "Manage Program" : "View Defaults"}
                    </Link>

                    {canCreateUnderProg && (
                      <button
                        type="button"
                        disabled={cohortsQuotaReached || !org.is_approved}
                        onClick={() => openCreateCohort(program.id)}
                        className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50 cursor-pointer"
                      >
                        <Plus className="w-3.5 h-3.5" /> Add Cohort
                      </button>
                    )}

                    {!isObserver && isOrgOwnedProgram && (
                      <>
                        <button
                          type="button"
                          onClick={() => setEditingProgram(program)}
                          className="inline-flex items-center gap-1 h-8 px-2.5 rounded-lg border border-border bg-background text-xs font-medium text-foreground hover:bg-muted transition cursor-pointer"
                          title="Quick Edit Program"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        {program.cohorts.length === 0 && (
                          <button
                            type="button"
                            onClick={() => {
                              if (window.confirm(`Delete program "${program.name}"?`)) {
                                deleteProgramMut.mutate(program.id)
                              }
                            }}
                            className="inline-flex items-center justify-center h-8 w-8 rounded-lg border border-border bg-background text-muted-foreground hover:text-destructive transition cursor-pointer"
                            title="Delete Program"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </div>

                {/* Cohorts Sections */}
                {!isCollapsed && (
                  <div className="p-5 sm:p-6 space-y-6">
                    {cohortsList.length === 0 ? (
                      <div className="py-8 text-center rounded-[10px] border border-dashed border-border bg-muted/10">
                        <p className="text-sm font-semibold text-muted-foreground">
                          No cohorts scheduled under this program yet.
                        </p>
                        {canCreateUnderProg && (
                          <button
                            type="button"
                            disabled={cohortsQuotaReached || !org.is_approved}
                            onClick={() => openCreateCohort(program.id)}
                            className="mt-3 inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-colors disabled:opacity-50 cursor-pointer"
                          >
                            <Plus className="w-3.5 h-3.5" /> Launch First Cohort
                          </button>
                        )}
                      </div>
                    ) : (
                      <>
                        {runningCohorts.length > 0 && (
                          <div>
                            <div className="flex items-center gap-2 mb-2.5">
                              <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />
                              <h3 className="text-[11px] font-extrabold uppercase tracking-wider text-muted-foreground">
                                Running Now ({runningCohorts.length})
                              </h3>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                              {runningCohorts.map((cohort) => (
                                <OrgCohortCard
                                  key={cohort.id}
                                  cohort={cohort}
                                  country={org.country || "ae"}
                                  isObserver={isObserver}
                                  isOrgOwnedProgram={isOrgOwnedProgram}
                                  onEdit={() => openEditCohort(cohort)}
                                  onDuplicate={() => setDuplicateTargetCohort(cohort)}
                                />
                              ))}
                            </div>
                          </div>
                        )}

                        {openCohorts.length > 0 && (
                          <div>
                            <div className="flex items-center gap-2 mb-2.5">
                              <span className="w-2 h-2 rounded-full bg-primary inline-block" />
                              <h3 className="text-[11px] font-extrabold uppercase tracking-wider text-muted-foreground">
                                Registration Open &amp; Upcoming ({openCohorts.length})
                              </h3>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                              {openCohorts.map((cohort) => (
                                <OrgCohortCard
                                  key={cohort.id}
                                  cohort={cohort}
                                  country={org.country || "ae"}
                                  isObserver={isObserver}
                                  isOrgOwnedProgram={isOrgOwnedProgram}
                                  onEdit={() => openEditCohort(cohort)}
                                  onDuplicate={() => setDuplicateTargetCohort(cohort)}
                                />
                              ))}
                            </div>
                          </div>
                        )}

                        {pastCohorts.length > 0 && (
                          <div className="pt-2 border-t border-border/70">
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedPastByProg((prev) => ({
                                  ...prev,
                                  [program.id]: !pastExpanded,
                                }))
                              }
                              className="inline-flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                            >
                              <span className="w-2 h-2 rounded-full bg-muted-foreground/60 inline-block" />
                              <span>Past &amp; Completed ({pastCohorts.length})</span>
                              {pastExpanded ? (
                                <ChevronDown className="w-3.5 h-3.5" />
                              ) : (
                                <ChevronRight className="w-3.5 h-3.5" />
                              )}
                            </button>

                            {pastExpanded && (
                              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mt-3">
                                {pastCohorts.map((cohort) => (
                                  <OrgCohortCard
                                    key={cohort.id}
                                    cohort={cohort}
                                    country={org.country || "ae"}
                                    isObserver={isObserver}
                                    isOrgOwnedProgram={isOrgOwnedProgram}
                                    onEdit={() => openEditCohort(cohort)}
                                    onDuplicate={() => setDuplicateTargetCohort(cohort)}
                                  />
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}
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

      {/* ── Create / Edit Cohort Modal ──────────────────────────────────────── */}
      <OrgCohortModal
        open={cohortModalOpen}
        onClose={() => {
          setCohortModalOpen(false)
          setEditingCohort(null)
        }}
        programs={programs}
        defaultProgramId={cohortDefaultProgramId}
        cohort={editingCohort}
        maxStudentsPerCohort={quotas.max_students_per_cohort}
        onSuccess={invalidate}
      />

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
    </div>
  )
}

function OrgCohortCard({
  cohort,
  country,
  isObserver,
  isOrgOwnedProgram,
  onEdit,
  onDuplicate,
}: {
  cohort: OrgCohortSummary
  country: string
  isObserver: boolean
  isOrgOwnedProgram: boolean
  onEdit: () => void
  onDuplicate: () => void
}) {
  const isModeB = cohort.management_mode === "spacepoint"
  const unstaffed = !isModeB ? (cohort.unstaffed_count ?? 0) : 0
  const fillPct =
    cohort.capacity != null && cohort.capacity > 0
      ? Math.min(100, Math.round((cohort.active_students_count / cohort.capacity) * 100))
      : null

  return (
    <div className="rounded-xl border border-border bg-background p-4 flex flex-col justify-between gap-3 hover:border-primary/40 transition group">
      <div>
        <div className="flex items-start justify-between gap-2 mb-2">
          <Link
            to="/organization/programs/$cohortId"
            params={{ cohortId: cohort.id }}
            className="text-sm font-bold text-foreground hover:text-primary transition-colors truncate block"
          >
            {cohort.name}
          </Link>
          <CohortStatusBadge status={cohort.status} />
        </div>

        <div className="flex items-center gap-1.5 flex-wrap mb-2">
          {cohort.variation_name && (
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
              {cohort.variation_name}
            </span>
          )}
          {isModeB && (
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-600 dark:text-violet-300 border border-violet-500/30">
              Delivered by SpacePoint
            </span>
          )}
          {cohort.is_public && (
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 inline-flex items-center gap-1">
              <Globe className="w-2.5 h-2.5" /> Public
            </span>
          )}
          {cohort.coordinator_access_mode === "assigned" && (
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20">
              Assigned ({cohort.coordinators?.length ?? 0})
            </span>
          )}
          {unstaffed > 0 && (
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-500 text-white">
              {unstaffed} unstaffed
            </span>
          )}
        </div>

        <div className="space-y-1.5 text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5 truncate">
            <Calendar className="w-3.5 h-3.5 shrink-0" />
            <span className="truncate">{formatCohortDates(cohort)}</span>
          </div>
          <div className="flex items-center gap-1.5 truncate">
            <MapPin className="w-3.5 h-3.5 shrink-0" />
            <span className="truncate">
              {cohort.location_name || cohort.location || "Venue unassigned"}
            </span>
          </div>
          {(cohort.sessions_count != null || cohort.duration_hours != null) && (
            <div className="flex items-center gap-1.5 truncate">
              <Clock className="w-3.5 h-3.5 shrink-0" />
              <span className="truncate">
                {cohort.sessions_count ?? 0} session{(cohort.sessions_count ?? 0) === 1 ? "" : "s"}
                {cohort.duration_hours != null ? ` · ${cohort.duration_hours}h` : ""}
              </span>
            </div>
          )}
          <div className="flex items-center gap-1.5 truncate">
            <Users className="w-3.5 h-3.5 shrink-0" />
            <span className="truncate">
              {cohort.active_students_count}
              {cohort.capacity != null ? ` / ${cohort.capacity}` : ""} students
              {cohort.active_observers_count > 0
                ? ` · ${cohort.active_observers_count} observer${cohort.active_observers_count === 1 ? "" : "s"}`
                : ""}
            </span>
          </div>
        </div>

        {fillPct != null && (
          <div className="mt-2.5">
            <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full rounded-full ${fillPct >= 100 ? "bg-rose-500" : "bg-primary"}`}
                style={{ width: `${fillPct}%` }}
              />
            </div>
          </div>
        )}

        {cohort.linked_event_slug && (
          <div className="mt-2.5 pt-2 border-t border-border flex items-center justify-between text-[11px]">
            <span className="text-muted-foreground">Landing Page:</span>
            <a
              href={`/events/${country}/${cohort.linked_event_slug}`}
              target="_blank"
              rel="noreferrer"
              className="text-primary hover:underline inline-flex items-center gap-1 font-medium"
            >
              View Page <ExternalLink className="w-2.5 h-2.5" />
            </a>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between pt-2.5 border-t border-border gap-2">
        <div className="flex items-center gap-1.5">
          {!isObserver && (
            <button
              type="button"
              onClick={onEdit}
              title="Edit cohort details"
              className="inline-flex items-center gap-1 h-7 px-2 rounded-lg border border-border text-[11px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition cursor-pointer"
            >
              <Pencil className="w-3 h-3" /> Edit
            </button>
          )}
          {!isObserver && isOrgOwnedProgram && !isModeB && (
            <button
              type="button"
              onClick={onDuplicate}
              title="Duplicate cohort structure & curriculum"
              className="inline-flex items-center gap-1 h-7 px-2 rounded-lg border border-border text-[11px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition cursor-pointer"
            >
              <Copy className="w-3 h-3" /> Duplicate
            </button>
          )}
        </div>

        <Link
          to="/organization/programs/$cohortId"
          params={{ cohortId: cohort.id }}
          className="inline-flex items-center gap-1 h-7 px-2.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 text-xs font-semibold transition ml-auto"
        >
          Manage <ChevronRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    </div>
  )
}

// ── Modals ───────────────────────────────────────────────────────────────────

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
  const [durationHours, setDurationHours] = useState("2")
  const [keepCourseAccessAfterCompletion, setKeepCourseAccessAfterCompletion] = useState(true)
  const [description, setDescription] = useState("")

  const mut = useMutation({
    mutationFn: () =>
      createOrgProgramApi({
        name: (name || "").trim(),
        code: (code || "").trim().toUpperCase(),
        program_type: programType,
        default_capacity: defaultCapacity ? parseInt(defaultCapacity, 10) : undefined,
        duration_hours: durationHours.trim() ? Number(durationHours) : undefined,
        pricing_model: "free",
        price: undefined,
        completion_rule_type: "percentage",
        completion_rule_value: 70,
        keep_course_access_after_completion: keepCourseAccessAfterCompletion,
        description: (description || "").trim() || undefined,
      }),
    onSuccess: () => {
      toast.success("Program created!")
      onSuccess()
    },
    onError: (err) => {
      toast.error(getErrorMessage(err, "Failed to create program"))
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
                      .toUpperCase(),
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
              </select>
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Default Capacity</span>
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
              <span className="text-xs font-semibold text-muted-foreground">Session Duration (hrs)</span>
              <input
                type="number"
                step="0.5"
                min="0.5"
                value={durationHours}
                onChange={(e) => setDurationHours(e.target.value)}
                placeholder="2"
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
            className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!(name || "").trim() || !(code || "").trim() || mut.isPending}
            onClick={() => mut.mutate()}
            className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50 cursor-pointer"
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
  const [defaultCapacity, setDefaultCapacity] = useState(
    program.default_capacity ? String(program.default_capacity) : "50",
  )
  const [durationHours, setDurationHours] = useState(
    program.duration_hours != null ? String(program.duration_hours) : "",
  )
  const [keepCourseAccessAfterCompletion, setKeepCourseAccessAfterCompletion] = useState(
    program.keep_course_access_after_completion ?? true,
  )
  const [description, setDescription] = useState(program.description || "")

  const mut = useMutation({
    mutationFn: () =>
      updateOrgProgramApi(program.id, {
        name: (name || "").trim(),
        program_type: programType,
        default_capacity: defaultCapacity ? parseInt(defaultCapacity, 10) : undefined,
        duration_hours: durationHours.trim() ? Number(durationHours) : undefined,
        pricing_model: "free",
        price: undefined,
        keep_course_access_after_completion: keepCourseAccessAfterCompletion,
        description: (description || "").trim() || undefined,
      }),
    onSuccess: () => {
      toast.success("Program updated!")
      onSuccess()
    },
    onError: (err) => {
      toast.error(getErrorMessage(err, "Failed to update program"))
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl border border-border bg-card p-6 shadow-xl space-y-4">
        <h2 className="text-base font-bold text-foreground">Quick Edit Program</h2>

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

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
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
              </select>
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Capacity</span>
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
              <span className="text-xs font-semibold text-muted-foreground">Session (hrs)</span>
              <input
                type="number"
                step="0.5"
                min="0.5"
                value={durationHours}
                onChange={(e) => setDurationHours(e.target.value)}
                placeholder="2"
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
            className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!(name || "").trim() || mut.isPending}
            onClick={() => mut.mutate()}
            className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50 cursor-pointer"
          >
            {mut.isPending ? "Saving..." : "Save Changes"}
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
    onError: (err) => {
      toast.error(getErrorMessage(err, "Failed to duplicate cohort"))
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
              className={`h-9 px-3 rounded-xl border bg-background text-sm focus:outline-none transition ${capacityExceeded ? "border-destructive text-destructive" : "border-border"
                }`}
            />
          </label>

          {capacityExceeded && (
            <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-2.5 text-xs text-destructive">
              Your limit is {quotas.max_students_per_cohort} students per cohort. Talk to the SpacePoint team to request a higher limit.
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
                Public cohorts appear on SpacePoint&apos;s public learning catalog.
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
                Copy Milestones &amp; Learning Modules
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
            className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!name.trim() || !code.trim() || capacityExceeded || mut.isPending}
            onClick={() => mut.mutate()}
            className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50 cursor-pointer"
          >
            {mut.isPending ? "Duplicating..." : "Duplicate Cohort"}
          </button>
        </div>
      </div>
    </div>
  )
}
