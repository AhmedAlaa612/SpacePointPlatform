import type { LmsProgramChecklistItem } from "@/api/lms";
import { cn } from "@/lib/utils";
import { actionLineText, iconForItem, tileState, MISSION_STEP_LABELS, type MissionStepKey } from "./roadmap";

const RING_GLOW: Record<ReturnType<typeof tileState>, string> = {
  cleared: "inset 0 0 0 1.5px var(--board-cleared-ring), 0 0 22px var(--board-cleared-glow)",
  live: "inset 0 0 0 1.5px var(--board-live-ring), 0 0 22px var(--board-live-glow)",
  locked: "inset 0 0 0 1px var(--board-locked-ring)",
};

const INK: Record<ReturnType<typeof tileState>, string> = {
  cleared: "var(--board-cleared-ink)", live: "var(--board-live-ink)", locked: "var(--board-locked-ink)",
};

function tileMeta(item: LmsProgramChecklistItem): string | null {
  if (item.item_type === "mission_run" && item.mission_step_key) {
    return MISSION_STEP_LABELS[item.mission_step_key as MissionStepKey] ?? null;
  }
  if (item.deadline_at) {
    return `Due ${new Date(item.deadline_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
  }
  if (item.item_type === "session" && item.session_date) {
    return new Date(item.session_date).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  }
  return item.checkpoint_label;
}

/** One roadmap tile — 158×136 desktop / 200×104 mobile per the design
 * spec's "Tile anatomy". State (cleared/live/locked) drives the ring,
 * glow, ink colour and cursor; `isPulsing` (only the single computed
 * live task) adds the dark-mode pulse. Locked tiles are `aria-disabled`
 * and inert — flow rule 2, "not-powered tile → no-op": no handler, no
 * alert, the card body just states the condition. */
export function TaskTile({
  item, number, isPulsing, onOpen, tileRef,
}: {
  item: LmsProgramChecklistItem;
  number: number;
  isPulsing: boolean;
  onOpen: () => void;
  tileRef: (el: HTMLDivElement | null) => void;
}) {
  const state = tileState(item);
  // iconForItem always returns one of a small fixed set of stable lucide
  // component references (never constructs one) — a false positive for
  // this rule, same as any icon-lookup-by-key idiom (disabled at the JSX
  // usage site below, where the rule actually reports).
  const Icon = iconForItem(item);
  const interactive = state !== "locked";
  const meta = tileMeta(item);

  return (
    <div
      ref={tileRef}
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : -1}
      aria-disabled={!interactive}
      onClick={interactive ? onOpen : undefined}
      onKeyDown={interactive ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen(); } } : undefined}
      className={cn(
        "relative z-[1] flex w-[200px] h-[104px] md:w-[158px] md:h-[136px] shrink-0 flex-col rounded-2xl p-3 md:p-[13px] box-border bg-card transition-transform transition-shadow duration-150 ease-in-out",
        interactive ? "cursor-pointer hover:-translate-y-1" : "cursor-default",
        isPulsing && "animate-board-pulse",
      )}
      style={{ boxShadow: RING_GLOW[state] }}
    >
      <div className="flex items-center justify-between">
        <div
          className="flex h-[26px] w-[26px] md:h-[30px] md:w-[30px] items-center justify-center rounded-[10px]"
          style={{ backgroundColor: "hsl(var(--muted))", color: INK[state] }}
        >
          {/* eslint-disable-next-line react-hooks/static-components -- iconForItem is a fixed-lookup, not a per-render component construction */}
          <Icon size={14} />
        </div>
        <div
          className={cn(
            "flex h-[22px] w-[22px] items-center justify-center rounded-full font-display text-[11px] font-bold",
            state === "live" ? "bg-primary/15" : "bg-transparent",
          )}
          style={{ color: INK[state] }}
        >
          {number}
        </div>
      </div>

      <div
        className="mt-2 md:mt-2.5 font-display text-[12px] font-bold leading-[1.25] tracking-[-0.01em] text-foreground line-clamp-2"
      >
        {item.title}
      </div>

      {meta && <div className="hidden md:block mt-auto text-[10px] text-muted-foreground truncate">{meta}</div>}

      <div
        className={cn("mt-auto md:mt-1.5 text-[10px] font-bold tracking-[0.03em]", state === "locked" && "flex items-center gap-1")}
        style={{ color: INK[state] }}
      >
        {actionLineText(state)}
      </div>
    </div>
  );
}
