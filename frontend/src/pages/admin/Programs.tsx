import { useState, useMemo } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import {
  Plus,
  Pencil,
  Trash2,
  Search,
  Calendar,
  MapPin,
  Users,
  ChevronDown,
  ChevronRight,
  Layers,
  SlidersHorizontal,
  ArrowRight,
  X,
} from "lucide-react"
import type {
  Program,
  ProgramType,
  Cohort,
  CohortStatus,
} from "@/types/sessions"
import { getProgramsApi } from "@/api/sessions/programs"
import { getCohortsApi, deleteCohortApi } from "@/api/sessions/cohorts"
import { Spinner } from "@/pages/admin/components/common"
import { CohortModal } from "@/pages/admin/Cohorts"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

const PROGRAM_TYPES: ProgramType[] = ["workshop", "course", "info_session", "competition"]

const PROGRAM_TYPE_LABEL: Record<ProgramType, string> = {
  workshop: "Workshop",
  course: "Course",
  info_session: "Info session",
  competition: "Competition",
}

export default function Programs() {
  const toast = useToast()
  const queryClient = useQueryClient()

  const [viewMode, setViewMode] = useState<"program" | "worklist">("program")
  const [search, setSearch] = useState("")
  const [typeFilter, setTypeFilter] = useState<string>("")
  const [statusFilter, setStatusFilter] = useState<string>("")

  const [editingCohort, setEditingCohort] = useState<Cohort | null>(null)
  const [expandedPastMap, setExpandedPastMap] = useState<Record<string, boolean>>({})

  // Queries
  const { data: programs = [], isLoading: programsLoading } = useQuery<Program[]>({
    queryKey: ["sessions-programs"],
    queryFn: getProgramsApi,
  })

  const { data: rawCohorts = [], isLoading: cohortsLoading } = useQuery<Cohort[]>({
    queryKey: ["sessions-cohorts"],
    queryFn: () => getCohortsApi(),
  })

  const cohorts = useMemo(
    () =>
      rawCohorts.filter((c) => {
        const statusStr = String(c.status).toLowerCase()
        const normName = c.name.trim().toLowerCase()
        return statusStr !== "draft" && !normName.startsWith("[template]") && normName !== "template"
      }),
    [rawCohorts]
  )

  // Cohort Delete Mutation
  const deleteCohortMutation = useMutation({
    mutationFn: deleteCohortApi,
    onSuccess: () => {
      toast.success("Cohort deleted")
      queryClient.invalidateQueries({ queryKey: ["sessions-cohorts"] })
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to delete cohort")),
  })

  // Group cohorts by parent program ID
  const cohortsByProgramId = useMemo(() => {
    const map = new Map<string, Cohort[]>()
    for (const c of cohorts) {
      const list = map.get(c.program_id) ?? []
      list.push(c)
      map.set(c.program_id, list)
    }
    return map
  }, [cohorts])

  // Filtered Programs
  const filteredPrograms = useMemo(() => {
    const q = search.trim().toLowerCase()
    return programs.filter((p) => {
      if (typeFilter && p.program_type !== typeFilter) return false
      if (!q) return true
      const matchesProgram =
        p.name.toLowerCase().includes(q) || p.code.toLowerCase().includes(q)
      if (matchesProgram) return true

      const programCohorts = cohortsByProgramId.get(p.id) ?? []
      return programCohorts.some(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          (c.location_name ?? "").toLowerCase().includes(q) ||
          (c.location ?? "").toLowerCase().includes(q)
      )
    })
  }, [programs, cohortsByProgramId, typeFilter, search])

  // Filtered Cohorts for the Operational Worklist
  const filteredWorklist = useMemo(() => {
    const q = search.trim().toLowerCase()
    return cohorts.filter((c) => {
      if (statusFilter && c.status !== statusFilter) return false
      if (!q) return true
      return (
        c.name.toLowerCase().includes(q) ||
        (c.program_name ?? "").toLowerCase().includes(q) ||
        (c.location_name ?? "").toLowerCase().includes(q) ||
        (c.location ?? "").toLowerCase().includes(q)
      )
    })
  }, [cohorts, statusFilter, search])

  const togglePast = (programId: string) => {
    setExpandedPastMap((prev) => ({
      ...prev,
      [programId]: !prev[programId],
    }))
  }

  if (programsLoading || cohortsLoading) {
    return <Spinner />
  }

  return (
    <div className="flex flex-col gap-6 max-w-[1240px] mx-auto pb-16">
      {/* ── Page Header ───────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
            Programs
          </h1>
        </div>

        <div className="flex items-center gap-2">
          <Link
            to="/operations/programs/new"
            className="inline-flex items-center gap-2 h-10 px-4 rounded-[10px] bg-primary text-primary-foreground text-sm font-semibold hover:opacity-90 transition-colors cursor-pointer"
          >
            <Plus size={16} /> New Program
          </Link>
        </div>
      </div>

      {/* ── Filter & View Mode Controls ───────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center justify-between gap-3">
        <div className="flex flex-wrap flex-1 items-center gap-2 min-w-0">
          <div className="relative w-full sm:flex-1 sm:min-w-[200px]">
            <Search
              size={15}
              className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none"
            />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search program, cohort, or venue..."
              className="w-full h-10 pl-10 pr-8 rounded-[10px] border border-border bg-card text-foreground text-sm font-medium focus:outline-none focus:border-primary transition-colors"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                aria-label="Clear search"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground p-0.5 rounded-full transition-colors"
              >
                <X size={14} />
              </button>
            )}
          </div>

          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="flex-1 sm:flex-none sm:w-44 shrink-0 h-10 px-3 rounded-[10px] border border-border bg-card text-foreground text-sm font-medium focus:outline-none focus:border-primary transition-colors cursor-pointer"
          >
            <option value="">All Types</option>
            {PROGRAM_TYPES.map((t) => (
              <option key={t} value={t}>
                {PROGRAM_TYPE_LABEL[t]}
              </option>
            ))}
          </select>

          {viewMode === "worklist" && (
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="flex-1 sm:flex-none sm:w-44 shrink-0 h-10 px-3 rounded-[10px] border border-border bg-card text-foreground text-sm font-medium focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              <option value="">All Statuses</option>
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
            onClick={() => setViewMode("program")}
            className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] text-xs font-bold transition-all cursor-pointer ${
              viewMode === "program"
                ? "bg-background text-foreground shadow-xs"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Layers size={14} /> Program View
          </button>
          <button
            onClick={() => setViewMode("worklist")}
            className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] text-xs font-bold transition-all cursor-pointer ${
              viewMode === "worklist"
                ? "bg-background text-foreground shadow-xs"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <SlidersHorizontal size={14} /> Cohort View
          </button>
        </div>
      </div>

      {/* ── VIEW 1: PROGRAM-CENTRIC BLUEPRINT VIEW ─────────────────── */}
      {viewMode === "program" && (
        <div className="space-y-6">
          {filteredPrograms.length === 0 ? (
            <div className="p-12 text-center rounded-[10px] border border-border bg-card">
              <p className="text-base font-bold text-foreground">No programs found</p>
              <p className="text-sm text-muted-foreground mt-1">
                Try clearing your search query or type filters.
              </p>
            </div>
          ) : (
            filteredPrograms.map((program) => {
              const programCohorts = cohortsByProgramId.get(program.id) ?? []
              const runningCohorts = programCohorts.filter((c) => c.status === "running")
              const openCohorts = programCohorts.filter(
                (c) => c.status === "registration_open" || c.status === "planned"
              )
              const pastCohorts = programCohorts.filter(
                (c) => c.status === "completed" || c.status === "cancelled"
              )
              const pastExpanded = !!expandedPastMap[program.id]

              return (
                <div
                  key={program.id}
                  className="rounded-[10px] border border-border bg-card overflow-hidden transition-colors"
                >
                  {/* Clean Program Header with Interactive Arrow */}
                  <div className="p-5 sm:p-6 border-b border-border bg-muted/20 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2.5 flex-wrap">
                        <Link
                          to="/operations/programs/$programId"
                          params={{ programId: program.id }}
                          className="text-xl font-extrabold text-foreground tracking-tight hover:text-primary transition-colors"
                        >
                          {program.name}
                        </Link>
                        <span className="text-xs font-bold px-2.5 py-0.5 rounded-[10px] bg-primary/10 text-primary border border-primary/20 capitalize">
                          {program.program_type}
                        </span>
                      </div>

                      {program.description && (
                        <p className="text-sm text-muted-foreground mt-1 line-clamp-1">
                          {program.description}
                        </p>
                      )}
                    </div>

                    {/* Master Action & Navigatable Arrow */}
                    <div className="flex items-center gap-2 shrink-0">
                      <Link
                        to="/operations/cohorts/new"
                        search={{ programId: program.id }}
                        className="inline-flex items-center gap-1.5 h-10 px-4 rounded-[10px] bg-primary text-primary-foreground text-sm font-bold hover:opacity-90 transition-colors cursor-pointer"
                      >
                        <Plus size={15} /> Add Cohort
                      </Link>

                      <Link
                        to="/operations/programs/$programId"
                        params={{ programId: program.id }}
                        className="inline-flex items-center justify-center h-10 w-10 rounded-[10px] border border-border bg-background text-foreground hover:bg-muted hover:border-primary/40 transition-colors group cursor-pointer"
                        title="Manage Program"
                        aria-label={`Manage ${program.name}`}
                      >
                        <ChevronRight
                          size={18}
                          className="group-hover:translate-x-0.5 transition-transform"
                        />
                      </Link>
                    </div>
                  </div>

                  {/* Child Cohorts Groups */}
                  <div className="p-5 sm:p-6 space-y-6">
                    {programCohorts.length === 0 ? (
                      <div className="py-8 text-center rounded-[10px] border border-dashed border-border bg-muted/10">
                        <p className="text-sm font-semibold text-muted-foreground">
                          No cohorts scheduled under this program yet.
                        </p>
                        <Link
                          to="/operations/cohorts/new"
                          search={{ programId: program.id }}
                          className="mt-3 inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-colors cursor-pointer"
                        >
                          <Plus size={13} /> Launch First Cohort
                        </Link>
                      </div>
                    ) : (
                      <>
                        {/* 1. Running Cohorts */}
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
                                <CohortCard
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

                        {/* 2. Registration Open & Upcoming Cohorts */}
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
                                <CohortCard
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

                        {/* 3. Past & Completed Cohorts */}
                        {pastCohorts.length > 0 && (
                          <div className="pt-2 border-t border-border">
                            <button
                              onClick={() => togglePast(program.id)}
                              className="inline-flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                            >
                              <span className="w-2.5 h-2.5 rounded-full bg-muted-foreground/60 inline-block" />
                              <span>Past & Completed ({pastCohorts.length} Cohorts)</span>
                              {pastExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            </button>

                            {pastExpanded && (
                              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mt-3">
                                {pastCohorts.map((c) => (
                                  <CohortCard
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
                      </>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>
      )}

      {/* ── VIEW 2: GLOBAL OPERATIONAL WORKLIST (TIMELINE) ─────────── */}
      {viewMode === "worklist" && (
        <div className="rounded-[10px] border border-border bg-card overflow-hidden">
          <div className="hidden md:grid md:grid-cols-12 gap-3 p-4 border-b border-border bg-muted/20 text-xs font-bold uppercase tracking-wider text-muted-foreground">
            <div className="col-span-2">Status</div>
            <div className="col-span-3">Cohort & Program</div>
            <div className="col-span-3">Dates & Venue</div>
            <div className="col-span-2">Staffing & Capacity</div>
            <div className="col-span-2 text-right">Actions</div>
          </div>

          <div className="divide-y divide-border">
            {filteredWorklist.length === 0 ? (
              <div className="p-12 text-center text-sm font-semibold text-muted-foreground">
                No cohorts match the selected filters.
              </div>
            ) : (
              filteredWorklist.map((c) => {
                const registered = c.registrations_count ?? 0
                const unstaffed = c.unstaffed_count ?? 0

                return (
                  <div
                    key={c.id}
                    className="flex flex-col md:grid md:grid-cols-12 gap-3 p-4 md:items-center hover:bg-muted/30 transition-colors"
                  >
                    <div className="md:col-span-2 flex items-center gap-1.5 flex-wrap">
                      <CohortStatusBadge status={c.status} />
                      {unstaffed > 0 && (
                        <span className="text-[11px] font-bold px-2 py-0.5 rounded-[10px] bg-rose-500/15 text-rose-600 dark:text-rose-400 border border-rose-500/30">
                          {unstaffed} unstaffed
                        </span>
                      )}
                    </div>

                    <div className="md:col-span-3 min-w-0">
                      <Link
                        to="/operations/cohorts/$cohortId"
                        params={{ cohortId: c.id }}
                        search={{ from: "/operations/programs" } as never}
                        className="text-sm font-bold text-foreground hover:text-primary transition-colors block md:truncate"
                      >
                        {c.name}
                      </Link>
                      <span className="text-xs text-muted-foreground block md:truncate">
                        {c.program_name ?? "—"}
                      </span>
                    </div>

                    <div className="md:col-span-3 text-xs text-muted-foreground min-w-0">
                      <div className="md:truncate">
                        {c.starts_on
                          ? `${c.starts_on}${c.ends_on && c.ends_on !== c.starts_on ? ` – ${c.ends_on}` : ""}`
                          : "Dates unassigned"}
                      </div>
                      <div className="md:truncate text-foreground font-medium mt-0.5">
                        {c.location_name ?? c.location ?? "Venue unassigned"}
                      </div>
                    </div>

                    <div className="md:col-span-2 flex md:block items-center justify-between gap-2 text-xs text-muted-foreground">
                      <div className="font-bold text-foreground">
                        {registered}
                        {c.capacity ? ` / ${c.capacity}` : ""} Seats
                      </div>
                      <div className="md:truncate md:mt-0.5">
                        {c.sessions_count != null ? `${c.sessions_count} sessions` : ""}
                      </div>
                    </div>

                    <div className="md:col-span-2 flex items-center justify-end gap-1.5 pt-2 md:pt-0 border-t border-border/50 md:border-t-0">
                      <button
                        onClick={() => setEditingCohort(c)}
                        className="p-1.5 rounded-[10px] text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                        title="Edit Cohort"
                      >
                        <Pencil size={14} />
                      </button>
                      <Link
                        to="/operations/cohorts/$cohortId"
                        params={{ cohortId: c.id }}
                        search={{ from: "/operations/programs" } as never}
                        className="inline-flex items-center gap-1 h-8 px-3 rounded-[10px] border border-border bg-background text-xs font-bold text-foreground hover:bg-muted transition-colors"
                      >
                        Manage <ArrowRight size={12} />
                      </Link>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>
      )}

      {/* ── COHORT QUICK EDIT MODAL ─────────────────────────────── */}
      {editingCohort && (
        <CohortModal
          programs={programs}
          cohort={editingCohort}
          onClose={() => setEditingCohort(null)}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ["sessions-cohorts"] })
            setEditingCohort(null)
          }}
        />
      )}
    </div>
  )
}

/* ── COHORT CARD (Inside Program Blueprint) ─────────────────────── */
function CohortCard({
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
    <div className="rounded-[var(--sp-control-radius)] border-[length:var(--sp-control-border-width)] border-[var(--sp-control-border-color)] bg-transparent p-4 flex flex-col justify-between gap-3 hover:border-primary/60 transition-colors">
      <div>
        <div className="flex items-start justify-between gap-2 mb-2">
          <Link
            to="/operations/cohorts/$cohortId"
            params={{ cohortId: c.id }}
            search={{ from: "/operations/programs" } as never}
            className="text-sm font-bold text-foreground hover:text-primary transition-colors truncate block"
          >
            {c.name}
          </Link>
          <div className="flex items-center gap-1 shrink-0">
            <CohortStatusBadge status={c.status} />
          </div>
        </div>

        {(c.organization_id || unstaffed > 0) && (
          <div className="mb-2.5 flex items-center gap-1.5 flex-wrap">
            {c.organization_id && (
              <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-600 dark:text-violet-400 border border-violet-500/30">
                Partner: {c.organization_name || "Organization"}
              </span>
            )}
            {unstaffed > 0 && (
              <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-600 dark:text-rose-400 border border-rose-500/30">
                {unstaffed} unstaffed session{unstaffed === 1 ? "" : "s"}
              </span>
            )}
          </div>
        )}

        <div className="space-y-1.5 text-xs text-muted-foreground mt-2">
          <div className="flex items-center gap-1.5 truncate">
            <Calendar size={13} className="shrink-0 text-muted-foreground" />
            <span className="truncate">
              {c.starts_on
                ? `${c.starts_on}${c.ends_on && c.ends_on !== c.starts_on ? ` – ${c.ends_on}` : ""}`
                : "Dates unassigned"}
            </span>
          </div>

          <div className="flex items-center gap-1.5 truncate">
            <MapPin size={13} className="shrink-0 text-muted-foreground" />
            <span className="truncate">{c.location_name ?? c.location ?? "Venue unassigned"}</span>
          </div>

          <div className="flex items-center gap-1.5 truncate">
            <Users size={13} className="shrink-0 text-muted-foreground" />
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
                className={`h-full rounded-[10px] ${
                  fillPct >= 100 ? "bg-rose-500" : "bg-primary"
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
          search={{ from: "/operations/programs" } as never}
          className="text-xs font-bold text-primary hover:underline inline-flex items-center gap-1"
        >
          Manage <ArrowRight size={12} />
        </Link>
      </div>
    </div>
  )
}

function CohortStatusBadge({ status }: { status: CohortStatus }) {
  if (status === "running") {
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
        Running
      </span>
    )
  }
  if (status === "registration_open") {
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
        Registration Open
      </span>
    )
  }
  if (status === "planned") {
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-muted text-muted-foreground border border-border">
        Planned
      </span>
    )
  }
  if (status === "completed") {
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-foreground text-background border border-foreground">
        Completed
      </span>
    )
  }
  return (
    <span className="text-[11px] font-bold px-2 py-0.5 rounded-[10px] bg-rose-500/15 text-rose-600 dark:text-rose-400 border border-rose-500/30">
      Cancelled
    </span>
  )
}