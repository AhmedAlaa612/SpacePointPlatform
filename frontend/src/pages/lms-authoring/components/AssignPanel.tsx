import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Search, UserPlus, Users, X } from "lucide-react"
import { ROLE_LABEL, type Role } from "@/types/shared"
import { searchStaffApi, type StaffOption } from "@/api/lms_admin"

/** Every role except `student` — staff assignment is deliberately not the
 * self-enrol/self-registration surface (that's /learn's own flow). */
const ASSIGNABLE_ROLES = (Object.keys(ROLE_LABEL) as Role[]).filter((r) => r !== "student")

/** Minimal shape shared by course enrollments and mission assignments — the
 * two backends return differently-named fields (`student_name` vs
 * `user_name`), so the host page maps its own roster type into this before
 * handing it to the panel, rather than the panel importing either type. */
export interface AssignRow {
  /** The enrollment/assignment row id — what revoke takes. */
  id: string
  /** The person's user id — used to hide already-assigned people from the picker. */
  userId: string
  name: string
  email: string
  status: string
}

interface BulkResult {
  granted: number
  already_enrolled?: number
  already_assigned?: number
  skipped_no_account?: number
}

/**
 * Staff course/mission assignment panel (2026-08-12) — the frontend for the
 * `grant_enrollment`/`bulk_grant_enrollment` backend that already existed
 * but had never been wired to any UI. Presentation-only: the host page
 * (`LmsCourseDetail.tsx`, `LmsMissionDetail.tsx`) owns the
 * roster query and grant/bulk-grant/revoke mutations and passes them in, so
 * this one component works for both courses and missions.
 */
export function AssignPanel({
  roster,
  isLoading,
  onGrant,
  onBulkGrant,
  onRevoke,
  grantPending,
  bulkPending,
  revokePending,
  bulkResult,
}: {
  roster: AssignRow[]
  isLoading: boolean
  onGrant: (userId: string) => void
  onBulkGrant: (role: string) => void
  onRevoke: (assignmentId: string) => void
  grantPending: boolean
  bulkPending: boolean
  revokePending: boolean
  bulkResult?: BulkResult | null
}) {
  const [query, setQuery] = useState("")
  const [bulkRole, setBulkRole] = useState<Role | "">("")

  // Runs with an empty query too — the panel should show who's assignable
  // the moment it opens, not sit blank until you guess a name. The backend
  // caps at 25 rows, so an unfiltered list is a picker, not a dump.
  const { data: options = [], isFetching } = useQuery({
    queryKey: ["lms-admin-staff-search", query],
    queryFn: () => searchStaffApi({ q: query || undefined }),
  })

  // Don't offer people who already have access — the roster below is where
  // those are managed, and listing them twice invites a pointless re-grant.
  const assignedIds = new Set(roster.filter((r) => r.status === "active").map((r) => r.userId))
  const assignable = options.filter((o) => !assignedIds.has(o.id))

  // The host page is responsible for pre-filtering `roster` to ops-granted,
  // active rows (e.g. a course's roster can also contain self-enrolled
  // students, which don't belong on this grant/revoke surface) — this
  // panel just renders whatever it's handed.
  const active = roster.filter((r) => r.status === "active")

  return (
    <div className="flex flex-col gap-4 p-4 bg-card border border-border rounded-2xl">
      <div className="flex items-center gap-2">
        <Users size={16} className="text-muted-foreground" />
        <h3 className="text-sm font-medium text-foreground">Assigned access</h3>
        <span className="text-xs text-muted-foreground">({active.length})</span>
      </div>

      {/* named-individual search + assign */}
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search staff by name or email..."
          className="w-full h-9 pl-8 pr-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
        />
      </div>
      <div className="flex flex-col gap-1 max-h-48 overflow-y-auto">
        {isFetching && assignable.length === 0 && (
          <p className="text-xs text-muted-foreground px-1">Loading staff…</p>
        )}
        {!isFetching && assignable.length === 0 && (
          <p className="text-xs text-muted-foreground px-1">
            {query.trim()
              ? "No matching staff accounts."
              : options.length > 0
                ? "Everyone found already has access."
                : "No staff accounts found."}
          </p>
        )}
        {assignable.map((opt: StaffOption) => (
          <button
            key={opt.id}
            onClick={() => { onGrant(opt.id); setQuery("") }}
            disabled={grantPending}
            className="flex items-center justify-between gap-2 h-9 px-3 rounded-lg text-sm text-left hover:bg-muted transition-colors disabled:opacity-50"
          >
            <span className="truncate">
              {opt.full_name} <span className="text-xs text-muted-foreground">{opt.email}</span>
            </span>
            <UserPlus size={14} className="text-muted-foreground shrink-0" />
          </button>
        ))}
      </div>

      {/* bulk-assign by role */}
      <div className="flex items-center gap-2 pt-1 border-t border-border">
        <select
          value={bulkRole}
          onChange={(e) => setBulkRole(e.target.value as Role | "")}
          className="flex-1 h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="">Assign to everyone with role...</option>
          {ASSIGNABLE_ROLES.map((r) => (
            <option key={r} value={r}>{ROLE_LABEL[r]}</option>
          ))}
        </select>
        <button
          onClick={() => bulkRole && onBulkGrant(bulkRole)}
          disabled={!bulkRole || bulkPending}
          className="h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors disabled:opacity-50"
        >
          Assign
        </button>
      </div>
      {bulkResult && (
        <p className="text-xs text-muted-foreground -mt-2">
          Assigned {bulkResult.granted}, already had access {bulkResult.already_enrolled ?? bulkResult.already_assigned ?? 0}
          {bulkResult.skipped_no_account ? `, ${bulkResult.skipped_no_account} skipped (no account)` : ""}.
        </p>
      )}

      {/* roster */}
      <div className="flex flex-col gap-1 pt-1 border-t border-border">
        {isLoading && <p className="text-xs text-muted-foreground px-1">Loading roster...</p>}
        {!isLoading && active.length === 0 && (
          <p className="text-xs text-muted-foreground px-1">No staff assigned yet.</p>
        )}
        {active.map((e) => (
          <div key={e.id} className="flex items-center justify-between gap-2 h-9 px-1 text-sm">
            <span className="truncate">
              {e.name} <span className="text-xs text-muted-foreground">{e.email}</span>
            </span>
            <button
              onClick={() => onRevoke(e.id)}
              disabled={revokePending}
              className="shrink-0 text-muted-foreground hover:text-red-600 transition-colors disabled:opacity-50"
              title="Remove access"
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
