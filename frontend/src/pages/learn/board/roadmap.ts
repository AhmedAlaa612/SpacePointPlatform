import {
  BatteryCharging, BookOpen, Calendar, Cpu, FileText, HelpCircle, Layout, Link2, Lock, Rocket, Scale, Target, Upload,
  ClipboardCheck, ClipboardList, type LucideIcon,
} from "lucide-react";
import type { LmsProgramChecklistItem } from "@/api/lms";

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
  if (item.locked) return "locked";
  if (itemDone(item)) return "cleared";
  return "live";
}

/** Every Madar design-phase key a `mission_run` item's `mission_step_key`
 * can carry — mirrors the backend's MISSION_STEP_KEYS. */
export const MISSION_STEP_KEYS = [
  "setup", "components", "conops", "power_budget",
  "mass_budget", "data_budget", "link_budget", "cost_budget", "report",
] as const;
export type MissionStepKey = (typeof MISSION_STEP_KEYS)[number];

export const MISSION_STEP_LABELS: Record<MissionStepKey, string> = {
  setup: "Name the mission", components: "Components", conops: "CONOPS",
  power_budget: "Power budget", mass_budget: "Mass budget",
  data_budget: "Data budget", link_budget: "Link budget", cost_budget: "Cost budget",
  report: "Report",
};

/** mission_step_key → DesignMissionPage's own tab `value` — the board
 * tile's deep link target (`?phase=<tab>`). Everything is 1:1 except the
 * renamed budget tabs and `report` → `dashboard`. */
export function stepKeyToDesignTab(stepKey: string): string {
  const map: Record<string, string> = {
    power_budget: "power", mass_budget: "mass", report: "dashboard",
  };
  return map[stepKey] ?? stepKey;
}

export const STEP_ICON: Record<MissionStepKey, LucideIcon> = {
  setup: Target, components: Cpu, conops: Layout, power_budget: BatteryCharging,
  mass_budget: Scale, data_budget: FileText,
  link_budget: Link2, cost_budget: FileText, report: ClipboardList,
};

const ITEM_TYPE_ICON: Record<LmsProgramChecklistItem["item_type"], LucideIcon> = {
  course: BookOpen, mission_run: Rocket, external_link: Link2, submission: Upload,
  pdf: FileText, manual: ClipboardCheck, session: Calendar, quiz: HelpCircle,
};

/** Locked tiles always render `lock` regardless of type (README: "locked
 * tiles always render lock"). */
export function iconForItem(item: LmsProgramChecklistItem): LucideIcon {
  if (item.locked) return Lock;
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
export function checklistItemToTile(item: LmsProgramChecklistItem): BoardTile {
  return {
    id: item.id, title: item.title, state: tileState(item), icon: iconForItem(item),
    optional: item.optional, meta: tileMeta(item),
  };
}

export type NavTarget =
  | { kind: "course"; courseId: string }
  | { kind: "design"; attemptId: string; phase?: string }
  | { kind: "operate"; attemptId: string }
  | { kind: "mission"; missionId: string }
  | { kind: "external"; url: string }
  | { kind: "quiz"; itemId: string }
  | { kind: "drawer" } // submission / pdf / manual / session — open the task drawer, no direct nav
  | { kind: "none" };

/** What clicking a *live* tile does — direct navigation, no intermediate
 * screen (flow rule 1). A locked tile is a no-op (flow rule 2), enforced
 * by callers checking `item.locked` before calling this, not here. */
export function navTargetFor(item: LmsProgramChecklistItem): NavTarget {
  if (item.item_type === "course" && item.course_id) return { kind: "course", courseId: item.course_id };
  if (item.item_type === "mission_run" && item.mission_attempt_id) {
    if (item.mission_kind === "design") {
      return {
        kind: "design", attemptId: item.mission_attempt_id,
        phase: item.mission_step_key ? stepKeyToDesignTab(item.mission_step_key) : undefined,
      };
    }
    if (item.mission_kind === "operate") return { kind: "operate", attemptId: item.mission_attempt_id };
    if (item.mission_id) return { kind: "mission", missionId: item.mission_id };
  }
  if (item.item_type === "external_link" && item.external_url) return { kind: "external", url: item.external_url };
  if (item.item_type === "quiz") return { kind: "quiz", itemId: item.id };
  if (item.item_type === "submission" || item.item_type === "pdf" || item.item_type === "manual" || item.item_type === "session") {
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
