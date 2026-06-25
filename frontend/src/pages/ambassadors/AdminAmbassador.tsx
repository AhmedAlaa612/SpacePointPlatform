import { useQuery } from "@tanstack/react-query"
import { useParams, Link } from "@tanstack/react-router"
import { ArrowLeft, CheckSquare, GraduationCap, Target, UserCheck, Users } from "lucide-react"
import { getAmbassadorNetworkApi, getAmbassadorPointsLogApi, getAmbassadorStatsApi } from "@/api/ambassadors/admin"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { EmptyState, Spinner, StatCard, StatusPill } from "@/pages/ambassadors/components/common"
import { AchievementGrid, TitleProgress } from "@/pages/ambassadors/components/title"
import { NetworkTree } from "@/pages/ambassadors/components/NetworkTree"

export default function AdminAmbassador() {
  const { ambassadorId } = useParams({ strict: false }) as { ambassadorId: string }

  const { data: stats, isLoading } = useQuery({
    queryKey: ["admin-ambassador-stats", ambassadorId],
    queryFn: () => getAmbassadorStatsApi(ambassadorId),
  })
  const { data: network } = useQuery({
    queryKey: ["admin-network", ambassadorId],
    queryFn: () => getAmbassadorNetworkApi(ambassadorId),
  })
  const { data: pointsLog = [] } = useQuery({
    queryKey: ["admin-ambassador-points", ambassadorId],
    queryFn: () => getAmbassadorPointsLogApi(ambassadorId),
  })

  if (isLoading || !stats) return <Spinner />

  const a = stats.ambassador
  const o = stats.overview
  const initials = a.full_name.split(" ").map((w: string) => w[0]).join("").slice(0, 2).toUpperCase()

  return (
    <div>
      <Link to="/ambassadors/admin" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4">
        <ArrowLeft size={16} /> Back to admin
      </Link>

      {/* Identity */}
      <Card className="mb-6">
        <CardContent className="p-6 flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="w-16 h-16 rounded-full bg-foreground text-background text-xl font-bold flex items-center justify-center shrink-0">
            {initials}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="text-xl font-bold">{a.full_name}</p>
              <StatusPill status={a.status} />
            </div>
            <p className="text-sm text-muted-foreground">{a.email}{a.country ? ` · ${a.country}` : ""}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {stats.rank != null ? `Rank #${stats.rank} · ` : ""}{stats.points.balance.toLocaleString()} lifetime pts · {stats.points.season.toLocaleString()} this month
              {a.invite_code ? ` · invite ${a.invite_code}` : ""}
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Title + points */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-0"><CardTitle>Title</CardTitle></CardHeader>
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
            <p className="text-4xl font-bold mt-1">{stats.points.balance.toLocaleString()}</p>
          </CardContent>
        </Card>
      </div>

      {/* Performance */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4 mb-6">
        <StatCard icon={<GraduationCap size={20} />} label="Sessions Done" value={o.sessions_done} sub={`${o.sessions_pending} pending`} />
        <StatCard icon={<Users size={20} />} label="Students Reached" value={o.students_reached} />
        <StatCard icon={<UserCheck size={20} />} label="Teachers" value={o.active_teachers} sub={`${o.pending_teachers} pending`} />
        <StatCard icon={<UserCheck size={20} />} label="Instructors" value={o.active_instructors} sub={`${o.pending_instructors} pending`} />
        <StatCard icon={<Target size={20} />} label="Leads Converted" value={o.converted_leads} sub={`${o.total_leads} total`} />
        <StatCard icon={<CheckSquare size={20} />} label="Tasks Done" value={o.completed_tasks} sub={`${o.pending_tasks} pending`} />
      </div>

      {/* Badges */}
      <Card className="mb-6">
        <CardHeader><CardTitle>Badges</CardTitle></CardHeader>
        <CardContent><AchievementGrid achievements={stats.achievements} /></CardContent>
      </Card>

      {/* Network */}
      <Card className="mb-6">
        <CardHeader><CardTitle>Network</CardTitle></CardHeader>
        <CardContent>
          {network ? (
            <NetworkTree rootName={a.full_name} teachers={network.teachers as any} instructors={network.instructors as any} sessions={network.sessions as any} />
          ) : (
            <EmptyState title="Loading network…" />
          )}
        </CardContent>
      </Card>

      {/* Points log */}
      <Card>
        <CardHeader>
          <CardTitle>Points log</CardTitle>
          <p className="text-xs text-muted-foreground">Every entry that makes up the {stats.points.balance.toLocaleString()} lifetime total.</p>
        </CardHeader>
        <CardContent>
          {pointsLog.length === 0 ? <EmptyState title="No points yet" /> : (
            <div className="divide-y divide-border">
              {pointsLog.map((p) => (
                <div key={p.id} className="flex items-center justify-between gap-3 py-2.5">
                  <div className="min-w-0">
                    <p className="text-sm truncate">{p.reason}</p>
                    <p className="text-xs text-muted-foreground">{new Date(p.created_at).toLocaleString()}</p>
                  </div>
                  <span className={`text-sm font-semibold shrink-0 ${p.amount < 0 ? "text-destructive" : "text-green-600 dark:text-green-400"}`}>
                    {p.amount < 0 ? "" : "+"}{p.amount.toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
