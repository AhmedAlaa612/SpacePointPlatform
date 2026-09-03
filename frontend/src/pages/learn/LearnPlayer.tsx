import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  fetchCourse, fetchModule, recordProgress, type CourseDetail, type ModuleDetail, type ModuleItem,
} from "@/api/lms";
import { PlayerLayout } from "./PlayerLayout";
import { ItemPane } from "./ItemPane";
import { CompletionCelebration } from "./CompletionCelebration";

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

  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [modulesData, setModulesData] = useState<Record<string, ModuleDetail>>({});
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [error, setError] = useState("");

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
      try {
        const c = await fetchCourse(courseId);
        if (cancelled) return;
        if (!c.enrolled) {
          void navigate({ to: `/learn/courses/${courseId}` });
          return;
        }
        setCourse(c);
        const map = await loadUnlockedModules(c, {});
        if (cancelled) return;
        setModulesData(map);

        const deepLinkItem = new URLSearchParams(window.location.search).get("item");
        if (deepLinkItem) {
          setSelectedItemId(deepLinkItem);
        } else {
          const firstIncomplete = findFirstIncomplete(c, map);
          setSelectedItemId(firstIncomplete);
        }
      } catch {
        if (!cancelled) setError("Couldn't load this course.");
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
  const [showCourseCelebration, setShowCourseCelebration] = useState(false);
  useEffect(() => {
    if (!search.program) return;
    const done = flat.length > 0 && selectedItemId === null;
    const was = wasCourseDoneRef.current;
    wasCourseDoneRef.current = done;
    if (was === null || was === done || !done) return;
    setShowCourseCelebration(true);
  }, [flat.length, selectedItemId, search.program]);

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
  if (!course) return <div className="p-8"><p className="text-sm text-muted-foreground">Loading...</p></div>;

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
          <div className="flex flex-col items-center text-center gap-3 py-16">
            <CheckCircle2 className="size-12 text-emerald-500" />
            <h2 className="font-display text-2xl font-bold">Course complete</h2>
            <p className="text-base text-muted-foreground">Nice work — every module is done.</p>
            <Button size="xl" onClick={() => void navigate({ to: `/learn/courses/${courseId}` })}>Back to course</Button>
          </div>
        )}
      </PlayerLayout>
      <CompletionCelebration
        open={showCourseCelebration}
        onOpenChange={setShowCourseCelebration}
        title="Course complete!"
        subtitle="Nice work — everything's finished here."
        assignmentId={search.program ?? ""}
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
