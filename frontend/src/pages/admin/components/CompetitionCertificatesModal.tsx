import { useEffect, useMemo, useState } from "react"
import { createPortal } from "react-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Award, Check, Download, Loader2, Mail, Search, X } from "lucide-react"
import {
  downloadCompetitionCertificatesApi, getCohortCertificateRecipientsApi, sendCohortCertificatesApi,
} from "@/api/competitions"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

type FilterMode = "at_least_one" | "all_completed" | "all"

interface CompetitionCertificatesModalProps {
  cohortId: string
  cohortName: string
  open: boolean
  onClose: () => void
}

export function CompetitionCertificatesModal({
  cohortId,
  cohortName,
  open,
  onClose,
}: CompetitionCertificatesModalProps) {
  const toast = useToast()
  const queryClient = useQueryClient()

  const [filter, setFilter] = useState<FilterMode>("at_least_one")
  const [theme, setTheme] = useState<"dark" | "light">("dark")
  const [skipAlreadyIssued, setSkipAlreadyIssued] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [downloading, setDownloading] = useState(false)

  const handleDownload = async () => {
    if (selectedIds.size === 0) return
    setDownloading(true)
    try {
      await downloadCompetitionCertificatesApi(
        cohortId,
        cohortName,
        filter,
        theme,
        Array.from(selectedIds),
      )
      toast.success(
        `Downloaded ${theme} certificate PDF (${selectedIds.size} student${selectedIds.size === 1 ? "" : "s"})`,
      )
    } catch (e: unknown) {
      toast.error(getErrorMessage(e, "Failed to download certificates PDF"))
    } finally {
      setDownloading(false)
    }
  }

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["cohort-certificates-recipients", cohortId, filter],
    queryFn: () => getCohortCertificateRecipientsApi(cohortId, filter),
    enabled: open,
  })

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
    mutationFn: () =>
      sendCohortCertificatesApi(cohortId, {
        filter,
        registration_ids: Array.from(selectedIds),
        theme,
        skip_already_issued: skipAlreadyIssued,
      }),
    onSuccess: (res) => {
      toast.success(`Certificates sent: ${res.sent_count} sent, ${res.skipped_count} skipped`)
      queryClient.invalidateQueries({ queryKey: ["cohort-certificates-recipients", cohortId] })
      queryClient.invalidateQueries({ queryKey: ["sessions-cohort-registrations", cohortId] })
      refetch()
    },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Failed to send certificates")),
  })

  if (!open) return null

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/75 backdrop-blur-md p-3 sm:p-4"
      onClick={onClose}
    >
      <div
        className="bg-card border border-border rounded-2xl p-4 sm:p-6 max-w-4xl w-full flex flex-col gap-4 shadow-2xl max-h-[90vh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-border">
          <div className="min-w-0 pr-3">
            <div className="flex items-center gap-2">
              <Award className="text-primary shrink-0" size={20} />
              <h2 className="text-lg font-bold text-foreground truncate">
                Send Certificates — {cohortName}
              </h2>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Issue and email completion certificate PDFs to students based on submission deliverables.
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

        {/* Filter Tabs */}
        <div className="flex items-center gap-1.5 p-1 bg-muted/60 rounded-xl overflow-x-auto">
          <button
            onClick={() => setFilter("at_least_one")}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors ${
              filter === "at_least_one"
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <span>At least 1 submission</span>
            {data && (
              <span className="px-1.5 py-0.2 rounded-full bg-primary/15 text-primary text-[11px] font-bold">
                {data.at_least_one_count}
              </span>
            )}
          </button>
          <button
            onClick={() => setFilter("all_completed")}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors ${
              filter === "all_completed"
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <span>Completed all submissions</span>
            {data && (
              <span className="px-1.5 py-0.2 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 text-[11px] font-bold">
                {data.all_completed_count}
              </span>
            )}
          </button>
          <button
            onClick={() => setFilter("all")}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors ${
              filter === "all"
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <span>All registered</span>
            {data && (
              <span className="px-1.5 py-0.2 rounded-full bg-muted text-muted-foreground text-[11px] font-bold">
                {data.total_registered}
              </span>
            )}
          </button>
        </div>

        {/* Controls: Search, Theme & Skip options */}
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

          <div className="flex items-center gap-3 flex-wrap justify-between sm:justify-end">
            <label className="flex items-center gap-1.5 text-xs text-foreground cursor-pointer select-none">
              <input
                type="checkbox"
                checked={skipAlreadyIssued}
                onChange={(e) => setSkipAlreadyIssued(e.target.checked)}
                className="rounded border-border"
              />
              <span>Skip already issued</span>
            </label>

            <div className="flex items-center gap-1.5 border border-border rounded-lg p-0.5 bg-background">
              <button
                type="button"
                onClick={() => setTheme("dark")}
                className={`px-2 py-1 text-xs rounded font-medium transition-colors ${
                  theme === "dark" ? "bg-primary text-primary-foreground font-semibold" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Dark template
              </button>
              <button
                type="button"
                onClick={() => setTheme("light")}
                className={`px-2 py-1 text-xs rounded font-medium transition-colors ${
                  theme === "light" ? "bg-primary text-primary-foreground font-semibold" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Light template
              </button>
            </div>
          </div>
        </div>

        {/* Recipient Table */}
        <div className="border border-border rounded-xl flex-1 overflow-y-auto min-h-[220px]">
          {isLoading ? (
            <div className="flex items-center justify-center h-48 gap-2 text-muted-foreground text-sm">
              <Loader2 size={16} className="animate-spin text-primary" /> Loading student submissions...
            </div>
          ) : filteredRecipients.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-muted-foreground text-sm gap-1">
              <p className="font-semibold text-foreground">No students qualify for this criteria</p>
              <p className="text-xs">Try switching tabs or searching with a different term.</p>
            </div>
          ) : (
            <table className="w-full text-left text-xs border-collapse">
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
                  <th className="py-2.5 pr-3 font-semibold text-muted-foreground text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {filteredRecipients.map((r) => {
                  const isSelected = selectedIds.has(r.registration_id)
                  const isSkippedDueToIssued = skipAlreadyIssued && r.certificate_issued
                  return (
                    <tr
                      key={r.registration_id}
                      onClick={() => toggleSelectOne(r.registration_id)}
                      className={`hover:bg-muted/40 transition-colors cursor-pointer ${
                        isSelected ? "bg-primary/5" : ""
                      } ${isSkippedDueToIssued ? "opacity-60" : ""}`}
                    >
                      <td className="py-2 pl-3 pr-2" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelectOne(r.registration_id)}
                          className="rounded border-border"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <p className="font-medium text-foreground">{r.student_name}</p>
                        {r.email && <p className="text-[11px] text-muted-foreground">{r.email}</p>}
                      </td>
                      <td className="py-2 px-2 text-foreground font-medium">
                        {r.team_name ? (
                          <div className="flex items-center gap-1">
                            <span>{r.team_name}</span>
                            {r.team_locked && (
                              <span className="text-[10px] px-1.5 py-0.2 rounded bg-muted text-muted-foreground font-semibold">
                                Locked
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="py-2 px-2">
                        <div className="flex items-center gap-1.5">
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
                        </div>
                      </td>
                      <td className="py-2 pr-3 text-right">
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

        {/* Footer actions */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2 border-t border-border">
          <div className="text-xs text-muted-foreground flex items-center gap-2">
            <span>
              <strong>{selectedIds.size}</strong> selected
            </span>
            <span>·</span>
            <span>
              <strong>{willSendCount}</strong> will be emailed
            </span>
            {skipAlreadyIssued && selectedIds.size > willSendCount && (
              <span className="text-amber-600 dark:text-amber-400">
                ({selectedIds.size - willSendCount} already issued will be skipped)
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
            <button
              type="button"
              onClick={onClose}
              className="h-9 px-4 rounded-xl border border-border text-sm font-medium text-foreground hover:bg-muted transition-colors"
            >
              Cancel
            </button>

            <button
              type="button"
              onClick={handleDownload}
              disabled={downloading || selectedIds.size === 0}
              className="flex items-center justify-center gap-1.5 h-9 px-4 rounded-xl border border-border text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
              title={`Download merged PDF for ${selectedIds.size} selected student(s) (${theme} theme)`}
            >
              {downloading ? (
                <>
                  <Loader2 size={14} className="animate-spin" /> Preparing…
                </>
              ) : (
                <>
                  <Download size={14} /> Download PDF ({selectedIds.size})
                </>
              )}
            </button>

            <button
              type="button"
              onClick={() => sendMutation.mutate()}
              disabled={sendMutation.isPending || willSendCount === 0}
              className="flex items-center justify-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
            >
              {sendMutation.isPending ? (
                <>
                  <Loader2 size={14} className="animate-spin" /> Sending…
                </>
              ) : (
                <>
                  <Mail size={14} /> Send Certificates ({willSendCount})
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
