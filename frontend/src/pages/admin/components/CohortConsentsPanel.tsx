import { useState, useMemo } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import * as XLSX from "xlsx"
import {
  CheckCircle2, XCircle, Search, FileSpreadsheet, AlertTriangle, Link2,
  FileText, Check,
} from "lucide-react"
import type { Registration, CohortMediaConsent } from "@/types/sessions"
import { getCohortMediaConsentsApi, manualMatchMediaConsentApi } from "@/api/sessions/cohorts"
import { Modal, ModalActions, Spinner, EmptyState } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

interface CohortConsentsPanelProps {
  cohortId: string
  registrations: Registration[]
}

export function CohortConsentsPanel({ cohortId, registrations }: CohortConsentsPanelProps) {
  const queryClient = useQueryClient()
  const toast = useToast()

  const [search, setSearch] = useState("")
  const [matchFilter, setMatchFilter] = useState<"all" | "matched" | "unmatched">("all")
  const [choiceFilter, setChoiceFilter] = useState<"all" | "consented" | "declined">("all")

  const [matchingConsent, setMatchingConsent] = useState<CohortMediaConsent | null>(null)
  const [selectedRegId, setSelectedRegId] = useState<string>("")
  const [detailConsent, setDetailConsent] = useState<CohortMediaConsent | null>(null)

  const { data: summary, isLoading } = useQuery({
    queryKey: ["cohort-media-consents", cohortId],
    queryFn: () => getCohortMediaConsentsApi(cohortId),
  })

  const linkMutation = useMutation({
    mutationFn: () => {
      if (!matchingConsent || !selectedRegId) throw new Error("Please select a student")
      return manualMatchMediaConsentApi(cohortId, matchingConsent.id, selectedRegId)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["cohort-media-consents", cohortId] })
      queryClient.invalidateQueries({ queryKey: ["sessions-cohort-registrations", cohortId] })
      toast?.success(`Successfully linked consent to ${data.matched_student_name ?? "student"}.`)
      setMatchingConsent(null)
      setSelectedRegId("")
    },
    onError: (err) => {
      toast?.error(getErrorMessage(err))
    },
  })

  const items = summary?.items ?? []

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      if (matchFilter === "matched" && item.match_status === "unmatched") return false
      if (matchFilter === "unmatched" && item.match_status !== "unmatched") return false
      if (choiceFilter !== "all" && item.consent_choice !== choiceFilter) return false

      if (search.trim()) {
        const q = search.toLowerCase()
        const matchName = (item.matched_student_name ?? "").toLowerCase()
        const rawName = (item.student_name_raw ?? "").toLowerCase()
        const parent = (item.parent_name ?? "").toLowerCase()
        const school = (item.school_name_raw ?? "").toLowerCase()
        const phone = (item.parent_phone ?? "").toLowerCase()
        const email = (item.parent_email ?? "").toLowerCase()

        return (
          matchName.includes(q) ||
          rawName.includes(q) ||
          parent.includes(q) ||
          school.includes(q) ||
          phone.includes(q) ||
          email.includes(q)
        )
      }
      return true
    })
  }, [items, matchFilter, choiceFilter, search])

  const handleExportConsents = () => {
    if (items.length === 0) return

    const rows = items.map((c) => ({
      "Submitted At": c.created_at ? new Date(c.created_at).toLocaleString() : "",
      "Match Status": c.match_status,
      "Match Method": c.match_method ?? "",
      "Matched Student": c.matched_student_name ?? "",
      "Student Name (Form)": c.student_name_raw ?? "",
      "School Name": c.school_name_raw ?? "",
      "Parent / Guardian Name": c.parent_name,
      "Relationship": c.relationship ?? "",
      "Mobile Number": c.parent_phone ?? "",
      "Email Address": c.parent_email ?? "",
      "Consent Choice": c.consent_choice === "consented" ? "YES (Granted)" : "NO (Declined)",
      "Signed Date": c.date_of_signing ?? "",
      "Permission Grants": (c.permission_grants || []).join(", "),
      "Declaration Agreed": c.declaration_agreed ? "YES" : "NO",
      "Source": c.source,
      "Notes": c.notes ?? "",
    }))

    const ws = XLSX.utils.json_to_sheet(rows)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, "Media Consents")
    XLSX.writeFile(wb, `cohort_${cohortId}_media_consents_${new Date().toISOString().slice(0, 10)}.xlsx`)
  }

  return (
    <div className="space-y-5">
      {/* Metric Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="p-3 bg-card border border-border rounded-xl">
          <p className="text-xs text-muted-foreground font-medium">Submissions</p>
          <p className="text-xl font-bold text-foreground mt-0.5">{summary?.total_submissions ?? 0}</p>
        </div>

        <div className="p-3 bg-card border border-emerald-500/20 bg-emerald-500/5 rounded-xl">
          <p className="text-xs text-emerald-700 dark:text-emerald-400 font-medium">Matched</p>
          <p className="text-xl font-bold text-emerald-700 dark:text-emerald-400 mt-0.5">
            {summary?.matched_count ?? 0}
          </p>
        </div>

        <div
          className={`p-3 border rounded-xl ${
            (summary?.unmatched_count ?? 0) > 0
              ? "bg-amber-500/10 border-amber-500/40 text-amber-700 dark:text-amber-400"
              : "bg-card border-border text-muted-foreground"
          }`}
        >
          <p className="text-xs font-medium flex items-center gap-1">
            {(summary?.unmatched_count ?? 0) > 0 && <AlertTriangle size={12} />}
            Unmatched
          </p>
          <p className="text-xl font-bold mt-0.5">{summary?.unmatched_count ?? 0}</p>
        </div>

        <div className="p-3 bg-card border border-emerald-500/20 bg-emerald-500/5 rounded-xl">
          <p className="text-xs text-emerald-700 dark:text-emerald-400 font-medium">Granted (YES)</p>
          <p className="text-xl font-bold text-emerald-700 dark:text-emerald-400 mt-0.5">
            {summary?.consented_count ?? 0}
          </p>
        </div>

        <div className="p-3 bg-card border border-red-500/20 bg-red-500/5 rounded-xl">
          <p className="text-xs text-red-700 dark:text-red-400 font-medium">Declined (NO)</p>
          <p className="text-xl font-bold text-red-700 dark:text-red-400 mt-0.5">
            {summary?.declined_count ?? 0}
          </p>
        </div>

        <div className="p-3 bg-card border border-border rounded-xl">
          <p className="text-xs text-muted-foreground font-medium">Pending Forms</p>
          <p className="text-xl font-bold text-foreground mt-0.5">
            {summary?.pending_registrations_count ?? 0}
          </p>
        </div>
      </div>

      {/* Filter and Action Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2.5">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search student, parent, email, phone, school…"
            className="w-full h-9 pl-9 pr-3 bg-background border border-border rounded-xl text-xs focus:outline-none focus:border-primary transition-colors"
          />
        </div>

        <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
          <select
            value={matchFilter}
            onChange={(e) => setMatchFilter(e.target.value as any)}
            className="h-9 px-2.5 bg-background border border-border rounded-xl text-xs cursor-pointer focus:outline-none focus:border-primary"
          >
            <option value="all">All match states</option>
            <option value="matched">Matched only</option>
            <option value="unmatched">Unmatched only</option>
          </select>

          <select
            value={choiceFilter}
            onChange={(e) => setChoiceFilter(e.target.value as any)}
            className="h-9 px-2.5 bg-background border border-border rounded-xl text-xs cursor-pointer focus:outline-none focus:border-primary"
          >
            <option value="all">All consent choices</option>
            <option value="consented">Granted (YES) only</option>
            <option value="declined">Declined (NO) only</option>
          </select>

          <button
            onClick={handleExportConsents}
            disabled={items.length === 0}
            className="flex items-center gap-1.5 h-9 px-3 border border-border rounded-xl text-xs font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50 shrink-0"
          >
            <FileSpreadsheet size={14} /> Export Consents
          </button>
        </div>
      </div>

      {/* Submissions List / Table */}
      {isLoading ? (
        <Spinner />
      ) : items.length === 0 ? (
        <EmptyState title="No media consent submissions yet" />
      ) : filteredItems.length === 0 ? (
        <EmptyState title={search ? `No consents match "${search}"` : "No consents match this filter"} />
      ) : (
        <div className="flex flex-col gap-2">
          {filteredItems.map((c) => {
            const isMatched = c.match_status !== "unmatched"
            const isConsented = c.consent_choice === "consented"

            return (
              <div
                key={c.id}
                className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-3 bg-background border border-border rounded-xl hover:border-border/80 transition-colors"
              >
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    {/* Consent Choice Badge */}
                    <span
                      className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full ${
                        isConsented
                          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400"
                          : "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400"
                      }`}
                    >
                      {isConsented ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                      {isConsented ? "Granted" : "Declined"}
                    </span>

                    {/* Matched Status Badge */}
                    {isMatched ? (
                      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400">
                        <Check size={11} />
                        Matched: {c.matched_student_name}
                        {c.match_method && (
                          <span className="text-[10px] opacity-75">({c.match_method})</span>
                        )}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
                        <AlertTriangle size={11} /> Unmatched
                      </span>
                    )}

                    <span className="text-xs text-muted-foreground">
                      {c.student_name_raw ? `Student: ${c.student_name_raw}` : "Unnamed"}
                    </span>
                    {c.school_name_raw && (
                      <span className="text-xs text-muted-foreground">· {c.school_name_raw}</span>
                    )}
                  </div>

                  <p className="text-xs text-muted-foreground truncate">
                    Parent: <span className="font-medium text-foreground">{c.parent_name}</span>
                    {c.relationship ? ` (${c.relationship})` : ""}
                    {c.parent_phone ? ` · ${c.parent_phone}` : ""}
                    {c.parent_email ? ` · ${c.parent_email}` : ""}
                    {c.date_of_signing ? ` · Signed: ${c.date_of_signing}` : ""}
                    {c.created_at ? ` · Submitted: ${new Date(c.created_at).toLocaleDateString()}` : ""}
                  </p>
                </div>

                <div className="flex items-center gap-2 shrink-0 justify-end pt-2 sm:pt-0 border-t border-border/50 sm:border-0">
                  {!isMatched && (
                    <button
                      onClick={() => {
                        setMatchingConsent(c)
                        setSelectedRegId("")
                      }}
                      className="flex items-center gap-1 h-7 px-2.5 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:opacity-90 transition-opacity"
                    >
                      <Link2 size={13} /> Match to student
                    </button>
                  )}
                  <button
                    onClick={() => setDetailConsent(c)}
                    className="flex items-center gap-1 h-7 px-2.5 border border-border text-foreground text-xs font-medium rounded-lg hover:bg-muted transition-colors"
                  >
                    <FileText size={13} /> Details
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Manual Link Modal (for unmatched form submissions) */}
      {matchingConsent && (
        <Modal
          title={`Match Consent Form to Student`}
          onClose={() => setMatchingConsent(null)}
        >
          <div className="space-y-4">
            <div className="p-3 bg-card border border-border rounded-xl space-y-1 text-xs text-muted-foreground">
              <p className="font-semibold text-foreground">Form Submission Details:</p>
              <p>Student Name on Form: <span className="text-foreground font-medium">{matchingConsent.student_name_raw ?? "—"}</span></p>
              <p>Parent Name: <span className="text-foreground font-medium">{matchingConsent.parent_name}</span></p>
              <p>Parent Mobile: <span className="text-foreground font-medium">{matchingConsent.parent_phone ?? "—"}</span></p>
              <p>Parent Email: <span className="text-foreground font-medium">{matchingConsent.parent_email ?? "—"}</span></p>
              <p>School: <span className="text-foreground font-medium">{matchingConsent.school_name_raw ?? "—"}</span></p>
            </div>

            <div>
              <label className="block text-xs font-medium text-foreground mb-1">
                Select Registered Student in Cohort:
              </label>
              <select
                value={selectedRegId}
                onChange={(e) => setSelectedRegId(e.target.value)}
                className="w-full h-9 px-2.5 bg-background border border-border rounded-xl text-xs focus:outline-none focus:border-primary cursor-pointer"
              >
                <option value="">-- Choose student from cohort --</option>
                {registrations.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.student_name} ({r.student_email ?? r.student_phone ?? "No contact"})
                  </option>
                ))}
              </select>
            </div>

            <ModalActions
              onCancel={() => setMatchingConsent(null)}
              onConfirm={() => linkMutation.mutate()}
              loading={linkMutation.isPending}
              disabled={!selectedRegId}
              label="Confirm Link"
            />
          </div>
        </Modal>
      )}

      {/* Full Details Modal */}
      {detailConsent && (
        <Modal
          title="Media Consent Submission Details"
          onClose={() => setDetailConsent(null)}
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-3 p-3 bg-card border border-border rounded-xl">
              <div>
                <p className="text-muted-foreground">Consent Choice:</p>
                <p className="font-semibold text-foreground text-sm mt-0.5">
                  {detailConsent.consent_choice === "consented" ? "Granted (YES)" : "Declined (NO)"}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Match Status:</p>
                <p className="font-semibold text-foreground text-sm mt-0.5">
                  {detailConsent.match_status} {detailConsent.match_method ? `(${detailConsent.match_method})` : ""}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Student Name (Typed):</p>
                <p className="font-medium text-foreground">{detailConsent.student_name_raw ?? "—"}</p>
              </div>
              <div>
                <p className="text-muted-foreground">School (Typed):</p>
                <p className="font-medium text-foreground">{detailConsent.school_name_raw ?? "—"}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Parent / Guardian:</p>
                <p className="font-medium text-foreground">
                  {detailConsent.parent_name} {detailConsent.relationship ? `(${detailConsent.relationship})` : ""}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Parent Mobile:</p>
                <p className="font-medium text-foreground">{detailConsent.parent_phone ?? "—"}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Parent Email:</p>
                <p className="font-medium text-foreground">{detailConsent.parent_email ?? "—"}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Date of Signing:</p>
                <p className="font-medium text-foreground">{detailConsent.date_of_signing ?? "—"}</p>
              </div>
            </div>

            {detailConsent.permission_grants && detailConsent.permission_grants.length > 0 && (
              <div>
                <p className="font-semibold text-foreground mb-1.5">Permission Grants:</p>
                <div className="flex flex-wrap gap-1.5">
                  {detailConsent.permission_grants.map((grant, idx) => (
                    <span
                      key={idx}
                      className="px-2.5 py-1 bg-muted rounded-lg text-foreground font-medium"
                    >
                      {grant}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {detailConsent.notes && (
              <div>
                <p className="font-semibold text-foreground mb-1">Notes:</p>
                <p className="p-2.5 bg-muted rounded-lg text-muted-foreground">{detailConsent.notes}</p>
              </div>
            )}

            <div className="pt-2 text-right">
              <button
                type="button"
                onClick={() => setDetailConsent(null)}
                className="h-8 px-4 bg-muted text-foreground text-xs font-medium rounded-lg hover:bg-muted/80"
              >
                Close
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
