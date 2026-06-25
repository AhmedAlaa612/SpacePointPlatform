import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Medal } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { getAdminLeaderboardApi } from "@/api/ambassadors/admin"
import { getDashboardStatsApi } from "@/api/ambassadors/dashboard"
import { getTeacherLeaderboardApi } from "@/api/ambassadors/teacher"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PageHeader, Spinner, EmptyState } from "@/pages/ambassadors/components/common"
import { LeaderboardTable } from "@/pages/ambassadors/components/Leaderboard"

const MEDAL_SHADES = [
  "text-zinc-900 dark:text-zinc-100",
  "text-zinc-500 dark:text-zinc-400",
  "text-zinc-400 dark:text-zinc-500",
]

export default function LeaderboardPage() {
  const { currentUser } = useAuth()
  const navigate = useNavigate()
  const isAdmin = currentUser?.roles?.includes("admin")
  const isTeacher = currentUser?.roles?.includes("teacher")
  const [season, setSeason] = useState(false)

  if (isTeacher) return <TeacherLeaderboard meId={currentUser?.id} />

  // Admins get the full board; ambassadors reuse their dashboard board.
  const adminQuery = useQuery({
    queryKey: ["admin-leaderboard", season],
    queryFn: () => getAdminLeaderboardApi(season),
    enabled: isAdmin,
  })
  const dashQuery = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboardStatsApi,
    enabled: !isAdmin,
  })

  const rows = isAdmin
    ? adminQuery.data ?? []
    : (season ? dashQuery.data?.season_leaderboard : dashQuery.data?.leaderboard) ?? []
  const loading = isAdmin ? adminQuery.isLoading : dashQuery.isLoading

  return (
    <div>
      <PageHeader title="Leaderboard" subtitle="Ambassadors ranked by points earned." />
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>{season ? "This month" : "All-time"}</CardTitle>
          <div className="flex rounded-lg border border-border overflow-hidden text-xs font-semibold">
            <button onClick={() => setSeason(false)} className={!season ? "px-3 py-1.5 bg-foreground text-background" : "px-3 py-1.5 text-muted-foreground hover:bg-muted/50"}>All-time</button>
            <button onClick={() => setSeason(true)} className={season ? "px-3 py-1.5 bg-foreground text-background" : "px-3 py-1.5 text-muted-foreground hover:bg-muted/50"}>This month</button>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Spinner />
          ) : (
            <LeaderboardTable
              rows={rows}
              highlightId={currentUser?.id}
              myRank={dashQuery.data?.my_rank}
              onRowClick={isAdmin ? (id) => navigate({ to: `/admin/ambassador/${id}` as any }) : undefined}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function TeacherLeaderboard({ meId }: { meId?: string }) {
  const { data: rows = [], isLoading } = useQuery({ queryKey: ["teacher-leaderboard"], queryFn: getTeacherLeaderboardApi })

  return (
    <div>
      <PageHeader title="Teacher Leaderboard" subtitle="Teachers ranked by students reached." />
      <Card>
        <CardContent>
          {isLoading ? (
            <Spinner />
          ) : rows.length === 0 ? (
            <EmptyState title="No teachers yet" />
          ) : (
            <div className="overflow-x-auto -mx-1">
              <table className="w-full text-sm min-w-[560px]">
                <thead>
                  <tr className="text-left text-muted-foreground border-b border-gray-100 dark:border-zinc-800">
                    <th className="py-2.5 pr-3 font-semibold">#</th>
                    <th className="py-2.5 pr-3 font-semibold">Teacher</th>
                    <th className="py-2.5 pr-3 font-semibold">Country</th>
                    <th className="py-2.5 pr-3 font-semibold text-center">Sessions</th>
                    <th className="py-2.5 pr-3 font-semibold text-center">Points</th>
                    <th className="py-2.5 pr-3 font-semibold text-right">Students</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((t, i) => {
                    const me = t.id === meId
                    return (
                      <tr key={t.id} className={`border-b border-gray-50 dark:border-zinc-900 last:border-0 ${me ? "bg-snuff/20 dark:bg-snuff/10" : ""}`}>
                        <td className="py-2.5 pr-3 font-bold text-muted-foreground">
                          {i < 3 ? <Medal size={18} className={`inline ${MEDAL_SHADES[i]}`} strokeWidth={2.2} /> : `#${i + 1}`}
                        </td>
                        <td className="py-2.5 pr-3 font-semibold text-foreground">{t.name}{me && " (you)"}</td>
                        <td className="py-2.5 pr-3 text-muted-foreground">{t.country}</td>
                        <td className="py-2.5 pr-3 text-center text-green-600 dark:text-green-400 font-semibold">{t.sessions_done}</td>
                        <td className="py-2.5 pr-3 text-center text-affair dark:text-heliotrope font-semibold">{t.points.toLocaleString()}</td>
                        <td className="py-2.5 pr-3 text-right font-bold text-foreground">{t.students_reached.toLocaleString()}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
