import { Flag } from "lucide-react";
import type { CheckpointGroup } from "./roadmap";

/** Design spec §"Final gate bar" — pinned to the bottom of the board
 * (`margin-top:auto` on desktop). Summarizes the checklist's last
 * checkpoint group rather than hard-coding "Checkpoint 3" — a program
 * with no checkpoint labels at all still gets a generic "Final gate"
 * reading over its last few required tasks. */
export function FinalGateBar({ groups, allDone }: { groups: CheckpointGroup[]; allDone: boolean }) {
  if (groups.length === 0) return null;
  const last = groups[groups.length - 1];
  const previous = groups.length > 1 ? groups[groups.length - 2] : null;
  const taskCount = last.items.length;

  const eyebrow = last.label ? `FINAL GATE · ${last.label.toUpperCase()}` : "FINAL GATE";
  const condition = allDone
    ? "All clear — nice work"
    : previous?.label
    ? `Powers on when ${previous.label} is clear`
    : "Complete every task above to finish";

  return (
    <div className="mt-6 md:mt-auto flex items-center gap-3 rounded-2xl bg-card px-4 py-3.5 border border-border">
      <div className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <Flag size={18} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[9px] font-bold uppercase tracking-[0.08em] text-primary">{eyebrow}</div>
        <div className="font-display text-[16px] font-bold text-foreground truncate">
          Review &amp; submit — {taskCount} task{taskCount === 1 ? "" : "s"}
        </div>
      </div>
      <div className="hidden sm:block shrink-0 text-xs text-muted-foreground text-right max-w-[220px]">{condition}</div>
    </div>
  );
}
