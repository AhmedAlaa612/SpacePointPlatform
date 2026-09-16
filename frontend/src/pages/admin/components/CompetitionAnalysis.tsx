import { useMemo, useState, useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import * as XLSX from "xlsx"
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts"
import {
  AlertTriangle, ChevronDown, ChevronRight, Clock, FileSpreadsheet, Search,
  Rocket, UserX, Users, UsersRound,
} from "lucide-react"
import {
  getCohortTeamAnalyticsApi,
  type CompetitionAnalytics, type CompetitionAnalyticsItem, type CompetitionAnalyticsTeam,
  type CompetitionAnalyticsDeliverable,
} from "@/api/competitions"
import { Spinner, EmptyState, StatCard } from "@/components/ui/primitives"

/* ================================================================== */
/* Analysis tab (2026-09-16)                                           */
/*                                                                     */
/* The team-first half of "how is this competition going". Per-student  */
/* checklist progress already has a home (the cohort's LMS > Progress   */
/* tab, one expandable row per student); nothing before this showed the */
/* other axis — how many teams there are, how far each has got, and     */
/* which single deliverable the cohort as a whole is stuck on.          */
/*                                                                     */
/* One fetch, one payload — see `services/competitions/analytics.py`    */
/* for where each number comes from, and in particular why mission_run  */
/* items are reported as their own block rather than as completion-rate */
/* bars (their real completion is per-design-step, and a stale bar      */
/* labelled "Build the CubeSat" is worse than no bar).                  */
/* ================================================================== */

/* ── Chart palette ──────────────────────────────────────────────────
 * Status encoding, not a categorical one: done / awaiting confirmation /
 * not submitted. Both modes are *selected* rather than auto-flipped, and
 * each pair was validated against the surface it actually renders on —
 * white for light, the dark theme's own card (#1A0F26) for dark:
 *
 *   light  done #047857 + awaiting #d97706 — CVD ΔE 11.0, both >= 3:1 on white
 *   dark   done #199e70 + awaiting #c98500 — CVD ΔE  8.4, both >= 3:1 on #1A0F26
 *
 * "Not submitted" is deliberately a neutral track, not a third hue: it's
 * the unfilled remainder of the bar, not a series competing for identity.
 * Colour never carries the meaning alone — every segment is in the legend
 * and every bar is directly labelled.
 *
 * Recharts needs concrete colours (a CSS var in an SVG `fill` doesn't
 * resolve reliably), which is why these are hex here rather than theme
 * tokens — same reason `instructors/admin/Overview.tsx` hardcodes its own. */
const CHART = {
  light: { done: "#047857", awaiting: "#d97706", track: "#e2e8f0", accent: "#6d3fd4", grid: "#e1e0d9", ink: "#898781" },
  dark: { done: "#199e70", awaiting: "#c98500", track: "#2e2440", accent: "#9a72f5", grid: "#2c2c2a", ink: "#898781" },
} as const

/** The app toggles dark mode by putting `.dark` on <html> imperatively
 * (see components/layout/ThemeToggle.tsx) — there's no context to read,
 * so the charts watch the class attribute instead. */
function useIsDark(): boolean {
  const [isDark, setIsDark] = useState(() => document.documentElement.classList.contains("dark"))
  useEffect(() => {
    const observer = new MutationObserver(() => setIsDark(document.documentElement.classList.contains("dark")))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] })
    return () => observer.disconnect()
  }, [])
  return isDark
}

/** Recharts' `YAxis width` is a fixed pixel prop, not CSS — a label
 * column wide enough for a full checklist-item title on desktop (180px)
 * leaves almost nothing for the bar itself on a ~360px phone. Watched
 * live (2026-09-17) rather than read once, so rotating a phone doesn't
 * strand the chart in its old layout. */
function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 640)
  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 640)
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [])
  return isMobile
}

function SectionCard({ title, hint, action, children }: {
  title: string; hint?: string; action?: React.ReactNode; children: React.ReactNode
}) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4 sm:p-5 flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-foreground">{title}</h3>
          {hint && <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>}
        </div>
        {action}
      </div>
      {children}
    </div>
  )
}

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}

function ChartTooltip({ active, payload, label, unit }: {
  active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string; unit?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-border bg-popover px-3 py-2 shadow-lg">
      <p className="text-xs font-semibold text-foreground mb-1">{label}</p>
      {payload.map((entry) => (
        <p key={entry.name} className="text-xs text-muted-foreground flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-sm shrink-0" style={{ backgroundColor: entry.color }} />
          {entry.name}: <span className="font-semibold text-foreground tabular-nums">{entry.value}</span>
          {unit && ` ${unit}`}
        </p>
      ))}
    </div>
  )
}

/* ── Completion-rate bars ─────────────────────────────────────────── */

/** One horizontal stacked bar per checklist item, in checklist order —
 * "which deliverable is the cohort stuck on" in one glance. A team-scoped
 * item's bar counts teams; an individual one counts students (the item's
 * own `denominator` says which, so this never infers it). */
function CompletionRateChart({ items, isDark }: { items: CompetitionAnalyticsItem[]; isDark: boolean }) {
  const c = isDark ? CHART.dark : CHART.light
  const isMobile = useIsMobile()
  const maxChars = isMobile ? 16 : 28
  const rows = items.map((item) => ({
    ...item,
    // Truncated for the axis; the tooltip and the row label carry the full title.
    shortTitle: item.title.length > maxChars ? `${item.title.slice(0, maxChars - 1)}…` : item.title,
  }))

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-4 flex-wrap">
        <LegendSwatch color={c.done} label="Done" />
        <LegendSwatch color={c.awaiting} label="Awaiting confirmation" />
        <LegendSwatch color={c.track} label="Not submitted" />
      </div>
      <ResponsiveContainer width="100%" height={Math.max(160, rows.length * 38)}>
        <BarChart
          data={rows} layout="vertical"
          margin={{ top: 4, right: isMobile ? 32 : 56, bottom: 4, left: 8 }} barCategoryGap="28%"
        >
          <CartesianGrid horizontal={false} stroke={c.grid} />
          <XAxis type="number" tick={{ fontSize: 11, fill: c.ink }} stroke={c.grid} allowDecimals={false} />
          <YAxis
            type="category" dataKey="shortTitle" width={isMobile ? 108 : 180}
            tick={{ fontSize: 11, fill: c.ink }} stroke={c.grid} interval={0}
          />
          <Tooltip
            cursor={{ fill: c.track, opacity: 0.35 }}
            content={({ active, payload }) => {
              const row = payload?.[0]?.payload as (typeof rows)[number] | undefined
              if (!active || !row) return null
              return (
                <div className="rounded-xl border border-border bg-popover px-3 py-2 shadow-lg max-w-xs">
                  <p className="text-xs font-semibold text-foreground">{row.title}</p>
                  <p className="text-[11px] text-muted-foreground mb-1">
                    {row.scope === "team" ? "Team deliverable" : "Individual item"} · {row.item_type}
                    {row.optional && " · optional"}
                  </p>
                  <p className="text-xs text-foreground tabular-nums">
                    {row.done} of {row.total} {row.denominator} done ({row.pct}%)
                  </p>
                  {row.awaiting > 0 && (
                    <p className="text-xs text-muted-foreground tabular-nums">{row.awaiting} awaiting confirmation</p>
                  )}
                </div>
              )
            }}
          />
          {/* 2px stroke in the surface colour is the mandated gap between
              stacked segments — without it adjacent fills read as one. */}
          <Bar dataKey="done" stackId="a" name="Done" fill={c.done} stroke="transparent" strokeWidth={2} />
          <Bar dataKey="awaiting" stackId="a" name="Awaiting" fill={c.awaiting} stroke="transparent" strokeWidth={2} />
          <Bar
            dataKey="pending" stackId="a" name="Not submitted" fill={c.track}
            stroke="transparent" strokeWidth={2} radius={[0, 4, 4, 0]}
          >
            {/* Direct label on the end of the whole stack — the mandated
                secondary encoding, so done-vs-awaiting never rests on
                hue alone. */}
            <LabelList
              dataKey="pct" position="right" fontSize={11} fill={c.ink}
              formatter={(value) => `${value ?? 0}%`}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ── Distribution + activity ──────────────────────────────────────── */

const BUCKETS = [
  { label: "0%", test: (p: number) => p === 0 },
  { label: "1–25%", test: (p: number) => p > 0 && p <= 25 },
  { label: "26–50%", test: (p: number) => p > 25 && p <= 50 },
  { label: "51–75%", test: (p: number) => p > 50 && p <= 75 },
  { label: "76–99%", test: (p: number) => p > 75 && p < 100 },
  { label: "100%", test: (p: number) => p === 100 },
]

/** Teams bucketed by completion — the shape of the cohort, which the
 * average hides: "62% average" reads very differently when it's eight
 * teams at 0% and eight at 100%. */
function DistributionChart({ teams, isDark }: { teams: CompetitionAnalyticsTeam[]; isDark: boolean }) {
  const c = isDark ? CHART.dark : CHART.light
  const data = BUCKETS.map((bucket) => ({
    label: bucket.label,
    teams: teams.filter((t) => bucket.test(t.pct)).length,
  }))
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ top: 12, right: 8, bottom: 4, left: -20 }} barCategoryGap="22%">
        <CartesianGrid vertical={false} stroke={c.grid} />
        <XAxis dataKey="label" tick={{ fontSize: 11, fill: c.ink }} stroke={c.grid} />
        <YAxis tick={{ fontSize: 11, fill: c.ink }} stroke={c.grid} allowDecimals={false} />
        <Tooltip cursor={{ fill: c.track, opacity: 0.35 }} content={<ChartTooltip unit="" />} />
        <Bar dataKey="teams" name="Teams" fill={c.accent} radius={[4, 4, 0, 0]}>
          {/* The 100% bucket wears the "done" green — it's the same state
              the completion bars call done, so it should read the same. */}
          {data.map((row) => (
            <Cell key={row.label} fill={row.label === "100%" ? c.done : c.accent} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Deliverables touched per day. `updated_at` is a last-write timestamp,
 * not an event log (a team that replaced a link three times counts once,
 * on the last day it touched that item) — enough to see the crunch and
 * the teams that went quiet, which is what this is for. */
function ActivityChart({ activity, isDark }: { activity: CompetitionAnalytics["activity"]; isDark: boolean }) {
  const c = isDark ? CHART.dark : CHART.light
  const data = activity.map((point) => ({
    ...point,
    label: new Date(point.date).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
  }))
  return (
    <ResponsiveContainer width="100%" height={180}>
      <AreaChart data={data} margin={{ top: 12, right: 8, bottom: 4, left: -20 }}>
        <defs>
          <linearGradient id="analysis-activity-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={c.accent} stopOpacity={0.35} />
            <stop offset="100%" stopColor={c.accent} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke={c.grid} />
        <XAxis dataKey="label" tick={{ fontSize: 10, fill: c.ink }} stroke={c.grid} interval="preserveStartEnd" minTickGap={24} />
        <YAxis tick={{ fontSize: 11, fill: c.ink }} stroke={c.grid} allowDecimals={false} />
        <Tooltip cursor={{ stroke: c.accent, strokeWidth: 1 }} content={<ChartTooltip />} />
        <Area
          type="monotone" dataKey="updates" name="Deliverables updated"
          stroke={c.accent} strokeWidth={2} fill="url(#analysis-activity-fill)"
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

/* ── Team table ───────────────────────────────────────────────────── */

function relativeTime(iso: string | null): string {
  if (!iso) return "—"
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  if (days <= 0) return "today"
  if (days === 1) return "yesterday"
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

/** Every required deliverable, not just what's missing — a done or
 * awaiting item shows what the team actually submitted (a link, several
 * labelled links, or free text) instead of making ops open the checklist
 * to find out. */
function DeliverableList({ deliverables }: { deliverables: CompetitionAnalyticsDeliverable[] }) {
  return (
    <ul className="mt-1 flex flex-col gap-1">
      {deliverables.map((d) => (
        <li key={d.item_id} className="flex flex-wrap items-baseline gap-1.5">
          <span
            className={
              d.status === "done"
                ? "text-emerald-600 dark:text-emerald-400"
                : d.status === "awaiting_confirmation"
                  ? "text-amber-600 dark:text-amber-400"
                  : "text-muted-foreground"
            }
          >
            {d.status === "done" ? "✓" : d.status === "awaiting_confirmation" ? "⏳" : "—"}
          </span>
          <span className="text-foreground font-medium">{d.title}:</span>
          {d.submitted_links && d.submitted_links.length > 0 ? (
            <span className="flex flex-wrap gap-x-1.5">
              {d.submitted_links.map((link, i) => (
                <a
                  key={i} href={link.url ?? undefined} target="_blank" rel="noreferrer"
                  className="text-primary underline truncate max-w-[220px]"
                >
                  {link.label || link.url || link.text || "link"}
                </a>
              ))}
            </span>
          ) : d.submitted_url ? (
            <a
              href={d.submitted_url} target="_blank" rel="noreferrer"
              className="text-primary underline truncate max-w-[240px]"
            >
              {d.submitted_url}
            </a>
          ) : d.submitted_text ? (
            <span className="text-foreground truncate max-w-[280px]">{d.submitted_text}</span>
          ) : (
            <span className="text-muted-foreground italic">not submitted</span>
          )}
        </li>
      ))}
    </ul>
  )
}

type SortKey = "pct" | "name" | "members" | "activity"

function TeamTable({ teams, isDark }: { teams: CompetitionAnalyticsTeam[]; isDark: boolean }) {
  const c = isDark ? CHART.dark : CHART.light
  const [search, setSearch] = useState("")
  const [sort, setSort] = useState<SortKey>("pct")
  const [expanded, setExpanded] = useState<string | null>(null)

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase()
    const filtered = q
      ? teams.filter((t) =>
          t.team_name.toLowerCase().includes(q) ||
          (t.roster_team_id ?? "").toLowerCase().includes(q) ||
          t.members.some((m) => m.name.toLowerCase().includes(q)))
      : teams
    const sorted = [...filtered]
    if (sort === "pct") sorted.sort((a, b) => b.pct - a.pct || a.team_name.localeCompare(b.team_name))
    if (sort === "name") sorted.sort((a, b) => a.team_name.localeCompare(b.team_name))
    if (sort === "members") sorted.sort((a, b) => b.member_count - a.member_count)
    if (sort === "activity") {
      sorted.sort((a, b) =>
        new Date(b.last_activity_at ?? 0).getTime() - new Date(a.last_activity_at ?? 0).getTime())
    }
    return sorted
  }, [teams, search, sort])

  const exportXlsx = () => {
    const sheet = XLSX.utils.json_to_sheet(rows.map((t) => ({
      Team: t.team_name,
      "Team ID": t.roster_team_id ?? "",
      Members: t.member_count,
      "Never logged in": t.never_logged_in,
      Done: t.items_done,
      Total: t.items_total,
      "Completion %": t.pct,
      "Awaiting confirmation": t.awaiting,
      Missing: t.deliverables.filter((d) => d.status !== "done").map((d) => d.title).join("; "),
      "Last activity": t.last_activity_at ? new Date(t.last_activity_at).toISOString().slice(0, 10) : "",
      Stalled: t.stalled ? "yes" : "",
      Roster: t.members.map((m) => `${m.name} (${m.last_login_at ? relativeTime(m.last_login_at) : "never logged in"})`).join("; "),
    })))
    const book = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(book, sheet, "Team progress")
    XLSX.writeFile(book, "team_progress.xlsx")
  }

  return (
    <SectionCard
      title="Team progress"
      hint="Against this cohort's required team deliverables. Awaiting confirmation counts as not done — confirming it is the outstanding work."
      action={
        <button
          onClick={exportXlsx}
          className="flex items-center gap-1.5 h-9 px-3 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors shrink-0"
        >
          <FileSpreadsheet size={14} /> Export
        </button>
      }
    >
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by team, team ID or student…"
            className="w-full h-9 pl-8 pr-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </div>
        <select
          value={sort} onChange={(e) => setSort(e.target.value as SortKey)}
          className="h-9 px-2.5 border border-border bg-background rounded-xl text-xs font-medium text-foreground w-auto max-w-fit cursor-pointer focus:outline-none"
        >
          <option value="pct">Sort: completion</option>
          <option value="name">Sort: name</option>
          <option value="members">Sort: members</option>
          <option value="activity">Sort: last activity</option>
        </select>
      </div>

      {rows.length === 0 ? (
        <p className="text-xs text-muted-foreground text-center py-6">No teams match "{search}".</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {rows.map((team) => (
            <div key={team.team_id} className="rounded-xl border border-border/70 bg-background/40 overflow-hidden">
              <button
                onClick={() => setExpanded(expanded === team.team_id ? null : team.team_id)}
                className="w-full flex items-center gap-3 p-3 text-left hover:bg-muted/40 transition-colors cursor-pointer"
              >
                {expanded === team.team_id
                  ? <ChevronDown size={14} className="text-muted-foreground shrink-0" />
                  : <ChevronRight size={14} className="text-muted-foreground shrink-0" />}

                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-foreground truncate">
                    {team.team_name}
                    {team.roster_team_id && team.roster_team_id !== team.team_name && (
                      <span className="ml-2 text-xs font-normal text-muted-foreground">{team.roster_team_id}</span>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground truncate">
                    {team.member_count} {team.member_count === 1 ? "member" : "members"}
                    {team.never_logged_in > 0 && ` · ${team.never_logged_in} never logged in`}
                  </p>
                </div>

                {team.stalled && (
                  <span className="hidden sm:flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/30 shrink-0">
                    <Clock size={11} /> Stalled
                  </span>
                )}
                {team.awaiting > 0 && (
                  <span className="hidden sm:inline text-[11px] font-semibold px-2 py-0.5 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/30 shrink-0">
                    {team.awaiting} to confirm
                  </span>
                )}

                <div className="w-28 sm:w-40 shrink-0">
                  <div className="flex items-center justify-between text-[11px] font-semibold tabular-nums mb-1">
                    <span className="text-muted-foreground">{team.items_done}/{team.items_total}</span>
                    <span className={team.pct === 100 ? "text-emerald-600 dark:text-emerald-400" : "text-foreground"}>
                      {team.pct}%
                    </span>
                  </div>
                  <div className="h-2 rounded-full overflow-hidden" style={{ backgroundColor: c.track }}>
                    <div
                      className="h-full rounded-full transition-all"
                      style={{ width: `${team.pct}%`, backgroundColor: team.pct === 100 ? c.done : c.accent }}
                    />
                  </div>
                </div>
              </button>

              {expanded === team.team_id && (
                <div className="px-3 pb-3 pt-1 border-t border-border/50 flex flex-col gap-2.5 text-xs">
                  <div>
                    <span className="text-muted-foreground">Roster: </span>
                    {team.members.length === 0 ? (
                      <span className="text-foreground">No members yet</span>
                    ) : (
                      <span className="text-foreground">
                        {team.members.map((m, i) => (
                          <span key={m.name + i}>
                            {i > 0 && ", "}
                            {m.name} <span className="text-muted-foreground">
                              ({m.last_login_at ? `last login ${relativeTime(m.last_login_at)}` : "never logged in"})
                            </span>
                          </span>
                        ))}
                      </span>
                    )}
                  </div>
                  <div>
                    <span className="text-muted-foreground">Deliverables: </span>
                    {team.deliverables.length === 0 ? (
                      <span className="text-foreground">Nothing required</span>
                    ) : (
                      <DeliverableList deliverables={team.deliverables} />
                    )}
                  </div>
                  <div>
                    <span className="text-muted-foreground">Last activity: </span>
                    <span className="text-foreground">{relativeTime(team.last_activity_at)}</span>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  )
}

/* ── Attention list ───────────────────────────────────────────────── */

function AttentionList({ data }: { data: CompetitionAnalytics }) {
  const notStarted = data.teams.filter((t) => t.items_done === 0 && t.items_total > 0)
  const empty = data.teams.filter((t) => t.member_count === 0)
  const solo = data.teams.filter((t) => t.member_count === 1)
  const awaiting = data.teams.filter((t) => t.awaiting > 0)

  const groups = [
    {
      key: "awaiting", tone: "amber" as const,
      label: `${awaiting.length} ${awaiting.length === 1 ? "team is" : "teams are"} waiting on your confirmation`,
      names: awaiting.map((t) => `${t.team_name} (${t.awaiting})`),
    },
    {
      key: "notStarted", tone: "amber" as const,
      label: `${notStarted.length} ${notStarted.length === 1 ? "team has" : "teams have"} submitted nothing at all`,
      names: notStarted.map((t) => t.team_name),
    },
    {
      key: "roster", tone: "muted" as const,
      label: `${empty.length} empty ${empty.length === 1 ? "team" : "teams"}, ${solo.length} with a single member`,
      names: [...empty, ...solo].map((t) => `${t.team_name} (${t.member_count})`),
    },
    {
      key: "unassigned", tone: "muted" as const,
      label: `${data.totals.students_without_team} registered ${
        data.totals.students_without_team === 1 ? "student is" : "students are"} not on any team`,
      names: [],
    },
  ].filter((g) => g.key === "unassigned" ? data.totals.students_without_team > 0 : g.names.length > 0)

  if (groups.length === 0) {
    return (
      <SectionCard title="Needs attention">
        <p className="text-sm text-muted-foreground">
          Nothing outstanding — every team has members, recent activity, and nothing waiting on a confirmation.
        </p>
      </SectionCard>
    )
  }

  return (
    <SectionCard title="Needs attention" hint="Everything here is something only ops can unblock.">
      <div className="flex flex-col gap-3">
        {groups.map((group) => (
          <div key={group.key} className="flex items-start gap-2.5">
            {group.tone === "amber"
              ? <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
              : <UserX size={14} className="mt-0.5 shrink-0 text-muted-foreground" />}
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground">{group.label}</p>
              {group.names.length > 0 && (
                <p className="text-xs text-muted-foreground mt-0.5">{group.names.join(", ")}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </SectionCard>
  )
}

/* ── Missions ─────────────────────────────────────────────────────── */

function MissionsBlock({ missions, isDark }: { missions: CompetitionAnalytics["missions"]; isDark: boolean }) {
  const c = isDark ? CHART.dark : CHART.light
  const isMobile = useIsMobile()
  const maxChars = isMobile ? 16 : 28
  const rows = missions.map((m) => ({
    ...m,
    shortTitle: m.title.length > maxChars ? `${m.title.slice(0, maxChars - 1)}…` : m.title,
  }))
  return (
    <SectionCard
      title="Mission runs"
      hint="Read off each run's shared MissionAttempt, not the checklist's stored status — a run is multi-step, so it gets its own block rather than a completion bar."
    >
      <div className="flex items-center gap-4 flex-wrap">
        <LegendSwatch color={c.done} label="Passed" />
        <LegendSwatch color={c.awaiting} label="Started" />
        <LegendSwatch color={c.track} label="Not started" />
      </div>
      <ResponsiveContainer width="100%" height={Math.max(120, rows.length * 46)}>
        <BarChart
          data={rows} layout="vertical"
          margin={{ top: 4, right: isMobile ? 24 : 40, bottom: 4, left: 8 }} barCategoryGap="28%"
        >
          <CartesianGrid horizontal={false} stroke={c.grid} />
          <XAxis type="number" tick={{ fontSize: 11, fill: c.ink }} stroke={c.grid} allowDecimals={false} />
          <YAxis
            type="category" dataKey="shortTitle" width={isMobile ? 100 : 160}
            tick={{ fontSize: 11, fill: c.ink }} stroke={c.grid} interval={0}
          />
          <Tooltip cursor={{ fill: c.track, opacity: 0.35 }} content={<ChartTooltip />} />
          <Bar dataKey="passed" stackId="m" name="Passed" fill={c.done} stroke="transparent" strokeWidth={2} />
          <Bar dataKey="in_progress" stackId="m" name="Started" fill={c.awaiting} stroke="transparent" strokeWidth={2} />
          <Bar dataKey="not_started" stackId="m" name="Not started" fill={c.track} stroke="transparent" strokeWidth={2} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </SectionCard>
  )
}

/* ── Page ─────────────────────────────────────────────────────────── */

export function CompetitionAnalysisTab({ cohortId }: { cohortId: string }) {
  const isDark = useIsDark()
  const { data, isLoading, isError } = useQuery({
    queryKey: ["competitions-team-analytics", cohortId],
    queryFn: () => getCohortTeamAnalyticsApi(cohortId),
  })

  if (isLoading) return <Spinner />
  if (isError || !data) {
    return <EmptyState title="Couldn't load the analysis" hint="Try reloading the page." />
  }
  if (data.totals.teams === 0) {
    return (
      <EmptyState
        title="No teams yet"
        hint="Import a roster or add a team first — everything on this tab is measured per team."
      />
    )
  }

  const { totals } = data
  // Optional items are excluded from the completion bars for the same
  // reason `_assignment_summary` excludes them from a student's own
  // percentage: an optional step nobody did isn't a cohort behind.
  const requiredItems = data.items.filter((i) => !i.optional)

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={<UsersRound size={20} />} label="Teams" value={totals.teams}
          sub={`${totals.empty_teams} with no members`}
        />
        <StatCard
          icon={<Users size={20} />} label="Students on teams" value={totals.students_on_teams}
          sub={`${totals.avg_team_size} avg per team · ${totals.students_without_team} not on a team`}
        />
        <StatCard
          icon={<Rocket size={20} />} label="Avg completion" value={`${totals.avg_team_pct}%`}
          sub={`${totals.teams_complete} done · ${totals.teams_not_started} not started`}
        />
        <StatCard
          icon={<Clock size={20} />} label="Awaiting confirmation" value={totals.deliverables_awaiting}
          sub={`${totals.teams_stalled} stalled ${totals.teams_stalled === 1 ? "team" : "teams"}`}
        />
      </div>

      {requiredItems.length > 0 ? (
        <SectionCard
          title="Checklist completion rate"
          hint="Every required checklist item, in order. A team deliverable counts teams; an individual item counts the students holding this cohort's checklist."
        >
          <CompletionRateChart items={requiredItems} isDark={isDark} />
        </SectionCard>
      ) : (
        <SectionCard title="Checklist completion rate">
          <p className="text-sm text-muted-foreground">
            This cohort's checklist has no required items yet — add some from the cohort's LMS tab.
          </p>
        </SectionCard>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard
          title="Team completion distribution"
          hint="How the cohort is spread — an average hides a split between teams that are done and teams that never started."
        >
          <DistributionChart teams={data.teams} isDark={isDark} />
        </SectionCard>
        <SectionCard
          title="Submission activity"
          hint={`Team deliverables touched per day over the last ${data.activity.length} days. Counts each deliverable once, on the day it was last updated.`}
        >
          <ActivityChart activity={data.activity} isDark={isDark} />
        </SectionCard>
      </div>

      {data.missions.length > 0 && <MissionsBlock missions={data.missions} isDark={isDark} />}

      <TeamTable teams={data.teams} isDark={isDark} />
      <AttentionList data={data} />
    </div>
  )
}
