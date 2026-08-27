import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, Clock, XCircle } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import {
  approveRequestApi,
  getApprovalPoliciesApi,
  getApprovalQueueApi,
  getMyApprovalRequestsApi,
  rejectRequestApi,
  setApprovalPolicyApi,
  type ApprovalRequest,
} from "@/api/inventory"
import { Spinner } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { cn } from "@/lib/utils"

type Tab = "pending" | "settings"

/** The approval gate's own surface (2026-08-27 follow-up) — what a COO sees
 *  depends entirely on whether anything actually needs them. Anyone else who
 *  can hit a gated endpoint (operations, storekeeper) only ever sees their
 *  own submissions, never the queue or the settings — those are
 *  `require_inventory_approval` (coo/admin) on the backend too, so this is
 *  just not offering a control that would 403. */
export default function Approvals() {
  const { activeRole } = useAuth()
  const isApprover = activeRole === "coo" || activeRole === "admin"
  return isApprover ? <ApproverView /> : <MyRequestsView />
}

function StatusBadge({ status }: { status: ApprovalRequest["status"] }) {
  if (status === "approved") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400">
        <CheckCircle2 size={12} /> Approved
      </span>
    )
  }
  if (status === "rejected") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400">
        <XCircle size={12} /> Rejected
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
      <Clock size={12} /> Pending
    </span>
  )
}

function MyRequestsView() {
  const { data: requests = [], isLoading } = useQuery({
    queryKey: ["inv-approvals-mine"],
    queryFn: getMyApprovalRequestsApi,
  })

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold text-foreground tracking-tight">My requests</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Anything you submitted that needed a COO's sign-off, and what happened to it.
        </p>
      </div>

      {isLoading ? <Spinner /> : (
        <div className="rounded-2xl border border-border bg-card divide-y divide-border">
          {requests.map((r) => (
            <div key={r.id} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="text-sm text-foreground">{r.summary}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {r.requested_at ? new Date(r.requested_at).toLocaleString() : ""}
                  {r.review_note && ` — "${r.review_note}"`}
                </p>
              </div>
              <StatusBadge status={r.status} />
            </div>
          ))}
          {requests.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-10">
              Nothing waiting on anyone — everything you've submitted went through right away.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function ApproverView() {
  const [tab, setTab] = useState<Tab>("pending")

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold text-foreground tracking-tight">Approvals</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          What's waiting on you, and what needs your sign-off in the first place.
        </p>
      </div>

      <div className="flex gap-1 border-b border-border">
        {([["pending", "Pending"], ["settings", "Settings"]] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === key ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "pending" ? <PendingQueue /> : <PolicySettings />}
    </div>
  )
}

function PendingQueue() {
  const queryClient = useQueryClient()
  const { success } = useToast()
  const [noteDrafts, setNoteDrafts] = useState<Record<string, string>>({})

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ["inv-approvals-pending"],
    queryFn: () => getApprovalQueueApi("pending"),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["inv-approvals-pending"] })
  const approve = useMutation({
    mutationFn: approveRequestApi,
    onSuccess: (r) => { invalidate(); success(`Approved — ${r.summary}`) },
  })
  const reject = useMutation({
    mutationFn: rejectRequestApi,
    onSuccess: (r) => { invalidate(); success(`Rejected — ${r.summary}`) },
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-3">
      {requests.map((r) => (
        <div key={r.id} className="rounded-2xl border border-border bg-card p-4 flex flex-col gap-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-foreground">{r.summary}</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {r.action_label} · requested by {r.requested_by_name}
                {r.requested_at && ` · ${new Date(r.requested_at).toLocaleString()}`}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input
              value={noteDrafts[r.id] ?? ""}
              onChange={(e) => setNoteDrafts((prev) => ({ ...prev, [r.id]: e.target.value }))}
              placeholder="Note (optional)"
              className="flex-1 h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
            />
            <button
              onClick={() => reject.mutate({ id: r.id, note: noteDrafts[r.id] })}
              disabled={reject.isPending || approve.isPending}
              className="h-9 px-3 border border-border text-foreground text-sm font-medium rounded-xl hover:bg-muted/60 disabled:opacity-50"
            >
              Reject
            </button>
            <button
              onClick={() => approve.mutate({ id: r.id, note: noteDrafts[r.id] })}
              disabled={reject.isPending || approve.isPending}
              className="h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 disabled:opacity-50"
            >
              Approve
            </button>
          </div>
        </div>
      ))}
      {requests.length === 0 && (
        <p className="text-sm text-muted-foreground text-center py-10 border border-dashed border-border rounded-2xl">
          Nothing waiting on you right now.
        </p>
      )}
    </div>
  )
}

function PolicySettings() {
  const queryClient = useQueryClient()
  const { data: policies = [], isLoading } = useQuery({
    queryKey: ["inv-approval-policies"],
    queryFn: getApprovalPoliciesApi,
  })

  const toggle = useMutation({
    mutationFn: setApprovalPolicyApi,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["inv-approval-policies"] }),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-4 max-w-2xl">
      <p className="text-sm text-muted-foreground -mt-1">
        Turn one on and anyone who isn't you (or an admin) has to wait for your sign-off before it
        takes effect — nothing happens until you approve or reject it. Off means it works exactly
        like it does today.
      </p>
      <div className="rounded-2xl border border-border bg-card divide-y divide-border">
        {policies.map((p) => (
          <div key={p.action_type} className="flex items-center justify-between px-4 py-3 gap-3">
            <div>
              <p className="text-sm font-medium text-foreground">{p.action_label}</p>
              {p.updated_at && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  Last changed {new Date(p.updated_at).toLocaleDateString()}
                  {p.updated_by_name && ` by ${p.updated_by_name}`}
                </p>
              )}
            </div>
            <label className="inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={p.requires_approval}
                onChange={(e) => toggle.mutate({ actionType: p.action_type, requiresApproval: e.target.checked })}
                disabled={toggle.isPending}
                className="sr-only peer"
              />
              <span className="w-10 h-6 rounded-full bg-muted peer-checked:bg-primary transition-colors relative">
                <span className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-background shadow transition-transform peer-checked:translate-x-4" />
              </span>
            </label>
          </div>
        ))}
      </div>
    </div>
  )
}
