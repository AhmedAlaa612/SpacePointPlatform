import { useMemo, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { Plus, Pencil, Trash2, Search, X } from "lucide-react"
import type { Cohort, CohortStatus, CohortVisibility, Program } from "@/types/sessions"
import { getProgramsApi } from "@/api/sessions/programs"
import { getLocationsApi, getWarehousesApi, getCitiesApi, createLocationApi } from "@/api/inventory"
import {
  getCohortsApi, createCohortApi, updateCohortApi, deleteCohortApi,
} from "@/api/sessions/cohorts"
import { Modal, Field, ModalActions, ConfirmDialog, Spinner, PageHeader, EmptyState } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { useAuth } from "@/context/AuthContext"
import { getErrorMessage } from "@/lib/utils"

const STATUS_OPTIONS: CohortStatus[] = ["planned", "registration_open", "running", "completed", "cancelled"]
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
  const [programFilter, setProgramFilter] = useState("")
  const [statusFilter, setStatusFilter] = useState<CohortStatus | "">("")
  const [search, setSearch] = useState("")
  const [showPast, setShowPast] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
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
  const { data: cohorts = [], isLoading } = useQuery<Cohort[]>({
    queryKey: ["sessions-cohorts", programFilter],
    queryFn: () => getCohortsApi(programFilter || undefined),
  })

  const grouped = useMemo(() => {
    const q = search.trim().toLowerCase()
    const matching = cohorts.filter((c) => {
      if (statusFilter && c.status !== statusFilter) return false
      if (!q) return true
      return [c.name, c.program_name, c.location_name, c.location].some(
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
        subtitle="Real runs of a program — dates, capacity, and the registration desk"
        action={
          <button
            onClick={() => setCreateOpen(true)}
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

      {createOpen && (
        <CohortModal
          programs={programs}
          onClose={() => setCreateOpen(false)}
          onSuccess={() => { queryClient.invalidateQueries({ queryKey: ["sessions-cohorts"] }); setCreateOpen(false) }}
        />
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
        className="min-w-0 text-left flex-1 block"
      >
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-medium text-foreground truncate">{c.name}</p>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${COHORT_STATUS_COLOR[c.status]}`}>
            {COHORT_STATUS_LABEL[c.status]}
          </span>
          {/* Only ever shown when there's something to do about it — a "0
              unstaffed" pill on every row is noise, not information. */}
          {(c.unstaffed_count ?? 0) > 0 && (
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400">
              {c.unstaffed_count} unstaffed
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground truncate mt-0.5">
          {c.program_name ?? "—"}
          {c.starts_on ? ` · ${c.starts_on}${c.ends_on && c.ends_on !== c.starts_on ? ` – ${c.ends_on}` : ""}` : ""}
          {c.location_name ? ` · ${c.location_name}` : c.location ? ` · ${c.location}` : ""}
          {c.sessions_count != null ? ` · ${c.sessions_count} session${c.sessions_count === 1 ? "" : "s"}` : ""}
          {c.next_session_date ? ` · next ${c.next_session_date}` : ""}
        </p>
        <div className="flex items-center gap-2 mt-1.5">
          <span className="text-xs text-muted-foreground tabular-nums shrink-0">
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
export function CohortModal({ programs, cohort, onClose, onSuccess }: {
  programs: Program[]; cohort?: Cohort; onClose: () => void; onSuccess: () => void
}) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const { hasRole } = useAuth()
  const isEdit = !!cohort
  const [programId, setProgramId] = useState(cohort?.program_id ?? "")
  const [name, setName] = useState(cohort?.name ?? "")
  const [startsOn, setStartsOn] = useState(cohort?.starts_on ?? "")
  const [endsOn, setEndsOn] = useState(cohort?.ends_on ?? "")
  const [locationId, setLocationId] = useState(cohort?.location_id ?? "")
  const [warehouseId, setWarehouseId] = useState(cohort?.warehouse_id ?? "")
  const [capacity, setCapacity] = useState(cohort?.capacity != null ? String(cohort.capacity) : "")
  const { data: locations = [] } = useQuery({ queryKey: ["inv-locations"], queryFn: () => getLocationsApi() })
const { data: warehouses = [] } = useQuery({
    queryKey: ["inv-warehouses"],
    queryFn: () => getWarehousesApi(),
  })
  const [visibility, setVisibility] = useState<CohortVisibility>(cohort?.visibility ?? "public")
  const [status, setStatus] = useState<CohortStatus>(cohort?.status ?? "planned")
  const [notes, setNotes] = useState(cohort?.notes ?? "")
  const [error, setError] = useState("")

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
          warehouse_id: warehouseId || null,
          capacity: capacity.trim() ? Number(capacity) : null,
          visibility,
          status,
          notes: notes.trim() || null,
        })
      }
      return createCohortApi({
        program_id: programId,
        name: name.trim(),
        starts_on: startsOn || undefined,
        ends_on: endsOn || undefined,
        location_id: locationId || undefined,
        warehouse_id: warehouseId || undefined,
        capacity: capacity.trim() ? Number(capacity) : undefined,
        visibility,
        notes: notes.trim() || undefined,
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
              value={programId} onChange={(e) => setProgramId(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              <option value="">— Select a program —</option>
              {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
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
        {locationId && (
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
        <div className="grid grid-cols-2 gap-3">
          <Field label="Capacity (optional)">
            <input
              value={capacity} onChange={(e) => setCapacity(e.target.value)} type="number" placeholder="20"
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
        {isEdit && (
          <Field label="Status">
            <select
              value={status} onChange={(e) => setStatus(e.target.value as CohortStatus)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{COHORT_STATUS_LABEL[s]}</option>)}
            </select>
          </Field>
        )}
        <Field label="Notes (optional)">
          <textarea
            value={notes} onChange={(e) => setNotes(e.target.value)} rows={2}
            className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors resize-none"
          />
        </Field>
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
