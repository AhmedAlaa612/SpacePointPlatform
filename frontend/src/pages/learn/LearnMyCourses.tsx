import { useQuery } from "@tanstack/react-query";
import { BookMarked, GraduationCap, PlayCircle } from "lucide-react";
import { useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatCard, EmptyState } from "@/components/ui/primitives";
import { useAuth } from "@/context/AuthContext";
import { fetchMyCourses, type DashboardCourse } from "@/api/lms";
import { CourseProgress } from "./CourseProgress";

/** /learn/my-courses (design 1f) — the logged-in home base. Stat row is
 * StatCard verbatim. Phase 2 stats (streak, XP) are left out entirely for
 * now — Phase 1 is going live for real, and a permanently-inert "—" card
 * reads as broken to an actual student, not "coming soon." Add them back
 * when LM2-1 actually ships. */
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
          <div className="grid grid-cols-2 max-w-md gap-3">
            <StatCard icon={<BookMarked className="size-5" />} label="In progress" value={data.stats.in_progress} sub={`of ${data.stats.total_enrolled} enrolled`} />
            <StatCard icon={<GraduationCap className="size-5" />} label="Modules done" value={data.stats.modules_done} />
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
  const cta = course.status === "completed" ? "Review" : course.status === "not_started" ? "Start" : "Resume";
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
        onClick={() => void navigate({ to: `/learn/courses/${course.course_id}/learn` })}
        className="shrink-0"
      >
        {cta}
      </Button>
    </Card>
  );
}
