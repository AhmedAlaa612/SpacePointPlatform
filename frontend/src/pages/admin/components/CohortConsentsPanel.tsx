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

  // Quick inline match selector state per card
  const [inlineMatches, setInlineMatches] = useState<Record<string, string>>({})
  const [inlineLoading, setInlineLoading] = useState<string | null>(null)

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

  const handleInlineMatch = async (consentId: string) => {
    const regId = inlineMatches[consentId]
    if (!regId) return
    setInlineLoading(consentId)
    try {
      const data = await manualMatchMediaConsentApi(cohortId, consentId, regId)
      queryClient.invalidateQueries({ queryKey: ["cohort-media-consents", cohortId] })
      queryClient.invalidateQueries({ queryKey: ["sessions-cohort-registrations", cohortId] })
      toast?.success(`Matched consent to ${data.matched_student_name ?? "student"}`)
    } catch (err) {
      toast?.error(getErrorMessage(err))
    } finally {
      setInlineLoading(null)
    }
  }

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
        const studentEmail = (item.student_email_raw ?? "").toLowerCase()
        const parent = (item.parent_name ?? "").toLowerCase()
        const school = (item.school_name_raw ?? "").toLowerCase()
        const phone = (item.parent_phone ?? "").toLowerCase()
        const email = (item.parent_email ?? "").toLowerCase()

        return (
          matchName.includes(q) ||
          rawName.includes(q) ||
          studentEmail.includes(q) ||
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
      "Student Email (Form)": c.student_email_raw ?? "",
      "School Name": c.school_name_raw ?? "",
      "Parent / Guardian Name": c.parent_name,
      "Relationship": c.relationship ?? "",
      "Mobile Number": c.parent_phone ?? "",
      "Email Address": c.parent_email ?? "",
      "Consent Choice": c.consent_choice === "consented" ? "YES (Granted)" : "NO (Declined)",
      "Signed Date": c.date_of_signing ?? "",
      "Permission Grants": (c.permission_grants || []).join(", "),
      "Declaration Agreed": c.declaration_agreed ? "YES" : "NO",
      Notes: c.notes ?? "",
    }))

    const ws = XLSX.utils.json_to_sheet(rows)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, "Media Consents")
    XLSX.writeFile(wb, `cohort-media-consents-${new Date().toISOString().split("T")[0]}.xlsx`)
  }

  return (
    <div className="space-y-5">
      {/* Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="p-3 bg-card border border-border rounded-xl">
          <span className="text-[11px] text-muted-foreground block">Total Submissions</span>
          <span className="text-xl font-bold text-foreground">{summary?.total_submissions ?? 0}</span>
        </div>
        <div className="p-3 bg-card border border-border rounded-xl">
          <span className="text-[11px] text-emerald-600 dark:text-emerald-400 block font-medium">Granted (YES)</span>
          <span className="text-xl font-bold text-emerald-600 dark:text-emerald-400">{summary?.consented_count ?? 0}</span>
        </div>
        <div className="p-3 bg-card border border-border rounded-xl">
          <span className="text-[11px] text-red-600 dark:text-red-400 block font-medium">Declined (NO)</span>
          <span className="text-xl font-bold text-red-600 dark:text-red-400">{summary?.declined_count ?? 0}</span>
        </div>
        <div className="p-3 bg-card border border-border rounded-xl">
          <span className="text-[11px] text-blue-600 dark:text-blue-400 block font-medium">Matched Students</span>
          <span className="text-xl font-bold text-blue-600 dark:text-blue-400">{summary?.matched_count ?? 0}</span>
        </div>
        <div className="p-3 bg-card border border-border rounded-xl">
          <span className="text-[11px] text-amber-600 dark:text-amber-400 block font-medium">Unmatched Submissions</span>
          <span className="text-xl font-bold text-amber-600 dark:text-amber-400">{summary?.unmatched_count ?? 0}</span>
        </div>
        <div className="p-3 bg-card border border-border rounded-xl">
          <span className="text-[11px] text-muted-foreground block">Pending Registrations</span>
          <span className="text-xl font-bold text-foreground">{summary?.pending_registrations_count ?? 0}</span>
        </div>
      </div>

      {/* Filter and Action Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="relative flex-1 sm:max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search by student, email, parent..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full h-9 pl-9 pr-3 bg-background border border-border rounded-xl text-xs placeholder:text-muted-foreground focus:outline-none focus:border-primary"
          />
        </div>

        <div className="flex items-center gap-2 flex-wrap">
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

      {/* Submissions Cards */}
      {isLoading ? (
        <Spinner />
      ) : items.length === 0 ? (
        <EmptyState title="No media consent submissions yet" />
      ) : filteredItems.length === 0 ? (
        <EmptyState title={search ? `No consents match "${search}"` : "No consents match this filter"} />
      ) : (
        <div className="flex flex-col gap-3">
          {filteredItems.map((c) => {
            const isMatched = c.match_status !== "unmatched"
            const isConsented = c.consent_choice === "consented"
            const displayName = c.student_name_raw || c.matched_student_name || "Unnamed Student"

            return (
              <div
                key={c.id}
                className="bg-card border border-border/80 rounded-2xl p-4 sm:p-5 shadow-sm hover:border-border transition-all space-y-3.5"
              >
                {/* Top Row: Student Name as BIGGEST THING, Badges, View Details */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border/40">
                  <div className="flex items-center gap-3 flex-wrap">
                    {/* Big Student Name */}
                    <h3 className="text-lg sm:text-xl font-bold text-foreground tracking-tight">
                      {displayName}
                    </h3>

                    {/* State Badge */}
                    <span
                      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold ${
                        isConsented
                          ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/25"
                          : "bg-red-500/15 text-red-600 dark:text-red-400 border border-red-500/25"
                      }`}
                    >
                      {isConsented ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
                      {isConsented ? "Granted" : "Declined"}
                    </span>

                    {/* Match Badge */}
                    {isMatched ? (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-500/25">
                        <Check size={12} />
                        Matched: {c.matched_student_name}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/25">
                        <AlertTriangle size={12} />
                        Unmatched
                      </span>
                    )}
                  </div>

                  {/* View Details Button */}
                  <button
                    onClick={() => setDetailConsent(c)}
                    className="flex items-center gap-1.5 h-8 px-3.5 border border-border text-foreground text-xs font-semibold rounded-xl hover:bg-muted transition-colors shrink-0 self-start sm:self-auto"
                  >
                    <FileText size={14} /> View Details
                  </button>
                </div>

                {/* Info Grid: Student Email, School, Signed Date */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 text-xs">
                  <div className="p-2.5 bg-muted/40 rounded-xl border border-border/40">
                    <span className="text-muted-foreground block text-[11px] mb-0.5 font-medium">Student Email</span>
                    <span className="font-semibold text-foreground break-all">
                      {c.student_email_raw || "—"}
                    </span>
                  </div>

                  <div className="p-2.5 bg-muted/40 rounded-xl border border-border/40">
                    <span className="text-muted-foreground block text-[11px] mb-0.5 font-medium">School</span>
                    <span className="font-semibold text-foreground">
                      {c.school_name_raw || "—"}
                    </span>
                  </div>

                  <div className="p-2.5 bg-muted/40 rounded-xl border border-border/40">
                    <span className="text-muted-foreground block text-[11px] mb-0.5 font-medium">Signed & Submitted</span>
                    <span className="font-semibold text-foreground">
                      {c.date_of_signing || "—"} · {c.created_at ? new Date(c.created_at).toLocaleDateString() : ""}
                    </span>
                  </div>
                </div>

                {/* Guardian & Quick Student Match Selector Row */}
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 p-3 bg-muted/30 rounded-xl border border-border/50 text-xs">
                  {/* Guardian Info */}
                  <div className="flex items-center gap-2 flex-wrap text-foreground">
                    <span className="font-semibold text-muted-foreground">Guardian:</span>
                    <span className="font-bold text-foreground">{c.parent_name}</span>
                    {c.relationship && <span className="text-muted-foreground">({c.relationship})</span>}
                    {c.parent_phone && <span className="text-muted-foreground">· 📞 {c.parent_phone}</span>}
                    {c.parent_email && <span className="text-muted-foreground">· ✉️ {c.parent_email}</span>}
                  </div>

                  {/* Inline Student Selector and Match Button */}
                  <div className="flex items-center gap-2 w-full lg:w-auto shrink-0">
                    <select
                      value={inlineMatches[c.id] || (isMatched && c.registration_id ? c.registration_id : "")}
                      onChange={(e) => setInlineMatches((prev) => ({ ...prev, [c.id]: e.target.value }))}
                      className="h-8 px-2.5 bg-background border border-border rounded-xl text-xs flex-1 lg:w-64 focus:outline-none focus:border-primary cursor-pointer truncate"
                    >
                      <option value="">{isMatched ? "Change matched student..." : "Select student to match..."}</option>
                      {registrations.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.student_name} ({r.student_email || r.student_phone || "No contact"})
                        </option>
                      ))}
                    </select>

                    <button
                      onClick={() => handleInlineMatch(c.id)}
                      disabled={!inlineMatches[c.id] || inlineLoading === c.id}
                      className="flex items-center gap-1 h-8 px-3.5 bg-primary text-primary-foreground text-xs font-semibold rounded-xl hover:opacity-90 transition-opacity disabled:opacity-40 shrink-0"
                    >
                      <Link2 size={13} />
                      {inlineLoading === c.id ? "Matching..." : "Match"}
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Manual Link Modal (Fallback) */}
      {matchingConsent && (
        <Modal
          title={`Match Consent Form to Student`}
          onClose={() => setMatchingConsent(null)}
        >
          <div className="space-y-4">
            <div className="p-3 bg-card border border-border rounded-xl space-y-1 text-xs text-muted-foreground">
              <p className="font-semibold text-foreground">Form Submission Details:</p>
              <p>Student Name on Form: <span className="text-foreground font-medium">{matchingConsent.student_name_raw ?? "—"}</span></p>
              <p>Student Email: <span className="text-foreground font-medium">{matchingConsent.student_email_raw ?? "—"}</span></p>
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
                <p className="text-muted-foreground">Student Email (Typed):</p>
                <p className="font-medium text-foreground">{detailConsent.student_email_raw ?? "—"}</p>
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
