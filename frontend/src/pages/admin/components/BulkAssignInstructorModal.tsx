import { useEffect, useState } from "react"
import { useQuery, useMutation } from "@tanstack/react-query"
import { Modal, Field, ModalActions } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"
import { listEligibleInstructorsApi } from "@/api/sessions/staffing"
import { getDeliveryRolesApi } from "@/api/sessions/openings"
import { bulkAssignInstructorApi, type BulkActionResult } from "@/api/sessions/cohorts"
import type { Cohort, EligibleInstructor } from "@/types/sessions"

export function BulkAssignInstructorModal({ cohort, sessionIds, onClose, onDone }: {
  cohort: Cohort; sessionIds: string[]; onClose: () => void; onDone: () => void
}) {
  const toast = useToast()
  const [userId, setUserId] = useState("")
  const [roleId, setRoleId] = useState("")
  const [error, setError] = useState("")
  const [result, setResult] = useState<BulkActionResult | null>(null)

  // The platform-wide instructor|facilitator roster, same source the
  // "Target Instructors…" picker uses — require_operations, unlike
  // /admin/users, and not scoped to one session's own interest.
  const { data: eligible = [] } = useQuery<EligibleInstructor[]>({
    queryKey: ["staffing-eligible-instructors", sessionIds[0]],
    queryFn: () => listEligibleInstructorsApi(sessionIds[0]),
    enabled: sessionIds.length > 0,
  })
  const { data: deliveryRoles = [] } = useQuery({
    queryKey: ["delivery-roles"], queryFn: () => getDeliveryRolesApi(),
  })
  useEffect(() => {
    if (!roleId && deliveryRoles.length) setRoleId(deliveryRoles[0].id)
  }, [deliveryRoles, roleId])

  const mutation = useMutation({
    mutationFn: () => bulkAssignInstructorApi(cohort.id, { session_ids: sessionIds, user_id: userId, role_id: roleId || undefined }),
    onSuccess: (r) => {
      setResult(r)
      if (r.failed.length === 0) { toast.success(`Assigned to ${r.succeeded.length} session(s)`); onDone() }
    },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to assign")),
  })

  return (
    <Modal title={`Assign instructor to ${sessionIds.length} session(s)`} onClose={onClose} maxWidth="max-w-md">
      <div className="flex flex-col gap-3">
        <Field label="Instructor">
          <select
            value={userId} onChange={(e) => setUserId(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm cursor-pointer"
          >
            <option value="">— Select an instructor —</option>
            {eligible.map((u) => <option key={u.user_id} value={u.user_id}>{u.full_name || u.email}</option>)}
          </select>
        </Field>
        <Field label="Role">
          <select
            value={roleId} onChange={(e) => setRoleId(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm cursor-pointer"
          >
            {deliveryRoles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        {result && result.failed.length > 0 && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            Assigned to {result.succeeded.length} of {sessionIds.length}. {result.failed.length} couldn't be
            assigned — most likely already staffed for that role.
          </p>
        )}
        <ModalActions
          onCancel={onClose}
          onConfirm={() => { setError(""); setResult(null); mutation.mutate() }}
          loading={mutation.isPending}
          disabled={!userId || !roleId}
          label={result ? "Done" : "Assign"}
        />
      </div>
    </Modal>
  )
}
