import { useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, PlayCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { fetchCatalog, fetchMyCourses, fetchUpcomingPrograms } from "@/api/lms";
import { CourseProgress } from "./CourseProgress";
import { UpcomingProgramRow } from "./UpcomingProgramRow";

/** /learn — the new landing/home base (design 1c). Resume band sits above
 * discovery so a returning student never hunts for where they left off. */
export default function LearnLanding() {
  const navigate = useNavigate();

  const { data: dashboard } = useQuery({ queryKey: ["lms-my-courses"], queryFn: fetchMyCourses });
  const { data: catalog } = useQuery({ queryKey: ["lms-catalog"], queryFn: () => fetchCatalog() });
  const { data: programs } = useQuery({ queryKey: ["lms-upcoming-programs"], queryFn: fetchUpcomingPrograms });

  const resume = dashboard?.resume;
  const featured = catalog?.slice(0, 3) ?? [];
  const upcoming = programs?.slice(0, 3) ?? [];

  return (
    <div className="mx-auto max-w-[1320px] px-5 sm:px-8 lg:px-14 py-10 sm:py-14 flex flex-col gap-12 sm:gap-14">
      <div className="grid lg:grid-cols-[1.05fr_.95fr] gap-10 items-center">
        <div className="flex flex-col gap-5">
          <h1 className="font-display text-4xl sm:text-5xl font-extrabold tracking-tight leading-[1.05]">
            Build satellites.<br />Start with one module.
          </h1>
          <p className="text-base leading-relaxed text-muted-foreground max-w-lg">
            Short videos, quick checks, and hands-on missions. Learn at your own pace — we'll keep your place.
          </p>
          <div className="flex flex-wrap gap-3 pt-1">
            <Button size="xl" onClick={() => void navigate({ to: "/learn/my-courses" })}>
              Continue learning <ArrowRight className="size-4" />
            </Button>
            <Button size="xl" variant="outline" onClick={() => void navigate({ to: "/learn/catalog" })}>
              Browse the catalog
            </Button>
          </div>
          {catalog && (
            <div className="flex gap-8 pt-2">
              <div>
                <div className="font-display text-2xl font-bold">{catalog.length}</div>
                <div className="text-xs text-muted-foreground mt-0.5">courses live</div>
              </div>
            </div>
          )}
        </div>
        <div className="h-64 sm:h-96 rounded-2xl ring-1 ring-border bg-[repeating-linear-gradient(135deg,hsl(var(--primary)/0.10)_0px,hsl(var(--primary)/0.10)_9px,hsl(var(--primary)/0.03)_9px,hsl(var(--primary)/0.03)_18px)] flex flex-col items-center justify-center gap-2 text-muted-foreground">
          <PlayCircle className="size-8" />
          <span className="text-xs font-mono">students with SatKit</span>
        </div>
      </div>

      {resume && (
        <Card className="flex-row items-center gap-6 p-5 sm:p-6">
          <div className="w-24 h-16 sm:w-28 sm:h-[70px] rounded-xl shrink-0 bg-[repeating-linear-gradient(135deg,hsl(var(--primary)/0.12)_0px,hsl(var(--primary)/0.12)_8px,hsl(var(--primary)/0.03)_8px,hsl(var(--primary)/0.03)_16px)] flex items-center justify-center">
            <PlayCircle className="size-6 text-primary" />
          </div>
          <div className="flex-1 min-w-0 flex flex-col gap-1.5">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-primary">Pick up where you left off</div>
            <div className="font-display text-lg font-semibold truncate">{resume.module_title}</div>
            <CourseProgress value={resume.mandatory_total ? Math.round(100 * resume.mandatory_completed / resume.mandatory_total) : 0} className="max-w-sm" />
          </div>
          <Button
            size="xl"
            className="shrink-0"
            onClick={() => void navigate({ to: `/learn/courses/${resume.course_id}/learn`, search: { item: resume.next_item_id ?? undefined } as never })}
          >
            Resume
          </Button>
        </Card>
      )}

      {featured.length > 0 && (
        <div className="flex flex-col gap-5">
          <div className="flex items-end justify-between">
            <div>
              <h2 className="font-display text-2xl font-bold tracking-tight">Start something new</h2>
              <p className="text-sm text-muted-foreground mt-1">No prerequisites on the first few.</p>
            </div>
            <button
              onClick={() => void navigate({ to: "/learn/catalog" })}
              className="flex items-center gap-1.5 text-sm font-medium text-primary hover:opacity-80 cursor-pointer"
            >
              See all <ArrowRight className="size-3.5" />
            </button>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {featured.map((course) => (
              <Card
                key={course.id}
                className="cursor-pointer hover:ring-primary/30 transition-shadow p-0"
                onClick={() => void navigate({ to: `/learn/courses/${course.id}` })}
              >
                <div
                  className="h-[130px] rounded-t-2xl bg-[repeating-linear-gradient(135deg,hsl(var(--primary)/0.11)_0px,hsl(var(--primary)/0.11)_8px,hsl(var(--primary)/0.03)_8px,hsl(var(--primary)/0.03)_16px)]"
                  style={course.image_url ? { backgroundImage: `url(${course.image_url})`, backgroundSize: "cover", backgroundPosition: "center" } : undefined}
                />
                <div className="p-4 flex flex-col gap-2">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    {course.kind === "mission" ? "Mission" : "Course"}
                    {course.level && <span className="capitalize">· {course.level}</span>}
                  </div>
                  <div className="font-display text-base font-semibold leading-snug">{course.title}</div>
                  {course.description && (
                    <div className="text-sm text-muted-foreground line-clamp-2">{course.description}</div>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      <Card className="p-5 sm:p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display text-lg font-bold">Upcoming programs</h3>
          <button
            onClick={() => void navigate({ to: "/learn/catalog", search: { tab: "programs" } as never })}
            className="text-sm font-medium text-primary hover:opacity-80 cursor-pointer"
          >
            View all
          </button>
        </div>
        {upcoming.length === 0 ? (
          <p className="text-sm text-muted-foreground">No public programs open right now.</p>
        ) : (
          <div className="flex flex-col">
            {upcoming.map((p) => <UpcomingProgramRow key={p.cohort_id} program={p} />)}
          </div>
        )}
      </Card>
    </div>
  );
}
