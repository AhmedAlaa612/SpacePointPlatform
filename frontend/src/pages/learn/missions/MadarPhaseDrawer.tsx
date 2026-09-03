import { CheckCircle2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DesignState } from "@/api/missionsDesign";
import {
  DESIGN_TABS, tabIsDone,
  SetupTab, ComponentsTab, ConopsTab, DataBudgetTab, PowerBudgetTab, EnergyBudgetTab, LinkBudgetTab,
  MassBudgetTab, CostBudgetTab, DashboardTab,
} from "../DesignMissionPage";

/** The side panel for one Madar phase (2026-09) — sibling of the
 * checklist's `TaskDrawer.tsx` (same scrim + fixed-panel + mobile-sheet
 * mechanics), except the desktop panel reaches `LearnSidebar`'s own left
 * nav (`left-64`, matching its own `w-64`) instead of a fixed width —
 * the boss's own ask, "opens till it touches the left sidebar". Mobile has
 * no left-nav concept (bottom tab bar instead), so it stays a full-width
 * bottom sheet, same as `TaskDrawer`'s own mobile treatment.
 *
 * Renders whichever phase's existing tab component unchanged — this panel
 * is only the shell (header, one Complete CTA); every phase's actual
 * editing UI is untouched from the old tab-strip layout. */
export function MadarPhaseDrawer({
  tab, state, attemptId, onClose, onSaved, onGoToTab, confirmedSteps, confirmingTab, confirmError, onConfirm,
}: {
  tab: string | null;
  state: DesignState;
  attemptId: string;
  onClose: () => void;
  onSaved: (s: DesignState) => void;
  onGoToTab: (tab: string) => void;
  confirmedSteps: Record<string, boolean>;
  confirmingTab: string | null;
  confirmError: string;
  onConfirm: (tab: string) => void;
}) {
  if (!tab) return null;

  const meta = DESIGN_TABS.find((t) => t.value === tab);
  const confirmed = confirmedSteps[tab];
  const ready = tabIsDone(state, tab);
  const isDashboard = tab === "dashboard";

  const header = (
    <div className="flex items-center justify-between gap-2 shrink-0">
      <div className="text-base font-extrabold uppercase tracking-[0.06em] text-primary truncate">
        Madar &middot; {meta?.label ?? "Step"}
      </div>
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
      >
        <X size={22} strokeWidth={2.75} />
      </button>
    </div>
  );

  const content = (
    <>
      {tab === "setup" && <SetupTab state={state} onSaved={onSaved} />}
      {tab === "components" && <ComponentsTab state={state} attemptId={attemptId} onChanged={onSaved} />}
      {tab === "conops" && <ConopsTab state={state} attemptId={attemptId} onSaved={onSaved} />}
      {tab === "data" && <DataBudgetTab state={state} attemptId={attemptId} onSaved={onSaved} />}
      {tab === "power" && <PowerBudgetTab state={state} attemptId={attemptId} onSaved={onSaved} />}
      {tab === "energy" && <EnergyBudgetTab state={state} attemptId={attemptId} onSaved={onSaved} />}
      {tab === "link" && <LinkBudgetTab state={state} attemptId={attemptId} onSaved={onSaved} />}
      {tab === "mass" && <MassBudgetTab state={state} attemptId={attemptId} onSaved={onSaved} />}
      {tab === "cost" && <CostBudgetTab state={state} attemptId={attemptId} onSaved={onSaved} />}
      {isDashboard && <DashboardTab state={state} onGoToTab={onGoToTab} />}
    </>
  );

  // Report/Downlink stays purely validity-driven — no self-check of its
  // own, matching the backend's own exclusion of "report" from
  // CONFIRMABLE_STEP_KEYS (routers/missions/design.py).
  const footer = !isDashboard && (
    <div className="shrink-0 pt-4 flex flex-col items-center gap-2.5 border-t border-border bg-card">
      {confirmError && <p className="text-xs text-destructive text-center">{confirmError}</p>}
      <Button
        variant={confirmed ? "outline" : "default"}
        disabled={!ready || confirmed || confirmingTab === tab}
        onClick={() => onConfirm(tab)}
        className="h-14 px-16 text-base font-semibold rounded-lg transition-transform duration-150 hover:scale-[1.03] active:scale-[0.97] hover:shadow-[0_10px_28px_-10px_hsl(var(--primary)/0.55)]"
      >
        {confirmed ? <><CheckCircle2 className="size-5" /> Completed</> : confirmingTab === tab ? "Confirming..." : "Complete this step"}
      </Button>
    </div>
  );

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/55 transition-opacity"
        style={{ background: "var(--drawer-scrim, rgba(5,3,10,0.55))" }}
        onClick={onClose}
      />
      {/* Header and the Complete CTA are outside the scroll area on every
          phase — only the phase's own content scrolls between them, so the
          CTA stays put (sticky) instead of scrolling out of reach on a
          long tab. */}
      <div className="hidden md:flex fixed inset-y-0 right-0 left-64 z-50 flex-col bg-card p-8 gap-5 shadow-[-28px_0_60px_-30px_rgba(23,17,31,0.6)]">
        {header}
        <div className="flex-1 min-h-0 overflow-y-auto">{content}</div>
        {footer}
      </div>
      <div className="md:hidden fixed inset-x-0 bottom-0 z-50 flex flex-col rounded-t-[22px] bg-card px-5 pt-3 pb-6 gap-4 max-h-[86vh]">
        <div className="mx-auto h-1.5 w-12 rounded-full bg-border shrink-0" />
        {header}
        <div className="flex-1 min-h-0 overflow-y-auto">{content}</div>
        {footer}
      </div>
    </>
  );
}
