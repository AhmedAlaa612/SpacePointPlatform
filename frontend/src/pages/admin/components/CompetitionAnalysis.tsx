import { useMemo, useState, useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import * as XLSX from "xlsx"
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts"
import {
  AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Circle, Clock, ExternalLink, Eye, FileSpreadsheet, Loader2, Lock, Search,
  Rocket, UserX, Users, UsersRound, X, Maximize2,
} from "lucide-react"
import {
  getCohortTeamAnalyticsApi, downloadCohortQuizAnswersWorkbookApi, unlockTeamApi,
  type CompetitionAnalytics, type CompetitionAnalyticsItem, type CompetitionAnalyticsTeam,
  type CompetitionAnalyticsDeliverable, type CompetitionMissionRun, type CompetitionTeamQuizSubmission,
  type CompetitionAnalyticsTeamMember,
} from "@/api/competitions"
import { getAssignmentItemsApi, type LmsAssignmentItemDetail } from "@/api/lms_admin"
import { Spinner, EmptyState, StatCard } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { useToast } from "@/components/ui/toast"
import { ensureAbsoluteUrl, getErrorMessage } from "@/lib/utils"
import { DesignRunDetail } from "@/pages/lms-authoring/components/DesignRunDetail"
import { QuizAnswersReview, AssignmentItemRow } from "@/pages/lms-authoring/components/LmsProgressAndMissions"

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
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-foreground">{title}</h3>
          {hint && <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>}
        </div>
        {action && <div className="w-full sm:w-auto shrink-0">{action}</div>}
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
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60_000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days === 1) return "yesterday"
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })
}

/** Every required deliverable, not just what's missing — a done or
 * awaiting item shows what the team actually submitted (a link, several
 * labelled links, or free text) instead of making ops open the checklist
 * to find out. */
function DeliverableList({ deliverables }: { deliverables: CompetitionAnalyticsDeliverable[] }) {
  return (
    <div className="flex flex-col gap-2">
      {deliverables.map((d) => {
        const isDone = d.status === "done"
        const isAwaiting = d.status === "awaiting_confirmation"
        const hasLinks = Boolean(d.submitted_links && d.submitted_links.length > 0)
        const hasUrl = Boolean(d.submitted_url)
        const hasText = Boolean(d.submitted_text)
        const hasSubmissions = hasLinks || hasUrl || hasText

        return (
          <div
            key={d.item_id}
            className="p-2.5 sm:p-3 rounded-xl bg-card/60 border border-border/60 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 sm:gap-3 hover:border-border transition-all"
          >
            <div className="flex items-center gap-2.5 sm:gap-3 min-w-0 flex-1">
              {isDone ? (
                <div className="w-7 h-7 rounded-lg bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 flex items-center justify-center border border-emerald-500/30 shrink-0">
                  <CheckCircle2 size={15} />
                </div>
              ) : isAwaiting ? (
                <div className="w-7 h-7 rounded-lg bg-amber-500/15 text-amber-600 dark:text-amber-400 flex items-center justify-center border border-amber-500/30 shrink-0">
                  <Clock size={15} />
                </div>
              ) : (
                <div className="w-7 h-7 rounded-lg bg-muted text-muted-foreground flex items-center justify-center border border-border/50 shrink-0">
                  <Circle size={15} />
                </div>
              )}

              <div className="flex items-center gap-1.5 min-w-0 flex-1">
                <span className="text-xs sm:text-sm font-semibold text-foreground truncate">
                  {d.title}
                </span>
                {d.optional && (
                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/50 shrink-0">
                    Optional
                  </span>
                )}
              </div>

              <span
                className={`text-[10px] sm:hidden font-bold uppercase tracking-wider px-2 py-0.5 rounded-md shrink-0 ${
                  isDone
                    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                    : isAwaiting
                      ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
                      : "bg-muted text-muted-foreground border border-border/40"
                }`}
              >
                {d.status.replace("_", " ")}
              </span>
            </div>

            <div className="flex items-center gap-2 flex-wrap shrink-0 justify-end sm:justify-start">
              {hasSubmissions ? (
                <div className="flex items-center gap-2 flex-wrap shrink-0 w-full sm:w-auto pt-1 sm:pt-0 border-t sm:border-t-0 border-border/30">
                  {hasLinks ? (
                    d.submitted_links!.map((link, i) =>
                      link.text ? (
                        <span
                          key={i}
                          title={link.text}
                          className="h-7 sm:h-8 px-2.5 sm:px-3 rounded-lg border border-border/60 bg-muted/40 text-foreground text-xs font-semibold flex items-center gap-1.5 shrink-0 max-w-[200px]"
                        >
                          <span className="truncate">{link.label || `Field ${i + 1}`}: {link.text}</span>
                        </span>
                      ) : (
                        <a
                          key={i}
                          href={ensureAbsoluteUrl(link.url ?? "")}
                          target="_blank"
                          rel="noreferrer"
                          className="h-7 sm:h-8 px-2.5 sm:px-3 rounded-lg border border-primary/30 bg-primary/10 text-primary text-xs font-semibold flex items-center gap-1.5 hover:bg-primary/20 transition-colors shrink-0 max-w-[220px]"
                          title={link.label || link.url || `Link ${i + 1}`}
                        >
                          <ExternalLink size={12} className="shrink-0" />
                          <span className="truncate">{link.label || `Link ${i + 1}`}</span>
                        </a>
                      ),
                    )
                  ) : hasUrl ? (
                    <a
                      href={ensureAbsoluteUrl(d.submitted_url!)}
                      target="_blank"
                      rel="noreferrer"
                      className="h-7 sm:h-8 px-2.5 sm:px-3 rounded-lg border border-primary/30 bg-primary/10 text-primary text-xs font-semibold flex items-center gap-1.5 hover:bg-primary/20 transition-colors shrink-0 max-w-[240px]"
                    >
                      <ExternalLink size={12} className="shrink-0" />
                      <span className="truncate">View submission</span>
                    </a>
                  ) : hasText ? (
                    <span
                      title={d.submitted_text!}
                      className="h-7 sm:h-8 px-2.5 sm:px-3 rounded-lg border border-border/60 bg-muted/40 text-foreground text-xs font-semibold flex items-center gap-1.5 shrink-0 max-w-[240px]"
                    >
                      <span className="truncate">{d.submitted_text}</span>
                    </span>
                  ) : null}
                </div>
              ) : (
                <span className="text-xs text-muted-foreground italic px-1">
                  Not submitted
                </span>
              )}

              <span
                className={`hidden sm:inline-block text-[11px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-md shrink-0 ${
                  isDone
                    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                    : isAwaiting
                      ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
                      : "bg-muted text-muted-foreground border border-border/40"
                }`}
              >
                {d.status.replace("_", " ")}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

const MISSION_RUN_STATUS_LABEL: Record<string, string> = {
  not_started: "Not started", in_progress: "In progress", submitted: "Submitted", passed: "Passed", failed: "Failed",
}

/** One team-scoped Design mission run — a thin wrapper around
 * `DesignRunDetail`, same expand-on-click pattern the judge team-detail
 * view uses (`JudgeTeamDetail.tsx`'s MissionRunRow). No custom fetchFn
 * needed here: `DesignRunDetail` already defaults to the ops/instructor
 * design-detail endpoint, which `operations`/`admin` (this tab's own
 * gate) can already call. */
function MissionRunRow({ run }: { run: CompetitionMissionRun }) {
  const [expanded, setExpanded] = useState(false)
  const isPassed = run.status === "passed" || run.status === "submitted"
  const isInProgress = run.status === "in_progress"

  return (
    <div className="rounded-xl border border-border/60 bg-card/60 overflow-hidden shadow-2xs">
      <div className="p-2.5 sm:p-3 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2.5 sm:gap-3 min-w-0 flex-1">
          {isPassed ? (
            <div className="w-7 h-7 rounded-lg bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 flex items-center justify-center border border-emerald-500/30 shrink-0">
              <CheckCircle2 size={15} />
            </div>
          ) : isInProgress ? (
            <div className="w-7 h-7 rounded-lg bg-amber-500/15 text-amber-600 dark:text-amber-400 flex items-center justify-center border border-amber-500/30 shrink-0">
              <Clock size={15} />
            </div>
          ) : (
            <div className="w-7 h-7 rounded-lg bg-muted text-muted-foreground flex items-center justify-center border border-border/50 shrink-0">
              <Circle size={15} />
            </div>
          )}

          <span className="text-xs sm:text-sm font-semibold text-foreground flex-1 min-w-0 truncate">
            {run.title}
          </span>

          <span
            className={`text-[10px] sm:hidden font-bold uppercase tracking-wider px-2 py-0.5 rounded-md shrink-0 ${
              isPassed
                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                : isInProgress
                  ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
                  : "bg-muted text-muted-foreground border border-border/40"
            }`}
          >
            {MISSION_RUN_STATUS_LABEL[run.status] ?? run.status}
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {run.attempt_id ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setExpanded((v) => !v)}
              className="h-7 text-xs font-semibold gap-1.5 shrink-0"
            >
              <Eye size={12} className="text-primary" />
              {expanded ? "Hide run" : "View run"}
            </Button>
          ) : (
            <span className="text-xs text-muted-foreground italic px-1">
              Not started
            </span>
          )}

          <span
            className={`hidden sm:inline-block text-[11px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-md shrink-0 ${
              isPassed
                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                : isInProgress
                  ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
                  : "bg-muted text-muted-foreground border border-border/40"
            }`}
          >
            {MISSION_RUN_STATUS_LABEL[run.status] ?? run.status}
          </span>
        </div>
      </div>

      {expanded && run.attempt_id && (
        <div className="p-3 border-t border-border/60 bg-muted/20">
          <DesignRunDetail attemptId={run.attempt_id} queryKeySuffix="analysis" />
        </div>
      )}
    </div>
  )
}

/** One student's quiz submission under an expanded Team row.
 * If submitted, shows score and an expand button to inspect per-question
 * answers (QuizAnswersReview), mirroring individual progress in LMS tab. */
function TeamQuizSubmissionRow({
  submission, cohortId,
}: {
  submission: CompetitionTeamQuizSubmission; cohortId: string
}) {
  const [showAnswers, setShowAnswers] = useState(false)
  const isSubmitted = submission.status === "submitted"
  const isInProgress = submission.status === "in_progress"
  const canViewAnswers = isSubmitted && !!submission.assignment_id

  return (
    <div className="border border-border/70 rounded-xl bg-card/60 overflow-hidden shadow-xs">
      <div className="p-2.5 sm:p-3 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2.5 min-w-0 flex-1">
          {isSubmitted ? (
            <div className="w-6 h-6 rounded-md bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 flex items-center justify-center border border-emerald-500/30 shrink-0">
              <CheckCircle2 size={13} />
            </div>
          ) : isInProgress ? (
            <div className="w-6 h-6 rounded-md bg-amber-500/15 text-amber-600 dark:text-amber-400 flex items-center justify-center border border-amber-500/30 shrink-0">
              <Clock size={13} />
            </div>
          ) : (
            <div className="w-6 h-6 rounded-md bg-muted text-muted-foreground flex items-center justify-center border border-border/50 shrink-0">
              <Circle size={13} />
            </div>
          )}

          <div className="min-w-0 flex-1 flex items-baseline gap-2 flex-wrap">
            <span className="font-semibold text-foreground text-xs sm:text-sm">{submission.student_name}</span>
            <span className="text-muted-foreground text-[11px] truncate">· {submission.quiz_title}</span>
          </div>

          {isSubmitted && submission.score !== null && submission.total !== null && submission.total > 0 && (
            <span className="text-xs font-mono font-bold text-emerald-600 dark:text-emerald-400 shrink-0">
              {submission.score} / {submission.total} correct
              {` (${Math.round((submission.score / submission.total) * 100)}%)`}
            </span>
          )}
          {isSubmitted && (submission.total === 0 || submission.total === null) && (
            <span className="text-xs font-medium text-blue-600 dark:text-blue-400 shrink-0">
              Completed (Opinion/Ungraded)
            </span>
          )}

          {!isSubmitted && (
            <span className="text-[11px] font-medium text-muted-foreground capitalize shrink-0">
              {submission.status.replace("_", " ")}
            </span>
          )}
        </div>

        {canViewAnswers && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setShowAnswers((v) => !v)}
            className="h-7 text-xs font-semibold gap-1.5 shrink-0"
          >
            <Eye size={12} className="text-primary" />
            {showAnswers ? "Hide answers" : "View answers"}
          </Button>
        )}
      </div>

      {showAnswers && submission.assignment_id && (
        <div className="p-3 border-t border-border/60 bg-muted/20">
          <QuizAnswersReview
            cohortId={cohortId}
            assignmentId={submission.assignment_id}
            itemId={submission.item_id}
          />
        </div>
      )}
    </div>
  )
}

type SortKey = "pct" | "name" | "members" | "activity"

function MemberProgressDetail({
  member,
  cohortId,
  teamName,
  onOpenModal,
}: {
  member: CompetitionAnalyticsTeamMember
  cohortId: string
  teamName: string
  onOpenModal?: () => void
}) {
  const navigate = useNavigate()
  const assignmentId = member.assignment_id

  const { data: items, isLoading } = useQuery<LmsAssignmentItemDetail[]>({
    queryKey: ["assignment-items", cohortId, assignmentId],
    queryFn: () => getAssignmentItemsApi(cohortId, assignmentId!),
    enabled: !!assignmentId && !!cohortId,
  })

  const doneCount = items ? items.filter((i) => i.status === "done").length : (member.items_done ?? 0)
  const totalCount = items ? items.length : (member.items_total ?? 0)
  const pct = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : (member.pct ?? 0)

  return (
    <div className="flex flex-col gap-3">
      {/* Overview header stats */}
      <div className="flex items-center justify-between gap-3 p-3 rounded-xl bg-card border border-border/70 flex-wrap">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 text-primary font-bold flex items-center justify-center text-xs shrink-0">
            {member.name.trim().slice(0, 2).toUpperCase()}
          </div>
          <div className="min-w-0">
            <p className="font-semibold text-foreground text-xs sm:text-sm truncate">{member.name}</p>
            <p className="text-[11px] text-muted-foreground truncate">
              Team: <span className="text-foreground font-medium">{teamName}</span>
              {member.last_login_at && (
                <> · Active {relativeTime(member.last_login_at)}</>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {member.user_id && (
            <button
              type="button"
              onClick={() => {
                const from = typeof window !== "undefined" ? (window.location.pathname + window.location.search) : undefined
                void navigate({
                  to: `/lms-authoring/students/${member.user_id}`,
                  search: (from ? { from } : {}) as never,
                })
              }}
              className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-lg border border-border bg-background text-[11px] font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
              title="Open student manage page"
            >
              <ExternalLink size={12} />
              <span>Full Profile</span>
            </button>
          )}

          {onOpenModal && (
            <button
              type="button"
              onClick={onOpenModal}
              className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-lg border border-border bg-background text-[11px] font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
              title="Open in modal dialog"
            >
              <Maximize2 size={12} />
              <span className="hidden sm:inline">Dialog view</span>
            </button>
          )}
        </div>
      </div>

      {/* Completion bar */}
      <div className="flex flex-col gap-1.5 px-0.5">
        <div className="flex items-center justify-between text-xs font-mono font-bold">
          <span className="text-muted-foreground">{doneCount} / {totalCount} completed</span>
          <span className={pct === 100 ? "text-emerald-500 font-extrabold" : "text-foreground"}>{pct}%</span>
        </div>
        <div className="h-2 rounded-full bg-muted overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${pct === 100 ? "bg-emerald-500" : "bg-primary"}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Items list */}
      {!assignmentId ? (
        <div className="p-4 rounded-xl border border-dashed border-border/70 text-center">
          <p className="text-xs text-muted-foreground italic">
            No LMS checklist assigned for this student in this cohort yet.
          </p>
        </div>
      ) : isLoading ? (
        <div className="py-6 flex justify-center"><Spinner /></div>
      ) : (items ?? []).length === 0 ? (
        <div className="p-4 rounded-xl border border-dashed border-border/70 text-center">
          <p className="text-xs text-muted-foreground italic">
            No checklist items found on this assignment.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-2 pt-1 max-h-[420px] overflow-y-auto pr-1">
          {(items ?? []).map((item) => (
            <AssignmentItemRow
              key={item.item_id}
              item={item}
              cohortId={cohortId}
              assignmentId={assignmentId}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function MemberProgressDrilldown({
  member,
  cohortId,
  teamName,
  onClose,
  onOpenModal,
}: {
  member: CompetitionAnalyticsTeamMember
  cohortId: string
  teamName: string
  onClose: () => void
  onOpenModal?: () => void
}) {
  return (
    <div className="mt-3 p-3.5 sm:p-4 rounded-2xl border-2 border-primary/30 bg-primary/5 flex flex-col gap-3 shadow-xs animate-in fade-in-50 duration-200">
      <div className="flex items-center justify-between gap-2 pb-2 border-b border-primary/15">
        <div className="flex items-center gap-2">
          <Eye size={14} className="text-primary" />
          <span className="font-bold text-xs uppercase tracking-wider text-foreground">
            Drill-down: {member.name}'s Individual Progress
          </span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-background/80 transition-colors cursor-pointer"
          title="Close drill-down"
        >
          <X size={15} />
        </button>
      </div>

      <MemberProgressDetail
        member={member}
        cohortId={cohortId}
        teamName={teamName}
        onOpenModal={onOpenModal}
      />
    </div>
  )
}

export function TeamAnalysisCard({
  team,
  cohortId,
  cohortName,
  joinCode,
  isExpanded,
  onToggleExpand,
}: {
  team: CompetitionAnalyticsTeam
  cohortId: string
  cohortName?: string | null
  joinCode?: string | null
  isExpanded?: boolean
  onToggleExpand?: () => void
}) {
  const isDark = useIsDark()
  const c = isDark ? CHART.dark : CHART.light
  const [localExpanded, setLocalExpanded] = useState(false)
  const [drilledMember, setDrilledMember] = useState<CompetitionAnalyticsTeamMember | null>(null)
  const [modalMember, setModalMember] = useState<CompetitionAnalyticsTeamMember | null>(null)
  const expanded = isExpanded !== undefined ? isExpanded : localExpanded
  const handleToggle = onToggleExpand ?? (() => setLocalExpanded((v) => !v))
  const toast = useToast()
  const queryClient = useQueryClient()

  const toggleDrillMember = (m: CompetitionAnalyticsTeamMember) => {
    setDrilledMember((prev) => {
      if (prev && prev.name === m.name && (prev.user_id === m.user_id || (!prev.user_id && !m.user_id))) {
        return null
      }
      return m
    })
  }
  const unlockMutation = useMutation({
    mutationFn: (teamId: string) => unlockTeamApi(teamId),
    onSuccess: () => {
      toast.success("Team's checklist reopened for editing")
      queryClient.invalidateQueries({ queryKey: ["competitions-team-analytics", cohortId] })
    },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Failed to unlock this team")),
  })

  return (
    <div className="rounded-2xl border border-border/70 bg-background/40 overflow-hidden shadow-xs hover:border-border transition-all">
      <button
        onClick={handleToggle}
        className="w-full flex items-center gap-3 p-3 sm:p-3.5 text-left hover:bg-muted/40 transition-colors cursor-pointer"
      >
        <div className="p-1 rounded-lg bg-muted/60 text-muted-foreground shrink-0">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </div>

        <div className="w-8 h-8 rounded-xl bg-primary/10 border border-primary/20 text-primary font-bold flex items-center justify-center text-xs shrink-0">
          {team.team_name.trim().slice(0, 2).toUpperCase()}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
            <p className="text-sm font-semibold text-foreground truncate max-w-full">
              {team.team_name}
            </p>
            {team.is_observer && (
              <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border border-indigo-500/30">
                Observer
              </span>
            )}
            {team.roster_team_id && team.roster_team_id !== team.team_name && (
              <span className="text-xs font-normal text-muted-foreground font-mono shrink-0">
                ({team.roster_team_id})
              </span>
            )}
            {team.locked && (
              <span
                className="inline-flex sm:hidden items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 shrink-0"
                title={team.locked_at ? `Locked on ${formatDateTime(team.locked_at)}${team.locked_by_name ? ` by ${team.locked_by_name}` : ""}` : "Final submission locked"}
              >
                <Lock size={10} /> Locked
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground truncate mt-0.5">
            {cohortName ? `${cohortName} · ` : ""}
            {team.member_count} {team.member_count === 1 ? "member" : "members"}
            {joinCode ? <> · Code: <span className="font-mono">{joinCode}</span></> : null}
          </p>
        </div>

        {team.locked && (
          <span
            className="hidden sm:flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 shrink-0"
            title={team.locked_at ? `Locked on ${formatDateTime(team.locked_at)}${team.locked_by_name ? ` by ${team.locked_by_name}` : ""}` : "Final submission locked"}
          >
            <Lock size={11} /> Locked
          </span>
        )}
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

        <div className="w-20 sm:w-36 md:w-40 shrink-0">
          <div className="flex items-center justify-between text-[11px] font-semibold tabular-nums mb-1">
            <span className="text-muted-foreground">{team.items_done}/{team.items_total}</span>
            <span className={team.pct === 100 ? "text-emerald-600 dark:text-emerald-400" : "text-foreground"}>
              {team.pct}%
            </span>
          </div>
          <div className="h-2 rounded-full overflow-hidden" style={{ backgroundColor: c.track }}>
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{ width: `${team.pct}%`, backgroundColor: team.pct === 100 ? c.done : c.accent }}
            />
          </div>
        </div>
      </button>

      {expanded && (
        <div className="p-3 sm:p-4 border-t border-border/50 bg-muted/15 flex flex-col gap-4 text-xs">
          {/* Roster */}
          <div>
            <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
              <Users size={13} />
              <span>Team Roster ({team.members.length})</span>
            </div>
            {team.members.length === 0 ? (
              <p className="text-xs text-muted-foreground italic">No members yet</p>
            ) : (
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap gap-2">
                  {team.members.map((m, i) => {
                    const isDrilled = drilledMember !== null && drilledMember.name === m.name && (drilledMember.user_id === m.user_id || (!drilledMember.user_id && !m.user_id))
                    return (
                      <div
                        key={m.name + i}
                        className={`flex items-center gap-2 px-2.5 py-1.5 rounded-xl border transition-all max-w-full min-w-0 ${
                          isDrilled
                            ? "border-primary bg-primary/10 ring-1 ring-primary/40 shadow-xs"
                            : "border-border/60 bg-card/60 shadow-2xs hover:border-border"
                        }`}
                      >
                        <div className="w-6 h-6 rounded-lg bg-primary/10 border border-primary/20 text-primary font-bold flex items-center justify-center text-[10px] shrink-0">
                          {m.name.trim().slice(0, 2).toUpperCase()}
                        </div>

                        <button
                          type="button"
                          onClick={() => toggleDrillMember(m)}
                          className="font-semibold text-foreground text-xs truncate hover:text-primary transition-colors cursor-pointer text-left"
                          title={`Click to ${isDrilled ? "hide" : "view"} ${m.name}'s individual progress`}
                        >
                          {m.name}
                        </button>

                        {m.pct !== undefined && m.pct !== null && (
                          <span
                            className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded-md shrink-0 ${
                              m.pct === 100
                                ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30"
                                : "bg-muted text-muted-foreground border border-border/50"
                            }`}
                            title={`${m.items_done ?? 0}/${m.items_total ?? 0} items completed (${m.pct}%)`}
                          >
                            {m.pct}%
                          </span>
                        )}

                        {m.last_login_at ? (
                          <span className="text-[11px] text-muted-foreground shrink-0 hidden md:inline">
                            {relativeTime(m.last_login_at)}
                          </span>
                        ) : (
                          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/25 shrink-0 hidden md:inline">
                            never logged in
                          </span>
                        )}

                        <button
                          type="button"
                          onClick={() => toggleDrillMember(m)}
                          className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-lg border transition-colors cursor-pointer shrink-0 ${
                            isDrilled
                              ? "bg-primary text-primary-foreground border-primary shadow-xs"
                              : "bg-primary/10 text-primary hover:bg-primary/20 border-primary/20"
                          }`}
                          title={isDrilled ? `Hide ${m.name}'s progress` : `View ${m.name}'s progress`}
                        >
                          <Eye size={11} />
                          <span>{isDrilled ? "Hide progress" : "View progress"}</span>
                        </button>
                      </div>
                    )
                  })}
                </div>

                {drilledMember && (
                  <MemberProgressDrilldown
                    member={drilledMember}
                    cohortId={cohortId}
                    teamName={team.team_name}
                    onClose={() => setDrilledMember(null)}
                    onOpenModal={() => setModalMember(drilledMember)}
                  />
                )}
              </div>
            )}
          </div>

          {/* Deliverables */}
          <div>
            <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
              <FileSpreadsheet size={13} />
              <span>Deliverables ({team.items_done}/{team.items_total})</span>
            </div>
            {team.deliverables.length === 0 ? (
              <p className="text-xs text-muted-foreground italic">No deliverables</p>
            ) : (
              <DeliverableList deliverables={team.deliverables} />
            )}
          </div>

          {/* Mission runs */}
          {team.mission_runs.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
                <Rocket size={13} />
                <span>Mission Runs ({team.mission_runs.length})</span>
              </div>
              <div className="flex flex-col gap-2">
                {team.mission_runs.map((run) => (
                  <MissionRunRow key={run.mission_id} run={run} />
                ))}
              </div>
            </div>
          )}

          {/* Quiz submissions */}
          {team.quiz_submissions && team.quiz_submissions.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
                <CheckCircle2 size={13} />
                <span>Quiz Submissions ({team.quiz_submissions.length})</span>
              </div>
              <div className="flex flex-col gap-2">
                {team.quiz_submissions.map((sub) => (
                  <TeamQuizSubmissionRow
                    key={`${sub.user_id}-${sub.item_id}`}
                    submission={sub}
                    cohortId={cohortId}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Locked submission banner */}
          {team.locked && (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 text-xs">
              <div className="flex items-start sm:items-center gap-2.5 min-w-0">
                <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5 sm:mt-0">
                  <Lock size={14} />
                </div>
                <div className="min-w-0">
                  <div className="font-semibold text-emerald-700 dark:text-emerald-300 flex items-center gap-1.5 flex-wrap">
                    <span>Final submission locked</span>
                    {team.locked_at && (
                      <span className="text-[11px] font-normal text-muted-foreground">
                        · {relativeTime(team.locked_at)}
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5 flex flex-wrap gap-x-1 gap-y-0.5">
                    {team.locked_at && (
                      <span>
                        Locked on <strong className="text-foreground font-medium">{formatDateTime(team.locked_at)}</strong>
                      </span>
                    )}
                    {team.locked_by_name && (
                      <span>
                        by <strong className="text-foreground font-medium">{team.locked_by_name}</strong>
                        {team.locked_by_email ? <span className="text-muted-foreground"> ({team.locked_by_email})</span> : ""}
                      </span>
                    )}
                    {!team.locked_at && !team.locked_by_name && (
                      <span>Checklist is finalized and locked.</span>
                    )}
                  </p>
                </div>
              </div>

              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  if (confirm(`Reopen "${team.team_name}"'s checklist for editing?`)) {
                    unlockMutation.mutate(team.team_id)
                  }
                }}
                disabled={unlockMutation.isPending}
                className="h-8 text-xs font-semibold gap-1.5 border-emerald-500/40 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/20 shrink-0 self-start sm:self-center cursor-pointer"
              >
                <Lock size={12} /> Unlock final submission
              </Button>
            </div>
          )}

          {/* Footer metadata */}
          <div className="flex items-center justify-between flex-wrap gap-2 pt-2 border-t border-border/40 text-xs">
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Clock size={12} className="text-muted-foreground/70" />
              <span>Last activity: <strong className="text-foreground font-medium">{relativeTime(team.last_activity_at)}</strong></span>
            </div>

            {!team.locked && (
              <span className="text-[11px] text-muted-foreground italic">
                Submission not locked
              </span>
            )}
          </div>
        </div>
      )}

      {modalMember && (
        <Dialog open={!!modalMember} onOpenChange={(open) => !open && setModalMember(null)}>
          <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <span>{modalMember.name}</span>
                <span className="text-xs font-normal text-muted-foreground">• Individual Progress</span>
              </DialogTitle>
              <DialogDescription>
                Cohort LMS checklist progress for team {team.team_name}
              </DialogDescription>
            </DialogHeader>
            <MemberProgressDetail
              member={modalMember}
              cohortId={cohortId}
              teamName={team.team_name}
            />
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}

function TeamTable({
  teams, cohortId, cohortName,
}: {
  teams: CompetitionAnalyticsTeam[]; isDark?: boolean; cohortId: string; cohortName?: string
}) {
  const [search, setSearch] = useState("")
  const [sort, setSort] = useState<SortKey>("pct")
  const [expanded, setExpanded] = useState<string | null>(null)
  const [exportingQuiz, setExportingQuiz] = useState(false)

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

  const exportQuizAnswers = async () => {
    try {
      setExportingQuiz(true)
      await downloadCohortQuizAnswersWorkbookApi(cohortId, cohortName || "cohort")
    } catch (e) {
      console.error("Failed to export quiz answers", e)
    } finally {
      setExportingQuiz(false)
    }
  }

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
      Missing: t.deliverables.filter((d) => !d.optional && d.status !== "done").map((d) => d.title).join("; "),
      "Optional submitted": t.deliverables.filter((d) => d.optional && d.status === "done").map((d) => d.title).join("; "),
      "Last activity": t.last_activity_at ? new Date(t.last_activity_at).toISOString().slice(0, 10) : "",
      Stalled: t.stalled ? "yes" : "",
      Locked: t.locked ? "yes" : "no",
      "Locked at": t.locked_at ? formatDateTime(t.locked_at) : "",
      "Locked by": t.locked_by_name ? `${t.locked_by_name}${t.locked_by_email ? ` (${t.locked_by_email})` : ""}` : "",
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
        <div className="flex items-center gap-2 flex-wrap w-full sm:w-auto">
          <button
            onClick={exportQuizAnswers}
            disabled={exportingQuiz}
            className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 h-9 px-3 border border-border rounded-xl text-xs sm:text-sm font-medium text-foreground hover:bg-muted transition-colors shrink-0 disabled:opacity-50 cursor-pointer"
            title="Export all quiz answers grouped by team and quiz"
          >
            {exportingQuiz ? <Loader2 size={14} className="animate-spin" /> : <FileSpreadsheet size={14} />}
            <span>Export Quiz Answers</span>
          </button>
          <button
            onClick={exportXlsx}
            className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 h-9 px-3 border border-border rounded-xl text-xs sm:text-sm font-medium text-foreground hover:bg-muted transition-colors shrink-0 cursor-pointer"
          >
            <FileSpreadsheet size={14} /> <span>Export Progress</span>
          </button>
        </div>
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
            <TeamAnalysisCard
              key={team.team_id}
              team={team}
              cohortId={cohortId}
              isExpanded={expanded === team.team_id}
              onToggleExpand={() => setExpanded(expanded === team.team_id ? null : team.team_id)}
            />
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
  const [mode, setMode] = useState<"participant" | "observer" | "all">("participant")
  const { data, isLoading, isError } = useQuery({
    queryKey: ["competitions-team-analytics", cohortId, mode],
    queryFn: () => getCohortTeamAnalyticsApi(cohortId, mode),
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center p-1 bg-muted/60 border border-border/80 rounded-xl text-xs">
          <button
            type="button"
            onClick={() => setMode("participant")}
            className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
              mode === "participant" ? "bg-background text-foreground shadow-xs font-semibold" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Students
          </button>
          <button
            type="button"
            onClick={() => setMode("observer")}
            className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
              mode === "observer" ? "bg-background text-indigo-600 dark:text-indigo-400 shadow-xs font-semibold" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Observers
          </button>
          <button
            type="button"
            onClick={() => setMode("all")}
            className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
              mode === "all" ? "bg-background text-foreground shadow-xs font-semibold" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            All
          </button>
        </div>
      </div>

      {isLoading ? (
        <Spinner />
      ) : isError || !data ? (
        <EmptyState title="Couldn't load the analysis" hint="Try reloading the page." />
      ) : data.totals.teams === 0 ? (
        <EmptyState
          title={mode === "observer" ? "No observer teams yet" : "No teams yet"}
          hint={mode === "observer" ? "No observer sandbox teams exist in this cohort." : "Import a roster or add a team first — everything on this tab is measured per team."}
        />
      ) : (
        <>
          {(() => {
            const { totals } = data
            const requiredItems = data.items.filter((i) => !i.optional)
            return (
              <>
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

      <TeamTable teams={data.teams} isDark={isDark} cohortId={cohortId} cohortName={data.cohort_name} />
      <AttentionList data={data} />
              </>
            )
          })()}
        </>
      )}
    </div>
  )
}
