import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  GraduationCap, Users, UserCheck, Target, CheckSquare, Download, ArrowUpRight,
} from "lucide-react"

import { useAuth } from "@/context/AuthContext"
import { getDashboardStatsApi, getMyPointsApi } from "@/api/ambassadors/dashboard"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { PageHeader, StatCard, Spinner, EmptyState } from "@/pages/ambassadors/components/common"
import { TitleProgress, AchievementGrid } from "@/pages/ambassadors/components/title"
import { TitleUpCelebration } from "@/pages/ambassadors/components/Celebration"
import { LeaderboardTable } from "@/pages/ambassadors/components/Leaderboard"
import { generateImpactReport } from "@/lib/pdf"

export default function Dashboard() {
  const { currentUser } = useAuth()
  const [season, setSeason] = useState(false)
  const [celebrate, setCelebrate] = useState(false)

  const { data: stats, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboardStatsApi,
  })
  const { data: points = [] } = useQuery({ queryKey: ["points-me"], queryFn: getMyPointsApi })

  // Title-up celebration: fire when the current title id changes upward.
  useEffect(() => {
    if (!stats?.current_title) return
    const key = `last_title_${currentUser?.id}`
    const prev = localStorage.getItem(key)
    if (prev && prev !== stats.current_title.id) setCelebrate(true)
    localStorage.setItem(key, stats.current_title.id)
  }, [stats?.current_title, currentUser?.id])

  if (isLoading || !stats) return <Spinner />

  const board = season ? stats.season_leaderboard : stats.leaderboard

  return (
    <div>
      <PageHeader
        title="Mission Control"
        subtitle="Your ambassador orbit at a glance."
        action={
          <Button variant="outline" onClick={() => generateImpactReport(currentUser?.full_name ?? "Ambassador", stats)}>
            <Download size={16} /> Impact report
          </Button>
        }
      />

      {/* Title + points hero */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-0">
            <CardTitle>Title</CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            <TitleProgress
              current={stats.current_title}
              next={stats.next_title}
              pointsToNext={stats.points_to_next}
              progress={stats.progress_to_next}
            />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5 flex flex-col justify-center h-full">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Lifetime points</p>
            <p className="text-4xl font-bold text-foreground font-outfit mt-1">
              {stats.points_balance.toLocaleString()}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Rank #{stats.my_rank} · {stats.season_points.toLocaleString()} this month
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4 mb-6">
        <StatCard icon={<GraduationCap size={20} />} label="Sessions Done" value={stats.sessions_done} sub={`${stats.sessions_pending} pending`} />
        <StatCard icon={<Users size={20} />} label="Students Reached" value={stats.students_reached} sub="Impact" />
        <StatCard icon={<UserCheck size={20} />} label="Teachers" value={stats.active_teachers} sub={`${stats.pending_teachers} pending`} />
        <StatCard icon={<UserCheck size={20} />} label="Instructors" value={stats.active_instructors} sub={`${stats.pending_instructors} pending`} />
        <StatCard icon={<Target size={20} />} label="Leads Converted" value={stats.converted_leads} sub={`${stats.pending_leads} pending`} />
        <StatCard icon={<CheckSquare size={20} />} label="Tasks Done" value={stats.completed_tasks} sub={`${stats.pending_tasks} pending`} />
      </div>

      {/* Achievements */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Badges</CardTitle>
        </CardHeader>
        <CardContent>
          <AchievementGrid achievements={stats.achievements} />
        </CardContent>
      </Card>

      {/* Leaderboard */}
      <Card className="mb-6">
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Global Leaderboard</CardTitle>
          <div className="flex rounded-lg border border-border overflow-hidden text-xs font-semibold">
            <button
              onClick={() => setSeason(false)}
              className={!season ? "px-3 py-1.5 bg-foreground text-background" : "px-3 py-1.5 text-muted-foreground hover:bg-muted/50"}
            >
              All-time
            </button>
            <button
              onClick={() => setSeason(true)}
              className={season ? "px-3 py-1.5 bg-foreground text-background" : "px-3 py-1.5 text-muted-foreground hover:bg-muted/50"}
            >
              This month
            </button>
          </div>
        </CardHeader>
        <CardContent>
          <LeaderboardTable rows={board} highlightId={currentUser?.id} myRank={stats.my_rank} />
        </CardContent>
      </Card>

      {/* Points log */}
      <Card>
        <CardHeader>
          <CardTitle>Points History</CardTitle>
        </CardHeader>
        <CardContent>
          {points.length === 0 ? (
            <EmptyState title="No points yet" hint="Complete tasks, recruit teachers, or convert leads to earn points." />
          ) : (
            <div className="divide-y divide-gray-50 dark:divide-zinc-800">
              {points.map((tx) => (
                <div key={tx.id} className="flex items-center justify-between py-2.5">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-full bg-green-50 dark:bg-green-950/30 text-green-600 dark:text-green-400 flex items-center justify-center shrink-0">
                      <ArrowUpRight size={15} />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm text-foreground truncate">{tx.reason}</p>
                      <p className="text-xs text-muted-foreground">{new Date(tx.created_at).toLocaleString()}</p>
                    </div>
                  </div>
                  <span className="text-sm font-bold text-green-600 dark:text-green-400 whitespace-nowrap">+{tx.amount} pts</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <TitleUpCelebration title={stats.current_title} open={celebrate} onClose={() => setCelebrate(false)} />
    </div>
  )
}
