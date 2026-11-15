import { useState } from "react"
import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import {
  ArrowRight,
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Layers,
  Ticket,
  Users,
  Warehouse as WarehouseIcon,
} from "lucide-react"
import {
  Line,
  LineChart,
  ResponsiveContainer,
} from "recharts"
import {
  getOpsDashboardOverviewApi,
  type DashboardRange,
  type MilestoneKindFilter,
} from "@/api/sessions/dashboard"
import { AnalysisFunnelWidget } from "@/components/ui/AnalysisFunnelWidget"
import { EmptyState, PageHeader, Spinner } from "@/pages/admin/components/common"
import { cn } from "@/lib/utils"

const RANGE_OPTIONS: { key: DashboardRange; label: string }[] = [
  { key: "1h", label: "1h" },
  { key: "24h", label: "24h" },
  { key: "7d", label: "7d" },
  { key: "30d", label: "30d" },
  { key: "all", label: "All time" },
]

const KIND_FILTERS: { key: MilestoneKindFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "course", label: "Courses" },
  { key: "mission", label: "Missions" },
  { key: "quiz", label: "Quizzes" },
  { key: "team", label: "Teams" },
]

const KIND_LABEL: Record<string, string> = {
  course: "Course",
  mission: "Mission",
  quiz: "Quiz",
  team: "Team",
}

const TONE_BADGE: Record<string, string> = {
  green: "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  purple: "border-primary/40 bg-primary/10 text-primary",
  rose: "border-rose-500/40 bg-rose-500/10 text-rose-600 dark:text-rose-400",
  neutral: "border-border bg-muted/40 text-muted-foreground",
}

function formatRelativeTime(iso: string): string {
  const diffSec = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000))
  if (diffSec < 60) return "just now"
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`
  if (diffSec < 86400 * 7) return `${Math.floor(diffSec / 86400)}d ago`
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" })
}

const TOP_CODES_PREVIEW = 5
const MILESTONES_PAGE_SIZE = 10

export default function OpsDashboard() {
  const [range, setRange] = useState<DashboardRange>("7d")
  const [kind, setKind] = useState<MilestoneKindFilter>("all")
  const [page, setPage] = useState(1)
  const [showAllCodes, setShowAllCodes] = useState(false)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["ops-dashboard-overview", range, kind, page],
    queryFn: () =>
      getOpsDashboardOverviewApi({ range, kind, page, page_size: MILESTONES_PAGE_SIZE }),
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
    staleTime: 20_000,
  })

  const rangeLabel = range === "all" ? "All time" : range

  return (
    <div className="flex flex-col gap-5 pb-12">
      <PageHeader
        title="Operations Dashboard"
        action={
          <div
            className="inline-flex p-0.5 rounded-[10px] border border-border bg-card w-fit"
            role="group"
            aria-label="Timeframe filter"
          >
            {RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                type="button"
                onClick={() => {
                  setRange(opt.key)
                  setPage(1)
                  setShowAllCodes(false)
                }}
                className={cn(
                  "px-3 py-1.5 text-xs font-medium rounded-[8px] transition-colors cursor-pointer whitespace-nowrap",
                  range === opt.key
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
        }
      />

      {isLoading && !data ? (
        <div className="py-16 flex justify-center">
          <Spinner />
        </div>
      ) : isError || !data ? (
        <div className="rounded-[10px] border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-600 dark:text-rose-400">
          Could not load dashboard overview. {error instanceof Error ? error.message : ""}
        </div>
      ) : (
        <>
          {/* Row 1: Top KPIs — Active Cohorts, Upcoming Sessions, Active Learners */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Link
              to="/operations/cohorts"
              className="rounded-[10px] border border-border bg-card p-4 flex items-center justify-between gap-3 hover:border-primary/40 transition-colors"
            >
              <div>
                <p className="text-xs font-medium text-muted-foreground">Active Cohorts</p>
                <p className="text-2xl font-bold text-foreground tabular-nums mt-0.5">
                  {data.active_cohorts}
                </p>
                <p className="text-xs text-muted-foreground mt-1 inline-flex items-center gap-1.5">
                  <Layers size={12} /> Currently running
                </p>
              </div>
              <span className="px-2.5 py-1 rounded-[10px] border border-emerald-500/35 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-xs font-medium shrink-0">
                Live
              </span>
            </Link>

            <Link
              to="/operations/this-week"
              className="rounded-[10px] border border-border bg-card p-4 flex items-center justify-between gap-3 hover:border-primary/40 transition-colors"
            >
              <div>
                <p className="text-xs font-medium text-muted-foreground">Upcoming Sessions</p>
                <p className="text-2xl font-bold text-foreground tabular-nums mt-0.5">
                  {data.upcoming_sessions_7d}
                </p>
                <p className="text-xs text-muted-foreground mt-1 inline-flex items-center gap-1.5">
                  <CalendarDays size={12} /> Next 7 days
                </p>
              </div>
              <span className="text-xs font-medium text-primary inline-flex items-center gap-1 shrink-0">
                This week <ArrowRight size={13} />
              </span>
            </Link>

            <div className="rounded-[10px] border border-border bg-card p-4 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-medium text-muted-foreground">
                  Active Learners ({rangeLabel})
                </p>
                <p className="text-2xl font-bold text-foreground tabular-nums mt-0.5">
                  {data.active_learners}
                </p>
                <p className="text-xs text-emerald-600 dark:text-emerald-400 font-medium mt-1 truncate">
                  {data.learner_delta_label}
                </p>
              </div>
              <div className="w-24 h-10 shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={data.learner_trend.map((v, idx) => ({ idx, v }))}
                    margin={{ top: 4, right: 4, bottom: 4, left: 4 }}
                  >
                    <Line
                      type="monotone"
                      dataKey="v"
                      stroke="#7C3AED"
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Row 2: Executive Funnel (exact Cohort Analysis widget) + 3 Stacked Side Cards */}
          <AnalysisFunnelWidget
            stages={[
              {
                label: "Enrolled",
                value: data.funnel.enrolled,
                weight: Math.max(data.funnel.enrolled, 1),
              },
              {
                label: `Active (${rangeLabel})`,
                value: data.funnel.active,
                weight: data.funnel.active,
              },
              {
                label: "Completed course or mission",
                value: data.funnel.completed,
                weight: data.funnel.completed,
              },
            ]}
            sideCards={[
              {
                title: "Active Teams",
                badge: "Teams",
                subtitle: `${data.active_teams.locked} teams locked final submission`,
                value: `${data.active_teams.active} / ${data.active_teams.total}`,
                ok: data.active_teams.total > 0 && data.active_teams.active > 0,
              },
              {
                title: "Avg Course Completion Rate",
                subtitle: "Across course enrollments",
                value: `${data.avg_course_completion_pct}%`,
                ok: data.avg_course_completion_pct >= 60,
              },
              {
                title: "Avg Mission Completion Rate",
                subtitle: "Passed vs attempted missions",
                value: `${data.avg_mission_completion_pct}%`,
                ok: data.avg_mission_completion_pct >= 60,
              },
            ]}
          />

          {/* Row 3: Top Invite Codes + Active Programs Progress */}
          {(() => {
            const maxRedeemed = Math.max(1, ...data.top_invite_codes.map((c) => c.redeemed))
            return (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
                <div className="lg:col-span-5 rounded-[10px] border border-border bg-card p-4 flex flex-col gap-3">
                  <div className="flex items-center justify-between gap-2">
                    <h2 className="text-sm font-semibold text-foreground inline-flex items-center gap-2">
                      <Ticket size={15} className="text-primary" />
                      Top Invite Codes
                    </h2>
                    <Link
                      to="/lms-authoring/invite-codes"
                      className="text-xs font-medium text-primary hover:underline inline-flex items-center gap-1"
                    >
                      Open Invite Codes <ArrowRight size={12} />
                    </Link>
                  </div>

                  {data.top_invite_codes.length === 0 ? (
                    <div className="flex-1 flex items-center justify-center py-8 text-xs text-muted-foreground">
                      No invite code redemptions in this timeframe.
                    </div>
                  ) : (
                    <>
                      <div
                        className={cn(
                          "flex-1 flex flex-col justify-center gap-3",
                          showAllCodes && "max-h-72 overflow-y-auto pr-1 justify-start",
                        )}
                      >
                        {(showAllCodes
                          ? data.top_invite_codes
                          : data.top_invite_codes.slice(0, TOP_CODES_PREVIEW)
                        ).map((c) => {
                          const totalPct = Math.round((c.redeemed / maxRedeemed) * 100)
                          const activePct = Math.round((c.active / maxRedeemed) * 100)
                          return (
                            <div key={c.code} className="space-y-1">
                              <div className="flex items-center justify-between text-xs gap-2">
                                <div className="flex items-center gap-2 min-w-0">
                                  <span className="font-mono font-semibold text-primary shrink-0">
                                    {c.code}
                                  </span>
                                  {c.label && (
                                    <span className="text-muted-foreground truncate">{c.label}</span>
                                  )}
                                </div>
                                <span className="tabular-nums shrink-0 text-muted-foreground">
                                  {c.active}/{c.redeemed} active
                                </span>
                              </div>
                              <div className="h-2.5 rounded-[10px] bg-muted overflow-hidden relative">
                                <div
                                  className="h-full rounded-[10px] bg-primary/30"
                                  style={{ width: `${totalPct}%` }}
                                />
                                <div
                                  className="h-full rounded-[10px] bg-primary absolute top-0 left-0"
                                  style={{ width: `${activePct}%` }}
                                />
                              </div>
                            </div>
                          )
                        })}
                      </div>

                      {data.top_invite_codes.length > TOP_CODES_PREVIEW && (
                        <div className="pt-2 border-t border-border flex items-center justify-between text-xs text-muted-foreground">
                          <span>
                            Showing{" "}
                            {showAllCodes ? data.top_invite_codes.length : TOP_CODES_PREVIEW} of{" "}
                            {data.top_invite_codes.length}
                          </span>
                          <button
                            type="button"
                            onClick={() => setShowAllCodes((v) => !v)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-[10px] border border-border hover:border-primary/50 cursor-pointer text-foreground font-medium"
                          >
                            {showAllCodes ? (
                              <>
                                Show less <ChevronUp size={13} />
                              </>
                            ) : (
                              <>
                                Show more ({data.top_invite_codes.length - TOP_CODES_PREVIEW}){" "}
                                <ChevronDown size={13} />
                              </>
                            )}
                          </button>
                        </div>
                      )}
                    </>
                  )}
                </div>

                <div className="lg:col-span-7 rounded-[10px] border border-border bg-card p-4 flex flex-col gap-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 className="text-sm font-semibold text-foreground inline-flex items-center gap-2">
                      <Users size={15} className="text-primary" />
                      Active Programs Progress
                    </h2>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-[3px] bg-[#16A34A]" /> Completed
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-[3px] bg-[#7C3AED]" /> Active
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-[3px] bg-[#71717A]/35" /> Not started
                      </span>
                    </div>
                  </div>

                  {data.active_programs.length === 0 ? (
                    <div className="flex-1 flex items-center justify-center py-8 text-xs text-muted-foreground">
                      No running cohorts with LMS assignments.
                    </div>
                  ) : (
                    <div className="w-full space-y-3.5 pt-1">
                      {data.active_programs.map((prog) => (
                        <div key={prog.cohort_id} className="space-y-1.5">
                          <div className="flex items-center justify-between gap-2 text-xs">
                            <span className="font-medium text-foreground truncate">
                              {prog.cohort_name}
                            </span>
                            <div className="flex items-center gap-3 shrink-0 text-muted-foreground">
                              <span className="tabular-nums">{prog.students} students</span>
                              <span className="font-semibold text-foreground tabular-nums">
                                {prog.engaged_pct}% engaged
                              </span>
                            </div>
                          </div>
                          <div className="h-3 rounded-[6px] overflow-hidden flex bg-muted">
                            <div
                              style={{ width: `${prog.completed_pct}%`, background: "#16A34A" }}
                              title={`Completed: ${prog.completed_pct}%`}
                            />
                            <div
                              style={{ width: `${prog.active_pct}%`, background: "#7C3AED" }}
                              title={`Active: ${prog.active_pct}%`}
                            />
                            <div
                              style={{
                                width: `${prog.not_started_pct}%`,
                                background: "rgba(113,113,122,0.35)",
                              }}
                              title={`Not started: ${prog.not_started_pct}%`}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )
          })()}

          {/* Row 4: Paginated Student Activity & Milestones + Warehouse Inventory Changes */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            {/* Student Activity & Milestones (Paginated) */}
            <div className="lg:col-span-7 rounded-[10px] border border-border bg-card p-4 flex flex-col justify-between gap-3">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-sm font-semibold text-foreground">
                    Student Activity &amp; Milestones
                  </h2>
                  <div className="flex flex-wrap items-center gap-1" role="tablist">
                    {KIND_FILTERS.map((f) => (
                      <button
                        key={f.key}
                        type="button"
                        role="tab"
                        aria-selected={kind === f.key}
                        onClick={() => {
                          setKind(f.key)
                          setPage(1)
                        }}
                        className={cn(
                          "px-2.5 py-1 text-xs font-medium rounded-[10px] border transition-colors cursor-pointer",
                          kind === f.key
                            ? "border-primary text-primary bg-primary/10"
                            : "border-transparent text-muted-foreground hover:text-foreground",
                        )}
                      >
                        {f.label}
                      </button>
                    ))}
                  </div>
                </div>

                {data.milestones.items.length === 0 ? (
                  <div className="py-8">
                    <EmptyState title="No milestones in this timeframe" />
                  </div>
                ) : (
                  <div className="divide-y divide-border">
                    {data.milestones.items.map((item) => {
                      const badgeCls = TONE_BADGE[item.tone] ?? TONE_BADGE.neutral
                      const content = (
                        <div className="py-2.5 flex items-center justify-between gap-3 text-xs">
                          <div className="flex items-center gap-2.5 min-w-0">
                            <span className={cn("px-2 py-0.5 rounded-[10px] border font-medium shrink-0", badgeCls)}>
                              {KIND_LABEL[item.kind] ?? item.kind}
                            </span>
                            <div className="min-w-0 truncate">
                              <span className="font-semibold text-foreground">{item.actor_name}</span>
                              <span className="text-muted-foreground ml-1.5">{item.title}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-3 shrink-0 text-muted-foreground">
                            {item.meta && (
                              <span className="hidden sm:inline truncate max-w-[140px]">
                                {item.meta}
                              </span>
                            )}
                            <span className="tabular-nums w-14 text-right">
                              {formatRelativeTime(item.timestamp)}
                            </span>
                          </div>
                        </div>
                      )
                      return item.link ? (
                        <Link
                          key={item.id}
                          to={item.link}
                          className="block hover:bg-muted/30 -mx-2 px-2 rounded-[10px] transition-colors"
                        >
                          {content}
                        </Link>
                      ) : (
                        <div key={item.id}>{content}</div>
                      )
                    })}
                  </div>
                )}
              </div>

              <div className="pt-3 border-t border-border flex items-center justify-between gap-2 text-xs text-muted-foreground">
                <span>
                  Page {data.milestones.page} of {data.milestones.total_pages} ({data.milestones.total} total)
                </span>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    disabled={data.milestones.page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-[10px] border border-border hover:border-primary/50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer text-foreground"
                  >
                    <ChevronLeft size={13} /> Previous
                  </button>
                  <button
                    type="button"
                    disabled={data.milestones.page >= data.milestones.total_pages}
                    onClick={() => setPage((p) => Math.min(data.milestones.total_pages, p + 1))}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-[10px] border border-border hover:border-primary/50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer text-foreground"
                  >
                    Next <ChevronRight size={13} />
                  </button>
                </div>
              </div>
            </div>

            {/* Warehouse Inventory Changes */}
            {(() => {
              const maxDelta = Math.max(
                1,
                ...data.warehouses.flatMap((w) => [w.added, w.removed]),
              )
              return (
                <div className="lg:col-span-5 rounded-[10px] border border-border bg-card p-4 flex flex-col gap-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 className="text-sm font-semibold text-foreground inline-flex items-center gap-2">
                      <WarehouseIcon size={15} className="text-primary" />
                      Warehouse Inventory Changes
                    </h2>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-[3px] bg-[#16A34A]" /> Added
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-[3px] bg-[#E11D48]" /> Removed
                      </span>
                    </div>
                  </div>

                  {data.warehouses.length === 0 ? (
                    <p className="text-xs text-muted-foreground py-4">No active warehouses.</p>
                  ) : (
                    <div className="space-y-3">
                      {data.warehouses.slice(0, 6).map((w) => {
                        const addPct = Math.round((w.added / maxDelta) * 100)
                        const remPct = Math.round((w.removed / maxDelta) * 100)
                        return (
                          <div key={w.warehouse_id} className="space-y-1.5">
                            <div className="flex items-center justify-between text-xs gap-2">
                              <span className="font-medium text-foreground truncate">
                                {w.warehouse_name}
                              </span>
                              <div className="flex items-center gap-3 tabular-nums shrink-0">
                                <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                                  +{w.added} added
                                </span>
                                <span className="text-rose-600 dark:text-rose-400 font-medium">
                                  -{w.removed} removed
                                </span>
                              </div>
                            </div>
                            <div className="grid grid-cols-2 gap-1.5">
                              <div className="h-2 rounded-[10px] bg-muted overflow-hidden">
                                <div
                                  className="h-full rounded-[10px] bg-[#16A34A]"
                                  style={{ width: `${addPct}%` }}
                                />
                              </div>
                              <div className="h-2 rounded-[10px] bg-muted overflow-hidden">
                                <div
                                  className="h-full rounded-[10px] bg-[#E11D48]"
                                  style={{ width: `${remPct}%` }}
                                />
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}

                  <div className="pt-3 border-t border-border">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-muted-foreground">
                        Latest stock movements
                      </span>
                      <Link
                        to="/operations/inventory/stock"
                        className="text-xs font-medium text-primary hover:underline inline-flex items-center gap-1"
                      >
                        Open Stock <ArrowRight size={12} />
                      </Link>
                    </div>
                    {data.recent_movements.length === 0 ? (
                      <p className="text-xs text-muted-foreground py-2">
                        No warehouse movements recorded in this timeframe.
                      </p>
                    ) : (
                      <div className="divide-y divide-border">
                        {data.recent_movements.map((mv) => (
                          <div key={mv.id} className="py-2 flex items-center justify-between gap-2 text-xs">
                            <div className="flex items-center gap-2 min-w-0">
                              <span
                                className={cn(
                                  "px-2 py-0.5 rounded-[10px] border font-semibold tabular-nums shrink-0",
                                  TONE_BADGE[mv.tone] ?? TONE_BADGE.neutral,
                                )}
                              >
                                {mv.qty_display}
                              </span>
                              <span className="font-medium text-foreground truncate">{mv.item_label}</span>
                              <span className="text-muted-foreground truncate hidden sm:inline">
                                {mv.warehouse_label}
                              </span>
                            </div>
                            <span className="text-muted-foreground tabular-nums shrink-0">
                              {formatRelativeTime(mv.created_at)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )
            })()}
          </div>
        </>
      )}
    </div>
  )
}
