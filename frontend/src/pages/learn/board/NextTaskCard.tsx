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
      className="flex flex-col md:flex-row md:items-center gap-4 rounded-2xl p-4 md:py-4 md:px-[18px]"
      style={{
        background: "var(--board-next-bg)",
        boxShadow: "inset 0 0 0 1.5px var(--board-live-ring), 0 0 30px var(--board-live-glow)",
      }}
    >
      <div className="flex items-center gap-3 md:gap-4 min-w-0 flex-1">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary/15" style={{ color: "var(--board-live-ink)" }}>
          <Target size={20} />
        </div>
        <div className="min-w-0">
          <div className="text-[10px] font-bold uppercase tracking-[0.08em]" style={{ color: "var(--board-live-ink)" }}>
            Your next task
          </div>
          <div className="font-display text-[19px] font-bold tracking-tight text-foreground truncate">{item.title}</div>
          {meta && <div className="text-xs text-muted-foreground truncate">{meta}</div>}
        </div>
      </div>

      <div className="flex flex-col items-stretch md:items-end gap-1 shrink-0">
        <Button
          onClick={onStart}
          className="h-10 md:h-[42px] w-full md:w-auto rounded-[11px] font-display text-[13px] font-bold"
        >
          <span className="flex items-center gap-1.5">
            {/* eslint-disable-next-line react-hooks/static-components -- iconForItem is a fixed-lookup, not a per-render component construction */}
            <Icon size={14} /> Start task →
          </span>
        </Button>
        {opensGuidelineFirst && (
          <span className="text-[11px] text-muted-foreground text-center md:text-right">Opens the guideline first</span>
        )}
      </div>
    </div>
  );
}
