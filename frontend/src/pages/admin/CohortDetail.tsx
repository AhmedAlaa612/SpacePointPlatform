import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "@tanstack/react-router"
import * as XLSX from "xlsx"
import {
  ArrowLeft, CalendarPlus, UserPlus, Upload, Ticket, Mail, Wallet, Ban, FileText, Download, FileSpreadsheet, Copy,
  CheckCircle2, Award, Trash2, Search, Pencil, MoreVertical, Camera, X,
} from "lucide-react"
import type {
  Cohort, CohortStatus, Program, Session,
  Registration,
  SessionReport,
  ProgramCertificateTemplate,
} from "@/types/sessions"
import { getProgramsApi } from "@/api/sessions/programs"
import { MaterialsPanel } from "@/pages/admin/components/MaterialsPanel"
import { CohortCallsPanel } from "@/pages/admin/components/CohortCallsPanel"
import CohortStaffingPanel from "@/pages/admin/components/CohortStaffingPanel"
import CohortDayReviewsPanel from "@/pages/admin/components/CohortDayReviewsPanel"
import { CohortKitsPanel } from "@/pages/admin/components/CohortKitsPanel"
import { CohortRolesPanel } from "@/pages/admin/components/CohortRolesPanel"
import { AssessmentAssignmentPanel } from "@/pages/admin/components/AssessmentAssignmentPanel"
import { LmsCohortSection } from "@/pages/lms-authoring/components/LmsCohortSection"
import { CohortConsentsPanel } from "@/pages/admin/components/CohortConsentsPanel"
import { MediaConsentModal } from "@/pages/admin/components/MediaConsentModal"
import { SessionsTable } from "@/pages/admin/components/SessionsTable"
import {
  getCohortApi, getSessionsApi,
  generateSessionsApi, addSessionApi,
  getRegistrationsApi, resendTicketApi, resendOnboardingEmailApi, getSetPasswordLinkApi, cancelRegistrationApi, confirmPaymentApi, giveCertificateApi,
  deleteRegistrationApi, downloadCohortCertificatesApi,
  updateCohortApi,
} from "@/api/sessions/cohorts"
import { listCohortReportsApi, uploadSessionReportApi, completeCohortApi } from "@/api/sessions/delivery"
import { listProgramCertificateTemplatesApi } from "@/api/sessions/programCertificateTemplates"
import { Modal, Field, ModalActions, ConfirmDialog, Spinner, PageHeader, EmptyState } from "@/pages/admin/components/common"
import { ImportListModal } from "@/pages/admin/components/ImportList"
import { BulkAssignInstructorModal } from "@/pages/admin/components/BulkAssignInstructorModal"
import { BulkOpenCallModal } from "@/pages/admin/components/BulkOpenCallModal"
import { DeskRegisterModal } from "@/pages/admin/components/DeskRegisterModal"
import { updateContactApi } from "@/api/spine/contacts"
import { CohortModal, COHORT_STATUS_LABEL, COHORT_STATUS_COLOR, statusOptionsFor } from "@/pages/admin/Cohorts"
import { ContactDetailModal } from "@/pages/admin/Contacts"
import { useToast } from "@/components/ui/toast"
import { Card } from "@/components/ui/card"
import { getErrorMessage } from "@/lib/utils"
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]



/** Sessions and Students are the daily work; Setup is the stuff you touch
 *  once when the cohort is created (2026-08-02). Setup used to sit *between*
 *  the two daily ones, which is what made the page feel endless. */
type CohortTab = "sessions" | "roles" | "staffing" | "assessment" | "lms" | "students" | "consents" | "setup"
const TABS: { key: CohortTab; label: string }[] = [
  { key: "sessions", label: "Sessions" },
  // Roles moved out of Staffing (2026-08-28): rate, responsibilities and the
  // checklist are all "what does this role mean here", one thing ops sets up
  // before opening a call — separate from running the call itself.
  { key: "roles", label: "Checklists & Roles" },
  // Staffing moved out of the Sessions tab (2026-08-24): opening a call,
  // reading the applicant table and seeing who ended up staffed are one job,
  // and they were buried under a table that had grown to own the whole tab.
  { key: "staffing", label: "Staffing" },
  // Instructor assessment (2026-09) — whether applying to this cohort's
  // open calls requires passing an assessment first, and which one. Its own
  // tab rather than folded into Roles/Staffing: it's a one-time on/off
  // decision about the cohort, not part of running a specific call.
  { key: "assessment", label: "Assessment" },
  // LMS checklist/missions/progress/review (2026-09) — the exact same
  // cohort-scope views `/lms-authoring` already shows, embedded here so
  // ops never has to leave the cohort page for LMS-checklist work.
  { key: "lms", label: "LMS" },
  { key: "students", label: "Students" },
  { key: "consents", label: "Consents" },
  { key: "setup", label: "Setup" },
]

function CounterChip({ label, value, onClick, tone = "default" }: {
  label: string; value: React.ReactNode; onClick: () => void; tone?: "default" | "alert"
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center justify-center gap-1.5 h-9 px-4 rounded-xl border text-sm transition-colors ${
        tone === "alert"
          ? "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400 hover:bg-red-500/20"
          : "border-border bg-card text-foreground hover:bg-muted"
      }`}
    >
      <span className="font-semibold tabular-nums leading-none flex items-center">{value}</span>
      <span className="text-xs text-muted-foreground leading-none flex items-center">{label}</span>
    </button>
  )
}

/* ================================================================== */
/* Cohort detail page — registrations + sessions + desk registration.  */
/* Was CohortDetailDrawer (an in-page modal inside Cohorts.tsx); now a */
/* real route (/operations/cohorts/$cohortId) so it can be linked to   */
/* and bookmarked, and so a session can link back to its cohort.       */
/* ================================================================== */
export default function CohortDetail() {
  const { cohortId } = useParams({ strict: false }) as { cohortId: string }

  const { data: cohort, isLoading } = useQuery<Cohort>({
    queryKey: ["sessions-cohort", cohortId],
    queryFn: () => getCohortApi(cohortId),
  })

  if (isLoading) return <Spinner />
  if (!cohort) {
    return (
      <div className="flex flex-col gap-4">
        <Link to="/operations/cohorts" className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft size={14} /> Cohorts
        </Link>
        <p className="text-sm text-muted-foreground">Cohort not found.</p>
      </div>
    )
  }

  return <CohortDetailView key={cohortId} cohort={cohort} />
}

function CohortDetailView({ cohort }: { cohort: Cohort }) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [editOpen, setEditOpen] = useState(false)
  const [generateOpen, setGenerateOpen] = useState(false)
  const [addSessionOpen, setAddSessionOpen] = useState(false)
  const [drawerError, setDrawerError] = useState<string | null>(null)
  const [regSearch, setRegSearch] = useState("")
  const [regLoginFilter, setRegLoginFilter] = useState<"all" | "never" | "has_logged_in">("all")
  const [regConsentFilter, setRegConsentFilter] = useState<"all" | "consented" | "declined" | "pending">("all")
  const [regGenderFilter, setRegGenderFilter] = useState<string>("all")
  const [consentTarget, setConsentTarget] = useState<Registration | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Registration | null>(null)
  const [cancelTarget, setCancelTarget] = useState<Registration | null>(null)
  const [certificateTarget, setCertificateTarget] = useState<Registration | null>(null)
  const [registerOpen, setRegisterOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [paymentTarget, setPaymentTarget] = useState<Registration | null>(null)
  const [editRegistrationTarget, setEditRegistrationTarget] = useState<Registration | null>(null)
  const [profileContactId, setProfileContactId] = useState<string | null>(null)
  const [bulkMode, setBulkMode] = useState(false)
  const [selectedSessionIds, setSelectedSessionIds] = useState<string[]>([])
  const [bulkAssignOpen, setBulkAssignOpen] = useState(false)
  const [bulkOpenCallOpen, setBulkOpenCallOpen] = useState(false)
  const [completeConfirmOpen, setCompleteConfirmOpen] = useState(false)
  const [sendCertificates, setSendCertificates] = useState(false)
  const [tab, setTab] = useState<CohortTab>("sessions")

  const { data: programs = [] } = useQuery<Program[]>({ queryKey: ["sessions-programs"], queryFn: getProgramsApi })
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

  const normalizeGenderKey = (raw?: string | null): string => {
    const s = (raw ?? "").trim().toLowerCase()
    if (!s) return "unspecified"
    if (s === "m" || s === "male" || s === "boy" || s === "ذكر") return "male"
    if (s === "f" || s === "female" || s === "girl" || s === "أنثى" || s === "انثى") return "female"
    return s
  }

  const customGenderOptions = Array.from(
    registrations.reduce((map, r) => {
      const raw = (r.student_gender ?? "").trim()
      if (!raw) return map
      const key = normalizeGenderKey(raw)
      if (key !== "male" && key !== "female" && key !== "unspecified" && !map.has(key)) {
        map.set(key, raw)
      }
      return map
    }, new Map<string, string>()).entries(),
  )

  // Ops open this on a phone at a venue door, where a cohort can easily run to
  // dozens of rows — searching beats scrolling. Matches every field shown on
  // the row so "the school" or "the parent's number" both work.
  const filteredRegistrations = registrations.filter((r) => {
    if (regLoginFilter === "never" && r.last_login_at) return false
    if (regLoginFilter === "has_logged_in" && !r.last_login_at) return false
    if (regConsentFilter !== "all") {
      const cStatus = r.media_consent_status ?? "pending"
      if (cStatus !== regConsentFilter) return false
    }
    if (regGenderFilter !== "all") {
      if (normalizeGenderKey(r.student_gender) !== regGenderFilter) return false
    }
    const q = regSearch.trim().toLowerCase()
    if (!q) return true
    return [
      r.student_name, r.student_phone, r.student_email, r.student_grade, r.student_gender,
      r.student_organization_name, r.guardian_name, r.guardian_phone,
      r.media_consent_parent_name, r.media_consent_parent_phone,
      r.status, r.payment_status,
    ].some((v) => (v ?? "").toString().toLowerCase().includes(q))
  })

  // Client-side, from whatever's currently on screen — respects the search
  // box and login-status filter above rather than always dumping every
  // registration, same as the mission behind those filters in the first
  // place (e.g. filter to "never logged in", export just that batch).
  const handleExportRegistrations = () => {
    const rows = filteredRegistrations.map((r) => ({
      "Student Name": r.student_name,
      "Gender": r.student_gender ?? "",
      "Phone": r.student_phone ?? "",
      "Email": r.student_email ?? "",
      "School": r.student_organization_name ?? "",
      "Media Consent": r.media_consent_status === "consented" ? "Granted (YES)" : r.media_consent_status === "declined" ? "Declined (NO)" : "Pending",
      "Consent Parent Name": r.media_consent_parent_name ?? r.guardian_name ?? "",
      "Consent Parent Phone": r.media_consent_parent_phone ?? r.guardian_phone ?? "",
      "Consent Parent Email": r.media_consent_parent_email ?? "",
      "Consent Signed Date": r.media_consent_signed_date ?? "",
      "Ticket Sent": r.ticket_sent ? "Yes" : "No",
      "Onboarding Sent": r.onboarding_sent ? "Yes" : "No",
      "Registered At": r.created_at ? new Date(r.created_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }) : "",
      "Last Login At": r.last_login_at ? new Date(r.last_login_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }) : "Never logged in",
    }))

    const ws = XLSX.utils.json_to_sheet(rows)
    ws["!cols"] = [
      { wch: 24 }, // Student Name
      { wch: 12 }, // Gender
      { wch: 16 }, // Phone
      { wch: 26 }, // Email
      { wch: 22 }, // School
      { wch: 16 }, // Media Consent
      { wch: 22 }, // Consent Parent Name
      { wch: 16 }, // Consent Parent Phone
      { wch: 24 }, // Consent Parent Email
      { wch: 14 }, // Consent Signed Date
      { wch: 12 }, // Ticket Sent
      { wch: 16 }, // Onboarding Sent
      { wch: 14 }, // Registered At
      { wch: 16 }, // Last Login At
    ]

    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, "Registrations")
    XLSX.writeFile(wb, `${cohort.name.replace(/[^a-z0-9]+/gi, "_")}_registrations.xlsx`)
  }

  const invalidateCohort = () => {
    queryClient.invalidateQueries({ queryKey: ["sessions-cohort", cohort.id] })
    queryClient.invalidateQueries({ queryKey: ["sessions-cohorts"] })
  }
  const invalidateRegistrations = () => queryClient.invalidateQueries({ queryKey: ["sessions-registrations", cohort.id] })
  const invalidateSessions = () => {
    queryClient.invalidateQueries({ queryKey: ["sessions-sessions", cohort.id] })
    // Kits move to the lead instructor automatically the moment both exist
    // (2026-08-01) — instructor assignment can trigger that from over here,
    // so the Kits panel's own query needs a nudge too, not just the session list.
    queryClient.invalidateQueries({ queryKey: ["session-kits"] })
  }
  const invalidateReports = () => queryClient.invalidateQueries({ queryKey: ["sessions-cohort-reports", cohort.id] })

  const resendMutation = useMutation({
    mutationFn: resendTicketApi,
    onSuccess: () => { toast.success("Ticket sent"); invalidateRegistrations() },
  })
  const resendOnboardingMutation = useMutation({
    mutationFn: resendOnboardingEmailApi,
    onSuccess: (res: { sent: boolean }) => {
      if (res.sent) { toast.success("Onboarding email sent"); invalidateRegistrations() }
      else toast.error("Send failed — check SMTP")
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to send onboarding email")),
  })
  const copySetPasswordLinkMutation = useMutation({
    mutationFn: getSetPasswordLinkApi,
    onSuccess: async ({ link }) => {
      try {
        await navigator.clipboard.writeText(link)
        toast.success("Set-password link copied")
      } catch {
        toast.error("Couldn't copy to clipboard")
      }
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to get set-password link")),
  })
  const cancelMutation = useMutation({
    mutationFn: cancelRegistrationApi,
    onSuccess: () => {
      toast.success("Registration cancelled")
      setDrawerError(null)
      setCancelTarget(null)
      invalidateRegistrations()
    },
    onError: (e: any) => setDrawerError(getErrorMessage(e, "Failed to cancel registration")),
  })
  const giveCertificateMutation = useMutation({
    mutationFn: giveCertificateApi,
    onSuccess: () => {
      toast.success("Certificate issued")
      setDrawerError(null)
      setCertificateTarget(null)
      invalidateRegistrations()
    },
    onError: (e: any) => setDrawerError(getErrorMessage(e, "Failed to issue certificate")),
  })
  const { data: programTemplates = [] } = useQuery<ProgramCertificateTemplate[]>({
    queryKey: ["program-certificate-templates", cohort.program_id],
    queryFn: () => listProgramCertificateTemplatesApi(cohort.program_id),
    enabled: !!cohort.program_id,
  })
  const downloadCertificatesMutation = useMutation({
    mutationFn: ({ theme, templateId }: { theme: "dark" | "light" | "custom"; templateId?: string }) =>
      downloadCohortCertificatesApi(cohort.id, cohort.name, theme, templateId),
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to download certificates")),
  })
  // Both refuse server-side once real history is attached (attendance, a
  // certificate) — show the API's reason instead of failing quietly.
  const deleteRegistrationMutation = useMutation({
    mutationFn: ({ id, deleteContact }: { id: string; deleteContact: boolean }) =>
      deleteRegistrationApi(id, deleteContact),
    onSuccess: (_data, variables) => {
      toast.success(variables.deleteContact ? "Registration and contact deleted" : "Registration deleted")
      setDrawerError(null)
      setDeleteTarget(null)
      invalidateRegistrations()
      // Deleting a contact changes the Contacts page too.
      queryClient.invalidateQueries({ queryKey: ["spine-contacts"] })
    },
    onError: (e: any) => setDrawerError(getErrorMessage(e, "Failed to delete registration")),
  })

  const uploadReportMutation = useMutation({
    mutationFn: (file: File) => uploadSessionReportApi(cohort.id, { file }),
    onSuccess: () => { toast.success("Report uploaded"); invalidateReports() },
  })
  const [attendanceTarget, setAttendanceTarget] = useState<Registration | null>(null)
  const [completeWarnings, setCompleteWarnings] = useState<string[] | null>(null)
  const completeCohortMutation = useMutation({
    mutationFn: (sendCerts: boolean) => completeCohortApi(cohort.id, sendCerts),
    onSuccess: (result) => {
      toast.success("Cohort marked completed")
      setCompleteWarnings(result.warnings)
      invalidateCohort()
    },
  })
  const statusMutation = useMutation({
    mutationFn: (status: CohortStatus) => updateCohortApi(cohort.id, { status }),
    onSuccess: () => { toast.success("Status updated"); invalidateCohort() },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Failed to update status")),
  })
  const unstaffedCount = sessions.filter((s) => s.staffing_status === "unstaffed").length
  // Completing the cohort completes these too (backend, 2026-08-31) — the
  // confirm dialog says so rather than letting it happen quietly.
  const unfinishedSessionCount = sessions.filter((s) => !s.completed_at).length

  return (
    <div className="flex flex-col gap-5">
      <Link to="/operations/cohorts" className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
        <ArrowLeft size={14} /> Cohorts
      </Link>

      <PageHeader
        title={cohort.name}
        subtitle={
          <>
            {cohort.program_name ?? "—"} ·{" "}
            <span className={`px-2 py-0.5 rounded-full font-semibold ${COHORT_STATUS_COLOR[cohort.status]}`}>
              {COHORT_STATUS_LABEL[cohort.status]}
            </span>
            {cohort.starts_on ? ` · ${cohort.starts_on}${cohort.ends_on && cohort.ends_on !== cohort.starts_on ? ` – ${cohort.ends_on}` : ""}` : ""}
            {cohort.location_name ? ` · ${cohort.location_name}` : cohort.location ? ` · ${cohort.location}` : ""}
            {cohort.effective_warehouse_name ? ` · ${cohort.effective_warehouse_name}` : ""}
          </>
        }
        action={
          <div className="flex items-center gap-2 flex-wrap">
            {cohort.program_is_competition && (
              <Link
                to="/operations/cohorts/$cohortId/judging"
                params={{ cohortId: cohort.id }}
                className="flex items-center gap-1.5 h-9 px-3 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors shrink-0"
              >
                <Award size={14} /> Judging
              </Link>
            )}
            <select
              value={cohort.status}
              onChange={(e) => statusMutation.mutate(e.target.value as CohortStatus)}
              disabled={statusMutation.isPending}
              title="Change cohort status"
              className="h-8 px-2.5 border border-border bg-background rounded-lg text-xs font-medium text-foreground hover:bg-muted transition-colors shrink-0 cursor-pointer disabled:opacity-50 disabled:cursor-wait focus:outline-none w-auto max-w-fit"
            >
              {statusOptionsFor(cohort.status).map((s) => <option key={s} value={s}>{COHORT_STATUS_LABEL[s]}</option>)}
            </select>
            {cohort.status !== "completed" && cohort.status !== "cancelled" && (
              <button
                onClick={() => { setSendCertificates(false); setCompleteConfirmOpen(true) }}
                disabled={completeCohortMutation.isPending}
                className="flex items-center gap-1.5 h-9 px-3 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors shrink-0 disabled:opacity-50"
              >
                <CheckCircle2 size={14} className="text-emerald-600 dark:text-emerald-400" />
                {completeCohortMutation.isPending ? "Completing…" : "Complete cohort"}
              </button>
            )}
            <button
              onClick={() => setEditOpen(true)}
              className="flex items-center gap-1.5 h-9 px-3 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors shrink-0"
            >
              <Pencil size={14} /> Edit
            </button>
          </div>
        }
      />

      {/* Three counters that are also navigation — the numbers ops came to
          check, each one a door into the tab that acts on it. */}
      <div className="flex flex-wrap gap-2">
        <CounterChip
          label="Registered"
          value={cohort.capacity != null ? `${registrations.length} / ${cohort.capacity}` : `${registrations.length}`}
          onClick={() => setTab("students")}
        />
        <CounterChip label="Sessions" value={sessions.length} onClick={() => setTab("sessions")} />
        <CounterChip
          label="Unstaffed"
          value={unstaffedCount}
          tone={unstaffedCount > 0 ? "alert" : "default"}
          onClick={() => setTab("sessions")}
        />
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
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              disabled={downloadCertificatesMutation.isPending}
              className="flex items-center gap-1.5 h-9 px-3 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
              title="One merged PDF, one certificate per registered student"
            >
              <Award size={14} /> {downloadCertificatesMutation.isPending ? "Preparing…" : "Download certificates"}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56 max-h-80 overflow-y-auto">
            <DropdownMenuItem onClick={() => downloadCertificatesMutation.mutate({ theme: "dark" })}>
              Dark background
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => downloadCertificatesMutation.mutate({ theme: "light" })}>
              Light background
            </DropdownMenuItem>
            {programTemplates.map((tmpl: ProgramCertificateTemplate) => (
              <DropdownMenuItem
                key={tmpl.id}
                onClick={() => downloadCertificatesMutation.mutate({ theme: "custom", templateId: tmpl.id })}
                className="truncate"
              >
                {tmpl.name}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Sessions / Students / Setup — the page used to be five screens of
          stacked panels with setup wedged between the two things ops touches
          daily. Nothing is removed, it just stops all being on screen at once. */}
      <div className="flex items-center gap-1 border-b border-border overflow-x-auto scrollbar-none no-scrollbar" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`h-9 px-3 -mb-px border-b-2 text-sm font-medium transition-colors shrink-0 whitespace-nowrap ${
              tab === t.key
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "sessions" && (
      <div>
        <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
          <p className="text-sm font-semibold text-foreground">
            Sessions{sessions.length > 0 ? ` (${sessions.length})` : ""}
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            {sessions.length > 0 && (
              <button
                onClick={() => { setBulkMode(!bulkMode); setSelectedSessionIds([]) }}
                className="h-7 px-2.5 border border-border rounded-lg text-xs font-medium text-foreground hover:bg-muted transition-colors"
              >
                {bulkMode ? "Cancel" : "Select…"}
              </button>
            )}
            <button
              onClick={() => setAddSessionOpen(true)}
              className="h-7 px-2.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:opacity-90 transition-colors"
            >
              + Add session
            </button>
          </div>
        </div>

        {bulkMode && (
          <div className="flex items-center justify-between gap-2 mb-2 p-2 bg-primary/5 border border-primary/20 rounded-xl flex-wrap">
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1.5 text-xs font-medium text-foreground cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={sessions.length > 0 && selectedSessionIds.length === sessions.length}
                  onChange={() => setSelectedSessionIds(
                    selectedSessionIds.length === sessions.length ? [] : sessions.map((s) => s.id),
                  )}
                />
                Select all
              </label>
              <span className="text-xs text-muted-foreground">{selectedSessionIds.length} selected</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setBulkAssignOpen(true)}
                disabled={selectedSessionIds.length === 0}
                className="h-7 px-2.5 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:opacity-90 disabled:opacity-40"
              >
                Assign instructor…
              </button>
              <button
                onClick={() => setBulkOpenCallOpen(true)}
                disabled={selectedSessionIds.length === 0}
                className="h-7 px-2.5 border border-border text-foreground text-xs font-medium rounded-lg hover:bg-muted disabled:opacity-40"
              >
                Open call…
              </button>
            </div>
          </div>
        )}

        <SessionsTable
          cohortId={cohort.id}
          sessions={sessions}
          bulkMode={bulkMode}
          selectedSessionIds={selectedSessionIds}
          onToggleSession={(id) =>
            setSelectedSessionIds((prev) => prev.includes(id) ? prev.filter((sid) => sid !== id) : [...prev, id])}
        />
      </div>
      )}

      {tab === "roles" && (
      <div className="space-y-5">
        <Card className="px-4">
          <CohortRolesPanel cohort={cohort} sessions={sessions} />
        </Card>
      </div>
      )}

      {tab === "assessment" && (
      <div className="space-y-5">
        <Card className="px-4">
          <AssessmentAssignmentPanel cohortId={cohort.id} />
        </Card>
      </div>
      )}

      {tab === "lms" && (
      <div className="space-y-5">
        <Card className="px-4">
          <LmsCohortSection cohortId={cohort.id} cohortName={cohort.name} />
        </Card>
      </div>
      )}

      {tab === "staffing" && (
      <div className="space-y-5">
        {/* One "Open a call" entry point, managed and closed as one entity.
            The old ungrouped "Open call for all" quick action is gone: it
            wrote to a model this panel couldn't see, so calls opened that way
            could never be closed as a group. */}
        <Card className="px-4">
          <CohortCallsPanel cohort={cohort} sessions={sessions} />
        </Card>
        {/* One row per applicant, not per session — see the panel's docstring. */}
        <Card className="px-4">
          <CohortStaffingPanel cohort={cohort} />
        </Card>
        <Card className="px-4">
          <CohortDayReviewsPanel cohort={cohort} />
        </Card>
      </div>
      )}

      {tab === "students" && (
      <div>
        <p className="text-sm font-semibold text-foreground mb-2">
          Registrations{registrations.length > 0 ? ` (${registrations.length}${cohort.capacity != null ? ` / ${cohort.capacity}` : ""})` : ""}
        </p>
        {registrations.length > 0 && (
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 mb-2">
            <div className="relative w-full sm:flex-1 min-w-0">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
              <input
                type="text"
                dir="auto"
                value={regSearch}
                onChange={(e) => setRegSearch(e.target.value)}
                placeholder="Search name, phone, email, school…"
                className="w-full h-9 pl-9 pr-8 bg-background border border-border rounded-xl text-xs placeholder:text-muted-foreground focus:outline-none focus:border-primary transition-colors"
              />
              {regSearch && (
                <button
                  type="button"
                  onClick={() => setRegSearch("")}
                  aria-label="Clear search"
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground p-0.5 rounded-full transition-colors"
                >
                  <X size={13} />
                </button>
              )}
            </div>
            <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap w-full sm:w-auto">
              <select
                value={regGenderFilter}
                onChange={(e) => setRegGenderFilter(e.target.value)}
                aria-label="Filter registrations by gender"
                className="flex-1 sm:flex-none sm:w-auto h-9 px-2.5 bg-background border border-border rounded-xl text-xs focus:outline-none focus:border-primary transition-colors cursor-pointer"
              >
                <option value="all">Any gender</option>
                <option value="male">Gender: Male</option>
                <option value="female">Gender: Female</option>
                {customGenderOptions.map(([key, label]) => (
                  <option key={key} value={key}>Gender: {label}</option>
                ))}
                <option value="unspecified">Gender: Not specified</option>
              </select>
              <select
                value={regLoginFilter}
                onChange={(e) => setRegLoginFilter(e.target.value as "all" | "never" | "has_logged_in")}
                className="flex-1 sm:flex-none sm:w-auto h-9 px-2.5 bg-background border border-border rounded-xl text-xs focus:outline-none focus:border-primary transition-colors cursor-pointer"
              >
                <option value="all">Any login status</option>
                <option value="never">Never logged in</option>
                <option value="has_logged_in">Has logged in</option>
              </select>
              <select
                value={regConsentFilter}
                onChange={(e) => setRegConsentFilter(e.target.value as "all" | "consented" | "declined" | "pending")}
                className="flex-1 sm:flex-none sm:w-auto h-9 px-2.5 bg-background border border-border rounded-xl text-xs focus:outline-none focus:border-primary transition-colors cursor-pointer"
              >
                <option value="all">Any media consent</option>
                <option value="consented">Consent: Granted</option>
                <option value="declined">Consent: Declined</option>
                <option value="pending">Consent: Pending</option>
              </select>
              <button
                onClick={handleExportRegistrations}
                disabled={filteredRegistrations.length === 0}
                title="Export the rows shown below to an .xlsx file"
                className="flex items-center justify-center gap-1.5 h-9 px-3 shrink-0 border border-border rounded-xl text-xs font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
              >
                <FileSpreadsheet size={14} /> Export
              </button>
            </div>
          </div>
        )}
        {drawerError && (
          <div className="text-xs text-red-600 dark:text-red-400 bg-red-500/10 border border-red-500/30 rounded-xl px-3 py-2 mb-2">
            {drawerError}
          </div>
        )}
        {isLoading ? <Spinner /> : registrations.length === 0 ? (
          <EmptyState title="No registrations yet" />
        ) : filteredRegistrations.length === 0 ? (
          <EmptyState title={regSearch ? `No registrations match "${regSearch}"` : "No registrations match this filter"} />
        ) : (
          <div className="flex flex-col gap-2">
            {filteredRegistrations.map((r) => {
              const attendancePct = r.total_cohort_sessions_count
                ? Math.round(((r.attended_sessions_count ?? 0) / r.total_cohort_sessions_count) * 100)
                : null
              return (
                <div
                  key={r.id}
                  className="flex flex-col gap-2 p-3 bg-background border border-border rounded-xl sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:gap-3"
                >
                  <div
                    className="min-w-0 flex-1 cursor-pointer group"
                    onClick={() => setEditRegistrationTarget(r)}
                  >
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <button
                        onClick={(e) => { e.stopPropagation(); setProfileContactId(r.contact_id) }}
                        className="text-sm font-medium text-foreground hover:text-primary hover:underline transition-colors break-words w-full sm:w-auto text-left"
                      >
                        {r.student_name}
                      </button>
                      {r.student_gender && (
                        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                          {r.student_gender}
                        </span>
                      )}
                      {/* Media Consent Clickable Badge */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          setConsentTarget(r)
                        }}
                        className={`text-xs font-semibold px-2 py-0.5 rounded-full transition-colors cursor-pointer ${
                          r.media_consent_status === "consented"
                            ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 hover:bg-emerald-200"
                            : r.media_consent_status === "declined"
                            ? "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400 hover:bg-red-200"
                            : "bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
                        }`}
                        title="Click to view details or change Media Consent state"
                      >
                        {r.media_consent_status === "consented"
                          ? "Consent: Granted"
                          : r.media_consent_status === "declined"
                          ? "Consent: Declined"
                          : "Consent: Pending"}
                      </button>
                      {r.ticket_sent ? (
                        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400">
                          Ticket sent
                        </span>
                      ) : (
                        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
                          No ticket
                        </span>
                      )}
                      {r.onboarding_sent ? (
                        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-400">
                          Onboarding sent
                        </span>
                      ) : (
                        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
                          No onboarding email
                        </span>
                      )}
                      {r.certificate_issued ? (
                        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400">
                          Certificate issued
                        </span>
                      ) : (
                        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                          No certificate
                        </span>
                      )}
                      {r.status === "cancelled" && (
                        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400">
                          Cancelled
                        </span>
                      )}
                      {!r.last_login_at && (
                        <span
                          className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400"
                          title="No LMS account exists yet, or one does but nobody's ever logged into it"
                        >
                          Never logged in
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground truncate">
                      {r.student_phone ?? "—"}
                      {r.student_email ? ` · ${r.student_email}` : ""}
                      {r.student_gender ? ` · ${r.student_gender}` : ""}
                      {r.student_date_of_birth ? ` · DOB: ${r.student_date_of_birth}` : ""}
                      {r.student_grade ? ` · ${r.student_grade}` : ""}
                      {r.student_organization_name ? ` · ${r.student_organization_name}` : ""}
                      {r.guardian_name ? ` · Guardian: ${r.guardian_name} (${r.guardian_phone ?? "—"})` : ""}
                      {r.price_charged != null ? ` · AED ${r.price_charged}` : ""}
                      {r.checked_in ? " · Checked in" : ""}
                      {attendancePct != null ? ` · Attendance ${r.attended_sessions_count ?? 0}/${r.total_cohort_sessions_count} (${attendancePct}%)` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0 justify-end border-t border-border/60 pt-2 sm:border-0 sm:pt-0">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                          aria-label={`Actions for ${r.student_name}`}
                        >
                          <MoreVertical size={16} />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent>
                        {r.total_cohort_sessions_count ? (
                          <DropdownMenuItem onClick={() => setAttendanceTarget(r)}>
                            <Award size={14} /> View attendance
                          </DropdownMenuItem>
                        ) : null}
                        {/* certificate_issued, not certificate_url — student certs
                            are emailed and never stored, so they have no URL. */}
                        {r.certificate_url ? (
                          <DropdownMenuItem asChild>
                            <a href={r.certificate_url} target="_blank" rel="noreferrer">
                              <Award size={14} /> Download certificate
                            </a>
                          </DropdownMenuItem>
                        ) : !r.certificate_issued && r.status !== "cancelled" && (
                          <DropdownMenuItem onClick={() => setCertificateTarget(r)}>
                            <Award size={14} /> Give certificate
                          </DropdownMenuItem>
                        )}
                        <DropdownMenuItem onClick={() => resendMutation.mutate(r.id)} disabled={resendMutation.isPending}>
                          <Ticket size={14} /> {r.ticket_sent ? "Resend ticket" : "Send ticket"}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => resendOnboardingMutation.mutate(r.id)}
                          disabled={resendOnboardingMutation.isPending}
                        >
                          <Mail size={14} /> {r.onboarding_sent ? "Resend onboarding email" : "Send onboarding email"}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => copySetPasswordLinkMutation.mutate(r.id)}
                          disabled={copySetPasswordLinkMutation.isPending}
                        >
                          <Copy size={14} /> Copy set-password link
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => setPaymentTarget(r)}>
                          <Wallet size={14} /> Confirm payment
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => setConsentTarget(r)}>
                          <Camera size={14} /> Media consent
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          variant="destructive"
                          disabled={r.status === "cancelled" || cancelMutation.isPending}
                          onClick={() => { setDrawerError(null); setCancelTarget(r) }}
                        >
                          <Ban size={14} /> Cancel registration
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          variant="destructive"
                          disabled={deleteRegistrationMutation.isPending}
                          onClick={() => { setDrawerError(null); setDeleteTarget(r) }}
                        >
                          <Trash2 size={14} /> Delete registration
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      )}

      {tab === "consents" && (
        <Card className="p-4">
          <CohortConsentsPanel cohortId={cohort.id} registrations={registrations} />
        </Card>
      )}

      {tab === "setup" && (
      <div className="flex flex-col gap-5">
      {/* I5-6: cohort-level materials — sessions use these unless they
          have their own. */}
      <Card className="px-4">
        <MaterialsPanel
          owner={{ cohort_id: cohort.id }}
          level="program"
          inheritedNote="Sessions use these unless they have their own."
        />
      </Card>

      {/* Phase 3a: same "set a default, session can override" pattern, for
          kits rather than materials. */}
      <Card className="px-4">
        <CohortKitsPanel cohort={cohort} />
      </Card>

      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-semibold text-foreground">
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
          <EmptyState title="No reports uploaded yet" />
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
      )}      </div>
      )}

      {editOpen && (
        <CohortModal
          programs={programs} cohort={cohort}
          onClose={() => setEditOpen(false)}
          onSuccess={() => { invalidateCohort(); setEditOpen(false) }}
        />
      )}
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
      {registerOpen && (
        <DeskRegisterModal
          cohort={cohort} sessions={sessions}
          onClose={() => setRegisterOpen(false)}
          onSuccess={() => { invalidateRegistrations(); setRegisterOpen(false) }}
        />
      )}
      {bulkAssignOpen && (
        <BulkAssignInstructorModal
          cohort={cohort} sessionIds={selectedSessionIds}
          onClose={() => setBulkAssignOpen(false)}
          onDone={() => { invalidateSessions(); setBulkAssignOpen(false); setBulkMode(false); setSelectedSessionIds([]) }}
        />
      )}
      {bulkOpenCallOpen && (
        <BulkOpenCallModal
          cohort={cohort} sessionIds={selectedSessionIds}
          onClose={() => setBulkOpenCallOpen(false)}
          onDone={() => { invalidateSessions(); setBulkOpenCallOpen(false); setBulkMode(false); setSelectedSessionIds([]) }}
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
      {profileContactId && (
        <ContactDetailModal
          contactId={profileContactId}
          onClose={() => setProfileContactId(null)}
          onChanged={invalidateRegistrations}
        />
      )}
      {attendanceTarget && (
        <StudentAttendanceModal
          registration={attendanceTarget}
          onClose={() => setAttendanceTarget(null)}
        />
      )}
      {consentTarget && (
        <MediaConsentModal
          cohortId={cohort.id}
          registration={consentTarget}
          onClose={() => setConsentTarget(null)}
        />
      )}

      {deleteTarget && (
        <DeleteRegistrationModal
          registration={deleteTarget}
          pending={deleteRegistrationMutation.isPending}
          error={drawerError}
          onCancel={() => { setDeleteTarget(null); setDrawerError(null) }}
          onConfirm={(deleteContact) =>
            deleteRegistrationMutation.mutate({ id: deleteTarget.id, deleteContact })
          }
        />
      )}
      {completeConfirmOpen && (
        <ConfirmDialog
          title={`Mark "${cohort.name}" as completed?`}
          description={
            unfinishedSessionCount > 0
              ? `This settles every registration and marks the ${unfinishedSessionCount} session(s) nobody completed as done.`
              : "This settles every registration for this cohort."
          }
          confirmLabel="Complete cohort"
          pending={completeCohortMutation.isPending}
          onCancel={() => {
            setCompleteConfirmOpen(false)
            setSendCertificates(false)
          }}
          onConfirm={() => {
            completeCohortMutation.mutate(sendCertificates)
            setCompleteConfirmOpen(false)
          }}
        >
          <label className="flex items-start gap-2 cursor-pointer select-none p-3 border border-border rounded-xl">
            <input
              type="checkbox"
              checked={sendCertificates}
              onChange={(e) => setSendCertificates(e.target.checked)}
              className="rounded text-primary focus:ring-primary border-border bg-background shrink-0 mt-0.5"
            />
            <span className="text-xs text-muted-foreground leading-snug">
              <span className="text-foreground font-medium">Send certificates to students via email</span>
              <br />
              When enabled, a completion certificate will be automatically emailed to each eligible student.
            </span>
          </label>
        </ConfirmDialog>
      )}
      {cancelTarget && (
        <ConfirmDialog
          title="Cancel registration?"
          description={`This frees ${cancelTarget.student_name}'s seat but keeps the record — you can register them again later.`}
          confirmLabel="Cancel registration"
          cancelLabel="Keep it"
          destructive
          error={drawerError}
          pending={cancelMutation.isPending}
          onCancel={() => { setCancelTarget(null); setDrawerError(null) }}
          onConfirm={() => cancelMutation.mutate(cancelTarget.id)}
        />
      )}
      {certificateTarget && (
        <ConfirmDialog
          title="Give completion certificate?"
          description={`Use this if ${certificateTarget.student_name} didn't meet the program's attendance requirement but still earned one.`}
          confirmLabel="Give certificate"
          error={drawerError}
          pending={giveCertificateMutation.isPending}
          onCancel={() => { setCertificateTarget(null); setDrawerError(null) }}
          onConfirm={() => giveCertificateMutation.mutate(certificateTarget.id)}
        />
      )}
    </div>
  )
}



/* ================================================================== */
/* Delete registration — destructive, so it spells out what goes      */
/* ================================================================== */
function DeleteRegistrationModal({ registration, pending, error, onCancel, onConfirm }: {
  registration: Registration
  pending: boolean
  error: string | null
  onCancel: () => void
  onConfirm: (deleteContact: boolean) => void
}) {
  const [alsoDeleteContact, setAlsoDeleteContact] = useState(false)

  return (
    <ConfirmDialog
      title={`Delete ${registration.student_name}'s registration?`}
      description={
        <>
          This erases the sign-up along with any attendance recorded for it and any certificate issued from it.
          It can't be undone.
          <br /><br />
          If they genuinely signed up and then dropped out, use <strong className="text-foreground">Cancel</strong> instead —
          that frees the seat but keeps the record, and you can register them again later.
        </>
      }
      confirmLabel={pending ? "Deleting…" : alsoDeleteContact ? "Delete registration + contact" : "Delete registration"}
      cancelLabel="Keep it"
      destructive
      pending={pending}
      error={error}
      onCancel={onCancel}
      onConfirm={() => onConfirm(alsoDeleteContact)}
    >
      <label className="flex items-start gap-2 cursor-pointer select-none p-3 border border-border rounded-xl">
        <input
          type="checkbox" checked={alsoDeleteContact} onChange={(e) => setAlsoDeleteContact(e.target.checked)}
          className="rounded text-primary focus:ring-primary border-border bg-background shrink-0 mt-0.5"
        />
        <span className="text-xs text-muted-foreground leading-snug">
          <span className="text-foreground font-medium">Also delete {registration.student_name} from Contacts.</span>
          {" "}Removes the person entirely — their touchpoints, role history and household links.
          Refused if they hold a staff account or are registered in another cohort.
        </span>
      </label>
    </ConfirmDialog>
  )
}

/* ================================================================== */
/* Generate sessions modal                                             */
/* ================================================================== */
function GenerateSessionsModal({ cohort, onClose, onGenerated }: {
  cohort: Cohort; onClose: () => void; onGenerated: () => void
}) {
  const toast = useToast()
  const [weekdays, setWeekdays] = useState<number[]>([0])
  const [count, setCount] = useState("8")
  const [startsAt, setStartsAt] = useState("")
  const [error, setError] = useState("")

  const toggleWeekday = (i: number) =>
    setWeekdays((prev) => prev.includes(i) ? prev.filter((w) => w !== i) : [...prev, i].sort())

  const mutation = useMutation({
    mutationFn: () => generateSessionsApi(cohort.id, { weekdays, count: Number(count), starts_at: startsAt || null }),
    onSuccess: (r) => {
      const created = r.created.length
      toast.success(`Created ${created} session${created !== 1 ? "s" : ""}${r.skipped > 0 ? ` (${r.skipped} already existed, skipped)` : ""}`)
      onGenerated()
      onClose()
    },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to generate sessions")),
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
  const toast = useToast()
  const [meetingDate, setMeetingDate] = useState(cohort.starts_on ?? "")
  const [startsAt, setStartsAt] = useState("")
  const [title, setTitle] = useState("")
  const [durationHours, setDurationHours] = useState("")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () => addSessionApi(cohort.id, {
      meeting_date: meetingDate, starts_at: startsAt || null, title: title.trim() || null,
      duration_hours: durationHours.trim() ? Number(durationHours) : null,
    }),
    onSuccess: () => { toast.success("Session added"); onSuccess() },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to add session")),
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
        <Field label="Duration override, hours (optional)">
          <input
            value={durationHours} onChange={(e) => setDurationHours(e.target.value)} type="number" step="0.5"
            placeholder="Leave blank to use the cohort/program duration"
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
/* Confirm payment modal                                               */
/* ================================================================== */
function ConfirmPaymentModal({ registration, onClose, onSuccess }: {
  registration: Registration; onClose: () => void; onSuccess: () => void
}) {
  const toast = useToast()
  const [amount, setAmount] = useState(registration.price_charged != null ? String(registration.price_charged) : "")
  const [status, setStatus] = useState<"paid" | "partial">("paid")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () => confirmPaymentApi(registration.id, { amount: Number(amount), status }),
    onSuccess: () => { toast.success("Payment confirmed"); onSuccess() },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to confirm payment")),
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
  const toast = useToast()
  const [studentName, setStudentName] = useState(registration.student_name || "")
  const [email, setEmail] = useState(registration.student_email || "")
  const [phone, setPhone] = useState(registration.student_phone || "")
  const [dateOfBirth, setDateOfBirth] = useState(registration.student_date_of_birth || "")
  const [grade, setGrade] = useState(registration.student_grade || "")
  const [gender, setGender] = useState(registration.student_gender || "")
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
        gender: gender.trim() || null,
        ...(organizationName.trim() ? { organization_name: organizationName.trim() } : {}),
      }),
    onSuccess: () => { toast.success("Student info saved"); onSuccess() },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to update student info")),
  })

  return (
    <Modal title={`Edit student — ${registration.student_name}`} onClose={onClose}>
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
        <div className="grid grid-cols-3 gap-2">
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
          <Field label="Gender">
            <input
              value={gender}
              onChange={(e) => setGender(e.target.value)}
              placeholder="Male / Female"
              list="cohort-student-gender-list"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
            <datalist id="cohort-student-gender-list">
              <option value="Male" />
              <option value="Female" />
            </datalist>
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
    <Modal title={`Attendance breakdown — ${registration.student_name}`} onClose={onClose} maxWidth="max-w-md">
      <div className="flex flex-col gap-4">
        <div className="p-3 bg-muted/30 border border-border rounded-xl flex items-center justify-between">
          <div>
            <p className="text-xs text-muted-foreground font-medium">Overall attendance</p>
            <p className="text-lg font-bold text-foreground">{attended} / {total} sessions <span className="text-sm font-normal text-muted-foreground">({pct}%)</span></p>
          </div>
          <div className="w-20 bg-muted h-2 rounded-full overflow-hidden shrink-0">
            <div className="bg-primary h-full rounded-full" style={{ width: `${Math.min(100, pct)}%` }} />
          </div>
        </div>

        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Session breakdown</p>
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
