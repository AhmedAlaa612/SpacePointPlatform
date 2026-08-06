import { useQuery } from "@tanstack/react-query";
import { Award, BookMarked, GraduationCap, PlayCircle } from "lucide-react";
import { useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatCard, EmptyState } from "@/components/ui/primitives";
import { useAuth } from "@/context/AuthContext";
import { fetchMyCourses, type DashboardCourse } from "@/api/lms";
import { CourseProgress } from "./CourseProgress";

/** /learn/my-courses (design 1f) — the logged-in home base. Stat row is
 * StatCard verbatim; two Phase-2 slots (streak, XP — LM2-1) are shown as
 * inert placeholders so the row's shape doesn't change when they ship. */
export default function LearnMyCourses() {
  const { currentUser } = useAuth();
  const { data, isLoading } = useQuery({ queryKey: ["lms-my-courses"], queryFn: fetchMyCourses });

  const firstName = currentUser?.full_name?.split(" ")[0] ?? "there";

  return (
    <div className="mx-auto max-w-[1320px] px-5 sm:px-8 lg:px-14 py-8 sm:py-10 flex flex-col gap-8">
      <div>
        <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight">Welcome back, {firstName}</h1>
        <p className="text-sm text-muted-foreground mt-1.5">Here's where every enrolled course stands.</p>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}

      {data && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard icon={<BookMarked className="size-5" />} label="In progress" value={data.stats.in_progress} sub={`of ${data.stats.total_enrolled} enrolled`} />
            <StatCard icon={<GraduationCap className="size-5" />} label="Modules done" value={data.stats.modules_done} />
            <div className="rounded-2xl bg-card/40 ring-1 ring-border/60 p-4 sm:p-5 flex items-center gap-4 opacity-50" title="Coming in Phase 2 (LM2-1)">
              <div className="w-11 h-11 rounded-xl bg-muted flex items-center justify-center shrink-0">
                <Award className="size-5 text-muted-foreground" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Day streak</p>
                <p className="font-display text-2xl font-bold leading-tight">—</p>
                <p className="text-xs text-muted-foreground mt-0.5">Phase 2</p>
              </div>
            </div>
            <div className="rounded-2xl bg-card/40 ring-1 ring-border/60 p-4 sm:p-5 flex items-center gap-4 opacity-50" title="Coming in Phase 2 (LM2-2)">
              <div className="w-11 h-11 rounded-xl bg-muted flex items-center justify-center shrink-0">
                <Award className="size-5 text-muted-foreground" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">XP earned</p>
                <p className="font-display text-2xl font-bold leading-tight">—</p>
                <p className="text-xs text-muted-foreground mt-0.5">Phase 2</p>
              </div>
            </div>
          </div>

          {data.courses.length === 0 ? (
            <EmptyState title="No courses yet" hint="Browse the catalog and enrol in something." />
          ) : (
            <div className="flex flex-col gap-3">
              {data.courses.map((c) => <EnrolledCourseRow key={c.course_id} course={c} />)}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function EnrolledCourseRow({ course }: { course: DashboardCourse }) {
  const navigate = useNavigate();
  const cta = course.status === "completed" ? "Certificate" : course.status === "not_started" ? "Start" : "Resume";
  return (
    <Card className="flex-row items-center gap-5 p-4 sm:p-5">
      <div className="w-11 h-11 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
        <PlayCircle className="size-5" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-medium truncate">{course.title}</div>
        <div className="text-xs text-muted-foreground mt-0.5 mb-2">
          {course.status === "completed"
            ? `${course.modules_total} of ${course.modules_total} modules · completed`
            : course.status === "not_started"
            ? `${course.modules_total} modules · not started`
            : `${course.modules_done} of ${course.modules_total} modules`}
        </div>
        <CourseProgress value={course.pct} className="max-w-sm" />
      </div>
      <Button
        size="xl"
        variant={course.status === "completed" ? "outline" : "default"}
        disabled={course.status === "completed"}
        onClick={() => void navigate({ to: cta === "Start" || cta === "Resume" ? `/learn/courses/${course.course_id}/learn` : `/learn/courses/${course.course_id}` })}
        className="shrink-0"
      >
        {cta}
      </Button>
    </Card>
  );
}
