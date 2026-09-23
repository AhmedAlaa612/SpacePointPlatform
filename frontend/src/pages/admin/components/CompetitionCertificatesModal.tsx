import { useEffect, useMemo, useState } from "react"
import { createPortal } from "react-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Award, Check, ChevronDown, ChevronUp, Download, Eye, Loader2, Mail,
  RefreshCw, Search, ShieldCheck, X,
} from "lucide-react"
import {
  type CertificateFilterMode,
  downloadCompetitionCertificatesApi,
  getCohortCertificateRecipientsApi,
  sendCohortCertificatesApi,
} from "@/api/competitions"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

interface CompetitionCertificatesModalProps {
  cohortId: string
  cohortName: string
  programName?: string
  open: boolean
  onClose: () => void
}

export function CompetitionCertificatesModal({
  cohortId,
  cohortName,
  programName,
  open,
  onClose,
}: CompetitionCertificatesModalProps) {
  const toast = useToast()
  const queryClient = useQueryClient()

  const [filter, setFilter] = useState<CertificateFilterMode>("locked_only")
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("dark")
  const [hasUserSelectedTemplate, setHasUserSelectedTemplate] = useState(false)
  const [skipAlreadyIssued, setSkipAlreadyIssued] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [downloading, setDownloading] = useState(false)

  // Email customization state (2026-09)
  const [showEmailEditor, setShowEmailEditor] = useState(false)
  const [emailSubject, setEmailSubject] = useState("")
  const [emailBody, setEmailBody] = useState("")
  const [saveEmailToTemplate, setSaveEmailToTemplate] = useState(false)
  const [previewMode, setPreviewMode] = useState(false)
  const [hasManuallyEditedEmail, setHasManuallyEditedEmail] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["cohort-certificates-recipients", cohortId, filter],
    queryFn: () => getCohortCertificateRecipientsApi(cohortId, filter),
    enabled: open,
  })

  // Whenever recipient data loads, auto-select the program's default template if user hasn't manually picked one
  useEffect(() => {
    if (data?.default_template_id && !hasUserSelectedTemplate) {
      setSelectedTemplateId(data.default_template_id)
    }
  }, [data?.default_template_id, hasUserSelectedTemplate])

  const availableTemplates = useMemo(() => {
    if (data?.templates && data.templates.length > 0) {
      return data.templates
    }
    return [
      { id: "dark", name: "Dark Default", is_default: true, background_type: "dark" },
      { id: "light", name: "Light Default", is_default: false, background_type: "light" },
    ]
  }, [data?.templates])

  const selectedTemplate = useMemo(() => {
    return availableTemplates.find((t) => t.id === selectedTemplateId) || availableTemplates[0]
  }, [availableTemplates, selectedTemplateId])

  const effectiveProgramTitle = useMemo(() => {
    const p = (data?.program_name || programName || "").trim()
    const c = (data?.cohort_name || cohortName || "").trim()
    if (p && c && p.toLowerCase() !== c.toLowerCase()) {
      return `${p} - ${c}`
    }
    return p || c || "SpacePoint"
  }, [data?.program_name, data?.cohort_name, programName, cohortName])

  const effectiveDates = data?.dates || "October 2026"

  // Synchronize email subject and body when template or filter changes (unless user manually typed custom copy)
  useEffect(() => {
    if (hasManuallyEditedEmail) return

    if (selectedTemplate?.email_subject) {
      setEmailSubject(selectedTemplate.email_subject)
    } else {
      if (filter === "participation") {
        setEmailSubject(`Your Certificate of Participation — ${effectiveProgramTitle}`)
      } else {
        setEmailSubject(`Your SpacePoint certificate — ${effectiveProgramTitle}`)
      }
    }

    if (selectedTemplate?.email_body) {
      setEmailBody(selectedTemplate.email_body)
    } else {
      if (filter === "participation") {
        setEmailBody(
          `<p>Hi {student_name},</p>\n<p>Thank you for participating in <strong>{program_name}</strong> with team <strong>{team_name}</strong> ({dates})!</p>\n<p>Your certificate of participation is attached to this email as a PDF.</p>\n<p>— SpacePoint</p>`,
        )
      } else {
        setEmailBody(
          `<p>Hi {student_name},</p>\n<p>Congratulations on completing <strong>{program_name}</strong> ({dates})!</p>\n<p>Your certificate of completion is attached to this email as a PDF.</p>\n<p>— SpacePoint</p>`,
        )
      }
    }
  }, [selectedTemplate, filter, effectiveProgramTitle, hasManuallyEditedEmail])

  const handleResetEmail = () => {
    setHasManuallyEditedEmail(false)
    if (selectedTemplate?.email_subject) {
      setEmailSubject(selectedTemplate.email_subject)
    } else {
      setEmailSubject(
        filter === "participation"
          ? `Your Certificate of Participation — ${effectiveProgramTitle}`
          : `Your SpacePoint certificate — ${effectiveProgramTitle}`,
      )
    }

    if (selectedTemplate?.email_body) {
      setEmailBody(selectedTemplate.email_body)
    } else {
      setEmailBody(
        filter === "participation"
          ? `<p>Hi {student_name},</p>\n<p>Thank you for participating in <strong>{program_name}</strong> with team <strong>{team_name}</strong> ({dates})!</p>\n<p>Your certificate of participation is attached to this email as a PDF.</p>\n<p>— SpacePoint</p>`
          : `<p>Hi {student_name},</p>\n<p>Congratulations on completing <strong>{program_name}</strong> ({dates})!</p>\n<p>Your certificate of completion is attached to this email as a PDF.</p>\n<p>— SpacePoint</p>`,
      )
    }
    toast.success("Email copy reset to defaults")
  }

  const handleDownload = async () => {
    if (selectedIds.size === 0) return
    setDownloading(true)
    try {
      const isStock = selectedTemplateId === "dark" || selectedTemplateId === "light"
      await downloadCompetitionCertificatesApi(
        cohortId,
        cohortName,
        filter,
        isStock ? (selectedTemplateId as "dark" | "light") : "custom",
        Array.from(selectedIds),
        isStock ? undefined : selectedTemplateId,
      )
      toast.success(
        `Downloaded ${selectedTemplate?.name || "certificate"} PDF (${selectedIds.size} student${selectedIds.size === 1 ? "" : "s"})`,
      )
    } catch (e: unknown) {
      toast.error(getErrorMessage(e, "Failed to download certificates PDF"))
    } finally {
      setDownloading(false)
    }
  }

  // Whenever recipient data or filter changes, default select all matching unissued students (or all if skip=false)
  useEffect(() => {
    if (!data?.recipients) return
    const initial = new Set<string>()
    for (const r of data.recipients) {
      if (!skipAlreadyIssued || !r.certificate_issued) {
        initial.add(r.registration_id)
      }
    }
    setSelectedIds(initial)
  }, [data?.recipients, filter, skipAlreadyIssued])

  const recipients = data?.recipients ?? []

  const filteredRecipients = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return recipients
    return recipients.filter((r) =>
      r.student_name.toLowerCase().includes(q) ||
      (r.email && r.email.toLowerCase().includes(q)) ||
      (r.team_name && r.team_name.toLowerCase().includes(q)),
    )
  }, [recipients, searchQuery])

  const allVisibleSelected = useMemo(() => {
    if (filteredRecipients.length === 0) return false
    return filteredRecipients.every((r) => selectedIds.has(r.registration_id))
  }, [filteredRecipients, selectedIds])

  const toggleSelectAll = () => {
    if (allVisibleSelected) {
      setSelectedIds((prev) => {
        const next = new Set(prev)
        for (const r of filteredRecipients) {
          next.delete(r.registration_id)
        }
        return next
      })
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev)
        for (const r of filteredRecipients) {
          next.add(r.registration_id)
        }
        return next
      })
    }
  }

  const toggleSelectOne = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // Count how many will actually receive an email
  const willSendCount = useMemo(() => {
    return recipients.filter((r) => selectedIds.has(r.registration_id) && (!skipAlreadyIssued || !r.certificate_issued)).length
  }, [recipients, selectedIds, skipAlreadyIssued])

  const sendMutation = useMutation({
    mutationFn: () => {
      const isStock = selectedTemplateId === "dark" || selectedTemplateId === "light"
      return sendCohortCertificatesApi(cohortId, {
        filter,
        registration_ids: Array.from(selectedIds),
        theme: isStock ? (selectedTemplateId as "dark" | "light") : "custom",
        template_id: isStock ? undefined : selectedTemplateId,
        skip_already_issued: skipAlreadyIssued,
        custom_email_subject: emailSubject.trim() || undefined,
        custom_email_body: emailBody.trim() || undefined,
        save_email_to_template: saveEmailToTemplate,
      })
    },
    onSuccess: (res) => {
      if (res.status === "queued" || res.status === "inline") {
        toast.success(`Dispatching ${res.total_targeted} certificate(s) in background...`)
      } else {
        toast.success(`Certificates sent: ${res.sent_count} sent, ${res.skipped_count} skipped`)
      }
      queryClient.invalidateQueries({ queryKey: ["cohort-certificates-recipients", cohortId] })
      queryClient.invalidateQueries({ queryKey: ["sessions-cohort-registrations", cohortId] })
      queryClient.invalidateQueries({ queryKey: ["program-certificate-templates"] })
      refetch()
    },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Failed to send certificates")),
  })

  // Sample student for live email preview
  const sampleRecipient = filteredRecipients[0] || recipients[0] || {
    student_name: "Ahmed Mubarak",
    team_name: "Nebula Pioneers",
    certificate_type_earned: filter === "participation" ? "participation" : "completion",
  }

  const renderedPreviewBody = useMemo(() => {
    const sName = sampleRecipient.student_name
    const tName = sampleRecipient.team_name || "Team"
    const cType = (sampleRecipient.certificate_type_earned === "participation" || filter === "participation") ? "Participation" : "Completion"
    const cName = data?.cohort_name || cohortName
    let body = emailBody
      .replace(/\{student_name\}/g, sName)
      .replace(/\{program_name\}/g, effectiveProgramTitle)
      .replace(/\{cohort_name\}/g, cName)
      .replace(/\{cohort\}/g, cName)
      .replace(/\{dates\}/g, effectiveDates)
      .replace(/\{team_name\}/g, tName)
      .replace(/\{certificate_type\}/g, cType)

    if (!body.includes("<p") && !body.includes("<br") && !body.includes("<div")) {
      body = body.split("\n").join("<br/>")
    }
    return body
  }, [emailBody, sampleRecipient, effectiveProgramTitle, data?.cohort_name, cohortName, effectiveDates, filter])

  const renderedPreviewSubject = useMemo(() => {
    const sName = sampleRecipient.student_name
    const tName = sampleRecipient.team_name || "Team"
    const cType = (sampleRecipient.certificate_type_earned === "participation" || filter === "participation") ? "Participation" : "Completion"
    const cName = data?.cohort_name || cohortName
    return emailSubject
      .replace(/\{student_name\}/g, sName)
      .replace(/\{program_name\}/g, effectiveProgramTitle)
      .replace(/\{cohort_name\}/g, cName)
      .replace(/\{cohort\}/g, cName)
      .replace(/\{dates\}/g, effectiveDates)
      .replace(/\{team_name\}/g, tName)
      .replace(/\{certificate_type\}/g, cType)
  }, [emailSubject, sampleRecipient, effectiveProgramTitle, data?.cohort_name, cohortName, effectiveDates, filter])

  if (!open) return null

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/75 backdrop-blur-md p-2.5 sm:p-4 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="bg-card border border-border rounded-2xl p-3.5 sm:p-6 max-w-4xl w-full flex flex-col gap-3.5 sm:gap-4 shadow-2xl max-h-[94vh] sm:max-h-[90vh] overflow-hidden my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start sm:items-center justify-between pb-3 border-b border-border gap-2">
          <div className="min-w-0 pr-2">
            <div className="flex items-center gap-2 flex-wrap">
              <Award className="text-primary shrink-0" size={20} />
              <h2 className="text-base sm:text-lg font-bold text-foreground break-words">
                Send Certificates — {cohortName}
              </h2>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
              Issue completion certificates to locked teams, or participation certificates to submitting students.
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition-colors shrink-0"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Filter Tabs - Height & touch-friendly on mobile */}
        <div className="flex items-center gap-1.5 sm:gap-2 p-1.5 bg-muted/60 rounded-xl overflow-x-auto min-h-[46px] scrollbar-thin">
          <button
            onClick={() => setFilter("locked_only")}
            className={`flex items-center gap-2 px-3 sm:px-3.5 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors shrink-0 ${
              filter === "locked_only"
                ? "bg-card text-foreground shadow-sm border border-border"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <ShieldCheck size={14} className="text-emerald-500" />
            <span>Locked only (Completion)</span>
            {data && (
              <span className="px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 text-[11px] font-bold">
                {data.locked_only_count}
              </span>
            )}
          </button>

          <button
            onClick={() => setFilter("participation")}
            className={`flex items-center gap-2 px-3 sm:px-3.5 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors shrink-0 ${
              filter === "participation"
                ? "bg-card text-foreground shadow-sm border border-border"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <span>Participation (≥ 1 submission)</span>
            {data && (
              <span className="px-1.5 py-0.5 rounded-full bg-violet-500/15 text-violet-600 dark:text-violet-400 text-[11px] font-bold">
                {data.participation_count}
              </span>
            )}
          </button>

          <button
            onClick={() => setFilter("all_completed")}
            className={`flex items-center gap-2 px-3 sm:px-3.5 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors shrink-0 ${
              filter === "all_completed"
                ? "bg-card text-foreground shadow-sm border border-border"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <span>Completed all</span>
            {data && (
              <span className="px-1.5 py-0.5 rounded-full bg-primary/15 text-primary text-[11px] font-bold">
                {data.all_completed_count}
              </span>
            )}
          </button>

          <button
            onClick={() => setFilter("all")}
            className={`flex items-center gap-2 px-3 sm:px-3.5 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors shrink-0 ${
              filter === "all"
                ? "bg-card text-foreground shadow-sm border border-border"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <span>All registered</span>
            {data && (
              <span className="px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground text-[11px] font-bold">
                {data.total_registered}
              </span>
            )}
          </button>
        </div>

        {/* Controls: Search, Theme, Skip options, and Email Editor toggle */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2.5">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search student or team..."
              className="w-full h-8 pl-8 pr-3 border border-border bg-background text-foreground rounded-lg text-xs focus:outline-none focus:border-primary"
            />
          </div>

          <div className="flex items-center gap-2 sm:gap-2.5 flex-wrap justify-between sm:justify-end">
            <label className="flex items-center gap-1.5 text-xs text-foreground cursor-pointer select-none">
              <input
                type="checkbox"
                checked={skipAlreadyIssued}
                onChange={(e) => setSkipAlreadyIssued(e.target.checked)}
                className="rounded border-border text-primary"
              />
              <span className="whitespace-nowrap">Skip already issued</span>
            </label>

            <div className="flex items-center gap-1.5 border border-border rounded-lg px-2.5 py-0.5 bg-background max-w-full">
              <label className="text-xs text-muted-foreground whitespace-nowrap">Template:</label>
              <select
                value={selectedTemplateId}
                onChange={(e) => {
                  setSelectedTemplateId(e.target.value)
                  setHasUserSelectedTemplate(true)
                  setHasManuallyEditedEmail(false)
                }}
                className="h-7 text-xs font-medium bg-transparent text-foreground border-0 focus:outline-none cursor-pointer max-w-full"
              >
                {availableTemplates.map((t) => (
                  <option key={t.id} value={t.id} className="bg-card text-foreground">
                    {t.name}{t.is_default ? " ★ (Default)" : ""}
                  </option>
                ))}
              </select>
            </div>

            {/* Email Template Toggle Button */}
            <button
              type="button"
              onClick={() => setShowEmailEditor((prev) => !prev)}
              className={`flex items-center gap-1.5 h-8 px-2.5 rounded-lg border text-xs font-medium transition-colors ${
                showEmailEditor
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border bg-background text-foreground hover:bg-muted"
              }`}
            >
              <Mail size={13} />
              <span>Email Template</span>
              {hasManuallyEditedEmail && (
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400" title="Customized copy" />
              )}
              {showEmailEditor ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>
          </div>
        </div>

        {/* Email Template Editor Drawer (Visible when toggled) */}
        {showEmailEditor && (
          <div className="p-3.5 bg-muted/40 border border-border rounded-xl flex flex-col gap-3 text-xs animate-in fade-in-50 duration-200">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-foreground">
                  Customize Email Copy
                </span>
                {hasManuallyEditedEmail ? (
                  <span className="text-[10px] text-amber-600 dark:text-amber-400 font-medium bg-amber-500/10 px-2 py-0.5 rounded-full">
                    Customized for this send
                  </span>
                ) : (
                  <span className="text-[10px] text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                    Using {selectedTemplate?.name || "default"} copy
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setPreviewMode(!previewMode)}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-md border border-border bg-background text-[11px] font-medium text-foreground hover:bg-muted transition-colors"
                >
                  <Eye size={12} /> {previewMode ? "Edit Raw" : "Preview"}
                </button>
                {hasManuallyEditedEmail && (
                  <button
                    type="button"
                    onClick={handleResetEmail}
                    className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
                    title="Reset to template defaults"
                  >
                    <RefreshCw size={11} /> Reset
                  </button>
                )}
              </div>
            </div>

            {previewMode ? (
              <div className="border border-border/80 rounded-lg p-3 bg-card space-y-2">
                <div className="border-b border-border/60 pb-1.5">
                  <span className="text-[11px] text-muted-foreground font-semibold">Subject: </span>
                  <span className="text-[12px] font-medium text-foreground">{renderedPreviewSubject}</span>
                </div>
                <div
                  className="text-xs text-foreground leading-relaxed prose prose-sm dark:prose-invert max-w-none pt-1"
                  dangerouslySetInnerHTML={{ __html: renderedPreviewBody }}
                />
                <div className="text-[10px] text-muted-foreground pt-1 border-t border-border/40 italic">
                  * Live preview rendered for student: <strong>{sampleRecipient.student_name}</strong>
                  {sampleRecipient.team_name ? ` (${sampleRecipient.team_name})` : ""}
                </div>
              </div>
            ) : (
              <div className="space-y-2.5">
                <div>
                  <label className="text-[11px] text-muted-foreground font-medium mb-1 block">Subject Line</label>
                  <input
                    type="text"
                    value={emailSubject}
                    onChange={(e) => {
                      setEmailSubject(e.target.value)
                      setHasManuallyEditedEmail(true)
                    }}
                    placeholder={`Your SpacePoint certificate — ${effectiveProgramTitle}`}
                    className="w-full h-8 px-2.5 rounded-lg border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-muted-foreground font-medium mb-1 block">Body (HTML supported)</label>
                  <textarea
                    rows={4}
                    value={emailBody}
                    onChange={(e) => {
                      setEmailBody(e.target.value)
                      setHasManuallyEditedEmail(true)
                    }}
                    className="w-full p-2 rounded-lg border border-border bg-background text-xs text-foreground font-mono focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div className="flex items-center justify-between flex-wrap gap-2 pt-0.5">
                  <div className="flex items-center gap-1 flex-wrap">
                    <span className="text-[10px] text-muted-foreground font-medium">Insert:</span>
                    {["{student_name}", "{program_name}", "{dates}", "{team_name}", "{certificate_type}"].map((token) => (
                      <button
                        key={token}
                        type="button"
                        onClick={() => {
                          setEmailBody((prev) => (prev ? `${prev} ${token}` : token))
                          setHasManuallyEditedEmail(true)
                        }}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-background hover:bg-muted border border-border text-foreground transition-colors font-mono"
                      >
                        {token}
                      </button>
                    ))}
                  </div>

                  {selectedTemplateId !== "dark" && selectedTemplateId !== "light" && (
                    <label className="flex items-center gap-1.5 text-[11px] text-foreground cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={saveEmailToTemplate}
                        onChange={(e) => setSaveEmailToTemplate(e.target.checked)}
                        className="rounded border-border text-primary"
                      />
                      <span>Save as template default</span>
                    </label>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Recipient Table */}
        <div className="border border-border rounded-xl flex-1 overflow-x-auto overflow-y-auto min-h-[220px]">
          {isLoading ? (
            <div className="flex items-center justify-center h-48 gap-2 text-muted-foreground text-sm">
              <Loader2 size={16} className="animate-spin text-primary" /> Loading student submissions...
            </div>
          ) : filteredRecipients.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-muted-foreground text-sm gap-1 p-4 text-center">
              <p className="font-semibold text-foreground">No students qualify for this criteria</p>
              <p className="text-xs">Try switching filter tabs or searching with a different term.</p>
            </div>
          ) : (
            <table className="w-full text-left text-xs border-collapse min-w-[580px]">
              <thead>
                <tr className="border-b border-border bg-muted/40 sticky top-0 backdrop-blur z-10">
                  <th className="py-2.5 pl-3 pr-2 w-8">
                    <input
                      type="checkbox"
                      checked={allVisibleSelected}
                      onChange={toggleSelectAll}
                      className="rounded border-border"
                      title={allVisibleSelected ? "Deselect all" : "Select all"}
                    />
                  </th>
                  <th className="py-2.5 px-2 font-semibold text-muted-foreground">Student</th>
                  <th className="py-2.5 px-2 font-semibold text-muted-foreground">Team</th>
                  <th className="py-2.5 px-2 font-semibold text-muted-foreground">Submissions</th>
                  <th className="py-2.5 px-2 font-semibold text-muted-foreground">Certificate</th>
                  <th className="py-2.5 pr-3 font-semibold text-muted-foreground text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {filteredRecipients.map((r) => {
                  const isSelected = selectedIds.has(r.registration_id)
                  const isSkippedDueToIssued = skipAlreadyIssued && r.certificate_issued
                  const isLocked = r.team_locked
                  const certType = r.certificate_type_earned || (isLocked ? "completion" : "participation")

                  return (
                    <tr
                      key={r.registration_id}
                      onClick={() => toggleSelectOne(r.registration_id)}
                      className={`hover:bg-muted/40 transition-colors cursor-pointer ${
                        isSelected ? "bg-primary/5" : ""
                      } ${isSkippedDueToIssued ? "opacity-60" : ""}`}
                    >
                      <td className="py-2.5 pl-3 pr-2" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelectOne(r.registration_id)}
                          className="rounded border-border text-primary"
                        />
                      </td>
                      <td className="py-2.5 px-2">
                        <p className="font-medium text-foreground">{r.student_name}</p>
                        {r.email && <p className="text-[11px] text-muted-foreground">{r.email}</p>}
                      </td>
                      <td className="py-2.5 px-2 text-foreground font-medium">
                        {r.team_name ? (
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span>{r.team_name}</span>
                            {isLocked ? (
                              <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-semibold border border-emerald-500/20">
                                🔒 Locked
                              </span>
                            ) : (
                              <span className="text-[10px] px-1.5 py-0.2 rounded bg-muted text-muted-foreground font-medium">
                                In Progress
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="py-2.5 px-2">
                        <span
                          className={`font-semibold tabular-nums px-2 py-0.5 rounded-md ${
                            r.meets_all_completed
                              ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                              : r.meets_at_least_one
                              ? "bg-violet-500/10 text-violet-600 dark:text-violet-400"
                              : "bg-muted text-muted-foreground"
                          }`}
                        >
                          {r.submissions_done} / {r.required_submissions_total || r.submissions_total}
                        </span>
                      </td>
                      <td className="py-2.5 px-2">
                        {certType === "completion" ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 rounded-full px-2 py-0.5 border border-emerald-500/20">
                            Completion
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-violet-600 dark:text-violet-400 bg-violet-500/10 rounded-full px-2 py-0.5 border border-violet-500/20">
                            Participation
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 pr-3 text-right">
                        {r.certificate_issued ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 rounded-full px-2 py-0.5">
                            <Check size={11} /> Issued
                          </span>
                        ) : (
                          <span className="text-[11px] text-muted-foreground bg-muted rounded-full px-2 py-0.5">
                            Pending
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer actions - Mobile responsive without text overflow */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-3 border-t border-border">
          <div className="text-xs text-muted-foreground flex items-center gap-2 flex-wrap">
            <span>
              <strong>{selectedIds.size}</strong> selected
            </span>
            <span>·</span>
            <span>
              <strong>{willSendCount}</strong> will be emailed
            </span>
            {skipAlreadyIssued && selectedIds.size > willSendCount && (
              <span className="text-amber-600 dark:text-amber-400">
                ({selectedIds.size - willSendCount} already issued skipped)
              </span>
            )}
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 w-full sm:w-auto">
            <button
              type="button"
              onClick={onClose}
              className="h-9 px-4 rounded-xl border border-border text-xs sm:text-sm font-medium text-foreground hover:bg-muted transition-colors order-3 sm:order-1 text-center"
            >
              Cancel
            </button>

            <button
              type="button"
              onClick={handleDownload}
              disabled={downloading || selectedIds.size === 0}
              className="flex items-center justify-center gap-1.5 h-9 px-3.5 rounded-xl border border-border text-xs sm:text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50 order-2"
              title={`Download merged PDF for ${selectedIds.size} student(s)`}
            >
              {downloading ? (
                <>
                  <Loader2 size={14} className="animate-spin shrink-0" /> Preparing…
                </>
              ) : (
                <>
                  <Download size={14} className="shrink-0" />
                  <span className="truncate">Download PDF ({selectedIds.size})</span>
                </>
              )}
            </button>

            <button
              type="button"
              onClick={() => sendMutation.mutate()}
              disabled={sendMutation.isPending || willSendCount === 0}
              className="flex items-center justify-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground rounded-xl text-xs sm:text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50 order-1 sm:order-3"
            >
              {sendMutation.isPending ? (
                <>
                  <Loader2 size={14} className="animate-spin shrink-0" /> Sending…
                </>
              ) : (
                <>
                  <Mail size={14} className="shrink-0" />
                  <span className="truncate">Send Certificates ({willSendCount})</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}
