import { useEffect, useState } from "react";
import { Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { actionLineText, type BoardTile, type TileState } from "./roadmap";
import { formatCountdown } from "./FinalGateBar";

const RING_GLOW: Record<TileState, string> = {
  cleared: "inset 0 0 0 1.5px var(--board-cleared-ring), 0 0 22px var(--board-cleared-glow)",
  live: "inset 0 0 0 1.5px var(--board-live-ring), 0 0 22px var(--board-live-glow)",
  locked: "inset 0 0 0 1px var(--board-locked-ring)",
};

const INK: Record<TileState, string> = {
  cleared: "var(--board-cleared-ink)", live: "var(--board-live-ink)", locked: "var(--board-locked-ink)",
};

/** One roadmap tile — 158×136 desktop / 200×104 mobile per the design
 * spec's "Tile anatomy". State (cleared/live/locked) drives the ring,
 * glow, ink colour and cursor; `isPulsing` (only the single computed
 * live task) adds the dark-mode pulse. Locked tiles are `aria-disabled`
 * and inert — flow rule 2, "not-powered tile → no-op": no handler, no
 * alert, the card body just states the condition.
 *
 * Takes a `BoardTile`, not a raw checklist item — this same component
 * renders both the checklist's Roadmap board and Madar's own phase board
 * (`pages/learn/missions/MadarPhaseBoard.tsx`), each reducing its own
 * domain object to this shape rather than two look-alike tile components. */
export function TaskTile({
  tile, number, isPulsing, onOpen, tileRef,
}: {
  tile: BoardTile;
  number: number;
  isPulsing: boolean;
  onOpen: () => void;
  tileRef: (el: HTMLDivElement | null) => void;
}) {
  const state = tile.state;
  const Icon = tile.icon;
  const isLocked = state === "locked";
  const meta = tile.meta;
  // Checkpoint gates reuse the final gate's animated beacon border
  // (FinalGateBar's `gate-beacon-border`, mounted on the same board) so a
  // gate reads as a milestone, not a plain task. Only the reachable one
  // glows — locked/cleared gates keep their own state styling.
  const isGate = tile.accent === "checkpoint" && state === "live";
  const isCheckpoint = tile.accent === "checkpoint";

  const activeWindow = tile.timingWindow?.activeWindow;
  const isDeadlinePassed = !!tile.timingWindow?.isDeadlinePassed;

  const [secondsLeft, setSecondsLeft] = useState<number>(() => {
    if (activeWindow?.cutoff_at) {
      const ms = new Date(activeWindow.cutoff_at).getTime() - Date.now();
      return Math.max(0, Math.floor(ms / 1000));
    }
    return Math.max(0, activeWindow?.seconds_remaining ?? 0);
  });

  useEffect(() => {
    if (!activeWindow?.cutoff_at) {
      setSecondsLeft(0);
      return;
    }
    const cutoffMs = new Date(activeWindow.cutoff_at).getTime();
    const update = () => {
      setSecondsLeft(Math.max(0, Math.floor((cutoffMs - Date.now()) / 1000)));
    };
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, [activeWindow?.cutoff_at, activeWindow?.seconds_remaining]);

  return (
    <div
      ref={tileRef}
      role="button"
      tabIndex={0}
      title={isLocked && tile.lockHint ? tile.lockHint : undefined}
      onClick={onOpen}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen(); } }}
      className={cn(
        "relative z-[1] flex w-[200px] h-[104px] md:w-[158px] md:h-[136px] shrink-0 flex-col rounded-2xl p-3 md:p-[13px] box-border bg-card transition-transform transition-shadow duration-150 ease-in-out cursor-pointer hover:-translate-y-1",
        isLocked && "hover:shadow-md",
        isPulsing && "animate-board-pulse",
        isGate && "gate-beacon-border border-[2px]",
      )}
      style={{ boxShadow: RING_GLOW[state] }}
    >
      <div className="flex items-center justify-between">
        <div
          className="flex h-[26px] w-[26px] md:h-[30px] md:w-[30px] items-center justify-center rounded-[10px]"
          style={{ backgroundColor: "hsl(var(--muted))", color: INK[state] }}
        >
          <Icon size={14} />
        </div>
        <div className="flex items-center gap-1">
          {tile.optional && (
            <span className="rounded-full bg-muted px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wide text-muted-foreground">
              Optional
            </span>
          )}
          {activeWindow && state !== "cleared" && !isDeadlinePassed && activeWindow.points !== 0 && (
            <span
              className={cn(
                "rounded-full px-1.5 py-0.5 text-[8px] font-mono font-bold border",
                activeWindow.points > 0
                  ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                  : "bg-rose-500/15 text-rose-400 border-rose-500/30"
              )}
            >
              {activeWindow.points > 0 ? `+${activeWindow.points}` : activeWindow.points}
            </span>
          )}
          <div
            className={cn(
              "flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full font-display text-[11px] font-bold",
              state === "live" ? "bg-primary/15" : "bg-transparent",
            )}
            style={{ color: INK[state] }}
          >
            {number}
          </div>
        </div>
      </div>

      <div
        className="mt-2 md:mt-2.5 font-display text-[12px] font-bold leading-[1.25] tracking-[-0.01em] text-foreground line-clamp-2"
      >
        {tile.title}
      </div>

      {/* Checkpoint countdown line on desktop */}
      {isCheckpoint && state !== "cleared" && (
        isDeadlinePassed ? (
          <div className="hidden md:flex mt-auto text-[10px] font-bold text-rose-400 truncate">
            Deadline passed
          </div>
        ) : activeWindow && secondsLeft > 0 ? (
          <div className="hidden md:flex items-center gap-1 mt-auto text-[10px] font-mono font-bold text-primary truncate">
            <Clock size={10} className="shrink-0 text-primary" />
            <span className="truncate">{formatCountdown(secondsLeft)}</span>
          </div>
        ) : null
      )}

      {meta && !(isCheckpoint && (activeWindow || isDeadlinePassed)) && (
        <div className="hidden md:block mt-auto text-[10px] text-muted-foreground truncate">{meta}</div>
      )}

      {/* Desktop action line */}
      <div
        className={cn(
          "hidden md:block text-[10px] font-bold tracking-[0.03em]",
          isCheckpoint && state !== "cleared" && (activeWindow || isDeadlinePassed) ? "mt-0.5" : "mt-auto md:mt-1.5",
          state === "locked" && "flex items-center gap-1"
        )}
        style={{ color: INK[state] }}
      >
        {isGate ? "Review gate →" : actionLineText(state)}
      </div>

      {/* Mobile action line / countdown */}
      <div className="md:hidden mt-auto">
        {isCheckpoint && state !== "cleared" && isDeadlinePassed ? (
          <div className="flex items-center justify-between text-[10px] font-bold">
            <span className="text-rose-400">Deadline passed</span>
            <span style={{ color: INK[state] }}>Review →</span>
          </div>
        ) : isCheckpoint && state !== "cleared" && activeWindow && secondsLeft > 0 ? (
          <div className="flex items-center justify-between text-[10px] font-bold">
            <span className="font-mono text-primary flex items-center gap-1 truncate max-w-[125px]">
              <Clock size={10} className="shrink-0" />
              <span className="truncate">{formatCountdown(secondsLeft)}</span>
            </span>
            <span className="shrink-0" style={{ color: INK[state] }}>Review →</span>
          </div>
        ) : (
          <div
            className={cn("text-[10px] font-bold tracking-[0.03em]", state === "locked" && "flex items-center gap-1")}
            style={{ color: INK[state] }}
          >
            {isGate ? "Review gate →" : actionLineText(state)}
          </div>
        )}
      </div>
    </div>
  );
}
