import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useSearch } from "@tanstack/react-router"
import { X, FileText, ArrowRight, ExternalLink } from "lucide-react"
import { ResolvedAnswersSection, PlatformFootprintSection } from "@/components/apply/ApplicationFootprintPanel"
import { getCountries } from "@/lib/countries"
import {
  listRoleRequestsAdminApi,
  approveRoleRequestApi,
  rejectRoleRequestApi,
  onboardRoleRequestToInstructorApi,
  getRoleRequestCvUrlApi,
} from "@/api/internship"
import { fetchPublicCities } from "@/api/lms"
import type { RoleRequest } from "@/types/internship"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { InternshipLetterFields, emptyInternshipApprove, isInternshipApproveComplete } from "@/components/InternshipLetterFields"

const STATUS_COLOR: Record<string, string> = {
  pending: "bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300",
  approved: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300",
  rejected: "bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300",
}

export default function AdminRoleRequests() {
  const { id: searchId } = useSearch({ strict: false }) as { id?: string }
  const [statusFilter, setStatusFilter] = useState<string>("pending")
  const [selected, setSelected] = useState<string | null>(searchId ?? null)

  const qc = useQueryClient()
  const { data: requests = [], isLoading } = useQuery({
    queryKey: ["admin-role-requests", statusFilter],
    queryFn: () => listRoleRequestsAdminApi({ status: statusFilter !== "all" ? statusFilter : undefined }),
  })

  useEffect(() => {
    if (searchId) setSelected(searchId)
  }, [searchId])

  // If deep-linking to a role request that was already approved/rejected,
  // widen the filter so `selectedRequest` resolves instead of staying blank.
  useEffect(() => {
    if (searchId && !isLoading && statusFilter !== "all" && !requests.some((r) => r.id === searchId)) {
      setStatusFilter("all")
    }
  }, [searchId, isLoading, requests, statusFilter])

  const selectedRequest = requests.find((r) => r.id === selected) ?? null

  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-role-requests"] })

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="font-display text-2xl font-bold text-foreground mb-1">Role Requests</h1>
        <p className="text-sm text-muted-foreground">
          Existing accounts requesting an additional role — e.g. an instructor applying for an internship.
        </p>
      </div>

      <div className="flex gap-1 bg-muted rounded-xl p-1 w-fit">
        {["pending", "approved", "rejected", "all"].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors capitalize ${statusFilter === s ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
          >
            {s === "all" ? "All statuses" : s}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12"><div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : requests.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground text-sm">No role requests found</div>
      ) : (
        <div className="flex flex-col gap-2">
          {requests.map((req) => (
            <button
              key={req.id}
              onClick={() => setSelected(req.id)}
              className="w-full flex items-center justify-between p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors text-left gap-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-sm font-semibold text-foreground">{req.requester_name}</p>
                  <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-[10px] bg-[#653F84] text-white">
                    requesting {req.target_role}
                  </span>
                  <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${STATUS_COLOR[req.status]}`}>
                    {req.status}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">{req.requester_email}</p>
              </div>
              <p className="text-xs text-muted-foreground shrink-0">
                {new Date(req.created_at).toLocaleDateString()}
              </p>
            </button>
          ))}
        </div>
      )}

      {selectedRequest && (
        <RoleRequestDetailDialog
          req={selectedRequest}
          onClose={() => setSelected(null)}
          onChanged={refresh}
        />
      )}
    </div>
  )
}

function RoleRequestDetailDialog({
  req, onClose, onChanged,
}: { req: RoleRequest; onClose: () => void; onChanged: () => void }) {
  const [notes, setNotes] = useState("")
  const [form, setForm] = useState(emptyInternshipApprove)
  const [loadingCv, setLoadingCv] = useState(false)
  const { data: cities = [] } = useQuery({ queryKey: ["public-cities"], queryFn: fetchPublicCities })
  const requestedCityName = cities.find((c) => c.id === req.details.preferred_city_id)?.name

  const approve = useMutation({
    mutationFn: () => approveRoleRequestApi(req.id, { ...form, admin_notes: notes || undefined }),
    onSuccess: () => { onChanged(); onClose() },
    onError: (err: any) => alert(err?.response?.data?.detail || "Failed to approve request."),
  })
  const onboardToInstructor = useMutation({
    mutationFn: () => onboardRoleRequestToInstructorApi(req.id, { ...form, admin_notes: notes || undefined }),
    onSuccess: () => { onChanged(); onClose() },
    onError: (err: any) => alert(err?.response?.data?.detail || "Failed to route to instructor onboarding."),
  })
  const reject = useMutation({
    mutationFn: () => rejectRoleRequestApi(req.id, notes || undefined),
    onSuccess: () => { onChanged(); onClose() },
    onError: (err: any) => alert(err?.response?.data?.detail || "Failed to reject request."),
  })

  const handleViewCv = async () => {
    try {
      setLoadingCv(true)
      const res = await getRoleRequestCvUrlApi(req.id)
      if (res.cv_url) {
        window.open(res.cv_url, "_blank", "noopener,noreferrer")
      }
    } catch (err: any) {
      alert(err?.response?.data?.detail || "Failed to retrieve CV download URL")
    } finally {
      setLoadingCv(false)
    }
  }

  const canSubmit = isInternshipApproveComplete(form)
  const isPending = req.status === "pending"
  const isInternRequest = req.target_role === "intern"
  const isAlreadyInstructor = Boolean(
    req.requester_profile?.roles?.includes("instructor") ||
      req.platform_footprint?.existing_user?.roles?.includes("instructor"),
  )
  const hasCv = Boolean(req.details.cv_path || req.details.cv_url)

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="bg-background w-full max-w-2xl h-screen flex flex-col shadow-2xl border-l border-border">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <div>
            <p className="text-sm font-semibold text-foreground">Role Request Review</p>
            <p className="text-xs text-muted-foreground">Submitted {new Date(req.created_at).toLocaleString()}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:bg-muted transition-colors">
            <X size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <div className="p-5 flex flex-col gap-4">
            <Card>
              <CardContent className="p-4 flex flex-col gap-2">
                <div className="flex items-start justify-between gap-2 flex-wrap">
                  <div>
                    <p className="font-semibold text-foreground">{req.requester_name ?? "Unnamed User"}</p>
                    <p className="text-sm text-muted-foreground">{req.requester_email ?? "—"}</p>
                  </div>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-[10px] bg-[#653F84] text-white">
                      requesting {req.target_role}
                    </span>
                    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${STATUS_COLOR[req.status]}`}>
                      {req.status}
                    </span>
                  </div>
                </div>
                {req.requester_profile && (
                  <div className="mt-2 pt-2 border-t border-border grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-xs">
                    <p><span className="text-muted-foreground">Phone: </span>{req.requester_profile.phone ?? "Not provided"}</p>
                    <p>
                      <span className="text-muted-foreground">Country: </span>
                      {req.requester_profile.country
                        ? getCountries().find((c) => c.code === req.requester_profile?.country)?.name ?? req.requester_profile.country
                        : "—"}
                    </p>
                    <p><span className="text-muted-foreground">City: </span>{req.requester_profile.city ?? "—"}</p>
                    <p><span className="text-muted-foreground">Birthdate: </span>{req.requester_profile.birthdate ?? "—"}</p>
                    {req.requester_profile.card_id && (
                      <p><span className="text-muted-foreground">Card ID: </span><span className="font-mono">{req.requester_profile.card_id}</span></p>
                    )}
                    {req.requester_profile.student_id && (
                      <p><span className="text-muted-foreground">Student ID: </span>{req.requester_profile.student_id}</p>
                    )}
                    {req.requester_profile.organization_name && (
                      <p className="sm:col-span-2"><span className="text-muted-foreground">Organization: </span>{req.requester_profile.organization_name}</p>
                    )}
                    {req.requester_profile.roles && req.requester_profile.roles.length > 0 && (
                      <p className="sm:col-span-2"><span className="text-muted-foreground">Current roles: </span>{req.requester_profile.roles.join(", ")}</p>
                    )}
                  </div>
                )}
                {Object.keys(req.details ?? {}).length > 0 && (
                  <div className="mt-2 flex flex-col gap-1 text-xs">
                    {req.details.university != null && (
                      <p><span className="text-muted-foreground">University: </span>{String(req.details.university)}</p>
                    )}
                    {req.details.university_id_number != null && (
                      <p><span className="text-muted-foreground">University ID: </span>{String(req.details.university_id_number)}</p>
                    )}
                    {req.details.major != null && (
                      <p><span className="text-muted-foreground">Major / Field: </span>{String(req.details.major)}</p>
                    )}
                    {req.details.preferred_city_id != null && (
                      <p><span className="text-muted-foreground">Requested city: </span>{req.preferred_city_name ?? requestedCityName ?? String(req.details.preferred_city_id)}</p>
                    )}
                    {req.details.requested_start_date != null && (
                      <p><span className="text-muted-foreground">Requested start: </span>{String(req.details.requested_start_date)}</p>
                    )}
                    {req.details.requested_duration_weeks != null && (
                      <p><span className="text-muted-foreground">Requested duration: </span>{String(req.details.requested_duration_weeks)} weeks</p>
                    )}
                    {!hasCv && (
                      <p className="text-muted-foreground">CV: Not uploaded</p>
                    )}
                    {hasCv && (
                      <div className="mt-2 pt-2 border-t border-border">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={loadingCv}
                          onClick={handleViewCv}
                          className="gap-1.5 text-xs h-8"
                        >
                          <FileText size={13} />
                          {loadingCv ? "Opening CV..." : "View Uploaded CV (PDF)"}
                        </Button>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {isPending && isInternRequest && (
              <Card>
                <CardContent className="p-4 flex flex-col gap-3">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Internship Letter Details
                  </p>
                  <InternshipLetterFields
                    value={form}
                    onChange={setForm}
                    requestedCityId={req.details.preferred_city_id as string | undefined}
                    requestedDurationWeeks={req.details.requested_duration_weeks as number | undefined}
                    requestedStartDate={req.details.requested_start_date as string | undefined}
                    internName={req.requester_name ?? undefined}
                    universityIdNumber={req.details.university_id_number as string | undefined}
                  />
                </CardContent>
              </Card>
            )}

            {isPending && (
              <Card>
                <CardContent className="p-4 flex flex-col gap-3">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Review Decision</p>
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Admin notes (optional — shown to the requester if you reject)"
                    rows={3}
                    className="w-full p-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none resize-none"
                  />

                  {isInternRequest ? (
                    <div className="flex flex-col gap-2">
                      {!isAlreadyInstructor && (
                        <Button
                          variant="outline"
                          className="w-full h-auto py-2.5 px-4 rounded-[10px] border-2 border-[#653F84] text-white hover:bg-[#653F84]/20 gap-1.5"
                          onClick={() => onboardToInstructor.mutate()}
                          disabled={onboardToInstructor.isPending || approve.isPending || reject.isPending || !canSubmit}
                        >
                          <ArrowRight size={14} />
                          {onboardToInstructor.isPending ? "Routing to Onboarding…" : "Route to Instructor Onboarding"}
                        </Button>
                      )}
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          className="flex-1 h-auto py-2.5 px-4 rounded-[10px] border-2 border-rose-500 text-white hover:bg-rose-500/20"
                          onClick={() => reject.mutate()}
                          disabled={reject.isPending || approve.isPending || onboardToInstructor.isPending}
                        >
                          {reject.isPending ? "Rejecting…" : "Reject"}
                        </Button>
                        <Button
                          className="flex-1 h-auto py-2.5 px-4 rounded-[10px] bg-emerald-600 hover:bg-emerald-700 text-white"
                          onClick={() => approve.mutate()}
                          disabled={approve.isPending || reject.isPending || onboardToInstructor.isPending || !canSubmit}
                        >
                          {approve.isPending ? "Approving…" : "Direct Approve (Intern Role)"}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        className="flex-1 h-auto py-2.5 px-4 rounded-[10px] border-2 border-rose-500 text-white hover:bg-rose-500/20"
                        onClick={() => reject.mutate()}
                        disabled={reject.isPending || approve.isPending}
                      >
                        {reject.isPending ? "Rejecting…" : "Reject"}
                      </Button>
                      <Button
                        className="flex-1 h-auto py-2.5 px-4 rounded-[10px] bg-emerald-600 hover:bg-emerald-700 text-white"
                        onClick={() => approve.mutate()}
                        disabled={approve.isPending || reject.isPending || !canSubmit}
                      >
                        {approve.isPending ? "Approving…" : "Approve"}
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {req.status !== "pending" && (req.admin_notes || req.reviewed_by_name || req.reviewed_at) && (
              <Card>
                <CardContent className="p-4 space-y-1.5">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Review & Admin Notes</p>
                  {(req.reviewed_by_name || req.reviewed_at) && (
                    <p className="text-xs text-muted-foreground">
                      Reviewed{req.reviewed_by_name ? ` by ${req.reviewed_by_name}` : ""}
                      {req.reviewed_at ? ` on ${new Date(req.reviewed_at).toLocaleString()}` : ""}
                    </p>
                  )}
                  {req.admin_notes && <p className="text-sm text-foreground">{req.admin_notes}</p>}
                </CardContent>
              </Card>
            )}

            {req.status === "approved" && Boolean(req.resolution?.routed_to_onboarding) && (
              <Card>
                <CardContent className="p-4 flex flex-col gap-1">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Pipeline Status</p>
                  <p className="text-sm font-medium text-primary">Routed to Instructor Onboarding Pipeline</p>
                  <p className="text-xs text-muted-foreground">Letter will be finalized and both [intern, instructor] roles granted upon applicant graduation.</p>
                </CardContent>
              </Card>
            )}

            {req.status === "approved" && (Object.keys(req.resolution ?? {}).length > 0 || req.intern_profile) && (
              <Card>
                <CardContent className="p-4 flex flex-col gap-2">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Resolution & Internship Letter</p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-xs">
                    {req.resolution?.ref_number != null && (
                      <p><span className="text-muted-foreground">Ref Number: </span><span className="font-mono text-foreground">{String(req.resolution.ref_number)}</span></p>
                    )}
                    {(req.final_city_name || req.intern_profile?.work_city_name) && (
                      <p><span className="text-muted-foreground">Work City: </span>{req.final_city_name ?? req.intern_profile?.work_city_name}</p>
                    )}
                    {(req.resolution?.final_start_date != null || req.intern_profile?.start_date) && (
                      <p><span className="text-muted-foreground">Start Date: </span>{String(req.resolution?.final_start_date ?? req.intern_profile?.start_date)}</p>
                    )}
                    {(req.resolution?.final_duration_weeks != null || req.intern_profile?.duration_weeks != null) && (
                      <p><span className="text-muted-foreground">Duration: </span>{String(req.resolution?.final_duration_weeks ?? req.intern_profile?.duration_weeks)} weeks</p>
                    )}
                    {(req.resolution?.final_hours_per_week != null || req.intern_profile?.hours_per_week != null) && (
                      <p><span className="text-muted-foreground">Hours / Week: </span>{String(req.resolution?.final_hours_per_week ?? req.intern_profile?.hours_per_week)}</p>
                    )}
                    {req.intern_profile?.department && (
                      <p><span className="text-muted-foreground">Department: </span>{req.intern_profile.department}</p>
                    )}
                    {(req.resolution?.supervisor_name != null || req.intern_profile?.supervisor_name) && (
                      <p><span className="text-muted-foreground">Supervisor: </span>{String(req.resolution?.supervisor_name ?? req.intern_profile?.supervisor_name)}</p>
                    )}
                    {(req.resolution?.supervisor_email != null || req.intern_profile?.supervisor_email) && (
                      <p><span className="text-muted-foreground">Supervisor Email: </span>{String(req.resolution?.supervisor_email ?? req.intern_profile?.supervisor_email)}</p>
                    )}
                    {(req.resolution?.supervisor_phone != null || req.intern_profile?.supervisor_phone) && (
                      <p><span className="text-muted-foreground">Supervisor Phone: </span>{String(req.resolution?.supervisor_phone ?? req.intern_profile?.supervisor_phone)}</p>
                    )}
                  </div>
                  {(req.intern_profile?.letter_url || req.intern_profile?.signed_letter_url) && (
                    <div className="flex flex-wrap gap-3 pt-2 border-t border-border">
                      {req.intern_profile.letter_url && (
                        <a
                          href={req.intern_profile.letter_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                        >
                          <FileText size={13} /> Offer Letter <ExternalLink size={11} />
                        </a>
                      )}
                      {req.intern_profile.signed_letter_url && (
                        <a
                          href={req.intern_profile.signed_letter_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                        >
                          <FileText size={13} /> Signed Letter{req.intern_profile.letter_signed_at ? ` (${new Date(req.intern_profile.letter_signed_at).toLocaleDateString()})` : ""} <ExternalLink size={11} />
                        </a>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
            <ResolvedAnswersSection answers={req.resolved_answers} />
            <PlatformFootprintSection footprint={req.platform_footprint} />
          </div>
        </div>
      </div>
    </div>
  )
}
