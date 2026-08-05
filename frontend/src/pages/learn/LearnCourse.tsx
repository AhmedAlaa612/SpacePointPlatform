import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "@tanstack/react-router";
import { CheckCircle2, ChevronRight, Lock, PlayCircle } from "lucide-react";
import { enrollInCourse, fetchCourse, type CourseDetail } from "@/api/lms";

/** Course outline (LM1-8) — module list with lock states + enrollment
 * (D8: browsing needs only login, playing needs an active enrollment). */
export default function LearnCourse() {
  // strict from-string lookup can fail to resolve on a fresh/hard page load
  // (reproduced on the LM1-13 authoring pages, same router shape) — strict:
  // false reads whatever route actually matched instead of re-deriving it.
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

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!course) return <p className="text-sm text-muted-foreground">Loading...</p>;

  return (
    <div>
      <h1 className="text-xl font-semibold">{course.title}</h1>
      {course.description && <p className="text-sm text-muted-foreground mt-1">{course.description}</p>}

      {!course.enrolled ? (
        <button
          onClick={() => void handleEnroll()}
          disabled={enrolling}
          className="mt-4 h-11 px-6 bg-primary text-primary-foreground rounded-xl font-medium text-sm disabled:opacity-50 cursor-pointer"
        >
          {enrolling ? "Enrolling..." : "Enroll"}
        </button>
      ) : (
        <>
          {course.completed && (
            <div className="mt-4 flex items-center gap-2 text-sm text-primary font-medium">
              <CheckCircle2 size={16} /> Course completed
            </div>
          )}
          <div className="mt-4 flex flex-col gap-2">
            {course.modules.map((module) => (
              <button
                key={module.module_id}
                disabled={module.locked}
                onClick={() => void navigate({ to: `/learn/modules/${module.module_id}` })}
                className="flex items-center gap-3 p-4 rounded-xl border border-border bg-card text-left disabled:opacity-50 disabled:cursor-not-allowed hover:not-disabled:border-primary/50 cursor-pointer"
              >
                <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                  {module.locked ? (
                    <Lock size={16} className="text-muted-foreground" />
                  ) : module.mandatory_completed >= module.mandatory_total && module.mandatory_total > 0 ? (
                    <CheckCircle2 size={16} className="text-primary" />
                  ) : (
                    <PlayCircle size={16} className="text-primary" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">{module.title ?? `Module ${module.position}`}</div>
                  <div className="text-xs text-muted-foreground">
                    {module.mandatory_completed}/{module.mandatory_total} complete
                  </div>
                </div>
                {!module.locked && <ChevronRight size={18} className="text-muted-foreground shrink-0" />}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
