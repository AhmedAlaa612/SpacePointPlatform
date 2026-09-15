import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "@tanstack/react-router"
import { ArrowLeft, ArrowUpRight, Download, Mail, Plus, Search, Trash2, Trophy, Upload, UserPlus, UserMinus, Pencil, X, Check } from "lucide-react"
import { getCohortApi, getCohortsApi } from "@/api/sessions/cohorts"
import type { Cohort } from "@/types/sessions"
import { searchStaffApi, listInviteCodesApi, type StaffOption } from "@/api/lms_admin"
import { UserProfileModal } from "@/components/UserProfileModal"
import {
  advanceCohortTeamsApi, assignExistingStudentsApi, createCohortTeamApi, deleteTeamApi, downloadCohortResultsWorkbookApi,
  getCohortExportTop20Api,
  confirmCohortRegistrationImportApi,
  getCohortJudgesApi, getCohortLeaderboardApi, getCohortPublicationApi, getCohortTeamsApi, getProgramRubricApi,
  previewCohortRegistrationImportApi, searchAssignableStudentsApi,
  inviteCohortJudgeApi, publishCohortResultsApi, putProgramRubricApi, registerAndAddTeamMemberApi,
  removeTeamMemberApi, renameTeamApi, resendJudgeOnboardingEmailApi, revokeCohortJudgeApi, unpublishCohortResultsApi,
  type CompetitionAssignStudentsResult, type CompetitionImportPreviewRow, type CompetitionImportResult,
  type CompetitionJudgeProgress,
  type CompetitionLeaderboardRow, type CompetitionPublication, type CompetitionRubric, type CompetitionTeam,
} from "@/api/competitions"
import { PageHeader, Spinner, EmptyState } from "@/components/ui/primitives"
import { Field } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

type JudgingTab = "roster" | "assign" | "teams" | "rubric" | "judges" | "results"
const TABS: { key: JudgingTab; label: string }[] = [
  { key: "roster", label: "Roster" },
  { key: "assign", label: "Assign" },
  { key: "teams", label: "Teams" },
  { key: "rubric", label: "Rubric" },
  { key: "judges", label: "Judges" },
  { key: "results", label: "Results" },
]

export default function CompetitionJudging() {
  const { cohortId } = useParams({ strict: false }) as { cohortId: string }
  const [tab, setTab] = useState<JudgingTab>("roster")

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

      <PageHeader title={`Judging — ${cohort.name}`} subtitle={cohort.program_name ?? "—"} />

      <div className="flex gap-1 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
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
      {tab === "rubric" && <RubricTab programId={cohort.program_id} />}
      {tab === "judges" && <JudgesTab cohortId={cohort.id} />}
      {tab === "results" && <ResultsTab cohortId={cohort.id} cohortName={cohort.name} programId={cohort.program_id} />}
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
type LmsStatusFilter = "all" | "has_access" | "no_access"

function AssignTab({ cohortId }: { cohortId: string }) {
  const toast = useToast()
  const [query, setQuery] = useState("")
  const [inviteCode, setInviteCode] = useState("")
  // Unchecked by default (2026-09-15, flipped from the original "on" —
  // ops kept landing here first and having to untick it to find anyone not
  // already registered, since the platform-wide search underneath it just
  // became reliable now that a selected batch isn't silently capped, see
  // students.py::search_cohort_assignable_students). teamStatus still
  // defaults to "no team yet" — that's the actual "my roster to still
  // process" narrowing this tab is built around.
  const [registeredOnly, setRegisteredOnly] = useState(false)
  const [teamStatus, setTeamStatus] = useState<TeamStatusFilter>("no_team")
  const [lmsStatus, setLmsStatus] = useState<LmsStatusFilter>("all")
  const [teamIds, setTeamIds] = useState<Record<string, string>>({})
  const [sendWelcomeEmail, setSendWelcomeEmail] = useState(true)
  const [sendTicketEmail, setSendTicketEmail] = useState(true)
  const [result, setResult] = useState<CompetitionAssignStudentsResult | null>(null)

  const { data: students = [], isLoading } = useQuery({
    queryKey: ["competitions-assignable-students", cohortId, query, inviteCode, registeredOnly, teamStatus, lmsStatus],
    queryFn: () => searchAssignableStudentsApi(cohortId, {
      q: query || undefined, invite_code: inviteCode || undefined, registered_only: registeredOnly,
      team_status: teamStatus, lms_status: lmsStatus,
    }),
  })
  const { data: codes = [] } = useQuery({
    queryKey: ["lms-admin-invite-codes"],
    queryFn: listInviteCodesApi,
  })

  const assignMutation = useMutation({
    mutationFn: (rows: { user_id: string; team_id: string }[]) =>
      assignExistingStudentsApi(cohortId, rows, { send_welcome_email: sendWelcomeEmail, send_ticket_email: sendTicketEmail }),
    onSuccess: (res) => {
      setResult(res)
      setTeamIds({})
      toast.success(`Assigned: ${res.summary.created} newly registered, ${res.summary.matched} already registered, ${res.summary.error} errors`)
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to assign students")),
  })

  const rowsToSubmit = Object.entries(teamIds)
    .filter(([, teamId]) => teamId.trim())
    .map(([userId, teamId]) => ({ user_id: userId, team_id: teamId.trim() }))

  return (
    // Wider than the other tabs' max-w-2xl/3xl/4xl (2026-09-15) — this is
    // the one tab with a 6-column table (name/email/code/team/LMS/team ID
    // input), and 4xl was clipping the Team ID column on an ordinary desktop
    // viewport despite the table's own overflow-x-auto, since that scrolls
    // the table *within* an already-too-narrow container instead of the
    // container just using the room the page actually has.
    <div className="flex flex-col gap-4 max-w-6xl">
      <p className="text-sm text-muted-foreground max-w-4xl">
        Find students who already signed up with an invite code, type in a Team ID for each, and assign them —
        this registers them into this cohort and puts them on that team (creating it if it's new). Students set
        their own team's display name later; a Team ID here is just the grouping code, not a name.
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative max-w-md flex-1 min-w-[220px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name or email..."
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
          value={lmsStatus}
          onChange={(e) => setLmsStatus(e.target.value as LmsStatusFilter)}
          className="w-auto shrink-0 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="all">Any LMS access</option>
          <option value="no_access">No LMS access</option>
          <option value="has_access">Has LMS access</option>
        </select>
      </div>

      {isLoading ? (
        <Spinner />
      ) : students.length === 0 ? (
        <EmptyState
          title="No students found"
          hint={
            registeredOnly
              ? "Nobody registered to this cohort matches these filters — untick \"Registered to this cohort\" to search everyone."
              : query || inviteCode ? "Try a different search or batch." : "No student accounts exist yet."
          }
        />
      ) : (
        <div className="overflow-x-auto border border-border rounded-xl">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground uppercase tracking-wider border-b border-border">
                <th className="py-2 pl-3 pr-2">Name</th>
                <th className="py-2 pr-2">Email</th>
                <th className="py-2 pr-2">Code used</th>
                <th className="py-2 pr-2">Current team</th>
                <th className="py-2 pr-2">LMS access</th>
                <th className="py-2 pr-3">Team ID</th>
              </tr>
            </thead>
            <tbody>
              {students.map((s) => (
                <tr key={s.id} className="border-b border-border/50">
                  <td className="py-1.5 pl-3 pr-2 align-top pt-3 font-medium text-foreground whitespace-nowrap">{s.full_name}</td>
                  <td className="py-1.5 pr-2 align-top pt-3 text-muted-foreground whitespace-nowrap">{s.email}</td>
                  <td className="py-1.5 pr-2 align-top pt-3 text-muted-foreground whitespace-nowrap">
                    {s.invite_code ? (s.invite_label ?? s.invite_code) : "—"}
                  </td>
                  <td className="py-1.5 pr-2 align-top pt-3 whitespace-nowrap">
                    {s.team_name ? (
                      <span className="text-xs font-semibold text-primary">{s.team_name}</span>
                    ) : (
                      <span className="text-muted-foreground">Not assigned</span>
                    )}
                  </td>
                  <td className="py-1.5 pr-2 align-top pt-3 whitespace-nowrap">
                    {s.lms_access ? (
                      <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">Yes</span>
                    ) : (
                      <span className="text-muted-foreground">No</span>
                    )}
                  </td>
                  <td className="py-1.5 pr-3">
                    <input
                      value={teamIds[s.id] ?? ""}
                      onChange={(e) => setTeamIds((prev) => ({ ...prev, [s.id]: e.target.value }))}
                      placeholder="e.g. T1"
                      className="w-32 h-8 px-2 rounded-lg border border-border bg-background text-sm"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {rowsToSubmit.length > 0 && (
        <>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
              <input type="checkbox" checked={sendWelcomeEmail} onChange={(e) => setSendWelcomeEmail(e.target.checked)} />
              Send LMS onboarding mail
            </label>
            <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
              <input type="checkbox" checked={sendTicketEmail} onChange={(e) => setSendTicketEmail(e.target.checked)} />
              Send Ticket
            </label>
          </div>
          <button
            onClick={() => assignMutation.mutate(rowsToSubmit)}
            disabled={assignMutation.isPending}
            className="self-start flex items-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
          >
            <Check size={14} /> {assignMutation.isPending ? "Assigning…" : `Assign & register (${rowsToSubmit.length})`}
          </button>
        </>
      )}

      {result && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-foreground">
              {result.summary.total} rows · {result.summary.created} newly registered · {result.summary.matched} already registered ·{" "}
              {result.summary.error} errors
            </p>
            <button
              onClick={() => setResult(null)}
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Dismiss
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground uppercase tracking-wider border-b border-border">
                  <th className="py-2 pr-3">Team ID</th>
                  <th className="py-2 pr-3">Team</th>
                  <th className="py-2 pr-3">Result</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={r.row_number} className="border-b border-border/50">
                    <td className="py-2 pr-3">{r.team_id ?? "—"}</td>
                    <td className="py-2 pr-3">{r.team_name ?? "—"}</td>
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
/* Teams (manual management — complements Roster import)               */
/* ================================================================== */
function TeamsTab({ cohortId }: { cohortId: string }) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["competitions-teams", cohortId] })

  const { data: teams = [], isLoading } = useQuery<CompetitionTeam[]>({
    queryKey: ["competitions-teams", cohortId],
    queryFn: () => getCohortTeamsApi(cohortId),
  })

  const [newTeamName, setNewTeamName] = useState("")
  const createMutation = useMutation({
    mutationFn: () => createCohortTeamApi(cohortId, newTeamName.trim()),
    onSuccess: () => { setNewTeamName(""); invalidate() },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to create team")),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-4 max-w-3xl">
      <p className="text-sm text-muted-foreground">
        For one-off corrections after a Roster import — a late signup, a team split, someone switching
        teams — without re-uploading a whole sheet. Adding a member by name + email registers them if
        they're new, or matches an existing account if that email already has one — same as a Roster row.
      </p>

      <div className="flex items-end gap-2">
        <Field label="New team name">
          <input
            value={newTeamName} onChange={(e) => setNewTeamName(e.target.value)} placeholder="Falcon Eye"
            className="w-64 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
          />
        </Field>
        <button
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending || !newTeamName.trim()}
          className="flex items-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
        >
          <Plus size={14} /> Add team
        </button>
      </div>

      <div className="flex flex-col gap-3">
        {teams.map((team) => (
          <TeamCard key={team.id} team={team} onChanged={invalidate} />
        ))}
        {teams.length === 0 && (
          <EmptyState title="No teams yet" hint="Add one above, or import a roster from the Roster tab." />
        )}
      </div>
    </div>
  )
}

function TeamCard({ team, onChanged }: { team: CompetitionTeam; onChanged: () => void }) {
  const toast = useToast()
  const [renaming, setRenaming] = useState(false)
  const [name, setName] = useState(team.name)
  const [adding, setAdding] = useState(false)
  const [memberName, setMemberName] = useState("")
  const [memberEmail, setMemberEmail] = useState("")
  const [memberSendWelcomeEmail, setMemberSendWelcomeEmail] = useState(true)
  const [memberSendTicketEmail, setMemberSendTicketEmail] = useState(true)
  const [profileUserId, setProfileUserId] = useState<string | null>(null)

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
              className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
            >
              <Check size={14} />
            </button>
            <button
              onClick={() => { setRenaming(false); setName(team.name) }}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <X size={14} />
            </button>
          </div>
        ) : (
          <>
            <p className="text-sm font-semibold text-foreground">{team.name}</p>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setRenaming(true)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                title="Rename"
              >
                <Pencil size={14} />
              </button>
              <button
                onClick={() => { if (confirm(`Delete team "${team.name}"?`)) deleteMutation.mutate() }}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
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
                className="text-foreground hover:text-primary hover:underline transition-colors"
              >
                {memberFullName}
              </button>
              <span className="text-muted-foreground text-xs ml-2">{team.member_emails[i]}</span>
            </div>
            <button
              onClick={() => { if (confirm(`Remove ${memberFullName} from ${team.name}?`)) removeMemberMutation.mutate(team.member_ids[i]) }}
              className="p-1 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
              title="Remove from team"
            >
              <UserMinus size={13} />
            </button>
          </div>
        ))}
        {team.member_names.length === 0 && <p className="text-xs text-muted-foreground">No members yet.</p>}
      </div>

      {adding ? (
        <div className="flex flex-col gap-2 pt-1 border-t border-border/50">
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
              className="h-9 px-3 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
            >
              {addMemberMutation.isPending ? "Adding…" : "Add"}
            </button>
            <button
              onClick={() => setAdding(false)}
              className="h-9 px-3 border border-border rounded-lg text-sm font-medium text-foreground hover:bg-muted transition-colors"
            >
              Cancel
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
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="self-start flex items-center gap-1.5 text-xs font-medium text-primary hover:opacity-80 pt-1 border-t border-border/50 w-full justify-start"
        >
          <UserPlus size={13} /> Add member
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
function RubricTab({ programId }: { programId: string }) {
  const toast = useToast()
  const { data: rubric, isLoading } = useQuery<CompetitionRubric | null>({
    queryKey: ["competitions-rubric", programId],
    queryFn: () => getProgramRubricApi(programId).catch((e) => {
      if (e?.response?.status === 404) return null
      throw e
    }),
  })

  const [name, setName] = useState("")
  const [criteria, setCriteria] = useState<{ key: string; label: string; max_points: number }[]>([])

  useEffect(() => {
    setName(rubric?.name ?? "Competition Rubric")
    setCriteria(
      rubric?.criteria.map((c) => ({ key: c.key, label: c.label, max_points: c.max_points })) ?? [],
    )
  }, [rubric])

  const queryClient = useQueryClient()
  const saveMutation = useMutation({
    mutationFn: () => putProgramRubricApi(programId, { name, criteria }),
    onSuccess: () => {
      toast.success("Rubric saved")
      queryClient.invalidateQueries({ queryKey: ["competitions-rubric", programId] })
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to save rubric")),
  })

  if (isLoading) return <Spinner />

  const total = criteria.reduce((sum, c) => sum + (Number(c.max_points) || 0), 0)

  return (
    <div className="flex flex-col gap-4 max-w-2xl">
      <Field label="Rubric name">
        <input
          value={name} onChange={(e) => setName(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
        />
      </Field>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
            Criteria · {total} pts total
          </label>
          <button
            onClick={() => setCriteria((c) => [...c, { key: `criterion_${c.length + 1}`, label: "", max_points: 10 }])}
            className="flex items-center gap-1 text-xs font-medium text-primary hover:opacity-80"
          >
            <Plus size={12} /> Add criterion
          </button>
        </div>
        {criteria.map((c, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              value={c.key} placeholder="key"
              onChange={(e) => setCriteria((cs) => cs.map((x, j) => j === i ? { ...x, key: e.target.value } : x))}
              className="w-32 h-9 px-2 border border-border bg-card text-foreground rounded-lg text-xs font-mono focus:outline-none focus:border-primary"
            />
            <input
              value={c.label} placeholder="Label"
              onChange={(e) => setCriteria((cs) => cs.map((x, j) => j === i ? { ...x, label: e.target.value } : x))}
              className="flex-1 h-9 px-2 border border-border bg-card text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
            />
            <input
              value={c.max_points} type="number" min={0}
              onChange={(e) => setCriteria((cs) => cs.map((x, j) => j === i ? { ...x, max_points: Number(e.target.value) } : x))}
              className="w-20 h-9 px-2 border border-border bg-card text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
            />
            <button
              onClick={() => setCriteria((cs) => cs.filter((_, j) => j !== i))}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        {criteria.length === 0 && (
          <p className="text-xs text-muted-foreground">No criteria yet — add at least one before judges can score.</p>
        )}
      </div>

      <button
        onClick={() => saveMutation.mutate()}
        disabled={saveMutation.isPending || criteria.some((c) => !c.key.trim() || !c.label.trim())}
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
function JudgesTab({ cohortId }: { cohortId: string }) {
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
    <div className="flex flex-col gap-5 max-w-2xl">
      <div className="flex flex-col gap-2">
        <Field label="Add an existing account as judge">
          <input
            value={staffQuery} onChange={(e) => setStaffQuery(e.target.value)}
            placeholder="Search staff by name or email…"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
          />
        </Field>
        {staffQuery.trim().length >= 2 && (
          <div className="flex flex-col gap-1 border border-border rounded-xl p-1.5 bg-card max-h-56 overflow-y-auto">
            {staffOptions.length === 0 ? (
              <p className="text-xs text-muted-foreground px-2 py-1.5">No matching staff account.</p>
            ) : (
              staffOptions.map((u) => {
                const already = alreadyJudging.has(u.email)
                return (
                  <button
                    key={u.id}
                    disabled={already}
                    onClick={() => { setName(u.full_name); setEmail(u.email); setStaffQuery("") }}
                    className="flex items-center justify-between text-left px-2 py-1.5 rounded-lg text-sm hover:bg-muted transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <span>
                      <span className="text-foreground font-medium">{u.full_name}</span>
                      <span className="text-muted-foreground text-xs ml-2">{u.email}</span>
                    </span>
                    {already && <span className="text-xs text-muted-foreground shrink-0">Already judging</span>}
                  </button>
                )
              })
            )}
          </div>
        )}
      </div>

      <div className="flex items-end gap-2">
        <Field label={name || email ? "Name" : "…or add someone new — name"}>
          <input
            value={name} onChange={(e) => setName(e.target.value)} placeholder="Dr. Amina Al Suwaidi"
            className="w-48 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
          />
        </Field>
        <Field label="Email">
          <input
            value={email} onChange={(e) => setEmail(e.target.value)} placeholder="amina@example.com" type="email"
            className="w-64 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
          />
        </Field>
        <button
          onClick={() => inviteMutation.mutate()}
          disabled={inviteMutation.isPending || !name.trim() || !email.trim()}
          className="flex items-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
        >
          <UserPlus size={14} /> {inviteMutation.isPending ? "Adding…" : "Add as judge"}
        </button>
      </div>
      <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none -mt-3">
        <input type="checkbox" checked={sendJudgeEmail} onChange={(e) => setSendJudgeEmail(e.target.checked)} />
        Send email
      </label>

      <div className="flex flex-col gap-2">
        {judges.map((j) => (
          <div key={j.user_id} className="flex items-center justify-between p-3 bg-card border border-border rounded-xl">
            <div>
              <div className="flex items-center gap-1.5 flex-wrap">
                <p className="text-sm font-medium text-foreground">{j.full_name}</p>
                {j.onboarding_sent ? (
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-400">
                    Onboarding sent
                  </span>
                ) : (
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
                    No onboarding email
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground">{j.email}</p>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground">{j.scored_count} / {j.team_count} teams scored</span>
              <button
                onClick={() => resendOnboardingMutation.mutate(j.user_id)}
                disabled={resendOnboardingMutation.isPending}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                title={j.onboarding_sent ? "Resend onboarding email" : "Send onboarding email"}
              >
                <Mail size={14} />
              </button>
              <button
                onClick={() => { if (confirm(`Remove ${j.full_name} from this cohort's judges?`)) revokeMutation.mutate(j.user_id) }}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}
        {judges.length === 0 && <EmptyState title="No judges yet" hint="Invite a judge above to get started." />}
      </div>
    </div>
  )
}

/* ================================================================== */
/* Results                                                              */
/* ================================================================== */
function ResultsTab({ cohortId, cohortName, programId }: { cohortId: string; cohortName: string; programId: string }) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [showTop20, setShowTop20] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [toCohortId, setToCohortId] = useState("")
  const [sendTicketOnAdvance, setSendTicketOnAdvance] = useState(true)
  const [sendWelcomeOnAdvance, setSendWelcomeOnAdvance] = useState(true)
  const [exporting, setExporting] = useState(false)

  const { data: board = [], isLoading } = useQuery<CompetitionLeaderboardRow[]>({
    queryKey: ["competitions-leaderboard", cohortId],
    queryFn: () => getCohortLeaderboardApi(cohortId),
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
  const publishMutation = useMutation({
    mutationFn: () => publishCohortResultsApi(cohortId),
    onSuccess: () => { toast.success("Results published"); invalidatePublication() },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to publish results")),
  })
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
        <button
          onClick={() => (isPublished ? unpublishMutation.mutate() : publishMutation.mutate())}
          disabled={publishMutation.isPending || unpublishMutation.isPending}
          className={`h-9 px-4 rounded-xl text-sm font-medium transition-colors disabled:opacity-50 ${
            isPublished
              ? "border border-border text-foreground hover:bg-muted"
              : "bg-primary text-primary-foreground hover:opacity-90"
          }`}
        >
          {publishMutation.isPending || unpublishMutation.isPending
            ? "Working…"
            : isPublished ? "Unpublish" : "Publish results"}
        </button>
        <button
          onClick={() => setShowTop20((s) => !s)}
          title="Filters the table below to only the 20 highest-ranked teams — doesn't download anything"
          className="h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
        >
          {showTop20 ? "Show all teams" : "Filter to Top 20"}
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

      <LeaderboardTable rows={showTop20 ? top20 : board} selected={selected} onToggle={toggleTeam} />
    </div>
  )
}

function LeaderboardTable({ rows, selected, onToggle }: {
  rows: CompetitionLeaderboardRow[]; selected?: Set<string>; onToggle?: (teamId: string) => void
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
            <th className="py-2 pr-3">Avg. score</th>
            <th className="py-2 pr-3">Per judge</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.team_id} className="border-b border-border/50">
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
                <div className="flex items-center gap-1.5">
                  {r.team_name}
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
              <td className="py-2 pr-3 tabular-nums align-top">{r.score ?? "—"}</td>
              <td className="py-2 pr-3">
                {r.judge_scores.length === 0 ? (
                  <span className="text-muted-foreground">Not scored yet</span>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {r.judge_scores.map((js) => (
                      <span
                        key={js.judge_user_id}
                        className="inline-flex items-center gap-1 text-xs bg-muted/60 rounded-full px-2 py-0.5 whitespace-nowrap"
                      >
                        <span className="text-muted-foreground">{js.judge_name}</span>
                        <span className="font-semibold tabular-nums">{js.total_points}</span>
                      </span>
                    ))}
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
