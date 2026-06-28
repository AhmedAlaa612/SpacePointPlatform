import { Download } from "lucide-react"
import type { AmbassadorCardStats, TeacherCardStats, InstructorCardStats } from "@/api/auth"
import { generateImpactReport, generateTeacherImpactReport } from "@/lib/pdf"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { TitleBadge, TitleProgress, AchievementGrid } from "@/pages/ambassadors/components/title"

export const ROLE_BADGE: Record<string, string> = {
  admin:       "bg-black text-white dark:bg-white dark:text-black",
  intern:      "bg-[#d6c7e1] text-[#643f83]",
  leader:      "bg-[#643f83] text-white",
  ambassador:  "bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-300",
  teacher:     "bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300",
  instructor:  "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300",
  facilitator: "bg-teal-100 text-teal-700 dark:bg-teal-500/20 dark:text-teal-300",
  applicant:   "bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300",
}

export function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex flex-col gap-1 p-4 bg-muted/40 border border-border rounded-2xl">
      <span className="text-2xl font-bold text-foreground">
        {typeof value === "number" ? value.toLocaleString() : value}
      </span>
      <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">{label}</span>
    </div>
  )
}

export function AmbassadorCard({ name, stats }: { name: string; stats: AmbassadorCardStats }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle>Ambassador</CardTitle>
          <Button size="sm" variant="outline" className="gap-1.5"
            onClick={() => generateImpactReport(name, stats as any)}>
            <Download size={13} /> Impact Report
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <TitleBadge title={stats.current_title} />
          <span className="text-sm text-muted-foreground">{stats.points_balance.toLocaleString()} pts</span>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <StatTile label="Students reached"   value={stats.students_reached} />
          <StatTile label="Sessions delivered" value={stats.sessions_done} />
          <StatTile label="Active teachers"    value={stats.active_teachers} />
          <StatTile label="Leads converted"    value={stats.converted_leads} />
          <StatTile label="Tasks completed"    value={stats.completed_tasks} />
          <StatTile label="Active instructors" value={stats.active_instructors} />
        </div>
        {stats.achievements.some((a) => a.earned) && (
          <AchievementGrid achievements={stats.achievements} />
        )}
      </CardContent>
    </Card>
  )
}

export function TeacherCard({ name, stats }: { name: string; stats: TeacherCardStats }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle>Teacher</CardTitle>
          <Button size="sm" variant="outline" className="gap-1.5"
            onClick={() => generateTeacherImpactReport(name, stats as any)}>
            <Download size={13} /> Impact Report
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <TitleProgress
          current={stats.current_title}
          next={stats.next_title}
          pointsToNext={stats.points_to_next}
          progress={stats.progress_to_next}
        />
        <div className="grid grid-cols-3 gap-3">
          <StatTile label="Students reached"   value={stats.stats.students_reached} />
          <StatTile label="Sessions delivered" value={stats.stats.sessions_done} />
          <StatTile label="Upcoming"           value={stats.stats.upcoming} />
        </div>
        {stats.achievements?.some((a) => a.earned) && (
          <AchievementGrid achievements={stats.achievements} />
        )}
      </CardContent>
    </Card>
  )
}

export function InstructorCard({ stats }: { stats: InstructorCardStats }) {
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle>Instructor</CardTitle></CardHeader>
      <CardContent>
        <div className="grid grid-cols-3 gap-3">
          <StatTile label="Earned (AED)"       value={stats.total_earned_aed.toLocaleString()} />
          <StatTile label="Sessions delivered" value={stats.total_sessions} />
          <StatTile label="Training"           value={`${stats.completed_videos}/${stats.total_videos}`} />
        </div>
      </CardContent>
    </Card>
  )
}
