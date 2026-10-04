import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "@tanstack/react-router"
import { ArrowLeft, ArrowUpRight, Award, Clock, Download, Eye, Mail, MessageSquare, Plus, Printer, Search, Trash2, Trophy, Upload, UserPlus, UserMinus, Pencil, X, Check, RotateCcw } from "lucide-react"
import { getCohortApi, getCohortsApi } from "@/api/sessions/cohorts"
import type { Cohort, ProgramCertificateTemplate } from "@/types/sessions"
import { searchStaffApi, listInviteCodesApi, type StaffOption } from "@/api/lms_admin"
import { UserProfileModal } from "@/components/UserProfileModal"
import { CompetitionCertificatesModal } from "@/pages/admin/components/CompetitionCertificatesModal"
import { TeamScoreBreakdownModal } from "@/components/competitions/TeamScoreBreakdownModal"
import { TeamOperationsScoreModal } from "@/components/competitions/TeamOperationsScoreModal"
import { PublishResultsModal } from "@/components/competitions/PublishResultsModal"
import { TimingOverrideModal } from "@/components/competitions/TimingOverrideModal"
import { SubmissionWindowsModal } from "@/components/competitions/SubmissionWindowsModal"
import { listProgramCertificateTemplatesApi } from "@/api/sessions/programCertificateTemplates"
import {
  advanceCohortTeamsApi, createCohortTeamApi, deleteTeamApi, downloadCohortResultsWorkbookApi, registerUsersToCohortApi,
  downloadCompetitionCertificatesApi,
  getCohortExportTop20Api,
  confirmCohortRegistrationImportApi,
  getCohortJudgesApi, getCohortLeaderboardApi, getCohortPublicationApi, getCohortTeamsApi, getCohortRubricApi,
  previewCohortRegistrationImportApi, searchAssignableStudentsApi,
  inviteCohortJudgeApi, putCohortRubricApi, registerAndAddTeamMemberApi, addExistingTeamMemberApi,
  removeTeamMemberApi, renameTeamApi, resendJudgeOnboardingEmailApi, revokeCohortJudgeApi, unpublishCohortResultsApi,
  resetObserverTeamApi,
  type CompetitionAssignStudentsResult, type CompetitionImportPreviewRow, type CompetitionImportResult,
  type CompetitionJudgeProgress,
  type CompetitionLeaderboardRow, type CompetitionPublication, type CompetitionRubric, type CompetitionTeam,
  type CertificateFilterMode,
} from "@/api/competitions"
import { CompetitionAnalysisTab } from "@/pages/admin/components/CompetitionAnalysis"
import { PageHeader, Spinner, EmptyState } from "@/components/ui/primitives"
import { Field } from "@/pages/admin/components/common"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

type JudgingTab = "roster" | "assign" | "teams" | "analysis" | "rubric" | "judges" | "results"
const TABS: { key: JudgingTab; label: string }[] = [
  { key: "roster", label: "Roster" },
  { key: "assign", label: "Assign" },
  { key: "teams", label: "Teams" },
  // Analysis (2026-09-16) — read-only team progress across the whole
  // cohort. Sits next to Teams because it answers the question the
  // Teams tab makes you ask ("how are they all actually doing?"), and
  // before the judging tabs because it is about the run-up, not the
  // scoring.
  { key: "analysis", label: "Analysis" },
  { key: "rubric", label: "Rubric" },
  { key: "judges", label: "Judges" },
  { key: "results", label: "Results" },
]

export default function CompetitionJudging() {
  const { cohortId } = useParams({ strict: false }) as { cohortId: string }
  const [tab, setTab] = useState<JudgingTab>("roster")
  const [certificatesOpen, setCertificatesOpen] = useState(false)

  const { data: cohort, isLoading } = useQuery({
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

  return (
    <div className="flex flex-col gap-5">
      <Link
        to="/operations/cohorts/$cohortId" params={{ cohortId: cohort.id }}
        className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft size={14} /> {cohort.name}
      </Link>

      <PageHeader
        title={`Judging — ${cohort.name}`}
        subtitle={cohort.program_name ?? "—"}
        action={
          <button
            onClick={() => setCertificatesOpen(true)}
            className="flex items-center gap-1.5 h-9 px-3.5 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors shrink-0"
            title="Issue and email completion certificates"
          >
            <Award size={14} className="text-primary" /> Certificates
          </button>
        }
      />

      {/* overflow-x-auto + shrink-0 (2026-09-17) — seven tabs since Analysis
          landed no longer fits a phone width; without this the row just
          clipped past "Results" with no way to reach it by touch. */}
      <div className="flex gap-1 border-b border-border overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors shrink-0 whitespace-nowrap ${
              tab === t.key ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "roster" && <RosterTab cohortId={cohort.id} />}
      {tab === "assign" && <AssignTab cohortId={cohort.id} />}
      {tab === "teams" && <TeamsTab cohortId={cohort.id} />}
      {tab === "analysis" && <CompetitionAnalysisTab cohortId={cohort.id} />}
      {tab === "rubric" && <RubricTab cohortId={cohort.id} />}
      {tab === "judges" && <JudgesTab cohortId={cohort.id} />}
      {tab === "results" && (
        <ResultsTab
          cohortId={cohort.id}
          cohortName={cohort.name}
          programId={cohort.program_id}
          onOpenCertificates={() => setCertificatesOpen(true)}
        />
      )}

      <CompetitionCertificatesModal
        cohortId={cohort.id}
        cohortName={cohort.name}
        programName={cohort.program_name ?? undefined}
        open={certificatesOpen}
        onClose={() => setCertificatesOpen(false)}
      />
    </div>
  )
}

/* ================================================================== */
/* Roster (registration import)                                        */
/* ================================================================== */
const IMPORT_EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

// A missing required field is the only thing that stops a row from being
// written — mirrors registration_import.py's `_blocking_issues`. A
// malformed-but-present email is a *warning*: ops can still confirm and
// keep it (fix the address for that student later) rather than being
// forced to invent one just to get past this screen.
const BLOCKING_ISSUES = new Set(["Team ID is required", "Member name is required", "Email is required"])
const isBlockingIssue = (issue: string) => BLOCKING_ISSUES.has(issue)

// Mirrors registration_import.py's `_row_issues` — for instant feedback as
// ops edits a cell, before the real re-check happens server-side on confirm.
// team_name is NOT checked here — it's optional (see CompetitionImportPreviewRow's
// own comment); team_id is the required grouping key now.
function rowIssues(row: CompetitionImportPreviewRow): string[] {
  const issues: string[] = []
  if (!row.team_id?.trim()) issues.push("Team ID is required")
  if (!row.member_name?.trim()) issues.push("Member name is required")
  if (!row.email?.trim()) issues.push("Email is required")
  else if (!IMPORT_EMAIL_RE.test(row.email.trim())) issues.push("Email is not valid")
  return issues
}

function RosterTab({ cohortId }: { cohortId: string }) {
  const toast = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [previewRows, setPreviewRows] = useState<CompetitionImportPreviewRow[] | null>(null)
  const [result, setResult] = useState<CompetitionImportResult | null>(null)
  const [sendWelcomeEmail, setSendWelcomeEmail] = useState(true)
  const [sendTicketEmail, setSendTicketEmail] = useState(true)

  const previewMutation = useMutation({
    mutationFn: (file: File) => previewCohortRegistrationImportApi(cohortId, file),
    onSuccess: (res) => { setResult(null); setPreviewRows(res.rows) },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to read this file")),
  })

  const confirmMutation = useMutation({
    mutationFn: (rows: CompetitionImportPreviewRow[]) =>
      confirmCohortRegistrationImportApi(cohortId, rows.map(({ issues, ...rest }) => rest), {
        send_welcome_email: sendWelcomeEmail, send_ticket_email: sendTicketEmail,
      }),
    onSuccess: (res) => {
      setResult(res)
      setPreviewRows(null)
      setSendWelcomeEmail(true); setSendTicketEmail(true)
      toast.success(`Imported: ${res.summary.created} created, ${res.summary.matched} matched, ${res.summary.error} errors`)
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to import roster")),
  })

  const updateRow = (rowNumber: number, field: keyof CompetitionImportPreviewRow, value: string) => {
    setPreviewRows((rows) =>
      (rows ?? []).map((r) => {
        if (r.row_number !== rowNumber) return r
        const updated = { ...r, [field]: value || null }
        return { ...updated, issues: rowIssues(updated) }
      }),
    )
  }

  const issueCount = previewRows?.filter((r) => r.issues.length > 0).length ?? 0
  const blockingCount = previewRows?.filter((r) => r.issues.some(isBlockingIssue)).length ?? 0

  return (
    <div className="flex flex-col gap-4 max-w-4xl">
      {!previewRows && (
        <>
          <p className="text-sm text-muted-foreground">
            Upload the final roster exported from the registration form — columns <code>team_id</code>,{" "}
            <code>member_name</code>, <code>email</code>, and optionally <code>team_name</code>/<code>phone</code>/
            <code>nationality</code>/<code>school</code>. A team with no <code>team_name</code> yet gets its{" "}
            <code>team_id</code> as a placeholder — students set the real one themselves later. You'll get a
            preview to review before anything is created — a missing field blocks that row, a malformed email is
            just flagged (fix it or leave it, your call). Re-uploading the same sheet later just matches instead of
            duplicating, and never overwrites a name a team already set for real.
          </p>
          <input
            ref={fileInputRef} type="file" accept=".xlsx,.xls,.csv" className="hidden"
            onChange={(e) => { const file = e.target.files?.[0]; if (file) previewMutation.mutate(file); e.target.value = "" }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={previewMutation.isPending}
            className="self-start flex items-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
          >
            <Upload size={14} /> {previewMutation.isPending ? "Reading…" : "Upload roster"}
          </button>
        </>
      )}

      {previewRows && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-foreground">
              {previewRows.length} rows parsed
              {blockingCount > 0 && (
                <span className="text-red-600 dark:text-red-400"> · {blockingCount} won't import until fixed</span>
              )}
              {issueCount > blockingCount && (
                <span className="text-amber-600 dark:text-amber-400">
                  {" "}· {issueCount - blockingCount} flagged (email looks wrong) — importable as-is, or fix first
                </span>
              )}
            </p>
            <button
              onClick={() => setPreviewRows(null)}
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Start over
            </button>
          </div>

          <div className="overflow-x-auto border border-border rounded-xl">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground uppercase tracking-wider border-b border-border">
                  <th className="py-2 pl-3 pr-2">Row</th>
                  <th className="py-2 pr-2">Team ID</th>
                  <th className="py-2 pr-2">Team name</th>
                  <th className="py-2 pr-2">Member</th>
                  <th className="py-2 pr-2">Email</th>
                  <th className="py-2 pr-2">Phone</th>
                  <th className="py-2 pr-2">Nationality</th>
                  <th className="py-2 pr-3">School</th>
                </tr>
              </thead>
              <tbody>
                {previewRows.map((r) => {
                  const blocked = r.issues.some(isBlockingIssue)
                  return (
                    <tr key={r.row_number} className={`border-b border-border/50 ${
                      blocked ? "bg-red-50 dark:bg-red-950/20" : r.issues.length > 0 ? "bg-amber-50 dark:bg-amber-950/20" : ""
                    }`}>
                      <td className="py-1.5 pl-3 pr-2 text-muted-foreground align-top pt-3">{r.row_number}</td>
                      {(["team_id", "team_name", "member_name", "email", "phone", "nationality", "school"] as const).map((field) => (
                        <td key={field} className="py-1.5 pr-2">
                          <input
                            value={r[field] ?? ""}
                            onChange={(e) => updateRow(r.row_number, field, e.target.value)}
                            className={`w-full h-8 px-2 rounded-lg border bg-background text-sm ${
                              (field === "team_id" || field === "member_name" || field === "email") &&
                              r.issues.some((i) => i.toLowerCase().startsWith(field === "team_id" ? "team id" : field === "member_name" ? "member name" : "email"))
                                ? (r.issues.some(isBlockingIssue) ? "border-red-400 dark:border-red-700" : "border-amber-400 dark:border-amber-700")
                                : "border-border"
                            }`}
                          />
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {previewRows.some((r) => r.issues.length > 0) && (
            <ul className="text-xs flex flex-col gap-0.5">
              {previewRows.filter((r) => r.issues.length > 0).map((r) => (
                <li key={r.row_number} className={r.issues.some(isBlockingIssue) ? "text-red-600 dark:text-red-400" : "text-amber-600 dark:text-amber-400"}>
                  Row {r.row_number}: {r.issues.join("; ")}
                </li>
              ))}
            </ul>
          )}

          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
              <input
                type="checkbox" checked={sendWelcomeEmail}
                onChange={(e) => setSendWelcomeEmail(e.target.checked)}
              />
              Send LMS onboarding mail
            </label>
            <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
              <input
                type="checkbox" checked={sendTicketEmail}
                onChange={(e) => setSendTicketEmail(e.target.checked)}
              />
              Send Ticket
            </label>
          </div>

          <button
            onClick={() => confirmMutation.mutate(previewRows)}
            disabled={confirmMutation.isPending}
            className="self-start flex items-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
          >
            <Check size={14} /> {confirmMutation.isPending ? "Importing…" : "Confirm import"}
          </button>
        </div>
      )}

      {result && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-foreground">
              {result.summary.total} rows · {result.summary.created} created · {result.summary.matched} matched ·{" "}
              {result.summary.error} errors
            </p>
            <button
              onClick={() => setResult(null)}
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Import another file
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground uppercase tracking-wider border-b border-border">
                  <th className="py-2 pr-3">Row</th>
                  <th className="py-2 pr-3">Team ID</th>
                  <th className="py-2 pr-3">Team</th>
                  <th className="py-2 pr-3">Email</th>
                  <th className="py-2 pr-3">Result</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={r.row_number} className="border-b border-border/50">
                    <td className="py-2 pr-3 text-muted-foreground">{r.row_number}</td>
                    <td className="py-2 pr-3">{r.team_id ?? "—"}</td>
                    <td className="py-2 pr-3">{r.team_name ?? "—"}</td>
                    <td className="py-2 pr-3">{r.email ?? "—"}</td>
                    <td className={`py-2 pr-3 ${r.disposition === "error" ? "text-red-600 dark:text-red-400" : "text-foreground"}`}>
                      {r.disposition === "error" ? r.reason : r.disposition}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

/* ================================================================== */
/* Assign (existing self-registered students → team + registration)   */
/* ================================================================== */
// (2026-09-14) Requirements changed again: ops no longer holds student
// info at all — students self-register with an invite code first
// (routers/auth.py::student_signup), then ops finds them here and types
// in a Team ID per row, same editable-cell feel as the Roster table
// above. Team *naming* stays entirely the student's own deadline-gated
// step (the `team_setup` checklist item) — this tab only ever assigns a
// Team ID, never a display name.
type TeamStatusFilter = "all" | "has_team" | "no_team"
type LoginStatusFilter = "all" | "never" | "has_logged_in"
type AssignMode = "student" | "staff" | "observer"
type AssignSort = "full_name" | "card_number" | "created_at" | "email"

const STAFF_ROLE_OPTIONS = [
  "instructor", "intern", "operations", "facilitator", "admin",
  "lms_author", "judge", "ambassador", "teacher", "leader", "coo", "storekeeper",
]

function AssignTab({ cohortId }: { cohortId: string }) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [query, setQuery] = useState("")
  const [inviteCode, setInviteCode] = useState("")
  const [registeredOnly, setRegisteredOnly] = useState(false)
  const [teamStatus, setTeamStatus] = useState<TeamStatusFilter>("all")
  const [loginStatus, setLoginStatus] = useState<LoginStatusFilter>("all")
  // Rebuild (2026-10): Students | Staff (literally not a student, with a
  // role filter) | Observers (has the observer role). No All — the role
  // sets and team pools are disjoint per toggle.
  const [mode, setMode] = useState<AssignMode>("student")
  const [role, setRole] = useState("")
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [sort, setSort] = useState<AssignSort>("full_name")
  const [direction, setDirection] = useState<"asc" | "desc">("asc")
  const [selected, setSelected] = useState<Record<string, boolean>>({})
  const [rowTeam, setRowTeam] = useState<Record<string, string>>({})
  const [bulkTeam, setBulkTeam] = useState("")
  const [newTeamName, setNewTeamName] = useState("")
  const [sendWelcomeEmail, setSendWelcomeEmail] = useState(true)
  const [sendTicketEmail, setSendTicketEmail] = useState(true)
  const [result, setResult] = useState<CompetitionAssignStudentsResult | null>(null)
  // Snapshot of who each result row refers to, taken at click time — the
  // list refreshes after the mutation, so looking names up from the live
  // page afterwards would fall back to raw UUIDs.
  const [resultNames, setResultNames] = useState<Record<string, { name: string; email: string; card_id: string | null }>>({})
  const snapshotNames = (ids: string[]) => {
    const map: Record<string, { name: string; email: string; card_id: string | null }> = {}
    ids.forEach((id) => {
      const s = students.find((row) => row.id === id)
      if (s) map[id] = { name: s.full_name, email: s.email, card_id: s.card_id }
    })
    setResultNames(map)
  }

  // Any filter/mode change restarts at page 1.
  useEffect(() => { setPage(1); setSelected({}) }, [query, inviteCode, registeredOnly, teamStatus, loginStatus, mode, role, pageSize, sort, direction])

  const { data: assignPage, isLoading } = useQuery({
    queryKey: ["competitions-assignable-students", cohortId, query, inviteCode, registeredOnly, teamStatus, loginStatus, mode, role, page, pageSize, sort, direction],
    queryFn: () => searchAssignableStudentsApi(cohortId, {
      q: query || undefined, invite_code: inviteCode || undefined, registered_only: registeredOnly,
      team_status: teamStatus, login_status: loginStatus, mode,
      role: mode === "staff" && role ? role : undefined,
      page, page_size: pageSize, sort, direction,
    }),
  })
  const students = assignPage?.items ?? []
  const total = assignPage?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const { data: codes = [] } = useQuery({
    queryKey: ["lms-admin-invite-codes"],
    queryFn: listInviteCodesApi,
  })
  const { data: allTeams = [] } = useQuery({
    queryKey: ["competitions-cohort-teams", cohortId],
    queryFn: () => getCohortTeamsApi(cohortId),
  })
  // Team pool is partitioned like the toggles: students get student teams,
  // staff/observers get observer sandbox teams (the backend still enforces
  // the partition — this just keeps the dropdown honest).
  const teamPool = allTeams.filter((t) => mode === "student" ? !t.is_observer : !!t.is_observer)

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["competitions-assignable-students", cohortId] })
    void queryClient.invalidateQueries({ queryKey: ["competitions-cohort-teams", cohortId] })
  }

  // Add to program without a team (register + LMS assignment; staff gain
  // the observer role + a mode="observer" assignment server-side).
  const registerMutation = useMutation({
    mutationFn: (userIds: string[]) =>
      registerUsersToCohortApi(cohortId, userIds, { send_welcome_email: sendWelcomeEmail, send_ticket_email: sendTicketEmail }),
    onSuccess: (res) => {
      setResult(res)
      setSelected({})
      invalidate()
      toast.success(`Added: ${res.summary.created} newly registered, ${res.summary.matched} already in program, ${res.summary.error} errors`)
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to add to program")),
  })

  // Put user(s) on an existing team by UUID — the server registers them
  // first when needed (same interchangeable rule as add-to-program) and
  // enforces the single-team-per-cohort move.
  const moveMutation = useMutation({
    mutationFn: async (moves: { user_id: string; team_id: string }[]) => {
      for (const m of moves) await addExistingTeamMemberApi(m.team_id, m.user_id)
      return moves.length
    },
    onSuccess: (n) => {
      setSelected({})
      setRowTeam({})
      setBulkTeam("")
      invalidate()
      toast.success(n === 1 ? "Moved to team" : `Moved ${n} to team`)
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to move to team")),
  })

  const createTeamMutation = useMutation({
    mutationFn: (name: string) => createCohortTeamApi(cohortId, name, mode !== "student"),
    onSuccess: (team) => {
      setNewTeamName("")
      invalidate()
      toast.success(`Team "${team.name}" created`)
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to create team")),
  })

  const selectedIds = Object.keys(selected).filter((id) => selected[id])
  const toggleSort = (key: AssignSort) => {
    if (sort === key) setDirection((d) => (d === "asc" ? "desc" : "asc"))
    else { setSort(key); setDirection("asc") }
  }
  const sortArrow = (key: AssignSort) => (sort === key ? (direction === "asc" ? " ↑" : " ↓") : "")

  const allOnPageSelected = students.length > 0 && students.every((s) => selected[s.id])

  return (
    <div className="flex flex-col gap-4 w-full">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative max-w-md flex-1 min-w-[220px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Search ${mode === "student" ? "students" : mode === "staff" ? "staff" : "observers"} by name, email, or card ID...`}
            className="w-full h-10 pl-8 pr-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </div>
        <select
          value={inviteCode}
          onChange={(e) => setInviteCode(e.target.value)}
          className="w-auto shrink-0 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="">All batches</option>
          {codes.map((c) => (
            <option key={c.id} value={c.code}>{c.label ? `${c.label} (${c.code})` : c.code}</option>
          ))}
          <option value="none">No code</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
          <input type="checkbox" checked={registeredOnly} onChange={(e) => setRegisteredOnly(e.target.checked)} />
          Registered to this cohort
        </label>
        <select
          value={teamStatus}
          onChange={(e) => setTeamStatus(e.target.value as TeamStatusFilter)}
          className="w-auto shrink-0 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="all">Any team status</option>
          <option value="no_team">No team yet</option>
          <option value="has_team">Has a team</option>
        </select>
        <select
          value={loginStatus}
          onChange={(e) => setLoginStatus(e.target.value as LoginStatusFilter)}
          className="w-auto shrink-0 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="all">Any login status</option>
          <option value="never">Never logged in</option>
          <option value="has_logged_in">Has logged in</option>
        </select>

        <div className="flex items-center p-1 bg-muted/60 border border-border/80 rounded-xl text-xs">
          <button
            type="button"
            onClick={() => { setMode("student"); setRole("") }}
            className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
              mode === "student" ? "bg-background text-foreground shadow-xs font-semibold" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Students
          </button>
          <button
            type="button"
            onClick={() => setMode("staff")}
            className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
              mode === "staff" ? "bg-background text-foreground shadow-xs font-semibold" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Staff
          </button>
          <button
            type="button"
            onClick={() => { setMode("observer"); setRole("") }}
            className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
              mode === "observer" ? "bg-background text-indigo-600 dark:text-indigo-400 shadow-xs font-semibold" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Observers
          </button>
        </div>
        {mode === "staff" && (
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="w-auto shrink-0 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
          >
            <option value="">All roles</option>
            {STAFF_ROLE_OPTIONS.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        )}
      </div>

      {/* Team bar: existing teams + create — on top, applies to selection or per row */}
      <div className="flex flex-wrap items-center gap-3 p-3 bg-muted/40 border border-border rounded-xl">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          {mode === "student" ? "Student teams" : "Observer teams"} ({teamPool.length})
        </span>
        <select
          value={bulkTeam}
          onChange={(e) => setBulkTeam(e.target.value)}
          className="h-9 px-2 border border-border bg-card text-foreground rounded-lg text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer min-w-[180px]"
        >
          <option value="">Select a team…</option>
          {teamPool.map((t) => (
            <option key={t.id} value={t.id}>{t.name} ({t.member_ids.length})</option>
          ))}
        </select>
        <div className="flex items-center gap-2">
          <input
            value={newTeamName}
            onChange={(e) => setNewTeamName(e.target.value)}
            placeholder="New team name…"
            className="h-9 px-2 border border-border bg-card text-foreground rounded-lg text-sm w-44 focus:outline-none focus:border-primary transition-colors"
          />
          <button
            type="button"
            onClick={() => newTeamName.trim() && createTeamMutation.mutate(newTeamName.trim())}
            disabled={!newTeamName.trim() || createTeamMutation.isPending}
            className="h-9 px-3 rounded-lg bg-secondary text-secondary-foreground text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50 cursor-pointer"
          >
            <Plus size={13} className="inline mr-1" />Team
          </button>
        </div>
        {selectedIds.length > 0 && (
          <>
            <button
              type="button"
              onClick={() => { snapshotNames(selectedIds); registerMutation.mutate(selectedIds) }}
              disabled={registerMutation.isPending}
              className="h-9 px-3 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50 cursor-pointer"
            >
              <Check size={13} className="inline mr-1" />
              {registerMutation.isPending ? "Adding…" : `Add to program (${selectedIds.length})`}
            </button>
            <button
              type="button"
              onClick={() => bulkTeam && moveMutation.mutate(selectedIds.map((id) => ({ user_id: id, team_id: bulkTeam })))}
              disabled={!bulkTeam || moveMutation.isPending}
              className="h-9 px-3 rounded-lg border border-border bg-card text-foreground text-sm font-medium hover:bg-muted transition-colors disabled:opacity-50 cursor-pointer"
            >
              {moveMutation.isPending ? "Moving…" : `Move to team (${selectedIds.length})`}
            </button>
          </>
        )}
        <div className="flex items-center gap-4 ml-auto">
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer select-none">
            <input type="checkbox" checked={sendWelcomeEmail} onChange={(e) => setSendWelcomeEmail(e.target.checked)} />
            LMS mail
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer select-none">
            <input type="checkbox" checked={sendTicketEmail} onChange={(e) => setSendTicketEmail(e.target.checked)} />
            Ticket
          </label>
        </div>
      </div>

      {isLoading ? (
        <Spinner />
      ) : students.length === 0 ? (
        <EmptyState
          title={mode === "staff" ? "No staff found" : mode === "observer" ? "No observers found" : "No students found"}
          hint={
            registeredOnly
              ? "Nobody registered to this cohort matches these filters — untick \"Registered to this cohort\" to search everyone."
              : query || inviteCode ? "Try a different search or batch." : "No accounts match the selected filters."
          }
        />
      ) : (
        <div className="overflow-x-auto border border-border rounded-xl w-full">
          <table className="w-full min-w-[980px] text-sm table-fixed">
            <thead>
              <tr className="text-left text-xs text-muted-foreground uppercase tracking-wider border-b border-border">
                <th className="py-2 pl-3 pr-2 w-10">
                  <input
                    type="checkbox"
                    checked={allOnPageSelected}
                    onChange={(e) => {
                      const next: Record<string, boolean> = { ...selected }
                      students.forEach((s) => { next[s.id] = e.target.checked })
                      setSelected(next)
                    }}
                  />
                </th>
                <th className="py-2 pr-2 w-[22%]">
                  <button type="button" onClick={() => toggleSort("full_name")} className="cursor-pointer hover:text-foreground">
                    Name{sortArrow("full_name")}
                  </button>
                </th>
                <th className="py-2 pr-2 w-[18%]">Email</th>
                <th className="py-2 pr-2 w-[12%]">
                  <button type="button" onClick={() => toggleSort("card_number")} className="cursor-pointer hover:text-foreground">
                    Card ID{sortArrow("card_number")}
                  </button>
                </th>
                <th className="py-2 pr-2 w-[10%]">Code used</th>
                <th className="py-2 pr-2 w-[14%]">Status</th>
                <th className="py-2 pr-2 w-[11%]">Login</th>
                <th className="py-2 pr-3 w-[13%]">Team</th>
              </tr>
            </thead>
            <tbody>
              {students.map((s) => (
                <tr key={s.id} className="border-b border-border/50">
                  <td className="py-1.5 pl-3 pr-2">
                    <input
                      type="checkbox"
                      checked={!!selected[s.id]}
                      onChange={(e) => setSelected((prev) => ({ ...prev, [s.id]: e.target.checked }))}
                    />
                  </td>
                  <td className="py-1.5 pr-2 align-top pt-3 font-medium text-foreground break-words">
                    <div className="flex items-start gap-1.5 flex-wrap">
                      <span className="break-words">{s.full_name}</span>
                      {s.is_observer && (
                        <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border border-indigo-500/30">
                          Observer
                        </span>
                      )}
                      {mode === "staff" && s.roles.length > 0 && (
                        <span
                          className="inline-flex items-center gap-1 flex-wrap"
                          title={s.roles.join(", ")}
                        >
                          {s.roles.slice(0, 2).map((r) => (
                            <span key={r} className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground whitespace-nowrap">
                              {r}
                            </span>
                          ))}
                          {s.roles.length > 2 && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground whitespace-nowrap">
                              +{s.roles.length - 2}
                            </span>
                          )}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-1.5 pr-2 align-top pt-3 text-muted-foreground truncate max-w-0" title={s.email}>{s.email}</td>
                  <td className="py-1.5 pr-2 align-top pt-3 text-muted-foreground whitespace-nowrap font-mono text-xs">
                    {s.card_id ?? "—"}
                  </td>
                  <td className="py-1.5 pr-2 align-top pt-3 text-muted-foreground whitespace-nowrap">
                    {s.invite_code ? (s.invite_label ?? s.invite_code) : "—"}
                  </td>
                  <td className="py-1.5 pr-2 align-top pt-3 whitespace-nowrap">
                    {/* "In program" is interchangeable: a Registration, this
                    cohort's LMS assignment, or a team seat here all count —
                    some flows (try-as-observer) team people up without ever
                    writing a Registration row. The button only shows when
                    none of those exist; clicking it backfills the missing
                    Registration server-side. */}
                    {s.registered || s.lms_access || s.team_uuid ? (
                      <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">In program</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => { snapshotNames([s.id]); registerMutation.mutate([s.id]) }}
                        disabled={registerMutation.isPending}
                        className="text-xs font-semibold text-primary hover:underline cursor-pointer disabled:opacity-50"
                      >
                        + Add to program
                      </button>
                    )}
                    {s.team_name && (
                      <span className="block text-xs text-muted-foreground">{s.team_name}</span>
                    )}
                  </td>
                  <td className="py-1.5 pr-2 align-top pt-3 whitespace-nowrap">
                    {s.last_login_at ? (
                      <span className="text-muted-foreground">{new Date(s.last_login_at).toLocaleDateString()}</span>
                    ) : (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 whitespace-nowrap">
                        NEVER LOGGED IN
                      </span>
                    )}
                  </td>
                  <td className="py-1.5 pr-3">
                    <select
                      value={rowTeam[s.id] ?? s.team_uuid ?? ""}
                      onChange={(e) => {
                        const teamId = e.target.value
                        setRowTeam((prev) => ({ ...prev, [s.id]: teamId }))
                        if (teamId) moveMutation.mutate([{ user_id: s.id, team_id: teamId }])
                      }}
                      className="h-8 px-2 rounded-lg border border-border bg-background text-sm min-w-[140px] max-w-[200px] cursor-pointer"
                    >
                      {s.team_uuid ? (
                        <option value={s.team_uuid}>{s.team_name ?? "Current team"}</option>
                      ) : (
                        <option value="">No team</option>
                      )}
                      {teamPool.filter((t) => t.id !== s.team_uuid).map((t) => (
                        <option key={t.id} value={t.id}>{t.name}</option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
        <span>{total} result{total === 1 ? "" : "s"}</span>
        <div className="flex items-center gap-1 ml-auto">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="h-8 px-3 rounded-lg border border-border bg-card disabled:opacity-40 cursor-pointer"
          >
            Prev
          </button>
          <span className="px-2">Page {page} of {totalPages}</span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="h-8 px-3 rounded-lg border border-border bg-card disabled:opacity-40 cursor-pointer"
          >
            Next
          </button>
          <select
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
            className="h-8 px-2 border border-border bg-card text-foreground rounded-lg text-sm cursor-pointer"
          >
            {[10, 25, 50, 100].map((n) => (
              <option key={n} value={n}>{n} / page</option>
            ))}
          </select>
        </div>
      </div>

      {result && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-foreground">
              {result.summary.total} rows · {result.summary.created} newly registered · {result.summary.matched} already in program ·{" "}
              {result.summary.error} errors
            </p>
            <button
              onClick={() => setResult(null)}
              className="text-sm text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            >
              Dismiss
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground uppercase tracking-wider border-b border-border">
                  <th className="py-2 pr-3">Name</th>
                  <th className="py-2 pr-3">Card ID</th>
                  <th className="py-2 pr-3">Result</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r) => {
                  const snap = r.user_id ? resultNames[r.user_id] : undefined
                  const live = r.user_id ? students.find((s) => s.id === r.user_id) : undefined
                  const name = snap ? `${snap.name} (${snap.email})` : live ? `${live.full_name} (${live.email})` : (r.user_id ?? "—")
                  const card = snap?.card_id ?? live?.card_id ?? "—"
                  return (
                    <tr key={r.row_number} className="border-b border-border/50">
                      <td className="py-2 pr-3">
                        {name}
                        {r.team_name ? <span className="text-muted-foreground"> → {r.team_name}</span> : null}
                      </td>
                      <td className="py-2 pr-3 font-mono text-xs text-muted-foreground">{card}</td>
                      <td className={`py-2 pr-3 ${r.disposition === "error" ? "text-red-600 dark:text-red-400" : "text-foreground"}`}>
                        {r.disposition === "error" ? r.reason : r.disposition === "created" ? "added to program" : "already in program"}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

/* ================================================================== */
/* Teams (manual management — complements Roster import)               */
/* ================================================================== */
/** Same chip shape `CohortDetail.tsx`'s own counter row uses — read-only
 * here, since every number is already visible in the list below it. */
function TeamStatChip({ label, value, tone = "default" }: {
  label: string; value: React.ReactNode; tone?: "default" | "alert"
}) {
  return (
    <div
      className={`flex items-center justify-center gap-1.5 h-9 px-4 rounded-xl border text-sm ${
        tone === "alert"
          ? "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400"
          : "border-border bg-card text-foreground"
      }`}
    >
      <span className="font-semibold tabular-nums leading-none flex items-center">{value}</span>
      <span className="text-xs text-muted-foreground leading-none flex items-center">{label}</span>
    </div>
  )
}

function TeamsTab({ cohortId }: { cohortId: string }) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["competitions-teams", cohortId] })

  const { data: teams = [], isLoading } = useQuery<CompetitionTeam[]>({
    queryKey: ["competitions-teams", cohortId],
    queryFn: () => getCohortTeamsApi(cohortId),
  })

  const [newTeamName, setNewTeamName] = useState("")
  const [isObserverTeam, setIsObserverTeam] = useState(false)
  const [teamFilter, setTeamFilter] = useState<"all" | "student" | "observer">("student")
  const createMutation = useMutation({
    mutationFn: () => createCohortTeamApi(cohortId, newTeamName.trim(), isObserverTeam),
    onSuccess: () => { setNewTeamName(""); setIsObserverTeam(false); invalidate() },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to create team")),
  })

  // Client-side (2026-09-16) — `teams` is already the whole cohort roster in
  // one fetch (getCohortTeamsApi has no search param), and member_names
  // rides along on every row already, so there's nothing to round-trip to
  // the server for.
  const [search, setSearch] = useState("")
  const filteredTeams = teams.filter((team) => {
    if (teamFilter === "student" && team.is_observer) return false
    if (teamFilter === "observer" && !team.is_observer) return false
    const q = search.trim().toLowerCase()
    if (!q) return true
    return team.name.toLowerCase().includes(q) || team.member_names.some((n) => n.toLowerCase().includes(q))
  })

  // Derived here rather than fetched (2026-09-16): `teams` is already the
  // whole cohort roster, so the counts ops asked for on this tab cost
  // nothing. A student on two teams in one cohort shouldn't be counted
  // twice — not DB-enforced (see models/team.py), so dedupe rather than
  // summing member_ids.length.
  const studentsOnTeams = new Set(teams.flatMap((t) => t.member_ids)).size
  const emptyTeams = teams.filter((t) => t.member_ids.length === 0).length

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-4 max-w-3xl">
      <p className="text-sm text-muted-foreground">
        For one-off corrections after a Roster import — a late signup, a team split, someone switching
        teams — without re-uploading a whole sheet. Adding a member by name + email registers them if
        they're new, or matches an existing account if that email already has one — same as a Roster row.
      </p>

      {teams.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <TeamStatChip label={teams.length === 1 ? "team" : "teams"} value={teams.length} />
          <TeamStatChip label="students on teams" value={studentsOnTeams} />
          <TeamStatChip label="avg team size" value={(studentsOnTeams / teams.length).toFixed(1)} />
          {emptyTeams > 0 && <TeamStatChip label="with no members" value={emptyTeams} tone="alert" />}
        </div>
      )}

      <div className="flex flex-col gap-2 p-3.5 bg-card border border-border rounded-xl">
        <div className="flex items-end gap-2 flex-wrap">
          <Field label="New team name">
            <input
              value={newTeamName} onChange={(e) => setNewTeamName(e.target.value)} placeholder="Falcon Eye"
              className="w-64 h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
            />
          </Field>
          <button
            onClick={() => createMutation.mutate()}
            disabled={createMutation.isPending || !newTeamName.trim()}
            className="flex items-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50 cursor-pointer"
          >
            <Plus size={14} /> Add team
          </button>
        </div>
        <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer select-none">
          <input
            type="checkbox"
            checked={isObserverTeam}
            onChange={(e) => setIsObserverTeam(e.target.checked)}
            className="accent-primary"
          />
          Create as observer sandbox team (testing & rehearsal only)
        </label>
      </div>

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="relative max-w-sm flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by team or student name..."
            className="w-full h-10 pl-8 pr-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </div>

        <div className="flex items-center p-1 bg-muted/60 border border-border/80 rounded-xl text-xs">
          <button
            type="button"
            onClick={() => setTeamFilter("all")}
            className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
              teamFilter === "all" ? "bg-background text-foreground shadow-xs font-semibold" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            All ({teams.length})
          </button>
          <button
            type="button"
            onClick={() => setTeamFilter("student")}
            className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
              teamFilter === "student" ? "bg-background text-foreground shadow-xs font-semibold" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Students ({teams.filter((t) => !t.is_observer).length})
          </button>
          <button
            type="button"
            onClick={() => setTeamFilter("observer")}
            className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
              teamFilter === "observer" ? "bg-background text-indigo-600 dark:text-indigo-400 shadow-xs font-semibold" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Observers ({teams.filter((t) => t.is_observer).length})
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        {filteredTeams.map((team) => (
          <TeamCard key={team.id} team={team} cohortId={cohortId} onChanged={invalidate} />
        ))}
        {teams.length === 0 ? (
          <EmptyState title="No teams yet" hint="Add one above, or import a roster from the Roster tab." />
        ) : filteredTeams.length === 0 && (
          <EmptyState title="No teams found" hint="Try a different name." />
        )}
      </div>
    </div>
  )
}

function TeamCard({ team, cohortId, onChanged }: { team: CompetitionTeam; cohortId: string; onChanged: () => void }) {
  const toast = useToast()
  const [renaming, setRenaming] = useState(false)
  const [name, setName] = useState(team.name)
  const [adding, setAdding] = useState(false)
  const [addMode, setAddMode] = useState<"pick" | "new">("pick")
  const [studentSearch, setStudentSearch] = useState("")
  const [memberName, setMemberName] = useState("")
  const [memberEmail, setMemberEmail] = useState("")
  const [memberSendWelcomeEmail, setMemberSendWelcomeEmail] = useState(true)
  const [memberSendTicketEmail, setMemberSendTicketEmail] = useState(true)
  const [profileUserId, setProfileUserId] = useState<string | null>(null)

  const isObserverTeam = !!team.is_observer
  const memberMode = isObserverTeam ? "observer" : "student"

  const { data: assignablePage, isLoading: isSearchingStudents } = useQuery({
    queryKey: ["competitions-assignable-students-team", cohortId, studentSearch, memberMode],
    queryFn: () => searchAssignableStudentsApi(cohortId, {
      q: studentSearch.trim() || undefined,
      mode: memberMode,
      page_size: 50,
    }),
    enabled: adding && addMode === "pick",
  })

  const existingMemberIds = new Set(team.member_ids)
  const candidateStudents = (assignablePage?.items ?? []).filter((s) => !existingMemberIds.has(s.id))

  const addExistingMemberMutation = useMutation({
    mutationFn: (userId: string) => addExistingTeamMemberApi(team.id, userId),
    onSuccess: () => {
      setStudentSearch("")
      setAdding(false)
      onChanged()
      toast.success(isObserverTeam ? "Observer added to team" : "Team member added")
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to add member")),
  })

  const renameMutation = useMutation({
    mutationFn: () => renameTeamApi(team.id, name.trim()),
    onSuccess: () => { setRenaming(false); onChanged() },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to rename team")),
  })
  const deleteMutation = useMutation({
    mutationFn: () => deleteTeamApi(team.id),
    onSuccess: onChanged,
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to delete team")),
  })
  const addMemberMutation = useMutation({
    mutationFn: () => registerAndAddTeamMemberApi(team.id, {
      full_name: memberName.trim(), email: memberEmail.trim(),
      send_welcome_email: memberSendWelcomeEmail, send_ticket_email: memberSendTicketEmail,
    }),
    onSuccess: () => {
      setMemberName(""); setMemberEmail(""); setAdding(false)
      setMemberSendWelcomeEmail(true); setMemberSendTicketEmail(true)
      onChanged()
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to add member")),
  })
  const removeMemberMutation = useMutation({
    mutationFn: (userId: string) => removeTeamMemberApi(team.id, userId),
    onSuccess: onChanged,
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to remove member")),
  })
  const resetObserverTeamMutation = useMutation({
    mutationFn: () => resetObserverTeamApi(team.id),
    onSuccess: () => {
      onChanged()
      toast.success("Observer team deliverables, scores, and lock reset")
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to reset observer team")),
  })

  return (
    <div className="p-4 bg-card border border-border rounded-2xl flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        {renaming ? (
          <div className="flex items-center gap-2 flex-1">
            <input
              value={name} onChange={(e) => setName(e.target.value)} autoFocus
              className="flex-1 h-9 px-3 border border-border bg-card text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
            />
            <button
              onClick={() => renameMutation.mutate()} disabled={renameMutation.isPending || !name.trim()}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"
            >
              <Check size={14} />
            </button>
            <button
              onClick={() => { setRenaming(false); setName(team.name) }}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
            >
              <X size={14} />
            </button>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <p className="text-sm font-semibold text-foreground">{team.name}</p>
              {team.is_observer && (
                <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border border-indigo-500/30">
                  Observer
                </span>
              )}
            </div>
            <div className="flex items-center gap-1">
              {team.is_observer && (
                <button
                  onClick={() => {
                    if (confirm(`Reset deliverables, scores, and unlock observer team "${team.name}"?`)) {
                      resetObserverTeamMutation.mutate()
                    }
                  }}
                  disabled={resetObserverTeamMutation.isPending}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-amber-500 hover:bg-amber-500/10 transition-colors cursor-pointer"
                  title="Reset observer deliverables & scores"
                >
                  <RotateCcw size={14} className={resetObserverTeamMutation.isPending ? "animate-spin" : ""} />
                </button>
              )}
              <button
                onClick={() => setRenaming(true)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"
                title="Rename"
              >
                <Pencil size={14} />
              </button>
              <button
                onClick={() => { if (confirm(`Delete team "${team.name}"?`)) deleteMutation.mutate() }}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors cursor-pointer"
                title="Delete team"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        {team.member_names.map((memberFullName, i) => (
          <div key={team.member_ids[i]} className="flex items-center justify-between text-sm">
            <div>
              <button
                onClick={() => setProfileUserId(team.member_ids[i])}
                className="text-foreground hover:text-primary hover:underline transition-colors cursor-pointer"
              >
                {memberFullName}
              </button>
              <span className="text-muted-foreground text-xs ml-2">{team.member_emails[i]}</span>
            </div>
            <button
              onClick={() => { if (confirm(`Remove ${memberFullName} from ${team.name}?`)) removeMemberMutation.mutate(team.member_ids[i]) }}
              className="p-1 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors cursor-pointer"
              title="Remove from team"
            >
              <UserMinus size={13} />
            </button>
          </div>
        ))}
        {team.member_names.length === 0 && <p className="text-xs text-muted-foreground">No members yet.</p>}
      </div>

      {adding ? (
        <div className="flex flex-col gap-3 pt-2 border-t border-border/50">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center p-0.5 bg-muted/60 border border-border/80 rounded-lg text-xs">
              <button
                type="button"
                onClick={() => setAddMode("pick")}
                className={`px-2.5 py-1 rounded-md font-medium transition-colors cursor-pointer ${
                  addMode === "pick" ? "bg-background text-foreground shadow-xs font-semibold" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {isObserverTeam ? "Pick from observers" : "Pick from students"}
              </button>
              <button
                type="button"
                onClick={() => setAddMode("new")}
                className={`px-2.5 py-1 rounded-md font-medium transition-colors cursor-pointer ${
                  addMode === "new" ? "bg-background text-foreground shadow-xs font-semibold" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {isObserverTeam ? "New observer" : "New student"}
              </button>
            </div>

            <button
              type="button"
              onClick={() => { setAdding(false); setStudentSearch("") }}
              className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
              title="Cancel"
            >
              <X size={14} />
            </button>
          </div>

          {addMode === "pick" ? (
            <div className="flex flex-col gap-2">
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input
                  value={studentSearch}
                  onChange={(e) => setStudentSearch(e.target.value)}
                  placeholder={isObserverTeam ? "Search observers by name or email…" : "Search students by name or email…"}
                  className="w-full h-9 pl-8 pr-3 border border-border bg-background text-foreground rounded-lg text-sm focus:outline-none focus:border-primary transition-colors"
                  autoFocus
                />
              </div>

              {isSearchingStudents ? (
                <div className="p-3 text-center text-xs text-muted-foreground">
                  {isObserverTeam ? "Searching observers…" : "Searching students…"}
                </div>
              ) : candidateStudents.length === 0 ? (
                <div className="p-3 text-center text-xs text-muted-foreground bg-muted/30 rounded-lg border border-border/50">
                  {studentSearch
                    ? (isObserverTeam ? "No matching observers found." : "No matching students found.")
                    : (isObserverTeam ? "No available observers to add." : "No available students to add.")}
                </div>
              ) : (
                <div className="flex flex-col gap-1 max-h-48 overflow-y-auto border border-border rounded-xl p-1 bg-background/50">
                  {candidateStudents.slice(0, 30).map((s) => (
                    <div
                      key={s.id}
                      className="flex items-center justify-between p-2 rounded-lg hover:bg-muted/70 transition-colors gap-2 text-xs"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="font-medium text-foreground">{s.full_name}</span>
                          {s.is_observer && (
                            <span className="text-[9px] font-bold uppercase tracking-wider px-1 py-0.5 rounded bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border border-indigo-500/30">
                              Observer
                            </span>
                          )}
                          {s.team_name && (
                            <span className="text-[10px] text-muted-foreground">
                              (in {s.team_name})
                            </span>
                          )}
                        </div>
                        <p className="text-muted-foreground truncate text-[11px]">{s.email}</p>
                      </div>

                      <button
                        type="button"
                        onClick={() => addExistingMemberMutation.mutate(s.id)}
                        disabled={addExistingMemberMutation.isPending}
                        className="h-7 px-2.5 bg-primary text-primary-foreground rounded-md text-xs font-medium hover:opacity-90 transition-colors disabled:opacity-50 shrink-0 cursor-pointer"
                      >
                        {addExistingMemberMutation.isPending ? "Adding…" : "Add"}
                      </button>
                    </div>
                  ))}
                  {candidateStudents.length > 30 && (
                    <p className="text-[11px] text-center text-muted-foreground py-1">
                      Showing first 30 matches — type to narrow search
                    </p>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <div className="flex items-end gap-2 flex-wrap">
                <Field label="Name">
                  <input
                    value={memberName} onChange={(e) => setMemberName(e.target.value)}
                    className="w-40 h-9 px-2 border border-border bg-card text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
                  />
                </Field>
                <Field label="Email">
                  <input
                    value={memberEmail} onChange={(e) => setMemberEmail(e.target.value)} type="email"
                    className="w-56 h-9 px-2 border border-border bg-card text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
                  />
                </Field>
                <button
                  onClick={() => addMemberMutation.mutate()}
                  disabled={addMemberMutation.isPending || !memberName.trim() || !memberEmail.trim()}
                  className="h-9 px-3 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {addMemberMutation.isPending ? "Adding…" : "Add"}
                </button>
              </div>
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer select-none">
                  <input
                    type="checkbox" checked={memberSendWelcomeEmail}
                    onChange={(e) => setMemberSendWelcomeEmail(e.target.checked)}
                  />
                  Send LMS onboarding mail
                </label>
                <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer select-none">
                  <input
                    type="checkbox" checked={memberSendTicketEmail}
                    onChange={(e) => setMemberSendTicketEmail(e.target.checked)}
                  />
                  Send Ticket
                </label>
              </div>
            </div>
          )}
        </div>
      ) : (
        <button
          onClick={() => { setAdding(true); setAddMode("pick") }}
          className="self-start flex items-center gap-1.5 text-xs font-medium text-primary hover:opacity-80 pt-1 border-t border-border/50 w-full justify-start cursor-pointer"
        >
          <UserPlus size={13} /> {isObserverTeam ? "Add observer" : "Add member"}
        </button>
      )}
      {profileUserId && (
        <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />
      )}
    </div>
  )
}

/* ================================================================== */
/* Rubric                                                               */
/* ================================================================== */
export function RubricTab({ cohortId }: { cohortId: string }) {
  const toast = useToast()
  const { data: rubric, isLoading } = useQuery<CompetitionRubric | null>({
    queryKey: ["competitions-rubric", cohortId],
    queryFn: () => getCohortRubricApi(cohortId).catch((e) => {
      if (e?.response?.status === 404) return null
      throw e
    }),
  })

  interface RubricSubForm { key: string; label: string; max_points: number }
  interface RubricCriterionForm {
    key: string; label: string; max_points: number
    scored_by: "judge" | "operations"; sub_criteria: RubricSubForm[]
  }

  const [name, setName] = useState("")
  const [criteria, setCriteria] = useState<RubricCriterionForm[]>([])
  // Which criteria are expanded to show their sub-criteria editor.
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  useEffect(() => {
    setName(rubric?.name ?? "Competition Rubric")
    setCriteria(
      rubric?.criteria.map((c) => ({
        key: c.key,
        label: c.label,
        max_points: c.max_points,
        scored_by: c.scored_by === "operations" ? "operations" : "judge",
        sub_criteria: (c.sub_criteria ?? []).map((s) => ({
          key: s.key, label: s.label, max_points: s.max_points,
        })),
      })) ?? [],
    )
    setExpanded(new Set())
  }, [rubric])

  const queryClient = useQueryClient()
  const saveMutation = useMutation({
    mutationFn: () => putCohortRubricApi(cohortId, {
      name,
      criteria: criteria.map((c) => ({
        key: c.key.trim(),
        label: c.label.trim(),
        max_points: Number(c.max_points) || 0,
        scored_by: c.scored_by,
        sub_criteria: c.sub_criteria.map((s) => ({
          key: s.key.trim(), label: s.label.trim(), max_points: Number(s.max_points) || 0,
        })),
      })),
    }),
    onSuccess: () => {
      toast.success("Rubric saved for this cohort")
      queryClient.invalidateQueries({ queryKey: ["competitions-rubric", cohortId] })
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to save rubric")),
  })

  if (isLoading) return <Spinner />

  const total = criteria.reduce((sum, c) => sum + (Number(c.max_points) || 0), 0)
  const judgeTotal = criteria
    .filter((c) => c.scored_by === "judge")
    .reduce((sum, c) => sum + (Number(c.max_points) || 0), 0)
  const operationsTotal = total - judgeTotal
  const subSum = (c: RubricCriterionForm) =>
    c.sub_criteria.reduce((sum, s) => sum + (Number(s.max_points) || 0), 0)
  const subKeys = (c: RubricCriterionForm, skip?: number) => {
    const keys = c.sub_criteria.map((s) => s.key.trim()).filter(Boolean)
    if (skip !== undefined) keys.splice(skip, 1)
    return keys
  }
  const criterionInvalid = (c: RubricCriterionForm) => {
    if (!c.key.trim() || !c.label.trim()) return true
    if (c.sub_criteria.length > 0) {
      if (subSum(c) !== (Number(c.max_points) || 0)) return true
      if (c.sub_criteria.some((s) => !s.key.trim() || !s.label.trim())) return true
      const keys = c.sub_criteria.map((s) => s.key.trim()).filter(Boolean)
      if (new Set(keys).size !== keys.length) return true
    }
    return false
  }
  const anyInvalid = criteria.some(criterionInvalid)

  const toggleExpanded = (i: number) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  }

  return (
    <div className="flex flex-col gap-4 max-w-2xl">
      <Field label="Rubric name">
        <input
          value={name} onChange={(e) => setName(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
        />
      </Field>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
            Criteria · Judge {judgeTotal} pts · Operations {operationsTotal} pts · Total {total} pts
          </label>
          <button
            onClick={() => setCriteria((c) => [...c, { key: `criterion_${c.length + 1}`, label: "", max_points: 10, scored_by: "judge", sub_criteria: [] }])}
            className="flex items-center gap-1 text-xs font-medium text-primary hover:opacity-80"
          >
            <Plus size={12} /> Add criterion
          </button>
        </div>
        {criteria.map((c, i) => {
          const isOperations = c.scored_by === "operations"
          const hasSubs = c.sub_criteria.length > 0
          const sum = subSum(c)
          const sumMismatch = hasSubs && sum !== (Number(c.max_points) || 0)
          return (
            <div key={i} className={`border rounded-xl overflow-hidden ${isOperations ? "border-foreground/25 bg-foreground/[0.04]" : "border-border bg-card"}`}>
              <div className="flex flex-wrap items-center gap-2 p-2">
                <input
                  value={c.key} placeholder="key"
                  onChange={(e) => setCriteria((cs) => cs.map((x, j) => j === i ? { ...x, key: e.target.value } : x))}
                  className="w-28 shrink-0 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-xs font-mono focus:outline-none focus:border-primary"
                />
                <input
                  value={c.label} placeholder="Label"
                  onChange={(e) => setCriteria((cs) => cs.map((x, j) => j === i ? { ...x, label: e.target.value } : x))}
                  className="flex-1 min-w-[140px] h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
                />
                <input
                  value={c.max_points} type="number" min={0}
                  onChange={(e) => setCriteria((cs) => cs.map((x, j) => j === i ? { ...x, max_points: Number(e.target.value) } : x))}
                  className="w-20 shrink-0 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
                />
                {/* Grader toggle — who scores this criterion. Sub-criteria always inherit it. */}
                <div className="flex rounded-lg border border-border overflow-hidden shrink-0" title="Who grades this criterion">
                  {(["judge", "operations"] as const).map((g) => (
                    <button
                      key={g}
                      type="button"
                      onClick={() => setCriteria((cs) => cs.map((x, j) => j === i ? { ...x, scored_by: g } : x))}
                      className={`h-9 px-2.5 text-xs font-medium transition-colors ${
                        c.scored_by === g
                          ? g === "operations"
                            ? "bg-foreground text-background"
                            : "bg-primary text-primary-foreground"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {g === "judge" ? "Judge" : "Operations"}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => toggleExpanded(i)}
                  title={hasSubs ? "Edit sub-criteria" : "Add sub-criteria"}
                  className={`h-9 px-2 rounded-lg text-xs font-medium border transition-colors ${
                    hasSubs ? "border-primary/40 text-primary" : "border-border text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {hasSubs ? `Subs (${c.sub_criteria.length})` : "+ Subs"}
                </button>
                <button
                  onClick={() => setCriteria((cs) => cs.filter((_, j) => j !== i))}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
                >
                  <Trash2 size={14} />
                </button>
              </div>

              {expanded.has(i) && (
                <div className="px-3 pb-3 pt-1 flex flex-col gap-1.5 border-t border-border/50">
                  {sumMismatch && (
                    <p className="text-[11px] text-red-600 dark:text-red-400 font-medium pt-1.5">
                      Sub-points must sum to {c.max_points}.
                    </p>
                  )}
                  {c.sub_criteria.map((s, si) => {
                    const dup = s.key.trim() && subKeys(c, si).includes(s.key.trim())
                    return (
                      <div key={si} className="flex flex-wrap items-center gap-2 pl-4">
                        <span className="text-muted-foreground text-xs w-4 shrink-0">↳</span>
                        <input
                          value={s.key} placeholder="key"
                          onChange={(e) => setCriteria((cs) => cs.map((x, j) =>
                            j === i ? { ...x, sub_criteria: x.sub_criteria.map((y, k) => k === si ? { ...y, key: e.target.value } : y) } : x))}
                          className={`w-28 shrink-0 h-8 px-2 border bg-background text-foreground rounded-lg text-xs font-mono focus:outline-none focus:border-primary ${
                            dup ? "border-red-400 dark:border-red-700" : "border-border"
                          }`}
                        />
                        <input
                          value={s.label} placeholder="Label"
                          onChange={(e) => setCriteria((cs) => cs.map((x, j) =>
                            j === i ? { ...x, sub_criteria: x.sub_criteria.map((y, k) => k === si ? { ...y, label: e.target.value } : y) } : x))}
                          className="flex-1 min-w-[140px] h-8 px-2 border border-border bg-background text-foreground rounded-lg text-xs focus:outline-none focus:border-primary"
                        />
                        <input
                          value={s.max_points} type="number" min={0}
                          onChange={(e) => setCriteria((cs) => cs.map((x, j) =>
                            j === i ? { ...x, sub_criteria: x.sub_criteria.map((y, k) => k === si ? { ...y, max_points: Number(e.target.value) } : y) } : x))}
                          className="w-20 shrink-0 h-8 px-2 border border-border bg-background text-foreground rounded-lg text-xs focus:outline-none focus:border-primary"
                        />
                        <button
                          onClick={() => setCriteria((cs) => cs.map((x, j) =>
                            j === i ? { ...x, sub_criteria: x.sub_criteria.filter((_, k) => k !== si) } : x))}
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    )
                  })}
                  <button
                    onClick={() => setCriteria((cs) => cs.map((x, j) =>
                      j === i ? { ...x, sub_criteria: [...x.sub_criteria, { key: `sub_${x.sub_criteria.length + 1}`, label: "", max_points: 5 }] } : x))}
                    className="self-start flex items-center gap-1 text-xs font-medium text-primary hover:opacity-80 pl-8"
                  >
                    <Plus size={12} /> Add sub-criterion
                  </button>
                </div>
              )}
            </div>
          )
        })}
        {criteria.length === 0 && (
          <p className="text-xs text-muted-foreground">No criteria yet — add at least one before judges can score.</p>
        )}
      </div>

      <button
        onClick={() => saveMutation.mutate()}
        disabled={saveMutation.isPending || anyInvalid}
        title={anyInvalid ? "Fix highlighted criteria first (empty fields, duplicate sub-keys, or sub-points not summing to the parent max)" : undefined}
        className="self-start h-10 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
      >
        {saveMutation.isPending ? "Saving…" : "Save rubric"}
      </button>
    </div>
  )
}

/* ================================================================== */
/* Judges                                                               */
/* ================================================================== */
export function JudgesTab({ cohortId }: { cohortId: string }) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const { data: judges = [], isLoading } = useQuery<CompetitionJudgeProgress[]>({
    queryKey: ["competitions-judges", cohortId],
    queryFn: () => getCohortJudgesApi(cohortId),
  })

  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [sendJudgeEmail, setSendJudgeEmail] = useState(true)
  const [staffQuery, setStaffQuery] = useState("")
  const { data: staffOptions = [] } = useQuery<StaffOption[]>({
    queryKey: ["staff-search-for-judge", staffQuery],
    queryFn: () => searchStaffApi({ q: staffQuery.trim() }),
    enabled: staffQuery.trim().length >= 2,
  })
  const alreadyJudging = new Set(judges.map((j) => j.email))

  const inviteMutation = useMutation({
    mutationFn: () => inviteCohortJudgeApi(cohortId, {
      name: name.trim(), email: email.trim(), send_email: sendJudgeEmail,
    }),
    onSuccess: () => {
      toast.success("Judge added")
      setName(""); setEmail(""); setStaffQuery(""); setSendJudgeEmail(true)
      queryClient.invalidateQueries({ queryKey: ["competitions-judges", cohortId] })
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to add judge")),
  })
  const revokeMutation = useMutation({
    mutationFn: (userId: string) => revokeCohortJudgeApi(cohortId, userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["competitions-judges", cohortId] }),
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to remove judge")),
  })
  const resendOnboardingMutation = useMutation({
    mutationFn: (userId: string) => resendJudgeOnboardingEmailApi(cohortId, userId),
    onSuccess: (res) => {
      if (res.sent) {
        toast.success("Onboarding email sent")
        queryClient.invalidateQueries({ queryKey: ["competitions-judges", cohortId] })
      } else {
        toast.error("Send failed — check SMTP")
      }
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to send onboarding email")),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6 max-w-2xl lg:max-w-none lg:grid lg:grid-cols-2 lg:items-start">
      <div className="rounded-2xl border border-border bg-card p-4 sm:p-5 flex flex-col gap-4 min-w-0">
        <h3 className="text-sm font-bold text-foreground">Add a Judge</h3>

        <div className="flex flex-col gap-2">
          <Field label="Add an existing staff account">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                value={staffQuery} onChange={(e) => setStaffQuery(e.target.value)}
                placeholder="Search staff by name or email…"
                className="w-full h-10 pl-9 pr-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </div>
          </Field>
          {staffQuery.trim().length >= 2 && (
            <div className="flex flex-col gap-1 border border-border rounded-xl p-1.5 bg-background max-h-56 overflow-y-auto">
              {staffOptions.length === 0 ? (
                <p className="text-xs text-muted-foreground px-2 py-1.5">No matching staff account.</p>
              ) : (
                staffOptions.map((u) => {
                  const already = alreadyJudging.has(u.email)
                  return (
                    <button
                      key={u.id}
                      type="button"
                      disabled={already}
                      onClick={() => { setName(u.full_name); setEmail(u.email); setStaffQuery("") }}
                      className="flex items-center justify-between text-left px-2.5 py-2 rounded-lg text-sm hover:bg-muted transition-colors disabled:opacity-40 disabled:cursor-not-allowed gap-2 cursor-pointer"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-foreground font-medium truncate text-sm">{u.full_name}</p>
                        <p className="text-muted-foreground text-xs truncate">{u.email}</p>
                      </div>
                      {already && <span className="text-xs text-muted-foreground shrink-0 font-medium">Already judging</span>}
                    </button>
                  )
                })
              )}
            </div>
          )}
        </div>

        <div className="relative flex items-center my-0.5">
          <div className="flex-grow border-t border-border" />
          <span className="flex-shrink mx-3 text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">
            or add someone new
          </span>
          <div className="flex-grow border-t border-border" />
        </div>

        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Name">
              <input
                value={name} onChange={(e) => setName(e.target.value)} placeholder="Dr. Amina Al Suwaidi"
                className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </Field>
            <Field label="Email">
              <input
                value={email} onChange={(e) => setEmail(e.target.value)} placeholder="amina@example.com" type="email"
                className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </Field>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
            <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
              <input
                type="checkbox"
                checked={sendJudgeEmail}
                onChange={(e) => setSendJudgeEmail(e.target.checked)}
                className="rounded border-border"
              />
              <span>Send onboarding invite email</span>
            </label>

            <button
              type="button"
              onClick={() => inviteMutation.mutate()}
              disabled={inviteMutation.isPending || !name.trim() || !email.trim()}
              className="w-full sm:w-auto flex items-center justify-center gap-1.5 h-10 px-5 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50 cursor-pointer shrink-0"
            >
              <UserPlus size={15} /> {inviteMutation.isPending ? "Adding…" : "Add as judge"}
            </button>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-3 min-w-0">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-foreground">
            Assigned Judges {judges.length > 0 && `(${judges.length})`}
          </h3>
        </div>

        {judges.length === 0 ? (
          <EmptyState title="No judges yet" hint="Invite a judge above to get started." />
        ) : (
          <div className="flex flex-col gap-2">
            {judges.map((j) => (
              <div
                key={j.user_id}
                className="flex flex-col sm:flex-row sm:items-center justify-between p-3.5 bg-card border border-border rounded-2xl gap-3 hover:border-border/80 transition-all"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-semibold text-foreground truncate">{j.full_name}</p>
                    {j.onboarding_sent ? (
                      <span className="text-[10px] sm:text-xs font-semibold px-2 py-0.5 rounded-full bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-400">
                        Onboarding sent
                      </span>
                    ) : (
                      <span className="text-[10px] sm:text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
                        No onboarding email
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground truncate mt-0.5">{j.email}</p>
                </div>

                <div className="flex items-center justify-between sm:justify-end gap-3 shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-border/40">
                  <span className="text-xs font-medium text-muted-foreground tabular-nums">
                    {j.scored_count} / {j.team_count} teams scored
                  </span>

                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => resendOnboardingMutation.mutate(j.user_id)}
                      disabled={resendOnboardingMutation.isPending}
                      className="p-2 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors disabled:opacity-50 cursor-pointer"
                      title={j.onboarding_sent ? "Resend onboarding email" : "Send onboarding email"}
                      aria-label="Send onboarding email"
                    >
                      <Mail size={15} />
                    </button>
                    <button
                      type="button"
                      onClick={() => { if (confirm(`Remove ${j.full_name} from this cohort's judges?`)) revokeMutation.mutate(j.user_id) }}
                      className="p-2 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors cursor-pointer"
                      title="Remove judge"
                      aria-label="Remove judge"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/* ================================================================== */
/* Results                                                              */
/* ================================================================== */
function ResultsTab({
  cohortId,
  cohortName,
  programId,
  onOpenCertificates,
}: {
  cohortId: string
  cohortName: string
  programId: string
  onOpenCertificates?: () => void
}) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [showTop20, setShowTop20] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [toCohortId, setToCohortId] = useState("")
  const [sendTicketOnAdvance, setSendTicketOnAdvance] = useState(true)
  const [sendWelcomeOnAdvance, setSendWelcomeOnAdvance] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [downloadingCertificates, setDownloadingCertificates] = useState(false)

  const { data: programTemplates = [] } = useQuery<ProgramCertificateTemplate[]>({
    queryKey: ["program-certificate-templates", programId],
    queryFn: () => listProgramCertificateTemplatesApi(programId),
    enabled: !!programId,
  })

  const handleDownloadCertificates = async (
    filter: CertificateFilterMode,
    theme: "dark" | "light" | "custom",
    templateId?: string,
    templateName?: string,
  ) => {
    setDownloadingCertificates(true)
    try {
      await downloadCompetitionCertificatesApi(
        cohortId,
        cohortName,
        filter,
        theme,
        null,
        templateId,
      )
      const filterLabel =
        filter === "locked_only"
          ? "locked only (completion)"
          : filter === "participation"
          ? "participation"
          : filter === "at_least_one"
          ? "≥ 1 submission"
          : "completed all"
      toast.success(
        `Downloaded ${templateName || theme} certificates for ${filterLabel}`,
      )
    } catch (e: unknown) {
      toast.error(getErrorMessage(e, "Failed to download certificates PDF"))
    } finally {
      setDownloadingCertificates(false)
    }
  }

  const [mode, setMode] = useState<"participant" | "observer" | "all">("participant")
  const { data: board = [], isLoading } = useQuery<CompetitionLeaderboardRow[]>({
    queryKey: ["competitions-leaderboard", cohortId, mode],
    queryFn: () => getCohortLeaderboardApi(cohortId, mode),
  })
  const { data: top20 = [] } = useQuery<CompetitionLeaderboardRow[]>({
    queryKey: ["competitions-top20", cohortId],
    queryFn: () => getCohortExportTop20Api(cohortId),
    enabled: showTop20,
  })
  const { data: siblingCohorts = [] } = useQuery<Cohort[]>({
    queryKey: ["sessions-cohorts", programId],
    queryFn: () => getCohortsApi(programId),
  })
  const advanceTargets = siblingCohorts.filter((c) => c.id !== cohortId)

  const { data: publication } = useQuery<CompetitionPublication>({
    queryKey: ["competitions-publication", cohortId],
    queryFn: () => getCohortPublicationApi(cohortId),
  })
  const isPublished = publication?.published ?? false

  const invalidatePublication = () => {
    queryClient.invalidateQueries({ queryKey: ["competitions-publication", cohortId] })
    queryClient.invalidateQueries({ queryKey: ["competitions-leaderboard", cohortId] })
  }
  const unpublishMutation = useMutation({
    mutationFn: () => unpublishCohortResultsApi(cohortId),
    onSuccess: () => { toast.success("Results unpublished — judges can score again"); invalidatePublication() },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to unpublish results")),
  })
  const advanceMutation = useMutation({
    mutationFn: () => advanceCohortTeamsApi(cohortId, {
      team_ids: [...selected], to_cohort_id: toCohortId,
      send_ticket_email: sendTicketOnAdvance, send_welcome_email: sendWelcomeOnAdvance,
    }),
    onSuccess: (results) => {
      const targetName = advanceTargets.find((c) => c.id === toCohortId)?.name ?? "the next stage"
      toast.success(`Advanced ${results.length} team(s) to ${targetName}`)
      setSelected(new Set())
      setSendTicketOnAdvance(true)
      setSendWelcomeOnAdvance(true)
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to advance teams")),
  })

  const [windowsModalOpen, setWindowsModalOpen] = useState(false)
  const [breakdownTeamId, setBreakdownTeamId] = useState<string | null>(null)
  const [overrideTeam, setOverrideTeam] = useState<CompetitionLeaderboardRow | null>(null)
  const [gradingTeam, setGradingTeam] = useState<CompetitionLeaderboardRow | null>(null)
  const [publishModalOpen, setPublishModalOpen] = useState(false)
  const [publishModalMode, setPublishModalMode] = useState<"publish" | "edit">("publish")

  // Rubric for the operations grading modal (which criteria are
  // operations-graded and whether they have sub-criteria).
  const { data: rubric = null } = useQuery<CompetitionRubric | null>({
    queryKey: ["competitions-rubric", cohortId],
    queryFn: () => getCohortRubricApi(cohortId).catch((e: any) => {
      if (e?.response?.status === 404) return null
      throw e
    }),
    enabled: !!cohortId,
  })

  if (isLoading) return <Spinner />

  const toggleTeam = (teamId: string) => {
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(teamId)) next.delete(teamId); else next.add(teamId)
      return next
    })
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3 flex-wrap">
        <span
          className={`flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full ${
            isPublished ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
          }`}
        >
          <Trophy size={12} />
          {isPublished
            ? `Published${publication?.published_at ? ` · ${new Date(publication.published_at).toLocaleDateString()}` : ""}`
            : "Not published"}
        </span>
        {isPublished ? (
          <>
            <button
              onClick={() => {
                setPublishModalMode("edit")
                setPublishModalOpen(true)
              }}
              className="flex items-center gap-1.5 h-9 px-3.5 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
              title="Edit which results, scores, and comments are visible to students"
            >
              <Eye size={14} className="text-primary" /> Edit visibility
            </button>
            <button
              onClick={() => {
                if (confirm("Are you sure you want to unpublish these results? Scoring will be reopened.")) {
                  unpublishMutation.mutate()
                }
              }}
              disabled={unpublishMutation.isPending}
              className="h-9 px-3.5 border border-border rounded-xl text-sm font-medium text-muted-foreground hover:text-red-600 hover:border-red-300 dark:hover:border-red-800 transition-colors disabled:opacity-50 cursor-pointer"
            >
              {unpublishMutation.isPending ? "Unpublishing…" : "Unpublish"}
            </button>
          </>
        ) : (
          <button
            onClick={() => {
              setPublishModalMode("publish")
              setPublishModalOpen(true)
            }}
            className="h-9 px-4 rounded-xl text-sm font-medium transition-colors bg-primary text-primary-foreground hover:opacity-90 cursor-pointer"
          >
            Publish results
          </button>
        )}
        <div className="flex items-center p-1 bg-muted/60 border border-border/80 rounded-xl text-xs">
          <button
            type="button"
            onClick={() => setMode("participant")}
            className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
              mode === "participant" ? "bg-background text-foreground shadow-xs font-semibold" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Students
          </button>
          <button
            type="button"
            onClick={() => setMode("observer")}
            className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
              mode === "observer" ? "bg-background text-indigo-600 dark:text-indigo-400 shadow-xs font-semibold" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Observers
          </button>
          <button
            type="button"
            onClick={() => setMode("all")}
            className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
              mode === "all" ? "bg-background text-foreground shadow-xs font-semibold" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            All
          </button>
        </div>
        <button
          onClick={() => setShowTop20((s) => !s)}
          title="Filters the table below to only the 20 highest-ranked teams — doesn't download anything"
          className="h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
        >
          {showTop20 ? "Show all teams" : "Filter to Top 20"}
        </button>
        <button
          onClick={() => setWindowsModalOpen(true)}
          title="Configure tiered submission deadlines and timing incentives"
          className="flex items-center gap-1.5 h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
        >
          <Clock size={14} className="text-primary" /> Submission Windows
        </button>
        <button
          onClick={async () => {
            setExporting(true)
            try {
              await downloadCohortResultsWorkbookApi(cohortId, cohortName)
            } catch (e: any) {
              toast.error(getErrorMessage(e, "Failed to export results"))
            } finally {
              setExporting(false)
            }
          }}
          disabled={exporting}
          className="flex items-center gap-1.5 h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
        >
          <Download size={14} /> {exporting ? "Exporting…" : "Export spreadsheet"}
        </button>
        {onOpenCertificates && (
          <button
            onClick={onOpenCertificates}
            className="flex items-center gap-1.5 h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
            title="Review qualifying students and email certificates"
          >
            <Mail size={14} className="text-primary" /> Send certificates
          </button>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              disabled={downloadingCertificates}
              className="flex items-center gap-1.5 h-9 px-3 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
              title="Download merged PDF of certificates for students with submissions"
            >
              <Printer size={14} /> {downloadingCertificates ? "Preparing…" : "Print certificates"}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64 max-h-96 overflow-y-auto">
            <div className="px-2 py-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">
              Locked only (Completion)
            </div>
            <DropdownMenuItem onClick={() => handleDownloadCertificates("locked_only", "dark")}>
              Dark background
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => handleDownloadCertificates("locked_only", "light")}>
              Light background
            </DropdownMenuItem>
            {programTemplates.map((tmpl: ProgramCertificateTemplate) => (
              <DropdownMenuItem
                key={`locked-only-${tmpl.id}`}
                onClick={() => handleDownloadCertificates("locked_only", "custom", tmpl.id, tmpl.name)}
                className="truncate"
              >
                {tmpl.name}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <div className="px-2 py-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Participation (≥ 1 submission)
            </div>
            <DropdownMenuItem onClick={() => handleDownloadCertificates("participation", "dark")}>
              Dark background
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => handleDownloadCertificates("participation", "light")}>
              Light background
            </DropdownMenuItem>
            {programTemplates.map((tmpl: ProgramCertificateTemplate) => (
              <DropdownMenuItem
                key={`participation-${tmpl.id}`}
                onClick={() => handleDownloadCertificates("participation", "custom", tmpl.id, tmpl.name)}
                className="truncate"
              >
                {tmpl.name}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <div className="px-2 py-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Completed all submissions
            </div>
            <DropdownMenuItem onClick={() => handleDownloadCertificates("all_completed", "dark")}>
              Dark background
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => handleDownloadCertificates("all_completed", "light")}>
              Light background
            </DropdownMenuItem>
            {programTemplates.map((tmpl: ProgramCertificateTemplate) => (
              <DropdownMenuItem
                key={`all-completed-${tmpl.id}`}
                onClick={() => handleDownloadCertificates("all_completed", "custom", tmpl.id, tmpl.name)}
                className="truncate"
              >
                {tmpl.name}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <p className="text-xs text-muted-foreground -mt-2">
        Publishing closes scoring for every judge on this cohort — unpublish to reopen it. "Export spreadsheet"
        downloads an .xlsx with every team's score breakdown and submission links, for reviewing outside the app.
      </p>

      {advanceTargets.length > 0 ? (
        <div className="flex items-center gap-2 p-3 bg-card border border-border rounded-xl flex-wrap">
          <span className="text-sm text-foreground font-medium">
            {selected.size > 0 ? `${selected.size} team(s) selected` : "Select teams below to advance"}
          </span>
          <select
            value={toCohortId} onChange={(e) => setToCohortId(e.target.value)}
            className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary cursor-pointer"
          >
            <option value="">Advance to…</option>
            {advanceTargets.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
            <input
              type="checkbox" checked={sendWelcomeOnAdvance}
              onChange={(e) => setSendWelcomeOnAdvance(e.target.checked)}
            />
            Send LMS onboarding mail
          </label>
          <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
            <input
              type="checkbox" checked={sendTicketOnAdvance}
              onChange={(e) => setSendTicketOnAdvance(e.target.checked)}
            />
            Send Ticket
          </label>
          <button
            onClick={() => advanceMutation.mutate()}
            disabled={advanceMutation.isPending || selected.size === 0 || !toCohortId}
            className="h-9 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
          >
            {advanceMutation.isPending ? "Advancing…" : "Advance selected teams"}
          </button>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground p-3 bg-card border border-dashed border-border rounded-xl">
          No other cohort exists yet under this program to advance teams into — create one (e.g. a Finalist
          stage) on the Cohorts page first, and this control appears here.
        </p>
      )}

      <LeaderboardTable
        rows={showTop20 ? top20 : board}
        selected={selected}
        onToggle={toggleTeam}
        onInspectTeam={(teamId) => setBreakdownTeamId(teamId)}
        onEditTiming={(team) => setOverrideTeam(team)}
        hasOperationsCriteria={(rubric?.criteria ?? []).some((c) => (c.scored_by ?? "judge") === "operations")}
        onGradeOperations={(team) => setGradingTeam(team)}
      />

      <SubmissionWindowsModal
        cohortId={cohortId}
        open={windowsModalOpen}
        onClose={() => setWindowsModalOpen(false)}
      />

      <TeamScoreBreakdownModal
        cohortId={cohortId}
        teamId={breakdownTeamId}
        open={!!breakdownTeamId}
        onClose={() => setBreakdownTeamId(null)}
      />

      <TimingOverrideModal
        cohortId={cohortId}
        team={overrideTeam}
        open={!!overrideTeam}
        onClose={() => setOverrideTeam(null)}
      />

      <TeamOperationsScoreModal
        cohortId={cohortId}
        team={gradingTeam}
        rubric={rubric}
        open={!!gradingTeam}
        onClose={() => setGradingTeam(null)}
      />

      <PublishResultsModal
        cohortId={cohortId}
        open={publishModalOpen}
        onClose={() => setPublishModalOpen(false)}
        isPublished={publishModalMode === "edit"}
        currentSettings={publication?.visibility_settings}
      />
    </div>
  )
}

function LeaderboardTable({
  rows,
  selected,
  onToggle,
  onInspectTeam,
  onEditTiming,
  hasOperationsCriteria,
  onGradeOperations,
}: {
  rows: CompetitionLeaderboardRow[]
  selected?: Set<string>
  onToggle?: (teamId: string) => void
  onInspectTeam?: (teamId: string) => void
  onEditTiming?: (team: CompetitionLeaderboardRow) => void
  hasOperationsCriteria?: boolean
  onGradeOperations?: (team: CompetitionLeaderboardRow) => void
}) {
  if (rows.length === 0) return <EmptyState title="No teams yet" hint="Teams appear here once they're formed for this cohort." />
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted-foreground uppercase tracking-wider border-b border-border">
            {onToggle && <th className="py-2 pr-3 w-8" />}
            <th className="py-2 pr-3">Rank</th>
            <th className="py-2 pr-3">Team</th>
            <th className="py-2 pr-3">Final Score</th>
            <th className="py-2 pr-3">Rubric Score</th>
            <th className="py-2 pr-3">Operations</th>
            <th className="py-2 pr-3">Timing Adj.</th>
            <th className="py-2 pr-3">Per Judge</th>
            <th className="py-2 pr-3 text-right">Inspection</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.team_id} className="border-b border-border/50 hover:bg-muted/15 transition-colors">
              {onToggle && (
                <td className="py-2 pr-3 align-top">
                  <input
                    type="checkbox" checked={selected?.has(r.team_id) ?? false}
                    onChange={() => onToggle(r.team_id)}
                  />
                </td>
              )}
              <td className="py-2 pr-3 font-semibold tabular-nums align-top">{r.rank}</td>
              <td className="py-2 pr-3 text-foreground align-top">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="font-medium">{r.team_name}</span>
                  {r.is_observer && (
                    <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border border-indigo-500/30">
                      Observer
                    </span>
                  )}
                  {r.qualification && (
                    <span
                      className={`inline-flex items-center text-[10px] font-semibold uppercase tracking-wide rounded-full px-2 py-0.5 whitespace-nowrap border ${
                        r.qualification.toLowerCase().includes("top 10")
                          ? "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30"
                          : r.qualification.toLowerCase().includes("top")
                          ? "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/30"
                          : "bg-muted text-muted-foreground border-border"
                      }`}
                    >
                      {r.qualification}
                    </span>
                  )}
                  {r.advanced_to && (
                    <span
                      title={`Advanced to ${r.advanced_to}`}
                      className="inline-flex items-center gap-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 rounded-full px-1.5 py-0.5 whitespace-nowrap"
                    >
                      <ArrowUpRight size={10} /> Advanced
                    </span>
                  )}
                </div>
              </td>
              {/* Final Score */}
              <td className="py-2 pr-3 tabular-nums align-top">
                <div className="flex flex-col">
                  <span className="font-bold text-foreground">{r.score ?? "—"}</span>
                  {r.score_percent !== null && r.score_percent !== undefined && (
                    <span className="text-xs text-muted-foreground font-normal">{r.score_percent}%</span>
                  )}
                </div>
              </td>
              {/* Rubric Score (pure judge average) */}
              <td className="py-2 pr-3 tabular-nums align-top text-muted-foreground">
                <span>{r.raw_judge_score !== null && r.raw_judge_score !== undefined ? r.raw_judge_score : (r.score ?? "—")}</span>
              </td>
              {/* Operations Score & Feedback (clickable to grade or leave feedback) */}
              <td className="py-2 pr-3 align-top">
                {hasOperationsCriteria ? (
                  <button
                    type="button"
                    onClick={() => onGradeOperations?.(r)}
                    title="Grade operations criteria and leave feedback"
                    className="inline-flex items-center gap-1.5 text-xs font-semibold px-2 py-0.5 rounded-full border border-foreground/25 bg-foreground/[0.06] text-foreground transition-transform hover:scale-105 cursor-pointer tabular-nums"
                  >
                    <span>
                      {r.ops_score !== null && r.ops_score !== undefined
                        ? `${r.ops_score}${r.ops_max_points ? ` / ${r.ops_max_points}` : ""}`
                        : "Grade"}
                    </span>
                    {r.ops_criterion_notes ? (
                      <span title={r.ops_criterion_notes} className="inline-flex items-center text-primary">
                        <MessageSquare size={10} />
                      </span>
                    ) : (
                      <Pencil size={10} className="opacity-70" />
                    )}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => onGradeOperations?.(r)}
                    title={r.ops_criterion_notes ? `Feedback: ${r.ops_criterion_notes}` : "Add operations comments for this team"}
                    className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border transition-transform hover:scale-105 cursor-pointer ${
                      r.ops_criterion_notes
                        ? "bg-primary/10 text-primary border-primary/30 font-semibold"
                        : "text-muted-foreground hover:text-foreground border-dashed border-border hover:border-primary/40"
                    }`}
                  >
                    {r.ops_criterion_notes ? (
                      <>
                        <MessageSquare size={10} />
                        <span>Commented</span>
                        <Pencil size={9} className="opacity-70 ml-0.5" />
                      </>
                    ) : (
                      <>
                        <Plus size={10} />
                        <span>Add note</span>
                      </>
                    )}
                  </button>
                )}
              </td>
              {/* Timing Adjustment (clickable to override) */}
              <td className="py-2 pr-3 align-top">
                <button
                  type="button"
                  onClick={() => onEditTiming?.(r)}
                  title="Click to manually override or inspect timing points"
                  className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full border transition-transform hover:scale-105 cursor-pointer ${
                    (r.timing_adjustment ?? 0) > 0
                      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                      : (r.timing_adjustment ?? 0) < 0
                      ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                      : "bg-muted text-muted-foreground border-border"
                  }`}
                >
                  <span>
                    {(r.timing_adjustment ?? 0) > 0 ? `+${r.timing_adjustment}` : (r.timing_adjustment ?? 0)}
                  </span>
                  {r.is_timing_override && (
                    <span className="text-[9px] bg-purple-500/20 text-purple-300 px-1 rounded uppercase font-bold">
                      Override
                    </span>
                  )}
                  <Pencil size={10} className="text-muted-foreground hover:text-foreground ml-0.5" />
                </button>
              </td>
              {/* Per Judge chips (clicking opens breakdown) */}
              <td className="py-2 pr-3 align-top">
                {r.judge_scores.length === 0 ? (
                  <span className="text-muted-foreground text-xs">Not scored yet</span>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {r.judge_scores.map((js) => (
                      <button
                        type="button"
                        key={js.judge_user_id}
                        onClick={() => onInspectTeam?.(r.team_id)}
                        title={`Click to inspect ${js.judge_name}'s rubric breakdown and comments`}
                        className="inline-flex items-center gap-1 text-xs bg-muted/60 hover:bg-primary/20 hover:border-primary/40 border border-transparent rounded-full px-2 py-0.5 whitespace-nowrap transition-colors cursor-pointer"
                      >
                        <span className="text-muted-foreground">{js.judge_name}</span>
                        <span className="font-semibold tabular-nums text-foreground">{js.total_points}</span>
                      </button>
                    ))}
                  </div>
                )}
              </td>
              {/* Inspection button */}
              <td className="py-2 pr-3 text-right align-top">
                <button
                  type="button"
                  onClick={() => onInspectTeam?.(r.team_id)}
                  title="Inspect criteria breakdown and judge comments"
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                >
                  <Eye size={12} className="text-primary" />
                  <span>Breakdown</span>
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
