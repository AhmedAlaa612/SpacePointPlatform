import { useState } from "react"
import { ChevronDown, Download } from "lucide-react"
import type { AmbassadorCardStats, TeacherCardStats, InstructorCardStats, StudentCardStats, StudentMissionProgress } from "@/api/auth"
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

/** What a student has done here — the half of a learner's profile the page
 * was missing.
 *
 * Before this the profile showed a program registration and stopped, so the
 * screen that represents a person said how they got in and nothing about
 * what they did once they were in.
 *
 * Courses show a progress bar and a start date because partial progress is
 * the normal state and "when did they begin" is the first thing you ask
 * about someone who looks stuck. Missions show their best outcome across
 * every attempt — a profile is a record of what someone achieved, not a log
 * of how many tries it took — and expand to the phases behind that outcome,
 * because "in progress" tells you a student is somewhere in the middle
 * without telling you where.
 */
function MissionRow({ mission }: { mission: StudentMissionProgress }) {
  const [open, setOpen] = useState(false)
  const hasPhases = mission.phases.length > 0
  const donePhases = mission.phases.filter((p) => p.done).length

  return (
    <div className="rounded-xl ring-1 ring-border overflow-hidden">
      <button
        onClick={() => hasPhases && setOpen((v) => !v)}
        className={`w-full flex items-center gap-3 px-3.5 py-2.5 text-left transition-colors ${
          hasPhases ? "hover:bg-muted/40 cursor-pointer" : "cursor-default"}`}
      >
        <span className="flex-1 min-w-0 text-sm font-medium truncate">{mission.title}</span>
        <span className={`text-xs font-medium shrink-0 ${
          mission.status === "passed" ? "text-emerald-500"
            : mission.status === "failed" ? "text-destructive"
              : "text-muted-foreground"}`}>
          {mission.status.replace(/_/g, " ")}
        </span>
        {mission.score !== null && (
          <span className="text-xs font-mono text-muted-foreground shrink-0">{Math.round(mission.score)}%</span>
        )}
        {hasPhases && (
          <span className="text-xs font-mono text-muted-foreground shrink-0">
            {donePhases}/{mission.phases.length}
          </span>
        )}
        {hasPhases && (
          <ChevronDown className={`size-4 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
        )}
      </button>
      {open && (
        <div className="px-3.5 pb-3 pt-1 border-t border-border/60 flex flex-wrap gap-1.5">
          {mission.phases.map((phase) => (
            <span
              key={phase.key}
              className={`text-[11px] px-2 py-0.5 rounded-full ring-1 ${
                phase.done
                  ? "ring-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                  : "ring-border text-muted-foreground"}`}
            >
              {phase.label}
            </span>
          ))}
          {mission.attempts > 1 && (
            <span className="text-[11px] text-muted-foreground self-center ml-1">
              {mission.attempts} attempts
            </span>
          )}
        </div>
      )}
    </div>
  )
}

function DetailPair({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <p className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium mb-0.5">{label}</p>
      {value ? <p className="text-sm">{value}</p> : <p className="text-sm text-muted-foreground italic">Not set</p>}
    </div>
  )
}

export function StudentCard({ stats }: { stats: StudentCardStats }) {
  const { courses, missions } = stats
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle>Learning</CardTitle></CardHeader>
      <CardContent className="flex flex-col gap-5">
        <div className="grid grid-cols-3 gap-3">
          <StatTile label="Points" value={stats.points_balance} />
          <StatTile label="Courses completed" value={`${stats.courses_completed}/${courses.length}`} />
          <StatTile label="Missions passed" value={`${stats.missions_passed}/${missions.length}`} />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <DetailPair label="Nickname" value={stats.nickname} />
          <DetailPair label="Invite code used" value={stats.invitation_code_used} />
          <DetailPair label="School" value={stats.school_name} />
          <DetailPair label="Grade" value={stats.grade} />
        </div>

        {courses.length > 0 && (
          <div className="flex flex-col gap-2.5">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Courses</p>
            {courses.map((course) => (
              <div key={course.course_id} className="flex flex-col gap-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-sm truncate">{course.title}</span>
                  <span className="text-xs shrink-0">
                    <span className={course.completed ? "text-emerald-500" : "text-muted-foreground"}>
                      {course.completed ? "completed" : "in progress"}
                    </span>
                    <span className="font-mono text-muted-foreground">
                      {" "}&middot; {course.modules_completed}/{course.modules_total}
                    </span>
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${course.completed ? "bg-emerald-500" : "bg-primary"}`}
                    style={{ width: `${course.percent}%` }}
                  />
                </div>
                {course.enrolled_at && (
                  <p className="text-[10px] text-muted-foreground">
                    Started {new Date(course.enrolled_at).toLocaleDateString()}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}

        {missions.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Missions</p>
            {missions.map((mission) => <MissionRow key={mission.mission_id} mission={mission} />)}
          </div>
        )}

        {courses.length === 0 && missions.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Nothing started yet — enrolled courses and mission attempts show up here.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
