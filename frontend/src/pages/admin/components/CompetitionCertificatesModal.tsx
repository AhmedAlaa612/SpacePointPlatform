import { useEffect, useMemo, useState } from "react"
import { createPortal } from "react-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertCircle,
  Check,
  Circle,
  Download,
  Loader2,
  Lock,
  Mail,
  Search,
  SendHorizonal,
  X,
} from "lucide-react"
import {
  type CompetitionCertificateRecipient,
  type CompetitionCertificateTeam,
  downloadCompetitionCertificatesApi,
  getCohortCertificateRecipientsApi,
  sendCohortCertificatesApi,
  sendTestCertificateEmailApi,
} from "@/api/competitions"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"
import { CertificateEmailTemplatesModal } from "@/pages/admin/components/CertificateEmailTemplatesModal"

interface CompetitionCertificatesModalProps {
  cohortId: string
  cohortName: string
  programName?: string
  open?: boolean
  onClose?: () => void
  embedded?: boolean
}

type ViewMode = "students" | "teams"

export function CompetitionCertificatesModal({
  cohortId,
  cohortName,
  programName,
  open = true,
  onClose = () => { },
  embedded = false,
}: CompetitionCertificatesModalProps) {
  const toast = useToast()
  const queryClient = useQueryClient()

  const [view, setView] = useState<ViewMode>("students")
  const [search, setSearch] = useState("")
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  const [primaryTemplateId, setPrimaryTemplateId] = useState<string>("dark")
  const [primaryEmailTemplateId, setPrimaryEmailTemplateId] = useState<string>("")
  const [deliveryMode, setDeliveryMode] = useState<"email" | "publish">("email")
  const [notifyByEmail, setNotifyByEmail] = useState(false)

  const [alsoSendOther, setAlsoSendOther] = useState(false)
  const [secondaryTemplateId, setSecondaryTemplateId] = useState<string>("dark")
  const willSendEmail = deliveryMode === "email" || notifyByEmail

  const [skipAlreadyIssued, setSkipAlreadyIssued] = useState(true)
  const [emailModalOpen, setEmailModalOpen] = useState(false)
  const [testEmailAddress, setTestEmailAddress] = useState("")
  const [showTestInput, setShowTestInput] = useState(false)

  const { data: summary, isLoading } = useQuery({
    queryKey: ["cohort-certificate-recipients", cohortId],
    queryFn: () => getCohortCertificateRecipientsApi(cohortId, "all"),
    enabled: open && !!cohortId,
  })

  const individualTemplates = useMemo(
    () => (summary?.templates ?? []).filter((t) => !t.kind || t.kind === "individual" || t.kind === "both"),
    [summary?.templates]
  )
  const teamTemplates = useMemo(
    () => (summary?.templates ?? []).filter((t) => t.kind === "team" || t.kind === "both"),
    [summary?.templates]
  )
  const emailTemplates = summary?.email_templates ?? []

  useEffect(() => {
    if (!summary) return
    const primaryList = view === "students" ? individualTemplates : teamTemplates
    const secondaryList = view === "students" ? teamTemplates : individualTemplates
    const primaryDef =
      (view === "students" ? summary.default_template_id : summary.default_team_template_id) ||
      primaryList.find((t) => t.is_default)?.id ||
      primaryList[0]?.id ||
      "dark"
    const secondaryDef =
      (view === "students" ? summary.default_team_template_id : summary.default_template_id) ||
      secondaryList.find((t) => t.is_default)?.id ||
      secondaryList[0]?.id ||
      "dark"
    setPrimaryTemplateId(primaryDef)
    setSecondaryTemplateId(secondaryDef)
  }, [summary, view, individualTemplates, teamTemplates])

  useEffect(() => {
    if (emailTemplates.length === 0) return
    const wantedPrimaryKind = deliveryMode === "publish" ? "profile" : view === "students" ? "individual" : "team"
    const pMatch =
      emailTemplates.find((e) => e.kind === wantedPrimaryKind && e.is_default) ||
      emailTemplates.find((e) => e.kind === wantedPrimaryKind) ||
      emailTemplates[0]
    if (pMatch) setPrimaryEmailTemplateId(pMatch.id)
  }, [emailTemplates, view, deliveryMode])

  const recipients = summary?.recipients ?? []
  const teams = summary?.teams ?? []

  const filteredStudents = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return recipients
    return recipients.filter(
      (r) =>
        r.student_name.toLowerCase().includes(q) ||
        (r.email ?? "").toLowerCase().includes(q) ||
        (r.team_name ?? "").toLowerCase().includes(q)
    )
  }, [recipients, search])

  const filteredTeams = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return teams
    return teams.filter((t) => t.team_name.toLowerCase().includes(q))
  }, [teams, search])

  const switchView = (next: ViewMode) => {
    setView(next)
    setSelectedIds(new Set())
    setAlsoSendOther(false)
  }

  const toggleRow = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const applyQuickSelect = (mode: string) => {
    const next = new Set<string>()
    if (view === "students") {
      for (const r of filteredStudents) {
        const reqDone = r.required_submissions_done ?? r.submissions_done
        const reqTotal = r.required_submissions_total
        const optDone = r.optional_submissions_done ?? 0
        const optTotal = r.optional_submissions_total ?? 0
        const issued = r.student_cert_issued ?? r.certificate_issued
        if (
          mode === "all" ||
          (mode === "mandatory" && reqTotal > 0 && reqDone >= reqTotal) ||
          (mode === "completed" && reqTotal > 0 && reqDone >= reqTotal && optDone >= optTotal) ||
          (mode === "one" && reqDone >= 1) ||
          (mode === "locked" && r.team_locked) ||
          (mode === "new" && !issued) ||
          (mode === "noteam" && !r.team_id)
        ) {
          next.add(r.registration_id)
        }
      }
    } else {
      for (const t of filteredTeams) {
        if (
          mode === "all" ||
          (mode === "mandatory" && t.required_submissions_total > 0 && t.required_submissions_done >= t.required_submissions_total) ||
          (mode === "completed" &&
            t.required_submissions_total > 0 &&
            t.required_submissions_done >= t.required_submissions_total &&
            t.optional_submissions_done >= t.optional_submissions_total) ||
          (mode === "one" && t.required_submissions_done >= 1) ||
          (mode === "locked" && t.team_locked) ||
          (mode === "ranked" && t.rank != null) ||
          (mode === "unranked" && t.rank == null) ||
          (mode === "new" && !t.team_cert_issued)
        ) {
          next.add(t.team_id)
        }
      }
    }
    setSelectedIds(next)
  }

  const sendMutation = useMutation({
    mutationFn: () => {
      const ids = Array.from(selectedIds)
      return sendCohortCertificatesApi(cohortId, {
        filter: "custom",
        registration_ids: view === "students" ? ids : undefined,
        team_ids: view === "teams" ? ids : undefined,
        primary_kind: view === "students" ? "individual" : "team",
        primary_template_id: primaryTemplateId,
        primary_email_template_id: primaryEmailTemplateId || null,
        also_send_other: alsoSendOther,
        secondary_template_id: alsoSendOther ? secondaryTemplateId : null,
        secondary_email_template_id: alsoSendOther ? (primaryEmailTemplateId || null) : null,
        delivery_mode: deliveryMode,
        notify_by_email: deliveryMode === "publish" ? notifyByEmail : true,
        skip_already_issued: skipAlreadyIssued,
      })
    },
    onSuccess: (res) => {
      if (res.status === "queued") {
        toast.success(`Sending certificates to ${res.total_targeted} recipients`)
      } else {
        toast.success(`Sent ${res.sent_count}, skipped ${res.skipped_count}`)
      }
      queryClient.invalidateQueries({ queryKey: ["cohort-certificate-recipients", cohortId] })
    },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Failed to send certificates")),
  })

  const downloadMutation = useMutation({
    mutationFn: async () => {
      const ids = Array.from(selectedIds)
      if (view === "students") {
        await downloadCompetitionCertificatesApi(
          cohortId,
          programName || cohortName,
          "all",
          "dark",
          ids.length > 0 ? ids : undefined,
          primaryTemplateId,
          null,
          "individual"
        )
      } else {
        const regIds = teams
          .filter((t) => ids.length === 0 || ids.includes(t.team_id))
          .flatMap((t) => t.registration_ids)
        await downloadCompetitionCertificatesApi(
          cohortId,
          programName || cohortName,
          "all",
          "dark",
          regIds.length > 0 ? regIds : undefined,
          primaryTemplateId,
          null,
          "team"
        )
      }
    },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Failed to download PDF")),
  })

  const testEmailMutation = useMutation({
    mutationFn: () => {
      if (!testEmailAddress.trim()) throw new Error("Enter an email address")
      return sendTestCertificateEmailApi(cohortId, {
        to_email: testEmailAddress.trim(),
        template_id: primaryTemplateId,
        kind: view === "students" ? "individual" : "team",
        email_template_id: primaryEmailTemplateId || null,
        delivery_mode: deliveryMode,
        notify_by_email: deliveryMode === "publish" ? notifyByEmail : true,
      })
    },
    onSuccess: (res) => {
      toast.success(`Test email sent to ${res.to}`)
      setShowTestInput(false)
    },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Failed to send test email")),
  })

  const unrankedSelected = useMemo(() => {
    if (view !== "teams") return false
    return teams.some((t) => selectedIds.has(t.team_id) && t.rank == null)
  }, [view, teams, selectedIds])

  const selectedTeamMemberCount = useMemo(() => {
    if (view !== "teams") return 0
    return teams.filter((t) => selectedIds.has(t.team_id)).reduce((acc, t) => acc + t.member_count, 0)
  }, [view, teams, selectedIds])

  if (!open) return null

  const primaryOptions = view === "students" ? individualTemplates : teamTemplates
  const secondaryOptions = view === "students" ? teamTemplates : individualTemplates

  const renderProgressChips = (
    reqDone: number,
    reqTotal: number,
    optDone: number,
    optTotal: number,
    locked: boolean
  ) => {
    const reqComplete = reqTotal > 0 && reqDone >= reqTotal
    const optComplete = optTotal > 0 && optDone >= optTotal
    return (
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span
          className={`px-2 py-0.5 rounded-[10px] border ${reqComplete ? "border-emerald-500/50 text-emerald-500" : "border-border text-foreground"
            }`}
        >
          Mandatory {reqDone}/{reqTotal}
        </span>
        {optTotal > 0 && (
          <span
            className={`px-2 py-0.5 rounded-[10px] border ${optComplete ? "border-emerald-500/50 text-emerald-500" : "border-border text-muted-foreground"
              }`}
          >
            Optional {optDone}/{optTotal}
          </span>
        )}
        {locked && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-[10px] border border-emerald-500/50 text-emerald-500">
            <Lock className="w-3 h-3" />
            <span>Locked</span>
          </span>
        )}
      </div>
    )
  }

  const renderStatus = (issued: boolean, dateStr?: string | null, na?: boolean) => {
    if (na) return <span className="text-xs text-muted-foreground">N/A</span>
    if (issued) {
      const formatted = dateStr
        ? new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric" })
        : "Issued"
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-500">
          <Check className="w-3.5 h-3.5" />
          <span>{formatted}</span>
        </span>
      )
    }
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
        <Circle className="w-3.5 h-3.5" />
        <span>Not issued</span>
      </span>
    )
  }

  const body = (
    <div className="space-y-4">
      <div className="bg-card border border-border rounded-[10px] p-4 space-y-3">
        <div className={`grid grid-cols-1 ${willSendEmail ? "md:grid-cols-2" : ""} gap-4`}>
          <label className="space-y-1.5">
            <span className="text-xs font-medium text-muted-foreground block">1. Certificate template</span>
            <select
              value={primaryTemplateId}
              onChange={(e) => setPrimaryTemplateId(e.target.value)}
              className="w-full h-9 px-3 rounded-[10px] border border-border bg-background text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              {primaryOptions.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>

          {willSendEmail && (
            <div className="space-y-1.5">
              <span className="text-xs font-medium text-muted-foreground block">2. Email template</span>
              <select
                value={primaryEmailTemplateId}
                onChange={(e) => setPrimaryEmailTemplateId(e.target.value)}
                className="w-full h-9 px-3 rounded-[10px] border border-border bg-background text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              >
                {emailTemplates.map((et) => (
                  <option key={et.id} value={et.id}>
                    {et.name}
                  </option>
                ))}
              </select>
              <div className="flex items-center gap-4 text-xs text-primary pt-0.5">
                <button type="button" onClick={() => setEmailModalOpen(true)} className="hover:underline">
                  Manage email templates
                </button>
                <button type="button" onClick={() => setShowTestInput((v) => !v)} className="hover:underline">
                  Send test
                </button>
              </div>
              {showTestInput && (
                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="email"
                    value={testEmailAddress}
                    onChange={(e) => setTestEmailAddress(e.target.value)}
                    placeholder="you@example.com"
                    className="flex-1 h-8 px-2.5 rounded-[10px] border border-border bg-background text-xs text-foreground"
                  />
                  <button
                    type="button"
                    onClick={() => testEmailMutation.mutate()}
                    disabled={testEmailMutation.isPending}
                    className="h-8 px-3 rounded-[10px] bg-primary text-primary-foreground text-xs font-medium disabled:opacity-50"
                  >
                    {testEmailMutation.isPending ? "Sending..." : "Send"}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-5 pt-2 border-t border-border text-sm">
          <span className="text-xs font-medium text-muted-foreground">3. Delivery</span>
          <label className="inline-flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name={`delivery-${cohortId}`}
              checked={deliveryMode === "email"}
              onChange={() => setDeliveryMode("email")}
              className="accent-primary"
            />
            <span>Email with PDF attached</span>
          </label>
          <label className="inline-flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name={`delivery-${cohortId}`}
              checked={deliveryMode === "publish"}
              onChange={() => setDeliveryMode("publish")}
              className="accent-primary"
            />
            <span>Publish to profile only</span>
          </label>
          {deliveryMode === "publish" && (
            <label className="inline-flex items-center gap-2 cursor-pointer pl-2 border-l border-border text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={notifyByEmail}
                onChange={(e) => setNotifyByEmail(e.target.checked)}
                className="accent-primary"
              />
              <span>Notify by email</span>
            </label>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-[10px] border border-border overflow-hidden text-sm">
          <button
            type="button"
            onClick={() => switchView("students")}
            className={`px-4 py-1.5 font-medium transition-colors ${view === "students" ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-muted/50"
              }`}
          >
            Students
          </button>
          <button
            type="button"
            onClick={() => switchView("teams")}
            className={`px-4 py-1.5 font-medium transition-colors ${view === "teams" ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-muted/50"
              }`}
          >
            Teams
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={view === "students" ? "Search students..." : "Search teams..."}
              className="h-8 pl-8 pr-3 rounded-[10px] border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <button
            type="button"
            onClick={() => downloadMutation.mutate()}
            disabled={downloadMutation.isPending}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] border border-border text-xs font-medium text-foreground hover:bg-muted/50 disabled:opacity-50"
          >
            <Download className="w-3.5 h-3.5" />
            <span>{downloadMutation.isPending ? "Preparing..." : "Download PDF"}</span>
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        {(view === "students"
          ? [
            { id: "all", label: "All" },
            { id: "mandatory", label: "Completed all mandatory" },
            { id: "completed", label: "Completed all" },
            { id: "one", label: "≥ 1 submission" },
            { id: "locked", label: "Locked" },
            { id: "new", label: "Not issued yet" },
            { id: "noteam", label: "No team" },
          ]
          : [
            { id: "all", label: "All" },
            { id: "mandatory", label: "Completed all mandatory" },
            { id: "completed", label: "Completed all" },
            { id: "one", label: "≥ 1 submission" },
            { id: "locked", label: "Locked" },
            { id: "ranked", label: "Ranked" },
            { id: "unranked", label: "Unranked" },
            { id: "new", label: "Not issued yet" },
          ]
        ).map((chip) => (
          <button
            key={chip.id}
            type="button"
            onClick={() => applyQuickSelect(chip.id)}
            className="px-3 py-1 rounded-[10px] border border-border text-foreground hover:bg-muted/50 transition-colors"
          >
            {chip.label}
          </button>
        ))}
        {selectedIds.size > 0 && (
          <button
            type="button"
            onClick={() => setSelectedIds(new Set())}
            className="px-3 py-1 rounded-[10px] border border-border text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
          >
            Clear ({selectedIds.size})
          </button>
        )}
      </div>

      <div className="bg-card border border-border rounded-[10px] overflow-x-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-12 text-muted-foreground">
            <Loader2 className="w-5 h-5 animate-spin mr-2" />
            <span className="text-sm">Loading...</span>
          </div>
        ) : view === "students" ? (
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground bg-background border-b border-border">
              <tr>
                <th className="p-3 w-8">
                  <input
                    type="checkbox"
                    aria-label="Toggle all students"
                    checked={filteredStudents.length > 0 && filteredStudents.every((r) => selectedIds.has(r.registration_id))}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedIds(new Set(filteredStudents.map((r) => r.registration_id)))
                      } else {
                        setSelectedIds(new Set())
                      }
                    }}
                    className="accent-primary"
                  />
                </th>
                <th className="p-3 text-left">Student</th>
                <th className="p-3 text-left">Team</th>
                <th className="p-3 text-left">Progress</th>
                <th className="p-3 text-left">Student cert</th>
                <th className="p-3 text-left">Team cert</th>
              </tr>
            </thead>
            <tbody>
              {filteredStudents.map((r: CompetitionCertificateRecipient) => {
                const sIssued = r.student_cert_issued ?? r.certificate_issued
                const tIssued = r.team_cert_issued ?? false
                const checked = selectedIds.has(r.registration_id)
                return (
                  <tr
                    key={r.registration_id}
                    className={`border-t border-border ${sIssued && skipAlreadyIssued ? "opacity-65" : ""}`}
                  >
                    <td className="p-3">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleRow(r.registration_id)}
                        className="accent-primary"
                      />
                    </td>
                    <td className="p-3">
                      <div className="font-medium text-foreground">{r.student_name}</div>
                      {r.email && <div className="text-xs text-muted-foreground">{r.email}</div>}
                    </td>
                    <td className="p-3">
                      {r.team_name ? (
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-foreground">{r.team_name}</span>
                          <span className="px-2 py-0.5 rounded-[10px] border border-border text-xs text-muted-foreground">
                            {r.team_rank != null ? `#${r.team_rank}` : "Unranked"}
                          </span>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">No team</span>
                      )}
                    </td>
                    <td className="p-3">
                      {renderProgressChips(
                        r.required_submissions_done ?? r.submissions_done,
                        r.required_submissions_total,
                        r.optional_submissions_done ?? 0,
                        r.optional_submissions_total ?? 0,
                        r.team_locked
                      )}
                    </td>
                    <td className="p-3">{renderStatus(sIssued, r.student_cert_generated_at ?? r.certificate_generated_at)}</td>
                    <td className="p-3">{renderStatus(tIssued, r.team_cert_generated_at, !r.team_id)}</td>
                  </tr>
                )
              })}
              {filteredStudents.length === 0 && (
                <tr>
                  <td colSpan={6} className="p-6 text-center text-sm text-muted-foreground">
                    No matching students
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground bg-background border-b border-border">
              <tr>
                <th className="p-3 w-8">
                  <input
                    type="checkbox"
                    aria-label="Toggle all teams"
                    checked={filteredTeams.length > 0 && filteredTeams.every((t) => selectedIds.has(t.team_id))}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedIds(new Set(filteredTeams.map((t) => t.team_id)))
                      } else {
                        setSelectedIds(new Set())
                      }
                    }}
                    className="accent-primary"
                  />
                </th>
                <th className="p-3 text-left">Rank</th>
                <th className="p-3 text-left">Team</th>
                <th className="p-3 text-left">Members</th>
                <th className="p-3 text-left">Progress</th>
                <th className="p-3 text-left">Team cert</th>
                <th className="p-3 text-left">Member certs</th>
              </tr>
            </thead>
            <tbody>
              {filteredTeams.map((t: CompetitionCertificateTeam) => {
                const checked = selectedIds.has(t.team_id)
                return (
                  <tr
                    key={t.team_id}
                    className={`border-t border-border ${t.team_cert_issued && skipAlreadyIssued ? "opacity-65" : ""}`}
                  >
                    <td className="p-3">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleRow(t.team_id)}
                        className="accent-primary"
                      />
                    </td>
                    <td className="p-3 font-medium">{t.rank != null ? t.rank : "—"}</td>
                    <td className="p-3 font-medium text-foreground">{t.team_name}</td>
                    <td className="p-3 text-foreground">{t.member_count}</td>
                    <td className="p-3">
                      {renderProgressChips(
                        t.required_submissions_done,
                        t.required_submissions_total,
                        t.optional_submissions_done,
                        t.optional_submissions_total,
                        t.team_locked
                      )}
                    </td>
                    <td className="p-3">{renderStatus(t.team_cert_issued, t.team_cert_generated_at)}</td>
                    <td className="p-3 text-xs text-muted-foreground">
                      {t.member_student_certs_issued} of {t.member_count}
                    </td>
                  </tr>
                )
              })}
              {filteredTeams.length === 0 && (
                <tr>
                  <td colSpan={7} className="p-6 text-center text-sm text-muted-foreground">
                    No matching teams
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      <div className="bg-card border border-border rounded-[10px] p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-6">
          <label className="inline-flex items-center gap-2.5 text-sm font-medium text-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={alsoSendOther}
              onChange={(e) => setAlsoSendOther(e.target.checked)}
              className="w-[18px] h-[18px] accent-primary cursor-pointer"
            />
            <span>
              {view === "students"
                ? "Also send their team certificate"
                : "Also send each member their student certificate"}
            </span>
          </label>

          <label className="inline-flex items-center gap-2.5 text-sm font-medium text-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={skipAlreadyIssued}
              onChange={(e) => setSkipAlreadyIssued(e.target.checked)}
              className="w-[18px] h-[18px] accent-primary cursor-pointer"
            />
            <span>Skip already issued</span>
          </label>
        </div>

        {alsoSendOther && (
          <div className="pt-2 border-t border-border">
            <label className="space-y-1.5 block max-w-md">
              <span className="text-xs font-medium text-muted-foreground block">
                {view === "students" ? "Team certificate template" : "Student certificate template"}
              </span>
              <select
                value={secondaryTemplateId}
                onChange={(e) => setSecondaryTemplateId(e.target.value)}
                className="w-full h-9 px-3 rounded-[10px] border border-border bg-background text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              >
                {secondaryOptions.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="font-semibold text-foreground">{selectedIds.size} selected</span>
            {view === "teams" && selectedIds.size > 0 && (
              <span className="text-muted-foreground">{selectedTeamMemberCount} students</span>
            )}
            {unrankedSelected && (
              <span className="inline-flex items-center gap-1.5 text-xs text-rose-500">
                <AlertCircle className="w-3.5 h-3.5" />
                <span>Unranked teams selected</span>
              </span>
            )}
          </div>

          <button
            type="button"
            disabled={selectedIds.size === 0 || sendMutation.isPending}
            onClick={() => sendMutation.mutate()}
            className="inline-flex items-center gap-2 h-9 px-5 rounded-[10px] bg-primary text-primary-foreground text-sm font-semibold hover:opacity-90 disabled:opacity-50"
          >
            {sendMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <SendHorizonal className="w-4 h-4" />}
            <span>
              {deliveryMode === "publish" && !notifyByEmail
                ? selectedIds.size > 0
                  ? `Publish to ${selectedIds.size}`
                  : "Publish"
                : selectedIds.size > 0
                  ? `Send to ${selectedIds.size}`
                  : "Send"}
            </span>
          </button>
        </div>
      </div>

      <CertificateEmailTemplatesModal
        open={emailModalOpen}
        onClose={() => setEmailModalOpen(false)}
        cohortId={cohortId}
        initialTemplateId={primaryEmailTemplateId}
        onUpdated={() => {
          queryClient.invalidateQueries({ queryKey: ["cohort-certificate-recipients", cohortId] })
        }}
      />
    </div>
  )

  if (embedded) return body

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 overflow-y-auto">
      <div className="bg-background border border-border rounded-[10px] w-full max-w-5xl max-h-[92vh] overflow-y-auto p-5 space-y-4">
        <div className="flex items-center justify-between border-b border-border pb-3">
          <div className="flex items-center gap-2">
            <Mail className="w-4 h-4 text-primary" />
            <h2 className="text-base font-semibold text-foreground">
              {programName ? `${programName} — ${cohortName}` : cohortName}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-[10px] text-muted-foreground hover:text-foreground hover:bg-muted/50"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        {body}
      </div>
    </div>,
    document.body
  )
}
