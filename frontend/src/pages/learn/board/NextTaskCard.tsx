import { Target } from "lucide-react";
import type { LmsProgramChecklistItem } from "@/api/lms";
import { Button } from "@/components/ui/button";
import { iconForItem, MISSION_STEP_LABELS, type MissionStepKey } from "./roadmap";

function metaLine(item: LmsProgramChecklistItem): string {
  const parts: string[] = [];
  if (item.checkpoint_label) parts.push(item.checkpoint_label);
  if (item.item_type === "mission_run" && item.mission_step_key) {
    parts.push(`Madar · ${MISSION_STEP_LABELS[item.mission_step_key as MissionStepKey] ?? item.mission_step_key}`);
  }
  if (item.deadline_at) {
    parts.push(`due ${new Date(item.deadline_at).toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" })}`);
  }
  return parts.join(" · ");
}

/** Design spec §"Next-task card" — a second entry point to the exact same
 * tile TaskField marks live ("Always mirrors the single live tile — two
 * entry points, one target."). Renders nothing when there's no live task
 * (checklist empty, or fully cleared). */
export function NextTaskCard({ item, onStart }: { item: LmsProgramChecklistItem | null; onStart: () => void }) {
  if (!item) return null;
  const Icon = iconForItem(item);
  const meta = metaLine(item);
  const opensGuidelineFirst = !!item.guideline_kind;

  return (
    <div
      className="flex flex-col md:flex-row md:items-center gap-4 rounded-2xl p-4 md:py-4 md:px-[18px] border border-border/80 dark:border-[#a880ff]/30 bg-card/90 dark:bg-card/40"
      style={{
        boxShadow: "inset 0 0 0 1px var(--board-live-ring, rgba(168, 128, 255, 0.45)), 0 0 24px var(--board-live-glow, rgba(168, 128, 255, 0.15))",
      }}
    >
      <div className="flex items-center gap-3 md:gap-4 min-w-0 flex-1">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-lms-cta-light text-lms-cta dark:text-lms-accent border border-lms-cta-border dark:border-lms-accent-border">
          <Target size={20} />
        </div>
        <div className="min-w-0">
          <div className="text-[10px] font-bold uppercase tracking-[0.1em] text-lms-cta dark:text-lms-accent">
            Your next task
          </div>
          <div className="font-['Outfit'] text-lg sm:text-xl font-bold tracking-tight text-foreground truncate">{item.title}</div>
          {meta && <div className="text-xs text-muted-foreground truncate">{meta}</div>}
        </div>
      </div>

      <div className="flex flex-col items-stretch md:items-end gap-1 shrink-0">
        <button
          type="button"
          onClick={onStart}
          className="lms-btn-primary h-10 md:h-[42px] w-full md:w-auto px-5 rounded-xl font-['Outfit'] text-xs sm:text-sm font-bold flex items-center justify-center gap-1.5 cursor-pointer"
        >
          <Icon size={14} /> Start task →
        </button>
        {opensGuidelineFirst && (
          <span className="text-[11px] text-muted-foreground text-center md:text-right">Opens the guideline first</span>
        )}
      </div>
    </div>
  );
}
