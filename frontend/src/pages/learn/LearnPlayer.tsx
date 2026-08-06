import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "@tanstack/react-router";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchCourse, fetchModule, type CourseDetail, type ModuleDetail } from "@/api/lms";
import { PlayerLayout } from "./PlayerLayout";
import { ItemPane } from "./ItemPane";

const COMPLETED = new Set(["completed", "skipped"]);

/** /learn/courses/$courseId/learn (design 1h) — one route for the whole
 * course; PlayerLayout's sidebar swaps which item ItemPane renders. Replaces
 * the old per-module route (LM1-8) entirely. */
export default function LearnPlayer() {
  const { courseId } = useParams({ strict: false }) as { courseId: string };
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
    <PlayerLayout course={course} modulesData={modulesData} selectedItemId={selectedItemId} onSelectItem={setSelectedItemId}>
      {selectedItem ? (
        <ItemPane
          key={selectedItem.id}
          item={selectedItem}
          moduleItems={selectedModuleId ? modulesData[selectedModuleId]?.items ?? [] : []}
          onProgressed={() => void handleProgressed()}
        />
      ) : (
        <div className="flex flex-col items-center text-center gap-3 py-16">
          <CheckCircle2 className="size-10 text-emerald-500" />
          <h2 className="font-display text-xl font-bold">Course complete</h2>
          <p className="text-sm text-muted-foreground">Nice work — every module is done.</p>
          <Button size="xl" onClick={() => void navigate({ to: `/learn/courses/${courseId}` })}>Back to course</Button>
        </div>
      )}
    </PlayerLayout>
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
