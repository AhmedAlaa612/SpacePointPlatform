import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Calendar,
  Sparkles,
  Send,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  Search,
  ChevronLeft,
  ChevronRight,
  Cake,
  Image as ImageIcon,
  X,
  Clock,
} from "lucide-react"

import {
  getUpcomingBirthdaysApi,
  getBirthdayLogsApi,
  retryBirthdayEmailApi,
  getBirthdayStatsApi,
  type BirthdayEmailLog,
} from "@/api/birthdays"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ROLE_LABEL, type Role } from "@/types/shared"
import { ROLE_BADGE } from "@/components/ProfileStatsCards"

export default function Birthdays() {
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState<"upcoming" | "logs">("upcoming")
  const [daysFilter, setDaysFilter] = useState<number>(30)
  const [logStatusFilter, setLogStatusFilter] = useState<string>("all")
  const [searchQuery, setSearchQuery] = useState("")
  const [logPage, setLogPage] = useState(1)
  const [selectedLog, setSelectedLog] = useState<BirthdayEmailLog | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  // 1. Stats query
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["admin-birthday-stats"],
    queryFn: getBirthdayStatsApi,
  })

  // 2. Upcoming birthdays query
  const { data: upcomingUsers = [], isLoading: upcomingLoading } = useQuery({
    queryKey: ["admin-birthdays-upcoming", daysFilter],
    queryFn: () => getUpcomingBirthdaysApi(daysFilter),
  })

  // 3. Dispatch logs query
  const { data: logsData, isLoading: logsLoading } = useQuery({
    queryKey: ["admin-birthday-logs", logPage, logStatusFilter],
    queryFn: () =>
      getBirthdayLogsApi({
        page: logPage,
        page_size: 15,
        status: logStatusFilter === "all" ? undefined : logStatusFilter,
      }),
    enabled: activeTab === "logs",
  })

  // 5. Retry / Dispatch mutation
  const retryMutation = useMutation({
    mutationFn: (id: string) => retryBirthdayEmailApi(id),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["admin-birthday-stats"] })
      qc.invalidateQueries({ queryKey: ["admin-birthdays-upcoming"] })
      qc.invalidateQueries({ queryKey: ["admin-birthday-logs"] })
      qc.invalidateQueries({ queryKey: ["admin-birthday-failed-logs"] })
      setActionError(null)
      if (data.status === "sent") {
        setActionSuccess(`Birthday email successfully dispatched to ${data.user_full_name}! 🚀`)
      } else {
        setActionError(`Email dispatch attempt finished with status "${data.status}": ${data.error_message || "Unknown error"}`)
      }
      setTimeout(() => {
        setActionSuccess(null)
        setActionError(null)
      }, 6000)
    },
    onError: (err: any) => {
      setActionSuccess(null)
      setActionError(err?.response?.data?.detail || "Failed to trigger birthday email dispatch.")
      setTimeout(() => setActionError(null), 6000)
    },
  })

  // Filtered upcoming users based on search
  const filteredUpcoming = upcomingUsers.filter((u) => {
    const q = searchQuery.toLowerCase().trim()
    if (!q) return true
    return (
      u.full_name.toLowerCase().includes(q) ||
      u.email.toLowerCase().includes(q) ||
      u.roles.some((r) => r.toLowerCase().includes(q))
    )
  })

  return (
    <div className="max-w-7xl mx-auto flex flex-col gap-6 p-4 sm:p-6 lg:p-8">
      {/* ── Header ────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="p-2.5 rounded-2xl bg-gradient-to-tr from-purple-500/20 to-indigo-500/20 text-purple-400 border border-purple-500/30">
              <Cake size={24} />
            </span>
            <div>
              <h1 className="text-2xl font-bold font-display tracking-tight text-foreground flex items-center gap-2">
                Birthday Celebrations
              </h1>
              <p className="text-xs text-muted-foreground mt-0.5">
                Automated cosmic birthday greetings with personalized historical NASA Astronomy Pictures of the Day
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              qc.invalidateQueries({ queryKey: ["admin-birthday-stats"] })
              qc.invalidateQueries({ queryKey: ["admin-birthdays-upcoming"] })
              qc.invalidateQueries({ queryKey: ["admin-birthday-logs"] })
              qc.invalidateQueries({ queryKey: ["admin-birthday-failed-logs"] })
            }}
            className="h-9 gap-1.5 text-xs rounded-xl"
          >
            <RefreshCw size={13} className="text-muted-foreground" />
            Refresh
          </Button>
        </div>
      </div>

      {/* ── Status Feedback Banners ────────────────────────── */}
      {actionSuccess && (
        <div className="flex items-center gap-3 p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/25 text-emerald-400 text-sm">
          <CheckCircle2 size={18} className="shrink-0 text-emerald-400" />
          <span>{actionSuccess}</span>
        </div>
      )}
      {actionError && (
        <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-500/10 border border-rose-500/25 text-rose-400 text-sm">
          <AlertTriangle size={18} className="shrink-0 text-rose-400" />
          <span>{actionError}</span>
        </div>
      )}

      {/* ── Metrics Cards ─────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3.5">
        <Card className="border border-border/60 bg-card/60 backdrop-blur-sm">
          <CardContent className="p-4 flex flex-col justify-between">
            <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Birthdays On File
            </span>
            <div className="mt-2 flex items-baseline gap-1.5">
              <span className="text-2xl font-bold font-display text-foreground">
                {statsLoading ? "—" : stats?.total_with_birthdays ?? 0}
              </span>
              <span className="text-xs text-muted-foreground">profiles</span>
            </div>
          </CardContent>
        </Card>

        <Card className="border border-border/60 bg-card/60 backdrop-blur-sm">
          <CardContent className="p-4 flex flex-col justify-between">
            <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Dispatched This Year
            </span>
            <div className="mt-2 flex items-baseline gap-1.5">
              <span className="text-2xl font-bold font-display text-emerald-400">
                {statsLoading ? "—" : stats?.sent_this_year ?? 0}
              </span>
              <span className="text-xs text-emerald-400/70 font-mono">sent</span>
            </div>
          </CardContent>
        </Card>

        <Card className="border border-border/60 bg-card/60 backdrop-blur-sm">
          <CardContent className="p-4 flex flex-col justify-between">
            <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Next 7 Days
            </span>
            <div className="mt-2 flex items-baseline gap-1.5">
              <span className="text-2xl font-bold font-display text-purple-400">
                {statsLoading ? "—" : stats?.upcoming_7_days ?? 0}
              </span>
              <span className="text-xs text-purple-400/70">celebrations</span>
            </div>
          </CardContent>
        </Card>

        <Card className="border border-border/60 bg-card/60 backdrop-blur-sm">
          <CardContent className="p-4 flex flex-col justify-between">
            <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Next 30 Days
            </span>
            <div className="mt-2 flex items-baseline gap-1.5">
              <span className="text-2xl font-bold font-display text-indigo-400">
                {statsLoading ? "—" : stats?.upcoming_30_days ?? 0}
              </span>
              <span className="text-xs text-indigo-400/70">celebrations</span>
            </div>
          </CardContent>
        </Card>

        <Card className={`border backdrop-blur-sm col-span-2 lg:col-span-1 ${
          (stats?.failed_count ?? 0) > 0
            ? "border-rose-500/30 bg-rose-500/5 text-rose-300"
            : "border-border/60 bg-card/60 text-muted-foreground"
        }`}>
          <CardContent className="p-4 flex flex-col justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider">
              Failed Deliveries
            </span>
            <div className="mt-2 flex items-baseline gap-1.5">
              <span className={`text-2xl font-bold font-display ${
                (stats?.failed_count ?? 0) > 0 ? "text-rose-400" : "text-foreground"
              }`}>
                {statsLoading ? "—" : stats?.failed_count ?? 0}
              </span>
              <span className="text-xs opacity-70 font-mono">requiring retry</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Navigation Tabs ───────────────────────────────── */}
      <div className="flex border-b border-border gap-2 overflow-x-auto whitespace-nowrap scrollbar-none">
        <button
          onClick={() => setActiveTab("upcoming")}
          className={`pb-3 px-3 text-sm font-semibold transition-colors border-b-2 flex items-center gap-2 ${
            activeTab === "upcoming"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          <Calendar size={15} />
          Upcoming Celebrations
          {upcomingUsers.length > 0 && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-mono">
              {upcomingUsers.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab("logs")}
          className={`pb-3 px-3 text-sm font-semibold transition-colors border-b-2 flex items-center gap-2 ${
            activeTab === "logs"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          <Sparkles size={15} />
          Dispatch Audit & Delivery Logs
          {(stats?.failed_count ?? 0) > 0 && (
            <span
              className="text-[10px] px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-400 font-mono font-bold"
              title={`${stats?.failed_count} delivery error(s)`}
            >
              {stats?.failed_count} failed
            </span>
          )}
        </button>
      </div>

      {/* ── TAB 1: Upcoming Celebrations ──────────────────── */}
      {activeTab === "upcoming" && (
        <div className="flex flex-col gap-4">
          {/* Controls Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-card/40 p-3 rounded-2xl border border-border/60">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs text-muted-foreground font-semibold px-2 uppercase tracking-wider">
                Lookahead:
              </span>
              {[7, 30].map((days) => (
                <button
                  key={days}
                  onClick={() => setDaysFilter(days)}
                  className={`text-xs px-3 py-1.5 rounded-xl font-medium transition-all ${
                    daysFilter === days
                      ? "bg-primary text-primary-foreground shadow-sm shadow-primary/20"
                      : "bg-muted/40 text-muted-foreground hover:text-foreground hover:bg-muted"
                  }`}
                >
                  Next {days} Days
                </button>
              ))}
            </div>

            <div className="relative w-full sm:w-64">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search user or role..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full h-8 pl-9 pr-3 rounded-xl bg-background border border-border text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>

          {/* List or Table */}
          {upcomingLoading ? (
            <div className="py-20 flex justify-center items-center">
              <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          ) : filteredUpcoming.length === 0 ? (
            <div className="py-16 text-center rounded-2xl border border-dashed border-border p-6 bg-card/20">
              <Cake size={36} className="mx-auto text-muted-foreground/40 mb-3" />
              <p className="text-sm font-medium text-foreground">No upcoming birthdays in this time window</p>
              <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
                Try widening your lookahead filter to 30 or 90 days, or check that students and instructors have filled in their birthdates in their profiles.
              </p>
            </div>
          ) : (
            <div className="border border-border/80 rounded-2xl overflow-hidden bg-card/60 backdrop-blur-sm">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm border-collapse">
                  <thead>
                    <tr className="border-b border-border bg-muted/20 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                      <th className="py-3 px-4">User</th>
                      <th className="py-3 px-4">Role</th>
                      <th className="py-3 px-4">Birthdate</th>
                      <th className="py-3 px-4">Countdown</th>
                      <th className="py-3 px-4">Current Year Status</th>
                      <th className="py-3 px-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {filteredUpcoming.map((u) => {
                      const isToday = u.days_until === 0
                      const isTomorrow = u.days_until === 1

                      return (
                        <tr key={u.id} className={`hover:bg-muted/30 transition-colors ${isToday ? "bg-purple-500/5" : ""}`}>
                          {/* User */}
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-3">
                              <div className="w-9 h-9 rounded-full bg-muted border border-border flex items-center justify-center font-bold text-xs overflow-hidden shrink-0">
                                {u.photo_url ? (
                                  <img src={u.photo_url} alt={u.full_name} className="w-full h-full object-cover" />
                                ) : (
                                  u.full_name.slice(0, 2).toUpperCase()
                                )}
                              </div>
                              <div className="min-w-0">
                                <p className="font-semibold text-foreground truncate">{u.full_name}</p>
                                <p className="text-xs text-muted-foreground truncate">{u.email}</p>
                              </div>
                            </div>
                          </td>

                          {/* Role Badges */}
                          <td className="py-3 px-4">
                            <div className="flex flex-wrap gap-1">
                              {u.roles.map((r) => (
                                <span
                                  key={r}
                                  className={`text-[10px] font-semibold px-2 py-0.5 rounded-md ${
                                    ROLE_BADGE[r] ?? "bg-muted text-foreground"
                                  }`}
                                >
                                  {ROLE_LABEL[r as Role] ?? r}
                                </span>
                              ))}
                            </div>
                          </td>

                          {/* Birthdate */}
                          <td className="py-3 px-4 font-mono text-xs text-foreground whitespace-nowrap">
                            {new Date(u.birthdate).toLocaleDateString(undefined, {
                              month: "short",
                              day: "numeric",
                            })}
                          </td>

                          {/* Countdown Tag */}
                          <td className="py-3 px-4 whitespace-nowrap">
                            {isToday ? (
                              <span className="inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-md bg-purple-500/20 text-purple-300 border border-purple-500/40 animate-pulse">
                                🎉 Today!
                              </span>
                            ) : isTomorrow ? (
                              <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-md bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
                                Tomorrow
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-md bg-muted/60 text-muted-foreground border border-border/50">
                                <Clock size={12} />
                                In {u.days_until} days
                              </span>
                            )}
                          </td>

                          {/* Status */}
                          <td className="py-3 px-4">
                            {u.has_sent_this_year ? (
                              <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-400">
                                <CheckCircle2 size={13} />
                                Sent for {new Date().getFullYear()}
                              </span>
                            ) : (
                              <span className="text-xs text-muted-foreground italic">
                                Pending automated send
                              </span>
                            )}
                          </td>

                          {/* Actions */}
                          <td className="py-3 px-4 text-right">
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={retryMutation.isPending}
                              onClick={() => retryMutation.mutate(u.id)}
                              className="h-8 text-xs gap-1.5 rounded-xl border-purple-500/30 text-purple-300 hover:bg-purple-500/10"
                              title="Send or preview APOD birthday greeting now"
                            >
                              <Send size={12} />
                              {u.has_sent_this_year ? "Resend Card" : "Send Card Now"}
                            </Button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── TAB 2: Dispatch Audit & Delivery Logs ─────────── */}
      {activeTab === "logs" && (
        <div className="flex flex-col gap-4">
          {/* Controls & Filter Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-card/40 p-3 rounded-2xl border border-border/60">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs text-muted-foreground font-semibold px-2 uppercase tracking-wider">
                Status Filter:
              </span>
              {(["all", "sent", "failed"] as const).map((st) => (
                <button
                  key={st}
                  onClick={() => {
                    setLogStatusFilter(st)
                    setLogPage(1)
                  }}
                  className={`px-3 py-1 text-xs font-semibold rounded-xl capitalize transition-colors ${
                    logStatusFilter === st
                      ? st === "failed"
                        ? "bg-rose-500 text-white shadow-sm"
                        : "bg-primary text-primary-foreground shadow-sm"
                      : "bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground"
                  }`}
                >
                  {st}
                </button>
              ))}
            </div>

            <span className="text-xs text-muted-foreground px-2">
              Showing {logsData?.total ?? 0} record(s)
            </span>
          </div>

          {logsLoading ? (
            <div className="py-20 flex justify-center items-center">
              <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          ) : !logsData || logsData.items.length === 0 ? (
            <div className="py-16 text-center rounded-2xl border border-dashed border-border p-6 bg-card/20">
              <Sparkles size={36} className="mx-auto text-muted-foreground/40 mb-3" />
              <p className="text-sm font-medium text-foreground">No birthday email logs found</p>
              <p className="text-xs text-muted-foreground mt-1">
                Automated logs will accumulate here as daily background jobs or manual dispatches execute.
              </p>
            </div>
          ) : (
            <div className="border border-border/80 rounded-2xl overflow-hidden bg-card/60 backdrop-blur-sm">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm border-collapse">
                  <thead>
                    <tr className="border-b border-border bg-muted/20 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                      <th className="py-3 px-4">Recipient</th>
                      <th className="py-3 px-4">Birthdate</th>
                      <th className="py-3 px-4">Dispatched At</th>
                      <th className="py-3 px-4">NASA Photo Archive</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {logsData.items.map((log) => (
                      <tr key={log.id} className="hover:bg-muted/30 transition-colors">
                        {/* Recipient */}
                        <td className="py-4 px-4">
                          <div className="min-w-0">
                            <p className="font-semibold text-foreground truncate">{log.user_full_name}</p>
                            <p className="text-xs text-muted-foreground truncate">{log.user_email}</p>
                            <div className="flex flex-wrap gap-1 mt-1">
                              {log.user_roles.map((r) => (
                                <span
                                  key={r}
                                  className={`text-[9px] font-semibold px-1.5 py-0.5 rounded-md ${
                                    ROLE_BADGE[r] ?? "bg-muted text-foreground"
                                  }`}
                                >
                                  {ROLE_LABEL[r as Role] ?? r}
                                </span>
                              ))}
                            </div>
                          </div>
                        </td>

                        {/* Birthdate */}
                        <td className="py-4 px-4 whitespace-nowrap">
                          {log.user_birthdate ? (
                            <div className="flex items-center gap-2">
                              <span className="text-sm">🎂</span>
                              <div>
                                <span className="font-semibold text-xs text-foreground block">
                                  {new Date(log.user_birthdate).toLocaleDateString(undefined, {
                                    month: "short",
                                    day: "numeric",
                                  })}
                                </span>
                                <span className="text-[10px] text-muted-foreground font-mono">
                                  {new Date(log.user_birthdate).getFullYear()}
                                </span>
                              </div>
                            </div>
                          ) : (
                            <span className="text-xs text-muted-foreground italic">Not set</span>
                          )}
                        </td>

                        {/* Sent Timestamp */}
                        <td className="py-4 px-4 text-xs font-mono text-muted-foreground whitespace-nowrap">
                          {new Date(log.sent_at).toLocaleString(undefined, {
                            dateStyle: "medium",
                            timeStyle: "short",
                          })}
                        </td>

                        {/* NASA Image Preview (Generous & Prominent) */}
                        <td className="py-4 px-4">
                          <div className="flex items-center gap-3.5">
                            {log.nasa_image_url ? (
                              <button
                                type="button"
                                onClick={() => setSelectedLog(log)}
                                className="relative w-28 h-20 sm:w-36 sm:h-24 rounded-2xl overflow-hidden border border-border group shrink-0 shadow-md bg-black/60 focus:outline-none focus:ring-2 focus:ring-primary/40"
                                title="Click to view full NASA APOD card"
                              >
                                <img
                                  src={log.nasa_image_url}
                                  alt={log.nasa_title || "NASA"}
                                  className="w-full h-full object-cover group-hover:scale-105 transition-all duration-300"
                                />
                                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-end justify-center pb-2 text-[11px] font-medium text-white gap-1">
                                  <ImageIcon size={13} />
                                  <span>View Card</span>
                                </div>
                              </button>
                            ) : (
                              <div className="w-28 h-20 sm:w-36 sm:h-24 rounded-2xl bg-muted border border-border flex items-center justify-center text-muted-foreground text-xs shrink-0">
                                N/A
                              </div>
                            )}
                            <div className="min-w-0 flex flex-col justify-center gap-1.5">
                              <p
                                className="text-sm font-bold text-foreground line-clamp-2 max-w-sm hover:text-primary transition-colors cursor-pointer"
                                onClick={() => setSelectedLog(log)}
                              >
                                {log.nasa_title || "Space Observation"}
                              </p>
                              {log.birth_year_referenced && (
                                <span className="inline-flex items-center gap-1 text-[11px] font-mono text-sky-400 bg-sky-500/10 border border-sky-500/20 px-2 py-0.5 rounded-md w-fit">
                                  NASA APOD Archive • {log.birth_year_referenced}
                                </span>
                              )}
                            </div>
                          </div>
                        </td>

                        {/* Status */}
                        <td className="py-4 px-4 whitespace-nowrap">
                          {log.status === "sent" ? (
                            <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/25">
                              <CheckCircle2 size={12} />
                              Sent
                            </span>
                          ) : log.status === "failed" ? (
                            <span
                              className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-md bg-rose-500/10 text-rose-400 border border-rose-500/25"
                              title={log.error_message || "Failed"}
                            >
                              <AlertTriangle size={12} />
                              Failed
                            </span>
                          ) : (
                            <span className="text-xs font-medium px-2.5 py-1 rounded-md bg-muted text-muted-foreground">
                              {log.status}
                            </span>
                          )}
                        </td>

                        {/* Actions */}
                        <td className="py-4 px-4 text-right whitespace-nowrap">
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={retryMutation.isPending}
                            onClick={() => retryMutation.mutate(log.id)}
                            className="h-8 text-xs gap-1.5 rounded-xl border-border/80 hover:border-primary text-foreground hover:text-primary hover:bg-primary/5"
                            title="Resend birthday email"
                          >
                            <RefreshCw size={12} className={retryMutation.isPending ? "animate-spin" : ""} />
                            Retry
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {logsData.total_pages > 1 && (
                <div className="flex items-center justify-between px-4 py-3 border-t border-border bg-muted/10 text-xs">
                  <span className="text-muted-foreground">
                    Showing page <strong className="text-foreground">{logsData.page}</strong> of{" "}
                    <strong className="text-foreground">{logsData.total_pages}</strong> ({logsData.total} total logs)
                  </span>
                  <div className="flex items-center gap-1.5">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={logPage <= 1}
                      onClick={() => setLogPage((p) => Math.max(1, p - 1))}
                      className="h-7 w-7 p-0 rounded-lg"
                    >
                      <ChevronLeft size={14} />
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={logPage >= logsData.total_pages}
                      onClick={() => setLogPage((p) => p + 1)}
                      className="h-7 w-7 p-0 rounded-lg"
                    >
                      <ChevronRight size={14} />
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── NASA APOD Lightbox Modal ──────────────────────── */}
      {selectedLog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4"
          onClick={() => setSelectedLog(null)}
        >
          <div
            className="bg-card border border-border rounded-2xl max-w-3xl w-full overflow-hidden shadow-2xl flex flex-col max-h-[92vh]"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4 sm:p-5 border-b border-border bg-muted/20">
              <div className="min-w-0">
                <span className="text-[11px] font-bold uppercase tracking-wider text-sky-400 font-mono">
                  NASA Astronomy Picture of the Day • Year {selectedLog.birth_year_referenced}
                </span>
                <h2 className="text-base sm:text-lg font-bold text-foreground truncate mt-0.5">
                  {selectedLog.nasa_title || "Cosmic View"}
                </h2>
              </div>
              <button
                onClick={() => setSelectedLog(null)}
                className="p-1.5 rounded-lg text-muted-foreground hover:bg-muted transition-colors shrink-0"
              >
                <X size={18} />
              </button>
            </div>

            {/* Content */}
            <div className="overflow-y-auto p-5 sm:p-6 flex flex-col gap-4">
              {selectedLog.nasa_image_url && (
                <div className="rounded-2xl overflow-hidden border border-border bg-black/80 flex items-center justify-center">
                  <img
                    src={selectedLog.nasa_image_url}
                    alt={selectedLog.nasa_title || "NASA"}
                    className="w-full max-h-[480px] object-contain"
                  />
                </div>
              )}

              <div className="flex flex-col gap-2">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Astronomy Explanation
                </h4>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {selectedLog.nasa_explanation || "No explanation recorded for this historical astronomical capture."}
                </p>
              </div>

              <div className="p-3.5 rounded-xl bg-muted/30 border border-border text-xs flex flex-col sm:flex-row gap-2 sm:items-center justify-between">
                <div className="flex flex-col gap-0.5">
                  <span className="text-muted-foreground">
                    Recipient: <strong className="text-foreground">{selectedLog.user_full_name}</strong> ({selectedLog.user_email})
                  </span>
                  {selectedLog.user_birthdate && (
                    <span className="text-purple-400 font-semibold flex items-center gap-1.5">
                      <span>🎂</span>
                      Birth Date: {new Date(selectedLog.user_birthdate).toLocaleDateString(undefined, {
                        year: "numeric",
                        month: "long",
                        day: "numeric",
                      })}
                    </span>
                  )}
                </div>
                <div className="flex flex-col sm:items-end gap-0.5 text-muted-foreground">
                  <span>
                    Dispatched on: {new Date(selectedLog.sent_at).toLocaleDateString()}
                  </span>
                  <span className="font-mono text-[10px]">
                    Status: <strong className={selectedLog.status === "sent" ? "text-emerald-400" : "text-rose-400"}>{selectedLog.status.toUpperCase()}</strong>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
