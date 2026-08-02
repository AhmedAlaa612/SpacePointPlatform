import { useEffect, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "@tanstack/react-router"
import { ArrowLeft, MapPin, Trash2, Warehouse } from "lucide-react"
import type {
  Cohort, Session, StaffingStatus, EligibleInstructor, AttendanceStatus, SessionDelivery,
} from "@/types/sessions"
import { getLocationsApi, getWarehousesApi } from "@/api/inventory"
import { SessionKitAssignment } from "@/pages/admin/components/SessionKitAssignment"
import { SessionOpeningsPanel } from "@/pages/admin/components/SessionOpeningsPanel"
import { MaterialsPanel } from "@/pages/admin/components/MaterialsPanel"
import {
  getCohortApi, getSessionsApi, updateSessionApi, assignInstructorApi, unassignInstructorApi, deleteSessionApi,
  getSessionHistoryApi,
} from "@/api/sessions/cohorts"
import {
  openCallApi, reopenStaffingApi, listEligibleInstructorsApi, selectInstructorsApi, closeCallApi,
  listSessionCallsApi, closeOneCallApi,
} from "@/api/sessions/staffing"
import { getDeliveryRolesApi, getOpeningsApi } from "@/api/sessions/openings"
import { getSessionDeliveryApi, markAttendanceApi } from "@/api/sessions/delivery"
import { Modal, Field, ConfirmDialog, Spinner, PageHeader } from "@/pages/admin/components/common"
import { InheritedFrom } from "@/pages/admin/components/InheritedFrom"
import { UserProfileModal } from "@/components/UserProfileModal"
import { useToast } from "@/components/ui/toast"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"

const STAFFING_STATUS_LABEL: Record<StaffingStatus, string> = {
  unstaffed: "Unstaffed",
  open_call: "Open call",
  staffed: "Staffed",
}

const STAFFING_STATUS_COLOR: Record<StaffingStatus, string> = {
  unstaffed: "bg-muted text-muted-foreground",
  open_call: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400",
  staffed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
}

/* ================================================================== */
/* Session detail page — edit title/price/material + assign instructor */
/* Was SessionDetailModal (a dialog inside Cohorts.tsx); now a real     */
/* route (/operations/cohorts/$cohortId/sessions/$sessionId).          */
/* ================================================================== */
export default function SessionDetail() {
  const { cohortId, sessionId } = useParams({ strict: false }) as { cohortId: string; sessionId: string }
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: cohort, isLoading: cohortLoading } = useQuery<Cohort>({
    queryKey: ["sessions-cohort", cohortId],
    queryFn: () => getCohortApi(cohortId),
  })
  const { data: sessions = [], isLoading: sessionsLoading } = useQuery<Session[]>({
    queryKey: ["sessions-sessions", cohortId],
    queryFn: () => getSessionsApi(cohortId),
  })

  const invalidateSessions = () => {
    queryClient.invalidateQueries({ queryKey: ["sessions-sessions", cohortId] })
    // Kits move to the lead instructor automatically the moment both exist
    // (2026-08-01) — instructor assignment can trigger that from over here,
    // so the Kits panel's own query needs a nudge too, not just the session list.
    queryClient.invalidateQueries({ queryKey: ["session-kits"] })
  }

  if (cohortLoading || sessionsLoading) return <Spinner />

  const session = sessions.find((s) => s.id === sessionId)

  if (!cohort || !session) {
    return (
      <div className="flex flex-col gap-4">
        <Link
          to="/operations/cohorts/$cohortId" params={{ cohortId }}
          className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft size={14} /> Back to cohort
        </Link>
        <p className="text-sm text-muted-foreground">Session not found.</p>
      </div>
    )
  }

  return (
    <SessionDetailView
      key={sessionId}
      cohort={cohort}
      session={session}
      onChanged={invalidateSessions}
      onDeleted={() => void navigate({ to: "/operations/cohorts/$cohortId", params: { cohortId } })}
    />
  )
}

function SessionDetailView({ cohort, session, onChanged, onDeleted }: {
  cohort: Cohort; session: Session; onChanged: () => void; onDeleted: () => void
}) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<"setup" | "attendance" | "history">("setup")
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [title, setTitle] = useState(session.title ?? "")
  const [price, setPrice] = useState(session.price != null ? String(session.price) : "")
  const [locationId, setLocationId] = useState(session.location_id ?? "")
  const [warehouseId, setWarehouseId] = useState(session.warehouse_id ?? "")
  const { data: locations = [] } = useQuery({ queryKey: ["inv-locations"], queryFn: () => getLocationsApi() })
  // Scoped to the session's own override when set, else the cohort's
  // effective location — same fallback chain the server resolves.
  const warehousePickerLocationId = locationId || cohort.location_id || ""
  const { data: warehouses = [] } = useQuery({
    queryKey: ["inv-warehouses", warehousePickerLocationId],
    queryFn: () => getWarehousesApi(warehousePickerLocationId || undefined),
    enabled: !!warehousePickerLocationId,
  })
  const [error, setError] = useState("")

  const saveMutation = useMutation({
    mutationFn: () => updateSessionApi(cohort.id, session.id, {
      title: title.trim() || null,
      price: price.trim() ? Number(price) : null,
      location_id: locationId || null,
      warehouse_id: warehouseId || null,
    }),
    onSuccess: () => { setError(""); toast.success("Session saved"); onChanged() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to save session"),
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteSessionApi(cohort.id, session.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cohort-sessions", cohort.id] })
      toast.success("Session deleted")
      onChanged()
      onDeleted()
      navigate({ to: "/operations/cohorts/$cohortId", params: { cohortId: cohort.id } })
    },
    onError: (e: any) => {
      setError(e?.response?.data?.detail ?? "Could not delete session")
      setDeleteConfirmOpen(false)
    },
  })

  return (
    <div className="flex flex-col gap-4">
      <Link
        to="/operations/cohorts/$cohortId" params={{ cohortId: cohort.id }}
        className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft size={14} /> Back to cohort
      </Link>

      <PageHeader
        title={`Session — ${session.meeting_date}`}
        subtitle={`${cohort.name}${session.starts_at ? ` · ${session.starts_at.slice(0, 5)}` : ""}`}
      />

      {/* Tabs Navigation */}
      <div className="flex border-b border-border gap-2">
        <button
          onClick={() => setActiveTab("setup")}
          className={cn(
            "px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px",
            activeTab === "setup"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          Setup &amp; Staffing
        </button>
        <button
          onClick={() => setActiveTab("attendance")}
          className={cn(
            "px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px",
            activeTab === "attendance"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          Attendance
        </button>
        <button
          onClick={() => setActiveTab("history")}
          className={cn(
            "px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px",
            activeTab === "history"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          Session History
        </button>
      </div>

      {activeTab === "setup" && (
        <>
          <StaffingSection cohort={cohort} session={session} onChanged={onChanged} />

          <Card className="px-4">
            <SessionKitAssignment
              sessionId={session.id}
              hasInstructor={session.instructors.length > 0}
              effectiveWarehouseId={session.effective_warehouse_id ?? null}
              effectiveWarehouseName={session.effective_warehouse_name ?? null}
              onChanged={onChanged}
            />
          </Card>

          <Card className="px-4">
            <MaterialsPanel
              owner={{ session_id: session.id }}
              level="cohort"
              inheritedNote="Leave empty to use the cohort's (or the program's)."
            />
          </Card>

          <details className="rounded-2xl border border-border bg-card group">
            <summary className="flex items-center justify-between gap-2 px-4 py-3 cursor-pointer select-none list-none">
              <span className="text-sm font-semibold text-foreground">Session details &amp; overrides</span>
              <span className="text-xs text-muted-foreground">Title, price, location, what it offers</span>
            </summary>
            <div className="flex flex-col gap-3 px-4 pb-4 pt-1 border-t border-border">
              <Field label="Title (optional)">
                <input
                  value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Intro to Orbits"
                  className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                />
              </Field>
              <Field label="Price override (optional)">
                <input
                  value={price} onChange={(e) => setPrice(e.target.value)} type="number" placeholder="Leave blank to use the program price"
                  className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                />
              </Field>

              <div className="rounded-2xl border border-border bg-card p-4 flex flex-col gap-4">
                <p className="text-sm font-semibold text-foreground">Location &amp; warehouse</p>

                <div className="flex flex-col gap-1.5">
                  <InheritedFrom
                    label="Location"
                    icon={<MapPin size={12} />}
                    overridden={!!locationId}
                    using={session.effective_location_name ?? "No location set"}
                    onRevert={() => { setLocationId(""); setWarehouseId("") }}
                    hint="Only set this when this specific session meets somewhere other than usual."
                  />
                  <select
                    value={locationId}
                    onChange={(e) => { setLocationId(e.target.value); setWarehouseId("") }}
                    className="h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
                  >
                    <option value="">
                      {cohort.location_name ? `Use cohort default (${cohort.location_name})` : "Use cohort default (none set)"}
                    </option>
                    {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                  </select>
                </div>

                {warehousePickerLocationId && (
                  <div className="flex flex-col gap-1.5 border-t border-border pt-4">
                    <InheritedFrom
                      label="Warehouse"
                      icon={<Warehouse size={12} />}
                      overridden={!!warehouseId}
                      autoResolved={!!locationId}
                      using={session.effective_warehouse_name ?? "Not resolved yet"}
                      onRevert={() => setWarehouseId("")}
                      hint="Which warehouse this session's equipment comes from — only set it when that differs from the cohort's."
                    />
                    <select
                      value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}
                      className="h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
                    >
                      <option value="">
                        {cohort.effective_warehouse_name && !locationId
                          ? `Inherit (${cohort.effective_warehouse_name})` : "Resolve automatically"}
                      </option>
                      {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                    </select>
                  </div>
                )}
              </div>
              {error && <p className="text-xs text-red-500">{error}</p>}
              <button
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending}
                className="w-fit h-10 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
              >
                {saveMutation.isPending ? "Saving…" : "Save details"}
              </button>

              <SessionOpeningsPanel sessionId={session.id} />
            </div>
          </details>

          <div className="border-t border-border pt-3 mt-1 flex justify-end">
            <button
              onClick={() => setDeleteConfirmOpen(true)}
              disabled={deleteMutation.isPending}
              className="text-xs font-medium text-red-600 dark:text-red-400 hover:opacity-80 transition-colors disabled:opacity-50 inline-flex items-center gap-1.5"
            >
              <Trash2 size={13} /> Delete this session
            </button>
          </div>
        </>
      )}

      {activeTab === "attendance" && (
        <SessionAttendanceRosterSection sessionId={session.id} />
      )}

      {activeTab === "history" && (
        <SessionHistoryPanel sessionId={session.id} />
      )}

      {deleteConfirmOpen && (
        <ConfirmDialog
          title={`Delete the session on ${session.meeting_date}?`}
          description="This only works if no attendance has been recorded for it."
          confirmLabel="Delete session"
          destructive
          pending={deleteMutation.isPending}
          onCancel={() => setDeleteConfirmOpen(false)}
          onConfirm={() => { deleteMutation.mutate(); setDeleteConfirmOpen(false) }}
        />
      )}
    </div>
  )
}

/* ================================================================== */
/* Staffing — everything about who runs this session, in one card.     */
/* 2026-08-02: absorbed the separate "Instructor(s)" section that used */
/* to sit ~300px below with its own instructor picker and its own role */
/* picker. That was the same job as this one, minus "they applied", so */
/* there were three role dropdowns and three mental models on one      */
/* screen. Operator requirement (2026-07-24) still holds: the picker   */
/* shows every eligible instructor/facilitator, not just those who     */
/* registered interest — multi-select, select-all, clickable profile.  */
/* ================================================================== */
function StaffingSection({ cohort, session, onChanged }: {
  cohort: Cohort; session: Session; onChanged: () => void
}) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  // Direct assignment (no open call involved) — moved here from the page.
  const [instructorId, setInstructorId] = useState("")
  const [assignRoleId, setAssignRoleId] = useState("")
  // Assigning used to close the open call unconditionally, which blocked
  // further interest even when ops still wanted more people (2026-07-26).
  const [closeCall, setCloseCall] = useState(true)
  const [roleId, setRoleId] = useState("")
  // Per-row role choice for the single-click "Assign" button — defaults to
  // whatever the instructor actually applied for (B1), else the first role,
  // once both the roster and delivery roles have loaded.
  const [rowRoleIds, setRowRoleIds] = useState<Record<string, string>>({})
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
  const [error, setError] = useState("")
  const [lastResult, setLastResult] = useState<{ assigned: number; withoutInterest: number } | null>(null)

  const [openCallModalTarget, setOpenCallModalTarget] = useState(false)
  const [openCallModalMode, setOpenCallModalMode] = useState<"open" | "reopen">("open")

  const isOpenCall = session.staffing_status === "open_call"

  const { data: deliveryRoles = [] } = useQuery({
    queryKey: ["delivery-roles"], queryFn: () => getDeliveryRolesApi(),
  })
  useEffect(() => {
    if (!roleId && deliveryRoles.length) setRoleId(deliveryRoles[0].id)
  }, [deliveryRoles, roleId])
  useEffect(() => {
    if (!assignRoleId && deliveryRoles.length) setAssignRoleId(deliveryRoles[0].id)
  }, [deliveryRoles, assignRoleId])
  const rolesLoaded = deliveryRoles.length > 0

  // Unconditional now (was `enabled: isOpenCall`): the direct-assign picker
  // below needs this roster whether or not a call is open — that's the whole
  // point of being able to staff a session without opening one.
  const eligible = useQuery<EligibleInstructor[]>({
    queryKey: ["staffing-eligible-instructors", session.id],
    queryFn: () => listEligibleInstructorsApi(session.id),
  })
  const assignableUsers = (eligible.data ?? [])
    .filter((e) => !session.instructors.some((si) => si.user_id === e.user_id))

  const assignMutation = useMutation({
    mutationFn: () => assignInstructorApi(cohort.id, session.id, { user_id: instructorId, role_id: assignRoleId }),
    onSuccess: () => { toast.success("Instructor assigned"); setInstructorId(""); invalidate() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to assign instructor"),
  })
  const unassignMutation = useMutation({
    mutationFn: (userId: string) => unassignInstructorApi(cohort.id, session.id, userId),
    onSuccess: () => { toast.success("Instructor removed"); invalidate() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to remove instructor"),
  })

  // A session can have several calls open at once (2026-08-01) — this is
  // the "view open calls, public or targeted, edit them or close them" list.
  const calls = useQuery({
    queryKey: ["staffing-calls", session.id],
    queryFn: () => listSessionCallsApi(session.id),
    enabled: isOpenCall,
  })
  const openCalls = (calls.data ?? []).filter((c) => c.status === "open")
  const closeOneMutation = useMutation({
    mutationFn: ({ callId, clearInterest }: { callId: string; clearInterest: boolean }) =>
      closeOneCallApi(session.id, callId, clearInterest),
    onSuccess: () => {
      toast.success("Call closed")
      queryClient.invalidateQueries({ queryKey: ["staffing-calls", session.id] })
      invalidate()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to close that call"),
  })

  useEffect(() => {
    if (!rolesLoaded || !eligible.data) return
    setRowRoleIds((prev) => {
      const next = { ...prev }
      let changed = false
      for (const u of eligible.data!) {
        if (!next[u.user_id]) {
          next[u.user_id] = u.interest_role_id ?? deliveryRoles[0].id
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [rolesLoaded, eligible.data, deliveryRoles])

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["staffing-eligible-instructors", session.id] })
    queryClient.invalidateQueries({ queryKey: ["staffing-calls", session.id] })
    onChanged()
  }

  const openCallMutation = useMutation({
    mutationFn: ({ userIds, roleIds }: { userIds?: string[]; roleIds?: string[] }) =>
      openCallApi(session.id, userIds, roleIds),
    onSuccess: () => {
      toast.success("Call opened")
      setOpenCallModalTarget(false)
      invalidate()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to open call"),
  })

  const [closeCallOptionOpen, setCloseCallOptionOpen] = useState(false)

  const closeCallMutation = useMutation({
    mutationFn: (clearInterest: boolean) => closeCallApi(session.id, clearInterest),
    onSuccess: () => {
      toast.success("Call closed")
      setCloseCallOptionOpen(false)
      invalidate()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to close call"),
  })

  const reopenMutation = useMutation({
    mutationFn: ({ targetUserIds, roleIds }: { targetUserIds?: string[]; roleIds?: string[] } = {}) =>
      reopenStaffingApi(session.id, targetUserIds, roleIds),
    onSuccess: () => { toast.success("Call reopened"); invalidate() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to reopen"),
  })

  const selectMutation = useMutation({
    mutationFn: () => selectInstructorsApi(session.id, selectedIds, roleId, closeCall),
    onSuccess: (result) => {
      toast.success(`Assigned ${result.assigned.length} instructor(s)`)
      setLastResult({ assigned: result.assigned.length, withoutInterest: result.without_interest.length })
      setSelectedIds([])
      invalidate()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to assign selected instructors"),
  })

  const assignSingleMutation = useMutation({
    mutationFn: ({ userId, assignRole }: { userId: string; assignRole: string }) =>
      selectInstructorsApi(session.id, [userId], assignRole),
    onSuccess: () => {
      toast.success("Instructor assigned")
      invalidate()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to assign instructor"),
  })

  // Open call roster is interest-only — picking someone who hasn't registered
  // interest goes through "Target Instructors…" instead, so this list doesn't
  // duplicate that picker.
  const roster = (eligible.data ?? []).filter((u) => u.interested)

  const allSelected = roster.length > 0 && selectedIds.length === roster.length
  const toggleAll = () => setSelectedIds(allSelected ? [] : roster.map((r) => r.user_id))
  const toggleOne = (userId: string) =>
    setSelectedIds((prev) => prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId])

  return (
    <div className="rounded-2xl border border-border bg-card p-4">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div>
          <p className="text-sm font-semibold text-foreground">Staffing</p>
          <p className="text-xs text-muted-foreground">Who's running this session, and who wants to</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${STAFFING_STATUS_COLOR[session.staffing_status]}`}>
            {STAFFING_STATUS_LABEL[session.staffing_status]}
          </span>
          {isOpenCall && (
            <button
              onClick={() => { setError(""); setCloseCallOptionOpen(true) }}
              className="text-xs font-semibold text-red-500 hover:text-red-600 px-2 py-1 rounded-lg border border-red-500/20 hover:bg-red-500/10 transition-colors"
              title="Close or pause every call on this session"
            >
              Close call
            </button>
          )}
        </div>
      </div>

      {/* Assigned, then one way to add someone directly. Below that, the
          call layer — same job, but for people who put their hand up. */}
      {session.instructors.length > 0 && (
        <div className="flex flex-col gap-1.5 mb-2">
          {session.instructors.map((si) => (
            <div key={si.user_id} className="flex items-center justify-between px-3 py-2 bg-background border border-border rounded-xl">
              <span className="text-sm text-foreground">
                {si.full_name} <span className="text-xs text-muted-foreground">({si.role})</span>
              </span>
              <button
                onClick={() => unassignMutation.mutate(si.user_id)}
                disabled={unassignMutation.isPending}
                className="text-xs font-medium text-red-500 hover:opacity-80 transition-colors disabled:opacity-50"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-3">
        <select
          value={instructorId} onChange={(e) => setInstructorId(e.target.value)}
          className="flex-1 h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer min-w-[160px]"
        >
          <option value="">— Add an instructor directly —</option>
          {assignableUsers.map((u) => (
            <option key={u.user_id} value={u.user_id}>{u.full_name || u.email}</option>
          ))}
        </select>
        <select
          value={assignRoleId} onChange={(e) => setAssignRoleId(e.target.value)}
          disabled={!rolesLoaded}
          className="h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer disabled:opacity-50"
        >
          {deliveryRoles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
        <button
          onClick={() => { setError(""); assignMutation.mutate() }}
          disabled={!instructorId || !assignRoleId || assignMutation.isPending}
          className="h-9 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
        >
          Assign
        </button>
      </div>

      {isOpenCall && openCalls.length > 0 && (
        <div className="mb-3 flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Open calls ({openCalls.length})
            </p>
            <button
              onClick={() => { setError(""); setOpenCallModalMode("open"); setOpenCallModalTarget(true) }}
              className="text-[11px] font-medium text-primary hover:underline"
            >
              + Add another call…
            </button>
          </div>
          {openCalls.map((c) => (
            <div key={c.id} className="flex items-center justify-between gap-2 px-3 py-2 bg-background border border-border rounded-xl">
              <span className="text-xs text-foreground min-w-0 truncate">
                {c.label || (c.target_user_ids.length === 0 ? "Public — open to everyone" : "Targeted")}
                {c.target_user_ids.length > 0 && (
                  <span className="ml-1.5 text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-purple-500/15 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                    {c.target_user_ids.length} instructor{c.target_user_ids.length === 1 ? "" : "s"}
                  </span>
                )}
              </span>
              <button
                onClick={() => { setError(""); closeOneMutation.mutate({ callId: c.id, clearInterest: false }) }}
                disabled={closeOneMutation.isPending}
                className="text-[11px] font-medium text-muted-foreground hover:text-red-600 shrink-0 disabled:opacity-50"
              >
                Close
              </button>
            </div>
          ))}
        </div>
      )}

      {session.staffing_status === "unstaffed" && (
        <div className="flex flex-col sm:flex-row gap-2">
          <button
            onClick={() => { setError(""); openCallMutation.mutate({}) }}
            disabled={openCallMutation.isPending}
            className="flex-1 h-10 bg-primary/10 border border-primary/30 text-primary rounded-xl text-sm font-medium hover:bg-primary/20 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            Open call (all instructors)
          </button>
          <button
            onClick={() => { setError(""); setOpenCallModalMode("open"); setOpenCallModalTarget(true) }}
            className="h-10 px-4 border border-border text-foreground rounded-xl text-sm font-medium hover:bg-muted transition-colors flex items-center justify-center gap-1.5"
          >
            Target instructors…
          </button>
        </div>
      )}

      {session.staffing_status === "staffed" && (
        <div className="flex flex-col gap-1.5">
          <button
            onClick={() => { setError(""); reopenMutation.mutate({}) }}
            disabled={reopenMutation.isPending}
            className="w-full h-9 border border-border rounded-xl text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:opacity-50"
          >
            {session.target_user_ids?.length > 0
              ? `Reopen for the same ${session.target_user_ids.length} instructor(s)`
              : "Reopen call for more interest"}
          </button>
          {/* Without this the only reopen keeps the original restriction, and
              there'd be no way to widen a targeted call short of closing it. */}
          {session.target_user_ids?.length > 0 && (
            <button
              onClick={() => { setError(""); reopenMutation.mutate({ targetUserIds: [] }) }}
              disabled={reopenMutation.isPending}
              className="w-full h-8 text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
            >
              …or reopen it to all instructors
            </button>
          )}
          <button
            onClick={() => { setError(""); setOpenCallModalMode("reopen"); setOpenCallModalTarget(true) }}
            className="w-full h-8 text-[11px] font-medium text-primary hover:underline transition-colors"
          >
            Reopen for specific roles…
          </button>
        </div>
      )}

      {isOpenCall && (
        <div className="space-y-3">
          {eligible.isLoading ? (
            <Spinner />
          ) : roster.length === 0 ? (
            <div className="p-4 border border-dashed border-border rounded-xl bg-muted/30 text-center">
              <p className="text-xs text-muted-foreground font-medium">
                No interest registered yet. To bring in a specific instructor directly, use "+ Add another
                call…" above.
              </p>
            </div>
          ) : (
            <>
              {/* A5: one list, interested instructors sorted first, rather than
                  a duplicate "interested" section plus a separate full-roster
                  picker. A7: role comes from a picker driven by delivery_roles
                  (defaulting to what the instructor applied for), not two
                  hardcoded "Lead"/"Co-instructor" buttons. */}
              <div className="flex items-center justify-between gap-2 pb-1">
                <label className="flex items-center gap-2 text-xs font-medium text-foreground cursor-pointer select-none">
                  <input type="checkbox" checked={allSelected} onChange={toggleAll}
                    className="rounded text-primary focus:ring-primary border-border bg-background" />
                  Select all ({roster.length})
                </label>
                {!rolesLoaded && <span className="text-[11px] text-muted-foreground">Loading roles…</span>}
              </div>

              <div className="flex flex-col gap-1.5 max-h-80 overflow-y-auto pr-1">
                {roster.map((u) => {
                  const assigned = session.instructors.find((i) => i.user_id === u.user_id)
                  return (
                  <div key={u.user_id} className="p-3 bg-card border border-border rounded-xl flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0 flex-1 flex items-center gap-3">
                      <input type="checkbox" checked={selectedIds.includes(u.user_id)} onChange={() => toggleOne(u.user_id)}
                        className="rounded text-primary focus:ring-primary border-border bg-background shrink-0" />
                      <button onClick={() => setProfileUserId(u.user_id)} className="shrink-0 font-bold text-xs w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center">
                        {u.full_name ? u.full_name.charAt(0).toUpperCase() : u.email.charAt(0).toUpperCase()}
                      </button>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <button onClick={() => setProfileUserId(u.user_id)} className="text-sm font-semibold text-foreground hover:text-primary transition-colors truncate text-left">
                            {u.full_name || u.email}
                          </button>
                          {u.interested && (
                            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 shrink-0">
                              Interested
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground truncate">{u.email}</p>
                        {u.interest_role_name && (
                          <p className="text-[11px] text-primary/80 truncate">Applied for: {u.interest_role_name}</p>
                        )}
                        {u.note && (
                          <p className="text-xs text-foreground/90 italic bg-muted/50 px-2.5 py-1 rounded-lg mt-1 border border-border/50">
                            "{u.note}"
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      {assigned ? (
                        <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                          Assigned · {assigned.role}
                        </span>
                      ) : (
                        <>
                          <select
                            value={rowRoleIds[u.user_id] ?? ""}
                            onChange={(e) => setRowRoleIds((prev) => ({ ...prev, [u.user_id]: e.target.value }))}
                            disabled={!rolesLoaded}
                            className="h-8 px-2 border border-border bg-card text-foreground rounded-lg text-xs focus:outline-none focus:border-primary transition-colors cursor-pointer disabled:opacity-50"
                          >
                            {deliveryRoles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                          </select>
                          <button
                            onClick={() => assignSingleMutation.mutate({ userId: u.user_id, assignRole: rowRoleIds[u.user_id] })}
                            disabled={!rolesLoaded || !rowRoleIds[u.user_id] || assignSingleMutation.isPending}
                            className="h-8 px-3 bg-primary text-primary-foreground text-xs font-semibold rounded-lg hover:opacity-90 transition-colors disabled:opacity-50"
                          >
                            Assign
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                  )
                })}
              </div>

              <div className="space-y-2 bg-muted/20 p-3 rounded-xl border border-border">
                <label className="flex items-start gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox" checked={closeCall} onChange={(e) => setCloseCall(e.target.checked)}
                    className="rounded text-primary focus:ring-primary border-border bg-background shrink-0 mt-0.5"
                  />
                  <span className="text-[11px] text-muted-foreground leading-snug">
                    Close the open call after assigning.
                    {" "}Untick to keep collecting interest — useful when you want to pick
                    several instructors over time rather than all at once.
                  </span>
                </label>

                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground shrink-0">Role for selected:</span>
                  <select
                    value={roleId} onChange={(e) => setRoleId(e.target.value)}
                    disabled={!rolesLoaded}
                    className="h-8 px-2 border border-border bg-card text-foreground rounded-lg text-xs focus:outline-none focus:border-primary transition-colors cursor-pointer disabled:opacity-50 flex-1"
                  >
                    {deliveryRoles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                  </select>
                </div>

                <button
                  onClick={() => { setError(""); setLastResult(null); selectMutation.mutate() }}
                  disabled={!rolesLoaded || selectedIds.length === 0 || selectMutation.isPending}
                  className="w-full h-9 bg-primary text-primary-foreground rounded-xl text-xs font-medium hover:opacity-90 transition-colors disabled:opacity-50"
                >
                  {selectMutation.isPending ? "Assigning…" : `Assign selected (${selectedIds.length})`}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {lastResult && session.staffing_status === "staffed" && (
        <p className="text-xs text-muted-foreground mt-2">
          Assigned {lastResult.assigned}.
          {lastResult.withoutInterest > 0 ? ` ${lastResult.withoutInterest} of them hadn't registered interest.` : ""}
        </p>
      )}
      {error && <p className="text-xs text-red-500 mt-2">{error}</p>}

      {profileUserId && <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />}
      {openCallModalTarget && (
        <TargetedOpenCallModal
          sessionId={session.id}
          mode={openCallModalMode}
          onClose={() => setOpenCallModalTarget(false)}
          onSuccess={() => {
            setOpenCallModalTarget(false)
            invalidate()
          }}
        />
      )}
      {closeCallOptionOpen && (
        <Modal title="Close open call options" onClose={() => setCloseCallOptionOpen(false)} maxWidth="max-w-md">
          <div className="flex flex-col gap-4">
            <p className="text-xs text-muted-foreground">
              Select how you would like to close this open call:
            </p>

            <div className="space-y-2.5">
              <button
                onClick={() => closeCallMutation.mutate(false)}
                disabled={closeCallMutation.isPending}
                className="w-full text-left p-3.5 border border-border bg-card rounded-xl hover:border-primary/50 transition-all group cursor-pointer"
              >
                <p className="text-xs font-bold text-foreground group-hover:text-primary transition-colors">Pause call (keep registered interests)</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Pauses open registration. Previously submitted interest notes remain saved if you reopen the call later.
                </p>
              </button>

              <button
                onClick={() => closeCallMutation.mutate(true)}
                disabled={closeCallMutation.isPending}
                className="w-full text-left p-3.5 border border-red-500/30 bg-red-500/5 rounded-xl hover:bg-red-500/10 transition-all cursor-pointer"
              >
                <p className="text-xs font-bold text-red-500">Abort call & delete interests</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Cancels the call and permanently deletes all registered interest entries for a completely clean slate.
                </p>
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

/* ================================================================== */
/* Session attendance roster section inside SessionDetail              */
/* ================================================================== */
function SessionAttendanceRosterSection({ sessionId }: { sessionId: string }) {
  const queryClient = useQueryClient()
  const { data: delivery, isLoading } = useQuery<SessionDelivery>({
    queryKey: ["session-delivery", sessionId],
    queryFn: () => getSessionDeliveryApi(sessionId),
  })

  const markMutation = useMutation({
    mutationFn: ({ registrationId, status }: { registrationId: string; status: AttendanceStatus }) =>
      markAttendanceApi(sessionId, registrationId, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["session-delivery", sessionId] })
      queryClient.invalidateQueries({ queryKey: ["sessions-registrations"] })
    },
  })

  if (isLoading) return <Spinner />
  const roster = delivery?.roster ?? []

  const statusColors: Record<string, string> = {
    present: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 border-emerald-500/30",
    absent: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400 border-red-500/30",
  }

  return (
    <div className="border-t border-border pt-4 mt-2">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Student attendance roster</p>
          <p className="text-xs text-muted-foreground">View and mark attendance for students in this session ({roster.length} registered)</p>
        </div>
      </div>

      {roster.length === 0 ? (
        <p className="text-xs text-muted-foreground italic p-3 bg-muted/20 border border-border rounded-xl">
          No students registered in this cohort yet.
        </p>
      ) : (
        <div className="flex flex-col gap-2 max-h-64 overflow-y-auto pr-1">
          {roster.map((entry) => (
            <div key={entry.registration_id} className="p-3 bg-card border border-border rounded-xl flex flex-wrap items-center justify-between gap-2 shadow-sm">
              <div>
                <p className="text-xs font-semibold text-foreground">{entry.student_name}</p>
                <p className="text-[11px] text-muted-foreground">{entry.student_phone ?? "No phone"}</p>
              </div>

              <div className="flex items-center gap-1.5 flex-wrap">
                {(["present", "absent"] as AttendanceStatus[]).map((st) => {
                  const isActive = entry.att_status === st
                  return (
                    <button
                      key={st}
                      onClick={() => markMutation.mutate({ registrationId: entry.registration_id, status: st })}
                      disabled={markMutation.isPending}
                      className={`text-xs font-medium px-2.5 py-1 rounded-lg border transition-all ${
                        isActive
                          ? `${statusColors[st]} font-bold shadow-xs`
                          : "border-border text-muted-foreground hover:bg-muted"
                      }`}
                    >
                      {st.charAt(0).toUpperCase() + st.slice(1)}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ================================================================== */
/* Targeted Open Call modal for selecting specific instructors        */
/* ================================================================== */
function TargetedOpenCallModal({
  sessionId,
  mode = "open",
  onClose,
  onSuccess,
}: {
  sessionId: string
  /** "open": opens a new call — works from unstaffed, or to add another call
   *  alongside ones already open (2026-08-01). "reopen": staffed -> open_call,
   *  without touching existing assignments — the common B2 case ("we still
   *  need 2 Assistants"). */
  mode?: "open" | "reopen"
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  const [selectedUserIds, setSelectedUserIds] = useState<string[]>([])
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([])
  const [error, setError] = useState("")

  // NOT /admin/users — require_admin, so ops saw an empty list and no error.
  // This is the "target specific instructors" picker, and it was the reason it
  // came up blank even with instructors on the platform.
  const { data: eligible = [], isLoading } = useQuery<EligibleInstructor[]>({
    queryKey: ["staffing-eligible-instructors", sessionId],
    queryFn: () => listEligibleInstructorsApi(sessionId),
  })
  const instructors = eligible.map((e) => ({ id: e.user_id, full_name: e.full_name, email: e.email }))

  // B2: which roles are on offer. Ops sees every opening here, including
  // ones already closed — that's what "reopen for just the roles still
  // needed" is picking from. Sessions with no openings configured skip this
  // section entirely: there's nothing to scope by role.
  const { data: openings = [] } = useQuery({
    queryKey: ["session-openings", sessionId], queryFn: () => getOpeningsApi(sessionId),
  })
  useEffect(() => {
    if (selectedRoleIds.length === 0 && openings.length) {
      setSelectedRoleIds(openings.map((o) => o.role_id))
    }
  }, [openings, selectedRoleIds])

  const mutation = useMutation({
    mutationFn: ({ userIds, roleIds }: { userIds?: string[]; roleIds?: string[] }) =>
      mode === "reopen"
        ? reopenStaffingApi(sessionId, userIds, roleIds)
        : openCallApi(sessionId, userIds, roleIds),
    onSuccess: () => { toast.success(mode === "reopen" ? "Call reopened" : "Call opened"); onSuccess() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to open call"),
  })

  const toggleAll = () => {
    if (selectedUserIds.length === instructors.length) {
      setSelectedUserIds([])
    } else {
      setSelectedUserIds(instructors.map((u) => u.id))
    }
  }

  const toggleOne = (id: string) => {
    setSelectedUserIds((prev) => prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id])
  }

  const allRolesSelected = openings.length > 0 && selectedRoleIds.length === openings.length
  const toggleAllRoles = () => setSelectedRoleIds(allRolesSelected ? [] : openings.map((o) => o.role_id))
  const toggleRole = (id: string) =>
    setSelectedRoleIds((prev) => prev.includes(id) ? prev.filter((r) => r !== id) : [...prev, id])

  // Omitting role_ids opens every role (the API default) — only send an
  // explicit list when it's a real restriction, i.e. not all of them.
  const roleIdsForSubmit = openings.length === 0 || allRolesSelected ? undefined : selectedRoleIds

  return (
    <Modal title={mode === "reopen" ? "Reopen call" : "Open call for instructor interest"} onClose={onClose} maxWidth="max-w-md">
      <div className="flex flex-col gap-4">
        <p className="text-xs text-muted-foreground">
          Picking specific instructors <strong className="text-foreground">restricts</strong> the call to them:
          the session only appears on their Available Sessions page, and only they can register
          interest. Opening it to everyone leaves it visible to all instructors and facilitators.
        </p>

        {openings.length > 0 && (
          <div className="flex flex-col gap-1.5 pb-3 border-b border-border">
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-xs font-semibold text-foreground cursor-pointer select-none">
                <input type="checkbox" checked={allRolesSelected} onChange={toggleAllRoles} />
                Roles on offer ({selectedRoleIds.length}/{openings.length})
              </label>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {openings.map((o) => (
                <label
                  key={o.role_id}
                  className={cn(
                    "flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs cursor-pointer transition-colors",
                    selectedRoleIds.includes(o.role_id)
                      ? "border-primary/30 bg-primary/10 text-primary"
                      : "border-border text-muted-foreground hover:bg-muted",
                  )}
                >
                  <input
                    type="checkbox" className="hidden"
                    checked={selectedRoleIds.includes(o.role_id)}
                    onChange={() => toggleRole(o.role_id)}
                  />
                  {o.role_name} ({o.remaining} left)
                </label>
              ))}
            </div>
          </div>
        )}

        <div className="flex items-center justify-between pb-2 border-b border-border">
          <label className="flex items-center gap-2 text-xs font-semibold text-foreground cursor-pointer select-none">
            <input
              type="checkbox"
              checked={instructors.length > 0 && selectedUserIds.length === instructors.length}
              onChange={toggleAll}
            />
            Select all ({instructors.length})
          </label>
        </div>

        {isLoading ? (
          <Spinner />
        ) : (
          <div className="flex flex-col gap-1.5 max-h-60 overflow-y-auto pr-1">
            {instructors.map((u) => (
              <label key={u.id} className="flex items-center gap-2.5 p-2 bg-card border border-border rounded-xl cursor-pointer hover:bg-muted/40 transition-colors">
                <input
                  type="checkbox"
                  checked={selectedUserIds.includes(u.id)}
                  onChange={() => toggleOne(u.id)}
                />
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-foreground truncate">{u.full_name || u.email}</p>
                  <p className="text-[11px] text-muted-foreground truncate">{u.email}</p>
                </div>
              </label>
            ))}
          </div>
        )}

        {error && <p className="text-xs text-red-500">{error}</p>}

        <div className="flex flex-col gap-2 pt-2 border-t border-border">
          <button
            onClick={() => mutation.mutate({ userIds: selectedUserIds, roleIds: roleIdsForSubmit })}
            disabled={selectedUserIds.length === 0 || selectedRoleIds.length === 0 || mutation.isPending}
            className="w-full h-10 bg-primary text-primary-foreground font-semibold rounded-xl text-xs hover:opacity-90 transition-colors disabled:opacity-50"
          >
            {mutation.isPending ? "Opening…" : `Open call for these ${selectedUserIds.length} only`}
          </button>
          <button
            onClick={() => mutation.mutate({ userIds: undefined, roleIds: roleIdsForSubmit })}
            disabled={selectedRoleIds.length === 0 || mutation.isPending}
            className="w-full h-9 border border-border text-muted-foreground font-medium rounded-xl text-xs hover:bg-muted hover:text-foreground transition-colors disabled:opacity-50"
          >
            Open to all instructors ({instructors.length})
          </button>
        </div>
      </div>
    </Modal>
  )
}

function SessionHistoryPanel({ sessionId }: { sessionId: string }) {
  const { data: history, isLoading, error } = useQuery({
    queryKey: ["session-history", sessionId],
    queryFn: () => getSessionHistoryApi(sessionId),
  })

  if (isLoading) return <Spinner />
  if (error || !history) {
    return <p className="text-xs text-muted-foreground p-4">Could not load session history.</p>
  }

  const { pre_session, during_session, post_session, notes } = history

  return (
    <div className="space-y-6">
      {notes && (
        <Card className="p-5 border-amber-500/30 bg-amber-500/5 space-y-2">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
            <h3 className="text-sm font-semibold text-foreground">Instructor Session Comments</h3>
          </div>
          <p className="text-xs text-foreground bg-background/80 p-3 rounded-xl border border-border whitespace-pre-wrap">
            {notes}
          </p>
        </Card>
      )}

      {/* Pre-Session Phase */}
      <Card className="p-5 space-y-4">
        <div className="flex items-center gap-2 border-b border-border pb-3">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
          <h3 className="text-sm font-semibold text-foreground">Pre-Session (Equipment Pickups &amp; Counts)</h3>
        </div>

        <div className="space-y-3">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Equipment &amp; Kits Taken</p>
          {pre_session.movements.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">No equipment taken from warehouse recorded.</p>
          ) : (
            <div className="space-y-2">
              {pre_session.movements.map((m) => (
                <div key={m.id} className="p-3 bg-muted/20 border border-border rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                  <div>
                    <span className="font-semibold text-foreground">{m.subject}</span>
                    <span className="text-muted-foreground"> from {m.from_warehouse_name || m.from_location_name || "Warehouse"}</span>
                    {m.note && <p className="text-muted-foreground italic mt-0.5">&quot;{m.note}&quot;</p>}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium text-[11px]">
                      {m.actor_name} ({m.actor_role})
                    </span>
                    {m.created_at && (
                      <span className="text-muted-foreground text-[11px] font-mono">
                        {new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-3 pt-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Kit Pre-Checks &amp; Counts</p>
          {pre_session.kit_checks.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">No pre-session counts recorded.</p>
          ) : (
            <div className="space-y-2">
              {pre_session.kit_checks.map((kc) => (
                <div key={kc.id} className="p-3 bg-muted/20 border border-border rounded-xl space-y-1.5 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-foreground">{kc.kit_label} Pre-Check</span>
                    <span className="px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground text-[11px]">
                      {kc.actor_name} ({kc.actor_role})
                    </span>
                  </div>
                  {kc.skipped ? (
                    <p className="text-amber-600 dark:text-amber-400 font-medium">Skipped count check before session.</p>
                  ) : (
                    <div>
                      <p className="text-muted-foreground">Counted lines: {Object.keys(kc.counts || {}).length} items</p>
                      {Object.keys(kc.missing || {}).length > 0 && (
                        <p className="text-amber-600 dark:text-amber-400 font-semibold mt-1">
                          Shortages found: {Object.entries(kc.missing).map(([_, qty]) => `${qty} missing`).join(", ")}
                        </p>
                      )}
                    </div>
                  )}
                  {kc.note && <p className="text-muted-foreground italic">&quot;{kc.note}&quot;</p>}
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>

      {/* During-Session Phase */}
      <Card className="p-5 space-y-4">
        <div className="flex items-center gap-2 border-b border-border pb-3">
          <span className="w-2.5 h-2.5 rounded-full bg-blue-500" />
          <h3 className="text-sm font-semibold text-foreground">During Session (Attendance)</h3>
        </div>

        <div className="grid grid-cols-2 gap-3 max-w-xs">
          <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-center">
            <p className="text-xl font-bold text-emerald-700 dark:text-emerald-400">{during_session.attendance.present}</p>
            <p className="text-xs text-muted-foreground font-medium">Present</p>
          </div>
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-center">
            <p className="text-xl font-bold text-red-700 dark:text-red-400">{during_session.attendance.absent}</p>
            <p className="text-xs text-muted-foreground font-medium">Absent</p>
          </div>
        </div>
      </Card>

      {/* Post-Session Phase */}
      <Card className="p-5 space-y-4">
        <div className="flex items-center gap-2 border-b border-border pb-3">
          <span className="w-2.5 h-2.5 rounded-full bg-purple-500" />
          <h3 className="text-sm font-semibold text-foreground">Post-Session (Returns &amp; Reports)</h3>
        </div>

        <div className="space-y-3">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Equipment &amp; Kits Returned</p>
          {post_session.movements.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">No return movements recorded yet.</p>
          ) : (
            <div className="space-y-2">
              {post_session.movements.map((m) => (
                <div key={m.id} className="p-3 bg-muted/20 border border-border rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                  <div>
                    <span className="font-semibold text-foreground">{m.subject}</span>
                    <span className="text-muted-foreground"> returned to {m.to_warehouse_name || m.to_location_name || "Warehouse"}</span>
                    {m.note && <p className="text-muted-foreground italic mt-0.5">&quot;{m.note}&quot;</p>}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="px-2 py-0.5 rounded-full bg-purple-500/15 text-purple-600 dark:text-purple-400 font-medium text-[11px]">
                      {m.actor_name} ({m.actor_role})
                    </span>
                    {m.created_at && (
                      <span className="text-muted-foreground text-[11px] font-mono">
                        {new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-3 pt-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Uploaded Reports &amp; Photos</p>
          {post_session.reports.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">No session reports uploaded.</p>
          ) : (
            <div className="space-y-2">
              {post_session.reports.map((r) => (
                <div key={r.id} className="p-3 bg-muted/20 border border-border rounded-xl flex items-center justify-between gap-2 text-xs">
                  <div>
                    <span className="font-semibold text-foreground">{r.actor_name} ({r.actor_role})</span>
                    {r.notes && <p className="text-muted-foreground italic mt-0.5">&quot;{r.notes}&quot;</p>}
                  </div>
                  <a
                    href={r.file_url}
                    target="_blank"
                    rel="noreferrer"
                    className="px-3 py-1.5 bg-primary text-primary-foreground font-medium rounded-lg text-xs hover:opacity-90 transition-opacity shrink-0"
                  >
                    Download report
                  </a>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}
