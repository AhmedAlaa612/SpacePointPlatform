import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Clock, List, Search, X } from "lucide-react";
import {
  fetchCatalog,
  fetchLearningPaths,
  fetchMyCourses,
  fetchPublicCatalog,
  fetchPublicPaths,
  fetchUpcomingPrograms,
} from "@/api/lms";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";
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

type CatalogTab = "courses" | "programs" | "paths";
type StatusFilter = "all" | "in_progress" | "available" | "completed";

export default function LearnCatalog() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAuthed = !!user;

  const [tab, setTab] = useState<CatalogTab>(() => {
    const t = new URLSearchParams(window.location.search).get("tab");
    if (t === "programs") return "programs";
    if (t === "paths") return "paths";
    return "courses"; // Main view default
  });

  const [searchInput, setSearchInput] = useState(
    () => new URLSearchParams(window.location.search).get("q") ?? ""
  );
  const [search, setSearch] = useState(searchInput);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  useEffect(() => {
    const id = setTimeout(() => setSearch(searchInput), 300);
    return () => clearTimeout(id);
  }, [searchInput]);

  const { data: catalog, isLoading: catalogLoading } = useQuery({
    queryKey: [isAuthed ? "lms-catalog" : "public-catalog", search],
    queryFn: () =>
      isAuthed ? fetchCatalog(search || undefined) : fetchPublicCatalog(search || undefined),
  });

  const { data: programs, isLoading: programsLoading } = useQuery({
    queryKey: ["lms-upcoming-programs"],
    queryFn: fetchUpcomingPrograms,
  });

  const { data: paths, isLoading: pathsLoading } = useQuery({
    queryKey: [isAuthed ? "lms-learning-paths" : "public-learning-paths"],
    queryFn: () => (isAuthed ? fetchLearningPaths() : fetchPublicPaths()),
  });

  const { data: dashboard } = useQuery({
    queryKey: ["lms-my-courses"],
    queryFn: fetchMyCourses,
    enabled: isAuthed,
  });

  const enrolledMap = useMemo(() => {
    const map = new Map<
      string,
      { status: string; pct: number; modules_done: number; modules_total: number }
    >();
    for (const c of dashboard?.courses ?? []) {
      map.set(c.course_id, c);
    }
    return map;
  }, [dashboard]);

  const handleTabChange = (nextTab: CatalogTab) => {
    setTab(nextTab);
    const sp = new URLSearchParams(window.location.search);
    sp.set("tab", nextTab);
    window.history.replaceState(null, "", `?${sp.toString()}`);
  };

  const filteredCourses = useMemo(() => {
    if (!catalog) return [];
    return catalog.filter((course) => {
      const enrolledInfo = enrolledMap.get(course.id);
      const isEnrolled = course.enrolled || !!enrolledInfo;
      const isCompleted = enrolledInfo?.status === "completed" || enrolledInfo?.pct === 100;

      if (statusFilter === "in_progress") {
        return isEnrolled && !isCompleted;
      }
      if (statusFilter === "available") {
        return !isEnrolled;
      }
      if (statusFilter === "completed") {
        return isEnrolled && isCompleted;
      }
      return true;
    });
  }, [catalog, enrolledMap, statusFilter]);

  return (
    <div className="mx-auto max-w-[1240px] px-6 sm:px-10 lg:px-12 py-10 sm:py-16 flex flex-col gap-10 sm:gap-12">
      {/* Page Heading */}
      <div>
        <h1 className="font-display text-[38px] sm:text-[46px] lg:text-[48px] font-extrabold leading-[48px] tracking-[-1.2px] text-foreground">
          {tab === "courses" && "Build skills for space."}
          {tab === "programs" && "Live programs, real momentum."}
          {tab === "paths" && "Structured learning paths."}
        </h1>
      </div>

      {/* Catalog Switcher Pills */}
      <div className="flex items-center gap-2.5 sm:gap-3 flex-wrap">
        <button
          onClick={() => handleTabChange("courses")}
          className={cn(
            "h-10 px-5 rounded-full text-xs sm:text-sm font-bold transition-all cursor-pointer inline-flex items-center gap-2 select-none",
            tab === "courses"
              ? "bg-lms-cta text-white shadow-none"
              : "bg-transparent text-muted-foreground border border-border/60 dark:border-lms-accent-border hover:text-foreground hover:border-lms-accent"
          )}
        >
          Courses
          {catalog && (
            <span
              className={cn(
                "font-mono text-[11px] px-1.5 py-0.5 rounded-full",
                tab === "courses" ? "bg-white/20 text-white" : "text-muted-foreground"
              )}
            >
              {catalog.length}
            </span>
          )}
        </button>

        <button
          onClick={() => handleTabChange("programs")}
          className={cn(
            "h-10 px-5 rounded-full text-xs sm:text-sm font-bold transition-all cursor-pointer inline-flex items-center gap-2 select-none",
            tab === "programs"
              ? "bg-lms-cta text-white shadow-none"
              : "bg-transparent text-muted-foreground border border-border/60 dark:border-lms-accent-border hover:text-foreground hover:border-lms-accent"
          )}
        >
          Upcoming programs
          {programs && (
            <span
              className={cn(
                "font-mono text-[11px] px-1.5 py-0.5 rounded-full",
                tab === "programs" ? "bg-white/20 text-white" : "text-muted-foreground"
              )}
            >
              {programs.length}
            </span>
          )}
        </button>

        <button
          onClick={() => handleTabChange("paths")}
          className={cn(
            "h-10 px-5 rounded-full text-xs sm:text-sm font-bold transition-all cursor-pointer inline-flex items-center gap-2 select-none",
            tab === "paths"
              ? "bg-lms-cta text-white shadow-none"
              : "bg-transparent text-muted-foreground border border-border/60 dark:border-lms-accent-border hover:text-foreground hover:border-lms-accent"
          )}
        >
          Learning paths
          {paths && (
            <span
              className={cn(
                "font-mono text-[11px] px-1.5 py-0.5 rounded-full",
                tab === "paths" ? "bg-white/20 text-white" : "text-muted-foreground"
              )}
            >
              {paths.length}
            </span>
          )}
        </button>
      </div>

      {/* =========================================================================
          TAB 1: COURSES (MAIN VIEW)
          ========================================================================= */}
      {tab === "courses" && (
        <div className="flex flex-col gap-8">
          {/* Controls: Search & Status Filters */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center gap-2 flex-wrap">
              {(
                [
                  { key: "all", label: "All courses" },
                  { key: "in_progress", label: "In progress" },
                  { key: "available", label: "Available" },
                  { key: "completed", label: "Completed" },
                ] as const
              ).map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setStatusFilter(key)}
                  className={cn(
                    "h-8 px-3.5 rounded-full text-xs font-semibold transition-all cursor-pointer select-none",
                    statusFilter === key
                      ? "bg-lms-cta text-white shadow-none"
                      : "bg-transparent text-muted-foreground border border-border/60 dark:border-lms-accent-border/40 hover:text-foreground hover:border-lms-accent"
                  )}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="relative w-full md:w-80">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search courses..."
                className="w-full h-10 pl-9 pr-9 border border-border/80 dark:border-lms-accent-border bg-background text-foreground rounded-full text-xs sm:text-sm focus:outline-none focus:border-lms-cta dark:focus:border-lms-accent transition-colors"
              />
              {searchInput && (
                <button
                  onClick={() => setSearchInput("")}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
                >
                  <X className="size-4" />
                </button>
              )}
            </div>
          </div>

          {/* Catalog Loading / Empty State */}
          {catalogLoading && <p className="text-sm text-muted-foreground">Loading courses...</p>}

          {!catalogLoading && filteredCourses.length === 0 && (
            <div className="lms-card p-12 text-center flex flex-col items-center justify-center gap-2">
              <p className="font-display text-base font-bold text-foreground">
                {search ? `No courses match "${search}".` : "No courses match the selected filter."}
              </p>
              <p className="text-xs text-muted-foreground">
                Try switching the status filter or clearing your search term.
              </p>
            </div>
          )}

          {/* Courses 3-Column Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {filteredCourses.map((course) => {
              const enrolledInfo = enrolledMap.get(course.id);
              const isEnrolled = course.enrolled || !!enrolledInfo;
              const isCompleted =
                enrolledInfo?.status === "completed" || enrolledInfo?.pct === 100;
              const modulesCount = getCourseModules(course);
              const duration = getCourseDuration(modulesCount);

              return (
                <article
                  key={course.id}
                  onClick={() => void navigate({ to: `/learn/courses/${course.id}` })}
                  className="lms-card overflow-hidden flex flex-col justify-between cursor-pointer group transition-all"
                >
                  {/* Media banner */}
                  <div className="h-44 sm:h-48 w-full border-b border-[#a880ff]/20 relative overflow-hidden bg-foreground/5 flex items-center justify-center">
                    {course.image_url ? (
                      <img
                        src={course.image_url}
                        alt={course.title}
                        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                      />
                    ) : (
                      <div className="relative w-full h-full flex items-center justify-center overflow-hidden">
                        <div className="w-20 h-20 rounded-full border border-[#a880ff]/40 relative flex items-center justify-center">
                          <div className="w-6 h-6 rounded-full border border-[#a880ff]/60" />
                          <div className="absolute w-32 h-12 rounded-full border border-[#a880ff]/25 rotate-[-25deg]" />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Body */}
                  <div className="p-6 sm:p-7 flex flex-col flex-1 justify-between gap-6">
                    <div className="flex flex-col gap-2.5">
                      <div className="flex items-center gap-4 text-xs text-muted-foreground pt-1">
                        <span className="flex items-center gap-1.5 font-medium">
                          <List className="size-3.5 text-lms-cta dark:text-lms-accent" />
                          {modulesCount} modules
                        </span>
                        <span className="flex items-center gap-1.5 font-medium">
                          <Clock className="size-3.5 text-lms-cta dark:text-lms-accent" />
                          {duration}
                        </span>
                        {course.level && (
                          <span className="capitalize text-muted-foreground">
                            · {course.level}
                          </span>
                        )}
                      </div>

                      <h3 className="font-display font-extrabold text-lg sm:text-xl text-foreground tracking-tight group-hover:text-lms-cta dark:group-hover:text-lms-accent transition-colors line-clamp-2 leading-snug">
                        {course.title}
                      </h3>

                      {course.description && (
                        <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed min-h-[36px]">
                          {course.description}
                        </p>
                      )}
                    </div>

                    {isEnrolled ? (
                      <div className="flex flex-col gap-2 pt-3 border-t border-border dark:border-white/10">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-muted-foreground font-medium">
                            {isCompleted ? "Completed" : "Progress"}
                          </span>
                          <strong className="font-display font-bold text-lms-cta dark:text-lms-accent">
                            {enrolledInfo?.pct ?? (isCompleted ? 100 : 0)}%
                          </strong>
                        </div>
                        <div className="h-1.5 rounded-full bg-foreground/10 dark:bg-white/10 overflow-hidden">
                          <div
                            className="h-full bg-lms-cta dark:bg-lms-accent rounded-full transition-all duration-300"
                            style={{ width: `${enrolledInfo?.pct ?? (isCompleted ? 100 : 0)}%` }}
                          />
                        </div>
                      </div>
                    ) : (
                      <div className="pt-3 border-t border-border dark:border-white/10 flex items-center justify-between">
                        <span className="text-xs font-semibold text-muted-foreground">
                          {course.access_mode === "paid" ? "Paid course" : "Free access"}
                        </span>
                        <span className="text-xs font-bold text-lms-cta dark:text-lms-accent inline-flex items-center gap-1 group-hover:translate-x-1 transition-transform">
                          View course <ArrowRight className="size-3.5" />
                        </span>
                      </div>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 2: UPCOMING PROGRAMS
          ========================================================================= */}
      {tab === "programs" && (
        <div className="flex flex-col gap-6">
          {programsLoading && <p className="text-sm text-muted-foreground">Loading programs...</p>}

          {!programsLoading && programs && programs.length === 0 && (
            <div className="lms-card p-12 text-center flex flex-col items-center justify-center gap-2">
              <p className="font-display text-base font-bold text-foreground">
                No upcoming programs open right now.
              </p>
              <p className="text-xs text-muted-foreground">
                Check back soon for new live cohort announcements.
              </p>
            </div>
          )}

          <div className="flex flex-col gap-4">
            {programs?.map((program) => (
              <UpcomingProgramRow key={program.cohort_id} program={program} />
            ))}
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 3: LEARNING PATHS
          ========================================================================= */}
      {tab === "paths" && (
        <div className="flex flex-col gap-8">
          {pathsLoading && <p className="text-sm text-muted-foreground">Loading paths...</p>}

          {!pathsLoading && paths && paths.length === 0 && (
            <div className="lms-card p-12 text-center flex flex-col items-center justify-center gap-2">
              <p className="font-display text-base font-bold text-foreground">
                No learning paths published yet.
              </p>
              <p className="text-xs text-muted-foreground">
                Check back soon for curated multi-course tracks.
              </p>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {paths?.map((path) => (
              <article
                key={path.id}
                onClick={() => void navigate({ to: `/learn/paths/${path.id}` })}
                className="lms-card overflow-hidden flex flex-col justify-between cursor-pointer group transition-all"
              >
                {/* Media banner */}
                <div className="h-44 sm:h-48 w-full border-b border-[#a880ff]/20 relative overflow-hidden bg-foreground/5 flex items-center justify-center">
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
                      <span>· Certificate included</span>
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
                        className="lms-btn-secondary w-full h-11 text-xs sm:text-sm inline-flex items-center justify-center gap-2 cursor-pointer"
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
        </div>
      )}
    </div>
  );
}
