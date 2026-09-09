import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Modal, Field, ModalActions } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"
import { listEligibleInstructorsApi, openCohortCallApi, type CohortCall } from "@/api/sessions/staffing"
import { type BulkActionResult } from "@/api/sessions/cohorts"
import type { Cohort, EligibleInstructor } from "@/types/sessions"

/* ================================================================== */
/* Bulk open call — targeted or public, across N sessions at once      */
/* ================================================================== */
export function BulkOpenCallModal({ cohort, sessionIds, onClose, onDone }: {
  cohort: Cohort; sessionIds: string[]; onClose: () => void; onDone: () => void
}) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [targeted, setTargeted] = useState(false)
  const [selectedUserIds, setSelectedUserIds] = useState<string[]>([])
  const [label, setLabel] = useState("")
  const [error, setError] = useState("")
  const [result, setResult] = useState<{ call: CohortCall; failed: BulkActionResult["failed"] } | null>(null)

  const { data: eligible = [] } = useQuery<EligibleInstructor[]>({
    queryKey: ["staffing-eligible-instructors", sessionIds[0]],
    queryFn: () => listEligibleInstructorsApi(sessionIds[0]),
    enabled: sessionIds.length > 0 && targeted,
  })

  const toggleUser = (id: string) =>
    setSelectedUserIds((prev) => prev.includes(id) ? prev.filter((u) => u !== id) : [...prev, id])

  // 2026-08-01: this now opens a single grouped CohortCall across these
  // sessions (manageable/closeable as one entity from the Cohort Calls
  // panel below) instead of the old ungrouped bulk-open-call endpoint.
  const mutation = useMutation({
    mutationFn: () => openCohortCallApi(cohort.id, {
      session_ids: sessionIds,
      user_ids: targeted ? selectedUserIds : undefined,
      label: label.trim() || undefined,
    }),
    onSuccess: (r) => {
      setResult(r)
      queryClient.invalidateQueries({ queryKey: ["cohort-calls", cohort.id] })
      if (r.failed.length === 0) { toast.success(`Call opened for ${r.call.sessions.length} session(s)`); onDone() }
    },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to open calls")),
  })

  return (
    <Modal title={`Open call for ${sessionIds.length} session(s)`} onClose={onClose} maxWidth="max-w-md">
      <div className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">
          Only sessions that are currently <strong className="text-foreground">unstaffed</strong> will actually
          open — anything already open or staffed is left as it is. Grouped as one call you can track and
          close together from the Cohort Calls panel.
        </p>
        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
          <input type="checkbox" checked={targeted} onChange={(e) => setTargeted(e.target.checked)} />
          Restrict to specific instructors
        </label>
        {targeted && (
          <div className="flex flex-col gap-1.5 max-h-52 overflow-y-auto pr-1 border border-border rounded-xl p-2">
            {eligible.map((u) => (
              <label key={u.user_id} className="flex items-center gap-2.5 p-1.5 rounded-lg cursor-pointer hover:bg-muted/40">
                <input type="checkbox" checked={selectedUserIds.includes(u.user_id)} onChange={() => toggleUser(u.user_id)} />
                <span className="text-sm text-foreground truncate">{u.full_name || u.email}</span>
              </label>
            ))}
            {eligible.length === 0 && <p className="text-xs text-muted-foreground p-1.5">Loading…</p>}
          </div>
        )}
        <Field label="Label (optional)">
          <input
            value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Weekend cover"
            className="w-full h-9 px-3 border border-border bg-background text-foreground rounded-lg text-sm"
          />
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        {result && (
          <p className="text-xs text-muted-foreground">
            Opened {result.call.sessions.length} of {sessionIds.length}.
            {result.failed.length > 0 && ` ${result.failed.length} were skipped (not unstaffed).`}
          </p>
        )}
        <ModalActions
          onCancel={onClose}
          onConfirm={() => { setError(""); setResult(null); mutation.mutate() }}
          loading={mutation.isPending}
          disabled={targeted && selectedUserIds.length === 0}
          label={result ? "Done" : "Open call"}
        />
      </div>
    </Modal>
  )
}
