import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams, useSearch, Link } from "@tanstack/react-router";
import { isAxiosError } from "axios";
import { CheckCircle2, ChevronDown, ChevronRight, Circle, Lock, PlayCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  enrollInCourse, fetchCourse, fetchModule, fetchPublicCourse, startCourseCheckout,
  type CourseDetail, type ModuleDetail, type ModuleItem, type ModuleLock,
} from "@/api/lms";
import { useAuth } from "@/context/AuthContext";
import { CourseProgress } from "./CourseProgress";

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail;
  return fallback;
}

function formatPrice(cents: number, currency: string): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: currency.toUpperCase() }).format(cents / 100);
}

const ITEM_KIND_LABEL: Record<ModuleItem["kind"], string> = {
  video: "Video", text: "Reading", quiz: "Quiz", flashcards: "Flashcards", attachment: "Attachment", mission: "Mission",
};

/** Course landing (design 1g) — orient & enrol only; in-progress state lives
 * on /learn/my-courses, the player is /learn/courses/$id/learn. Browsing
 * needs only login (D8); playing needs an active enrollment. */
export default function LearnCourse() {
  // strict from-string lookup can fail to resolve on a fresh/hard page load
  // (see LMS_EXECUTION_PLAN.md §DISCOVERIES, LM1-13) — strict: false reads
  // whatever route actually matched instead of re-deriving it.
  const { courseId } = useParams({ strict: false }) as { courseId: string };
  // Carried through from a Roadmap board tile (TaskDrawer) so the player
  // can offer a "back to your program" nudge on completion — forwarded
  // as-is into the player below, not read for anything on this page itself.
  const search = useSearch({ strict: false }) as { program?: string };
  const navigate = useNavigate();
  // Logged-out visitors get the public outline (same shape, prices
  // included, module-1-open/rest-locked). Enrolling costs a login.
  const { user } = useAuth();
  const isAuthed = !!user;
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [error, setError] = useState("");
  const [enrolling, setEnrolling] = useState(false);
  // Separate from `error` (a fatal, whole-page load failure below) — an
  // enroll attempt failing (invite-only, payment not available yet) is a
  // transient, in-place message, not a reason to blank out the page the
  // student is currently looking at.
  const [enrollError, setEnrollError] = useState("");

  // A module's item list (2026-09, "let me see what's inside before I
  // commit to a module") is only ever fetched once it's actually opened —
  // fetchModule per module, not fetchCourse's own payload, so browsing this
  // page doesn't pull every module's contents up front. Cached by id so
  // re-collapsing/expanding the same module doesn't refetch.
  const [expandedModuleId, setExpandedModuleId] = useState<string | null>(null);
  const [moduleItems, setModuleItems] = useState<Record<string, ModuleDetail>>({});
  const [loadingModuleId, setLoadingModuleId] = useState<string | null>(null);

  const load = useCallback(() => {
    (isAuthed ? fetchCourse(courseId) : fetchPublicCourse(courseId))
      .then(setCourse)
      .catch(() => setError("Couldn't load this course."));
  }, [courseId, isAuthed]);

  useEffect(() => {
    load();
  }, [load]);

  const toggleModule = (moduleId: string) => {
    setExpandedModuleId((cur) => (cur === moduleId ? null : moduleId));
    // Module contents are an enrolled-student read — visitors expanding a
    // module get the login nudge instead (rendered by ModuleRow), never a
    // 401 that would bounce the whole page to /learn/login.
    if (!isAuthed || moduleItems[moduleId]) return;
    setLoadingModuleId(moduleId);
    fetchModule(moduleId)
      .then((m) => setModuleItems((prev) => ({ ...prev, [moduleId]: m })))
      .catch(() => {})
      .finally(() => setLoadingModuleId((cur) => (cur === moduleId ? null : cur)));
  };

  const isPurchasable = course?.access_mode === "paid" || (course?.price_cents != null && course.price_cents > 0);

  const handleEnroll = async () => {
    // Browsing is free, enrolling costs a login — send visitors to sign in
    // first rather than firing an authed POST that bounces them.
    if (!isAuthed) {
      void navigate({ to: "/learn/login" });
      return;
    }
    setEnrolling(true);
    setEnrollError("");
    try {
      if (isPurchasable) {
        const { checkout_url } = await startCourseCheckout(courseId);
        window.location.href = checkout_url;
        return; // leaving the page — don't clear `enrolling` on the way out
      }
      await enrollInCourse(courseId);
      load();
    } catch (err) {
      // Surfaces the backend's own message — it already distinguishes
      // invite-only (403) and not-yet-available payment (402) from a
      // genuine failure (P1-7). A 409 means another checkout attempt is
      // already in flight for this course — worth a plain retry.
      setEnrollError(errorDetail(err, "Couldn't enroll right now. Please try again."));
      setEnrolling(false);
    }
  };

  if (error) return <div className="mx-auto max-w-[900px] px-5 py-10"><p className="text-sm text-destructive">{error}</p></div>;
  if (!course) return <div className="mx-auto max-w-[900px] px-5 py-10"><p className="text-sm text-muted-foreground">Loading...</p></div>;

  const modulesDone = course.modules.filter((m) =>
    (m.total_items ?? (m.mandatory_total > 0 ? m.mandatory_total : 0)) > 0 &&
    (m.mandatory_total === 0 || m.mandatory_completed >= m.mandatory_total)
  ).length;
  const pct = course.modules.length ? Math.round(100 * modulesDone / course.modules.length) : 0;
  const itemCta = course.completed ? "Review" : modulesDone > 0 ? "Resume" : "Start";

  return (
    <div className="mx-auto max-w-[1180px] px-5 sm:px-8 lg:px-10 py-8 sm:py-10 flex flex-col gap-8">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/learn/catalog" className="text-primary hover:opacity-80">Catalog</Link>
        {course.track && (
          <>
            <ChevronRight className="size-3.5" />
            <span>{course.track}</span>
          </>
        )}
        <ChevronRight className="size-3.5" />
        <span className="text-foreground">{course.title}</span>
      </div>

      <div className="grid lg:grid-cols-[1fr_380px] gap-10 items-start">
        <div className="flex flex-col gap-8 min-w-0">
          <div className="flex flex-col gap-4">
            {course.level && (
              <span className="w-fit text-xs font-semibold uppercase tracking-wider px-3 py-1 rounded-md bg-lms-cta-light border border-lms-accent-border text-lms-cta dark:text-lms-accent capitalize">
                {course.level}
              </span>
            )}
            <h1 className="font-['Outfit'] text-3xl sm:text-4xl font-extrabold tracking-tight leading-tight text-foreground">{course.title}</h1>
            {course.description && <p className="text-base sm:text-lg leading-relaxed text-muted-foreground max-w-xl">{course.description}</p>}
            <div className="flex items-center gap-6 pt-1">
              <div className="flex items-center gap-2 text-sm sm:text-base text-muted-foreground">
                <PlayCircle className="size-[18px] text-lms-cta dark:text-lms-accent" /> {course.modules.length} modules
              </div>
            </div>
          </div>

          {course.outcomes.length > 0 && (
            <div className="flex flex-col gap-4">
              <h2 className="font-['Outfit'] text-xl sm:text-2xl font-bold tracking-tight text-foreground">What you'll be able to do</h2>
              <div className="grid sm:grid-cols-2 gap-x-6 gap-y-3.5">
                {course.outcomes.map((o, i) => (
                  <div key={i} className="flex items-start gap-3">
                    <div className="w-5 h-5 rounded-md bg-lms-cta-light text-lms-cta dark:text-lms-accent border border-lms-accent-border flex items-center justify-center shrink-0 mt-0.5">
                      <CheckCircle2 className="size-3.5" />
                    </div>
                    <span className="text-sm sm:text-base text-muted-foreground leading-snug">{o}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex flex-col gap-4">
            <div className="flex items-end justify-between">
              <h2 className="font-['Outfit'] text-xl sm:text-2xl font-bold tracking-tight text-foreground">Course contents</h2>
              <span className="text-xs sm:text-sm text-muted-foreground font-semibold">{course.modules.length} modules</span>
            </div>
            <div className="lms-card divide-y divide-[#a880ff]/20 overflow-hidden">
              {course.modules.map((module) => (
                <ModuleRow
                  key={module.module_id}
                  module={module}
                  courseId={course.id}
                  program={search.program}
                  enrolled={course.enrolled}
                  isAuthed={isAuthed}
                  expanded={expandedModuleId === module.module_id}
                  onToggle={() => toggleModule(module.module_id)}
                  detail={moduleItems[module.module_id]}
                  loading={loadingModuleId === module.module_id}
                />
              ))}
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-5 lg:sticky lg:top-24">
          <div className="lms-card overflow-hidden">
            <div className="h-[200px] border-b border-[#a880ff]/20 overflow-hidden bg-foreground/5 flex items-center justify-center">
              {course.image_url ? (
                <img src={course.image_url} alt="" className="w-full h-full object-cover" />
              ) : (
                <PlayCircle className="size-9 text-muted-foreground" />
              )}
            </div>
            <div className="p-6 flex flex-col gap-4">
              {course.enrolled ? (
                <>
                  {course.completed && (
                    <div className="flex items-center gap-2 text-sm font-semibold text-emerald-400">
                      <CheckCircle2 className="size-4" /> Completed
                    </div>
                  )}
                  <CourseProgress value={pct} label={`${modulesDone} of ${course.modules.length} modules`} />
                  <button
                    type="button"
                    className="lms-btn-primary w-full py-3.5 font-['Outfit'] text-sm tracking-wide cursor-pointer"
                    onClick={() => void navigate({ to: `/learn/courses/${course.id}/learn`, search: { program: search.program } as never })}
                  >
                    {itemCta}
                  </button>
                </>
              ) : course.access_mode === "invite" && !isPurchasable ? (
                <>
                  <Button size="xl" className="w-full" disabled>
                    <Lock className="size-[18px]" /> Invite only
                  </Button>
                  <p className="text-xs sm:text-sm text-muted-foreground text-center">Ask an admin for access.</p>
                </>
              ) : course.locked ? (
                <>
                  <Button size="xl" className="w-full" disabled>
                    <Lock className="size-[18px]" /> Locked
                  </Button>
                  <div className="flex flex-wrap gap-2">
                    {course.prerequisites.map((p) => (
                      <span
                        key={p.item_id}
                        className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border ${
                          p.satisfied ? "border-emerald-500/30 text-emerald-400" : "border-border text-muted-foreground"
                        }`}
                      >
                        {p.satisfied ? <CheckCircle2 className="size-3.5" /> : <Lock className="size-3.5" />}
                        {p.title}
                      </span>
                    ))}
                  </div>
                </>
              ) : (
                <button
                  type="button"
                  className="lms-btn-primary w-full py-3.5 font-['Outfit'] text-sm tracking-wide cursor-pointer disabled:opacity-40"
                  onClick={() => void handleEnroll()}
                  disabled={enrolling}
                >
                  {enrolling
                    ? (isPurchasable ? "Redirecting to checkout..." : "Enrolling...")
                    : !isAuthed
                      ? (isPurchasable
                        ? `Log in to buy${course.price_cents != null ? ` — ${formatPrice(course.price_cents, course.currency)}` : ""}`
                        : "Log in to enroll")
                      : isPurchasable
                        ? `Buy${course.price_cents != null ? ` — ${formatPrice(course.price_cents, course.currency)}` : ""}`
                        : "Enroll"}
                </button>
              )}
              {enrollError && <p className="text-xs sm:text-sm text-destructive text-center">{enrollError}</p>}
              <div className="h-px bg-[#a880ff]/15 my-1" />
              <div className="flex items-center gap-3 text-xs sm:text-sm text-muted-foreground">
                <PlayCircle className="size-4 shrink-0 text-[#A880FF]" /> Learn at your own pace
              </div>
              <div className="flex items-center gap-3 text-xs sm:text-sm text-muted-foreground">
                <CheckCircle2 className="size-4 shrink-0 text-lms-cta dark:text-lms-accent" /> Quizzes &amp; flashcards included
              </div>
            </div>
          </div>

          {course.instructor_name && (
            <div className="lms-card p-6 flex flex-col gap-4 items-start">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Your instructor</div>
              <div className="flex items-center gap-3.5">
                <div className="w-14 h-14 rounded-full bg-lms-cta-light border border-lms-accent-border overflow-hidden shrink-0 flex items-center justify-center text-lms-cta dark:text-lms-accent font-['Outfit'] font-bold text-base">
                  {course.instructor_photo_url ? (
                    <img src={course.instructor_photo_url} alt="" className="w-full h-full object-cover" />
                  ) : (
                    course.instructor_name.split(" ").map((w) => w[0]).slice(0, 2).join("")
                  )}
                </div>
                <div className="min-w-0">
                  <div className="font-['Outfit'] text-base font-bold text-foreground truncate">{course.instructor_name}</div>
                  {course.instructor_title && <div className="text-xs text-lms-cta dark:text-lms-accent mt-0.5 truncate">{course.instructor_title}</div>}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** One "Course contents" row — collapsed it's a summary (position/done
 * marker, title, mandatory-item count); expanded it lazy-loads and lists
 * every item in the module, each independently clickable straight into the
 * player at that exact item (`?item=`, the same deep-link LearnLanding's
 * "Resume" card and LearnPlayer's own init effect already use). Locked
 * modules still expand for a look — the header row and every item just
 * aren't clickable. */
function ModuleRow({
  module, courseId, program, enrolled, isAuthed, expanded, onToggle, detail, loading,
}: {
  module: ModuleLock;
  courseId: string;
  program: string | undefined;
  enrolled: boolean;
  isAuthed: boolean;
  expanded: boolean;
  onToggle: () => void;
  detail: ModuleDetail | undefined;
  loading: boolean;
}) {
  const navigate = useNavigate();
  const hasItems = (module.total_items ?? (module.mandatory_total > 0 ? 1 : 0)) > 0;
  const done = hasItems && (module.mandatory_total === 0 || module.mandatory_completed >= module.mandatory_total);
  const openable = enrolled && !module.locked;

  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        className={`w-full flex items-center gap-4 p-5 text-left transition-colors cursor-pointer hover:bg-[#a880ff]/5 ${module.locked ? "opacity-60" : ""}`}
      >
        <div className={`w-8 h-8 rounded-full border flex items-center justify-center shrink-0 text-xs font-bold font-['Outfit'] ${
          module.locked ? "border-[#a880ff]/20 text-muted-foreground/50" : done ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-400" : "border-[#a880ff]/40 text-foreground"
        }`}>
          {module.locked ? <Lock className="size-3.5" /> : done ? <CheckCircle2 className="size-4" /> : module.position}
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-['Outfit'] text-base font-bold text-foreground">{module.title ?? `Module ${module.position}`}</div>
          <div className="text-xs sm:text-sm text-muted-foreground mt-0.5">
            {module.total_items === 0
              ? "No content yet"
              : module.mandatory_total === 0
              ? "Optional content"
              : `${module.mandatory_completed}/${module.mandatory_total} complete`}
          </div>
        </div>
        <ChevronDown className={`size-4 text-muted-foreground shrink-0 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`} />
      </button>

      {expanded && (
        <div className="px-5 pb-4 flex flex-col gap-0.5 border-t border-[#a880ff]/15 pt-3">
          {loading && <p className="text-xs sm:text-sm text-muted-foreground py-2 px-3">Loading...</p>}
          {!loading && !isAuthed && (
            <div className="flex flex-col sm:flex-row sm:items-center gap-3 py-2 px-3">
              <p className="text-xs sm:text-sm text-muted-foreground flex-1">Log in to see what's inside this module.</p>
              <button
                type="button"
                onClick={() => void navigate({ to: "/learn/login" })}
                className="shrink-0 px-4 py-2 rounded-xl text-xs sm:text-sm font-semibold lms-btn-primary cursor-pointer"
              >
                Log in
              </button>
            </div>
          )}
          {!loading && isAuthed && detail && detail.items.length === 0 && (
            <p className="text-xs sm:text-sm text-muted-foreground py-2 px-3">No content in this module yet.</p>
          )}
          {detail?.items.map((item) => {
            const itemDone = item.status === "completed" || item.status === "skipped";
            return (
              <button
                key={item.id}
                type="button"
                disabled={!openable}
                onClick={() => {
                  if (!openable) return;
                  void navigate({ to: `/learn/courses/${courseId}/learn`, search: { item: item.id, program } as never });
                }}
                className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${
                  openable ? "hover:bg-[#a880ff]/5 cursor-pointer text-foreground" : "cursor-default text-muted-foreground/60"
                }`}
              >
                {itemDone ? (
                  <CheckCircle2 className="size-4 text-emerald-400 shrink-0" />
                ) : (
                  <Circle className="size-4 text-muted-foreground/30 shrink-0" />
                )}
                <span className="text-xs sm:text-sm flex-1 min-w-0 truncate">{item.title ?? ITEM_KIND_LABEL[item.kind]}</span>
                <span className="text-xs text-muted-foreground shrink-0">{ITEM_KIND_LABEL[item.kind]}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
