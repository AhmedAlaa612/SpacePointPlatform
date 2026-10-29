import {
  BatteryCharging, BookOpen, Calendar, Cpu, FileText, Flag, HelpCircle, Image, Layout, Link2, Lock, Rocket, Scale, Target, Upload,
  ClipboardCheck, ClipboardList, Users, Gamepad2, type LucideIcon,
} from "lucide-react";
import type { LmsProgramChecklistItem } from "@/api/lms";
import type { CheckpointTimingWindowInfo, SubmissionWindowItem } from "@/api/competitions";

/** Pure helpers shared by every board surface (RoadmapBoard, TaskTile,
 * NextTaskCard, FinalGateBar, TraceLayer, TaskDrawer) — one place that
 * decides a tile's visual state, icon, and navigation target so the five
 * flow rules (design spec §"Interactions & Behavior") are enforced
 * identically everywhere they matter, not re-derived per component. */

export type TileState = "cleared" | "live" | "locked";

/** What `TaskTile`/`TileField`/`TraceLayer` actually need to render one
 * tile and one wire — reduced away from `LmsProgramChecklistItem` so
 * those three components work for any board, not just the checklist's.
 * Madar's own phase board (`pages/learn/missions/MadarPhaseBoard.tsx`)
 * builds this same shape from `DESIGN_TABS` instead of a checklist item —
 * "the same wires, the same card style" for both boards means both
 * literally render through these same three components, not two
 * look-alike implementations. */
export interface BoardTile {
  id: string;
  title: string;
  state: TileState;
  icon: LucideIcon;
  optional?: boolean;
  meta?: string | null;
  /** Set for checkpoint gates so the tile renders the gate glow. */
  accent?: "checkpoint";
  /** Explains why this tile is locked and what to complete to unlock it. */
  lockHint?: string;
  timingWindow?: {
    activeWindow: (SubmissionWindowItem & { seconds_remaining: number; is_active: boolean }) | null;
    isDeadlinePassed?: boolean;
  };
}

export function itemDone(item: LmsProgramChecklistItem): boolean {
  return item.status === "done";
}

/** The single live task — first non-optional, not-done, unlocked item in
 * position order. Drives both the next-task card and the one purple trace
 * (design spec: "Always mirrors the single live tile — two entry points,
 * one target."). Optional items are never live themselves (nothing gates
 * on them, so they'd never naturally become "next"); an ungated program
 * (no item has `gated` set) still gets a live tile — pending, unlocked, in
 * position order — same as a gated one. */
export function computeLiveTaskId(items: LmsProgramChecklistItem[]): string | null {
  const ordered = [...items].sort((a, b) => a.position - b.position);
  const next = ordered.find((i) => !i.optional && !itemDone(i) && !i.locked);
  return next?.id ?? null;
}

/** The board's three visual states. Because gating is opt-in *per item*
 * (the client's explicit requirement — never a blanket "lock everything
 * after the current task"), more than one tile can legitimately be
 * unlocked-and-undone at once: an ungated program renders with *every*
 * tile "live" (decision, handoff §4.5 — "an ungated board where everything
 * is live"), not just a single one. Every unlocked, not-done tile gets
 * `"live"` styling (purple ring, clickable); only the one tile matching
 * `computeLiveTaskId` additionally gets the pulse animation and mirrors
 * the next-task card — see TaskTile's own `isPulsing` check. */
export function tileState(item: LmsProgramChecklistItem): TileState {
  if (itemDone(item)) return "cleared";
  if (item.locked) return "locked";
  return "live";
}

/** Every Madar design-phase key a `mission_run` item's `mission_step_key`
 * can carry — mirrors the backend's MISSION_STEP_KEYS. */
export const MISSION_STEP_KEYS = [
  "setup", "components", "conops", "power_budget",
  "mass_budget", "data_budget", "link_budget", "cost_budget", "report", "poster",
] as const;
export type MissionStepKey = (typeof MISSION_STEP_KEYS)[number];

export const MISSION_STEP_LABELS: Record<MissionStepKey, string> = {
  setup: "Name the mission", components: "Components", conops: "CONOPS",
  power_budget: "Power budget", mass_budget: "Mass budget",
  data_budget: "Data budget", link_budget: "Link budget", cost_budget: "Cost budget",
  report: "Report", poster: "Mission poster",
};

/** mission_step_key → DesignMissionPage's own tab `value` — the board
 * tile's deep link target (`?phase=<tab>`). Everything is 1:1 except the
 * renamed budget tabs and `report` → `dashboard`. */
export function stepKeyToDesignTab(stepKey: string): string {
  const map: Record<string, string> = {
    power_budget: "power", mass_budget: "mass", report: "dashboard", poster: "poster",
  };
  return map[stepKey] ?? stepKey;
}

export const STEP_ICON: Record<MissionStepKey, LucideIcon> = {
  setup: Target, components: Cpu, conops: Layout, power_budget: BatteryCharging,
  mass_budget: Scale, data_budget: FileText,
  link_budget: Link2, cost_budget: FileText, report: ClipboardList, poster: Image,
};

const ITEM_TYPE_ICON: Record<LmsProgramChecklistItem["item_type"], LucideIcon> = {
  course: BookOpen, mission_run: Rocket, external_link: Link2, submission: Upload,
  pdf: FileText, manual: ClipboardCheck, session: Calendar, quiz: HelpCircle, team_setup: Users,
  checkpoint: Flag, arcade_game: Gamepad2,
};

/** Locked tiles always render `lock` regardless of type (README: "locked
 * tiles always render lock"). Checkpoint gates keep their flag even when
 * locked — the gate identity matters more than the generic padlock here. */
export function iconForItem(item: LmsProgramChecklistItem): LucideIcon {
  if (item.item_type === "checkpoint" && item.status !== "done") return Flag;
  if (!itemDone(item) && item.locked) return Lock;
  if (item.item_type === "mission_run" && item.mission_step_key) {
    return STEP_ICON[item.mission_step_key as MissionStepKey] ?? Rocket;
  }
  return ITEM_TYPE_ICON[item.item_type] ?? Target;
}

/** The action-line copy per state (design spec §"Tile anatomy"). */
export function actionLineText(state: TileState): string {
  if (state === "cleared") return "Cleared";
  if (state === "locked") return "Not powered";
  return "Start now →";
}

/** The tile's small bottom-left meta line — a Madar phase name, a
 * deadline, or a session date, whichever applies. */
export function tileMeta(item: LmsProgramChecklistItem): string | null {
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

/** One checklist item, reduced to what `TileField`/`TaskTile`/`TraceLayer`
 * actually need. */
export function checklistItemToTile(
  item: LmsProgramChecklistItem,
  allItems?: LmsProgramChecklistItem[],
  checkpointTiming?: CheckpointTimingWindowInfo,
): BoardTile {
  const isLocked = item.locked && item.status !== "done";
  return {
    id: item.id, title: item.title, state: tileState(item), icon: iconForItem(item),
    optional: item.optional, meta: tileMeta(item),
    lockHint: isLocked && allItems ? unlockReasonForItem(allItems, item) : undefined,
    ...(item.item_type === "checkpoint" ? { accent: "checkpoint" as const } : {}),
    timingWindow: checkpointTiming
      ? {
          activeWindow: checkpointTiming.active_window,
          isDeadlinePassed: checkpointTiming.is_deadline_passed,
        }
      : undefined,
  };
}

export interface UnlockRequirement {
  type: "checkpoint" | "task" | "generic";
  blockerTitle: string;
  message: string;
}

/** Returns structured info about what blocks this item from unlocking. */
export function unlockRequirementDetails(
  items: LmsProgramChecklistItem[], item: LmsProgramChecklistItem,
): UnlockRequirement {
  const ordered = [...items].sort((a, b) => a.position - b.position);
  const targetIdx = ordered.findIndex((i) => i.id === item.id);
  if (targetIdx === -1) {
    return {
      type: "generic",
      blockerTitle: "Earlier tasks",
      message: "Complete earlier required tasks on the checklist to unlock this step.",
    };
  }

  // Check 1: An earlier uncompleted checkpoint gate hard-locks everything after it
  const blockingCheckpoint = ordered
    .slice(0, targetIdx)
    .reverse()
    .find((i) => i.item_type === "checkpoint" && i.status !== "done");

  if (blockingCheckpoint) {
    return {
      type: "checkpoint",
      blockerTitle: blockingCheckpoint.title,
      message: `Your team must lock the checkpoint "${blockingCheckpoint.title}" before this section becomes available.`,
    };
  }

  // Check 2: Preceding task blocking a gated item
  if (item.gated) {
    const blockingTask = ordered
      .slice(0, targetIdx)
      .find((i) => !i.optional && i.item_type !== "team_setup" && i.status !== "done");
    if (blockingTask) {
      return {
        type: "task",
        blockerTitle: blockingTask.title,
        message: `Complete "${blockingTask.title}" first to unlock this step.`,
      };
    }
  }

  // Check 3: Checkpoint waiting for earlier checkpoint
  if (item.item_type === "checkpoint") {
    const earlierCp = ordered
      .slice(0, targetIdx)
      .reverse()
      .find((i) => i.item_type === "checkpoint" && i.status !== "done");
    if (earlierCp) {
      return {
        type: "checkpoint",
        blockerTitle: earlierCp.title,
        message: `Your team must lock the checkpoint "${earlierCp.title}" first.`,
      };
    }
  }

  return {
    type: "generic",
    blockerTitle: "Earlier tasks",
    message: "Complete earlier required tasks on the roadmap to unlock this step.",
  };
}

/** True once this item sits *above* a locked checkpoint on its team's
 * checklist — the client-side mirror of the backend's `team_section_frozen`
 * (services/lms/program.py). Only team-scoped, non-checkpoint items freeze;
 * only a done, non-optional checkpoint below this item counts; no team (solo
 * student) never freezes. Used to hide submit/complete actions and show the
 * neutral "locked for your team" notice instead of letting the write 409. */
export function isSectionFrozen(
  items: LmsProgramChecklistItem[], item: LmsProgramChecklistItem, hasTeam: boolean,
): boolean {
  if (!hasTeam) return false;
  if (item.scope !== "team") return false;
  if (item.item_type === "checkpoint") return false;
  return items.some(
    (c) =>
      c.item_type === "checkpoint" &&
      !c.optional &&
      c.status === "done" &&
      c.position > item.position,
  );
}

/** When an item is locked, returns a clear human-readable explanation of
 * what must be completed to unlock it (e.g. "Complete 'Step Name' first"). */
export function unlockReasonForItem(
  items: LmsProgramChecklistItem[], item: LmsProgramChecklistItem,
): string {
  if (!item.locked) return "";
  return unlockRequirementDetails(items, item).message;
}

/** A checkpoint gate's own section: required team-scoped items after the
 * previous checkpoint (or the start) and before this gate, in position
 * order. Mirrors the backend's `checkpoint_lock_readiness` slice —
 * individual items and team_setup never block the lock, so they're excluded here too. */
export function checkpointSectionItems(
  items: LmsProgramChecklistItem[], checkpointId: string,
): LmsProgramChecklistItem[] {
  const ordered = [...items].sort((a, b) => a.position - b.position);
  const idx = ordered.findIndex((i) => i.id === checkpointId);
  if (idx === -1) return [];
  let start = 0;
  for (let i = idx - 1; i >= 0; i--) {
    if (ordered[i].item_type === "checkpoint") { start = i + 1; break; }
  }
  return ordered.slice(start, idx).filter(
    (i) => !i.optional && i.scope === "team" && i.item_type !== "checkpoint" && i.item_type !== "team_setup",
  );
}

export type NavTarget =
  | { kind: "course"; courseId: string }
  | { kind: "design"; attemptId: string; phase?: string }
  | { kind: "operate"; attemptId: string }
  | { kind: "mission"; missionId: string }
  | { kind: "external"; url: string }
  | { kind: "quiz"; itemId: string }
  | { kind: "arcade_game"; gameKey: string; mode: string; itemId: string }
  | { kind: "drawer" } // submission / pdf / manual / session / poster — open the task drawer, no direct nav
  | { kind: "none" };

/** What clicking a *live* tile does — direct navigation, no intermediate
 * screen (flow rule 1). A locked tile is a no-op (flow rule 2), enforced
 * by callers checking `item.locked` before calling this, not here. */
export function navTargetFor(item: LmsProgramChecklistItem): NavTarget {
  if (item.item_type === "mission_run" && item.mission_step_key === "poster") {
    return { kind: "drawer" };
  }
  if (item.item_type === "course" && item.course_id) return { kind: "course", courseId: item.course_id };
  if (item.item_type === "arcade_game" && item.arcade_game_key) {
    return {
      kind: "arcade_game",
      gameKey: item.arcade_game_key,
      mode: item.arcade_game_mode === "engineer" ? "engineer" : "explorer",
      itemId: item.id,
    };
  }
  if (item.item_type === "mission_run") {
    if (item.mission_attempt_id) {
      if (item.mission_kind === "design") {
        return {
          kind: "design", attemptId: item.mission_attempt_id,
          phase: item.mission_step_key ? stepKeyToDesignTab(item.mission_step_key) : undefined,
        };
      }
      if (item.mission_kind === "operate") return { kind: "operate", attemptId: item.mission_attempt_id };
      if (item.mission_id) return { kind: "mission", missionId: item.mission_id };
    }
    if (item.mission_id) return { kind: "mission", missionId: item.mission_id };
  }
  if (item.item_type === "external_link" && item.external_url) return { kind: "external", url: item.external_url };
  if (item.item_type === "quiz") return { kind: "quiz", itemId: item.id };
  if (
    item.item_type === "submission" || item.item_type === "pdf" || item.item_type === "manual"
    || item.item_type === "session" || item.item_type === "team_setup" || item.item_type === "checkpoint"
  ) {
    return { kind: "drawer" };
  }
  return { kind: "none" };
}

/** Whether a tile is directly clickable at all — mirrors LearnChecklist's
 * old `clickable` check for course/mission_run, extended to every type
 * that now has *something* to open (the drawer, if nothing else). Locked
 * tiles are never clickable regardless (flow rule 2), checked separately
 * by callers. */
export function isOpenable(item: LmsProgramChecklistItem): boolean {
  return navTargetFor(item).kind !== "none";
}

export interface CheckpointGroup {
  label: string | null;
  items: LmsProgramChecklistItem[];
}

/** Groups items into consecutive runs sharing the same `checkpoint_label`
 * (position order) — cosmetic grouping only (eyebrow text, the final gate
 * bar's title), never a layout partition: the tile field's serpentine grid
 * always flows as one continuous sequence regardless of these boundaries
 * (see TraceLayer). A checklist with no checkpoint labels at all comes
 * back as a single `{ label: null, items: [...] }` group. */
export function groupByCheckpoint(items: LmsProgramChecklistItem[]): CheckpointGroup[] {
  const ordered = [...items].sort((a, b) => a.position - b.position);
  const groups: CheckpointGroup[] = [];
  for (const item of ordered) {
    const last = groups[groups.length - 1];
    if (last && last.label === item.checkpoint_label) {
      last.items.push(item);
    } else {
      groups.push({ label: item.checkpoint_label, items: [item] });
    }
  }
  return groups;
}

const SCROLL_KEY_PREFIX = "roadmap-board-scroll:";

export function saveBoardScrollPosition(assignmentId: string) {
  try {
    sessionStorage.setItem(`${SCROLL_KEY_PREFIX}${assignmentId}`, String(window.scrollY));
  } catch {
    /* sessionStorage unavailable (private mode, etc.) — scroll restore just no-ops */
  }
}

export function readBoardScrollPosition(assignmentId: string): number | null {
  try {
    const raw = sessionStorage.getItem(`${SCROLL_KEY_PREFIX}${assignmentId}`);
    return raw ? Number(raw) : null;
  } catch {
    return null;
  }
}
