import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronDown, ChevronUp, Trash2 } from "lucide-react"
import type { Cohort, Session, EligibleInstructor, StaffingStatus } from "@/types/sessions"
import {
  listCohortCallsApi, openCohortCallApi, closeCohortCallApi, deleteCohortCallApi, listEligibleInstructorsApi,
  type CohortCall,
} from "@/api/sessions/staffing"
import { Modal, Field, ModalActions, ConfirmDialog, EmptyState } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { cn, getErrorMessage } from "@/lib/utils"

const STAFFING_STATUS_COLOR: Record<StaffingStatus, string> = {
  unstaffed: "bg-muted text-muted-foreground",
  open_call: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400",
  staffed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
}

const CALL_STATUS_COLOR: Record<"open" | "closed", string> = {
  open: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400",
  closed: "bg-muted text-muted-foreground",
}

/* ================================================================== */
/* Cohort calls — a "grouped" open call spanning several sessions,      */
/* manageable and closeable as one entity (2026-08-01). Sibling to      */
/* SessionDetail's per-session StaffingSection, not a shared component: */
/* the "pick which sessions" step here has no session-level analogue.   */
/* ================================================================== */
export function CohortCallsPanel({ cohort, sessions }: { cohort: Cohort; sessions: Session[] }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [openModal, setOpenModal] = useState(false)
  const [closeTarget, setCloseTarget] = useState<CohortCall | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<CohortCall | null>(null)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  const { data: calls = [], isLoading } = useQuery<CohortCall[]>({
    queryKey: ["cohort-calls", cohort.id],
    queryFn: () => listCohortCallsApi(cohort.id),
  })
  // The API already orders most-recent-first — sort defensively in case that
  // changes, so this list never silently buries the newest call.
  const sortedCalls = [...calls].sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""))

  // Platform-wide instructor|facilitator roster, same source every other
  // targeting picker uses — just for turning a call's target_user_ids into
  // names instead of a bare count. Any session in the cohort works as the
  // lookup key since eligible-instructors isn't actually session-specific.
  const { data: roster = [] } = useQuery<EligibleInstructor[]>({
    queryKey: ["staffing-eligible-instructors", sessions[0]?.id],
    queryFn: () => listEligibleInstructorsApi(sessions[0].id),
    enabled: sessions.length > 0,
  })
  const nameById = new Map(roster.map((u) => [u.user_id, u.full_name || u.email]))

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["cohort-calls", cohort.id] })
    // Closing/opening a cohort call changes sessions' own staffing_status.
    qc.invalidateQueries({ queryKey: ["sessions-sessions", cohort.id] })
  }

  const closeAllMutation = useMutation({
    mutationFn: (callId: string) => closeCohortCallApi(cohort.id, callId),
    onSuccess: () => { toast.success("Call closed"); invalidate() },
  })
  const deleteMutation = useMutation({
    mutationFn: (callId: string) => deleteCohortCallApi(cohort.id, callId),
    onSuccess: () => { toast.success("Call deleted"); setDeleteTarget(null); invalidate() },
  })

  const toggleExpanded = (id: string) => setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Cohort calls{sortedCalls.length > 0 ? ` (${sortedCalls.length})` : ""}
        </p>
        <button
          onClick={() => setOpenModal(true)}
          className="h-7 px-2.5 border border-border rounded-lg text-xs font-medium text-foreground hover:bg-muted transition-colors"
        >
          Open cohort call…
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : sortedCalls.length === 0 ? (
        <EmptyState title="No cohort-wide calls yet" />
      ) : (
        <div className="flex flex-col gap-2">
          {sortedCalls.map((c) => {
            const isExpanded = expanded[c.id] ?? false
            const openSessionsCount = c.sessions.filter((s) => s.status === "open").length
            return (
              <div key={c.id} className="border border-border rounded-xl bg-background overflow-hidden">
                <div className="flex items-center justify-between gap-2 p-3">
                  <button
                    onClick={() => toggleExpanded(c.id)}
                    className="min-w-0 flex-1 flex items-center gap-2 text-left"
                  >
                    {isExpanded
                      ? <ChevronUp size={14} className="shrink-0 text-muted-foreground" />
                      : <ChevronDown size={14} className="shrink-0 text-muted-foreground" />}
                    <span className="min-w-0">
                      <span className="text-sm font-medium text-foreground truncate block">
                        {c.label || "Untitled call"}
                      </span>
                      <span className="text-xs text-muted-foreground truncate block">
                        {c.target_user_ids.length === 0
                          ? "Public"
                          : `Targeted: ${c.target_user_ids.map((id) => nameById.get(id) ?? "Unknown").join(", ")}`}
                        {" · "}{c.sessions.length} session{c.sessions.length === 1 ? "" : "s"}
                      </span>
                    </span>
                  </button>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full shrink-0 ${CALL_STATUS_COLOR[c.status]}`}>
                    {c.status === "open" ? "Open" : "Closed"}
                  </span>
                  {c.status === "open" ? (
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => setCloseTarget(c)}
                        className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                      >
                        Close…
                      </button>
                      <button
                        onClick={() => closeAllMutation.mutate(c.id)}
                        disabled={closeAllMutation.isPending || openSessionsCount === 0}
                        className="text-xs font-medium text-red-500 hover:text-red-600 transition-colors disabled:opacity-40"
                      >
                        Close all
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setDeleteTarget(c)}
                      disabled={deleteMutation.isPending}
                      className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors disabled:opacity-50 shrink-0"
                      title="Delete this closed call"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
                {isExpanded && (
                  <div className="border-t border-border px-3 py-2 flex flex-col gap-1">
                    {c.sessions.map((s) => (
                      <div key={s.session_id} className="flex items-center gap-2 text-xs">
                        <span
                          className={cn(
                            "w-1.5 h-1.5 rounded-full shrink-0",
                            s.status === "open" ? "bg-blue-500" : "bg-muted-foreground/40",
                          )}
                          title={s.status === "open" ? "Still open" : "Closed"}
                        />
                        <span className="text-foreground">
                          {s.meeting_date}{s.starts_at ? ` · ${s.starts_at.slice(0, 5)}` : ""}
                        </span>
                        <span className={`ml-auto text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${STAFFING_STATUS_COLOR[s.staffing_status]}`}>
                          {s.staffing_status}
                        </span>
                      </div>
                    ))}
                    {c.sessions.length === 0 && (
                      <p className="text-xs text-muted-foreground">No sessions under this call.</p>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {openModal && (
        <OpenCohortCallModal
          cohort={cohort} sessions={sessions}
          onClose={() => setOpenModal(false)}
          onDone={() => { invalidate(); setOpenModal(false) }}
        />
      )}
      {closeTarget && (
        <CloseCohortCallModal
          cohort={cohort} call={closeTarget}
          onClose={() => setCloseTarget(null)}
          onDone={() => { invalidate(); setCloseTarget(null) }}
        />
      )}
      {deleteTarget && (
        <ConfirmDialog
          title="Delete this closed call?"
          description="This can't be undone."
          confirmLabel="Delete call"
          destructive
          pending={deleteMutation.isPending}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
        />
      )}
    </div>
  )
}

/* ================================================================== */
/* Open a new cohort call — pick sessions (defaults to every currently  */
/* unstaffed one), optionally restrict to specific instructors, and     */
/* optionally label it.                                                 */
/* ================================================================== */
function OpenCohortCallModal({ cohort, sessions, onClose, onDone }: {
  cohort: Cohort; sessions: Session[]; onClose: () => void; onDone: () => void
}) {
  const toast = useToast()
  const [selectedSessionIds, setSelectedSessionIds] = useState<string[]>(
    sessions.filter((s) => s.staffing_status === "unstaffed").map((s) => s.id),
  )
  const [targeted, setTargeted] = useState(false)
  const [selectedUserIds, setSelectedUserIds] = useState<string[]>([])
  const [label, setLabel] = useState("")
  const [error, setError] = useState("")

  const { data: eligible = [] } = useQuery<EligibleInstructor[]>({
    queryKey: ["staffing-eligible-instructors", selectedSessionIds[0]],
    queryFn: () => listEligibleInstructorsApi(selectedSessionIds[0]),
    enabled: selectedSessionIds.length > 0 && targeted,
  })

  const toggleSession = (id: string) =>
    setSelectedSessionIds((prev) => prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id])
  const toggleUser = (id: string) =>
    setSelectedUserIds((prev) => prev.includes(id) ? prev.filter((u) => u !== id) : [...prev, id])

  const mutation = useMutation({
    mutationFn: () => openCohortCallApi(cohort.id, {
      session_ids: selectedSessionIds.length > 0 ? selectedSessionIds : undefined,
      user_ids: targeted ? selectedUserIds : undefined,
      label: label.trim() || undefined,
    }),
    onSuccess: (r) => { if (r.failed.length === 0) { toast.success(`Call opened for ${r.call.sessions.length} session(s)`); onDone() } },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to open the cohort call")),
  })

  return (
    <Modal title="Open a cohort-wide call" onClose={onClose} maxWidth="max-w-md">
      <div className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">
          Groups every checked session under one call you can track and close together. Every currently
          unstaffed session is checked by default.
        </p>
        <Field label="Sessions">
          {sessions.length > 0 && (
            <label className="flex items-center gap-2 text-xs font-medium text-foreground cursor-pointer select-none mb-1">
              <input
                type="checkbox"
                checked={selectedSessionIds.length === sessions.length}
                onChange={() => setSelectedSessionIds(
                  selectedSessionIds.length === sessions.length ? [] : sessions.map((s) => s.id),
                )}
              />
              Select all
            </label>
          )}
          <div className="flex flex-col gap-1 max-h-48 overflow-y-auto pr-1 border border-border rounded-xl p-2">
            {sessions.map((s) => (
              <label key={s.id} className="flex items-center gap-2.5 p-1.5 rounded-lg cursor-pointer hover:bg-muted/40">
                <input
                  type="checkbox" checked={selectedSessionIds.includes(s.id)}
                  onChange={() => toggleSession(s.id)}
                />
                <span className="text-sm text-foreground truncate min-w-0 flex-1">
                  {s.meeting_date}{s.starts_at ? ` · ${s.starts_at.slice(0, 5)}` : ""}{s.title ? ` · ${s.title}` : ""}
                </span>
                <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full shrink-0 ${STAFFING_STATUS_COLOR[s.staffing_status]}`}>
                  {s.staffing_status}
                </span>
              </label>
            ))}
            {sessions.length === 0 && <p className="text-xs text-muted-foreground p-1.5">No sessions in this cohort yet.</p>}
          </div>
        </Field>
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
        <ModalActions
          onCancel={onClose}
          onConfirm={() => { setError(""); mutation.mutate() }}
          loading={mutation.isPending}
          disabled={selectedSessionIds.length === 0 || (targeted && selectedUserIds.length === 0)}
          label="Open call"
        />
      </div>
    </Modal>
  )
}

/* ================================================================== */
/* Close a cohort call — subset picker, defaulting to every still-open  */
/* session under it; the panel's own "Close all" button skips this      */
/* modal entirely and closes with no session_ids.                       */
/* ================================================================== */
function CloseCohortCallModal({ cohort, call, onClose, onDone }: {
  cohort: Cohort; call: CohortCall; onClose: () => void; onDone: () => void
}) {
  const toast = useToast()
  const openSessions = call.sessions.filter((s) => s.status === "open")
  const [selectedIds, setSelectedIds] = useState<string[]>(openSessions.map((s) => s.session_id))
  const [clearInterest, setClearInterest] = useState(false)
  const [error, setError] = useState("")

  const toggle = (id: string) =>
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id])

  const mutation = useMutation({
    mutationFn: () => closeCohortCallApi(cohort.id, call.id, {
      // Omit session_ids when every open session is picked — that's the
      // "close everything still open" shape the API treats specially.
      session_ids: selectedIds.length === openSessions.length ? undefined : selectedIds,
      clear_interest: clearInterest,
    }),
    onSuccess: () => { toast.success("Call closed"); onDone() },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to close that call")),
  })

  return (
    <Modal title={`Close "${call.label || "Untitled call"}"`} onClose={onClose} maxWidth="max-w-md">
      <div className="flex flex-col gap-3">
        <Field label="Sessions to close">
          <div className="flex flex-col gap-1 max-h-52 overflow-y-auto pr-1 border border-border rounded-xl p-2">
            {openSessions.map((s) => (
              <label key={s.session_id} className="flex items-center gap-2.5 p-1.5 rounded-lg cursor-pointer hover:bg-muted/40">
                <input type="checkbox" checked={selectedIds.includes(s.session_id)} onChange={() => toggle(s.session_id)} />
                <span className="text-sm text-foreground truncate">
                  {s.meeting_date}{s.starts_at ? ` · ${s.starts_at.slice(0, 5)}` : ""}
                </span>
              </label>
            ))}
            {openSessions.length === 0 && (
              <p className="text-xs text-muted-foreground p-1.5">Every session under this call is already closed.</p>
            )}
          </div>
        </Field>
        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
          <input type="checkbox" checked={clearInterest} onChange={(e) => setClearInterest(e.target.checked)} />
          Also clear registered interest for these sessions
        </label>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose}
          onConfirm={() => { setError(""); mutation.mutate() }}
          loading={mutation.isPending}
          disabled={selectedIds.length === 0}
          label="Close"
        />
      </div>
    </Modal>
  )
}
