import { useMemo, useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { ArrowDown, ArrowUp, CheckCircle2 } from "lucide-react"
import type { Session, StaffingStatus } from "@/types/sessions"
import { EmptyState } from "@/pages/admin/components/common"
import { cn } from "@/lib/utils"

const STAFFING_STATUS_LABEL: Record<StaffingStatus, string> = {
  unstaffed: "Unstaffed",
  open_call: "Open call",
  staffed: "Staffed",
}
const STAFFING_STATUS_DOT: Record<StaffingStatus, string> = {
  unstaffed: "bg-muted-foreground/40",
  open_call: "bg-blue-500",
  staffed: "bg-emerald-500",
}
const STAFFING_RANK: Record<StaffingStatus, number> = { unstaffed: 0, open_call: 1, staffed: 2 }

type SortKey = "date" | "title" | "staffing" | "status" | "location"
type SortDir = "asc" | "desc"

/** Module-level, not defined inside SessionsTable — a component declared
 *  during render gets recreated (and loses any state) on every parent
 *  re-render. This one is stateless, but the lint rule (and the underlying
 *  footgun) doesn't distinguish, so it lives out here like everything else. */
function SortHeader({ label, k, sortKey, sortDir, onSort }: {
  label: string; k: SortKey; sortKey: SortKey; sortDir: SortDir; onSort: (k: SortKey) => void
}) {
  const active = sortKey === k
  return (
    <th
      role="columnheader"
      aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
      tabIndex={0}
      onClick={() => onSort(k)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onSort(k)
        }
      }}
      className="px-3 py-2 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider cursor-pointer select-none whitespace-nowrap hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset"
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {active && (sortDir === "asc" ? <ArrowUp size={11} /> : <ArrowDown size={11} />)}
      </span>
    </th>
  )
}

/**
 * Sortable sessions table (2026-08-01), replacing the wrapped pill-button
 * list that used to sit inline in CohortDetail.tsx. Client-side sort only —
 * a cohort's session list is small, no pagination needed.
 *
 * Status column shows whether the session is Scheduled, In Progress, or Completed,
 * replacing the old materials column.
 */
export function SessionsTable({
  cohortId, sessions, bulkMode, selectedSessionIds, onToggleSession,
}: {
  cohortId: string
  sessions: Session[]
  bulkMode: boolean
  selectedSessionIds: string[]
  onToggleSession: (id: string) => void
}) {
  const navigate = useNavigate()
  const [sortKey, setSortKey] = useState<SortKey>("date")
  const [sortDir, setSortDir] = useState<SortDir>("asc")

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortKey(key)
      setSortDir("asc")
    }
  }

  const sorted = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1
    return [...sessions].sort((a, b) => {
      switch (sortKey) {
        case "date": {
          const av = `${a.meeting_date} ${a.starts_at ?? ""}`
          const bv = `${b.meeting_date} ${b.starts_at ?? ""}`
          return av.localeCompare(bv) * dir
        }
        case "title":
          return (a.title ?? "").localeCompare(b.title ?? "") * dir
        case "staffing":
          return (STAFFING_RANK[a.staffing_status] - STAFFING_RANK[b.staffing_status]) * dir
        case "status": {
          const rank = (s: Session) => s.completed_at ? 2 : s.started_at ? 1 : 0
          return (rank(a) - rank(b)) * dir
        }
        case "location":
          return (a.effective_location_name ?? "").localeCompare(b.effective_location_name ?? "") * dir
        default:
          return 0
      }
    })
  }, [sessions, sortKey, sortDir])

  if (sessions.length === 0) {
    return <EmptyState title="No sessions scheduled yet" />
  }

  return (
    <div className="border border-border rounded-2xl overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-border">
            {bulkMode && <th className="w-8 px-3 py-2" />}
            <SortHeader label="Date" k="date" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
            <SortHeader label="Title" k="title" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
            <SortHeader label="Staffing" k="staffing" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
            <SortHeader label="State" k="status" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
            <th className="px-3 py-2 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">
              Kits
            </th>
            <SortHeader label="Location / warehouse" k="location" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
          </tr>
        </thead>
        <tbody>
          {sorted.map((s) => {
            const selected = selectedSessionIds.includes(s.id)
            return (
              <tr
                key={s.id}
                onClick={() => bulkMode
                  ? onToggleSession(s.id)
                  : void navigate({ to: "/operations/cohorts/$cohortId/sessions/$sessionId", params: { cohortId, sessionId: s.id } })}
                className={cn(
                  "border-b border-border last:border-0 cursor-pointer hover:bg-muted/40 transition-colors",
                  bulkMode && selected && "bg-primary/5",
                )}
              >
                {bulkMode && (
                  <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={selected} onChange={() => onToggleSession(s.id)} />
                  </td>
                )}
                <td className="px-3 py-2 whitespace-nowrap text-foreground">
                  {s.meeting_date}{s.starts_at ? ` · ${s.starts_at.slice(0, 5)}` : ""}
                </td>
                <td className="px-3 py-2 min-w-[10rem] text-foreground">
                  <div className="flex flex-col gap-0.5">
                    <span>{s.title || "—"}</span>
                    {s.instructors.length > 0 && (
                      <span className="text-xs text-muted-foreground">
                        {s.instructors.map((i) => `${i.full_name} (${i.role})`).join(", ")}
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span
                      className={cn("w-1.5 h-1.5 rounded-full shrink-0", STAFFING_STATUS_DOT[s.staffing_status])}
                      title={STAFFING_STATUS_LABEL[s.staffing_status]}
                    />
                    <span className="text-xs text-muted-foreground">{STAFFING_STATUS_LABEL[s.staffing_status]}</span>
                    {s.target_user_ids?.length > 0 && (
                      <span
                        className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-purple-500/15 text-purple-600 dark:text-purple-400 border border-purple-500/20"
                        title={`This call is restricted to ${s.target_user_ids.length} instructor(s) — nobody else can see or take it`}
                      >
                        Targeted · {s.target_user_ids.length}
                      </span>
                    )}
                    {s.interested_count && s.interested_count > 0 ? (
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                        ★ {s.interested_count}
                      </span>
                    ) : null}
                  </div>
                </td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {s.completed_at ? (
                    <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400">
                      <CheckCircle2 size={11} /> Completed
                    </span>
                  ) : s.started_at ? (
                    <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400">
                      In progress
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                      Scheduled
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-xs text-muted-foreground">
                  {s.kits_count ? s.kits_count : "—"}
                </td>
                <td className="px-3 py-2 text-xs text-foreground whitespace-nowrap">
                  {s.effective_location_name ?? "—"}
                  {s.effective_warehouse_name ? (
                    <span className="text-muted-foreground">
                      {" · "}{s.effective_warehouse_name}
                    </span>
                  ) : null}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
