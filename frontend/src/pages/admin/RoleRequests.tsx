import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { X } from "lucide-react"
import {
  listRoleRequestsAdminApi,
  approveRoleRequestApi,
  rejectRoleRequestApi,
} from "@/api/internship"
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
  const [statusFilter, setStatusFilter] = useState<string>("pending")
  const [selected, setSelected] = useState<string | null>(null)

  const qc = useQueryClient()
  const { data: requests = [], isLoading } = useQuery({
    queryKey: ["admin-role-requests", statusFilter],
    queryFn: () => listRoleRequestsAdminApi({ status: statusFilter !== "all" ? statusFilter : undefined }),
  })

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
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors capitalize ${
              statusFilter === s ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
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
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-[#d6c7e1] text-[#643f83]">
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

  const approve = useMutation({
    mutationFn: () => approveRoleRequestApi(req.id, { ...form, admin_notes: notes || undefined }),
    onSuccess: () => { onChanged(); onClose() },
    onError: (err: any) => alert(err?.response?.data?.detail || "Failed to approve request."),
  })
  const reject = useMutation({
    mutationFn: () => rejectRoleRequestApi(req.id, notes || undefined),
    onSuccess: () => { onChanged(); onClose() },
    onError: (err: any) => alert(err?.response?.data?.detail || "Failed to reject request."),
  })

  const canSubmit = isInternshipApproveComplete(form)

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="bg-background w-full max-w-lg h-screen flex flex-col shadow-2xl border-l border-border">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <p className="text-sm font-semibold text-foreground">Role Request</p>
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:bg-muted transition-colors">
            <X size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <div className="p-5 flex flex-col gap-4">
            <Card>
              <CardContent className="p-4 flex flex-col gap-2">
                <p className="font-semibold text-foreground">{req.requester_name}</p>
                <p className="text-sm text-muted-foreground">{req.requester_email}</p>
                <p className="text-xs text-muted-foreground mt-1">Requesting: <strong>{req.target_role}</strong></p>
                {Object.keys(req.details ?? {}).length > 0 && (
                  <div className="mt-2 flex flex-col gap-1 text-xs">
                    {req.details.university_id_number != null && (
                      <p><span className="text-muted-foreground">University ID: </span>{String(req.details.university_id_number)}</p>
                    )}
                    {req.details.requested_start_date != null && (
                      <p><span className="text-muted-foreground">Requested start: </span>{String(req.details.requested_start_date)}</p>
                    )}
                    {req.details.requested_duration_weeks != null && (
                      <p><span className="text-muted-foreground">Requested duration: </span>{String(req.details.requested_duration_weeks)} weeks</p>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {req.status === "pending" && req.target_role === "intern" && (
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
                  />
                </CardContent>
              </Card>
            )}

            {req.status === "pending" && (
              <Card>
                <CardContent className="p-4 flex flex-col gap-3">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Review</p>
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Admin notes (optional — shown to the requester if you reject)"
                    rows={3}
                    className="w-full p-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none resize-none"
                  />
                  <div className="flex gap-2">
                    <Button variant="outline" className="flex-1 border-red-300 text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10"
                      onClick={() => reject.mutate()} disabled={reject.isPending || approve.isPending}>
                      {reject.isPending ? "Rejecting…" : "Reject"}
                    </Button>
                    <Button className="flex-1 bg-emerald-600 hover:bg-emerald-700"
                      onClick={() => approve.mutate()} disabled={approve.isPending || reject.isPending || !canSubmit}>
                      {approve.isPending ? "Approving…" : "Approve"}
                    </Button>
                  </div>
                  {!canSubmit && req.target_role === "intern" && (
                    <p className="text-[11px] text-muted-foreground">
                      Fill in salutation, activity description, and all supervisor fields before approving.
                    </p>
                  )}
                </CardContent>
              </Card>
            )}

            {req.status !== "pending" && req.admin_notes && (
              <Card>
                <CardContent className="p-4">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">Admin notes</p>
                  <p className="text-sm text-foreground">{req.admin_notes}</p>
                </CardContent>
              </Card>
            )}

            {req.status === "approved" && req.resolution?.ref_number != null && (
              <Card>
                <CardContent className="p-4">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">Assigned Ref Number</p>
                  <p className="text-sm text-foreground">{String(req.resolution.ref_number)}</p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
