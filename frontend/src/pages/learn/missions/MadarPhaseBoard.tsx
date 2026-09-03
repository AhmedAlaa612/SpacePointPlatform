import { Rocket } from "lucide-react";
import { TileField } from "../board/TileField";
import { STEP_ICON, type BoardTile, type MissionStepKey } from "../board/roadmap";
import type { DesignState } from "@/api/missionsDesign";
import { DESIGN_TABS, designStepKeyForTab, tabBlockInfo, tabIsDone } from "../DesignMissionPage";

/** Madar's own phase board (2026-09) — the exact same tile/wire components
 * the checklist Roadmap board uses (`board/TileField.tsx`, `TaskTile.tsx`,
 * `TraceLayer.tsx`), not a look-alike: the boss's own ask was "literally
 * the same thing, same wires, same card style" after an earlier pass built
 * a custom (if similarly-styled) tile grid. `TileField` only needs each
 * item reduced to a `BoardTile` (id/title/state/icon/meta) — this is that
 * reduction for `DESIGN_TABS`, the same job `roadmap.ts`'s own
 * `checklistItemToTile` does for `LmsProgramChecklistItem`.
 *
 * A blocked tile reads as fully "locked" here (inert, matching the
 * checklist board's own rule) — the tab strip this replaced only ever
 * soft-blocked (D2: explain the order, don't enforce it), but full parity
 * with the checklist's tile behavior is the point of this pass. */
export function MadarPhaseBoard({
  state, visibleTabs, confirmedSteps, onOpenPhase,
}: {
  state: DesignState;
  visibleTabs: typeof DESIGN_TABS;
  confirmedSteps: Record<string, boolean>;
  onOpenPhase: (tab: string) => void;
}) {
  const tiles: BoardTile[] = visibleTabs.map((t) => {
    const { blocked } = tabBlockInfo(state, t);
    const valid = tabIsDone(state, t.value);
    const cleared = t.value === "dashboard" ? valid : confirmedSteps[t.value] && valid;
    const stepKey = (t.value === "dashboard" ? "report" : designStepKeyForTab(t.value)) as MissionStepKey;
    return {
      id: t.value,
      title: t.label,
      state: blocked ? "locked" : cleared ? "cleared" : "live",
      icon: STEP_ICON[stepKey] ?? Rocket,
      meta: !blocked && !cleared && valid ? "Ready to confirm" : null,
    };
  });
  const liveTile = tiles.find((tile) => tile.state === "live") ?? null;

  return (
    <TileField
      items={tiles}
      liveTaskId={liveTile?.id ?? null}
      onOpenItem={(tile) => onOpenPhase(tile.id)}
    />
  );
}
