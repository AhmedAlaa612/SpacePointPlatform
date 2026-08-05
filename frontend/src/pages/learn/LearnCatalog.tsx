import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { BookOpen, ChevronRight } from "lucide-react";
import { fetchCatalog, type CourseCatalogItem } from "@/api/lms";

/** Published courses (LM1-8). Enrollment status/progress live on the course
 * detail page (LearnCourse) — the catalog is just the "what exists" list. */
export default function LearnCatalog() {
  const navigate = useNavigate();
  const [courses, setCourses] = useState<CourseCatalogItem[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchCatalog()
      .then((data) => !cancelled && setCourses(data))
      .catch(() => !cancelled && setError("Couldn't load the catalog. Pull to refresh."));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Courses</h1>

      {error && <p className="text-sm text-destructive">{error}</p>}
      {!error && courses === null && <p className="text-sm text-muted-foreground">Loading...</p>}
      {courses !== null && courses.length === 0 && (
        <p className="text-sm text-muted-foreground">No courses are published yet.</p>
      )}

      <div className="flex flex-col gap-2">
        {courses?.map((course) => (
          <button
            key={course.id}
            onClick={() => void navigate({ to: `/learn/courses/${course.id}` })}
            className="flex items-center gap-3 p-4 rounded-xl border border-border bg-card text-left hover:border-primary/50 cursor-pointer"
          >
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
              <BookOpen size={18} className="text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-medium truncate">{course.title}</div>
              {course.description && (
                <div className="text-sm text-muted-foreground truncate">{course.description}</div>
              )}
            </div>
            <ChevronRight size={18} className="text-muted-foreground shrink-0" />
          </button>
        ))}
      </div>
    </div>
  );
}
