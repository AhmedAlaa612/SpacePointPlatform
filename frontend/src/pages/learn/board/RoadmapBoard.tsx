import { useEffect, useState } from "react";
import { useNavigate, useParams } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LogOut, RotateCcw, Users } from "lucide-react";
import {
  fetchChecklist, observerResetProgressApi, observerResetTeamApi, observerUnassignApi,
  type LmsProgramChecklistItem,
} from "@/api/lms";
import { cn } from "@/lib/utils";
import { NextTaskCard } from "./NextTaskCard";
import { TileField } from "./TileField";
import { FinalGateBar } from "./FinalGateBar";
import { TaskDrawer } from "./TaskDrawer";
import { CheckpointDrawer } from "./CheckpointDrawer";
import { StudentTeamResultCard } from "@/components/competitions/StudentTeamResultCard";
import { ObserverTeamModal } from "@/components/lms/ObserverTeamModal";
import { LockedTaskModal } from "./LockedTaskModal";
import {
  checklistItemToTile, computeLiveTaskId, groupByCheckpoint, readBoardScrollPosition,
} from "./roadmap";

/** `/learn/checklists/$assignmentId` — the gated visual roadmap ("the
 * board") that replaces the old flat `LearnChecklist.tsx`. Order per the
 * design spec: banner → header + progress → next-task card → tile field →
 * final gate bar. One student code path — a program with no gating/
 * checkpoints just renders as an ungated board where every tile is live
 * (handoff decision #5). */
export default function RoadmapBoard() {
  const { assignmentId } = useParams({ strict: false }) as { assignmentId: string };
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [openItemId, setOpenItemId] = useState<string | null>(null);
  const [lockedItem, setLockedItem] = useState<LmsProgramChecklistItem | null>(null);
  const [showTeamModal, setShowTeamModal] = useState(false);
  // Observer mode (2026-10) — which reset is in flight, so its button reads
  // busy and double-clicks can't stack two resets.
  const [observerBusy, setObserverBusy] = useState<"mine" | "team" | "leave" | null>(null);

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

  const isObserver = checklist?.mode === "observer";

  const handleResetMine = async () => {
    if (!window.confirm("Reset your own observer progress? Your team deliverables stay intact.")) return;
    setObserverBusy("mine");
    try {
      await observerResetProgressApi(assignmentId);
      await invalidate();
    } finally {
      setObserverBusy(null);
    }
  };

  const handleResetTeam = async () => {
    if (!window.confirm("Reset this observer team's deliverables and unlock its final submission?")) return;
    setObserverBusy("team");
    try {
      await observerResetTeamApi(assignmentId);
      await invalidate();
    } finally {
      setObserverBusy(null);
    }
  };

  const handleLeaveProgram = async () => {
    if (!window.confirm("Leave this observer program? Your observer progress and team membership are removed.")) return;
    setObserverBusy("leave");
    try {
      await observerUnassignApi(assignmentId);
      await navigate({ to: "/learn/checklists" });
    } finally {
      setObserverBusy(null);
    }
  };

  // Restore scroll position on return from a deep link (flow rule 5: "Back
  // closes the loop... at the same scroll position"). Runs once the
  // checklist has actually rendered so the page is tall enough to scroll to.
  useEffect(() => {
    if (!checklist) return;
    const y = readBoardScrollPosition(assignmentId);
    if (y !== null) requestAnimationFrame(() => window.scrollTo(0, y));
  }, [checklist, assignmentId]);

  // A team-scoped tile that isn't done yet reads locked once the team has
  // hit "Final Submit" (checklist.team_final_locked_at) — a done tile
  // stays "cleared" and reviewable, not styled "Not powered" like a tile
  // that was never reachable to begin with. Only the not-done case needs
  // the override: TaskTile already renders "cleared" for a done item
  // regardless of item.locked (found live, 2026-09-19: an earlier version
  // of this fix locked every team-scoped item unconditionally, which made
  // already-completed ones look broken instead of finished; this version
  // dropped the override entirely instead, which left a still-open
  // team-scoped item clickable after the team had already locked).
  const items = (checklist?.items ?? []).map((item) => (
    item.scope === "team" && item.status !== "done" && checklist?.team_final_locked_at
      ? { ...item, locked: true }
      : item
  ));
  const liveTaskId = computeLiveTaskId(items);
  const liveItem = items.find((i) => i.id === liveTaskId) ?? null;
  const requiredItems = items.filter((i) => !i.optional);
  const doneCount = requiredItems.filter((i) => i.status === "done").length;
  const pct = requiredItems.length ? Math.round((100 * doneCount) / requiredItems.length) : 100;
  const groups = groupByCheckpoint(items);
  // "Final Submit" is a team action — only the team's own required
  // deliverables gate it, not a teammate's unrelated personal task (found
  // live, 2026-09-19: a leftover individual item kept the button disabled
  // even once every team deliverable was in). Mirrors the backend's own
  // team_final_submit_readiness, which checks the same subset.
  const requiredTeamItems = requiredItems.filter((i) => i.scope === "team");
  const teamReady = requiredTeamItems.length > 0 && requiredTeamItems.every((i) => i.status === "done");
  // Same "team items only, when there are any" basis as teamReady above —
  // computed here, not guessed inside FinalGateBar from an optional prop,
  // so a no-team program (requiredTeamItems always [] there, never
  // undefined) can't silently read as 0-remaining/ready-to-review (found
  // live, 2026-09-19).
  const remainingCount = requiredTeamItems.length > 0
    ? requiredTeamItems.filter((i) => i.status !== "done").length
    : requiredItems.length - doneCount;
  const openItem = items.find((i) => i.id === openItemId) ?? null;

  if (error) return <div className="mx-auto max-w-[900px] px-5 py-10"><p className="text-sm text-destructive">Couldn't load this program.</p></div>;
  if (isLoading || !checklist) return <div className="mx-auto max-w-[900px] px-5 py-10"><p className="text-sm text-muted-foreground">Loading...</p></div>;

  const openItemById = (item: LmsProgramChecklistItem) => {
    if (item.locked && item.status !== "done") {
      setLockedItem(item);
      return;
    }
    setOpenItemId(item.id);
  };

  return (
    <div className="flex flex-col">
      {/* Observer mode (2026-10) — the "reset" half of "a student with a
          label plus a reset". Full student access; actions write to the
          observer sandbox, never official data. */}
      {isObserver && (
        <div className="bg-indigo-500/10 border-b border-indigo-500/20 text-indigo-950 dark:text-indigo-200 px-4 py-2.5 text-xs font-medium flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 rounded font-bold uppercase tracking-wider bg-indigo-500/20 border border-indigo-500/30">
              Observer Mode
            </span>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => void handleResetMine()}
              disabled={observerBusy !== null}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-indigo-500/30 hover:bg-indigo-500/10 transition-colors cursor-pointer disabled:opacity-50 text-xs font-semibold"
            >
              <RotateCcw size={12} /> {observerBusy === "mine" ? "Resetting…" : "Reset My Progress"}
            </button>
            {checklist.team_name ? (
              <button
                onClick={() => void handleResetTeam()}
                disabled={observerBusy !== null}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-indigo-500/30 hover:bg-indigo-500/10 transition-colors cursor-pointer disabled:opacity-50 text-xs font-semibold"
              >
                <RotateCcw size={12} /> {observerBusy === "team" ? "Resetting…" : "Reset Team Deliverables"}
              </button>
            ) : checklist.cohort_id ? (
              <button
                onClick={() => setShowTeamModal(true)}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-indigo-500/30 hover:bg-indigo-500/10 transition-colors cursor-pointer text-xs font-semibold"
                title="Join an existing observer team or create a new one"
              >
                <Users size={12} /> Join / Create Observer Team
              </button>
            ) : null}
            <button
              onClick={() => void handleLeaveProgram()}
              disabled={observerBusy !== null}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg hover:bg-indigo-500/10 transition-colors cursor-pointer disabled:opacity-50 text-xs font-semibold"
            >
              <LogOut size={12} /> {observerBusy === "leave" ? "Leaving…" : "Leave"}
            </button>
          </div>
        </div>
      )}
      {isObserver && checklist?.cohort_id && (
        <ObserverTeamModal
          cohortId={checklist.cohort_id}
          cohortName={checklist.cohort_name ?? undefined}
          open={showTeamModal}
          onClose={() => setShowTeamModal(false)}
          onSuccess={() => {
            void invalidate();
          }}
        />
      )}
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

        <div className="px-5 sm:px-8 lg:px-8 xl:px-14 py-6 sm:py-8 flex flex-col gap-6 sm:gap-8 max-w-[1180px] mx-auto w-full">
          <div className="flex flex-col gap-1.5">
            <h1 className="font-display text-[19px] sm:text-2xl font-extrabold tracking-tight leading-none">
              {checklist.name}
            </h1>
            {checklist.program_name && (
              <p className="text-xs sm:text-sm font-medium text-muted-foreground">
                {checklist.program_name}
              </p>
            )}
            {checklist.team_name && (
              <div className="flex flex-wrap items-center gap-2">
                <div className="inline-flex w-fit items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-sm font-semibold text-primary">
                  <Users className="size-4" /> Team {checklist.team_name}
                </div>
                {checklist.team_code && (
                  <span className="inline-flex w-fit items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs font-mono font-bold tracking-[0.15em] text-muted-foreground">
                    {checklist.team_code}
                  </span>
                )}
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

          {checklist?.cohort_id && <StudentTeamResultCard cohortId={checklist.cohort_id} />}

          <NextTaskCard item={liveItem} onStart={() => liveItem && openItemById(liveItem)} />

          {items.length > 0 && (
            <TileField
              items={items.map((i) => checklistItemToTile(i, items))}
              liveTaskId={liveTaskId}
              onOpenItem={(tile) => {
                const clicked = items.find((i) => i.id === tile.id);
                if (clicked) openItemById(clicked);
                else setOpenItemId(tile.id);
              }}
            />
          )}

          <FinalGateBar
            groups={groups}
            teamReady={teamReady}
            locked={!!checklist.team_final_locked_at}
            hasTeam={!!checklist.team_name}
            assignmentId={assignmentId}
            onFinalized={invalidate}
            teamName={checklist.team_name}
            lockedAt={checklist.team_final_locked_at}
            lockedByName={checklist.team_final_locked_by_name}
            pct={pct}
            remainingCount={remainingCount}
            cohortId={checklist?.cohort_id}
          />
        </div>
      </div>

      {/* key remounts the drawer per item — its own per-item local state
          (guidelineOpened, submitUrl) resets via fresh useState instead of
          a useEffect+setState reset on item change. Checkpoint gates get
          their own simple lock modal instead of the task drawer. */}
      {openItem?.item_type === "checkpoint" ? (
        <CheckpointDrawer
          key={openItem.id} item={openItem} items={items} assignmentId={assignmentId}
          hasTeam={!!checklist.team_name}
          onClose={() => setOpenItemId(null)} onChanged={invalidate}
        />
      ) : (
        <TaskDrawer
          key={openItem?.id ?? "closed"} item={openItem} items={items} assignmentId={assignmentId} teamName={checklist.team_name}
          teamCode={checklist.team_code ?? null} teamMembers={checklist.team_members ?? []}
          teamFinalLocked={!!checklist.team_final_locked_at}
          onClose={() => setOpenItemId(null)} onChanged={invalidate}
        />
      )}

      {lockedItem && (
        <LockedTaskModal
          item={lockedItem}
          items={items}
          onClose={() => setLockedItem(null)}
          onGoToBlocker={(blockerId) => {
            const blocker = items.find((i) => i.id === blockerId);
            if (blocker) openItemById(blocker);
          }}
        />
      )}
    </div>
  );
}
