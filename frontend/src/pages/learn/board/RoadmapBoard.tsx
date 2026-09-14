import { useEffect, useState } from "react";
import { useParams } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { fetchChecklist, type LmsProgramChecklistItem } from "@/api/lms";
import { cn } from "@/lib/utils";
import { NextTaskCard } from "./NextTaskCard";
import { TileField } from "./TileField";
import { FinalGateBar } from "./FinalGateBar";
import { TaskDrawer } from "./TaskDrawer";
import { checklistItemToTile, computeLiveTaskId, groupByCheckpoint, readBoardScrollPosition } from "./roadmap";

/** `/learn/checklists/$assignmentId` — the gated visual roadmap ("the
 * board") that replaces the old flat `LearnChecklist.tsx`. Order per the
 * design spec: banner → header + progress → next-task card → tile field →
 * final gate bar. One student code path — a program with no gating/
 * checkpoints just renders as an ungated board where every tile is live
 * (handoff decision #5). */
export default function RoadmapBoard() {
  const { assignmentId } = useParams({ strict: false }) as { assignmentId: string };
  const queryClient = useQueryClient();
  const [openItemId, setOpenItemId] = useState<string | null>(null);

  const { data: checklist, isLoading, error } = useQuery({
    queryKey: ["lms-checklist", assignmentId],
    queryFn: () => fetchChecklist(assignmentId),
    // The global default (30s staleTime) otherwise serves a cached board
    // as-is when a student finishes a step on a full page — a mission's
    // "back to program" link, a course, a quiz — and navigates back here:
    // the remount saw fresh-enough cached data and skipped refetching, so
    // the just-finished step still showed as not done until the 30s
    // window lapsed or the student refreshed by hand (found live,
    // 2026-09-14). This board's own data changes from *other* pages far
    // more than most queries do, so it always refetches on mount instead.
    refetchOnMount: "always",
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["lms-checklist", assignmentId] });

  // Restore scroll position on return from a deep link (flow rule 5: "Back
  // closes the loop... at the same scroll position"). Runs once the
  // checklist has actually rendered so the page is tall enough to scroll to.
  useEffect(() => {
    if (!checklist) return;
    const y = readBoardScrollPosition(assignmentId);
    if (y !== null) requestAnimationFrame(() => window.scrollTo(0, y));
  }, [checklist, assignmentId]);

  const items = checklist?.items ?? [];
  const liveTaskId = computeLiveTaskId(items);
  const liveItem = items.find((i) => i.id === liveTaskId) ?? null;
  const requiredItems = items.filter((i) => !i.optional);
  const doneCount = requiredItems.filter((i) => i.status === "done").length;
  const pct = requiredItems.length ? Math.round((100 * doneCount) / requiredItems.length) : 100;
  const groups = groupByCheckpoint(items);
  const openItem = items.find((i) => i.id === openItemId) ?? null;

  if (error) return <div className="mx-auto max-w-[900px] px-5 py-10"><p className="text-sm text-destructive">Couldn't load this program.</p></div>;
  if (isLoading || !checklist) return <div className="mx-auto max-w-[900px] px-5 py-10"><p className="text-sm text-muted-foreground">Loading...</p></div>;

  const openItemById = (item: LmsProgramChecklistItem) => {
    if (item.locked) return; // flow rule 2: locked tile → no-op
    setOpenItemId(item.id);
  };

  return (
    <div className="flex flex-col">
      <div className={cn("transition-[filter,opacity] duration-150", openItem && "md:blur-[1.5px] md:opacity-50")}>
        {/* Banner — native ratio, full width, never cropped (the clipping
            fix). The fade below is a lighting cue, not a crop: it sits on
            top of the image's own bottom edge so the poster reads as
            settling into the page instead of cutting off hard. */}
        <div className="relative">
          {checklist.image_url ? (
            <img src={checklist.image_url} alt="" className="w-full h-auto block" />
          ) : (
            <div className="h-[96px] sm:h-[180px] bg-[repeating-linear-gradient(135deg,hsl(var(--primary)/0.09)_0px,hsl(var(--primary)/0.09)_11px,hsl(var(--foreground)/0.014)_11px,hsl(var(--foreground)/0.014)_22px)]" />
          )}
          <div
            className="pointer-events-none absolute inset-x-0 bottom-0 h-2.5 sm:h-4 bg-[linear-gradient(to_top,hsl(var(--background)/0.7)_0%,hsl(var(--background)/0.3)_35%,hsl(var(--primary)/0.28)_65%,transparent_100%)]"
          />
        </div>

        <div className="px-5 sm:px-8 lg:px-14 py-6 sm:py-8 flex flex-col gap-6 sm:gap-8 max-w-[1180px] mx-auto w-full">
          <div className="flex flex-col gap-1.5">
            <h1 className="font-display text-[19px] sm:text-2xl font-extrabold tracking-tight leading-none">{checklist.name}</h1>
            {checklist.cohort_name && <p className="text-sm text-muted-foreground">{checklist.cohort_name}</p>}
            {checklist.team_name && (
              <div className="inline-flex w-fit items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-sm font-semibold text-primary">
                <Users className="size-4" /> Team {checklist.team_name}
              </div>
            )}
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-baseline gap-1 shrink-0">
              <span className="font-display text-2xl sm:text-3xl font-extrabold text-foreground">{doneCount}</span>
              <span className="text-base sm:text-lg font-semibold text-muted-foreground">/{requiredItems.length}</span>
              <span className="ml-1.5 whitespace-nowrap text-xs text-muted-foreground">steps done</span>
            </div>
            <div className="h-px flex-1 bg-border relative">
              <div className="absolute inset-y-0 left-0 bg-primary transition-[width] duration-300" style={{ width: `${pct}%` }} />
            </div>
          </div>

          <NextTaskCard item={liveItem} onStart={() => liveItem && openItemById(liveItem)} />

          {items.length > 0 && (
            <TileField
              items={items.map(checklistItemToTile)}
              liveTaskId={liveTaskId}
              onOpenItem={(tile) => setOpenItemId(tile.id)}
            />
          )}

          <FinalGateBar groups={groups} allDone={pct === 100} />
        </div>
      </div>

      {/* key remounts the drawer per item — its own per-item local state
          (guidelineOpened, submitUrl) resets via fresh useState instead of
          a useEffect+setState reset on item change. */}
      <TaskDrawer key={openItem?.id ?? "closed"} item={openItem} assignmentId={assignmentId} onClose={() => setOpenItemId(null)} onChanged={invalidate} />
    </div>
  );
}
