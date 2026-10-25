import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { CheckCircle2, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  fetchCourse, fetchModule, recordProgress, type CourseDetail, type ModuleDetail, type ModuleItem,
} from "@/api/lms";
import { PlayerLayout } from "./PlayerLayout";
import { ItemPane } from "./ItemPane";
import { CompletionCelebration } from "./CompletionCelebration";
import { EmojiRating } from "@/components/ui/EmojiRating";
import { useCourseRating } from "@/api/course_ratings";

const COMPLETED = new Set(["completed", "skipped"]);
const ITEM_KIND_LABEL: Record<ModuleItem["kind"], string> = {
  video: "Video", text: "Reading", quiz: "Quiz", flashcards: "Flashcards", attachment: "Attachment", mission: "Mission",
};

/** Ordered items across every unlocked module — module position, then item
 * position — for the Previous/Next-item nav bar (design 1h). */
function flatItems(course: CourseDetail, modulesData: Record<string, ModuleDetail>) {
  const ordered = [...course.modules].sort((a, b) => a.position - b.position).filter((m) => !m.locked);
  const flat: { moduleId: string; item: ModuleItem }[] = [];
  for (const m of ordered) {
    const items = [...(modulesData[m.module_id]?.items ?? [])].sort((a, b) => a.position - b.position);
    for (const item of items) flat.push({ moduleId: m.module_id, item });
  }
  return flat;
}

/** /learn/courses/$courseId/learn (design 1h) — one route for the whole
 * course; PlayerLayout's sidebar swaps which item ItemPane renders. Replaces
 * the old per-module route (LM1-8) entirely. */
export default function LearnPlayer() {
  const { courseId } = useParams({ strict: false }) as { courseId: string };
  const search = useSearch({ strict: false }) as { program?: string };
  const navigate = useNavigate();
  const [rating, setRating, { reviewText, saveReview, isSubmitting }] = useCourseRating(courseId);
  const [playerReviewOpen, setPlayerReviewOpen] = useState(false);
  const [playerReviewDraft, setPlayerReviewDraft] = useState(reviewText);
  const [playerReviewSaved, setPlayerReviewSaved] = useState(false);

  useEffect(() => {
    setPlayerReviewDraft(reviewText);
  }, [reviewText]);

  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [modulesData, setModulesData] = useState<Record<string, ModuleDetail>>({});
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [initialLoading, setInitialLoading] = useState(true);

  const loadUnlockedModules = useCallback(async (c: CourseDetail, have: Record<string, ModuleDetail>) => {
    const unlocked = c.modules.filter((m) => !m.locked && !have[m.module_id]);
    if (unlocked.length === 0) return have;
    const fetched = await Promise.all(unlocked.map((m) => fetchModule(m.module_id)));
    const next = { ...have };
    fetched.forEach((m) => { next[m.id] = m; });
    return next;
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function init() {
      setInitialLoading(true);
      setError("");
      try {
        const c = await fetchCourse(courseId);
        if (cancelled) return;
        if (!c.enrolled) {
          void navigate({ to: `/learn/courses/${courseId}` });
          return;
        }
        const map = await loadUnlockedModules(c, {});
        if (cancelled) return;

        const deepLinkItem = new URLSearchParams(window.location.search).get("item");
        const isOutline = new URLSearchParams(window.location.search).get("outline") === "true";
        let nextItemId = deepLinkItem || findFirstIncomplete(c, map);
        if (!nextItemId && (c.completed || isOutline)) {
          const flat = flatItems(c, map);
          if (flat.length > 0) {
            nextItemId = flat[0].item.id;
          }
        }

        setCourse(c);
        setModulesData(map);
        setSelectedItemId(nextItemId);
      } catch {
        if (!cancelled) setError("Couldn't load this course.");
      } finally {
        if (!cancelled) setInitialLoading(false);
      }
    }
    void init();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId]);

  const selectedModuleId = useMemo(() => {
    if (!selectedItemId) return null;
    for (const [moduleId, mod] of Object.entries(modulesData)) {
      if (mod.items.some((i) => i.id === selectedItemId)) return moduleId;
    }
    return null;
  }, [selectedItemId, modulesData]);

  const selectedItem = selectedModuleId ? modulesData[selectedModuleId]?.items.find((i) => i.id === selectedItemId) ?? null : null;
  const selectedVideoStatus =
    selectedItem?.kind === "video" && "transcode_status" in selectedItem.content
      ? selectedItem.content.transcode_status
      : null;

  // A video the worker hasn't finished transcoding yet flips to ready/failed
  // off-band — without this the student is stuck on "still processing" until
  // they manually reload the page.
  useEffect(() => {
    if (!selectedModuleId || (selectedVideoStatus !== "pending" && selectedVideoStatus !== "processing")) return;
    const moduleId = selectedModuleId;
    const interval = setInterval(() => {
      fetchModule(moduleId).then((fresh) => {
        setModulesData((prev) => ({ ...prev, [moduleId]: fresh }));
      }).catch(() => undefined);
    }, 5000);
    return () => clearInterval(interval);
  }, [selectedModuleId, selectedVideoStatus]);

  const currentModule = course?.modules.find((m) => m.module_id === selectedModuleId) ?? null;
  const itemsInModule = selectedModuleId ? modulesData[selectedModuleId]?.items ?? [] : [];
  const itemIndexInModule = itemsInModule.findIndex((i) => i.id === selectedItemId);

  // Still computed even though the Next-item nav bar it originally backed is
  // gone (see `handleProgressed`'s own advance-forward logic below, and
  // CompletionCelebration's own docblock) — `flat.length` is the readiness
  // gate the completion-celebration effect uses.
  const flat = useMemo(() => (course ? flatItems(course, modulesData) : []), [course, modulesData]);

  // Same "first observation is a baseline, not a celebration" pattern as
  // DesignMissionPage's own completion effect — `flat.length > 0` gates out
  // the loading window before modules/selectedItemId have actually settled,
  // where `selectedItemId === null` would otherwise look like a false
  // "already done" reading. Only wired up when this course was opened from
  // a checklist tile (`?program=`).
  const wasCourseDoneRef = useRef<boolean | null>(null);
  const celebrationShownRef = useRef(false);
  const [showCourseCelebration, setShowCourseCelebration] = useState(false);
  useEffect(() => {
    if (!search.program || initialLoading) return;
    if (flat.length === 0) return;
    const done = selectedItemId === null;
    const was = wasCourseDoneRef.current;
    wasCourseDoneRef.current = done;
    if (was === null) {
      if (done) celebrationShownRef.current = true;
      return;
    }
    if (!was && done && !celebrationShownRef.current) {
      celebrationShownRef.current = true;
      setShowCourseCelebration(true);
    }
  }, [flat.length, selectedItemId, search.program, initialLoading]);

  const handleProgressed = useCallback(async () => {
    if (!course || !selectedModuleId) return;
    const [freshModule, freshCourse] = await Promise.all([fetchModule(selectedModuleId), fetchCourse(courseId)]);
    let map = { ...modulesData, [selectedModuleId]: freshModule };
    map = await loadUnlockedModules(freshCourse, map);
    setCourse(freshCourse);
    setModulesData(map);

    const nextInModule = freshModule.items.find(
      (i) => i.id !== selectedItemId && !COMPLETED.has(i.status ?? "not_started"),
    );
    if (nextInModule) {
      setSelectedItemId(nextInModule.id);
      return;
    }
    const next = findFirstIncomplete(freshCourse, map, selectedModuleId);
    setSelectedItemId(next);
  }, [course, selectedModuleId, selectedItemId, modulesData, courseId, loadUnlockedModules]);

  if (error) return <div className="p-8"><p className="text-sm text-destructive">{error}</p></div>;
  if (initialLoading || !course) return <div className="p-8"><p className="text-sm text-muted-foreground">Loading...</p></div>;

  return (
    <>
      <PlayerLayout course={course} modulesData={modulesData} selectedItemId={selectedItemId} onSelectItem={setSelectedItemId}>
        {selectedItem ? (
          <div className="flex flex-col gap-6">
            {/* Video is player-first, title underneath (the YouTube/Vimeo
                convention — the thing you came here for is immediately
                visible, not below a heading) — every other kind keeps the
                title up top since there's no equivalent "big media" to lead
                with. */}
            {selectedItem.kind !== "video" && (
              <div className="min-w-0">
                {currentModule && (
                  <div className="text-xs font-semibold uppercase tracking-wide text-primary">
                    Module {currentModule.position} · Item {itemIndexInModule + 1} of {itemsInModule.length}
                  </div>
                )}
                <h1 className="font-display text-3xl font-bold tracking-tight mt-2">
                  {selectedItem.title ?? ITEM_KIND_LABEL[selectedItem.kind]}
                </h1>
              </div>
            )}

            {/* Each content type owns its own single "Got it!" action
                (ItemPane.tsx) — it both records progress and advances
                (onProgressed -> handleProgressed) in one step, so there's
                no separate "mark complete" control or Next-item nav bar
                here anymore. Video is the one exception: its Got it!
                button sits here instead, sharing a row with the title
                (below the player, both at the same height) rather than
                stacked under it inside ItemPane. */}
            <ItemPane key={selectedItem.id} item={selectedItem} onProgressed={() => void handleProgressed()} />

            {selectedItem.kind === "video" && (
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  {currentModule && (
                    <div className="text-xs font-semibold uppercase tracking-wide text-primary">
                      Module {currentModule.position} · Item {itemIndexInModule + 1} of {itemsInModule.length}
                    </div>
                  )}
                  <h1 className="font-display text-3xl font-bold tracking-tight mt-2">
                    {selectedItem.title ?? ITEM_KIND_LABEL[selectedItem.kind]}
                  </h1>
                </div>
                <Button
                  size="xl"
                  className="shrink-0"
                  onClick={() => { recordProgress(selectedItem.id, "video-watched").finally(() => void handleProgressed()); }}
                >
                  <CheckCircle2 className="size-4" /> Got it!
                </Button>
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center text-center gap-4 py-16 max-w-md mx-auto px-4">
            <CheckCircle2 className="size-14 text-emerald-500 animate-check-pop" />
            <h2 className="font-['Outfit'] text-3xl font-extrabold text-foreground">Course complete!</h2>
            <p className="text-base text-muted-foreground">Nice work — every module is done.</p>

            <div className="flex flex-col items-center gap-1.5 p-5 rounded-2xl border border-border/80 dark:border-lms-accent-border/30 bg-muted/20 dark:bg-[#0d0915] w-full my-1 shadow-lg shadow-black/10">
              <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                {rating ? "Your rating" : "Rate this course"}
              </p>
              <EmojiRating value={rating} onChange={setRating} />
              {rating && (
                <>
                  <p className="text-xs text-muted-foreground font-medium mt-1">
                    Rated {rating}/5 · Click to edit anytime
                  </p>
                  {!playerReviewOpen && !reviewText && (
                    <button
                      type="button"
                      onClick={() => setPlayerReviewOpen(true)}
                      className="text-xs text-primary hover:underline mt-1 cursor-pointer"
                    >
                      + Add a written review (optional)
                    </button>
                  )}
                  {(playerReviewOpen || reviewText) && (
                    <div className="w-full flex flex-col gap-1.5 mt-2.5 text-left">
                      <textarea
                        value={playerReviewDraft}
                        onChange={(e) => {
                          setPlayerReviewDraft(e.target.value);
                          setPlayerReviewSaved(false);
                        }}
                        placeholder="Share your feedback for the instructor (optional)..."
                        rows={2}
                        className="w-full text-xs p-2.5 rounded-lg bg-background border border-border resize-none focus:outline-none focus:ring-1 focus:ring-primary text-foreground"
                      />
                      <div className="flex items-center justify-between">
                        {playerReviewSaved ? (
                          <span className="text-xs text-emerald-500 font-medium flex items-center gap-1">
                            <Check className="size-3.5" /> Review saved!
                          </span>
                        ) : (
                          <span />
                        )}
                        {playerReviewDraft !== reviewText && (
                          <button
                            type="button"
                            disabled={isSubmitting}
                            onClick={async () => {
                              await saveReview(playerReviewDraft);
                              setPlayerReviewSaved(true);
                              setTimeout(() => setPlayerReviewSaved(false), 2500);
                            }}
                            className="text-xs font-medium px-3 py-1 rounded bg-primary text-primary-foreground hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-50"
                          >
                            {isSubmitting ? "Saving..." : "Save review"}
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            <Button size="xl" className="w-full mt-2" onClick={() => void navigate({ to: `/learn/courses/${courseId}` })}>
              Back to course
            </Button>
          </div>
        )}
      </PlayerLayout>
      <CompletionCelebration
        open={showCourseCelebration}
        onOpenChange={setShowCourseCelebration}
        title="Course complete!"
        subtitle="Nice work — everything's finished here."
        assignmentId={search.program ?? ""}
        courseId={courseId}
      />
    </>
  );
}

/** First non-completed item, walking modules in position order, skipping
 * locked modules and (optionally) a module already known to be exhausted. */
function findFirstIncomplete(course: CourseDetail, modulesData: Record<string, ModuleDetail>, skipModuleId?: string): string | null {
  const ordered = [...course.modules].sort((a, b) => a.position - b.position);
  for (const m of ordered) {
    if (m.locked || m.module_id === skipModuleId) continue;
    const items = modulesData[m.module_id]?.items ?? [];
    const next = items.find((i) => !COMPLETED.has(i.status ?? "not_started"));
    if (next) return next.id;
  }
  // Nothing incomplete left — the course-complete screen takes over; the
  // sidebar still lets a student click back into any item to review it.
  return null;
}
