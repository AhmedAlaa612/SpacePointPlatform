import { useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Bus, Check, CheckCircle2, LifeBuoy, MapPin, Plane, Star, Trash2, XCircle } from "lucide-react"
import { getDeliveryRolesApi, type DeliveryRole } from "@/api/sessions/openings"
import {
  listCohortApplicantsApi,
  listCohortAssignmentsApi,
  listCohortCallsApi,
  removeCohortAssignmentApi,
  selectForCohortApi,
} from "@/api/sessions/staffing"
import type { Cohort, CohortCallApplicant } from "@/types/sessions"
import { Button } from "@/components/ui/button"
import { ConfirmDialog, IconBadge as Badge, Modal, Spinner } from "@/pages/admin/components/common"
import { UserProfileModal } from "@/components/UserProfileModal"
import { AssessmentReviewModal } from "@/components/AssessmentReview"
import { cn, getErrorMessage } from "@/lib/utils"

function ApplicantDetailModal({
  applicant,
  callSessions,
  deliveryRoles,
  onClose,
  onOpenProfile,
  onAssignSingle,
  assignSinglePending,
  onViewAnswers,
}: {
  applicant: CohortCallApplicant
  callSessions: { session_id: string; title?: string | null; meeting_date: string; starts_at?: string | null }[]
  deliveryRoles: DeliveryRole[]
  onClose: () => void
  onOpenProfile: (userId: string) => void
  onAssignSingle: (userId: string, roleId?: string) => void
  assignSinglePending: boolean
  onViewAnswers: (userId: string, name: string) => void
}) {
  const [modalRoleId, setModalRoleId] = useState<string>(applicant.role_id ?? deliveryRoles[0]?.id ?? "")

  return (
    <Modal onClose={onClose} title={`Applicant Details — ${applicant.full_name}`} maxWidth="max-w-2xl">
      <div className="flex flex-col gap-4 py-1 max-h-[70vh] overflow-y-auto pr-1">
        {/* Profile / Basic Info Card */}
        <div className="p-3.5 rounded-xl border border-border bg-card flex flex-col gap-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <button
                type="button"
                onClick={() => { onClose(); onOpenProfile(applicant.user_id) }}
                className="font-semibold text-base text-foreground hover:text-primary hover:underline text-left"
              >
                {applicant.full_name}
              </button>
              <p className="text-xs text-muted-foreground">{applicant.email}</p>
            </div>
            {applicant.role_name && (
              <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-primary/10 text-primary border border-primary/20 shrink-0">
                Asked for: {applicant.role_name}
              </span>
            )}
          </div>

          <div className="flex flex-wrap gap-1.5 pt-1">
            {applicant.available_in_city && <Badge icon={MapPin} label="works in this city" tone="good" />}
            {applicant.needs_transport && <Badge icon={Bus} label="needs transport" />}
            {applicant.travelling_from_other_city && <Badge icon={Plane} label="another city" />}
            {applicant.needs_ops_support && <Badge icon={LifeBuoy} label="needs ops support" />}
            {applicant.already_assigned && <Badge icon={Check} label="assigned" tone="good" />}
          </div>
        </div>

        {/* Sessions Breakdown */}
        <div className="flex flex-col gap-2">
          <p className="text-xs font-semibold text-foreground uppercase tracking-wide">
            Session Availability ({applicant.session_count} of {callSessions.length} sessions)
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {callSessions.map((s) => {
              const attending = applicant.session_ids.includes(s.session_id)
              return (
                <div
                  key={s.session_id}
                  className={cn(
                    "p-2.5 rounded-xl border text-xs flex items-center justify-between gap-2",
                    attending
                      ? "border-emerald-500/30 bg-emerald-500/5 text-foreground"
                      : "border-border bg-muted/30 text-muted-foreground"
                  )}
                >
                  <div className="min-w-0">
                    <p className="font-medium truncate">{s.meeting_date}{s.starts_at ? ` · ${s.starts_at.slice(0, 5)}` : ""}</p>
                    {s.title && <p className="text-[11px] text-muted-foreground truncate">{s.title}</p>}
                  </div>
                  <span className={cn("shrink-0 font-semibold px-2 py-0.5 rounded-full text-[10px] inline-flex items-center gap-1", attending ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300" : "bg-muted text-muted-foreground")}>
                    {attending ? <CheckCircle2 size={11} /> : <XCircle size={11} />}
                    {attending ? "Attending" : "Cannot attend"}
                  </span>
                </div>
              )
            })}
          </div>
        </div>

        {/* Cover Letter */}
        {applicant.note && (
          <div className="flex flex-col gap-1.5">
            <p className="text-xs font-semibold text-foreground uppercase tracking-wide">Cover Letter / Note</p>
            <div className="p-3 rounded-xl border border-border bg-card text-xs text-foreground whitespace-pre-line leading-relaxed">
              {applicant.note}
            </div>
          </div>
        )}

        {/* Constraints / Support Needed */}
        {applicant.concerns && (
          <div className="flex flex-col gap-1.5">
            <p className="text-xs font-semibold text-foreground uppercase tracking-wide">Constraints &amp; Support Needed</p>
            <div className="p-3 rounded-xl border border-border bg-card text-xs text-foreground whitespace-pre-line leading-relaxed">
              {applicant.concerns}
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-border">
        {!applicant.already_assigned ? (
          <div className="flex flex-wrap items-center gap-2">
            <select
              className="input h-9 text-xs w-auto bg-background"
              value={modalRoleId}
              onChange={(e) => setModalRoleId(e.target.value)}
            >
              {deliveryRoles.map((r) => (
                <option key={r.id} value={r.id}>
                  Assign as {r.name} {r.id === applicant.role_id ? "(Asked)" : ""}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              disabled={assignSinglePending}
              onClick={() => onAssignSingle(applicant.user_id, modalRoleId || undefined)}
            >
              {assignSinglePending ? "Assigning…" : "Assign Instructor"}
            </Button>
          </div>
        ) : (
          <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
            <Check size={14} /> Already Assigned
          </span>
        )}

        <div className="flex items-center gap-2 ml-auto">
          {applicant.quiz_score != null && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => { onClose(); onViewAnswers(applicant.user_id, applicant.full_name) }}
            >
              View answers
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={() => { onClose(); onOpenProfile(applicant.user_id) }}
          >
            View Profile
          </Button>
          <Button size="sm" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function CohortStaffingPanel({ cohort }: { cohort: Cohort }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [callId, setCallId] = useState<string | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [overrideRoleId, setOverrideRoleId] = useState<string | null>(null)
  const [error, setError] = useState("")
  const [removing, setRemoving] = useState<{ userId: string; name: string } | null>(null)
  const [selectedProfileUserId, setSelectedProfileUserId] = useState<string | null>(null)
  const [selectedApplicantDetail, setSelectedApplicantDetail] = useState<CohortCallApplicant | null>(null)
  const [reviewTarget, setReviewTarget] = useState<{ userId: string; name: string } | null>(null)

  const deliveryRoles = useQuery({
    queryKey: ["delivery-roles"],
    queryFn: () => getDeliveryRolesApi(),
  })

  const calls = useQuery({
    queryKey: ["cohort-calls", cohort.id],
    queryFn: () => listCohortCallsApi(cohort.id),
  })
  const activeCallId = callId ?? calls.data?.find((c) => c.status === "open")?.id ?? calls.data?.[0]?.id ?? null
  const activeCall = calls.data?.find((c) => c.id === activeCallId)
  const totalCallSessions = activeCall?.sessions.length ?? 0

  const applicants = useQuery({
    queryKey: ["cohort-applicants", cohort.id, activeCallId],
    queryFn: () => listCohortApplicantsApi(cohort.id, activeCallId!),
    enabled: !!activeCallId,
  })
  const assignments = useQuery({
    queryKey: ["cohort-assignments", cohort.id],
    queryFn: () => listCohortAssignmentsApi(cohort.id),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["cohort-applicants", cohort.id] })
    qc.invalidateQueries({ queryKey: ["cohort-assignments", cohort.id] })
    qc.invalidateQueries({ queryKey: ["cohort-calls", cohort.id] })
    qc.invalidateQueries({ queryKey: ["cohort-sessions", cohort.id] })
  }

  const assign = useMutation({
    mutationFn: (customUserIds?: string[]) =>
      selectForCohortApi(cohort.id, {
        user_ids: customUserIds ?? selected,
        cohort_call_id: activeCallId,
        role_id: overrideRoleId,
      }),
    onSuccess: () => { setError(""); setSelected([]); invalidate() },
    onError: (e) => setError(getErrorMessage(e, "Could not assign those instructors")),
  })

  const assignSingle = useMutation({
    mutationFn: ({ userId, roleId }: { userId: string; roleId?: string }) =>
      selectForCohortApi(cohort.id, {
        user_ids: [userId],
        cohort_call_id: activeCallId,
        role_id: roleId,
      }),
    onSuccess: () => { setError(""); setSelectedApplicantDetail(null); invalidate() },
    onError: (e) => setError(getErrorMessage(e, "Could not assign instructor")),
  })

  const remove = useMutation({
    mutationFn: (userId: string) => removeCohortAssignmentApi(cohort.id, userId),
    onSuccess: () => { setRemoving(null); invalidate() },
    onError: (e) => setError(getErrorMessage(e, "Could not remove that assignment")),
  })

  const rows = applicants.data ?? []
  const pickable = rows.filter((r) => !r.already_assigned)
  const staffed = (assignments.data ?? []).filter((a) => a.status === "active")

  const toggle = (id: string) =>
    setSelected((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])

  return (
    <div className="py-4 space-y-6">
      <div>
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <div>
            <h3 className="font-semibold text-sm">Applicants</h3>
            <p className="text-xs text-muted-foreground">
              One row per instructor — the role they asked for and the sessions they can do.
            </p>
          </div>
          {(calls.data ?? []).length > 1 && (
            <select
              className="input h-8 text-xs w-auto"
              value={activeCallId ?? ""}
              onChange={(e) => { setCallId(e.target.value); setSelected([]) }}
            >
              {calls.data!.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label || "Call"} · {c.status} · {c.sessions.length} sessions
                </option>
              ))}
            </select>
          )}
        </div>

        {calls.isLoading || applicants.isLoading ? (
          <Spinner />
        ) : !activeCallId ? (
          <p className="text-xs text-muted-foreground">
            No cohort call yet — open one below and applicants will appear here.
          </p>
        ) : rows.length === 0 ? (
          <p className="text-xs text-muted-foreground">Nobody has registered interest yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground border-b border-border">
                  <th className="py-2 pr-2 w-8"></th>
                  <th className="py-2 pr-3">Instructor</th>
                  <th className="py-2 pr-3">Role</th>
                  <th className="py-2 pr-3">Sessions</th>
                  <th className="py-2 pr-3">Priority</th>
                  <th className="py-2 pr-3 text-right">Details</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.user_id} className="border-b border-border/60 align-top">
                    <td className="py-2.5 pr-2">
                      <input
                        type="checkbox"
                        disabled={r.already_assigned}
                        checked={selected.includes(r.user_id)}
                        onChange={() => toggle(r.user_id)}
                        className="rounded text-primary focus:ring-primary border-border bg-background cursor-pointer"
                      />
                    </td>
                    <td className="py-2 pr-3">
                      <button
                        type="button"
                        onClick={() => setSelectedProfileUserId(r.user_id)}
                        className="font-medium text-foreground text-left hover:text-primary hover:underline transition-colors"
                      >
                        {r.full_name}
                      </button>
                      <p className="text-[11px] text-muted-foreground">{r.email}</p>
                      {r.already_assigned && (
                        <div className="mt-1">
                          <Badge icon={Check} label="assigned" tone="good" />
                        </div>
                      )}
                    </td>
                    <td className="py-2 pr-3 whitespace-nowrap pt-2.5 font-medium">{r.role_name ?? "—"}</td>
                    <td className="py-2 pr-3 whitespace-nowrap tabular-nums pt-2.5">
                      <span className="font-semibold text-foreground">{r.session_count}</span>
                      <span className="text-muted-foreground text-xs">/{totalCallSessions} sessions</span>
                    </td>
                    <td className="py-2 pr-3 whitespace-nowrap tabular-nums pt-2.5">
                      {r.priority_score != null ? (
                        <span className="font-semibold text-foreground">{r.priority_score}</span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                      {r.quiz_score != null && (
                        <p className="text-[11px] text-muted-foreground font-normal">Quiz {r.quiz_score}%</p>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-right whitespace-nowrap pt-2">
                      <Button
                        type="button"
                        size="xs"
                        variant="outline"
                        onClick={() => setSelectedApplicantDetail(r)}
                        className="rounded-lg text-xs"
                      >
                        View details
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="flex flex-wrap items-center gap-3 mt-3">
              <Button
                size="sm"
                disabled={selected.length === 0 || assign.isPending}
                onClick={() => { setError(""); assign.mutate(undefined) }}
              >
                {assign.isPending ? "Assigning…" : `Assign selected (${selected.length})`}
              </Button>

              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span>Role:</span>
                <select
                  className="input h-8 text-xs py-0 px-2 w-auto bg-background"
                  value={overrideRoleId ?? ""}
                  onChange={(e) => setOverrideRoleId(e.target.value || null)}
                >
                  <option value="">Role applied for (default)</option>
                  {deliveryRoles.data?.map((r) => (
                    <option key={r.id} value={r.id}>
                      Assign as {r.name}
                    </option>
                  ))}
                </select>
              </div>

              {pickable.length > 0 && (
                <button
                  type="button"
                  className="text-xs text-primary hover:underline"
                  onClick={() => setSelected(
                    selected.length === pickable.length ? [] : pickable.map((r) => r.user_id),
                  )}
                >
                  {selected.length === pickable.length ? "Clear" : "Select all"}
                </button>
              )}
              <p className="text-xs text-muted-foreground">
                {overrideRoleId
                  ? `Instructors will be assigned as ${deliveryRoles.data?.find(r => r.id === overrideRoleId)?.name ?? 'the selected role'}.`
                  : "Each person gets exactly the days they ticked, in the role they applied for."}
              </p>
            </div>
          </div>
        )}
        {error && <p className="text-xs text-red-600 dark:text-red-400 mt-2">{error}</p>}
      </div>

      <div>
        <h3 className="font-semibold text-sm mb-1">Staffed</h3>
        <p className="text-xs text-muted-foreground mb-3">
          The agreed rate is snapshotted here — editing a cohort rate later won't reprice anyone
          already assigned.
        </p>
        {assignments.isLoading ? (
          <Spinner />
        ) : staffed.length === 0 ? (
          <p className="text-xs text-muted-foreground">Nobody assigned yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground border-b border-border">
                  <th className="py-2 pr-3">Instructor</th>
                  <th className="py-2 pr-3">Role</th>
                  <th className="py-2 pr-3">Sessions</th>
                  <th className="py-2 pr-3">Rate</th>
                  <th className="py-2 pr-3"></th>
                </tr>
              </thead>
              <tbody>
                {staffed.map((a) => (
                  <tr key={a.id} className="border-b border-border/60">
                    <td className="py-2 pr-3">
                      <button
                        type="button"
                        onClick={() => setSelectedProfileUserId(a.user_id)}
                        className="font-medium text-foreground text-left hover:text-primary hover:underline transition-colors"
                      >
                        {a.full_name}
                      </button>
                      <p className="text-[11px] text-muted-foreground">{a.email}</p>
                    </td>
                    <td className="py-2 pr-3 whitespace-nowrap">{a.role_name}</td>
                    <td className="py-2 pr-3 tabular-nums">{a.session_count}</td>
                    <td className="py-2 pr-3 tabular-nums whitespace-nowrap">
                      {a.rate_basis === "flat"
                        ? a.flat_amount_aed != null ? `AED ${a.flat_amount_aed.toLocaleString()} flat` : "flat —"
                        : a.rate_aed != null ? `AED ${a.rate_aed.toLocaleString()}/session` : "—"}
                    </td>
                    <td className="py-2 pr-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          type="button"
                          className="text-muted-foreground hover:text-primary transition-colors"
                          title="Rate this instructor's performance"
                          onClick={() => void navigate({
                            to: `/instructors/admin/ratings/${cohort.id}/${a.user_id}`,
                          })}
                        >
                          <Star size={14} />
                        </button>
                        <button
                          type="button"
                          className="text-muted-foreground hover:text-red-600 transition-colors"
                          title="Remove from this cohort"
                          onClick={() => setRemoving({ userId: a.user_id, name: a.full_name })}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedProfileUserId && (
        <UserProfileModal
          userId={selectedProfileUserId}
          onClose={() => setSelectedProfileUserId(null)}
        />
      )}

      {selectedApplicantDetail && activeCall && (
        <ApplicantDetailModal
          applicant={selectedApplicantDetail}
          callSessions={activeCall.sessions}
          deliveryRoles={deliveryRoles.data ?? []}
          onClose={() => setSelectedApplicantDetail(null)}
          onOpenProfile={(userId) => setSelectedProfileUserId(userId)}
          onAssignSingle={(userId, roleId) => assignSingle.mutate({ userId, roleId })}
          assignSinglePending={assignSingle.isPending}
          onViewAnswers={(userId, name) => setReviewTarget({ userId, name })}
        />
      )}

      {reviewTarget && activeCallId && (
        <AssessmentReviewModal
          title={`${reviewTarget.name}'s Assessment`}
          scope="cohort-call"
          id={activeCallId}
          userId={reviewTarget.userId}
          onClose={() => setReviewTarget(null)}
        />
      )}

      {removing && (
        <ConfirmDialog
          title={`Remove ${removing.name}?`}
          description="They'll be taken off every session in this cohort. The assignment is kept as withdrawn, so the record that they were staffed survives."
          confirmLabel="Remove"
          destructive
          pending={remove.isPending}
          onConfirm={() => remove.mutate(removing.userId)}
          onCancel={() => setRemoving(null)}
        />
      )}
    </div>
  )
}
