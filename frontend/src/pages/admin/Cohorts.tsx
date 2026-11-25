import { useEffect, useMemo, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "@tanstack/react-router"
import { Plus, Pencil, Trash2, Search, X, Layers, Calendar, MapPin, Clock, Users } from "lucide-react"
import type { Cohort, CohortStatus, CohortVisibility, Program, ProgramVariation } from "@/types/sessions"
import { getProgramsApi, listProgramVariationsApi } from "@/api/sessions/programs"
import { getLocationsApi, getWarehousesApi, getCitiesApi, createLocationApi } from "@/api/inventory"
import {
  getCohortsApi, createCohortApi, updateCohortApi, deleteCohortApi,
} from "@/api/sessions/cohorts"
import { Modal, Field, ModalActions, ConfirmDialog, Spinner, PageHeader, EmptyState } from "@/pages/admin/components/common"
import { CoordinatorAccessPicker } from "@/components/organization/CoordinatorAccessPicker"
import { useToast } from "@/components/ui/toast"
import { useAuth } from "@/context/AuthContext"
import { getErrorMessage } from "@/lib/utils"

export const STATUS_OPTIONS: CohortStatus[] = ["planned", "registration_open", "running", "completed", "cancelled"]

/** The statuses a cohort can be *moved to* by hand. "completed" is missing on
 *  purpose (2026-08-31): finishing a cohort settles its registrations, issues
 *  the student certificates and completes its sessions, and only
 *  POST /sessions/cohorts/{id}/complete — the "Complete cohort" button — does
 *  that. The plain status write used to look identical to ops and did none of
 *  it. The backend refuses the transition too; this just stops offering it.
 *  Filters still use STATUS_OPTIONS: ops must be able to filter by completed. */
const EDITABLE_STATUS_OPTIONS: CohortStatus[] = ["planned", "registration_open", "running", "cancelled"]

/** Options for a select bound to `current` — an already-completed cohort keeps
 *  "Completed" in its own list, or the select would render blank against a
 *  value it doesn't offer. */
export const statusOptionsFor = (current: CohortStatus): CohortStatus[] =>
  EDITABLE_STATUS_OPTIONS.includes(current) ? EDITABLE_STATUS_OPTIONS : [...EDITABLE_STATUS_OPTIONS, current]
const VISIBILITY_OPTIONS: CohortVisibility[] = ["public", "private"]

export const COHORT_STATUS_LABEL: Record<CohortStatus, string> = {
  planned: "Planned",
  registration_open: "Registration open",
  running: "Running",
  completed: "Completed",
  cancelled: "Cancelled",
}

export const COHORT_STATUS_COLOR: Record<CohortStatus, string> = {
  planned: "bg-muted text-muted-foreground",
  registration_open: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  running: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400",
  completed: "bg-foreground text-background",
  cancelled: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400",
}

/* ================================================================== */
/* Cohorts page                                                        */
/* ================================================================== */
/** The worklist's own grouping — deliberately not the raw status list.
 *  created_at DESC alone meant cancelled and completed cohorts sat forever at
 *  the top of a page ops opens every day; what they actually want is "what's
 *  live, what's coming, and everything else out of the way". */
type CohortGroup = "running" | "registration_open" | "upcoming" | "past"

const GROUP_ORDER: CohortGroup[] = ["running", "registration_open", "upcoming", "past"]
const GROUP_LABEL: Record<CohortGroup, string> = {
  running: "Running",
  registration_open: "Registration open",
  upcoming: "Upcoming",
  past: "Past",
}

function groupOf(c: Cohort): CohortGroup {
  if (c.status === "running") return "running"
  if (c.status === "registration_open") return "registration_open"
  if (c.status === "completed" || c.status === "cancelled") return "past"
  return "upcoming"
}

export default function Cohorts() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  const [programFilter, setProgramFilter] = useState("")
  const [statusFilter, setStatusFilter] = useState<CohortStatus | "">("")
  const [managementModeFilter, setManagementModeFilter] = useState<"spacepoint" | "partner" | "all">("spacepoint")
  const [search, setSearch] = useState("")
  const [showPast, setShowPast] = useState(false)
  const [editCohort, setEditCohort] = useState<Cohort | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Cohort | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  // Refused server-side if anyone has registered — cancelling the cohort is
  // the right move there, and the API says so.
  const deleteCohortMutation = useMutation({
    mutationFn: deleteCohortApi,
    onSuccess: () => {
      toast.success("Cohort deleted")
      setDeleteError(null)
      setDeleteTarget(null)
      queryClient.invalidateQueries({ queryKey: ["sessions-cohorts"] })
    },
    onError: (e: any) => setDeleteError(getErrorMessage(e, "Failed to delete cohort")),
  })

  const { data: programs = [] } = useQuery<Program[]>({ queryKey: ["sessions-programs"], queryFn: getProgramsApi })
  const { data: rawCohorts = [], isLoading } = useQuery<Cohort[]>({
    queryKey: ["sessions-cohorts", programFilter, managementModeFilter],
    queryFn: () =>
      getCohortsApi({
        ...(programFilter ? { program_id: programFilter } : {}),
        management_mode: managementModeFilter,
      }),
  })
  const cohorts = useMemo(
    () =>
      rawCohorts.filter((c) => {
        const statusStr = String(c.status).toLowerCase()
        const normName = c.name.trim().toLowerCase()
        return statusStr !== "draft" && !normName.startsWith("[template]") && normName !== "template"
      }),
    [rawCohorts],
  )

  const grouped = useMemo(() => {
    const q = search.trim().toLowerCase()
    const matching = cohorts.filter((c) => {
      if (statusFilter && c.status !== statusFilter) return false
      if (!q) return true
      return [c.name, c.program_name, c.location_name, c.location, c.organization_name].some(
        (v) => (v ?? "").toString().toLowerCase().includes(q),
      )
    })
    const buckets = { running: [], registration_open: [], upcoming: [], past: [] } as Record<CohortGroup, Cohort[]>
    for (const c of matching) buckets[groupOf(c)].push(c)
    // Soonest first inside the live groups — the next thing to happen is the
    // thing you're most likely looking for. Past stays newest-first.
    for (const key of ["running", "registration_open", "upcoming"] as const) {
      buckets[key].sort((a, b) => (a.starts_on ?? "9999").localeCompare(b.starts_on ?? "9999"))
    }
    return { buckets, total: matching.length }
  }, [cohorts, search, statusFilter])

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Cohorts"
        action={
          <button
            onClick={() => navigate({ to: "/operations/cohorts/new" })}
            className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
          >
            <Plus size={14} /> New cohort
          </button>
        }
      />

      {deleteError && (
        <div className="text-xs text-red-600 dark:text-red-400 bg-red-500/10 border border-red-500/30 rounded-xl px-3 py-2">
          {deleteError}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[12rem]">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          <input
            value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search cohort, program, location…"
            className="w-full h-9 pl-9 pr-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </div>
        <select
          value={programFilter} onChange={(e) => setProgramFilter(e.target.value)}
          className="h-9 px-3 w-full sm:w-52 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="">All programs</option>
          {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select
          value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as CohortStatus | "")}
          className="h-9 px-3 w-full sm:w-44 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="">Any status</option>
          {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{COHORT_STATUS_LABEL[s]}</option>)}
        </select>
        <select
          value={managementModeFilter}
          onChange={(e) => setManagementModeFilter(e.target.value as "spacepoint" | "partner" | "all")}
          aria-label="Management mode filter"
          className="h-9 px-3 w-full sm:w-44 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="spacepoint">SpacePoint-Run</option>
          <option value="partner">Partner-Run</option>
          <option value="all">All Modes</option>
        </select>
      </div>

      {grouped.total === 0 ? (
        <EmptyState
          title={cohorts.length === 0 ? "No cohorts yet" : "No cohorts match those filters"}
          hint={cohorts.length === 0 ? undefined : "Try clearing the search or status filter."}
        />
      ) : (
        <div className="flex flex-col gap-5">
          {GROUP_ORDER.map((group) => {
            const rows = grouped.buckets[group]
            if (rows.length === 0) return null
            // Past is collapsed by default — it's the group that used to bury
            // everything live, and it's the one you least often want.
            const collapsed = group === "past" && !showPast
            return (
              <div key={group} className="flex flex-col gap-2">
                {group === "past" ? (
                  <button
                    onClick={() => setShowPast((v) => !v)}
                    className="w-fit text-xs font-semibold text-muted-foreground uppercase tracking-wider hover:text-foreground transition-colors"
                  >
                    {GROUP_LABEL[group]} ({rows.length}) {collapsed ? "▸" : "▾"}
                  </button>
                ) : (
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    {GROUP_LABEL[group]} ({rows.length})
                  </p>
                )}
                {!collapsed && rows.map((c) => (
                  <CohortRow
                    key={c.id}
                    cohort={c}
                    onEdit={() => setEditCohort(c)}
                    onDelete={() => { setDeleteError(null); setDeleteTarget(c) }}
                    deleting={deleteCohortMutation.isPending}
                  />
                ))}
              </div>
            )
          })}
        </div>
      )}

      {editCohort && (
        <CohortModal
          programs={programs} cohort={editCohort}
          onClose={() => setEditCohort(null)}
          onSuccess={() => { queryClient.invalidateQueries({ queryKey: ["sessions-cohorts"] }); setEditCohort(null) }}
        />
      )}
      {deleteTarget && (
        <ConfirmDialog
          title={`Delete the cohort "${deleteTarget.name}"?`}
          description="This only works if nobody has registered — cancel the cohort instead if it already has registrations."
          confirmLabel="Delete cohort"
          destructive
          error={deleteError}
          pending={deleteCohortMutation.isPending}
          onCancel={() => { setDeleteTarget(null); setDeleteError(null) }}
          onConfirm={() => deleteCohortMutation.mutate(deleteTarget.id)}
        />
      )}
    </div>
  )
}

/* ================================================================== */
/* One worklist row — the operational numbers, not just the label      */
/* ================================================================== */
function CohortRow({ cohort: c, onEdit, onDelete, deleting }: {
  cohort: Cohort; onEdit: () => void; onDelete: () => void; deleting: boolean
}) {
  const registered = c.registrations_count ?? 0
  const fillPct = c.capacity ? Math.min(100, Math.round((registered / c.capacity) * 100)) : null

  return (
    <div className="flex items-center justify-between gap-3 p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors">
      <Link
        to="/operations/cohorts/$cohortId"
        params={{ cohortId: c.id }}
        search={{ from: "/operations/cohorts" } as never}
        className="min-w-0 text-left flex-1 block"
      >
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-medium text-foreground truncate">{c.name}</p>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${COHORT_STATUS_COLOR[c.status]}`}>
            {COHORT_STATUS_LABEL[c.status]}
          </span>
          {c.organization_id && (
            <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-600 dark:text-violet-400">
              Partner: {c.organization_name || "Organization"}
            </span>
          )}
          {c.management_mode === "partner" && (
            <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
              Partner-Run
            </span>
          )}
          {c.variation_name && (
            <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-primary/10 text-primary">
              {c.variation_name}
            </span>
          )}
          {/* Only ever shown when there's something to do about it — a "0
              unstaffed" pill on every row is noise, not information. */}
          {(c.unstaffed_count ?? 0) > 0 && (
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400">
              {c.unstaffed_count} unstaffed
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground mt-1.5">
          <span className="inline-flex items-center gap-1.5">
            <Layers size={12} className="shrink-0 opacity-70" />
            <span>{c.program_name ?? "—"}</span>
          </span>
          {c.starts_on && (
            <span className="inline-flex items-center gap-1.5">
              <Calendar size={12} className="shrink-0 opacity-70" />
              <span>
                {c.starts_on}
                {c.ends_on && c.ends_on !== c.starts_on ? ` – ${c.ends_on}` : ""}
              </span>
            </span>
          )}
          {(c.location_name || c.location) && (
            <span className="inline-flex items-center gap-1.5">
              <MapPin size={12} className="shrink-0 opacity-70" />
              <span>{c.location_name ?? c.location}</span>
            </span>
          )}
          {c.sessions_count != null && (
            <span className="inline-flex items-center gap-1.5">
              <Clock size={12} className="shrink-0 opacity-70" />
              <span>
                {c.sessions_count} session{c.sessions_count === 1 ? "" : "s"}
                {c.next_session_date ? ` (next ${c.next_session_date})` : ""}
              </span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-2">
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground tabular-nums shrink-0">
            <Users size={12} className="shrink-0 opacity-70" />
            {registered}{c.capacity != null ? ` / ${c.capacity}` : ""} registered
          </span>
          {fillPct != null && (
            <span className="h-1.5 w-24 rounded-full bg-muted overflow-hidden shrink-0">
              <span
                className={`block h-full rounded-full ${fillPct >= 100 ? "bg-amber-500" : "bg-primary"}`}
                style={{ width: `${fillPct}%` }}
              />
            </span>
          )}
        </div>
      </Link>
      <div className="flex items-center gap-1 flex-shrink-0">
        <button
          onClick={onEdit}
          className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
          title="Edit cohort"
          aria-label={`Edit ${c.name}`}
        >
          <Pencil size={14} />
        </button>
        <button
          onClick={onDelete}
          disabled={deleting}
          className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors disabled:opacity-50"
          title="Delete cohort"
          aria-label={`Delete ${c.name}`}
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  )
}

/* ================================================================== */
/* Create/edit cohort modal — also reused by CohortDetail.tsx's "Edit"  */
/* trigger, so this stays exported rather than duplicated.             */
/* ================================================================== */
export function CohortModal({ programs, cohort, onClose, onSuccess, initialProgramId, organizationId, defaultManagementMode }: {
  programs: Program[]
  cohort?: Cohort
  onClose: () => void
  onSuccess: () => void
  initialProgramId?: string
  organizationId?: string | null
  defaultManagementMode?: "spacepoint" | "partner"
}) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const { hasRole } = useAuth()
  const isEdit = !!cohort
  const [programId, setProgramId] = useState(cohort?.program_id ?? initialProgramId ?? "")
  const [managementMode, setManagementMode] = useState<"spacepoint" | "partner">(
    cohort?.management_mode ?? defaultManagementMode ?? "spacepoint",
  )
  const hideWarehouse = (cohort?.management_mode ?? managementMode) === "partner"
  const [name, setName] = useState(cohort?.name ?? "")
  const [startsOn, setStartsOn] = useState(cohort?.starts_on ?? "")
  const [endsOn, setEndsOn] = useState(cohort?.ends_on ?? "")
  const [locationId, setLocationId] = useState(cohort?.location_id ?? "")
  const [warehouseId, setWarehouseId] = useState(cohort?.warehouse_id ?? "")
  const [capacity, setCapacity] = useState(cohort?.capacity != null ? String(cohort.capacity) : "")
  const [durationHours, setDurationHours] = useState(cohort?.duration_hours != null ? String(cohort.duration_hours) : "")
  const { data: locations = [] } = useQuery({ queryKey: ["inv-locations"], queryFn: () => getLocationsApi() })
  const { data: warehouses = [] } = useQuery({
    queryKey: ["inv-warehouses"],
    queryFn: () => getWarehousesApi(),
    enabled: !hideWarehouse,
  })
  const [visibility, setVisibility] = useState<CohortVisibility>(cohort?.visibility ?? "private")
  const [status, setStatus] = useState<CohortStatus>(cohort?.status ?? "planned")
  const [notes, setNotes] = useState(cohort?.notes ?? "")
  const [posterTemplateUrl, setPosterTemplateUrl] = useState(cohort?.poster_template_url ?? "")
  const [keepCourseAccessAfterCompletion, setKeepCourseAccessAfterCompletion] = useState(
    cohort?.keep_course_access_after_completion ?? true,
  )
  const [variationChoice, setVariationChoice] = useState<string>(cohort?.variation_id ?? "")
  const [coordinatorAccessMode, setCoordinatorAccessMode] = useState<"general" | "assigned">(
    cohort?.coordinator_access_mode ?? "general",
  )
  const [coordinatorUserIds, setCoordinatorUserIds] = useState<string[]>(
    (cohort?.coordinators ?? []).map((c) => c.id),
  )
  const [error, setError] = useState("")

  const selectedProgram = programs.find((p) => p.id === programId)
  const effectiveOrgId = organizationId || cohort?.organization_id || selectedProgram?.organization_id || null
  const { data: variations = [] } = useQuery<ProgramVariation[]>({
    queryKey: ["program-variations-modal", programId, isEdit],
    queryFn: () => listProgramVariationsApi(programId, !isEdit),
    enabled: Boolean(programId),
  })

  const effectiveVariationId = useMemo(() => {
    if (variationChoice === "__blank__") return "__blank__"
    if (variationChoice && variations.some((v) => v.id === variationChoice)) return variationChoice
    if (isEdit) return cohort?.variation_id ?? ""
    if (variations.length > 0) return (variations.find((v) => v.is_default) ?? variations[0]).id
    return ""
  }, [variationChoice, variations, isEdit, cohort])

  const selectedVariation = variations.find((v) => v.id === effectiveVariationId) ?? null
  const isBlankChoice = effectiveVariationId === "__blank__"

  useEffect(() => {
    if (!isEdit && selectedProgram) {
      if (isBlankChoice) {
        setCapacity("")
        setDurationHours("")
        setPosterTemplateUrl("")
        setKeepCourseAccessAfterCompletion(selectedProgram.keep_course_access_after_completion ?? true)
        return
      }
      const effCap = selectedVariation?.default_capacity ?? selectedProgram.default_capacity
      const effDur = selectedVariation?.duration_hours ?? selectedProgram.duration_hours
      const effPoster = selectedVariation?.poster_template_url ?? selectedProgram.poster_template_url
      const effKeep = selectedVariation?.keep_course_access_after_completion ?? selectedProgram.keep_course_access_after_completion
      setCapacity(effCap != null ? String(effCap) : "")
      setDurationHours(effDur != null ? String(effDur) : "")
      setPosterTemplateUrl(effPoster || "")
      if (effKeep != null) {
        setKeepCourseAccessAfterCompletion(effKeep)
      }
    }
  }, [selectedProgram, selectedVariation, isBlankChoice, isEdit])

  // Inline "+ New location" — so ops doesn't have to leave the cohort form
  // to reach the Catalogue page just to add a venue. Only operations/admin
  // can actually create a location (require_operations backend-side); a
  // storekeeper picks from the existing list like before.
  const canCreateLocation = hasRole("operations") || hasRole("admin")
  const [addingLocation, setAddingLocation] = useState(false)
  const [newLocName, setNewLocName] = useState("")
  const [newLocCityId, setNewLocCityId] = useState("")
  const [newLocAddress, setNewLocAddress] = useState("")
  const [newLocMapsUrl, setNewLocMapsUrl] = useState("")
  const [newLocError, setNewLocError] = useState("")
  const { data: cities = [] } = useQuery({
    queryKey: ["inv-cities"], queryFn: () => getCitiesApi(), enabled: addingLocation,
  })

  const createLocationMutation = useMutation({
    mutationFn: () => createLocationApi({
      name: newLocName.trim(), city_id: newLocCityId,
      address: newLocAddress.trim() || null, maps_url: newLocMapsUrl.trim() || null,
    }),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["inv-locations"] })
      setLocationId(created.id)
      setWarehouseId("")
      setAddingLocation(false)
      setNewLocName("")
      setNewLocCityId("")
      setNewLocAddress("")
      setNewLocMapsUrl("")
    },
    onError: (e: any) => setNewLocError(getErrorMessage(e, "Could not create the location")),
  })

  const mutation = useMutation({
    mutationFn: () => {
      if (isEdit) {
        return updateCohortApi(cohort!.id, {
          name: name.trim(),
          starts_on: startsOn || null,
          ends_on: endsOn || null,
          location_id: locationId || null,
          warehouse_id: hideWarehouse ? undefined : (warehouseId || null),
          capacity: capacity.trim() ? Number(capacity) : null,
          duration_hours: durationHours.trim() ? Number(durationHours) : null,
          visibility,
          status,
          notes: notes.trim() || null,
          poster_template_url: posterTemplateUrl.trim() || null,
          keep_course_access_after_completion: keepCourseAccessAfterCompletion,
          variation_id: effectiveVariationId && !isBlankChoice ? effectiveVariationId : null,
          ...(effectiveOrgId
            ? {
                coordinator_access_mode: coordinatorAccessMode,
                coordinator_user_ids: coordinatorAccessMode === "assigned" ? coordinatorUserIds : [],
              }
            : {}),
        })
      }
      return createCohortApi({
        program_id: programId,
        name: name.trim(),
        starts_on: startsOn || undefined,
        ends_on: endsOn || undefined,
        location_id: locationId || undefined,
        warehouse_id: hideWarehouse ? undefined : (warehouseId || undefined),
        capacity: capacity.trim() ? Number(capacity) : undefined,
        duration_hours: durationHours.trim() ? Number(durationHours) : undefined,
        organization_id: organizationId || undefined,
        management_mode: managementMode,
        visibility,
        notes: notes.trim() || undefined,
        poster_template_url: posterTemplateUrl.trim() || undefined,
        keep_course_access_after_completion: keepCourseAccessAfterCompletion,
        variation_id: !isBlankChoice && selectedVariation ? selectedVariation.id : null,
        import_default_checklists: !isBlankChoice,
        ...(effectiveOrgId
          ? {
              coordinator_access_mode: coordinatorAccessMode,
              coordinator_user_ids: coordinatorAccessMode === "assigned" ? coordinatorUserIds : [],
            }
          : {}),
      })
    },
    onSuccess: () => { toast.success(isEdit ? "Cohort updated" : "Cohort created"); onSuccess() },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to save cohort")),
  })

  return (
    <Modal title={isEdit ? `Edit cohort — ${cohort!.name}` : "New cohort"} onClose={onClose}>
      <div className="flex flex-col gap-3">
        {!isEdit && (
          <Field label="Program">
            <select
              value={programId}
              onChange={(e) => {
                const nextId = e.target.value
                setProgramId(nextId)
                const prog = programs.find((p) => p.id === nextId)
                if (prog) {
                  setKeepCourseAccessAfterCompletion(prog.keep_course_access_after_completion ?? true)
                  if (!defaultManagementMode) {
                    setManagementMode(prog.organization_id ? "partner" : "spacepoint")
                  }
                }
              }}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              <option value="">— Select a program —</option>
              {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
        )}
        {programId && (
          <Field label={isEdit ? "Program variation" : "Variation / Program defaults"}>
            <select
              value={effectiveVariationId}
              onChange={(e) => setVariationChoice(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              {variations.length === 0 && !isEdit && (
                <option value="">Apply Program Base Defaults</option>
              )}
              {isEdit && <option value="">Program Base (no variation)</option>}
              {variations.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}{v.is_default ? " ★" : ""} · {v.days_count} day{v.days_count === 1 ? "" : "s"}
                </option>
              ))}
              {!isEdit && <option value="__blank__">Start blank (do not apply defaults)</option>}
            </select>
          </Field>
        )}
        <Field label="Name">
          <input
            value={name} onChange={(e) => setName(e.target.value)} placeholder="Q3 Cohort A" autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Starts on">
            <input
              value={startsOn} onChange={(e) => setStartsOn(e.target.value)} type="date"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          <Field label="Ends on">
            <input
              value={endsOn} onChange={(e) => setEndsOn(e.target.value)} type="date"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
        </div>
        <Field label="Location (optional)">
          {addingLocation ? (
            <div className="flex flex-col gap-2 p-3 border border-border rounded-xl bg-muted/20">
              <input
                value={newLocName} onChange={(e) => setNewLocName(e.target.value)}
                placeholder="Location name" autoFocus
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
              <select
                value={newLocCityId} onChange={(e) => setNewLocCityId(e.target.value)}
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
              >
                <option value="" disabled>City (required)</option>
                {cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <input
                value={newLocAddress} onChange={(e) => setNewLocAddress(e.target.value)}
                placeholder="Address (optional)"
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
              <input
                value={newLocMapsUrl} onChange={(e) => setNewLocMapsUrl(e.target.value)}
                placeholder="Maps link (optional)"
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
              <p className="text-xs text-muted-foreground">
                The country comes from the city — there is no separate country field.
              </p>
              {newLocError && <p className="text-xs text-red-500">{newLocError}</p>}
              <div className="flex gap-2">
                <button
                  type="button" onClick={() => { setNewLocError(""); createLocationMutation.mutate() }}
                  disabled={!newLocName.trim() || !newLocCityId || createLocationMutation.isPending}
                  className="h-9 px-4 bg-primary text-primary-foreground rounded-xl text-xs font-medium hover:opacity-90 transition-colors disabled:opacity-50"
                >
                  {createLocationMutation.isPending ? "…" : "Add"}
                </button>
                <button
                  type="button"
                  onClick={() => { setAddingLocation(false); setNewLocError(""); setNewLocName(""); setNewLocCityId(""); setNewLocAddress(""); setNewLocMapsUrl("") }}
                  className="h-9 px-3 flex items-center gap-1 border border-border rounded-xl text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                >
                  <X size={13} /> Cancel
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <select
                  value={locationId}
                  onChange={(e) => { setLocationId(e.target.value); setWarehouseId("") }}
                  className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
                >
                  <option value="">— None —</option>
                  {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
                {canCreateLocation && (
                  <button
                    type="button" onClick={() => setAddingLocation(true)}
                    className="flex items-center gap-1 h-10 px-3 shrink-0 border border-border rounded-xl text-xs font-medium text-foreground hover:bg-muted transition-colors"
                  >
                    <Plus size={12} /> New
                  </button>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                The venue sessions inherit by default.
              </p>
            </>
          )}
        </Field>
        {locationId && !hideWarehouse && (
          <Field label="Warehouse (optional)">
            <select
              value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              <option value="">— Select a warehouse —</option>
              {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
            <p className="text-xs text-muted-foreground mt-1">
              Which warehouse equipment comes from. Pick any one, or leave it unset.
            </p>
          </Field>
        )}
        <div className="grid grid-cols-3 gap-3">
          <Field label="Capacity (optional)">
            <input
              value={capacity} onChange={(e) => setCapacity(e.target.value)} type="number" placeholder="20"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          <Field label="Session duration (hrs)">
            <input
              value={durationHours} onChange={(e) => setDurationHours(e.target.value)}
              type="number" step="0.5" min="0" placeholder="e.g. 2"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          <Field label="Visibility">
            <select
              value={visibility} onChange={(e) => setVisibility(e.target.value as CohortVisibility)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              {VISIBILITY_OPTIONS.map((v) => <option key={v} value={v}>{v === "public" ? "Public" : "Private"}</option>)}
            </select>
          </Field>
        </div>
        <p className="text-xs text-muted-foreground -mt-2">
          Every session in this cohort uses this duration unless it has its own override. Shown to instructors before they apply, and feeds the payment letter's hours.
        </p>
        {isEdit && (
          <Field label="Status">
            <select
              value={status} onChange={(e) => setStatus(e.target.value as CohortStatus)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              {statusOptionsFor(cohort?.status ?? "planned").map((s) => <option key={s} value={s}>{COHORT_STATUS_LABEL[s]}</option>)}
            </select>
          </Field>
        )}
        <Field label="Notes (optional)">
          <textarea
            value={notes} onChange={(e) => setNotes(e.target.value)} rows={2}
            className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors resize-none"
          />
        </Field>
        <Field label="Poster template link (optional)">
          <input
            value={posterTemplateUrl} onChange={(e) => setPosterTemplateUrl(e.target.value)}
            placeholder={
              programs.find((p) => p.id === (isEdit ? cohort.program_id : programId))?.poster_template_url
                ? `Inherited: ${programs.find((p) => p.id === (isEdit ? cohort.program_id : programId))?.poster_template_url}`
                : "https://canva.com/design/..."
            }
            type="url"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
          <p className="text-xs text-muted-foreground mt-1">
            {programs.find((p) => p.id === (isEdit ? cohort.program_id : programId))?.poster_template_url
              ? "Inherits default template from program if left empty. Enter a URL here to override it for this cohort."
              : "Shown to students and teams for their mission poster — set a cohort-specific template."}
          </p>
        </Field>
        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
          <input
            type="checkbox"
            checked={keepCourseAccessAfterCompletion}
            onChange={(e) => setKeepCourseAccessAfterCompletion(e.target.checked)}
          />
          Keep course access after completion
        </label>
        {effectiveOrgId && (
          <CoordinatorAccessPicker
            organizationId={effectiveOrgId}
            mode={coordinatorAccessMode}
            onModeChange={setCoordinatorAccessMode}
            selectedUserIds={coordinatorUserIds}
            onSelectedUserIdsChange={setCoordinatorUserIds}
          />
        )}
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()}
          loading={mutation.isPending} disabled={!name.trim() || (!isEdit && !programId)}
          label={isEdit ? "Save changes" : "Create cohort"}
        />
      </div>
    </Modal>
  )
}
