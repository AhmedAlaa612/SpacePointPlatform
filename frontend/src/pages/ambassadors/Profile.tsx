import { useQuery } from "@tanstack/react-query"
import { Link2, Copy, Download, GraduationCap, Users } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { getDashboardStatsApi } from "@/api/ambassadors/dashboard"
import { getTeacherSummaryApi } from "@/api/ambassadors/teacher"
import { generateTeacherImpactReport } from "@/lib/pdf"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { PageHeader, StatCard } from "@/pages/ambassadors/components/common"
import { TitleBadge, TitleProgress, AchievementGrid } from "@/pages/ambassadors/components/title"

export default function Profile() {
  const { currentUser, logout } = useAuth()
  const isAmbassador = currentUser?.roles?.includes("ambassador")
  const isTeacher = currentUser?.roles?.includes("teacher")

  const { data: stats } = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboardStatsApi,
    enabled: isAmbassador,
  })
  const { data: teacher } = useQuery({
    queryKey: ["teacher-summary"],
    queryFn: getTeacherSummaryApi,
    enabled: isTeacher,
  })

  const certificateLink = currentUser
    ? `${window.location.origin}/${isTeacher ? "t" : "a"}/${currentUser.id}`
    : ""

  return (
    <div className="max-w-5xl mx-auto">
      <PageHeader title="Profile" />

      <Card className="mb-6">
        <CardContent className="p-6 flex flex-col items-center text-center gap-3">
          <div className="w-20 h-20 rounded-full bg-zinc-900 dark:bg-zinc-800 text-white dark:text-zinc-100 text-2xl font-bold flex items-center justify-center">
            {currentUser?.full_name?.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
          </div>
          <div className="min-w-0">
            <p className="text-xl font-bold text-foreground">{currentUser?.full_name}</p>
            <p className="text-sm text-gray-500">{currentUser?.email}</p>
            <p className="text-xs text-gray-400 capitalize mt-0.5">
              {currentUser?.roles?.join(", ")}{currentUser?.country ? ` · ${currentUser.country}` : ""}
            </p>
          </div>
        </CardContent>
      </Card>

      {isAmbassador && stats && (
        <>
          <Card className="mb-6">
            <CardHeader><CardTitle>Title & impact</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-3">
                <TitleBadge title={stats.current_title} />
                <span className="text-sm text-gray-500">{stats.points_balance.toLocaleString()} lifetime points</span>
              </div>
              <div className="rounded-xl border border-gray-100 dark:border-zinc-800 p-4 flex items-start gap-3 bg-gray-50/50 dark:bg-zinc-900/30">
                <Link2 size={18} className="text-heliotrope mt-0.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-foreground">Public certificate</p>
                  <p className="text-xs text-gray-500 break-all">{certificateLink}</p>
                </div>
                <Button size="sm" variant="outline" onClick={() => navigator.clipboard?.writeText(certificateLink)}>
                  <Copy size={14} /> Copy
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="mb-6">
            <CardHeader><CardTitle>Badges</CardTitle></CardHeader>
            <CardContent><AchievementGrid achievements={stats.achievements} /></CardContent>
          </Card>
        </>
      )}

      {isTeacher && teacher && (
        <>
          <Card className="mb-6">
            <CardHeader><CardTitle>Title & impact</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-3">
                <TitleBadge title={teacher.current_title} />
                <span className="text-sm text-gray-500">{teacher.points_balance.toLocaleString()} lifetime points</span>
              </div>
              <TitleProgress
                current={teacher.current_title}
                next={teacher.next_title}
                pointsToNext={teacher.points_to_next}
                progress={teacher.progress_to_next}
              />
              <div className="rounded-xl border border-gray-100 dark:border-zinc-800 p-4 flex items-start gap-3 bg-gray-50/50 dark:bg-zinc-900/30">
                <Link2 size={18} className="text-heliotrope mt-0.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-foreground">Public certificate</p>
                  <p className="text-xs text-gray-500 break-all">{certificateLink}</p>
                </div>
                <Button size="sm" variant="outline" onClick={() => navigator.clipboard?.writeText(certificateLink)}>
                  <Copy size={14} /> Copy
                </Button>
              </div>
              <Button variant="outline" onClick={() => generateTeacherImpactReport(currentUser?.full_name ?? "Teacher", teacher)}>
                <Download size={16} /> Impact report (PDF)
              </Button>
            </CardContent>
          </Card>

          <Card className="mb-6">
            <CardHeader><CardTitle>Badges</CardTitle></CardHeader>
            <CardContent><AchievementGrid achievements={teacher.achievements ?? []} /></CardContent>
          </Card>

          <div className="grid grid-cols-2 gap-3 sm:gap-4 mb-6">
            <StatCard icon={<GraduationCap size={20} />} label="Sessions Delivered" value={teacher.stats.sessions_done} />
            <StatCard icon={<Users size={20} />} label="Students Reached" value={teacher.stats.students_reached} />
          </div>
          <Card className="mb-6">
            <CardHeader><CardTitle>Ambassador</CardTitle></CardHeader>
            <CardContent>
              {teacher.ambassador ? (
                <div>
                  <p className="font-medium text-foreground">{teacher.ambassador.full_name}</p>
                  <p className="text-sm text-gray-500">{teacher.ambassador.email}{teacher.ambassador.country ? ` · ${teacher.ambassador.country}` : ""}</p>
                </div>
              ) : (
                <p className="text-sm text-gray-400">Not linked to an ambassador.</p>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {currentUser?.invite_code && (
        <Card className="mb-6">
          <CardHeader><CardTitle>Invite code</CardTitle></CardHeader>
          <CardContent>
            <code className="px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-zinc-800 text-foreground font-mono text-sm">{currentUser.invite_code}</code>
          </CardContent>
        </Card>
      )}

      <Button variant="destructive" onClick={logout}>Sign out</Button>
    </div>
  )
}
