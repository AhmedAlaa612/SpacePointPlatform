import { useState, useRef } from "react"
import { useQuery } from "@tanstack/react-query"
import { Download, Users, Sheet, ChevronDown } from "lucide-react"
import * as XLSX from "xlsx"
import { cn } from "@/lib/utils"
import { useAuth } from "@/context/AuthContext"
import type { Task, Team, User } from "@/types/interns"
import { getUsersApi } from "@/api/interns/users"
import { getAdminTrackerApi, getLeaderTrackerApi, getInternTrackerApi } from "@/api/interns/tracker"
import { getTeamsApi, getLeaderTeamApi, getInternTeamApi, getLeaderTeamMembersApi } from "@/api/interns/teams"
import logoImg from "@/assets/logos/intern.svg"

// ── helpers ───────────────────────────────────────────────────────────────────

function fmtDate(d: string | null) {
  if (!d) return "—"
  return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
}

function fmtHours(h: number | null) {
  if (h == null) return "—"
  return `${Number(h)}h`
}

function statusBadge(status: string) {
  const map: Record<string, string> = {
    todo:        "bg-muted text-muted-foreground",
    in_progress: "bg-[#d6c7e1] text-[#643f83]",
    done:        "bg-foreground text-background",
  }
  return map[status] ?? "bg-muted text-muted-foreground"
}

function computeStats(tasks: Task[]) {
  const total     = tasks.length
  const done      = tasks.filter((t) => t.status === "done").length
  const pctDone   = total ? Math.round((done / total) * 100) : 0

  const withDue   = tasks.filter((t) => t.due_date && t.status === "done")
  const onTime    = withDue.filter((t) => {
    const sub = t.submissions?.[t.submissions.length - 1]
    if (!sub) return false
    return new Date(sub.submitted_at) <= new Date(t.due_date!)
  }).length
  const pctOnTime = withDue.length ? Math.round((onTime / withDue.length) * 100) : null

  const withTime  = tasks.filter((t) => t.expected_time != null && t.actual_time != null)
  const avgDelta  = withTime.length
    ? withTime.reduce((acc, t) => acc + (Number(t.actual_time) - Number(t.expected_time)), 0) / withTime.length
    : null

  const totalActual   = tasks.reduce((acc, t) => acc + (t.actual_time   ? Number(t.actual_time)   : 0), 0)
  const totalExpected = tasks.reduce((acc, t) => acc + (t.expected_time ? Number(t.expected_time) : 0), 0)

  // average score across all reviewed submissions that have a score
  const scoredTasks = tasks.filter((t) => {
    const sub = t.submissions?.[t.submissions.length - 1]
    return sub?.status === "reviewed" && sub.score != null
  })
  const avgScore = scoredTasks.length
    ? Math.round(scoredTasks.reduce((acc, t) => {
        const sub = t.submissions![t.submissions!.length - 1]
        return acc + sub.score!
      }, 0) / scoredTasks.length)
    : null

  return { total, done, pctDone, pctOnTime, avgDelta, totalActual, totalExpected, avgScore, scoredCount: scoredTasks.length }
}

// ── main component ────────────────────────────────────────────────────────────

export default function Tracker() {
  const { currentUser } = useAuth()
  const printRef        = useRef<HTMLDivElement>(null)
  const isAdmin   = currentUser?.role === "admin"
  const isLeader  = currentUser?.role === "leader"
  const isIntern  = currentUser?.role === "intern"

  const [selectedUserId, setSelectedUserId] = useState<string>("")

  // ── data ──────────────────────────────────────────────────────────────────
  const { data: allUsers = [] } = useQuery<User[]>({
    queryKey: ["users"],
    queryFn: getUsersApi,
    enabled: isAdmin,
  })

  const { data: teamInterns = [] } = useQuery<User[]>({
    queryKey: ["leader", "team", "members"],
    queryFn: getLeaderTeamMembersApi,
    enabled: isLeader,
  })

  // admin sees all interns
  const adminInterns  = allUsers.filter((u) => u.roles.includes("intern"))

  const interns: User[] = isAdmin ? adminInterns : isLeader ? teamInterns : []

  // which user's tasks to fetch
  const targetId = isIntern ? currentUser?.id : selectedUserId

  const { data: tasks = [], isLoading } = useQuery<Task[]>({
    queryKey: ["tracker", targetId],
    queryFn: () => {
      if (isIntern)       return getInternTrackerApi()
      if (isAdmin)        return getAdminTrackerApi(targetId!)
      return getLeaderTrackerApi(targetId!)
    },
    enabled: !!targetId,
  })

  const selectedUser = isIntern
    ? currentUser
    : interns.find((u) => u.id === selectedUserId) ?? null

  // ── team name ────────────────────────────────────────────────────────────────
  const { data: internTeam }  = useQuery<Team>({ queryKey: ["intern", "team"], queryFn: getInternTeamApi,  enabled: isIntern })
  const { data: leaderTeam }  = useQuery<Team>({ queryKey: ["leader", "team"], queryFn: getLeaderTeamApi,  enabled: isLeader })
  const { data: allTeams = [] } = useQuery<Team[]>({ queryKey: ["teams"],      queryFn: getTeamsApi,       enabled: isAdmin  })

  const teamName: string | null = isIntern
    ? (internTeam?.name ?? null)
    : isLeader
    ? (leaderTeam?.name ?? null)
    : allTeams.find((t) => t.members.some((m) => m.id === selectedUserId))?.name ?? null

  const stats = computeStats(tasks)

  // ── export sheet ───────────────────────────────────────────────────────────
  const handleExportSheet = () => {
    const name = selectedUser?.full_name ?? "Intern"
    const rows = tasks.map((task) => {
      const latestSub = task.submissions?.[task.submissions.length - 1]
      return {
        "Task":             task.title,
        "Module":           task.module_title ?? "",
        "Epic":             task.epic_title ?? "",
        "Start date":       task.created_at ? new Date(task.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "",
        "Deadline":         task.due_date   ? new Date(task.due_date).toLocaleDateString("en-US",   { month: "short", day: "numeric", year: "numeric" }) : "",
        "Status":           task.status.replace("_", " "),
        "Expected (h)":     task.expected_time ?? "",
        "Actual (h)":       task.actual_time   ?? "",
        "Submitted":        latestSub?.submitted_at ? new Date(latestSub.submitted_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "",
        "Score (/100)":     latestSub?.status === "reviewed" && latestSub.score != null ? latestSub.score : "",
        "Submission link":  latestSub?.link ?? "",
      }
    })

    const ws = XLSX.utils.json_to_sheet(rows)

    // column widths
    ws["!cols"] = [
      { wch: 35 }, // Task
      { wch: 22 }, // Module
      { wch: 22 }, // Epic
      { wch: 14 }, // Start date
      { wch: 14 }, // Deadline
      { wch: 14 }, // Status
      { wch: 14 }, // Expected
      { wch: 14 }, // Actual
      { wch: 14 }, // Submitted
      { wch: 12 }, // Score
      { wch: 40 }, // Submission link
    ]

    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, "Tasks")

    // summary sheet
    const stats = computeStats(tasks)
    const summaryRows = [
      { "":  "Intern",         " ": name },
      { "":  "Generated",      " ": new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" }) },
      { "":  "",               " ": "" },
      { "":  "Total tasks",    " ": stats.total },
      { "":  "Completed",      " ": stats.done },
      { "":  "Completion %",   " ": `${stats.pctDone}%` },
      { "":  "On-time %",      " ": stats.pctOnTime != null ? `${stats.pctOnTime}%` : "—" },
      { "":  "Total hours",    " ": stats.totalActual > 0 ? `${stats.totalActual}h` : "—" },
      { "":  "Expected hours", " ": stats.totalExpected > 0 ? `${stats.totalExpected}h` : "—" },
      { "":  "Avg score",      " ": stats.avgScore != null ? `${stats.avgScore}/100` : "—" },
    ]
    const wsSummary = XLSX.utils.json_to_sheet(summaryRows, { skipHeader: true })
    wsSummary["!cols"] = [{ wch: 18 }, { wch: 30 }]
    XLSX.utils.book_append_sheet(wb, wsSummary, "Summary")

    XLSX.writeFile(wb, `SpacePoint_${name.replace(/\s+/g, "_")}_Tasks.xlsx`)
  }

  // ── print ──────────────────────────────────────────────────────────────────
  const handlePrint = () => window.print()

  if (!currentUser) return null

  return (
    <div className="flex flex-col gap-6">

      {/* ── print styles ────────────────────────────────────────────────── */}
      <style>{`
        @media print {
          @page { size: A4 landscape; margin: 18mm 16mm; }
          body * { visibility: hidden; }
          #pdf-report, #pdf-report * { visibility: visible; }
          #pdf-report {
            position: fixed; inset: 0;
            font-family: 'Inter', system-ui, sans-serif;
            font-size: 10pt;
            color: #111;
            background: white;
          }
          .no-print { display: none !important; }
          .pdf-table { width: 100%; border-collapse: collapse; }
          .pdf-table thead { display: table-header-group; }
          .pdf-table th {
            background: #f4f4f5;
            font-size: 7.5pt;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #71717a;
            padding: 6px 8px;
            text-align: left;
            border-bottom: 1.5px solid #e4e4e7;
          }
          .pdf-table td {
            padding: 6px 8px;
            font-size: 8.5pt;
            border-bottom: 1px solid #f4f4f5;
            page-break-inside: avoid;
          }
          .pdf-table tr { page-break-inside: avoid; }
          .pdf-table tbody tr:nth-child(even) td { background: #fafafa; }
          .pdf-stat-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 10px; margin: 14px 0 18px; }
          .pdf-stat-box { border: 1.5px solid #e4e4e7; border-radius: 8px; padding: 10px 12px; }
          .pdf-stat-label { font-size: 7pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #71717a; margin-bottom: 4px; }
          .pdf-stat-value { font-size: 20pt; font-weight: 800; color: #111; line-height: 1; }
          .pdf-stat-sub { font-size: 7.5pt; color: #a1a1aa; margin-top: 3px; }
          .pdf-divider { border: none; border-top: 1px solid #e4e4e7; margin: 12px 0; }
          .pdf-badge { display: inline-block; padding: 2px 7px; border-radius: 99px; font-size: 7.5pt; font-weight: 700; }
          .pdf-badge-done { background: #000; color: #fff; }
          .pdf-badge-progress { background: #d6c7e1; color: #643f83; }
          .pdf-badge-todo { background: #f4f4f5; color: #71717a; }
          .pdf-score-high { background: #000; color: #fff; }
          .pdf-score-mid  { background: #d6c7e1; color: #643f83; }
          .pdf-score-low  { background: #fee2e2; color: #ef4444; }
        }
        #pdf-report { display: none; }
        @media print { #pdf-report { display: block; } }
      `}</style>

      {/* ── Page header ─────────────────────────────────────────────────── */}
      <div className="flex items-end justify-between no-print">
        <div>
          <h1 className="text-xl font-bold text-foreground tracking-tight">Work Tracker</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {isIntern ? "Your task history and time log" : "View intern progress and time accuracy"}
          </p>
        </div>
        {targetId && tasks.length > 0 && (
          <div className="flex items-center gap-2">
            <button
              onClick={handleExportSheet}
              className="flex items-center gap-1.5 h-9 px-4 border border-border bg-background hover:bg-muted rounded-xl text-sm font-medium text-foreground transition-colors"
            >
              <Sheet size={14} /> Export sheet
            </button>
            <button
              onClick={handlePrint}
              className="flex items-center gap-1.5 h-9 px-4 border border-border bg-background hover:bg-muted rounded-xl text-sm font-medium text-foreground transition-colors"
            >
              <Download size={14} /> Export PDF
            </button>
          </div>
        )}
      </div>

      {/* ── Intern selector (admin / leader only) ───────────────────────── */}
      {(isAdmin || isLeader) && (
        <div className="no-print">
          <label className="block text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
            {isAdmin ? "Select intern" : "Team member"}
          </label>
          {interns.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {isLeader ? "No interns in your team yet." : "No intern accounts found."}
            </p>
          ) : (
            <div className="relative w-full max-w-xs">
              <select
                value={selectedUserId}
                onChange={(e) => setSelectedUserId(e.target.value)}
                className="w-full h-10 pl-4 pr-10 rounded-xl text-sm font-medium border bg-background text-foreground border-border hover:border-muted-foreground/30 focus:outline-none focus:ring-1 focus:ring-primary appearance-none cursor-pointer transition-colors"
              >
                <option value="" className="bg-background text-muted-foreground">Select an intern...</option>
                {interns.map((u) => (
                  <option key={u.id} value={u.id} className="bg-background text-foreground">
                    {u.full_name}
                  </option>
                ))}
              </select>
              <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none text-muted-foreground">
                <ChevronDown size={16} />
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Empty / loading state ────────────────────────────────────────── */}
      {!targetId && (isAdmin || isLeader) && (
        <div className="flex items-center justify-center h-40 border border-dashed border-border rounded-2xl">
          <p className="text-sm text-muted-foreground flex items-center gap-2">
            <Users size={16} /> Select an intern to view their tracker
          </p>
        </div>
      )}

      {isLoading && (
        <div className="flex items-center justify-center h-40">
          <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {/* ── Main printable area ──────────────────────────────────────────── */}
      {targetId && !isLoading && (
        <div id="tracker-print" ref={printRef}>

          {tasks.length === 0 ? (
            <div className="flex items-center justify-center h-40 border border-dashed border-border rounded-2xl">
              <p className="text-sm text-muted-foreground">No tasks assigned yet</p>
            </div>
          ) : (
            <>
              {/* ── Stats ─────────────────────────────────────────────── */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 mb-6">
                <StatCard
                  label="Completed"
                  value={`${stats.done}/${stats.total}`}
                  sub={`${stats.pctDone}%`}
                  highlight={stats.pctDone >= 80}
                />
                <StatCard
                  label="On time"
                  value={stats.pctOnTime != null ? `${stats.pctOnTime}%` : "—"}
                  sub={stats.pctOnTime != null ? "of done tasks" : "no data yet"}
                  highlight={stats.pctOnTime != null && stats.pctOnTime >= 70}
                />
                <StatCard
                  label="Total hours"
                  value={stats.totalActual > 0 ? `${stats.totalActual}h` : "—"}
                  sub={stats.totalExpected > 0 ? `of ${stats.totalExpected}h expected` : "no estimates yet"}
                />
                <StatCard
                  label="Avg time delta"
                  value={stats.avgDelta != null ? `${stats.avgDelta > 0 ? "+" : ""}${stats.avgDelta.toFixed(1)}h` : "—"}
                  sub={stats.avgDelta != null
                    ? stats.avgDelta > 0 ? "over estimate" : stats.avgDelta < 0 ? "under estimate" : "on point"
                    : "no data yet"}
                  highlight={stats.avgDelta != null && stats.avgDelta <= 0}
                />
                <StatCard
                  label="Score"
                  value={stats.avgScore != null ? `${stats.avgScore}/100` : "—"}
                  sub={stats.scoredCount > 0 ? `across ${stats.scoredCount} reviewed task${stats.scoredCount !== 1 ? "s" : ""}` : "no reviewed tasks yet"}
                  highlight={stats.avgScore != null && stats.avgScore >= 80}
                />
              </div>

              {/* ── Table ─────────────────────────────────────────────── */}
              <div className="overflow-x-auto rounded-2xl border border-border">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="bg-muted/50 border-b border-border">
                      {["Task", "Module", "Epic", "Start date", "Deadline", "Status", "Expected", "Actual", "Submitted", "Score", "Submission link"].map((h) => (
                        <th key={h} className="text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider px-4 py-3 whitespace-nowrap">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tasks.map((task, i) => {
                      const latestSub = task.submissions?.[task.submissions.length - 1]
                      const isOverdue = task.due_date && new Date(task.due_date) < new Date() && task.status !== "done"
                      return (
                        <tr key={task.id} className={cn(
                          "border-b border-border transition-colors hover:bg-muted/50",
                          i % 2 === 1 ? "bg-muted/20" : "bg-card"
                        )}>
                          {/* Task */}
                          <td className="px-4 py-3 font-medium text-foreground max-w-[180px]">
                            <p className="truncate">{task.title}</p>
                          </td>
                          {/* Module */}
                          <td className="px-4 py-3 max-w-[140px]">
                            {task.module_title
                              ? <p className="text-xs text-muted-foreground truncate">{task.module_title}</p>
                              : <span className="text-muted-foreground/30">—</span>}
                          </td>
                          {/* Epic */}
                          <td className="px-4 py-3">
                            {task.epic_title
                              ? <span className="text-[11px] font-semibold text-[#643f83] bg-[#d6c7e1]/40 px-2 py-0.5 rounded-full whitespace-nowrap">{task.epic_title}</span>
                              : <span className="text-muted-foreground/30">—</span>}
                          </td>
                          {/* Start date */}
                          <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{fmtDate(task.created_at)}</td>
                          {/* Deadline */}
                          <td className={cn("px-4 py-3 whitespace-nowrap", isOverdue ? "text-destructive font-medium" : "text-muted-foreground")}>
                            {fmtDate(task.due_date)}
                          </td>
                          {/* Status */}
                          <td className="px-4 py-3">
                            <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap", statusBadge(task.status))}>
                              {task.status.replace("_", " ")}
                            </span>
                          </td>
                          {/* Expected */}
                          <td className="px-4 py-3 text-muted-foreground text-right whitespace-nowrap">{fmtHours(task.expected_time)}</td>
                          {/* Actual */}
                          <td className="px-4 py-3 text-muted-foreground text-right whitespace-nowrap">{fmtHours(task.actual_time)}</td>
                          {/* Submitted */}
                          <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                            {latestSub?.submitted_at
                              ? fmtDate(latestSub.submitted_at)
                              : <span className="text-muted-foreground/30">—</span>}
                          </td>
                          {/* Score */}
                          <td className="px-4 py-3 text-center">
                            {latestSub?.status === "reviewed" && latestSub.score != null ? (
                              <span className={cn(
                                "text-xs font-bold px-2 py-0.5 rounded-full",
                                latestSub.score >= 80 ? "bg-foreground text-background" :
                                latestSub.score >= 60 ? "bg-[#d6c7e1] text-[#643f83]" :
                                "bg-destructive/20 text-destructive dark:text-red-400"
                              )}>
                                {latestSub.score}/100
                              </span>
                            ) : <span className="text-muted-foreground/30">—</span>}
                          </td>
                          {/* Submission link */}
                          <td className="px-4 py-3 max-w-[160px]">
                            {latestSub?.link
                              ? <a href={latestSub.link} target="_blank" rel="noreferrer"
                                  className="text-[#643f83] dark:text-snuff hover:underline text-xs truncate block">
                                  {latestSub.link}
                                </a>
                              : <span className="text-muted-foreground/30">—</span>}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

            </>
          )}
        </div>
      )}

      {/* ── PDF report (hidden on screen, shown only when printing) ─────── */}
      {targetId && tasks.length > 0 && selectedUser && (
        <div id="pdf-report">
          {/* header bar */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <img src={logoImg} alt="SpacePoint" style={{ height: 48 }} />
            <div style={{ textAlign: "right", fontSize: "8pt", color: "#71717a" }}>
              <div style={{ fontWeight: 700, fontSize: "9pt", color: "#111" }}>SpacePoint Internship</div>
              <div>Performance Report</div>
              <div>Generated {new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}</div>
            </div>
          </div>

          <hr className="pdf-divider" />

          {/* certification text */}
          <div style={{ margin: "14px 0", lineHeight: 1.6 }}>
            <div style={{ fontSize: "13pt", fontWeight: 800, marginBottom: 6 }}>Internship Performance Report</div>
            <p style={{ fontSize: "9.5pt", color: "#3f3f46" }}>
              This report certifies that <strong>{selectedUser.full_name}</strong> has served as an intern
              at <strong>SpacePoint Internship</strong>
              {teamName ? <> on the <strong>{teamName}</strong> team</> : null}
              {" "}from{" "}
              <strong>{new Date(selectedUser.created_at!).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}</strong>
              {" "}to{" "}
              <strong>{new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}</strong>.
              {" "}During this period, they were assigned <strong>{stats.total}</strong> task{stats.total !== 1 ? "s" : ""} and
              completed <strong>{stats.done}</strong> of them.
            </p>
          </div>

          {/* stat boxes */}
          <div className="pdf-stat-grid">
            {[
              { label: "Completed",   value: `${stats.done}/${stats.total}`, sub: `${stats.pctDone}% completion rate` },
              { label: "On time",     value: stats.pctOnTime != null ? `${stats.pctOnTime}%` : "—", sub: stats.pctOnTime != null ? "of completed tasks" : "no deadline data" },
              { label: "Hours logged",value: stats.totalActual > 0 ? `${stats.totalActual}h` : "—", sub: stats.totalExpected > 0 ? `of ${stats.totalExpected}h estimated` : "no time estimates" },
              { label: "Score",       value: stats.avgScore != null ? `${stats.avgScore}/100` : "—", sub: stats.scoredCount > 0 ? `across ${stats.scoredCount} reviewed task${stats.scoredCount !== 1 ? "s" : ""}` : "no reviewed tasks" },
            ].map(({ label, value, sub }) => (
              <div key={label} className="pdf-stat-box">
                <div className="pdf-stat-label">{label}</div>
                <div className="pdf-stat-value">{value}</div>
                <div className="pdf-stat-sub">{sub}</div>
              </div>
            ))}
          </div>

          <hr className="pdf-divider" />

          {/* task table */}
          <table className="pdf-table">
            <thead>
              <tr>
                {["Task", "Module", "Epic", "Date assigned", "Deadline", "Status", "Exp. (h)", "Act. (h)", "Submitted", "Score"].map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => {
                const latestSub = task.submissions?.[task.submissions.length - 1]
                const scoreVal  = latestSub?.status === "reviewed" && latestSub.score != null ? latestSub.score : null
                const scoreClass = scoreVal == null ? "" : scoreVal >= 80 ? "pdf-score-high" : scoreVal >= 60 ? "pdf-score-mid" : "pdf-score-low"
                const statusClass = task.status === "done" ? "pdf-badge pdf-badge-done" : task.status === "in_progress" ? "pdf-badge pdf-badge-progress" : "pdf-badge pdf-badge-todo"
                return (
                  <tr key={task.id}>
                    <td style={{ maxWidth: 160, wordBreak: "break-word" }}>{task.title}</td>
                    <td>{task.module_title ?? "—"}</td>
                    <td>{task.epic_title ?? "—"}</td>
                    <td>{fmtDate(task.created_at)}</td>
                    <td>{fmtDate(task.due_date)}</td>
                    <td><span className={statusClass}>{task.status.replace("_", " ")}</span></td>
                    <td style={{ textAlign: "right" }}>{fmtHours(task.expected_time)}</td>
                    <td style={{ textAlign: "right" }}>{fmtHours(task.actual_time)}</td>
                    <td>{latestSub?.submitted_at ? fmtDate(latestSub.submitted_at) : "—"}</td>
                    <td>{scoreVal != null ? <span className={`pdf-badge ${scoreClass}`}>{scoreVal}/100</span> : "—"}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          {/* footer */}
          <hr className="pdf-divider" style={{ marginTop: 18 }} />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "7.5pt", color: "#a1a1aa" }}>
            <span>SpacePoint Internship · Confidential</span>
            <span>{selectedUser.full_name} · {new Date().getFullYear()}</span>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, highlight }: {
  label: string; value: string; sub: string; highlight?: boolean
}) {
  return (
    <div className={cn(
      "rounded-2xl border p-4 flex flex-col gap-1 transition-colors",
      highlight
        ? "border-[#643f83] bg-[#643f83] text-[#d6c7e1] dark:border-[#d6c7e1] dark:bg-[#d6c7e1] dark:text-[#643f83]"
        : "border-border bg-card text-foreground"
    )}>
      <span className={cn(
        "text-xs font-semibold uppercase tracking-wider mb-1",
        highlight ? "text-[#d6c7e1]/80 dark:text-[#643f83]/80" : "text-muted-foreground"
      )}>
        {label}
      </span>
      <p className={cn(
        "text-2xl font-bold",
        highlight ? "text-white dark:text-[#643f83]" : "text-foreground"
      )}>
        {value}
      </p>
      <p className={cn(
        "text-xs",
        highlight ? "text-[#d6c7e1]/90 dark:text-[#643f83]/90" : "text-muted-foreground"
      )}>
        {sub}
      </p>
    </div>
  )
}
