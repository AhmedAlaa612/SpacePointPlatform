import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "@tanstack/react-router";
import { CheckCircle2, Lock, PlayCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { enrollInCourse, fetchCourse, type CourseDetail } from "@/api/lms";
import { CourseProgress } from "./CourseProgress";

/** Course landing (design 1g) — module list with lock states + enrollment
 * (D8: browsing needs only login, playing needs an active enrollment). */
export default function LearnCourse() {
  // strict from-string lookup can fail to resolve on a fresh/hard page load
  // (see LMS_EXECUTION_PLAN.md §DISCOVERIES, LM1-13) — strict: false reads
  // whatever route actually matched instead of re-deriving it.
  const { courseId } = useParams({ strict: false }) as { courseId: string };
  const navigate = useNavigate();
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [error, setError] = useState("");
  const [enrolling, setEnrolling] = useState(false);

  const load = useCallback(() => {
    fetchCourse(courseId)
      .then(setCourse)
      .catch(() => setError("Couldn't load this course."));
  }, [courseId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleEnroll = async () => {
    setEnrolling(true);
    try {
      await enrollInCourse(courseId);
      load();
    } catch {
      setError("Couldn't enroll right now. Please try again.");
    } finally {
      setEnrolling(false);
    }
  };

  if (error) return <div className="mx-auto max-w-[900px] px-5 py-10"><p className="text-sm text-destructive">{error}</p></div>;
  if (!course) return <div className="mx-auto max-w-[900px] px-5 py-10"><p className="text-sm text-muted-foreground">Loading...</p></div>;

  const modulesDone = course.modules.filter((m) => m.mandatory_total > 0 && m.mandatory_completed >= m.mandatory_total).length;
  const pct = course.modules.length ? Math.round(100 * modulesDone / course.modules.length) : 0;

  return (
    <div className="mx-auto max-w-[980px] px-5 sm:px-8 py-8 sm:py-10 flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight">{course.title}</h1>
        {course.description && <p className="text-sm text-muted-foreground mt-2 leading-relaxed">{course.description}</p>}
      </div>

      {!course.enrolled ? (
        <Button size="xl" className="w-fit" onClick={() => void handleEnroll()} disabled={enrolling}>
          {enrolling ? "Enrolling..." : "Enroll"}
        </Button>
      ) : (
        <>
          <Card className="flex-row items-center gap-5 p-5">
            <div className="flex-1">
              {course.completed ? (
                <div className="flex items-center gap-2 text-sm font-medium text-emerald-500">
                  <CheckCircle2 className="size-4" /> Course completed
                </div>
              ) : (
                <CourseProgress value={pct} label={`${modulesDone} of ${course.modules.length} modules`} />
              )}
            </div>
            <Button size="xl" onClick={() => void navigate({ to: `/learn/courses/${course.id}/learn` })}>
              {course.completed ? "Review" : modulesDone > 0 ? "Resume" : "Start"}
            </Button>
          </Card>

          <div className="flex flex-col gap-2">
            {course.modules.map((module) => {
              const done = module.mandatory_total > 0 && module.mandatory_completed >= module.mandatory_total;
              return (
                <Card
                  key={module.module_id}
                  className={`flex-row items-center gap-3 p-4 ${module.locked ? "opacity-60" : "cursor-pointer hover:ring-primary/30 transition-shadow"}`}
                  onClick={() => {
                    if (!module.locked) void navigate({ to: `/learn/courses/${course.id}/learn` });
                  }}
                >
                  <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                    {module.locked ? (
                      <Lock className="size-4 text-muted-foreground" />
                    ) : done ? (
                      <CheckCircle2 className="size-4 text-primary" />
                    ) : (
                      <PlayCircle className="size-4 text-primary" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">{module.title ?? `Module ${module.position}`}</div>
                    <div className="text-xs text-muted-foreground">
                      {module.mandatory_completed}/{module.mandatory_total} complete
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
