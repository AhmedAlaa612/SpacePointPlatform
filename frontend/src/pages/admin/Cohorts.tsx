import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus, Pencil, X, CalendarPlus, UserPlus, Upload, Ticket, Wallet, Ban, FileText, Download, CheckCircle2, Award, Trash2 } from "lucide-react"
import type {
  Cohort, CohortStatus, CohortVisibility, Program, Session,
  Registration, RegistrationStatus, PaymentStatus, StaffingStatus, EligibleInstructor,
  AttendanceStatus, SessionDelivery,
} from "@/types/sessions"
import type { User } from "@/types/shared"
import { getProgramsApi } from "@/api/sessions/programs"
import { getUsersApi } from "@/api/admin/users"
import {
  getCohortsApi, createCohortApi, updateCohortApi,
  generateSessionsApi, getSessionsApi, addSessionApi, updateSessionApi,
  assignInstructorApi, unassignInstructorApi,
  getRegistrationsApi, deskRegisterApi, resendTicketApi, cancelRegistrationApi, confirmPaymentApi, giveCertificateApi,
  deleteCohortApi, deleteSessionApi, deleteRegistrationApi,
} from "@/api/sessions/cohorts"
import {
  openCallApi, openCallForCohortApi, reopenStaffingApi, listEligibleInstructorsApi, selectInstructorsApi, closeCallApi,
} from "@/api/sessions/staffing"
import { listCohortReportsApi, uploadSessionReportApi, completeCohortApi, getSessionDeliveryApi, markAttendanceApi } from "@/api/sessions/delivery"
import type { SessionReport } from "@/types/sessions"
import { Modal, Field, ModalActions, Spinner } from "@/pages/admin/components/common"
import { ImportListModal } from "@/pages/admin/components/ImportList"
import { listOrganizationsApi, updateContactApi } from "@/api/spine/contacts"
import { UserProfileModal } from "@/components/UserProfileModal"

const STATUS_OPTIONS: CohortStatus[] = ["planned", "registration_open", "running", "completed", "cancelled"]
const VISIBILITY_OPTIONS: CohortVisibility[] = ["public", "private"]
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

const COHORT_STATUS_LABEL: Record<CohortStatus, string> = {
  planned: "Planned",
  registration_open: "Registration open",
  running: "Running",
  completed: "Completed",
  cancelled: "Cancelled",
}

const COHORT_STATUS_COLOR: Record<CohortStatus, string> = {
  planned: "bg-muted text-muted-foreground",
  registration_open: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  running: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400",
  completed: "bg-foreground text-background",
  cancelled: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400",
}

const REG_STATUS_COLOR: Record<RegistrationStatus, string> = {
  registered: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400",
  attended: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  completed: "bg-foreground text-background",
  cancelled: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400",
  no_show: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
}

const PAYMENT_STATUS_COLOR: Record<PaymentStatus, string> = {
  unpaid: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
  partial: "bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-400",
  paid: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  waived: "bg-muted text-muted-foreground",
  refunded: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400",
}

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
/* Cohorts page                                                        */
/* ================================================================== */
export default function Cohorts() {
  const queryClient = useQueryClient()
  const [programFilter, setProgramFilter] = useState("")
  const [createOpen, setCreateOpen] = useState(false)
  const [editCohort, setEditCohort] = useState<Cohort | null>(null)
  const [detailCohort, setDetailCohort] = useState<Cohort | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  // Refused server-side if anyone has registered — cancelling the cohort is
  // the right move there, and the API says so.
  const deleteCohortMutation = useMutation({
    mutationFn: deleteCohortApi,
    onSuccess: () => {
      setDeleteError(null)
      queryClient.invalidateQueries({ queryKey: ["sessions-cohorts"] })
    },
    onError: (e: any) => setDeleteError(e?.response?.data?.detail ?? "Failed to delete cohort"),
  })

  const { data: programs = [] } = useQuery<Program[]>({ queryKey: ["sessions-programs"], queryFn: getProgramsApi })
  const { data: cohorts = [], isLoading } = useQuery<Cohort[]>({
    queryKey: ["sessions-cohorts", programFilter],
    queryFn: () => getCohortsApi(programFilter || undefined),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground tracking-tight">Cohorts</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Real runs of a program — dates, capacity, and the registration desk</p>
        </div>
        <button
          onClick={() => setCreateOpen(true)}
          className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
        >
          <Plus size={14} /> New cohort
        </button>
      </div>

      {deleteError && (
        <div className="text-xs text-red-600 dark:text-red-400 bg-red-500/10 border border-red-500/30 rounded-xl px-3 py-2">
          {deleteError}
        </div>
      )}

      <select
        value={programFilter} onChange={(e) => setProgramFilter(e.target.value)}
        className="h-9 px-3 w-full sm:w-64 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
      >
        <option value="">All programs</option>
        {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>

      <div className="flex flex-col gap-2">
        {cohorts.map((c) => (
          <div
            key={c.id}
            className="flex items-center justify-between p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors"
          >
            <button onClick={() => setDetailCohort(c)} className="min-w-0 text-left flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-medium text-foreground truncate">{c.name}</p>
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${COHORT_STATUS_COLOR[c.status]}`}>
                  {COHORT_STATUS_LABEL[c.status]}
                </span>
              </div>
              <p className="text-xs text-muted-foreground truncate">
                {c.program_name ?? "—"}
                {c.starts_on ? ` · ${c.starts_on}${c.ends_on && c.ends_on !== c.starts_on ? ` – ${c.ends_on}` : ""}` : ""}
                {c.location ? ` · ${c.location}` : ""}
                {c.capacity != null ? ` · cap ${c.capacity}` : ""}
              </p>
            </button>
            <div className="flex items-center gap-1 flex-shrink-0 ml-3">
              <button
                onClick={() => setEditCohort(c)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                title="Edit cohort"
              >
                <Pencil size={14} />
              </button>
              <button
                onClick={() => {
                  if (confirm(`Delete the cohort "${c.name}"? This only works if nobody has registered.`)) {
                    deleteCohortMutation.mutate(c.id)
                  }
                }}
                disabled={deleteCohortMutation.isPending}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                title="Delete cohort"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}
        {cohorts.length === 0 && (
          <div className="flex items-center justify-center h-32 border border-dashed border-border rounded-2xl">
            <p className="text-sm text-muted-foreground">No cohorts yet</p>
          </div>
        )}
      </div>

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
      {detailCohort && (
        <CohortDetailDrawer
          // Re-derive from the live query by id rather than the stale object
          // captured at click-time — otherwise completing a cohort updates
          // the list behind the drawer but the drawer's own header/actions
          // (status label, Complete-cohort button) stay frozen until reopened.
          cohort={cohorts.find((c) => c.id === detailCohort.id) ?? detailCohort}
          onClose={() => setDetailCohort(null)}
        />
      )}
    </div>
  )
}

/* ================================================================== */
/* Create/edit cohort modal                                            */
/* ================================================================== */
function CohortModal({ programs, cohort, onClose, onSuccess }: {
  programs: Program[]; cohort?: Cohort; onClose: () => void; onSuccess: () => void
}) {
  const isEdit = !!cohort
  const [programId, setProgramId] = useState(cohort?.program_id ?? "")
  const [name, setName] = useState(cohort?.name ?? "")
  const [startsOn, setStartsOn] = useState(cohort?.starts_on ?? "")
  const [endsOn, setEndsOn] = useState(cohort?.ends_on ?? "")
  const [location, setLocation] = useState(cohort?.location ?? "")
  const [capacity, setCapacity] = useState(cohort?.capacity != null ? String(cohort.capacity) : "")
  const [visibility, setVisibility] = useState<CohortVisibility>(cohort?.visibility ?? "public")
  const [status, setStatus] = useState<CohortStatus>(cohort?.status ?? "planned")
  const [notes, setNotes] = useState(cohort?.notes ?? "")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () => {
      if (isEdit) {
        return updateCohortApi(cohort!.id, {
          name: name.trim(),
          starts_on: startsOn || null,
          ends_on: endsOn || null,
          location: location.trim() || null,
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
        location: location.trim() || undefined,
        capacity: capacity.trim() ? Number(capacity) : undefined,
        visibility,
        notes: notes.trim() || undefined,
      })
    },
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to save cohort"),
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
          <input
            value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Dubai HQ"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
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

/* ================================================================== */
/* Cohort detail drawer — registrations + sessions + desk registration */
/* Wider than the shared Modal (which tops out at max-w-sm and doesn't  */
/* fit a registrations table), reusing the same visual language directly. */
/* ================================================================== */
function CohortDetailDrawer({ cohort, onClose }: { cohort: Cohort; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [generateOpen, setGenerateOpen] = useState(false)
  const [addSessionOpen, setAddSessionOpen] = useState(false)
  const [sessionDetail, setSessionDetail] = useState<Session | null>(null)
  const [drawerError, setDrawerError] = useState<string | null>(null)
  const [registerOpen, setRegisterOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [paymentTarget, setPaymentTarget] = useState<Registration | null>(null)
  const [editRegistrationTarget, setEditRegistrationTarget] = useState<Registration | null>(null)

  const { data: registrations = [], isLoading } = useQuery<Registration[]>({
    queryKey: ["sessions-registrations", cohort.id],
    queryFn: () => getRegistrationsApi(cohort.id),
  })
  const { data: sessions = [] } = useQuery<Session[]>({
    queryKey: ["sessions-sessions", cohort.id],
    queryFn: () => getSessionsApi(cohort.id),
  })
  const { data: cohortReports = [] } = useQuery<SessionReport[]>({
    queryKey: ["sessions-cohort-reports", cohort.id],
    queryFn: () => listCohortReportsApi(cohort.id),
  })

  const invalidateRegistrations = () => queryClient.invalidateQueries({ queryKey: ["sessions-registrations", cohort.id] })
  const invalidateSessions = () => queryClient.invalidateQueries({ queryKey: ["sessions-sessions", cohort.id] })
  const invalidateReports = () => queryClient.invalidateQueries({ queryKey: ["sessions-cohort-reports", cohort.id] })

  const resendMutation = useMutation({ mutationFn: resendTicketApi, onSuccess: invalidateRegistrations })
  const cancelMutation = useMutation({ mutationFn: cancelRegistrationApi, onSuccess: invalidateRegistrations })
  const giveCertificateMutation = useMutation({ mutationFn: giveCertificateApi, onSuccess: invalidateRegistrations })
  // Both refuse server-side once real history is attached (attendance, a
  // certificate) — show the API's reason instead of failing quietly.
  const deleteRegistrationMutation = useMutation({
    mutationFn: deleteRegistrationApi,
    onSuccess: () => { setDrawerError(null); invalidateRegistrations() },
    onError: (e: any) => setDrawerError(e?.response?.data?.detail ?? "Failed to delete registration"),
  })

  const openCallForCohortMutation = useMutation({
    mutationFn: () => openCallForCohortApi(cohort.id),
    onSuccess: invalidateSessions,
  })
  const uploadReportMutation = useMutation({
    mutationFn: (file: File) => uploadSessionReportApi(cohort.id, { file }),
    onSuccess: invalidateReports,
  })
  const [attendanceTarget, setAttendanceTarget] = useState<Registration | null>(null)
  const [completeWarnings, setCompleteWarnings] = useState<string[] | null>(null)
  const completeCohortMutation = useMutation({
    mutationFn: () => completeCohortApi(cohort.id),
    onSuccess: (result) => {
      setCompleteWarnings(result.warnings)
      queryClient.invalidateQueries({ queryKey: ["sessions-cohorts"] })
    },
  })
  const unstaffedCount = sessions.filter((s) => s.staffing_status === "unstaffed").length

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center p-4">
      <div className="w-full max-w-4xl bg-card border border-border rounded-2xl p-6 flex flex-col gap-5 shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-base font-semibold text-foreground">{cohort.name}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {cohort.program_name ?? "—"} ·{" "}
              <span className={`px-2 py-0.5 rounded-full font-semibold ${COHORT_STATUS_COLOR[cohort.status]}`}>
                {COHORT_STATUS_LABEL[cohort.status]}
              </span>
            </p>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-muted-foreground hover:text-foreground transition-colors">
            <X size={16} />
          </button>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setGenerateOpen(true)}
            className="flex items-center gap-1.5 h-9 px-3 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
          >
            <CalendarPlus size={14} /> Generate sessions
          </button>
          <button
            onClick={() => setRegisterOpen(true)}
            className="flex items-center gap-1.5 h-9 px-3 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors"
          >
            <UserPlus size={14} /> Register student
          </button>
          <button
            onClick={() => setImportOpen(true)}
            className="flex items-center gap-1.5 h-9 px-3 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
          >
            <Upload size={14} /> Import list
          </button>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Sessions{sessions.length > 0 ? ` (${sessions.length})` : ""}
            </p>
            <div className="flex items-center gap-3">
              {unstaffedCount > 0 && (
                <button
                  onClick={() => openCallForCohortMutation.mutate()}
                  disabled={openCallForCohortMutation.isPending}
                  className="text-xs font-medium text-primary hover:opacity-80 transition-colors disabled:opacity-50"
                >
                  Open call for all ({unstaffedCount})
                </button>
              )}
              <button
                onClick={() => setAddSessionOpen(true)}
                className="text-xs font-medium text-primary hover:opacity-80 transition-colors"
              >
                + Add session
              </button>
            </div>
          </div>
          {sessions.length === 0 ? (
            <div className="flex items-center justify-center h-16 border border-dashed border-border rounded-2xl">
              <p className="text-sm text-muted-foreground">No sessions scheduled yet</p>
            </div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {sessions.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setSessionDetail(s)}
                  className="text-xs font-medium px-2.5 py-1 rounded-full bg-background border border-border text-foreground hover:border-primary transition-colors inline-flex items-center gap-1.5"
                  title={s.title ?? undefined}
                >
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                    s.staffing_status === "staffed" ? "bg-emerald-500" : s.staffing_status === "open_call" ? "bg-blue-500" : "bg-muted-foreground/40"
                  }`} title={STAFFING_STATUS_LABEL[s.staffing_status]} />
                  {s.meeting_date}{s.starts_at ? ` · ${s.starts_at.slice(0, 5)}` : ""}
                  {s.title ? ` · ${s.title}` : ""}
                  {s.instructors.length > 0 ? ` · ${s.instructors.map((i) => i.full_name).join(", ")}` : ""}
                  {s.interested_count && s.interested_count > 0 ? (
                    <span className="ml-1 text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                      ★ {s.interested_count} interested
                    </span>
                  ) : null}
                </button>
              ))}
            </div>
          )}
        </div>

        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Registrations{registrations.length > 0 ? ` (${registrations.length})` : ""}
          </p>
          {drawerError && (
            <div className="text-xs text-red-600 dark:text-red-400 bg-red-500/10 border border-red-500/30 rounded-xl px-3 py-2 mb-2">
              {drawerError}
            </div>
          )}
          {isLoading ? <Spinner /> : registrations.length === 0 ? (
            <div className="flex items-center justify-center h-24 border border-dashed border-border rounded-2xl">
              <p className="text-sm text-muted-foreground">No registrations yet</p>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {registrations.map((r) => (
                <div
                  key={r.id}
                  className="flex flex-wrap items-center justify-between gap-3 p-3 bg-background border border-border rounded-xl"
                >
                  <div
                    className="min-w-0 flex-1 cursor-pointer group"
                    onClick={() => setEditRegistrationTarget(r)}
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-medium text-foreground group-hover:text-primary transition-colors truncate">{r.student_name}</p>
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${REG_STATUS_COLOR[r.status]}`}>
                        {r.status}
                      </span>
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${PAYMENT_STATUS_COLOR[r.payment_status]}`}>
                        {r.payment_status}
                      </span>
                      {r.checked_in && (
                        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400">
                          Checked in
                        </span>
                      )}
                      <span
                        className={`text-[11px] font-semibold px-2 py-0.5 rounded-full inline-flex items-center gap-1 shrink-0 ${
                          r.ticket_sent
                            ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400"
                            : "bg-muted text-muted-foreground"
                        }`}
                        title={r.ticket_sent ? "The QR ticket email was sent" : "No ticket email has been sent yet"}
                      >
                        <Ticket size={11} /> {r.ticket_sent ? "Ticket sent" : "No ticket"}
                      </span>
                      {/* certificate_issued, not certificate_url — student certs
                          are emailed and never stored, so they have no URL. */}
                      <span
                        className={`text-[11px] font-semibold px-2 py-0.5 rounded-full inline-flex items-center gap-1 shrink-0 ${
                          r.certificate_issued
                            ? "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400"
                            : "bg-muted text-muted-foreground"
                        }`}
                        title={r.certificate_issued ? "A completion certificate has been issued" : "No certificate issued yet"}
                      >
                        <Award size={11} /> {r.certificate_issued ? "Certificate" : "No certificate"}
                      </span>
                      {r.total_cohort_sessions_count && r.total_cohort_sessions_count > 0 ? (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            setAttendanceTarget(r)
                          }}
                          className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors inline-flex items-center gap-1 shrink-0"
                          title="Click to view detailed session attendance breakdown"
                        >
                          <span>Attendance: {r.attended_sessions_count ?? 0} / {r.total_cohort_sessions_count}</span>
                          <span>({Math.round(((r.attended_sessions_count ?? 0) / r.total_cohort_sessions_count) * 100)}%)</span>
                        </button>
                      ) : null}
                    </div>
                    <p className="text-xs text-muted-foreground truncate">
                      {r.student_phone ?? "—"}
                      {r.student_email ? ` · ${r.student_email}` : ""}
                      {r.student_date_of_birth ? ` · DOB: ${r.student_date_of_birth}` : ""}
                      {r.student_grade ? ` · ${r.student_grade}` : ""}
                      {r.student_organization_name ? ` · ${r.student_organization_name}` : ""}
                      {r.guardian_name ? ` · Guardian: ${r.guardian_name} (${r.guardian_phone ?? "—"})` : ""}
                      {r.price_charged != null ? ` · AED ${r.price_charged}` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <button
                      onClick={() => setEditRegistrationTarget(r)}
                      className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                      title="Edit student info"
                    >
                      <Pencil size={14} />
                    </button>
                    {r.certificate_url ? (
                      <a
                        href={r.certificate_url} target="_blank" rel="noreferrer"
                        className="p-1.5 rounded-lg text-muted-foreground hover:text-amber-500 hover:bg-amber-500/10 transition-colors"
                        title="Download certificate"
                      >
                        <Award size={14} />
                      </a>
                    ) : !r.certificate_issued && r.status !== "cancelled" && (
                      <button
                        onClick={() => {
                          if (confirm(`Give ${r.student_name} a completion certificate? Use this if they didn't meet the program's attendance requirement but still earned one.`)) {
                            giveCertificateMutation.mutate(r.id)
                          }
                        }}
                        disabled={giveCertificateMutation.isPending}
                        className="p-1.5 rounded-lg text-muted-foreground/50 hover:text-amber-500 hover:bg-amber-500/10 transition-colors disabled:opacity-50"
                        title="Give certificate (manual override)"
                      >
                        <Award size={14} />
                      </button>
                    )}
                    <button
                      onClick={() => resendMutation.mutate(r.id)}
                      disabled={resendMutation.isPending}
                      className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors disabled:opacity-50"
                      title={r.ticket_sent ? "Resend ticket" : "Send ticket"}
                    >
                      <Ticket size={14} />
                    </button>
                    <button
                      onClick={() => setPaymentTarget(r)}
                      className="p-1.5 rounded-lg text-muted-foreground hover:text-emerald-500 hover:bg-emerald-500/10 transition-colors"
                      title="Confirm payment"
                    >
                      <Wallet size={14} />
                    </button>
                    <button
                      onClick={() => { if (confirm(`Cancel ${r.student_name}'s registration?`)) cancelMutation.mutate(r.id) }}
                      disabled={r.status === "cancelled" || cancelMutation.isPending}
                      className="p-1.5 rounded-lg text-muted-foreground hover:text-red-500 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                      title="Cancel registration"
                    >
                      <Ban size={14} />
                    </button>
                    <button
                      onClick={() => {
                        if (confirm(`Remove ${r.student_name} from this cohort entirely? Use Cancel instead if they really did sign up and then dropped out — this is for rows that shouldn't exist.`)) {
                          deleteRegistrationMutation.mutate(r.id)
                        }
                      }}
                      disabled={deleteRegistrationMutation.isPending}
                      className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                      title="Delete registration"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Reports{cohortReports.length > 0 ? ` (${cohortReports.length})` : ""}
            </p>
            <label className="text-xs font-medium text-primary hover:opacity-80 transition-colors cursor-pointer">
              {uploadReportMutation.isPending ? "Uploading…" : "+ Upload report"}
              <input
                type="file" className="hidden" disabled={uploadReportMutation.isPending}
                onChange={(e) => { const file = e.target.files?.[0]; if (file) uploadReportMutation.mutate(file); e.target.value = "" }}
              />
            </label>
          </div>
          {cohortReports.length === 0 ? (
            <div className="flex items-center justify-center h-12 border border-dashed border-border rounded-2xl">
              <p className="text-sm text-muted-foreground">No reports uploaded yet</p>
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {cohortReports.map((r) => (
                <a
                  key={r.id} href={r.file_url} target="_blank" rel="noreferrer"
                  className="flex items-center gap-2.5 px-3 py-2 bg-background border border-border rounded-xl hover:border-primary/50 transition-colors"
                >
                  <FileText size={14} className="text-muted-foreground shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-foreground truncate">{r.filename}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {r.uploaded_by_name ?? "Unknown"}{r.notes ? ` · ${r.notes}` : ""}
                    </p>
                  </div>
                  <Download size={13} className="text-muted-foreground shrink-0" />
                </a>
              ))}
            </div>
          )}
        </div>

        {completeWarnings && (
          <div className="flex items-start gap-2 p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-700 dark:bg-amber-500/10 dark:border-amber-900/50 dark:text-amber-400 text-sm">
            <CheckCircle2 size={16} className="shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Cohort marked completed.</p>
              {completeWarnings.map((w) => <p key={w} className="text-xs mt-0.5">{w}</p>)}
            </div>
          </div>
        )}

        <div className="flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 h-9 border border-border rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
          >
            Close
          </button>
          {cohort.status !== "completed" && cohort.status !== "cancelled" && (
            <button
              onClick={() => { if (confirm(`Mark "${cohort.name}" as completed?`)) completeCohortMutation.mutate() }}
              disabled={completeCohortMutation.isPending}
              className="flex-1 h-9 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
            >
              {completeCohortMutation.isPending ? "Completing…" : "Complete cohort"}
            </button>
          )}
        </div>
      </div>

      {generateOpen && (
        <GenerateSessionsModal
          cohort={cohort}
          onClose={() => setGenerateOpen(false)}
          onGenerated={invalidateSessions}
        />
      )}
      {addSessionOpen && (
        <AddSessionModal
          cohort={cohort}
          onClose={() => setAddSessionOpen(false)}
          onSuccess={() => { invalidateSessions(); setAddSessionOpen(false) }}
        />
      )}
      {sessionDetail && (
        <SessionDetailModal
          cohort={cohort}
          // Re-derive from the live query by id rather than using the stale
          // object captured at click-time — otherwise assigning/opening a
          // call updates the chip list behind the modal but the modal itself
          // (staffing status, instructor list) stays frozen until reopened.
          session={sessions.find((s) => s.id === sessionDetail.id) ?? sessionDetail}
          onClose={() => setSessionDetail(null)}
          onChanged={invalidateSessions}
        />
      )}
      {registerOpen && (
        <DeskRegisterModal
          cohort={cohort} sessions={sessions}
          onClose={() => setRegisterOpen(false)}
          onSuccess={() => { invalidateRegistrations(); setRegisterOpen(false) }}
        />
      )}
      {importOpen && (
        <ImportListModal cohort={cohort} onClose={() => setImportOpen(false)} onImported={invalidateRegistrations} />
      )}
      {paymentTarget && (
        <ConfirmPaymentModal
          registration={paymentTarget}
          onClose={() => setPaymentTarget(null)}
          onSuccess={() => { invalidateRegistrations(); setPaymentTarget(null) }}
        />
      )}
      {editRegistrationTarget && (
        <EditStudentModal
          registration={editRegistrationTarget}
          onClose={() => setEditRegistrationTarget(null)}
          onSuccess={() => { invalidateRegistrations(); setEditRegistrationTarget(null) }}
        />
      )}
      {attendanceTarget && (
        <StudentAttendanceModal
          registration={attendanceTarget}
          onClose={() => setAttendanceTarget(null)}
        />
      )}
    </div>
  )
}

/* ================================================================== */
/* Generate sessions modal                                             */
/* ================================================================== */
function GenerateSessionsModal({ cohort, onClose, onGenerated }: {
  cohort: Cohort; onClose: () => void; onGenerated: () => void
}) {
  const [weekdays, setWeekdays] = useState<number[]>([0])
  const [count, setCount] = useState("8")
  const [startsAt, setStartsAt] = useState("")
  const [error, setError] = useState("")
  const [result, setResult] = useState<{ created: number; skipped: number } | null>(null)

  const toggleWeekday = (i: number) =>
    setWeekdays((prev) => prev.includes(i) ? prev.filter((w) => w !== i) : [...prev, i].sort())

  const mutation = useMutation({
    mutationFn: () => generateSessionsApi(cohort.id, { weekdays, count: Number(count), starts_at: startsAt || null }),
    onSuccess: (r) => { setResult({ created: r.created.length, skipped: r.skipped }); onGenerated() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to generate sessions"),
  })

  return (
    <Modal title={`Generate sessions — ${cohort.name}`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        {cohort.starts_on ? (
          <p className="text-xs text-muted-foreground">
            Cohort starts {cohort.starts_on}. Pick every weekday this cohort meets on — e.g. Tuesday + Thursday
            for a twice-a-week course — and how many weeks to generate.
          </p>
        ) : (
          <p className="text-xs text-red-500">This cohort has no start date set — set one before generating sessions.</p>
        )}
        <Field label="Meets on">
          <div className="flex flex-wrap gap-1.5">
            {WEEKDAYS.map((w, i) => (
              <button
                key={w} type="button" onClick={() => toggleWeekday(i)}
                className={`h-9 px-3 rounded-xl text-sm font-medium border transition-colors ${
                  weekdays.includes(i)
                    ? "bg-primary text-primary-foreground border-primary"
                    : "border-border text-foreground hover:bg-muted"
                }`}
              >
                {w.slice(0, 3)}
              </button>
            ))}
          </div>
        </Field>
        <Field label="Number of weeks">
          <input
            value={count} onChange={(e) => setCount(e.target.value)} type="number" min={1}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Start time (optional)">
          <input
            value={startsAt} onChange={(e) => setStartsAt(e.target.value)} type="time"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        {result && (
          <p className="text-xs text-emerald-500">
            Created {result.created} session{result.created !== 1 ? "s" : ""}
            {result.skipped > 0 ? ` (${result.skipped} already existed, skipped)` : ""}.
          </p>
        )}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()}
          loading={mutation.isPending} disabled={!cohort.starts_on || !count.trim() || weekdays.length === 0}
          label="Generate"
        />
      </div>
    </Modal>
  )
}

/* ================================================================== */
/* Add a single one-off session date                                   */
/* ================================================================== */
function AddSessionModal({ cohort, onClose, onSuccess }: {
  cohort: Cohort; onClose: () => void; onSuccess: () => void
}) {
  const [meetingDate, setMeetingDate] = useState(cohort.starts_on ?? "")
  const [startsAt, setStartsAt] = useState("")
  const [title, setTitle] = useState("")
  const [price, setPrice] = useState("")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () => addSessionApi(cohort.id, {
      meeting_date: meetingDate, starts_at: startsAt || null, title: title.trim() || null,
      price: price.trim() ? Number(price) : null,
    }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to add session"),
  })

  return (
    <Modal title={`Add a session — ${cohort.name}`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">
          For a one-off session that doesn't fit the weekly pattern — an extra class, a make-up date, an
          irregular schedule.
        </p>
        <Field label="Date">
          <input
            value={meetingDate} onChange={(e) => setMeetingDate(e.target.value)} type="date" autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Start time (optional)">
          <input
            value={startsAt} onChange={(e) => setStartsAt(e.target.value)} type="time"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Title (optional)">
          <input
            value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Make-up session"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Price override (optional)">
          <input
            value={price} onChange={(e) => setPrice(e.target.value)} type="number" placeholder="Leave blank to use the program price"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()}
          loading={mutation.isPending} disabled={!meetingDate.trim()}
          label="Add session"
        />
      </div>
    </Modal>
  )
}

/* ================================================================== */
/* Session detail — edit title/price/material + assign instructor      */
/* ================================================================== */
function SessionDetailModal({ cohort, session, onClose, onChanged }: {
  cohort: Cohort; session: Session; onClose: () => void; onChanged: () => void
}) {
  const [title, setTitle] = useState(session.title ?? "")
  const [materialUrl, setMaterialUrl] = useState(session.material_url ?? "")
  const [price, setPrice] = useState(session.price != null ? String(session.price) : "")
  const [instructorId, setInstructorId] = useState("")
  const [assignRole, setAssignRole] = useState<"lead" | "co">("lead")
  const [error, setError] = useState("")

  const { data: users = [] } = useQuery<User[]>({ queryKey: ["admin-users"], queryFn: getUsersApi })
  const instructorUsers = users.filter((u) =>
    u.roles?.some((r) => ["instructor", "teacher", "facilitator"].includes(r))
    && !session.instructors.some((si) => si.user_id === u.id)
  )

  const saveMutation = useMutation({
    mutationFn: () => updateSessionApi(cohort.id, session.id, {
      title: title.trim() || null, material_url: materialUrl.trim() || null,
      price: price.trim() ? Number(price) : null,
    }),
    onSuccess: onChanged,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to save session"),
  })

  const assignMutation = useMutation({
    mutationFn: () => assignInstructorApi(cohort.id, session.id, { user_id: instructorId, role: assignRole }),
    onSuccess: () => { setInstructorId(""); onChanged() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to assign instructor"),
  })

  const unassignMutation = useMutation({
    mutationFn: (userId: string) => unassignInstructorApi(cohort.id, session.id, userId),
    onSuccess: onChanged,
  })

  // Refused server-side once attendance exists for this session.
  const deleteMutation = useMutation({
    mutationFn: () => deleteSessionApi(cohort.id, session.id),
    onSuccess: () => { onChanged(); onClose() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to delete session"),
  })

  return (
    <Modal title={`Session — ${session.meeting_date}`} onClose={onClose} maxWidth="max-w-2xl">
      <div className="flex flex-col gap-3">
        <Field label="Title (optional)">
          <input
            value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Intro to Orbits" autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Material link (optional)">
          <input
            value={materialUrl} onChange={(e) => setMaterialUrl(e.target.value)} placeholder="https://…"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Price override (optional)">
          <input
            value={price} onChange={(e) => setPrice(e.target.value)} type="number" placeholder="Leave blank to use the program price"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => saveMutation.mutate()}
          loading={saveMutation.isPending} disabled={false}
          label="Save"
        />

        <StaffingSection session={session} onChanged={onChanged} />

        <div className="border-t border-border pt-3">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Instructor(s)</p>
          {session.instructors.length === 0 ? (
            <p className="text-sm text-muted-foreground mb-2">No instructor assigned yet.</p>
          ) : (
            <div className="flex flex-col gap-1.5 mb-2">
              {session.instructors.map((si) => (
                <div key={si.user_id} className="flex items-center justify-between px-3 py-2 bg-background border border-border rounded-xl">
                  <span className="text-sm text-foreground">{si.full_name} <span className="text-xs text-muted-foreground">({si.role})</span></span>
                  <button
                    onClick={() => unassignMutation.mutate(si.user_id)}
                    className="text-xs font-medium text-red-500 hover:opacity-80 transition-colors"
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <select
              value={instructorId} onChange={(e) => setInstructorId(e.target.value)}
              className="flex-1 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer min-w-[180px]"
            >
              <option value="">— Select an instructor —</option>
              {instructorUsers.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
            </select>
            <select
              value={assignRole} onChange={(e) => setAssignRole(e.target.value as "lead" | "co")}
              className="h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              <option value="lead">Lead</option>
              <option value="co">Co-instructor</option>
            </select>
            <button
              onClick={() => assignMutation.mutate()}
              disabled={!instructorId || assignMutation.isPending}
              className="h-10 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
            >
              Assign as {assignRole === "lead" ? "Lead" : "Co"}
            </button>
          </div>
        </div>

        <SessionAttendanceRosterSection sessionId={session.id} />

        <div className="border-t border-border pt-3 mt-1 flex justify-end">
          <button
            onClick={() => {
              if (confirm(`Delete the session on ${session.meeting_date}? This only works if no attendance has been recorded for it.`)) {
                deleteMutation.mutate()
              }
            }}
            disabled={deleteMutation.isPending}
            className="text-xs font-medium text-red-600 dark:text-red-400 hover:opacity-80 transition-colors disabled:opacity-50 inline-flex items-center gap-1.5"
          >
            <Trash2 size={13} /> Delete this session
          </button>
        </div>
      </div>
    </Modal>
  )
}

/* ================================================================== */
/* Staffing marketplace — open call + ops picker (V2 W4 S4-3)          */
/* Direct-assign above stays untouched; this is the open-call layer   */
/* on top of it. Operator requirement (2026-07-24): the picker shows  */
/* every eligible instructor/facilitator, not just those who          */
/* registered interest — multi-select, select-all, clickable profile. */
/* ================================================================== */
function StaffingSection({ session, onChanged }: {
  session: Session; onChanged: () => void
}) {
  const queryClient = useQueryClient()
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  // Assigning used to close the open call unconditionally, which blocked
  // further interest even when ops still wanted more people (2026-07-26).
  const [closeCall, setCloseCall] = useState(true)
  const [role, setRole] = useState<"lead" | "co">("lead")
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
  const [showAllInstructors, setShowAllInstructors] = useState(false)
  const [error, setError] = useState("")
  const [lastResult, setLastResult] = useState<{ assigned: number; withoutInterest: number } | null>(null)

  const [openCallModalTarget, setOpenCallModalTarget] = useState(false)

  const isOpenCall = session.staffing_status === "open_call"

  const eligible = useQuery<EligibleInstructor[]>({
    queryKey: ["staffing-eligible-instructors", session.id],
    queryFn: () => listEligibleInstructorsApi(session.id),
    enabled: isOpenCall,
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["staffing-eligible-instructors", session.id] })
    onChanged()
  }

  const openCallMutation = useMutation({
    mutationFn: (userIds?: string[]) => openCallApi(session.id, userIds),
    onSuccess: () => {
      setOpenCallModalTarget(false)
      invalidate()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to open call"),
  })

  const [closeCallOptionOpen, setCloseCallOptionOpen] = useState(false)

  const closeCallMutation = useMutation({
    mutationFn: (clearInterest: boolean) => closeCallApi(session.id, clearInterest),
    onSuccess: () => {
      setCloseCallOptionOpen(false)
      invalidate()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to close call"),
  })

  const reopenMutation = useMutation({
    mutationFn: () => reopenStaffingApi(session.id),
    onSuccess: invalidate,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to reopen"),
  })

  const selectMutation = useMutation({
    mutationFn: () => selectInstructorsApi(session.id, selectedIds, role, closeCall),
    onSuccess: (result) => {
      setLastResult({ assigned: result.assigned.length, withoutInterest: result.without_interest.length })
      setSelectedIds([])
      invalidate()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to assign selected instructors"),
  })

  const assignSingleMutation = useMutation({
    mutationFn: ({ userId, assignRole }: { userId: string; assignRole: "lead" | "co" }) =>
      selectInstructorsApi(session.id, [userId], assignRole),
    onSuccess: () => {
      invalidate()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to assign instructor"),
  })

  const roster = eligible.data ?? []
  const interestedList = roster.filter((u) => u.interested)

  const allSelected = roster.length > 0 && selectedIds.length === roster.length
  const toggleAll = () => setSelectedIds(allSelected ? [] : roster.map((r) => r.user_id))
  const toggleOne = (userId: string) =>
    setSelectedIds((prev) => prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId])

  return (
    <div className="border-t border-border pt-4 mt-2">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Staffing Marketplace</p>
          <p className="text-xs text-muted-foreground">Manage instructor interest and assignments for this session</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${STAFFING_STATUS_COLOR[session.staffing_status]}`}>
            {STAFFING_STATUS_LABEL[session.staffing_status]}
          </span>
          {isOpenCall && (
            <button
              onClick={() => { setError(""); setCloseCallOptionOpen(true) }}
              className="text-xs font-semibold text-red-500 hover:text-red-600 px-2 py-1 rounded-lg border border-red-500/20 hover:bg-red-500/10 transition-colors"
              title="Close or pause open call"
            >
              Close Call
            </button>
          )}
        </div>
      </div>

      {session.staffing_status === "unstaffed" && (
        <div className="flex flex-col sm:flex-row gap-2">
          <button
            onClick={() => { setError(""); openCallMutation.mutate(undefined) }}
            disabled={openCallMutation.isPending}
            className="flex-1 h-10 bg-primary/10 border border-primary/30 text-primary rounded-xl text-sm font-medium hover:bg-primary/20 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            Open Call (All Instructors)
          </button>
          <button
            onClick={() => { setError(""); setOpenCallModalTarget(true) }}
            className="h-10 px-4 border border-border text-foreground rounded-xl text-sm font-medium hover:bg-muted transition-colors flex items-center justify-center gap-1.5"
          >
            Target Specific Instructors…
          </button>
        </div>
      )}

      {session.staffing_status === "staffed" && (
        <button
          onClick={() => { setError(""); reopenMutation.mutate() }}
          disabled={reopenMutation.isPending}
          className="w-full h-9 border border-border rounded-xl text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:opacity-50"
        >
          Reopen Call for More Interest
        </button>
      )}

      {isOpenCall && (
        <div className="space-y-4">
          {eligible.isLoading ? (
            <Spinner />
          ) : (
            <>
              {/* Interested Instructors Section */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold text-foreground uppercase tracking-wider flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                    Interested Instructors ({interestedList.length})
                  </p>
                </div>

                {interestedList.length === 0 ? (
                  <div className="p-4 border border-dashed border-border rounded-xl bg-muted/30 text-center">
                    <p className="text-xs text-muted-foreground font-medium">No instructors have registered interest for this session yet.</p>
                    <p className="text-[11px] text-muted-foreground/70 mt-0.5">Instructors receive notifications when calls are opened and can submit interest from their portal.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {interestedList.map((u) => (
                      <div key={u.user_id} className="p-3 bg-card border border-border rounded-xl flex flex-wrap items-center justify-between gap-3 shadow-sm">
                        <div className="min-w-0 flex-1 flex items-center gap-3">
                          <button onClick={() => setProfileUserId(u.user_id)} className="shrink-0 font-bold text-xs w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center">
                            {u.full_name ? u.full_name.charAt(0).toUpperCase() : u.email.charAt(0).toUpperCase()}
                          </button>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <button onClick={() => setProfileUserId(u.user_id)} className="text-sm font-semibold text-foreground hover:text-primary transition-colors truncate text-left">
                                {u.full_name || u.email}
                              </button>
                              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 shrink-0">
                                Interested
                              </span>
                            </div>
                            <p className="text-xs text-muted-foreground truncate">{u.email}</p>
                            {u.note && (
                              <p className="text-xs text-foreground/90 italic bg-muted/50 px-2.5 py-1 rounded-lg mt-1 border border-border/50">
                                "{u.note}"
                              </p>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5 shrink-0">
                          <button
                            onClick={() => assignSingleMutation.mutate({ userId: u.user_id, assignRole: "lead" })}
                            disabled={assignSingleMutation.isPending}
                            className="h-8 px-3 bg-primary text-primary-foreground text-xs font-semibold rounded-lg hover:opacity-90 transition-colors disabled:opacity-50"
                          >
                            Assign Lead
                          </button>
                          <button
                            onClick={() => assignSingleMutation.mutate({ userId: u.user_id, assignRole: "co" })}
                            disabled={assignSingleMutation.isPending}
                            className="h-8 px-3 border border-border text-foreground text-xs font-medium rounded-lg hover:bg-muted transition-colors disabled:opacity-50"
                          >
                            Assign Co-instructor
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Full Platform Roster (Collapsible) */}
              <div className="pt-2 border-t border-border/60">
                <button
                  onClick={() => setShowAllInstructors(!showAllInstructors)}
                  className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors flex items-center justify-between w-full py-1"
                >
                  <span>Or pick from all platform instructors ({roster.length})</span>
                  <span className="text-primary text-[11px] font-semibold">{showAllInstructors ? "Hide list ▲" : "Show list ▼"}</span>
                </button>

                {showAllInstructors && (
                  <div className="mt-2 space-y-2 bg-muted/20 p-3 rounded-xl border border-border">
                    <div className="flex items-center justify-between gap-2 pb-2 border-b border-border">
                      <label className="flex items-center gap-2 text-xs font-medium text-foreground cursor-pointer select-none">
                        <input type="checkbox" checked={allSelected} onChange={toggleAll}
                          className="rounded text-primary focus:ring-primary border-border bg-background" />
                        Select all ({roster.length})
                      </label>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground">Role:</span>
                        <select
                          value={role} onChange={(e) => setRole(e.target.value as "lead" | "co")}
                          className="h-8 px-2 border border-border bg-card text-foreground rounded-lg text-xs focus:outline-none focus:border-primary transition-colors cursor-pointer"
                        >
                          <option value="lead">Lead</option>
                          <option value="co">Co-instructor</option>
                        </select>
                      </div>
                    </div>

                    <div className="flex flex-col gap-1.5 max-h-56 overflow-y-auto pr-1">
                      {roster.map((u) => (
                        <div key={u.user_id} className="flex items-center gap-2.5 px-3 py-2 bg-card border border-border rounded-xl">
                          <input type="checkbox" checked={selectedIds.includes(u.user_id)} onChange={() => toggleOne(u.user_id)}
                            className="rounded text-primary focus:ring-primary border-border bg-background shrink-0" />
                          <button
                            onClick={() => setProfileUserId(u.user_id)}
                            className="min-w-0 flex-1 text-left"
                            title="View profile"
                          >
                            <span className="text-xs font-medium text-foreground hover:text-primary transition-colors truncate block">
                              {u.full_name || u.email}
                            </span>
                            <span className="text-[11px] text-muted-foreground truncate block">{u.email}</span>
                          </button>
                          {u.interested && (
                            <span className="shrink-0 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400">
                              Interested
                            </span>
                          )}
                        </div>
                      ))}
                    </div>

                    <label className="flex items-start gap-2 mt-2 cursor-pointer select-none">
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

                    <button
                      onClick={() => { setError(""); setLastResult(null); selectMutation.mutate() }}
                      disabled={selectedIds.length === 0 || selectMutation.isPending}
                      className="w-full h-9 bg-primary text-primary-foreground rounded-xl text-xs font-medium hover:opacity-90 transition-colors disabled:opacity-50 mt-2"
                    >
                      {selectMutation.isPending ? "Assigning…" : `Assign Selected (${selectedIds.length})`}
                    </button>
                  </div>
                )}
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
          onClose={() => setOpenCallModalTarget(false)}
          onSuccess={() => {
            setOpenCallModalTarget(false)
            invalidate()
          }}
        />
      )}
      {closeCallOptionOpen && (
        <Modal title="Close Open Call Options" onClose={() => setCloseCallOptionOpen(false)} maxWidth="max-w-md">
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
                <p className="text-xs font-bold text-foreground group-hover:text-primary transition-colors">Pause Call (Keep Registered Interests)</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Pauses open registration. Previously submitted interest notes remain saved if you reopen the call later.
                </p>
              </button>

              <button
                onClick={() => closeCallMutation.mutate(true)}
                disabled={closeCallMutation.isPending}
                className="w-full text-left p-3.5 border border-red-500/30 bg-red-500/5 rounded-xl hover:bg-red-500/10 transition-all cursor-pointer"
              >
                <p className="text-xs font-bold text-red-500">Abort Call & Delete Interests</p>
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
/* Desk (manual) registration modal                                    */
/* ================================================================== */
function DeskRegisterModal({ cohort, sessions, onClose, onSuccess }: {
  cohort: Cohort; sessions: Session[]; onClose: () => void; onSuccess: () => void
}) {
  const [studentName, setStudentName] = useState("")
  const [email, setEmail] = useState("")
  const [phone, setPhone] = useState("")
  const [city, setCity] = useState("")
  const [dateOfBirth, setDateOfBirth] = useState("")
  const [grade, setGrade] = useState("")
  const [organizationName, setOrganizationName] = useState("")
  const [parentName, setParentName] = useState("")
  const [parentPhone, setParentPhone] = useState("")
  const [parentEmail, setParentEmail] = useState("")
  const [sendTicketEmail, setSendTicketEmail] = useState(true)
  const [selectedSessionIds, setSelectedSessionIds] = useState<string[]>([])
  const [error, setError] = useState("")

  const toggleSession = (id: string) =>
    setSelectedSessionIds((prev) => prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id])

  const { data: organizations = [] } = useQuery({
    queryKey: ["spine-organizations", "picker"],
    queryFn: () => listOrganizationsApi(),
  })

  const mutation = useMutation({
    mutationFn: () => deskRegisterApi(cohort.id, {
      student_name: studentName.trim(),
      email: email.trim(),
      phone: phone.trim(),
      city: city.trim() || undefined,
      date_of_birth: dateOfBirth || undefined,
      grade: grade.trim() || undefined,
      organization_name: organizationName.trim() || undefined,
      parent_name: parentName.trim() || undefined,
      parent_phone: parentPhone.trim() || undefined,
      parent_email: parentEmail.trim() || undefined,
      session_ids: selectedSessionIds.length > 0 ? selectedSessionIds : undefined,
      send_ticket_email: sendTicketEmail,
    }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to register student"),
  })

  const canSubmit = !!(studentName.trim() && email.trim() && phone.trim())

  return (
    <Modal title={`Register student — ${cohort.name}`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="Student name">
          <input
            value={studentName} onChange={(e) => setStudentName(e.target.value)} placeholder="Jane Smith" autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Email">
            <input
              value={email} onChange={(e) => setEmail(e.target.value)} type="email" placeholder="jane@example.com"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          <Field label="Phone">
            <input
              value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="050 000 0000"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
        </div>
        <Field label="City (optional)">
          <input
            value={city} onChange={(e) => setCity(e.target.value)} placeholder="Dubai"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Date of birth (optional)">
            <input
              value={dateOfBirth} onChange={(e) => setDateOfBirth(e.target.value)} type="date"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          <Field label="Grade (optional)">
            <input
              value={grade} onChange={(e) => setGrade(e.target.value)} placeholder="Grade 8"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
        </div>
        <Field label="School / organization (optional)">
          <input
            value={organizationName} onChange={(e) => setOrganizationName(e.target.value)}
            placeholder="Type to match or create" list="org-picker-list"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
          <datalist id="org-picker-list">
            {organizations.map((o) => <option key={o.id} value={o.name_latin} />)}
          </datalist>
        </Field>

        {sessions.length > 1 && (
          <Field label="Which sessions? (optional — leave blank for all)">
            <div className="flex flex-wrap gap-1.5">
              {sessions.map((s) => (
                <button
                  key={s.id} type="button" onClick={() => toggleSession(s.id)}
                  className={`h-9 px-3 rounded-xl text-xs font-medium border transition-colors ${
                    selectedSessionIds.includes(s.id)
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border text-foreground hover:bg-muted"
                  }`}
                >
                  {s.meeting_date}{s.title ? ` · ${s.title}` : ""}
                </button>
              ))}
            </div>
          </Field>
        )}

        <p className="text-xs text-muted-foreground -mb-1">Parent/guardian details (optional)</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Parent/guardian name">
            <input
              value={parentName} onChange={(e) => setParentName(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          <Field label="Parent/guardian phone">
            <input
              value={parentPhone} onChange={(e) => setParentPhone(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
        </div>
        <Field label="Parent/guardian email (optional)">
          <input
            value={parentEmail} onChange={(e) => setParentEmail(e.target.value)} type="email"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>

        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
          <input type="checkbox" checked={sendTicketEmail} onChange={(e) => setSendTicketEmail(e.target.checked)} />
          Send ticket email
        </label>

        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()}
          loading={mutation.isPending} disabled={!canSubmit}
          label="Register"
        />
      </div>
    </Modal>
  )
}

/* ================================================================== */
/* Confirm payment modal                                               */
/* ================================================================== */
function ConfirmPaymentModal({ registration, onClose, onSuccess }: {
  registration: Registration; onClose: () => void; onSuccess: () => void
}) {
  const [amount, setAmount] = useState(registration.price_charged != null ? String(registration.price_charged) : "")
  const [status, setStatus] = useState<"paid" | "partial">("paid")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () => confirmPaymentApi(registration.id, { amount: Number(amount), status }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to confirm payment"),
  })

  return (
    <Modal title={`Confirm payment — ${registration.student_name}`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="Amount (AED)">
          <input
            value={amount} onChange={(e) => setAmount(e.target.value)} type="number" placeholder="250" autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Status">
          <select
            value={status} onChange={(e) => setStatus(e.target.value as "paid" | "partial")}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
          >
            <option value="paid">Paid in full</option>
            <option value="partial">Partial payment / deposit</option>
          </select>
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()}
          loading={mutation.isPending} disabled={!amount.trim() || Number(amount) <= 0}
          label="Confirm payment"
        />
      </div>
    </Modal>
  )
}

/* ================================================================== */
/* Edit student info modal                                            */
/* ================================================================== */
function EditStudentModal({
  registration,
  onClose,
  onSuccess,
}: {
  registration: Registration
  onClose: () => void
  onSuccess: () => void
}) {
  const [studentName, setStudentName] = useState(registration.student_name || "")
  const [email, setEmail] = useState(registration.student_email || "")
  const [phone, setPhone] = useState(registration.student_phone || "")
  const [dateOfBirth, setDateOfBirth] = useState(registration.student_date_of_birth || "")
  const [grade, setGrade] = useState(registration.student_grade || "")
  const [organizationName, setOrganizationName] = useState(registration.student_organization_name || "")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () =>
      updateContactApi(registration.contact_id, {
        full_name: studentName.trim(),
        email: email.trim() || null,
        primary_phone_e164: phone.trim() || null,
        date_of_birth: dateOfBirth || null,
        grade: grade.trim() || null,
      }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to update student info"),
  })

  return (
    <Modal title={`Edit Student — ${registration.student_name}`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="Full name">
          <input
            value={studentName}
            onChange={(e) => setStudentName(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Email">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="student@example.com"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          <Field label="Phone">
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+971..."
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Date of birth">
            <input
              type="date"
              value={dateOfBirth}
              onChange={(e) => setDateOfBirth(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          <Field label="Grade / Year">
            <input
              value={grade}
              onChange={(e) => setGrade(e.target.value)}
              placeholder="e.g. Grade 10"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
        </div>
        <Field label="School / Organization">
          <input
            value={organizationName}
            onChange={(e) => setOrganizationName(e.target.value)}
            placeholder="School name"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose}
          onConfirm={() => mutation.mutate()}
          loading={mutation.isPending}
          disabled={!studentName.trim()}
          label="Save student info"
        />
      </div>
    </Modal>
  )
}

/* ================================================================== */
/* Student attendance breakdown modal                                 */
/* ================================================================== */
function StudentAttendanceModal({
  registration,
  onClose,
}: {
  registration: Registration
  onClose: () => void
}) {
  const records = registration.attendance_records ?? []
  const total = registration.total_cohort_sessions_count ?? records.length
  const attended = registration.attended_sessions_count ?? records.filter((r) => r.att_status === "present").length
  const pct = total > 0 ? Math.round((attended / total) * 100) : 0

  const statusBadges: Record<string, { label: string; cls: string }> = {
    present: { label: "Present", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400" },
    absent: { label: "Absent", cls: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400" },
    unrecorded: { label: "Unrecorded", cls: "bg-muted text-muted-foreground" },
  }

  return (
    <Modal title={`Attendance Breakdown — ${registration.student_name}`} onClose={onClose} maxWidth="max-w-md">
      <div className="flex flex-col gap-4">
        <div className="p-3 bg-muted/30 border border-border rounded-xl flex items-center justify-between">
          <div>
            <p className="text-xs text-muted-foreground font-medium">Overall Attendance</p>
            <p className="text-lg font-bold text-foreground">{attended} / {total} sessions <span className="text-sm font-normal text-muted-foreground">({pct}%)</span></p>
          </div>
          <div className="w-20 bg-muted h-2 rounded-full overflow-hidden shrink-0">
            <div className="bg-primary h-full rounded-full" style={{ width: `${Math.min(100, pct)}%` }} />
          </div>
        </div>

        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Session Breakdown</p>
          {records.length === 0 ? (
            <p className="text-xs text-muted-foreground">No sessions scheduled for this cohort yet.</p>
          ) : (
            <div className="flex flex-col gap-2 max-h-64 overflow-y-auto pr-1">
              {records.map((r, i) => {
                const b = statusBadges[r.att_status] || statusBadges.unrecorded
                return (
                  <div key={r.session_id || i} className="flex items-center justify-between p-2.5 bg-card border border-border rounded-xl">
                    <div>
                      <p className="text-xs font-semibold text-foreground">{r.meeting_date} {r.session_title ? `· ${r.session_title}` : ""}</p>
                      {r.recorded_at && <p className="text-[10px] text-muted-foreground">Recorded at {new Date(r.recorded_at).toLocaleTimeString()}</p>}
                    </div>
                    <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full ${b.cls}`}>
                      {b.label}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}

/* ================================================================== */
/* Session attendance roster section inside SessionDetailModal        */
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
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Student Attendance Roster</p>
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
  onClose,
  onSuccess,
}: {
  sessionId: string
  onClose: () => void
  onSuccess: () => void
}) {
  const [selectedUserIds, setSelectedUserIds] = useState<string[]>([])
  const [error, setError] = useState("")

  const { data: users = [], isLoading } = useQuery<User[]>({ queryKey: ["admin-users"], queryFn: getUsersApi })
  const instructors = users.filter((u) =>
    u.roles?.some((r) => ["instructor", "teacher", "facilitator"].includes(r))
  )

  const mutation = useMutation({
    mutationFn: (userIds?: string[]) => openCallApi(sessionId, userIds),
    onSuccess,
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

  return (
    <Modal title="Open Call for Instructor Interest" onClose={onClose} maxWidth="max-w-md">
      <div className="flex flex-col gap-4">
        <p className="text-xs text-muted-foreground">
          Choose whether to notify all instructors across the platform or send an open call notification to specific instructors only.
        </p>

        <div className="flex items-center justify-between pb-2 border-b border-border">
          <label className="flex items-center gap-2 text-xs font-semibold text-foreground cursor-pointer select-none">
            <input
              type="checkbox"
              checked={instructors.length > 0 && selectedUserIds.length === instructors.length}
              onChange={toggleAll}
            />
            Select all platform instructors ({instructors.length})
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
            onClick={() => mutation.mutate(selectedUserIds)}
            disabled={selectedUserIds.length === 0 || mutation.isPending}
            className="w-full h-10 bg-primary text-primary-foreground font-semibold rounded-xl text-xs hover:opacity-90 transition-colors disabled:opacity-50"
          >
            {mutation.isPending ? "Notifying..." : `Launch Open Call for Selected (${selectedUserIds.length})`}
          </button>
          <button
            onClick={() => mutation.mutate(undefined)}
            disabled={mutation.isPending}
            className="w-full h-9 border border-border text-muted-foreground font-medium rounded-xl text-xs hover:bg-muted hover:text-foreground transition-colors disabled:opacity-50"
          >
            Notify ALL Instructors ({instructors.length})
          </button>
        </div>
      </div>
    </Modal>
  )
}
