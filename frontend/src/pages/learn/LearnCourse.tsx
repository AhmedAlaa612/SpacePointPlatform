import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams, Link } from "@tanstack/react-router";
import { CheckCircle2, ChevronRight, Lock, PlayCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { enrollInCourse, fetchCourse, type CourseDetail } from "@/api/lms";
import { CourseProgress } from "./CourseProgress";

/** Course landing (design 1g) — orient & enrol only; in-progress state lives
 * on /learn/my-courses, the player is /learn/courses/$id/learn. Browsing
 * needs only login (D8); playing needs an active enrollment. */
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
  const itemCta = course.completed ? "Review" : modulesDone > 0 ? "Resume" : "Start";

  return (
    <div className="mx-auto max-w-[1180px] px-5 sm:px-8 lg:px-10 py-6 sm:py-8 flex flex-col gap-6">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Link to="/learn/catalog" className="text-primary hover:opacity-80">Catalog</Link>
        {course.track && (
          <>
            <ChevronRight className="size-3" />
            <span>{course.track}</span>
          </>
        )}
        <ChevronRight className="size-3" />
        <span className="text-foreground">{course.title}</span>
      </div>

      <div className="grid lg:grid-cols-[1fr_360px] gap-8 items-start">
        <div className="flex flex-col gap-6 min-w-0">
          <div className="flex flex-col gap-3">
            {course.level && (
              <span className="w-fit text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded-md bg-primary/10 text-primary capitalize">
                {course.level}
              </span>
            )}
            <h1 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight leading-tight">{course.title}</h1>
            {course.description && <p className="text-base leading-relaxed text-muted-foreground max-w-xl">{course.description}</p>}
            <div className="flex items-center gap-6 pt-1">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <PlayCircle className="size-4 text-primary" /> {course.modules.length} modules
              </div>
            </div>
          </div>

          {course.outcomes.length > 0 && (
            <div className="flex flex-col gap-3">
              <h2 className="font-display text-xl font-bold tracking-tight">What you'll be able to do</h2>
              <div className="grid sm:grid-cols-2 gap-x-6 gap-y-2.5">
                {course.outcomes.map((o, i) => (
                  <div key={i} className="flex items-start gap-2.5">
                    <div className="w-[18px] h-[18px] rounded-md bg-primary/15 text-primary flex items-center justify-center shrink-0 mt-0.5">
                      <CheckCircle2 className="size-3" />
                    </div>
                    <span className="text-sm text-muted-foreground leading-snug">{o}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex flex-col gap-3">
            <div className="flex items-end justify-between">
              <h2 className="font-display text-xl font-bold tracking-tight">Course contents</h2>
              <span className="text-xs text-muted-foreground">{course.modules.length} modules</span>
            </div>
            <Card className="p-0 divide-y divide-border">
              {course.modules.map((module) => {
                const done = module.mandatory_total > 0 && module.mandatory_completed >= module.mandatory_total;
                return (
                  <div
                    key={module.module_id}
                    onClick={() => {
                      if (course.enrolled && !module.locked) void navigate({ to: `/learn/courses/${course.id}/learn` });
                    }}
                    className={`flex items-center gap-3.5 p-4 ${
                      course.enrolled && !module.locked ? "cursor-pointer hover:bg-foreground/5 transition-colors" : ""
                    } ${module.locked ? "opacity-60" : ""}`}
                  >
                    <div className="w-7 h-7 rounded-lg bg-muted flex items-center justify-center shrink-0 text-xs font-semibold text-muted-foreground">
                      {module.locked ? <Lock className="size-3.5" /> : done ? <CheckCircle2 className="size-4 text-primary" /> : module.position}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium">{module.title ?? `Module ${module.position}`}</div>
                      <div className="text-xs text-muted-foreground mt-0.5">
                        {module.mandatory_completed}/{module.mandatory_total} complete
                      </div>
                    </div>
                  </div>
                );
              })}
            </Card>
          </div>
        </div>

        <div className="flex flex-col gap-4 lg:sticky lg:top-24">
          <Card className="p-0">
            <div className="h-[160px] rounded-t-2xl overflow-hidden bg-muted flex items-center justify-center">
              {course.image_url ? (
                <img src={course.image_url} alt="" className="w-full h-full object-cover" />
              ) : (
                <PlayCircle className="size-8 text-muted-foreground" />
              )}
            </div>
            <div className="p-5 flex flex-col gap-3">
              {course.enrolled ? (
                <>
                  {course.completed ? (
                    <div className="flex items-center gap-2 text-sm font-medium text-emerald-500">
                      <CheckCircle2 className="size-4" /> Completed
                    </div>
                  ) : (
                    <CourseProgress value={pct} label={`${modulesDone} of ${course.modules.length} modules`} />
                  )}
                  <Button size="xl" className="w-full" onClick={() => void navigate({ to: `/learn/courses/${course.id}/learn` })}>
                    {itemCta}
                  </Button>
                </>
              ) : (
                <Button size="xl" className="w-full" onClick={() => void handleEnroll()} disabled={enrolling}>
                  {enrolling ? "Enrolling..." : "Enroll"}
                </Button>
              )}
              <div className="h-px bg-border" />
              <div className="flex items-center gap-2.5 text-sm text-muted-foreground">
                <PlayCircle className="size-4 shrink-0" /> Learn at your own pace
              </div>
              <div className="flex items-center gap-2.5 text-sm text-muted-foreground">
                <CheckCircle2 className="size-4 shrink-0" /> Quizzes &amp; flashcards included
              </div>
            </div>
          </Card>

          {course.instructor_name && (
            <Card className="p-5 gap-3 items-start">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Your instructor</div>
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-primary/10 overflow-hidden shrink-0 flex items-center justify-center text-primary font-display font-bold text-sm">
                  {course.instructor_photo_url ? (
                    <img src={course.instructor_photo_url} alt="" className="w-full h-full object-cover" />
                  ) : (
                    course.instructor_name.split(" ").map((w) => w[0]).slice(0, 2).join("")
                  )}
                </div>
                <div className="min-w-0">
                  <div className="font-display text-base font-semibold truncate">{course.instructor_name}</div>
                  {course.instructor_title && <div className="text-xs text-primary mt-0.5 truncate">{course.instructor_title}</div>}
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
