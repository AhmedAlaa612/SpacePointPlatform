import { CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DesignState } from "@/api/missionsDesign";
import { DESIGN_TABS, tabBlockInfo, tabIsDone } from "../DesignMissionPage";

/** Madar's own phase board (2026-09) — mirrors the Roadmap board's tile
 * grid + drawer pattern (the boss's own reference: "the task journey in
 * the checklist"), swapped onto Madar's nine design phases. Not a shared
 * component with the checklist's `TileField`/`TraceLayer`: those are built
 * around `LmsProgramChecklistItem`'s locked/status shape and a longer
 * serpentine layout — different enough from `DESIGN_TABS`' `needs`-graph
 * blocking that forcing reuse would bend both. Matching card styling and
 * status vocabulary ("Cleared"/"Start now →") gets the "same design"
 * result without warping either component to fit the other.
 *
 * A blocked tile still opens — same as the tab strip this replaces never
 * actually disabled a blocked tab either (D2: explain the order, don't
 * enforce it; the write endpoint is what enforces an instructor gate). */
export function MadarPhaseBoard({
  state, visibleTabs, confirmedSteps, onOpenPhase,
}: {
  state: DesignState;
  visibleTabs: typeof DESIGN_TABS;
  confirmedSteps: Record<string, boolean>;
  onOpenPhase: (tab: string) => void;
}) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      {visibleTabs.map((t) => {
        const { blocked, hint } = tabBlockInfo(state, t);
        const valid = tabIsDone(state, t.value);
        const confirmed = t.value === "dashboard" ? valid : confirmedSteps[t.value] && valid;
        const status = confirmed ? "cleared" : valid ? "ready" : blocked ? "blocked" : "open";
        return (
          <button
            key={t.value}
            type="button"
            title={blocked ? hint : undefined}
            onClick={() => onOpenPhase(t.value)}
            className={cn(
              "flex flex-col items-start gap-2 rounded-2xl ring-1 p-4 text-left transition-colors cursor-pointer",
              status === "cleared" ? "ring-emerald-500/40 bg-emerald-500/5 hover:bg-emerald-500/10" :
              status === "ready" ? "ring-amber-500/30 bg-amber-500/5 hover:bg-amber-500/10" :
              "ring-border hover:bg-foreground/5",
            )}
          >
            <div className="flex w-full items-center justify-between gap-1.5">
              <span className={cn(
                "flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold shrink-0",
                status === "cleared" ? "bg-emerald-500/15 text-emerald-500" : "bg-primary/10 text-primary",
              )}>
                {status === "cleared" && <CheckCircle2 size={15} />}
              </span>
              {blocked && <span className="text-[9px] font-bold text-amber-500">!</span>}
            </div>
            <span className="text-sm font-semibold text-foreground">{t.label}</span>
            <span className={cn(
              "text-xs font-medium",
              status === "cleared" ? "text-emerald-600 dark:text-emerald-500" :
              status === "ready" ? "text-amber-600 dark:text-amber-400" :
              "text-muted-foreground",
            )}>
              {status === "cleared" ? "Cleared" : status === "ready" ? "Ready to confirm" : "Start now →"}
            </span>
          </button>
        );
      })}
    </div>
  );
}
