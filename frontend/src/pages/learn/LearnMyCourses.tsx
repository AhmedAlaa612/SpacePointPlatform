import { useMemo, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  List,
  Play,
  Rocket,
  Ticket,
  Users,
} from "lucide-react";
import { isAxiosError } from "axios";
import {
  fetchCatalog,
  fetchPublicCatalog,
  fetchLearningPaths,
  fetchMyChecklists,
  fetchMyCourses,
  redeemInviteCodeApi,
  type CourseCatalogItem,
  type DashboardCourse,
  type LmsProgramAssignmentSummary,
} from "@/api/lms";
import { fetchMyTeams } from "@/api/missions";
import { fetchMe } from "@/api/auth";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";
import { RedeemInviteModal } from "./components/RedeemInviteModal";

function getCourseModules(course: { modules_total?: number }): number {
  if (course.modules_total && course.modules_total > 0) return course.modules_total;
  return 6;
}

function getCourseDuration(modules: number): string {
  if (modules >= 8) return "4h 20m";
  if (modules >= 6) return "3h 45m";
  if (modules >= 4) return "2h 30m";
  return "1h 45m";
}

type TabKey = "all" | "programs" | "courses" | "completed";

export default function LearnMyCourses() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser, user, setCurrentUser } = useAuth();
  const isAuthed = !!user;

  const [tab, setTab] = useState<TabKey>("all");
  const [redeemModalOpen, setRedeemModalOpen] = useState(false);
  const [inlineCode, setInlineCode] = useState("");
  const [inlineLoading, setInlineLoading] = useState(false);
  const [inlineError, setInlineError] = useState<string | null>(null);

  const { data: dashboard, isLoading: coursesLoading } = useQuery({
    queryKey: ["lms-my-courses"],
    queryFn: fetchMyCourses,
    enabled: isAuthed,
  });

  const { data: checklists, isLoading: programsLoading } = useQuery({
    queryKey: ["lms-my-checklists"],
    queryFn: fetchMyChecklists,
    enabled: isAuthed,
  });

  const { data: paths } = useQuery({
    queryKey: ["lms-learning-paths"],
    queryFn: fetchLearningPaths,
    enabled: isAuthed,
  });

  const { data: teams } = useQuery({
    queryKey: ["missions-my-teams"],
    queryFn: fetchMyTeams,
    enabled: isAuthed,
  });

  const { data: catalog } = useQuery({
    queryKey: ["lms-catalog"],
    queryFn: () => (isAuthed ? fetchCatalog() : fetchPublicCatalog()),
  });

  const catalogMap = useMemo(() => {
    const map = new Map<string, CourseCatalogItem>();
    for (const item of catalog ?? []) {
      map.set(item.id, item);
    }
    return map;
  }, [catalog]);

  const firstName = currentUser?.full_name?.split(" ")[0] ?? "there";

  const enrolledPaths = useMemo(() => paths?.filter((p) => p.enrolled) ?? [], [paths]);
  const activePrograms = useMemo(() => checklists ?? [], [checklists]);
  const enrolledCourses = useMemo(() => dashboard?.courses ?? [], [dashboard]);
  const activeCourses = useMemo(
    () => enrolledCourses.filter((c) => c.status !== "completed"),
    [enrolledCourses]
  );
  const completedCourses = useMemo(
    () => enrolledCourses.filter((c) => c.status === "completed"),
    [enrolledCourses]
  );
  const completedPrograms = useMemo(
    () => activePrograms.filter((p) => p.pct === 100),
    [activePrograms]
  );

  const primaryResume = dashboard?.resume ?? null;
  const topProgram = activePrograms.find((p) => p.pct < 100) ?? activePrograms[0] ?? null;
  const topTeam = teams?.[0] ?? null;

  const handleInlineRedeem = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = inlineCode.trim().toUpperCase();
    if (!trimmed) return;
    setInlineLoading(true);
    setInlineError(null);
    try {
      const res = await redeemInviteCodeApi(trimmed);
      try {
        const me = await fetchMe();
        setCurrentUser(me);
      } catch {
        // ignore
      }
      await queryClient.invalidateQueries({ queryKey: ["lms-my-checklists"] });
      await queryClient.invalidateQueries({ queryKey: ["lms-my-courses"] });
      await queryClient.invalidateQueries({ queryKey: ["auth-me"] });
      setInlineCode("");
      if (res.redirect_to) {
        void navigate({ to: res.redirect_to as never });
      }
    } catch (err: unknown) {
      if (isAxiosError(err) && typeof err.response?.data?.detail === "string") {
        setInlineError(err.response.data.detail);
      } else {
        setInlineError("Could not redeem code. Please check and try again.");
      }
    } finally {
      setInlineLoading(false);
    }
  };

  const isLoading = coursesLoading || programsLoading;

  return (
    <div className="mx-auto max-w-[1240px] px-6 sm:px-10 lg:px-12 py-10 sm:py-16 flex flex-col gap-10 sm:gap-14">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div className="flex flex-col gap-2">
          <h1 className="font-display text-[38px] sm:text-[46px] lg:text-[48px] font-extrabold leading-[48px] tracking-[-1.2px] text-foreground">
            Keep moving, {firstName}.
          </h1>
        </div>

        {/* Quick Actions & Code Redemption */}
        <div className="flex items-center gap-3 shrink-0">
          <button
            onClick={() => setRedeemModalOpen(true)}
            className="lms-btn-secondary h-11 px-5 text-xs sm:text-sm inline-flex items-center gap-2 cursor-pointer"
          >
            <Ticket className="size-4" />
            Redeem code
          </button>
        </div>
      </div>

      {/* Primary Resume Card: Pick up where you left off */}
      {primaryResume ? (
        <article
          onClick={() =>
            void navigate({
              to: `/learn/courses/${primaryResume.course_id}/learn`,
              search: { item: primaryResume.next_item_id ?? undefined } as never,
            })
          }
          className="lms-card p-6 sm:p-8 flex flex-col sm:flex-row sm:items-center justify-between gap-6 cursor-pointer group transition-all"
        >
          <div className="flex-1 min-w-0 flex flex-col gap-2.5">
            <span className="text-xs font-bold uppercase tracking-wider text-lms-cta dark:text-lms-accent">
              Pick up where you left off
            </span>
            <h2 className="font-display text-xl sm:text-2xl font-extrabold text-foreground tracking-tight group-hover:text-lms-cta dark:group-hover:text-lms-accent transition-colors truncate">
              {primaryResume.module_title}
            </h2>
            <div className="flex items-center gap-4 max-w-md mt-1">
              <div className="flex-1 h-1.5 rounded-full bg-foreground/10 dark:bg-white/10 overflow-hidden">
                <div
                  className="h-full bg-lms-cta dark:bg-lms-accent rounded-full transition-all duration-300"
                  style={{
                    width: `${
                      primaryResume.mandatory_total
                        ? Math.round((100 * primaryResume.mandatory_completed) / primaryResume.mandatory_total)
                        : 0
                    }%`,
                  }}
                />
              </div>
              <span className="font-display font-bold text-xs text-lms-cta dark:text-lms-accent whitespace-nowrap">
                {primaryResume.mandatory_total
                  ? Math.round((100 * primaryResume.mandatory_completed) / primaryResume.mandatory_total)
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
                to: `/learn/courses/${primaryResume.course_id}/learn`,
                search: { item: primaryResume.next_item_id ?? undefined } as never,
              });
            }}
          >
            Resume lesson <ArrowRight className="size-4" />
          </button>
        </article>
      ) : topProgram ? (
        <article
          onClick={() =>
            void navigate({
              to: "/learn/checklists/$assignmentId",
              params: { assignmentId: topProgram.assignment_id },
            })
          }
          className="lms-card p-6 sm:p-8 flex flex-col sm:flex-row sm:items-center justify-between gap-6 cursor-pointer group transition-all"
        >
          <div className="flex-1 min-w-0 flex flex-col gap-2.5">
            <span className="text-xs font-bold uppercase tracking-wider text-lms-cta dark:text-lms-accent">
              Active program cohort · {topProgram.cohort_name ?? "Your checklist"}
            </span>
            <h2 className="font-display text-xl sm:text-2xl font-extrabold text-foreground tracking-tight group-hover:text-lms-cta dark:group-hover:text-lms-accent transition-colors truncate">
              {topProgram.name}
            </h2>
            <div className="flex items-center gap-4 max-w-md mt-1">
              <div className="flex-1 h-1.5 rounded-full bg-foreground/10 dark:bg-white/10 overflow-hidden">
                <div
                  className="h-full bg-lms-cta dark:bg-lms-accent rounded-full transition-all duration-300"
                  style={{ width: `${topProgram.pct}%` }}
                />
              </div>
              <span className="font-display font-bold text-xs text-lms-cta dark:text-lms-accent whitespace-nowrap">
                {topProgram.pct}%
              </span>
            </div>
          </div>

          <button
            className="lms-btn-primary h-11 px-6 text-xs sm:text-sm inline-flex items-center justify-center gap-2 cursor-pointer shrink-0"
            onClick={(e) => {
              e.stopPropagation();
              void navigate({
                to: "/learn/checklists/$assignmentId",
                params: { assignmentId: topProgram.assignment_id },
              });
            }}
          >
            Open checklist <ArrowRight className="size-4" />
          </button>
        </article>
      ) : null}

      {/* Switcher Pills */}
      <div className="flex items-center gap-2.5 sm:gap-3 flex-wrap">
        {(
          [
            { key: "all", label: "All" },
            { key: "programs", label: `Programs (${activePrograms.length})` },
            { key: "courses", label: `Courses (${dashboard?.courses.length ?? 0})` },
            { key: "completed", label: `Completed (${completedCourses.length + completedPrograms.length})` },
          ] as const
        ).map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              "h-9 px-4 rounded-full text-xs sm:text-sm font-bold transition-all cursor-pointer select-none",
              tab === key
                ? "bg-lms-cta text-white shadow-none"
                : "bg-transparent text-muted-foreground border border-border/60 dark:border-lms-accent-border hover:text-foreground hover:border-lms-accent"
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading your learning dashboard...</p>}

      {/* =========================================================================
          SECTION 1: PROGRAMS
          ========================================================================= */}
      {(tab === "all" || tab === "programs") && (
        <section className="flex flex-col gap-6">
          <div className="flex items-end justify-between gap-4">
            <h2 className="font-display text-2xl sm:text-[28px] font-extrabold text-foreground tracking-[-0.8px]">
              Programs
            </h2>
          </div>

          {activePrograms.length === 0 ? (
            <div className="lms-card p-8 sm:p-10 flex flex-col sm:flex-row sm:items-center justify-between gap-6">
              <div className="flex flex-col gap-1.5 max-w-md">
                <h3 className="font-display text-base font-bold text-foreground">
                  No programs assigned yet
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Have an invite code from your university, company, or challenge cohort? Enter it to unlock your checklist.
                </p>
              </div>

              <form onSubmit={handleInlineRedeem} className="flex items-center gap-2 w-full sm:w-auto">
                <input
                  type="text"
                  value={inlineCode}
                  onChange={(e) => {
                    setInlineCode(e.target.value);
                    if (inlineError) setInlineError(null);
                  }}
                  placeholder="Enter code..."
                  className="h-10 px-4 rounded-full border border-border/80 dark:border-lms-accent-border bg-background text-foreground text-xs uppercase tracking-wider font-mono focus:outline-none focus:border-lms-cta dark:focus:border-lms-accent w-40 sm:w-48"
                />
                <button
                  type="submit"
                  disabled={inlineLoading || !inlineCode.trim()}
                  className="lms-btn-primary h-10 px-5 text-xs font-bold cursor-pointer disabled:opacity-50 shrink-0"
                >
                  {inlineLoading ? "Redeeming..." : "Redeem"}
                </button>
              </form>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 sm:gap-8">
              {activePrograms.map((p) => (
                <article
                  key={p.assignment_id}
                  onClick={() =>
                    void navigate({
                      to: "/learn/checklists/$assignmentId",
                      params: { assignmentId: p.assignment_id },
                    })
                  }
                  className="lms-card p-6 sm:p-7 flex flex-col justify-between gap-6 cursor-pointer group transition-all"
                >
                  <div className="flex flex-col gap-3">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-lms-cta dark:text-lms-accent">
                        <Rocket className="size-3.5" />
                        {p.cohort_name ?? "Program checklist"}
                      </span>
                      {p.mode && (
                        <span className="font-mono text-[10px] px-2 py-0.5 rounded border border-border/60 text-muted-foreground uppercase">
                          {p.mode}
                        </span>
                      )}
                    </div>

                    <h3 className="font-display font-extrabold text-xl sm:text-2xl text-foreground tracking-tight group-hover:text-lms-cta dark:group-hover:text-lms-accent transition-colors leading-snug">
                      {p.name}
                    </h3>

                    {p.next_item_title ? (
                      <p className="text-xs text-muted-foreground">
                        Next task: <span className="text-foreground/90 font-medium">{p.next_item_title}</span>
                      </p>
                    ) : (
                      <p className="text-xs text-muted-foreground">All current milestones up to date.</p>
                    )}

                    {topTeam && (
                      <div className="flex items-center gap-2 text-xs text-muted-foreground pt-1">
                        <Users className="size-3.5 text-lms-cta dark:text-lms-accent" />
                        <span>Team: <strong className="font-semibold text-foreground">{topTeam.name}</strong></span>
                      </div>
                    )}
                  </div>

                  <div className="flex flex-col gap-4 pt-4 border-t border-border dark:border-white/10">
                    <div className="flex flex-col gap-2">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground font-medium">
                          {p.items_done} of {p.items_total} tasks done
                        </span>
                        <strong className="font-display font-bold text-lms-cta dark:text-lms-accent">
                          {p.pct}%
                        </strong>
                      </div>
                      <div className="h-1.5 rounded-full bg-foreground/10 dark:bg-white/10 overflow-hidden">
                        <div
                          className="h-full bg-lms-cta dark:bg-lms-accent rounded-full transition-all duration-300"
                          style={{ width: `${p.pct}%` }}
                        />
                      </div>
                    </div>

                    <button
                      className="lms-btn-secondary w-full h-11 text-xs sm:text-sm font-bold inline-flex items-center justify-center gap-2 cursor-pointer"
                      onClick={(e) => {
                        e.stopPropagation();
                        void navigate({
                          to: "/learn/checklists/$assignmentId",
                          params: { assignmentId: p.assignment_id },
                        });
                      }}
                    >
                      Open checklist <ArrowRight className="size-4" />
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      {/* =========================================================================
          SECTION 2: ACTIVE COURSES
          ========================================================================= */}
      {(tab === "all" || tab === "courses") && (
        <section className="flex flex-col gap-6">
          <div className="flex items-end justify-between gap-4">
            <h2 className="font-display text-2xl sm:text-[28px] font-extrabold text-foreground tracking-[-0.8px]">
              Courses
            </h2>
            <button
              onClick={() => void navigate({ to: "/learn/catalog" })}
              className="text-xs sm:text-sm font-semibold text-muted-foreground hover:text-lms-cta dark:hover:text-lms-accent inline-flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              Browse catalog <ArrowRight className="size-3.5" />
            </button>
          </div>

          {enrolledCourses.length === 0 ? (
            <div className="lms-card p-10 text-center flex flex-col items-center justify-center gap-3">
              <h3 className="font-display text-base font-bold text-foreground">
                No active courses right now
              </h3>
              <p className="text-xs text-muted-foreground max-w-sm">
                Explore the space engineering catalog to enroll in foundational CubeSat and orbital mechanics courses.
              </p>
              <button
                onClick={() => void navigate({ to: "/learn/catalog" })}
                className="lms-btn-primary h-10 px-5 text-xs font-bold mt-2 cursor-pointer inline-flex items-center gap-2"
              >
                Browse catalog <ArrowRight className="size-4" />
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
              {enrolledCourses.map((course) => {
                const catItem = catalogMap.get(course.course_id);
                const imageUrl = catItem?.image_url;
                const description = catItem?.description;
                const modules = getCourseModules(course);
                const duration = getCourseDuration(modules);
                const isDone = course.status === "completed" || course.pct === 100;

                return (
                  <article
                    key={course.course_id}
                    onClick={() => void navigate({ to: `/learn/courses/${course.course_id}` })}
                    className="lms-card overflow-hidden flex flex-col justify-between cursor-pointer group transition-all"
                  >
                    {/* Media Banner */}
                    <div className="h-44 sm:h-48 w-full border-b border-[#a880ff]/20 relative overflow-hidden bg-foreground/5 flex items-center justify-center">
                      {imageUrl ? (
                        <img
                          src={imageUrl}
                          alt={course.title}
                          className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                        />
                      ) : (
                        <div className="relative w-full h-full flex items-center justify-center overflow-hidden bg-foreground/5">
                          <div className="w-20 h-20 rounded-full border border-[#a880ff]/30 relative flex items-center justify-center">
                            <div className="w-6 h-6 rounded-full border border-[#a880ff]/50" />
                            <div className="absolute w-32 h-12 rounded-full border border-[#a880ff]/20 rotate-[-25deg]" />
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Content */}
                    <div className="p-6 flex flex-col flex-1 justify-between gap-5">
                      <div className="flex flex-col gap-2.5">
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

                        <h3 className="font-display font-extrabold text-lg sm:text-xl text-foreground tracking-tight group-hover:text-lms-cta dark:group-hover:text-lms-accent transition-colors line-clamp-2 leading-snug">
                          {course.title}
                        </h3>

                        {description && (
                          <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed min-h-[36px]">
                            {description}
                          </p>
                        )}
                      </div>

                      <div className="flex flex-col gap-2 pt-4 border-t border-border dark:border-white/10">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-muted-foreground font-medium">
                            {isDone ? "Completed" : `${course.modules_done} of ${course.modules_total} modules`}
                          </span>
                          <strong className="font-display font-bold text-lms-cta dark:text-lms-accent">
                            {isDone ? "100%" : `${course.pct}%`}
                          </strong>
                        </div>
                        <div className="h-1.5 rounded-full bg-foreground/10 dark:bg-white/10 overflow-hidden">
                          <div
                            className="h-full bg-lms-cta dark:bg-lms-accent rounded-full transition-all duration-300"
                            style={{ width: `${isDone ? 100 : course.pct}%` }}
                          />
                        </div>

                        <button
                          className="lms-btn-primary w-full h-10 mt-2 text-xs font-bold inline-flex items-center justify-center gap-2 cursor-pointer"
                          onClick={(e) => {
                            e.stopPropagation();
                            void navigate({ to: `/learn/courses/${course.course_id}/learn` });
                          }}
                        >
                          {isDone ? "Review course" : "Resume course"} <ArrowRight className="size-3.5" />
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      )}

      {/* =========================================================================
          SECTION 3: ENROLLED LEARNING PATHS
          ========================================================================= */}
      {(tab === "all" || tab === "courses") && enrolledPaths.length > 0 && (
        <section className="flex flex-col gap-6">
          <h2 className="font-display text-2xl sm:text-[28px] font-extrabold text-foreground tracking-[-0.8px]">
            Enrolled Learning Paths
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {enrolledPaths.map((path) => (
              <article
                key={path.id}
                onClick={() => void navigate({ to: `/learn/paths/${path.id}` })}
                className="lms-card overflow-hidden flex flex-col justify-between cursor-pointer group transition-all"
              >
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
                  </div>

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
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {/* =========================================================================
          SECTION 4: COMPLETED & CERTIFICATIONS
          ========================================================================= */}
      {tab === "completed" && (
        <section className="flex flex-col gap-6">
          <h2 className="font-display text-2xl sm:text-[28px] font-extrabold text-foreground tracking-[-0.8px]">
            Completed
          </h2>

          {completedCourses.length === 0 && completedPrograms.length === 0 ? (
            <div className="lms-card p-8 text-center flex flex-col items-center justify-center gap-2">
              <p className="font-display text-base font-bold text-foreground">
                No completed courses or programs yet
              </p>
              <p className="text-xs text-muted-foreground">
                Keep progressing through your active modules to earn official certificates.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {completedCourses.map((c) => (
                <div
                  key={c.course_id}
                  onClick={() => void navigate({ to: `/learn/courses/${c.course_id}` })}
                  className="lms-card p-6 flex flex-col justify-between gap-4 cursor-pointer group"
                >
                  <div className="flex items-center gap-2 text-xs font-semibold text-emerald-400">
                    <CheckCircle2 className="size-4" />
                    <span>Course completed</span>
                  </div>
                  <h3 className="font-display font-bold text-lg text-foreground group-hover:text-lms-cta dark:group-hover:text-lms-accent transition-colors truncate">
                    {c.title}
                  </h3>
                  <button className="lms-btn-secondary h-9 px-4 text-xs font-semibold inline-flex items-center justify-center gap-1.5">
                    Review course <ArrowRight className="size-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Redeem Invite Code Modal */}
      <RedeemInviteModal
        open={redeemModalOpen}
        onOpenChange={setRedeemModalOpen}
      />
    </div>
  );
}
