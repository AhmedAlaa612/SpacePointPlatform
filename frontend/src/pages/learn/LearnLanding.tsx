import { useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Clock, List } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import {
  fetchCatalog,
  fetchLearningPaths,
  fetchMyChecklists,
  fetchMyCourses,
  fetchPublicCatalog,
  fetchPublicPaths,
  fetchUpcomingPrograms,
} from "@/api/lms";
import { fetchMyTeams } from "@/api/missions";
import { SatkitAssembly } from "@/components/satkit/SatkitAssembly";
import { CubeSatButton } from "@/components/ui/CubeSatButton";
import { UpcomingProgramRow } from "./UpcomingProgramRow";

function formatPrice(cents: number, currency: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
  }).format(cents / 100);
}

function getCourseModules(course: { modules_total?: number; level?: string | null }): number {
  if (course.modules_total && course.modules_total > 0) return course.modules_total;
  if (course.level === "advanced") return 8;
  if (course.level === "intermediate") return 6;
  return 5;
}

function getCourseDuration(modules: number): string {
  if (modules >= 8) return "4h 20m";
  if (modules >= 6) return "3h 45m";
  if (modules >= 4) return "2h 30m";
  return "1h 45m";
}

export default function LearnLanding() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAuthed = !!user;

  const { data: dashboard } = useQuery({
    queryKey: ["lms-my-courses"],
    queryFn: fetchMyCourses,
    enabled: isAuthed,
  });
  const { data: catalog } = useQuery({
    queryKey: ["lms-catalog"],
    queryFn: () => fetchCatalog(),
    enabled: isAuthed,
  });
  const { data: publicCatalog } = useQuery({
    queryKey: ["public-catalog"],
    queryFn: () => fetchPublicCatalog(),
    enabled: !isAuthed,
  });
  const { data: paths } = useQuery({
    queryKey: ["lms-learning-paths"],
    queryFn: fetchLearningPaths,
    enabled: isAuthed,
  });
  const { data: publicPaths } = useQuery({
    queryKey: ["public-learning-paths"],
    queryFn: fetchPublicPaths,
    enabled: !isAuthed,
  });
  const { data: programs } = useQuery({
    queryKey: ["lms-upcoming-programs"],
    queryFn: fetchUpcomingPrograms,
  });
  const { data: myTeams } = useQuery({
    queryKey: ["my-teams"],
    queryFn: fetchMyTeams,
    enabled: isAuthed,
  });
  const { data: myChecklists } = useQuery({
    queryKey: ["lms-my-checklists"],
    queryFn: fetchMyChecklists,
    enabled: isAuthed,
  });

  const resume = dashboard?.resume;
  const cohortTeams = (myTeams ?? []).filter((t) => t.cohort_id != null);
  const latestChecklist = myChecklists?.[0] ?? null;
  const latestTeam = latestChecklist
    ? (cohortTeams.find((t) => t.cohort_id === latestChecklist.cohort_id) ?? null)
    : (cohortTeams[0] ?? null);

  const fullCatalog = catalog ?? publicCatalog ?? [];
  const catalogMap = new Map(fullCatalog.map((c) => [c.id, c]));

  const myPaths = paths?.filter((p) => p.enrolled) ?? [];
  const visiblePaths = isAuthed ? paths : publicPaths;
  const otherPaths = (visiblePaths ?? []).filter((p) => !p.enrolled);
  const displayedPaths = (myPaths.length > 0 ? myPaths : otherPaths).slice(0, 4);

  const myCourses = dashboard?.courses ?? [];
  const visibleCatalog = isAuthed ? catalog : publicCatalog;
  const otherCourses = (visibleCatalog ?? []).filter((c) => !c.enrolled);
  const displayedCourses = (myCourses.length > 0 ? myCourses : otherCourses).slice(0, 6);

  const upcoming = programs?.slice(0, 3) ?? [];

  return (
    <div className="mx-auto max-w-[1240px] px-6 sm:px-10 lg:px-12 py-10 sm:py-16 flex flex-col gap-16 sm:gap-24">
      {/* Hero */}
      <section className="grid lg:grid-cols-[1.05fr_.95fr] gap-10 items-center">
        <div className="flex flex-col">
          <h1 className="font-display text-[42px] sm:text-[48px] font-extrabold leading-[48px] tracking-[-1.2px] text-foreground">
            Build satellites.
            <br />
            Start with one module.
          </h1>

          {/* Generous intentional gap between heading text and CTA buttons */}
          <div className="h-24 sm:h-32 lg:h-36" aria-hidden="true" />

          <div className="flex flex-wrap items-center gap-x-10 sm:gap-x-12 gap-y-6">
            {isAuthed ? (
              <>
                <CubeSatButton
                  variant="primary"
                  onClick={() => void navigate({ to: "/learn/my-courses" })}
                >
                  Continue learning <ArrowRight className="size-4" />
                </CubeSatButton>
                <CubeSatButton
                  variant="secondary"
                  onClick={() => void navigate({ to: "/learn/catalog" })}
                >
                  Explore courses
                </CubeSatButton>
              </>
            ) : (
              <>
                <CubeSatButton
                  variant="primary"
                  onClick={() => void navigate({ to: "/learn/catalog" })}
                >
                  Explore courses <ArrowRight className="size-4" />
                </CubeSatButton>
                <CubeSatButton
                  variant="secondary"
                  onClick={() => void navigate({ to: "/learn/signup" })}
                >
                  Get Started
                </CubeSatButton>
              </>
            )}
          </div>
        </div>

        <div className="h-80 sm:h-[32rem]">
          <SatkitAssembly height="100%" />
        </div>
      </section>

      {/* Resume Card (In-progress) */}
      {resume && (
        <article
          onClick={() =>
            void navigate({
              to: `/learn/courses/${resume.course_id}/learn`,
              search: { item: resume.next_item_id ?? undefined } as never,
            })
          }
          className="lms-card p-6 sm:p-7 flex flex-col sm:flex-row sm:items-center justify-between gap-6 cursor-pointer group"
        >
          <div className="flex-1 min-w-0 flex flex-col gap-2">
            <span className="text-xs font-semibold text-muted-foreground">Pick up where you left off</span>
            <h2 className="font-display text-xl sm:text-2xl font-extrabold text-foreground tracking-tight truncate group-hover:text-lms-cta dark:group-hover:text-lms-accent transition-colors">
              {resume.module_title}
            </h2>
            <div className="flex items-center gap-4 max-w-md mt-1">
              <div className="flex-1 h-1.5 rounded-full bg-foreground/10 dark:bg-white/10 overflow-hidden">
                <div
                  className="h-full bg-lms-cta dark:bg-lms-accent rounded-full transition-all duration-300"
                  style={{
                    width: `${
                      resume.mandatory_total
                        ? Math.round((100 * resume.mandatory_completed) / resume.mandatory_total)
                        : 0
                    }%`,
                  }}
                />
              </div>
              <span className="font-display font-bold text-xs text-lms-cta dark:text-lms-accent whitespace-nowrap">
                {resume.mandatory_total
                  ? Math.round((100 * resume.mandatory_completed) / resume.mandatory_total)
                  : 0}
                %
              </span>
            </div>
          </div>
          <button
            className="lms-btn-primary h-11 px-6 text-xs sm:text-sm inline-flex items-center justify-center gap-2 cursor-pointer shrink-0"
            onClick={(e) => {
              e.stopPropagation();
              void navigate({
                to: `/learn/courses/${resume.course_id}/learn`,
                search: { item: resume.next_item_id ?? undefined } as never,
              });
            }}
          >
            Resume <ArrowRight className="size-4" />
          </button>
        </article>
      )}

      {/* Team Card */}
      {latestTeam && (
        <article className="lms-card p-6 sm:p-7 flex flex-col sm:flex-row sm:items-center justify-between gap-6">
          <div className="flex-1 min-w-0 flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-muted-foreground">
              My Team{latestChecklist?.cohort_name ? ` · ${latestChecklist.cohort_name}` : ""}
            </span>
            <h2 className="font-display text-xl sm:text-2xl font-extrabold text-foreground tracking-tight truncate">
              {latestTeam.name}
            </h2>
            <p className="text-xs text-muted-foreground truncate">{latestTeam.member_names.join(", ")}</p>
          </div>
          {latestChecklist ? (
            <button
              onClick={() =>
                void navigate({ to: `/learn/checklists/${latestChecklist.assignment_id}` })
              }
              className="lms-btn-secondary h-11 px-6 text-xs sm:text-sm inline-flex items-center justify-center gap-2 cursor-pointer shrink-0"
            >
              Open checklist <ArrowRight className="size-4" />
            </button>
          ) : (
            <span className="text-xs text-muted-foreground shrink-0">No checklist yet</span>
          )}
        </article>
      )}

      {/* Learning Paths */}
      {displayedPaths.length > 0 && (
        <section className="flex flex-col">
          <div className="flex items-end justify-between gap-4 mb-6">
            <h2 className="font-display text-2xl sm:text-[28px] font-extrabold text-foreground tracking-[-0.8px]">
              Learning paths
            </h2>
            <button
              onClick={() =>
                void navigate({ to: "/learn/catalog", search: { tab: "paths" } as never })
              }
              className="text-xs sm:text-sm font-semibold text-muted-foreground hover:text-lms-cta dark:hover:text-lms-accent inline-flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              View all paths <ArrowRight className="size-3.5" />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {displayedPaths.map((path) => (
              <article
                key={path.id}
                onClick={() => void navigate({ to: `/learn/paths/${path.id}` })}
                className="lms-card overflow-hidden flex flex-col justify-between cursor-pointer group transition-all"
              >
                {/* Media banner */}
                <div className="h-44 sm:h-48 w-full border-b border-lms-accent-border relative overflow-hidden bg-foreground/5 flex items-center justify-center">
                  {path.image_url ? (
                    <img
                      src={path.image_url}
                      alt={path.title}
                      className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                    />
                  ) : (
                    <div className="relative w-full h-full flex items-center justify-center overflow-hidden">
                      <div className="w-24 h-10 border border-lms-accent-border rounded-full rotate-[-18deg] relative">
                        <div className="absolute inset-2 border border-lms-accent-border rounded-full" />
                      </div>
                      <span className="absolute bottom-3 text-[9px] font-bold tracking-widest text-lms-cta dark:text-lms-accent/60 uppercase">
                        CURATED TRACK
                      </span>
                    </div>
                  )}
                </div>

                <div className="p-6 sm:p-7 flex flex-col flex-1 justify-between gap-6">
                  <div className="flex flex-col gap-3">
                    <h3 className="font-display font-extrabold text-xl sm:text-2xl text-foreground tracking-tight group-hover:text-lms-cta dark:group-hover:text-lms-accent transition-colors">
                      {path.title}
                    </h3>
                    {path.description && (
                      <p className="text-xs sm:text-sm text-foreground/75 dark:text-white/72 line-clamp-2 leading-relaxed">
                        {path.description}
                      </p>
                    )}
                    <div className="flex items-center gap-2 text-xs text-muted-foreground pt-2 flex-wrap">
                      <span>
                        {path.course_count} course{path.course_count === 1 ? "" : "s"}
                      </span>
                      {path.mission_count > 0 && (
                        <span>
                          · {path.mission_count} mission{path.mission_count === 1 ? "" : "s"}
                        </span>
                      )}
                      {path.access_mode === "paid" && path.price_cents != null ? (
                        <span>· {formatPrice(path.price_cents, path.currency)}</span>
                      ) : (
                        <span>· Certificate included</span>
                      )}
                    </div>
                  </div>

                  {path.enrolled ? (
                    <div className="flex flex-col gap-2 pt-4 border-t border-border dark:border-white/10">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground font-medium">Path progress</span>
                        <strong className="font-display font-bold text-lms-cta dark:text-lms-accent">
                          {path.pct}%
                        </strong>
                      </div>
                      <div className="h-1.5 rounded-full bg-foreground/10 dark:bg-white/10 overflow-hidden">
                        <div
                          className="h-full bg-lms-cta dark:bg-lms-accent rounded-full transition-all duration-300"
                          style={{ width: `${path.pct}%` }}
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="pt-4 border-t border-border dark:border-white/10">
                      <button
                        className="lms-btn-secondary w-full h-11 text-xs sm:text-sm inline-flex items-center justify-center gap-2"
                        onClick={(e) => {
                          e.stopPropagation();
                          void navigate({ to: `/learn/paths/${path.id}` });
                        }}
                      >
                        Explore path <ArrowRight className="size-4" />
                      </button>
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {/* Courses */}
      {displayedCourses.length > 0 && (
        <section className="flex flex-col">
          <div className="flex items-end justify-between gap-4 mb-6">
            <h2 className="font-display text-2xl sm:text-[28px] font-extrabold text-foreground tracking-[-0.8px]">
              Courses
            </h2>
            <button
              onClick={() =>
                void navigate({ to: "/learn/catalog", search: { tab: "courses" } as never })
              }
              className="text-xs sm:text-sm font-semibold text-muted-foreground hover:text-lms-cta dark:hover:text-lms-accent inline-flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              View all courses <ArrowRight className="size-3.5" />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {displayedCourses.map((course) => {
              const courseId = "course_id" in course ? course.course_id : course.id;
              const catalogItem = catalogMap.get(courseId);
              const imageUrl = ("image_url" in course && course.image_url) ? course.image_url : catalogItem?.image_url;
              const description = ("description" in course && course.description) ? course.description : catalogItem?.description;
              const modules = getCourseModules(course);
              const duration = getCourseDuration(modules);
              const hasProgress = "pct" in course && course.pct != null;

              return (
                <article
                  key={courseId}
                  onClick={() => void navigate({ to: `/learn/courses/${courseId}` })}
                  className="lms-card overflow-hidden flex flex-col justify-between cursor-pointer group transition-all"
                >
                  {/* Card Media Header */}
                  <div className="h-44 sm:h-48 w-full border-b border-lms-accent-border relative overflow-hidden bg-foreground/5 flex items-center justify-center">
                    {imageUrl ? (
                      <img
                        src={imageUrl}
                        alt={course.title}
                        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                      />
                    ) : (
                      <div className="relative w-full h-full flex items-center justify-center overflow-hidden">
                        <div className="w-20 h-20 rounded-full border border-lms-accent-border relative flex items-center justify-center">
                          <div className="w-6 h-6 rounded-full border border-lms-accent-border" />
                          <div className="absolute w-32 h-12 rounded-full border border-lms-accent-border rotate-[-25deg]" />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Card Content */}
                  <div className="p-6 flex flex-col flex-1 justify-between gap-5">
                    <div className="flex flex-col gap-2.5">
                      <h3 className="font-display font-extrabold text-lg sm:text-xl text-foreground tracking-tight group-hover:text-lms-cta dark:group-hover:text-lms-accent transition-colors line-clamp-2">
                        {course.title}
                      </h3>
                      {description ? (
                        <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed min-h-[36px]">
                          {description}
                        </p>
                      ) : (
                        <div className="min-h-[36px]" />
                      )}

                      {/* Meta: modules count & duration */}
                      <div className="flex items-center gap-4 text-xs text-muted-foreground pt-1">
                        <span className="flex items-center gap-1.5 font-medium">
                          <List className="size-3.5 text-lms-cta dark:text-lms-accent" />
                          {modules} modules
                        </span>
                        <span className="flex items-center gap-1.5 font-medium">
                          <Clock className="size-3.5 text-lms-cta dark:text-lms-accent" />
                          {duration}
                        </span>
                      </div>
                    </div>

                    {hasProgress ? (
                      <div className="flex flex-col gap-2 pt-4 border-t border-border dark:border-white/10">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-muted-foreground font-medium">Course progress</span>
                          <strong className="font-display font-bold text-lms-cta dark:text-lms-accent">
                            {course.pct}%
                          </strong>
                        </div>
                        <div className="h-1.5 rounded-full bg-foreground/10 dark:bg-white/10 overflow-hidden">
                          <div
                            className="h-full bg-lms-cta dark:bg-lms-accent rounded-full transition-all duration-300"
                            style={{ width: `${course.pct}%` }}
                          />
                        </div>
                      </div>
                    ) : (
                      <div className="pt-4 border-t border-border dark:border-white/10 flex items-center justify-between text-xs font-semibold text-foreground/80 dark:text-white/72 group-hover:text-lms-cta dark:group-hover:text-lms-accent transition-colors">
                        <span>View course</span>
                        <ArrowRight className="size-3.5" />
                      </div>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      )}

      {/* Upcoming Programs */}
      <section className="flex flex-col">
        <div className="flex items-end justify-between gap-4 mb-6">
          <h2 className="font-display text-2xl sm:text-[28px] font-extrabold text-foreground tracking-[-0.8px]">
            Upcoming programs
          </h2>
          <button
            onClick={() =>
              void navigate({ to: "/learn/catalog", search: { tab: "programs" } as never })
            }
            className="text-xs sm:text-sm font-semibold text-muted-foreground hover:text-lms-cta dark:hover:text-lms-accent inline-flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            See all programs <ArrowRight className="size-3.5" />
          </button>
        </div>

        {upcoming.length === 0 ? (
          <div className="lms-card p-6 text-center text-sm text-muted-foreground">
            No public programs open right now.
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {upcoming.map((p) => (
              <UpcomingProgramRow key={p.cohort_id} program={p} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
