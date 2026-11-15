import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useSearch } from "@tanstack/react-router"
import { ArrowDown, ArrowUp, ArrowUpRight, FileText, Pencil, Plus, Save, Search, SlidersHorizontal, Trash2, Users, X } from "lucide-react"
import {
  listApplicationsApi, getApplicationApi, getApplicationCountsApi, approveApplicationApi, rejectApplicationApi, sendToOnboardingApi,
  getAdminFormConfigApi, updateAdminFormConfigApi, createQuestionApi, updateQuestionApi, reorderQuestionsApi, deleteQuestionApi,
  type ApplyQuestion, type ApplyQuestionType, type FormFieldConfig,
} from "@/api/apply"
import { PlatformFootprintSection, ResolvedAnswersSection } from "@/components/apply/ApplicationFootprintPanel"
import { ApplicationLivePreview } from "@/components/apply/ApplicationLivePreview"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { getCountries } from "@/lib/countries"
import { fetchPublicCities } from "@/api/lms"
import { InternshipLetterFields, emptyInternshipApprove, isInternshipApproveComplete } from "@/components/InternshipLetterFields"

const countryName = (code: string) => getCountries().find((c) => c.code === code)?.name ?? code

const ROLE_OPTIONS = [
  { value: "ambassador", label: "Ambassador" },
  { value: "intern", label: "Intern" },
  { value: "teacher", label: "Teacher" },
  { value: "facilitator", label: "Facilitator" },
  { value: "organization", label: "Organization" },
]

const CONFIGURABLE_ROLE_OPTIONS = [
  { value: "instructor", label: "Instructor" },
  { value: "intern", label: "Intern" },
  { value: "student", label: "Student" },
  { value: "ambassador", label: "Ambassador" },
  { value: "teacher", label: "Teacher" },
  { value: "facilitator", label: "Facilitator" },
  { value: "organization", label: "Organization" },
]

const QUESTION_TYPE_OPTIONS: Array<{ value: ApplyQuestionType; label: string }> = [
  { value: "text", label: "Short text" },
  { value: "textarea", label: "Long text (Paragraph)" },
  { value: "number", label: "Number" },
  { value: "date", label: "Date" },
  { value: "url", label: "URL / Link" },
  { value: "radio", label: "Radio (single choice)" },
  { value: "multiple_choice", label: "Multiple choice (checkboxes)" },
]

const STATUS_OPTIONS = [
  { value: "pending", label: "Pending" },
  { value: "onboarding", label: "Onboarding" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
]

const FILTER_SELECT_CLASS =
  "h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"

const STATUS_COLOR: Record<string, string> = {
  pending: "bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300",
  approved: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300",
  rejected: "bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300",
  onboarding: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300",
}

const ROLE_COLOR: Record<string, string> = {
  ambassador: "bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-300",
  intern: "bg-[#653F84] text-white",
  teacher: "bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300",
  facilitator: "bg-teal-100 text-teal-700 dark:bg-teal-500/20 dark:text-teal-300",
  organization: "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300",
}

type Tab = "applications" | "questions"

export default function AdminApplications() {
  const [tab, setTab] = useState<Tab>("applications")
  const { data: counts } = useQuery({
    queryKey: ["admin-application-counts"],
    queryFn: getApplicationCountsApi,
  })

  const totals = Object.values(counts ?? {}).reduce(
    (acc, roleCounts) => {
      acc.pending += roleCounts.pending ?? 0
      acc.onboarding += roleCounts.onboarding ?? 0
      acc.approved += roleCounts.approved ?? 0
      acc.rejected += roleCounts.rejected ?? 0
      return acc
    },
    { pending: 0, onboarding: 0, approved: 0, rejected: 0 },
  )
  const totalCount = totals.pending + totals.onboarding + totals.approved + totals.rejected

  return (
    <div className="flex flex-col gap-6 sp-wireframe">
      <div className="sp-wireframe-header relative overflow-hidden -mx-4 -mt-4 sm:-mx-6 sm:-mt-6 lg:-mx-10 lg:-mt-10 px-4 sm:px-6 lg:px-10 pt-6 pb-5 bg-[#231134] text-white">
        <img
          src="/space-logo-white.png"
          alt=""
          aria-hidden="true"
          className="pointer-events-none select-none absolute bottom-0 right-6 w-48 sm:w-64 opacity-10"
        />

        <div className="relative z-10 flex flex-col gap-5">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="space-y-3">
              <h1 className="text-2xl font-bold tracking-tight text-white">Applications</h1>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="px-3 py-1 rounded-[10px] bg-transparent border-2 border-solid border-[#D7D2CB] text-white font-medium">
                  Total: {totalCount}
                </span>
                <span className="px-3 py-1 rounded-[10px] bg-transparent border-2 border-solid border-[#D7D2CB] text-white font-medium">
                  Pending: {totals.pending}
                </span>
                <span className="px-3 py-1 rounded-[10px] bg-transparent border-2 border-solid border-[#D7D2CB] text-white font-medium">
                  Onboarding: {totals.onboarding}
                </span>
                <span className="px-3 py-1 rounded-[10px] bg-transparent border-2 border-solid border-emerald-500 text-emerald-300 font-medium">
                  Approved: {totals.approved}
                </span>
              </div>
            </div>

            <div className="flex flex-wrap sm:flex-nowrap items-center gap-2.5 shrink-0">
              <Link
                to="/instructors/admin/applicants"
                className="flex items-center justify-center gap-1.5 h-9 px-4 rounded-[10px] bg-[#653F84] border-0 text-sm font-medium text-white hover:opacity-90 transition-opacity cursor-pointer whitespace-nowrap"
              >
                <Users size={14} /> Instructor Applications <ArrowUpRight size={14} />
              </Link>
              <Link
                to="/admin/role-requests"
                className="flex items-center justify-center gap-1.5 h-9 px-4 bg-transparent border-2 border-solid border-[#D7D2CB] rounded-[10px] text-sm font-medium text-white hover:bg-white/10 transition-colors cursor-pointer whitespace-nowrap"
              >
                Role Requests <ArrowUpRight size={14} />
              </Link>
            </div>
          </div>

          <div className="flex items-center gap-1 border-b border-white/15 -mb-5 overflow-x-auto">
            <button
              type="button"
              onClick={() => setTab("applications")}
              className={`h-9 px-3 -mb-px border-b-2 text-sm font-medium transition-colors whitespace-nowrap cursor-pointer ${tab === "applications"
                ? "border-[#D7D2CB] text-white"
                : "border-transparent text-white/70 hover:text-white"
                }`}
            >
              Applications
            </button>
            <button
              type="button"
              onClick={() => setTab("questions")}
              className={`h-9 px-3 -mb-px border-b-2 text-sm font-medium transition-colors flex items-center gap-1.5 whitespace-nowrap cursor-pointer ${tab === "questions"
                ? "border-[#D7D2CB] text-white"
                : "border-transparent text-white/70 hover:text-white"
                }`}
            >
              <SlidersHorizontal size={14} /> Questions
            </button>
          </div>
        </div>
      </div>

      {tab === "applications" && <ApplicationsTab />}
      {tab === "questions" && <QuestionsTab />}
    </div>
  )
}

// ── Applications Tab ──────────────────────────────────────────────────────────

function ApplicationsTab() {
  const { id: searchId } = useSearch({ strict: false }) as { id?: string }
  const [roleFilter, setRoleFilter] = useState<string>("all")
  const [statusFilter, setStatusFilter] = useState<string>("pending")
  const [searchQuery, setSearchQuery] = useState("")
  const [selected, setSelected] = useState<string | null>(searchId ?? null)

  useEffect(() => {
    if (searchId) setSelected(searchId)
  }, [searchId])

  const { data: apps = [], isLoading } = useQuery({
    queryKey: ["admin-applications", roleFilter, statusFilter],
    queryFn: () => listApplicationsApi({
      role: roleFilter !== "all" ? roleFilter : undefined,
      status: statusFilter !== "all" ? statusFilter : undefined,
    }),
  })

  const q = searchQuery.trim().toLowerCase()
  const filteredApps = q
    ? apps.filter((app) => {
      const hay = [
        app.full_name,
        app.email,
        app.phone,
        app.country ? countryName(app.country) : "",
        app.city,
        app.invite_code,
        app.organization_details?.organization_name,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
      return hay.includes(q)
    })
    : apps

  return (
    <div className="flex flex-col gap-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search name, email, phone, city, code…"
            className="h-9 w-full pl-8 pr-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
          />
        </div>
        <select
          aria-label="Filter by role"
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          className={`w-full sm:w-44 ${FILTER_SELECT_CLASS}`}
        >
          <option value="all">All roles</option>
          {ROLE_OPTIONS.map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
        <select
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className={`w-full sm:w-44 ${FILTER_SELECT_CLASS}`}
        >
          <option value="all">All statuses</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
        <span className="text-xs text-muted-foreground ml-auto">{filteredApps.length} application(s)</span>
      </div>

      {/* List */}
      {isLoading ? (
        <div className="flex justify-center py-12"><div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : filteredApps.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground text-sm">No applications found</div>
      ) : (
        <div className="flex flex-col gap-2">
          {filteredApps.map((app) => (
            <button
              key={app.id}
              onClick={() => setSelected(app.id)}
              className="w-full flex items-center justify-between p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors text-left gap-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-sm font-semibold text-foreground">
                    {app.role === "organization" && (app.organization_details?.organization_name || app.answers?.organization_name)
                      ? `${app.full_name} · ${String(app.organization_details?.organization_name || app.answers.organization_name)}`
                      : app.full_name}
                  </p>
                  <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${ROLE_COLOR[app.role] ?? "bg-muted text-foreground"}`}>
                    {app.role}
                  </span>
                  <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${STATUS_COLOR[app.status]}`}>
                    {app.status}
                  </span>
                  {app.has_cv && (
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                      CV attached
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-0.5 truncate">
                  {app.email}
                  {app.phone ? ` · ${app.phone}` : ""}
                  {app.country ? ` · ${countryName(app.country)}` : ""}
                  {app.city ? ` (${app.city})` : ""}
                </p>
              </div>
              <p className="text-xs text-muted-foreground shrink-0">
                {app.created_at ? new Date(app.created_at).toLocaleDateString() : "—"}
              </p>
            </button>
          ))}
        </div>
      )}

      {selected && (
        <ApplicationDetailDialog id={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  )
}

function ApplicationDetailDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [notes, setNotes] = useState("")
  const [internship, setInternship] = useState(emptyInternshipApprove)

  const { data: app, isLoading } = useQuery({
    queryKey: ["admin-application", id],
    queryFn: () => getApplicationApi(id),
  })

  const { data: workCities = [] } = useQuery({
    queryKey: ["public-cities"],
    queryFn: fetchPublicCities,
    enabled: app?.role === "intern",
  })

  const isIntern = app?.role === "intern"
  const internshipReady = !isIntern || isInternshipApproveComplete(internship)

  const approve = useMutation({
    mutationFn: () => approveApplicationApi(id, notes || undefined, isIntern ? internship : undefined),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-applications"] }); onClose() },
    onError: (err: any) => alert(err?.response?.data?.detail || "Failed to approve application."),
  })
  const reject = useMutation({
    mutationFn: () => rejectApplicationApi(id, notes || undefined),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-applications"] }); onClose() },
  })
  const onboard = useMutation({
    mutationFn: () => sendToOnboardingApi(id, notes || undefined, isIntern ? internship : undefined),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-applications"] }); onClose() },
    onError: (err: any) => alert(err?.response?.data?.detail || "Failed to send to onboarding."),
  })

  const internInfo = app?.intern_details
  const requestedCityName =
    internInfo?.preferred_city_name ||
    workCities.find((c) => c.id === (internInfo?.preferred_city_id ?? app?.answers?.preferred_city_id))?.name ||
    null

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="bg-background w-full max-w-2xl h-screen flex flex-col shadow-2xl border-l border-border">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold text-foreground">Application Full Review</p>
            {app && (
              <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full capitalize ${STATUS_COLOR[app.status]}`}>
                {app.status}
              </span>
            )}
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:bg-muted transition-colors">
            <X size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <div className="p-5 flex flex-col gap-4">
            {isLoading ? (
              <div className="flex justify-center py-12"><div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
            ) : !app ? null : (
              <>
                <Card>
                  <CardContent className="p-4 flex flex-col gap-3">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center text-base font-bold text-foreground shrink-0">
                        {app.full_name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <p className="font-semibold text-foreground">{app.full_name}</p>
                        <p className="text-sm text-muted-foreground truncate">{app.email}</p>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm pt-2 border-t border-border/50">
                      <Info label="Role" value={app.role} />
                      <Info label="Status" value={app.status} />
                      <Info label="Phone / WhatsApp" value={app.phone || "Not provided"} muted={!app.phone} noCapitalize />
                      <Info label="Date of Birth" value={app.birthdate || "Not provided"} muted={!app.birthdate} noCapitalize />
                      <Info label="Nationality" value={String(app.answers?.nationality || "Not provided")} muted={!app.answers?.nationality} />
                      <Info label="Country" value={app.country ? countryName(app.country) : "Not provided"} muted={!app.country} />
                      <Info label="City" value={app.city || app.city_other || "Not provided"} muted={!app.city && !app.city_other} />
                      <Info label="Invite Code Used" value={app.invite_code || "None"} muted={!app.invite_code} noCapitalize />
                      <Info
                        label="Referred By"
                        value={app.invited_by ? `${app.invited_by.full_name} (${app.invited_by.email})` : "Direct / Organic"}
                        muted={!app.invited_by}
                        noCapitalize
                      />
                      <Info
                        label="Submitted At"
                        value={app.created_at ? new Date(app.created_at).toLocaleString() : "—"}
                        noCapitalize
                      />
                      {app.reviewed_at && (
                        <Info
                          label="Reviewed At"
                          value={new Date(app.reviewed_at).toLocaleString()}
                          noCapitalize
                        />
                      )}
                      {app.reviewed_by_name && (
                        <Info label="Reviewed By" value={app.reviewed_by_name} noCapitalize />
                      )}
                    </div>
                  </CardContent>
                </Card>

                {/* CV Status */}
                {app.has_cv && app.cv_signed_url ? (
                  <a href={app.cv_signed_url} target="_blank" rel="noreferrer">
                    <Button variant="outline" className="w-full gap-2">
                      <FileText size={14} /> View / Download Submitted CV
                    </Button>
                  </a>
                ) : (
                  <div className="rounded-xl border border-border bg-muted/20 px-4 py-2.5 text-xs text-muted-foreground">
                    CV / Resume: <span className="font-medium text-foreground">No CV uploaded with this application</span>
                  </div>
                )}

                {/* Always-visible Organization details */}
                {app.role === "organization" && (
                  <Card>
                    <CardContent className="p-4 flex flex-col gap-3">
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Organization Details</p>
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <Info
                          label="Organization Name"
                          value={app.organization_details?.organization_name || String(app.answers?.organization_name || "—")}
                          noCapitalize
                        />
                        {Boolean(app.organization_details?.organization_name_arabic || app.answers?.organization_name_arabic) && (
                          <Info
                            label="Arabic Name"
                            value={app.organization_details?.organization_name_arabic || String(app.answers?.organization_name_arabic)}
                            noCapitalize
                          />
                        )}
                        <Info
                          label="Organization Type"
                          value={app.organization_details?.organization_type || String(app.answers?.organization_type || "—")}
                        />
                        <Info
                          label="Approval State"
                          value={app.organization_details?.is_approved === true ? "Approved" : app.organization_details?.is_approved === false ? "Pending Org Approval" : "—"}
                        />
                        {app.organization_details?.website && (
                          <Info label="Website" value={app.organization_details.website} noCapitalize />
                        )}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Always-visible Intern details across ALL statuses */}
                {isIntern && (
                  <Card>
                    <CardContent className="p-4 flex flex-col gap-3">
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        Submitted Internship Details
                      </p>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
                        <Info label="University" value={internInfo?.university || "Not specified"} muted={!internInfo?.university} noCapitalize />
                        <Info label="Major" value={internInfo?.major || "Not specified"} muted={!internInfo?.major} noCapitalize />
                        <Info label="University ID" value={internInfo?.university_id_number || "Not provided"} muted={!internInfo?.university_id_number} noCapitalize />
                        <Info label="Requested City" value={requestedCityName || "Any / Not specified"} muted={!requestedCityName} noCapitalize />
                        <Info label="Requested Start" value={internInfo?.requested_start_date || "Not specified"} muted={!internInfo?.requested_start_date} noCapitalize />
                        <Info
                          label="Requested Duration"
                          value={internInfo?.requested_duration_weeks != null ? `${internInfo.requested_duration_weeks} weeks` : "Not specified"}
                          muted={internInfo?.requested_duration_weeks == null}
                          noCapitalize
                        />
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Resolved Custom Answers (never raw UUIDs or reserved keys) */}
                <ResolvedAnswersSection answers={app.resolved_answers} />

                {/* Cross-platform footprint */}
                <PlatformFootprintSection footprint={app.platform_footprint} />

                {app.status === "pending" && isIntern && (
                  <Card>
                    <CardContent className="p-4 flex flex-col gap-3">
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        Internship Letter Configuration
                      </p>
                      <InternshipLetterFields
                        value={internship}
                        onChange={setInternship}
                        requestedCityId={app.answers?.preferred_city_id as string | undefined}
                        requestedDurationWeeks={app.answers?.requested_duration_weeks as number | undefined}
                        requestedStartDate={app.answers?.requested_start_date as string | undefined}
                        showRefNumberOverride={false}
                        internName={app.full_name}
                        universityIdNumber={app.answers?.university_id_number as string | undefined}
                      />
                    </CardContent>
                  </Card>
                )}

                {app.status === "pending" && (
                  <Card>
                    <CardContent className="p-4 flex flex-col gap-3">
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Review Decision</p>
                      <textarea
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        placeholder="Admin notes (optional)"
                        rows={3}
                        className="w-full p-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none resize-none"
                      />
                      <div className="flex gap-2">
                        <Button variant="outline" className="flex-1 h-auto py-2.5 px-4 rounded-[10px] border-2 border-rose-500 text-white hover:bg-rose-500/20"
                          onClick={() => reject.mutate()} disabled={reject.isPending || approve.isPending || onboard.isPending}>
                          {reject.isPending ? "Rejecting…" : "Reject"}
                        </Button>
                        <Button className="flex-1 h-auto py-2.5 px-4 rounded-[10px] bg-emerald-600 hover:bg-emerald-700 text-white"
                          onClick={() => approve.mutate()} disabled={approve.isPending || reject.isPending || onboard.isPending || !internshipReady}>
                          {approve.isPending ? "Approving…" : "Approve"}
                        </Button>
                      </div>
                      {app.role === "intern" && !app.platform_footprint?.existing_user?.roles?.includes("instructor") && (
                        <Button variant="outline" className="w-full h-auto py-2.5 px-4 rounded-[10px] border-2 border-[#653F84] text-white hover:bg-[#653F84]/20"
                          onClick={() => onboard.mutate()} disabled={approve.isPending || reject.isPending || onboard.isPending || !internshipReady}>
                          {onboard.isPending ? "Sending…" : "Send to Instructor Onboarding"}
                        </Button>
                      )}
                    </CardContent>
                  </Card>
                )}

                {app.status !== "pending" && (
                  <Card>
                    <CardContent className="p-4 flex flex-col gap-2">
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Review Record</p>
                      <p className="text-sm text-foreground">{app.admin_notes || "No admin notes recorded."}</p>
                      {(app.reviewed_by_name || app.reviewed_at) && (
                        <p className="text-xs text-muted-foreground">
                          Actioned {app.reviewed_by_name ? `by ${app.reviewed_by_name} ` : ""}
                          {app.reviewed_at ? `on ${new Date(app.reviewed_at).toLocaleString()}` : ""}
                        </p>
                      )}
                    </CardContent>
                  </Card>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function Info({
  label,
  value,
  noCapitalize,
  muted,
}: {
  label: string
  value: string
  noCapitalize?: boolean
  muted?: boolean
}) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`text-sm font-medium ${muted ? "text-muted-foreground italic" : "text-foreground"} ${noCapitalize ? "" : "capitalize"}`}>
        {value}
      </p>
    </div>
  )
}

// ── Form Fields & Questions Tab ───────────────────────────────────────────────

interface QuestionDraft {
  id?: string
  question_text: string
  question_type: ApplyQuestionType
  required: boolean
  options: string[]
}

const EMPTY_QUESTION: QuestionDraft = {
  question_text: "",
  question_type: "text",
  required: true,
  options: [""],
}

function QuestionsTab() {
  const qc = useQueryClient()
  const [audience, setAudience] = useState("instructor")
  const [modalQ, setModalQ] = useState<QuestionDraft | null>(null)
  const [draftFields, setDraftFields] = useState<FormFieldConfig[]>([])
  const [fieldsDirty, setFieldsDirty] = useState(false)

  const { data: formConfig, isLoading } = useQuery({
    queryKey: ["admin-form-config", audience],
    queryFn: () => getAdminFormConfigApi(audience),
  })

  useEffect(() => {
    if (formConfig?.fields) {
      setDraftFields(formConfig.fields)
      setFieldsDirty(false)
    }
  }, [formConfig])

  const questions = formConfig?.questions ?? []

  const saveFieldConfig = useMutation({
    mutationFn: () =>
      updateAdminFormConfigApi(
        audience,
        draftFields.map((f) => ({ key: f.key, enabled: f.enabled, required: f.required })),
      ),
    onSuccess: () => {
      setFieldsDirty(false)
      qc.invalidateQueries({ queryKey: ["admin-form-config", audience] })
      qc.invalidateQueries({ queryKey: ["apply-form-config", audience] })
    },
  })

  const createQ = useMutation({
    mutationFn: (q: QuestionDraft) =>
      createQuestionApi({
        audience,
        question_text: q.question_text,
        question_type: q.question_type,
        required: q.required,
        options: q.options.map((o) => o.trim()).filter(Boolean),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-form-config", audience] })
      qc.invalidateQueries({ queryKey: ["apply-form-config", audience] })
      setModalQ(null)
    },
  })

  const updateQ = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ApplyQuestion> }) =>
      updateQuestionApi(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-form-config", audience] })
      qc.invalidateQueries({ queryKey: ["apply-form-config", audience] })
      setModalQ(null)
    },
  })

  const reorderQ = useMutation({
    mutationFn: (orderedIds: string[]) => reorderQuestionsApi(audience, orderedIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-form-config", audience] })
      qc.invalidateQueries({ queryKey: ["apply-form-config", audience] })
    },
  })

  const removeQ = useMutation({
    mutationFn: (id: string) => deleteQuestionApi(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-form-config", audience] })
      qc.invalidateQueries({ queryKey: ["apply-form-config", audience] })
    },
  })

  const toggleFieldFlag = (key: string, flag: "enabled" | "required") => {
    setDraftFields((prev) =>
      prev.map((f) => {
        if (f.key !== key || f.locked) return f
        if (flag === "enabled") {
          const nextEnabled = !f.enabled
          return { ...f, enabled: nextEnabled, required: nextEnabled ? f.required : false }
        }
        if (!f.enabled) return f
        return { ...f, required: !f.required }
      }),
    )
    setFieldsDirty(true)
  }

  const moveQuestion = (idx: number, dir: -1 | 1) => {
    const target = idx + dir
    if (target < 0 || target >= questions.length) return
    const nextIds = questions.map((q) => q.id)
    const [item] = nextIds.splice(idx, 1)
    nextIds.splice(target, 0, item)
    reorderQ.mutate(nextIds)
  }

  const needsOptions = modalQ?.question_type === "radio" || modalQ?.question_type === "multiple_choice"

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Application Role:</label>
          <select
            aria-label="Select question role"
            value={audience}
            onChange={(e) => setAudience(e.target.value)}
            className={`w-52 ${FILTER_SELECT_CLASS}`}
          >
            {CONFIGURABLE_ROLE_OPTIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          {fieldsDirty && (
            <Button
              disabled={saveFieldConfig.isPending}
              onClick={() => saveFieldConfig.mutate()}
              className="h-10 px-5 gap-2 rounded-[10px] bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              <Save size={14} /> {saveFieldConfig.isPending ? "Saving…" : "Save Changes"}
            </Button>
          )}
          <Button className="h-10 px-5 gap-1.5 shrink-0 rounded-[10px] bg-[#653F84] hover:bg-[#53326e] text-white" onClick={() => setModalQ({ ...EMPTY_QUESTION })}>
            <Plus size={14} /> Add Question
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8"><div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
          <div className="xl:col-span-6 flex flex-col gap-2">
            <div className="flex items-center justify-between px-1">
              <h2 className="text-base font-bold text-foreground">
                Questions ({draftFields.length + questions.length})
              </h2>
            </div>

            <div className="divide-y divide-border/60 border border-border rounded-[10px] overflow-hidden bg-card">
              {draftFields.map((f, idx) => (
                <div key={f.key} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 bg-card">
                  <div className="flex items-start gap-3">
                    <span className="text-xs text-muted-foreground font-semibold w-5 pt-0.5 shrink-0">{idx + 1}</span>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium text-foreground">{f.label}</span>
                        {f.section && (
                          <span className="text-[11px] px-2 py-0.5 rounded-[10px] bg-muted text-muted-foreground">{f.section}</span>
                        )}
                        {f.locked && (
                          <span className="text-[11px] px-2 py-0.5 rounded-[10px] bg-[#F5F3FF] text-[#6D28D9] dark:bg-[#2E1065] dark:text-purple-200">Core</span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 shrink-0 text-xs">
                    <label className={`flex items-center gap-1.5 ${f.locked ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}>
                      <input
                        type="checkbox"
                        checked={f.enabled}
                        disabled={f.locked}
                        onChange={() => toggleFieldFlag(f.key, "enabled")}
                      />
                      <span>Visible</span>
                    </label>
                    <label className={`flex items-center gap-1.5 ${f.locked || !f.enabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}>
                      <input
                        type="checkbox"
                        checked={f.required}
                        disabled={f.locked || !f.enabled}
                        onChange={() => toggleFieldFlag(f.key, "required")}
                      />
                      <span className={f.required ? "text-rose-600 dark:text-rose-400 font-semibold" : "text-muted-foreground"}>Mandatory</span>
                    </label>
                  </div>
                </div>
              ))}

              {questions.map((q, i) => {
                const isVisible = q.enabled !== false
                return (
                  <div key={q.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 bg-card">
                    <div className="flex items-start gap-3 flex-1 min-w-[200px]">
                      <div className="flex flex-col items-center gap-0.5 shrink-0 pt-0.5">
                        <button
                          type="button"
                          title="Move up"
                          disabled={i === 0 || reorderQ.isPending}
                          onClick={() => moveQuestion(i, -1)}
                          className="p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
                        >
                          <ArrowUp size={13} />
                        </button>
                        <span className="text-xs text-muted-foreground font-semibold">{draftFields.length + i + 1}</span>
                        <button
                          type="button"
                          title="Move down"
                          disabled={i === questions.length - 1 || reorderQ.isPending}
                          onClick={() => moveQuestion(i, 1)}
                          className="p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
                        >
                          <ArrowDown size={13} />
                        </button>
                      </div>

                      <div className="flex-1">
                        <p className="text-sm font-medium text-foreground">{q.question_text}</p>
                        <div className="flex items-center gap-2 mt-1 flex-wrap">
                          <span className="text-[11px] px-2 py-0.5 rounded-[10px] bg-muted text-muted-foreground capitalize">
                            {q.question_type.replace("_", " ")}
                          </span>
                          {q.options.length > 0 && (
                            <span className="text-xs text-muted-foreground">Options: {q.options.join(", ")}</span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-3 shrink-0 text-xs">
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={isVisible}
                          onChange={() => {
                            const nextEnabled = !isVisible
                            updateQ.mutate({
                              id: q.id,
                              data: { enabled: nextEnabled, required: nextEnabled ? q.required : false },
                            })
                          }}
                        />
                        <span>Visible</span>
                      </label>
                      <label className={`flex items-center gap-1.5 ${!isVisible ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}>
                        <input
                          type="checkbox"
                          checked={q.required}
                          disabled={!isVisible}
                          onChange={() => updateQ.mutate({ id: q.id, data: { required: !q.required } })}
                        />
                        <span className={q.required ? "text-rose-600 dark:text-rose-400 font-semibold" : "text-muted-foreground"}>Mandatory</span>
                      </label>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          title="Edit question"
                          onClick={() =>
                            setModalQ({
                              id: q.id,
                              question_text: q.question_text,
                              question_type: q.question_type,
                              required: q.required,
                              options: q.options.length > 0 ? q.options : [""],
                            })
                          }
                          className="p-1.5 rounded-[10px] text-muted-foreground hover:text-primary transition-colors cursor-pointer"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          type="button"
                          title="Delete question"
                          onClick={() => removeQ.mutate(q.id)}
                          className="p-1.5 rounded-[10px] text-muted-foreground hover:text-rose-600 transition-colors cursor-pointer"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="xl:col-span-6 flex flex-col gap-2">
            <div className="flex items-center justify-between px-1">
              <h2 className="text-base font-bold text-foreground">Live Preview</h2>
            </div>
            <ApplicationLivePreview role={audience} fields={draftFields} questions={questions} />
          </div>
        </div>
      )}

      {modalQ && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
          onClick={(e) => { if (e.target === e.currentTarget) setModalQ(null) }}>
          <Card className="w-full max-w-md">
            <CardContent className="p-5 flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <p className="font-semibold text-foreground text-sm">{modalQ.id ? "Edit question" : "New question"}</p>
                <button onClick={() => setModalQ(null)} className="text-muted-foreground hover:text-foreground"><X size={16} /></button>
              </div>
              <div className="flex flex-col gap-3">
                <textarea
                  value={modalQ.question_text}
                  onChange={(e) => setModalQ({ ...modalQ, question_text: e.target.value })}
                  placeholder="Question text"
                  rows={2}
                  className="w-full p-3 bg-background border border-border rounded-xl text-sm focus:outline-none resize-none"
                />
                <select
                  value={modalQ.question_type}
                  onChange={(e) => setModalQ({ ...modalQ, question_type: e.target.value as ApplyQuestionType })}
                  className="h-9 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none"
                >
                  {QUESTION_TYPE_OPTIONS.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
                {needsOptions && (
                  <div className="flex flex-col gap-2">
                    <p className="text-xs text-muted-foreground font-medium">Options</p>
                    {modalQ.options.map((opt, i) => (
                      <div key={i} className="flex gap-2">
                        <div className="flex-1">
                          <input
                            className="input"
                            placeholder={`Option ${i + 1}`}
                            value={opt}
                            onChange={(e) => {
                              const next = [...modalQ.options]
                              next[i] = e.target.value
                              setModalQ({ ...modalQ, options: next })
                            }}
                          />
                        </div>
                        {modalQ.options.length > 1 && (
                          <button
                            onClick={() => setModalQ({ ...modalQ, options: modalQ.options.filter((_, j) => j !== i) })}
                            className="text-muted-foreground hover:text-destructive"
                          >
                            <X size={14} />
                          </button>
                        )}
                      </div>
                    ))}
                    <button
                      onClick={() => setModalQ({ ...modalQ, options: [...modalQ.options, ""] })}
                      className="text-xs text-primary hover:underline text-left"
                    >
                      + Add option
                    </button>
                  </div>
                )}
                <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                  <input
                    type="checkbox"
                    checked={modalQ.required}
                    onChange={(e) => setModalQ({ ...modalQ, required: e.target.checked })}
                  />
                  Mandatory question
                </label>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" className="flex-1" onClick={() => setModalQ(null)}>Cancel</Button>
                <Button
                  className="flex-1"
                  disabled={!modalQ.question_text.trim() || createQ.isPending || updateQ.isPending}
                  onClick={() => {
                    if (modalQ.id) {
                      updateQ.mutate({
                        id: modalQ.id,
                        data: {
                          question_text: modalQ.question_text,
                          question_type: modalQ.question_type,
                          required: modalQ.required,
                          options: needsOptions ? modalQ.options.map((o) => o.trim()).filter(Boolean) : [],
                        },
                      })
                    } else {
                      createQ.mutate(modalQ)
                    }
                  }}
                >
                  {createQ.isPending || updateQ.isPending ? "Saving…" : "Save question"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
