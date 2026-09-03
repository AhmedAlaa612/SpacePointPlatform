import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useSearch, useNavigate, Link } from "@tanstack/react-router";
import { isAxiosError } from "axios";
import { AlertTriangle, Box, CheckCircle2, ChevronRight, Clock, FileText, Layers, Minus, Orbit, Plus, Rocket, Search, ShoppingCart, Trash2, XCircle, Zap } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PdfViewer } from "@/components/documents/PdfViewer";
import DesignHandbookDrawer from "@/components/missions/DesignHandbook";
import PosterTab from "@/components/missions/PosterTab";
import { CompletionCelebration } from "./CompletionCelebration";
import { MadarPhaseBoard } from "./missions/MadarPhaseBoard";
import { MadarPhaseDrawer } from "./missions/MadarPhaseDrawer";
import {
  addDesignComponent, completeDesign, confirmDesignStep, fetchComponentDatasheetUrl, fetchDesignHandbook,
  fetchDesignLibrary, fetchDesignState, joinObjectivePrompts, parseObjectivePrompts, removeDesignComponent,
  saveConops, saveCostBudget, saveDataBudget, saveLinkBudget, saveMassBudget, savePowerBudget, updateDesign,
  OBJECTIVE_PROMPTS,
  type DesignHandbook, type DesignLibraryComponent, type DesignState,
} from "@/api/missionsDesign";

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) return String(detail.message);
  }
  return fallback;
}

/** KB -> the largest whole unit that reads naturally ("1.00 GB" rather than
 * "1048576.00 KB") — everything in the data budget is tracked in KB, but a
 * whole-mission storage figure in raw KB is unreadable. */
function formatKB(kb: number): string {
  if (kb >= 1_048_576) return `${(kb / 1_048_576).toFixed(2)} GB`;
  if (kb >= 1024) return `${(kb / 1024).toFixed(2)} MB`;
  return `${kb.toFixed(2)} KB`;
}

/** Ported verbatim from backend/app/services/missions/design/rf_calc.py — the
 * server never exposes these intermediate values (only the final margin_db/
 * status), so the "detailed calculations" breakdown recomputes them
 * client-side, live, off the same formula. */
function freeSpacePathLossDb(frequencyMhz: number, distanceKm: number): number {
  if (frequencyMhz <= 0 || distanceKm <= 0) return 0;
  const fHz = frequencyMhz * 1e6;
  const dM = distanceKm * 1e3;
  return 20 * Math.log10(dM) + 20 * Math.log10(fHz) - 147.55;
}
function noisePowerDbm(dataRateKbps: number, tSysK = 290.0): number {
  if (dataRateKbps <= 0) return 0;
  const k = 1.380649e-23;
  const bw = dataRateKbps * 1e3;
  const pW = k * tSysK * bw;
  return 10 * Math.log10(pW) + 30;
}

const inputCls = "h-12 px-4 border border-border bg-card text-foreground rounded-xl text-base focus:outline-none focus:border-primary transition-colors w-full";
/** For a number input squeezed into a narrow table cell — inputCls's own
 * px-4 leaves too little room for digits once the cell is only ~80px wide,
 * and appending a conflicting px-* utility after inputCls isn't reliable
 * (Tailwind class-conflict winner depends on generated CSS order, not
 * source order — the same trap that broke the data budget table's column
 * widths). A standalone class list with one utility per property sidesteps
 * that; also drops the native spin buttons, which eat width a 2-3 digit
 * cell can't spare. */
const compactInputCls = "h-10 px-2 border border-border bg-card text-foreground rounded-xl text-sm text-center focus:outline-none focus:border-primary transition-colors w-full [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none";
const labelCls = "text-sm font-semibold uppercase tracking-wide text-muted-foreground";

/** The nine steps, with the dependency between them made visible (D2:
 * explain the order, don't enforce it). `needs` lists the steps whose data
 * this one is computed from — CONOPS feeds four separate budgets, which is
 * the single most important thing to communicate about the sequence. */
export const DESIGN_TABS: {
  value: string; label: string; step?: string; needs?: string[]; blockedHint?: string;
}[] = [
  { value: "setup", label: "Setup" },
  { value: "components", label: "Components", step: "components" },
  {
    value: "conops", label: "CONOPS", step: "conops", needs: ["components"],
    blockedHint: "Complete Components first — the CONOPS matrix is a grid of components against modes.",
  },
  {
    value: "data", label: "Data Budget", step: "data_budget", needs: ["conops"],
    blockedHint: "Complete CONOPS first — data volume is computed from how long each component is on.",
  },
  {
    value: "power", label: "Power Budget", step: "power_budget", needs: ["conops"],
    blockedHint: "Complete CONOPS first — power draw is computed from how long each component is on.",
  },
  {
    value: "energy", label: "Energy", step: "energy_budget", needs: ["power_budget"],
    blockedHint: "Complete the Power Budget first — energy over an orbit is computed from it.",
  },
  {
    value: "link", label: "Link", step: "link_budget", needs: ["components"],
    blockedHint: "Complete Components first.",
  },
  {
    value: "mass", label: "Mass", step: "mass_budget", needs: ["components"],
    blockedHint: "Complete Components first.",
  },
  {
    value: "cost", label: "Cost", step: "cost_budget", needs: ["components"],
    blockedHint: "Complete Components first.",
  },
  { value: "dashboard", label: "Report" },
];

/** Whether one design tab's own step is "closed", by the same signal
 * `CompletionMap` reads — `setup`/`dashboard` aren't real
 * `dashboard.steps` keys (see `DESIGN_TABS`' own `step` field, undefined
 * for both), so they get their own check, matching the backend's
 * `_mission_run_item_done` (services/lms/program.py). */
export function tabIsDone(state: DesignState, tabValue: string): boolean {
  if (tabValue === "setup") return state.design_objective !== null;
  if (tabValue === "dashboard") return state.dashboard.all_valid;
  const stepKey = DESIGN_TABS.find((t) => t.value === tabValue)?.step;
  return !!stepKey && !!state.dashboard.steps[stepKey]?.is_valid;
}

/** Whether one design tab is gated — a data dependency (`needs`) not yet
 * *confirmed*, or an instructor's explicit gate (`step_gates`, backed by a
 * 403 on the write endpoint). Steps gate each other (2026-09): `needs`
 * requires the prerequisite step to be in `state.confirmed_steps`, the same
 * "done, not just started" bar the checklist's own `compute_lock_states`
 * (backend/app/services/lms/program.py) uses — having *some* data in the
 * prerequisite used to be enough to unlock the next phase, which let a
 * half-finished CONOPS silently feed a budget tab. `MadarPhaseBoard`
 * renders a blocked tile fully locked (inert, no click), matching the
 * checklist board's own tile behavior; `DesignMissionPage` also closes a
 * `?phase=` deep link straight back to the board if it names a step that's
 * (still) blocked, so the gate holds regardless of entry point. */
export function tabBlockInfo(state: DesignState, t: (typeof DESIGN_TABS)[number]): { blocked: boolean; hint?: string } {
  const needsBlocked = t.needs?.some((k) => !state.confirmed_steps.includes(k));
  const gateLocked = t.step ? state.step_gates?.[t.step] === false : false;
  return {
    blocked: !!(needsBlocked || gateLocked),
    hint: gateLocked ? "Your instructor hasn't unlocked this step yet." : t.blockedHint,
  };
}

/** Per-step "I'm done here" confirmation (2026-09) — `tabIsDone` alone (e.g.
 * "at least one component added") used to flip a step straight to "done"
 * the moment its bare minimum was met, before the student had actually
 * finished shopping/tuning it. Confirmation is a separate, explicit click,
 * persisted server-side on `Design.confirmed_steps` (POST .../steps/
 * {step_key}/confirm — see routers/missions/design.py's
 * `confirm_design_step`) so it also gates the Roadmap board's own
 * checklist-item completion (`_mission_run_item_done`, services/lms/
 * program.py), not just this page's own display. The backend re-checks
 * `tabIsDone`'s own requirements before accepting a confirmation, so this
 * can't be used to skip validation from either side.
 *
 * `tabValue` (this page's tab id, e.g. "power") and the backend's step key
 * (e.g. "power_budget") differ for three renamed budgets plus "report" —
 * same map `roadmap.ts`'s `stepKeyToDesignTab` uses in the other direction. */
export function designStepKeyForTab(tabValue: string): string {
  if (tabValue === "setup") return "setup";
  return DESIGN_TABS.find((t) => t.value === tabValue)?.step ?? tabValue;
}

/** The design-mission nine-step wizard (P7-5), ported from Madar's eleven
 * HTML pages. One fetch (`DesignState`) drives every tab; each save action
 * re-fetches the whole state so the dashboard is always current — this is
 * a workshop-scale tool, not a high-traffic one, so re-fetching the full
 * state per save is the simple, correct choice over hand-rolled partial
 * updates. */
export default function DesignMissionPage() {
  const { attemptId } = useParams({ strict: false }) as { attemptId: string };
  const search = useSearch({ strict: false }) as { phase?: string; program?: string };
  const navigate = useNavigate();
  const [state, setState] = useState<DesignState | null>(null);
  const [error, setError] = useState("");
  // Which phase's drawer is open — null means the board is showing. Seeded
  // from ?phase= (a Roadmap board Madar tile's deep link, or a checklist
  // item's own deep link) when it names a real tab.
  const [openPhase, setOpenPhaseState] = useState<string | null>(
    () => (search.phase && DESIGN_TABS.some((t) => t.value === search.phase) ? search.phase : null),
  );
  // Keeps the URL in sync so the open phase survives a refresh/share,
  // mirroring DesignBriefingPage's own ?variant=/?team= write-back pattern.
  const setOpenPhase = useCallback((next: string | null) => {
    setOpenPhaseState(next);
    void navigate({ search: { phase: next ?? undefined, program: search.program } as never, replace: true });
  }, [navigate, search.program]);
  const [completeError, setCompleteError] = useState("");
  const [completing, setCompleting] = useState(false);
  const [handbook, setHandbook] = useState<DesignHandbook | null>(null);
  const [confirmingTab, setConfirmingTab] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState("");
  const [celebration, setCelebration] = useState<{ title: string; subtitle: string } | null>(null);
  // Confirming is always this one deliberate click now (2026-09) — no more
  // guessing at completion via a false→true-transition watcher, since a
  // phase can no longer complete itself as a side effect of ordinary
  // editing (that auto-complete-on-any-edit behavior is exactly the bug
  // the confirm-step work fixed). So the celebration just fires straight
  // from here, for any phase, whether or not the student arrived via a
  // checklist deep link (`search.program` only changes whether
  // `CompletionCelebration`'s own button offers a way back to it).
  const confirmStep = async (tabValue: string) => {
    setConfirmingTab(tabValue);
    setConfirmError("");
    try {
      const next = await confirmDesignStep(attemptId, designStepKeyForTab(tabValue));
      setState(next);
      setOpenPhase(null);
      const label = DESIGN_TABS.find((t) => t.value === tabValue)?.label;
      setCelebration({
        title: `${label} phase complete!`,
        subtitle: "Nice work — that step is locked in on your board.",
      });
    } catch (err) {
      setConfirmError(errorDetail(err, "Couldn't confirm this step right now."));
    } finally {
      setConfirmingTab(null);
    }
  };

  const load = useCallback(() => {
    fetchDesignState(attemptId).then(setState).catch(() => setError("Couldn't load this design."));
  }, [attemptId]);

  useEffect(() => { load(); }, [load]);

  // A `?phase=` deep link (a Roadmap board tile, a checklist item, a shared
  // URL) opens a phase directly, bypassing the board's own tile click — a
  // derived value, not an effect+setState, so a gated phase never actually
  // renders regardless of how it was reached, without a spurious extra
  // render or a stale URL race.
  const openPhaseMeta = openPhase ? DESIGN_TABS.find((t) => t.value === openPhase) : undefined;
  const openPhaseBlocked = !!(state && openPhaseMeta && tabBlockInfo(state, openPhaseMeta).blocked);
  const effectiveOpenPhase = openPhaseBlocked ? null : openPhase;

  // Static for the life of the attempt — fetched once, not on every save.
  useEffect(() => { fetchDesignHandbook(attemptId).then(setHandbook).catch(() => {}); }, [attemptId]);

  const handleComplete = async () => {
    setCompleting(true);
    setCompleteError("");
    try {
      const next = await completeDesign(attemptId);
      setState(next);
      setOpenPhase("dashboard");
      setCelebration({ title: "Mission complete!", subtitle: "Every budget checks out. Nice work." });
    } catch (err) {
      setCompleteError(errorDetail(err, "Couldn't complete this design right now."));
      load();
    } finally {
      setCompleting(false);
    }
  };

  if (error) return <div className="mx-auto max-w-[1100px] px-5 py-10"><p className="text-sm text-destructive">{error}</p></div>;
  if (!state) return <div className="mx-auto max-w-[1100px] px-5 py-10"><p className="text-sm text-muted-foreground">Loading...</p></div>;

  const passed = state.attempt_status === "passed";
  // 2026-08-17 — compositional step scope: excluded steps are removed from
  // the wizard entirely, not just blocked (contrast with gate/needs
  // blocking below, which keeps a tab visible but disabled).
  const visibleTabs = DESIGN_TABS.filter((t) => !t.step || state.included_steps[t.step] !== false);
  // Server-truth confirmations, re-keyed from the backend's step keys to
  // this page's own tab values (see `designStepKeyForTab`'s own comment).
  const confirmedSteps: Record<string, boolean> = {};
  for (const t of DESIGN_TABS) {
    if (t.value === "dashboard") continue;
    confirmedSteps[t.value] = state.confirmed_steps.includes(designStepKeyForTab(t.value));
  }

  return (
    <div className="mx-auto max-w-[1100px] px-5 sm:px-8 py-6 sm:py-8 flex flex-col gap-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/learn/missions" className="text-primary hover:opacity-80">Missions</Link>
        <ChevronRight className="size-3.5" />
        <span className="text-foreground">{state.design_name || "My CubeSat"}</span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-4">
          <div className="w-fit flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide px-3 py-1.5 rounded-md bg-primary/10 text-primary">
            <Rocket className="size-3.5" /> Design Mission &middot; {state.variant_label}
          </div>
          <h1 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight leading-tight">{state.design_name || "My CubeSat"}</h1>
        </div>
        {passed ? (
          <div className="flex items-center gap-1.5 text-sm font-semibold text-emerald-500"><CheckCircle2 className="size-5" /> Complete</div>
        ) : (
          <Button onClick={() => void handleComplete()} disabled={completing || !state.dashboard.all_valid}>
            {completing ? "Checking..." : "Mark design complete"}
          </Button>
        )}
      </div>
      {completeError && <p className="text-xs text-destructive">{completeError}</p>}

      <MadarPhaseBoard state={state} visibleTabs={visibleTabs} confirmedSteps={confirmedSteps} onOpenPhase={setOpenPhase} />

      <DesignHandbookDrawer handbook={handbook} />
      <PosterTab state={state} attemptId={attemptId} onSaved={setState} />

      <MadarPhaseDrawer
        tab={effectiveOpenPhase}
        state={state}
        attemptId={attemptId}
        handbook={handbook}
        onClose={() => setOpenPhase(null)}
        onSaved={setState}
        onGoToTab={setOpenPhase}
        confirmedSteps={confirmedSteps}
        confirmingTab={confirmingTab}
        confirmError={confirmError}
        onConfirm={(t) => void confirmStep(t)}
      />

      <CompletionCelebration
        open={!!celebration}
        onOpenChange={(open) => { if (!open) setCelebration(null); }}
        title={celebration?.title ?? ""}
        subtitle={celebration?.subtitle ?? ""}
        assignmentId={search.program ?? ""}
      />
    </div>
  );
}

// ── Setup ────────────────────────────────────────────────────────────────

/** 2026-08-24 — a program-linked mission run's attempt is created eagerly
 * at cohort-assignment time (`assign_lms_program`), server-side, with no
 * name/objective/orbit collected — the checklist links straight into this
 * page's attempt id, skipping `DesignBriefingPage` (the flow that normally
 * gathers those) entirely. So Setup has to be able to collect the same
 * guided questions on its own, not just a bare free-text field. */
const ORBIT_PRESETS: Record<string, { orbit_type: string; orbit_duration_min: number; orbits_per_day: number }> = {
  LEO: { orbit_type: "LEO", orbit_duration_min: 90, orbits_per_day: 16 },
  SSO: { orbit_type: "SSO", orbit_duration_min: 100, orbits_per_day: 14 },
  GEO: { orbit_type: "GEO", orbit_duration_min: 1436, orbits_per_day: 1 },
};

export function SetupTab({ state, onSaved }: { state: DesignState; onSaved: (s: DesignState) => void }) {
  const [fields, setFields] = useState(() => ({
    name: state.design_name,
    objectives: parseObjectivePrompts(state.design_objective),
    orbitType: state.orbit_type ?? "LEO",
    orbitDuration: state.orbit_duration_min ?? 90,
    orbitsPerDay: state.orbits_per_day ?? 15,
    cubesatSize: state.selected_cubesat_size,
  }));
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  // Auto-saves 500ms after the last edit, same debounce LinkBudgetTab
  // already uses — no separate "Save" button competing with the drawer's
  // own "Complete this step" (2026-09: two buttons for one step is one
  // button too many).
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);
  const push = useCallback((next: typeof fields) => {
    if (pending.current) clearTimeout(pending.current);
    pending.current = setTimeout(async () => {
      setSaving(true);
      setSaveError("");
      try {
        onSaved(await updateDesign(state.attempt_id, {
          design_name: next.name,
          design_objective: joinObjectivePrompts(next.objectives),
          orbit_type: next.orbitType,
          orbit_duration_min: Number(next.orbitDuration),
          orbits_per_day: Number(next.orbitsPerDay),
          selected_cubesat_size: next.cubesatSize,
        }));
      } catch (err) {
        setSaveError(errorDetail(err, "Couldn't save mission setup."));
      } finally {
        setSaving(false);
      }
    }, 500);
  }, [state.attempt_id, onSaved]);

  useEffect(() => () => { if (pending.current) clearTimeout(pending.current); }, []);

  const setField = <K extends keyof typeof fields>(key: K, value: (typeof fields)[K]) => {
    const next = { ...fields, [key]: value };
    setFields(next);
    push(next);
  };

  const applyOrbitPreset = (preset: keyof typeof ORBIT_PRESETS) => {
    const p = ORBIT_PRESETS[preset];
    const next = { ...fields, orbitType: p.orbit_type, orbitDuration: p.orbit_duration_min, orbitsPerDay: p.orbits_per_day };
    setFields(next);
    push(next);
  };

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-muted-foreground max-w-[70ch]">
        Define your satellite's core identity, mission objective, and orbital specifications.
        {saving && <span className="text-primary"> · Saving…</span>}
      </p>

      <div className="flex flex-col gap-2 max-w-md">
        <label className={labelCls}>Mission Name</label>
        <input
          className={inputCls}
          value={fields.name}
          onChange={(e) => setField("name", e.target.value)}
          placeholder="e.g. EduSat-1"
        />
        <p className="text-[11px] text-muted-foreground">You can run this mission more than once — this name is how you'll tell your runs apart.</p>
      </div>

      <div className="flex flex-col gap-3 border-t border-border/60 pt-5">
        <p className="text-sm font-bold uppercase tracking-wider text-primary">Mission Objective</p>
        <div className="grid sm:grid-cols-2 gap-x-6 gap-y-4">
          {OBJECTIVE_PROMPTS.map((p) => (
            <div key={p.key} className="flex flex-col gap-1.5">
              <label className="text-xs text-muted-foreground">{p.label}</label>
              <input
                className={inputCls}
                value={fields.objectives[p.key] ?? ""}
                onChange={(e) => setField("objectives", { ...fields.objectives, [p.key]: e.target.value })}
                placeholder={p.placeholder}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-4 border-t border-border/60 pt-5">
        <p className="text-sm font-bold uppercase tracking-wider text-primary">Orbital & Satellite Specifications</p>

        <div className="flex flex-wrap gap-2">
          {(Object.keys(ORBIT_PRESETS) as (keyof typeof ORBIT_PRESETS)[]).map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => applyOrbitPreset(preset)}
              className={`px-3 py-1.5 rounded-xl text-sm ring-1 transition-colors ${
                fields.orbitType === preset ? "ring-primary/40 bg-primary/10 text-primary font-medium" : "ring-border hover:bg-muted/50"
              }`}
            >
              {preset}
            </button>
          ))}
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="flex flex-col gap-2">
            <label className={labelCls}>Orbit Type</label>
            <select className={`${inputCls} cursor-pointer`} value={fields.orbitType} onChange={(e) => setField("orbitType", e.target.value)}>
              {["LEO", "MEO", "GEO", "SSO", "Custom"].map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>

          <div className="flex flex-col gap-2">
            <label className={labelCls}>CubeSat Size</label>
            <select className={`${inputCls} cursor-pointer`} value={fields.cubesatSize} onChange={(e) => setField("cubesatSize", e.target.value)}>
              {state.cubesat_presets.map((p) => (
                <option key={p.size} value={p.size}>
                  {p.size} ({p.max_mass_kg}kg, {p.available_volume_cm3}cm³)
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-2">
            <label className={labelCls}>Orbit Duration (min)</label>
            <input
              type="number"
              className={inputCls}
              value={fields.orbitDuration}
              onChange={(e) => setField("orbitDuration", Number(e.target.value))}
            />
          </div>

          <div className="flex flex-col gap-2">
            <label className={labelCls}>Orbits Per Day</label>
            <input
              type="number"
              className={inputCls}
              value={fields.orbitsPerDay}
              onChange={(e) => setField("orbitsPerDay", Number(e.target.value))}
            />
          </div>
        </div>
      </div>

      {saveError && <p className="text-xs text-destructive">{saveError}</p>}
    </div>
  );
}

// ── Components ───────────────────────────────────────────────────────────

const SUBSYSTEMS = ["All", "ADCS", "CDHS", "EPS", "COMMS", "Payload", "Structure", "Thermal"];

export function ComponentsTab({ state, attemptId, onChanged }: { state: DesignState; attemptId: string; onChanged: (s: DesignState) => void }) {
  const [library, setLibrary] = useState<DesignLibraryComponent[]>([]);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [subsystemFilter, setSubsystemFilter] = useState("All");
  const [tagFilter, setTagFilter] = useState("All Tags");

  useEffect(() => { fetchDesignLibrary().then(setLibrary).catch(() => {}); }, []);

  // Dynamic, not legacy's hardcoded 2-option list — the real catalog carries
  // more tag values (SatKit, MPKit) than legacy's own picker ever knew about.
  const tags = ["All Tags", ...Array.from(new Set(library.map((c) => c.tag).filter((t): t is string => !!t)))];

  const filteredLibrary = library.filter((c) => {
    if (search.trim() && !c.component_name.toLowerCase().includes(search.trim().toLowerCase())) return false;
    if (subsystemFilter !== "All" && c.subsystem !== subsystemFilter) return false;
    if (tagFilter !== "All Tags" && c.tag !== tagFilter) return false;
    return true;
  });

  const add = async (libraryComponentId: string, quantity: number) => {
    setError("");
    try {
      onChanged(await addDesignComponent(attemptId, libraryComponentId, quantity));
    } catch (err) {
      setError(errorDetail(err, "Couldn't add this component."));
    }
  };

  const remove = async (designComponentId: string) => {
    setError("");
    try {
      onChanged(await removeDesignComponent(attemptId, designComponentId));
    } catch (err) {
      setError(errorDetail(err, "Couldn't remove this component."));
    }
  };

  // Cost/mass totals come off the backend-computed dashboard, not a
  // client-side re-sum — the same numbers the Cost/Mass budget tabs show.
  const totalCost = state.dashboard.cost.total_cost_aed;
  const maxBudget = state.dashboard.cost.maximum_budget_aed;
  const overBudget = state.dashboard.cost.cost_margin_aed < 0;
  const budgetPct = maxBudget > 0 ? Math.min(100, (totalCost / maxBudget) * 100) : 0;
  const combinedMassG = state.dashboard.mass.total_mass_kg * 1000;

  return (
    <div className="flex flex-col gap-5">
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex flex-col lg:flex-row gap-5 items-start">
        {/* Component library */}
        <div className="flex-1 min-w-0 flex flex-col gap-4">
          <div>
            <p className="text-base font-bold">Component library</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Click a component to read its specs, then add it to your design. What you pick here decides
              every budget that follows.
            </p>
          </div>

          <div className="flex flex-col gap-2.5">
            <div className="relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search components by name…"
                className={`${inputCls} pl-11`}
              />
            </div>
            <div className="flex flex-wrap gap-1.5">
              {SUBSYSTEMS.map((s) => (
                <button
                  key={s}
                  onClick={() => setSubsystemFilter(s)}
                  className={`px-3 py-1.5 rounded-xl text-xs ring-1 transition-colors ${
                    subsystemFilter === s ? "ring-primary/40 bg-primary/10 text-primary font-medium" : "ring-border hover:bg-muted/50"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
            {tags.length > 1 && (
              <select
                value={tagFilter}
                onChange={(e) => setTagFilter(e.target.value)}
                className={`${inputCls} w-auto`}
              >
                {tags.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            )}
          </div>

          {filteredLibrary.length === 0 && (
            <p className="text-xs text-muted-foreground">No components match this filter.</p>
          )}
          <div className="grid sm:grid-cols-2 gap-4">
            {filteredLibrary.map((c) => (
              <LibraryCard key={c.id} component={c} onAdd={(quantity) => void add(c.id, quantity)} />
            ))}
          </div>
        </div>

        {/* Mission cart + invoice */}
        <div className="w-full lg:w-[360px] shrink-0 flex flex-col gap-4 lg:sticky lg:top-4">
          <Card className="p-5 flex flex-col gap-3.5">
            <div className="flex items-center gap-2">
              <ShoppingCart className="size-[19px] text-primary" />
              <p className="text-base font-bold">Your mission cart</p>
              <span className="ml-auto text-xs font-bold text-primary bg-primary/10 px-2.5 py-1 rounded-full">
                {state.components.length} {state.components.length === 1 ? "item" : "items"}
              </span>
            </div>
            {state.components.length === 0 ? (
              <p className="text-xs text-muted-foreground">Add components from the library to build your mission.</p>
            ) : (
              <div className="flex flex-col gap-2.5">
                {state.components.map((c) => (
                  <div key={c.id} className="flex items-center gap-2.5">
                    {c.image_url
                      ? <img src={c.image_url} alt="" className="size-11 rounded-lg object-cover shrink-0 ring-1 ring-border" />
                      : (
                        <div className="size-11 rounded-lg shrink-0 ring-1 ring-border bg-muted flex items-center justify-center">
                          <Box className="size-5 text-muted-foreground" strokeWidth={1.5} />
                        </div>
                      )}
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">{c.component_name}</p>
                      <p className="text-xs text-muted-foreground">Qty {c.quantity} &middot; {(c.cost_per_unit_aed ?? 0).toFixed(0)} AED each</p>
                    </div>
                    <p className="text-sm font-bold text-amber-600 dark:text-amber-400 shrink-0">
                      {((c.cost_per_unit_aed ?? 0) * c.quantity).toFixed(0)} AED
                    </p>
                    <button onClick={() => void remove(c.id)} className="text-muted-foreground hover:text-destructive shrink-0">
                      <Trash2 className="size-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card className="p-5 flex flex-col gap-3">
            <p className="text-sm font-bold uppercase tracking-wider text-primary">Invoice</p>
            {state.components.length > 0 && (
              <>
                <div className="flex flex-col gap-1.5 text-xs">
                  {state.components.map((c) => (
                    <div key={c.id} className="flex justify-between gap-3">
                      <span className="text-muted-foreground truncate">{c.component_name} &times; {c.quantity}</span>
                      <span className="shrink-0">{((c.cost_per_unit_aed ?? 0) * c.quantity).toFixed(0)} AED</span>
                    </div>
                  ))}
                </div>
                <div className="h-px bg-border" />
              </>
            )}
            <div className="flex justify-between items-baseline">
              <span className="text-base font-bold">Total</span>
              <span className="text-xl font-extrabold text-amber-600 dark:text-amber-400">{totalCost.toFixed(0)} AED</span>
            </div>
            <div className="flex justify-between text-xs text-muted-foreground -mt-1">
              <span>Combined mass</span>
              <span>{combinedMassG.toFixed(0)} g</span>
            </div>
            <div className="flex flex-col gap-1.5 mt-1">
              <div className="flex justify-between text-[11px] text-muted-foreground">
                <span>Cost budget</span>
                <span>{totalCost.toFixed(0)} of {maxBudget.toFixed(0)} AED</span>
              </div>
              <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                <div
                  className={`h-full rounded-full ${overBudget ? "bg-destructive" : "bg-emerald-500"}`}
                  style={{ width: `${budgetPct}%` }}
                />
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

/** One library component, with the data the API has been sending all along
 * (7D-1). `DesignLibraryComponentOut` returns `example_role`,
 * `scaled_description`, `key_specs`, `temperature_range`, `datasheet_url`
 * and an image; the picker used to render name, mass, voltage and cost and
 * throw the rest away — so students chose parts from a spreadsheet with the
 * explanations deleted. No backend change was needed for any of this. */
function LibraryCard({ component: c, onAdd }: { component: DesignLibraryComponent; onAdd: (quantity: number) => void }) {
  const [qty, setQty] = useState(1);
  const dims = [c.length_mm, c.width_mm, c.height_mm];
  const hasDims = dims.every((d) => d != null && d > 0);

  const specs: { label: string; value: string; accent?: boolean }[] = [
    { label: "Voltage", value: c.voltage_v != null ? `${c.voltage_v}V` : "N/A" },
    { label: "Current", value: c.current_ma != null ? `${c.current_ma}mA` : "N/A" },
    { label: "Mass", value: c.scaled_mass_g != null ? `${c.scaled_mass_g}g` : "N/A" },
    { label: "Dimensions", value: hasDims ? dims.join(" × ") : "N/A" },
    { label: "Data size", value: c.data_size ?? "N/A" },
    { label: "Cost", value: c.assumed_cost_usd != null ? `$${c.assumed_cost_usd}` : "N/A", accent: true },
  ];

  return (
    <div className="rounded-2xl ring-1 ring-border bg-card overflow-hidden flex flex-col">
      <div className="relative h-[140px] shrink-0 flex items-center justify-center bg-gradient-to-br from-muted to-muted/40">
        {c.image_url
          ? <img src={c.image_url} alt="" className="h-full w-full object-cover" />
          : <Box className="size-11 text-muted-foreground/50" strokeWidth={1.5} />}
        <div className="absolute top-2.5 left-2.5 flex gap-1.5">
          <span className="px-2 py-1 rounded-lg text-[10px] font-bold tracking-wide bg-primary/90 text-primary-foreground">{c.subsystem}</span>
          {c.tag && <span className="px-2 py-1 rounded-lg text-[10px] font-bold tracking-wide bg-black/55 text-white">{c.tag.toUpperCase()}</span>}
        </div>
      </div>

      <div className="p-4 flex flex-col gap-3">
        <div className="flex flex-col gap-0.5">
          <p className="font-display text-[17px] font-bold leading-tight">{c.component_name}</p>
          {c.example_role && <p className="text-[13px] text-primary">{c.example_role}</p>}
          {c.scaled_description && (
            <p className="text-xs text-muted-foreground leading-relaxed mt-0.5 line-clamp-2">{c.scaled_description}</p>
          )}
        </div>

        {c.has_datasheet_file ? (
          <DatasheetViewerButton componentId={c.id} componentName={c.component_name} />
        ) : c.datasheet_url ? (
          <a
            href={c.datasheet_url} target="_blank" rel="noreferrer"
            className="h-9 rounded-lg bg-primary/10 ring-1 ring-primary/30 flex items-center justify-center gap-1.5 text-xs font-bold tracking-wide text-primary hover:bg-primary/15 transition-colors"
          >
            <FileText className="size-3.5" /> VIEW DATASHEET
          </a>
        ) : null}

        <div className="grid grid-cols-3 gap-2">
          {specs.map((s) => (
            <div key={s.label} className="rounded-lg bg-muted px-1.5 py-2 text-center">
              <p className={`text-sm font-bold ${s.accent ? "text-amber-600 dark:text-amber-400" : ""}`}>{s.value}</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">{s.label}</p>
            </div>
          ))}
        </div>

        {!hasDims && (
          <p className="text-[11px] text-amber-600 dark:text-amber-400">
            No dimensions on file — this component will contribute zero volume to your mass budget.
          </p>
        )}

        <div className="flex gap-2 mt-0.5">
          <div className="flex items-center justify-between gap-1 w-[104px] h-11 rounded-lg bg-muted ring-1 ring-border px-1.5 shrink-0">
            <button
              type="button"
              onClick={() => setQty((q) => Math.max(1, q - 1))}
              disabled={qty <= 1}
              className="size-7 flex items-center justify-center text-muted-foreground hover:text-foreground disabled:opacity-40"
            >
              <Minus className="size-3.5" />
            </button>
            <span className="text-sm font-semibold w-4 text-center">{qty}</span>
            <button
              type="button"
              onClick={() => setQty((q) => q + 1)}
              className="size-7 flex items-center justify-center text-primary hover:text-primary/80"
            >
              <Plus className="size-3.5" />
            </button>
          </div>
          <Button className="flex-1 h-11 gap-1.5 font-bold" onClick={() => { onAdd(qty); setQty(1); }}>
            <Plus className="size-3.5" /> Add to Mission
          </Button>
        </div>
      </div>
    </div>
  );
}

/** The org's own uploaded datasheet — opens in the same no-download viewer
 *  the LMS attachments and instructor library use, rather than a link.
 *  `datasheet_url` alone (no upload) stays a plain external link above —
 *  most of the seeded components still point at a Google Drive share or a
 *  manufacturer's site, files that aren't ours to protect. */
function DatasheetViewerButton({ componentId, componentName }: { componentId: string; componentName: string }) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const handleOpen = () => {
    setOpen(true);
    if (url || loading) return;
    setLoading(true);
    setError(false);
    fetchComponentDatasheetUrl(componentId)
      .then(setUrl)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  };

  return (
    <>
      <button
        type="button"
        onClick={handleOpen}
        className="h-9 rounded-lg bg-primary/10 ring-1 ring-primary/30 flex items-center justify-center gap-1.5 text-xs font-bold tracking-wide text-primary hover:bg-primary/15 transition-colors"
      >
        <FileText className="size-3.5" /> VIEW DATASHEET
      </button>
      <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) { setUrl(null); setError(false); } }}>
        <DialogContent className="sm:max-w-[95vw] max-w-[95vw] w-[95vw]">
          <DialogHeader><DialogTitle>{componentName}</DialogTitle></DialogHeader>
          {loading && <p className="text-sm text-muted-foreground py-6">Loading document...</p>}
          {error && <p className="text-sm text-destructive py-6">Couldn't load this document.</p>}
          {url && <PdfViewer url={url} />}
        </DialogContent>
      </Dialog>
    </>
  );
}

// ── CONOPS ───────────────────────────────────────────────────────────────

export function ConopsTab({ state, attemptId, onSaved }: { state: DesignState; attemptId: string; onSaved: (s: DesignState) => void }) {
  const [durations, setDurations] = useState<Record<string, number>>(
    Object.fromEntries(state.modes.map((m) => [m.id, m.duration_min])),
  );
  const [cells, setCells] = useState<Record<string, Record<string, boolean>>>(
    Object.fromEntries(state.components.map((c) => [c.id, Object.fromEntries(state.modes.map((m) => [m.id, c.on_mode_ids.includes(m.id)]))])),
  );
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const total = Object.values(durations).reduce((a, b) => a + (Number(b) || 0), 0);
  const diff = total - (state.orbit_duration_min ?? 0);

  // Auto-saves 500ms after the last edit, same debounce SetupTab/LinkBudgetTab
  // already use — no separate "Save" button competing with the drawer's own
  // "Complete this step" (2026-09: two buttons for one step is one too many).
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);
  const push = useCallback((nextDurations: typeof durations, nextCells: typeof cells) => {
    if (pending.current) clearTimeout(pending.current);
    pending.current = setTimeout(async () => {
      setSaving(true);
      setSaveError("");
      try {
        onSaved(await saveConops(attemptId, nextDurations, nextCells));
      } catch (err) {
        setSaveError(errorDetail(err, "Couldn't save CONOPS."));
      } finally {
        setSaving(false);
      }
    }, 500);
  }, [attemptId, onSaved]);

  useEffect(() => () => { if (pending.current) clearTimeout(pending.current); }, []);

  const setDuration = (modeId: string, value: number) => {
    const next = { ...durations, [modeId]: value };
    setDurations(next);
    push(next, cells);
  };

  const setCell = (componentId: string, modeId: string, checked: boolean) => {
    const next = { ...cells, [componentId]: { ...cells[componentId], [modeId]: checked } };
    setCells(next);
    push(durations, next);
  };

  const activeMinutes = (componentId: string) =>
    state.modes.reduce((sum, m) => sum + (cells[componentId]?.[m.id] ? (durations[m.id] ?? 0) : 0), 0);

  const matched = Math.abs(diff) < 0.01;

  const modeShareData = state.modes.map((m) => ({ name: m.mode_name, value: durations[m.id] ?? 0 }));

  const activeBySubsystem = Object.entries(
    state.components.reduce<Record<string, number>>((acc, c) => {
      acc[c.subsystem] = (acc[c.subsystem] ?? 0) + activeMinutes(c.id);
      return acc;
    }, {}),
  ).map(([subsystem, value], i) => ({ subsystem, value, color: CHART_COLORS[i % CHART_COLORS.length] }));
  const maxActive = Math.max(1, ...activeBySubsystem.map((d) => d.value));

  return (
    <Card className="p-5 flex flex-col gap-4">
      <div className={`flex items-start gap-3 rounded-2xl ring-1 px-5 py-4 ${matched ? ALERT_TONE.success : ALERT_TONE.warning}`}>
        {matched
          ? <CheckCircle2 className="size-5 shrink-0 mt-0.5 text-emerald-500" />
          : <AlertTriangle className="size-5 shrink-0 mt-0.5 text-amber-500" />}
        <p className="text-sm leading-relaxed">
          {matched
            ? <>Total mode duration <b>{total.toFixed(1)} min</b> matches the orbit period.</>
            : (
              <>
                Total mode duration <b>{total.toFixed(1)} min</b> &ne; orbit duration <b>{state.orbit_duration_min ?? 0} min</b> &middot; Difference:{" "}
                <b>{Math.abs(diff).toFixed(1)} min</b>. Adjust mode durations to match.
              </>
            )}
          {saving && <span className="text-primary"> &middot; Saving&hellip;</span>}
        </p>
      </div>

      <div className="flex flex-col gap-3">
        <p className="text-sm font-bold uppercase tracking-wider text-primary">Mission modes</p>
        <div className="grid sm:grid-cols-2 gap-3">
          {state.modes.map((m) => (
            <div key={m.id} className="flex flex-col gap-1.5">
              <label className={labelCls}>{m.mode_name}</label>
              <input
                type="number" className={inputCls} value={durations[m.id] ?? 0}
                onChange={(e) => setDuration(m.id, Number(e.target.value))}
              />
            </div>
          ))}
        </div>
      </div>

      {state.components.length > 0 && (
        <div className="flex flex-col gap-3">
          <p className="text-sm font-bold uppercase tracking-wider text-primary">CONOPS matrix</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 pr-3 font-medium text-muted-foreground">Component</th>
                  {state.modes.map((m) => <th key={m.id} className="px-2 py-2 font-medium text-muted-foreground text-center">{m.mode_name}</th>)}
                  <th className="px-2 py-2 font-medium text-muted-foreground text-center">Active time</th>
                </tr>
              </thead>
              <tbody>
                {state.components.map((c) => (
                  <tr key={c.id} className="border-b border-border/50">
                    <td className="py-2.5 pr-3">
                      <div className="flex items-center gap-2.5">
                        {c.image_url
                          ? <img src={c.image_url} alt="" className="size-8 rounded-lg object-cover shrink-0 ring-1 ring-border" />
                          : (
                            <div className="size-8 rounded-lg shrink-0 ring-1 ring-border bg-muted flex items-center justify-center">
                              <Box className="size-4 text-muted-foreground" strokeWidth={1.5} />
                            </div>
                          )}
                        <div className="flex flex-col gap-0.5">
                          <span className="font-medium">{c.component_name}</span>
                          <span className="w-fit px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-primary/10 text-primary">
                            {c.subsystem}
                          </span>
                        </div>
                      </div>
                    </td>
                    {state.modes.map((m) => {
                      const on = cells[c.id]?.[m.id] ?? false;
                      return (
                        <td key={m.id} className="px-2 py-2 text-center">
                          <button
                            type="button"
                            onClick={() => setCell(c.id, m.id, !on)}
                            className={`px-3 py-1 rounded-full text-[11px] font-bold tracking-wide transition-colors ${
                              on ? "bg-emerald-500 text-white" : "bg-muted text-muted-foreground hover:bg-muted/70"
                            }`}
                          >
                            {on ? "ON" : "OFF"}
                          </button>
                        </td>
                      );
                    })}
                    <td className="px-2 py-2 text-center">
                      <span className="px-2.5 py-1 rounded-full bg-primary/10 text-primary text-[11px] font-bold">
                        {activeMinutes(c.id).toFixed(1)} min
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid sm:grid-cols-3 gap-4 items-start">
            <div className="rounded-2xl ring-1 ring-border bg-card p-5 flex flex-col gap-1">
              <p className="text-sm font-bold uppercase tracking-wider text-primary mb-2">Summary</p>
              {[
                {
                  icon: Clock, label: "Total mode duration",
                  value: (
                    <div className="flex items-baseline gap-2">
                      <span className="text-lg font-extrabold">{total.toFixed(1)} min</span>
                      {!matched && (
                        <span className="px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400 text-[10px] font-bold">
                          {Math.abs(diff).toFixed(1)} off
                        </span>
                      )}
                    </div>
                  ),
                },
                { icon: Orbit, label: "Orbit duration", value: <span className="text-lg font-extrabold">{state.orbit_duration_min ?? 0} min</span> },
                { icon: Layers, label: "Selected components", value: <span className="text-lg font-extrabold">{state.components.length}</span> },
              ].map((row, i) => (
                <div key={row.label} className={`flex items-center justify-between gap-3 py-3 ${i > 0 ? "border-t border-border" : ""}`}>
                  <div className="flex items-center gap-2.5">
                    <div className="size-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                      <row.icon className="size-4 text-primary" />
                    </div>
                    <span className="text-xs text-muted-foreground">{row.label}</span>
                  </div>
                  {row.value}
                </div>
              ))}

              {activeBySubsystem.length > 0 && (
                <div className="flex flex-col gap-3 mt-3 pt-3 border-t border-border">
                  <p className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Active time by subsystem</p>
                  <div className="flex flex-col gap-3">
                    {activeBySubsystem.map((d) => (
                      <div key={d.subsystem} className="flex flex-col gap-1.5">
                        <div className="flex items-center justify-between gap-2">
                          <span
                            className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide"
                            style={{ background: `${d.color}26`, color: d.color }}
                          >
                            {d.subsystem}
                          </span>
                          <span className="text-xs font-bold">{d.value.toFixed(1)} min</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                          <div className="h-full rounded-full" style={{ width: `${(d.value / maxActive) * 100}%`, background: d.color }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="rounded-2xl ring-1 ring-border bg-card p-5 flex flex-col gap-2">
              <p className="text-sm font-bold uppercase tracking-wider text-primary">Mode duration share</p>
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie data={modeShareData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={2}>
                    {modeShareData.map((d, i) => <Cell key={d.name} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12 }} />
                  <Legend verticalAlign="top" wrapperStyle={{ fontSize: 11 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="rounded-2xl ring-1 ring-border bg-card p-5 flex flex-col gap-2">
              <p className="text-sm font-bold uppercase tracking-wider text-primary">Active time by subsystem (min)</p>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={activeBySubsystem} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-muted-foreground/20" />
                  <XAxis dataKey="subsystem" tick={{ fontSize: 11, fill: "currentColor" }} className="text-muted-foreground" />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "currentColor" }} className="text-muted-foreground" />
                  <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12 }} />
                  <Bar dataKey="value" name="Active time" radius={[6, 6, 0, 0]}>
                    {activeBySubsystem.map((d) => <Cell key={d.subsystem} fill={d.color} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {saveError && <p className="text-xs text-destructive">{saveError}</p>}
    </Card>
  );
}

// ── Budget tabs (data/power/mass/cost share the same per-component-row shape) ──

const PRIORITY_OPTIONS = ["Low", "Medium", "High"];

export function DataBudgetTab({ state, attemptId, onSaved, handbook }: {
  state: DesignState; attemptId: string; onSaved: (s: DesignState) => void; handbook: DesignHandbook | null;
}) {
  const [rows, setRows] = useState(Object.fromEntries(state.components.map((c) => [c.id, {
    data_type: c.data_entry?.data_type ?? "",
    data_size_per_measurement_kb: c.data_entry?.data_size_per_measurement_kb ?? 0,
    measurements_per_minute: c.data_entry?.measurements_per_minute ?? 0,
    priority: c.data_entry?.priority ?? "Medium",
    storage_mode: c.data_entry?.storage_mode ?? "Stored",
  }])));
  const [savingIds, setSavingIds] = useState<Set<string>>(new Set());
  const [saveError, setSaveError] = useState("");
  const [guideOpen, setGuideOpen] = useState(false);

  // Auto-saves 500ms after the last edit, same debounce SetupTab/ConopsTab
  // already use — no separate per-row "Save" button. Each component debounces
  // independently (keyed by id) so editing two rows back to back schedules
  // two saves rather than one cancelling the other.
  const pending = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const setRow = (id: string, patch: Partial<(typeof rows)[string]>) => {
    const next = { ...rows[id], ...patch };
    setRows((p) => ({ ...p, [id]: next }));
    if (pending.current[id]) clearTimeout(pending.current[id]);
    pending.current[id] = setTimeout(async () => {
      setSavingIds((s) => new Set(s).add(id));
      setSaveError("");
      try {
        onSaved(await saveDataBudget(attemptId, id, next));
      } catch (err) {
        setSaveError(errorDetail(err, "Couldn't save the data budget."));
      } finally {
        setSavingIds((s) => { const n = new Set(s); n.delete(id); return n; });
      }
    }, 500);
  };

  useEffect(() => () => { Object.values(pending.current).forEach(clearTimeout); }, []);

  if (state.components.length === 0) {
    return (
      <Card className="p-5">
        <p className="text-sm text-muted-foreground">Add components first — the data budget is computed from what you pick.</p>
      </Card>
    );
  }

  // Mirrors calc_data_budget (backend/app/services/missions/design/calculators.py)
  // exactly, over the live (not-yet-saved) row values, so this tab reads as
  // current as ConopsTab's own live totals instead of lagging one debounce
  // cycle behind the server-computed `state.dashboard.data`.
  const orbitsPerDay = state.orbits_per_day ?? 1;
  const dataRows = state.components.map((c) => {
    const activeMin = state.modes.reduce((sum, m) => sum + (c.on_mode_ids.includes(m.id) ? m.duration_min : 0), 0);
    const r = rows[c.id];
    const dpo = (r?.data_size_per_measurement_kb ?? 0) * (r?.measurements_per_minute ?? 0) * activeMin;
    const dpd = dpo * orbitsPerDay;
    return { component: c, activeMin, dpo, dpd, storageMode: r?.storage_mode ?? "Stored" };
  });
  const totalPerOrbit = dataRows.reduce((s, r) => s + r.dpo, 0);
  const totalPerDay = dataRows.reduce((s, r) => s + r.dpd, 0);
  const totalStored = dataRows.reduce((s, r) => s + (r.storageMode !== "Sent" ? r.dpd : 0), 0);
  const totalSent = dataRows.reduce((s, r) => s + (r.storageMode !== "Stored" ? r.dpd : 0), 0);

  const maxStorage = state.dashboard.data.max_storage_kb;
  const requiredMargin = state.dashboard.data.required_storage_margin_kb;
  const remaining = maxStorage - totalStored;
  const isValid = totalStored <= maxStorage && remaining >= requiredMargin;

  const bySubsystem = Object.entries(
    dataRows.reduce<Record<string, number>>((acc, r) => {
      acc[r.component.subsystem] = (acc[r.component.subsystem] ?? 0) + r.dpd;
      return acc;
    }, {}),
  ).map(([subsystem, value], i) => ({ subsystem, value, color: CHART_COLORS[i % CHART_COLORS.length] }));

  const topComponents = [...dataRows]
    .sort((a, b) => b.dpd - a.dpd)
    .slice(0, 6)
    .map((r) => ({ name: r.component.component_name, value: r.dpd }));

  return (
    <div className="flex flex-col gap-5">
      {/* Storage constraints */}
      <div className="grid sm:grid-cols-4 gap-4">
        <div className="rounded-2xl ring-1 ring-border bg-card p-4 flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Max storage</span>
          <span className="text-lg font-extrabold">{formatKB(maxStorage)}</span>
        </div>
        <div className="rounded-2xl ring-1 ring-border bg-card p-4 flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Required margin</span>
          <span className="text-lg font-extrabold">{formatKB(requiredMargin)}</span>
        </div>
        <div className="rounded-2xl ring-1 ring-border bg-card p-4 flex flex-col gap-1.5">
          <span className="text-xs text-muted-foreground">Stored/day</span>
          <span className="text-lg font-extrabold">{formatKB(totalStored)}</span>
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className={`h-full rounded-full ${totalStored <= maxStorage ? "bg-primary" : "bg-destructive"}`}
              style={{ width: `${Math.min(100, (totalStored / maxStorage) * 100)}%` }}
            />
          </div>
        </div>
        <div className="rounded-2xl ring-1 ring-border bg-card p-4 flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Remaining</span>
          <div className="flex items-center justify-between gap-2">
            <span className="text-lg font-extrabold">{formatKB(remaining)}</span>
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1 ${
              isValid ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" : "bg-destructive/15 text-destructive"
            }`}
            >
              {isValid ? <><CheckCircle2 className="size-3" /> OK</> : <><AlertTriangle className="size-3" /> Over</>}
            </span>
          </div>
        </div>
      </div>

      <Card className="p-5 flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-bold uppercase tracking-wider text-primary">Data budget table</p>
          <p className="text-xs text-muted-foreground">Amber rows are missing a data type.</p>
        </div>

        {handbook && handbook.data_types.length > 0 && (
          <div className="rounded-xl ring-1 ring-border overflow-hidden">
            <button
              type="button"
              onClick={() => setGuideOpen((v) => !v)}
              className="w-full flex items-center gap-2 px-3.5 py-2.5 hover:bg-muted/50 transition-colors text-left"
            >
              <FileText className="size-3.5 text-primary shrink-0" />
              <span className="flex-1 text-xs font-bold uppercase tracking-wide text-primary">Data types guide</span>
              <ChevronRight className={`size-4 shrink-0 text-muted-foreground transition-transform ${guideOpen ? "rotate-90" : ""}`} />
            </button>
            {guideOpen && (
              <div className="px-3.5 pb-3.5 pt-1 flex flex-col gap-2 border-t border-border/60">
                {handbook.data_types.map((dt) => (
                  <div key={dt.name} className="text-xs">
                    <span className="font-bold">{dt.name}</span>
                    <span className="text-muted-foreground"> &mdash; {dt.detail}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <p className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
          <AlertTriangle className="size-3.5 shrink-0" />
          Meas/min stands for measurement/min — how many data points are collected every minute.
        </p>

        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 pr-3 font-medium text-muted-foreground">Component</th>
                <th className="px-2 py-2 font-medium text-muted-foreground text-center">Data type</th>
                <th className="px-2 py-2 font-medium text-muted-foreground text-center">Size/meas (KB)</th>
                <th className="px-2 py-2 font-medium text-muted-foreground text-center">Meas/min</th>
                <th className="px-2 py-2 font-medium text-muted-foreground text-center">Active time (min)</th>
                <th className="px-2 py-2 font-medium text-muted-foreground text-center">Data/orbit (KB)</th>
                <th className="px-2 py-2 font-medium text-muted-foreground text-center">Orbits/day</th>
                <th className="px-2 py-2 font-medium text-muted-foreground text-center">Data/day (KB)</th>
                <th className="px-2 py-2 font-medium text-muted-foreground text-center">Priority</th>
                <th className="px-2 py-2 font-medium text-muted-foreground text-center">Stored/Sent</th>
              </tr>
            </thead>
            <tbody>
              {dataRows.map(({ component: c, activeMin, dpo, dpd }) => (
                <tr key={c.id} className={`border-b border-border/50 ${!rows[c.id]?.data_type ? "bg-amber-500/5" : ""}`}>
                  <td className="py-2.5 pr-3">
                    <div className="flex items-center gap-2.5">
                      {c.image_url
                        ? <img src={c.image_url} alt="" className="size-8 rounded-lg object-cover shrink-0 ring-1 ring-border" />
                        : (
                          <div className="size-8 rounded-lg shrink-0 ring-1 ring-border bg-muted flex items-center justify-center">
                            <Box className="size-4 text-muted-foreground" strokeWidth={1.5} />
                          </div>
                        )}
                      <div className="flex flex-col gap-0.5">
                        <span className="font-medium">{c.component_name}</span>
                        <span className="w-fit px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-primary/10 text-primary">
                          {c.subsystem}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td className="px-2 py-2">
                    <div className="w-32">
                      <select
                        className={`${inputCls} h-10 text-sm`} value={rows[c.id]?.data_type ?? ""}
                        onChange={(e) => setRow(c.id, { data_type: e.target.value })}
                      >
                        <option value="">-- Select --</option>
                        {(handbook?.data_types ?? []).map((dt) => <option key={dt.name} value={dt.name}>{dt.name}</option>)}
                      </select>
                    </div>
                  </td>
                  <td className="px-2 py-2">
                    <div className="w-20">
                      <input
                        type="number" className={compactInputCls}
                        value={rows[c.id]?.data_size_per_measurement_kb ?? 0}
                        onChange={(e) => setRow(c.id, { data_size_per_measurement_kb: Number(e.target.value) })}
                      />
                    </div>
                  </td>
                  <td className="px-2 py-2">
                    <div className="w-20">
                      <input
                        type="number" className={compactInputCls}
                        value={rows[c.id]?.measurements_per_minute ?? 0}
                        onChange={(e) => setRow(c.id, { measurements_per_minute: Number(e.target.value) })}
                      />
                    </div>
                  </td>
                  <td className="px-2 py-2 text-center font-mono text-xs text-muted-foreground">{activeMin.toFixed(1)}</td>
                  <td className="px-2 py-2 text-center font-mono text-xs font-bold text-primary">{dpo.toFixed(2)}</td>
                  <td className="px-2 py-2 text-center font-mono text-xs text-muted-foreground">{orbitsPerDay.toFixed(1)}</td>
                  <td className="px-2 py-2 text-center font-mono text-xs font-bold text-primary">{dpd.toFixed(2)}</td>
                  <td className="px-2 py-2">
                    <div className="w-28">
                      <select
                        className={`${inputCls} h-10 text-sm`} value={rows[c.id]?.priority ?? "Medium"}
                        onChange={(e) => setRow(c.id, { priority: e.target.value })}
                      >
                        {PRIORITY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
                      </select>
                    </div>
                  </td>
                  <td className="px-2 py-2">
                    <div className="w-28">
                      <select
                        className={`${inputCls} h-10 text-sm`} value={rows[c.id]?.storage_mode ?? "Stored"}
                        onChange={(e) => setRow(c.id, { storage_mode: e.target.value as "Stored" | "Sent" | "Both" })}
                      >
                        {["Stored", "Sent", "Both"].map((o) => <option key={o} value={o}>{o}</option>)}
                      </select>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {[...savingIds].length > 0 && <p className="text-xs text-primary">&middot; Saving&hellip;</p>}
        {saveError && <p className="text-xs text-destructive">{saveError}</p>}
      </Card>

      {/* Summary + charts */}
      <div className="grid sm:grid-cols-3 gap-4 items-start">
        <div className="rounded-2xl ring-1 ring-border bg-card p-5 flex flex-col gap-1">
          <p className="text-sm font-bold uppercase tracking-wider text-primary mb-2">Summary</p>
          <div className="flex items-center justify-between gap-3 py-3">
            <span className="text-xs text-muted-foreground">Total/orbit</span>
            <span className="text-lg font-extrabold">{formatKB(totalPerOrbit)}</span>
          </div>
          <div className="flex items-center justify-between gap-3 py-3 border-t border-border">
            <span className="text-xs text-muted-foreground">Total/day</span>
            <span className="text-lg font-extrabold">{formatKB(totalPerDay)}</span>
          </div>
          <div className="flex items-center justify-between gap-3 py-3 border-t border-border">
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground">Stored/day</span>
              <span className="text-sm font-bold text-emerald-600 dark:text-emerald-400">{formatKB(totalStored)}</span>
            </div>
            <div className="flex flex-col items-end">
              <span className="text-xs text-muted-foreground">Sent/day</span>
              <span className="text-sm font-bold text-sky-600 dark:text-sky-400">{formatKB(totalSent)}</span>
            </div>
          </div>
          <div className="flex items-center justify-between gap-3 py-3 border-t border-border">
            <span className="text-xs text-muted-foreground">Status</span>
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1 ${
              isValid ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" : "bg-destructive/15 text-destructive"
            }`}
            >
              {isValid ? <><CheckCircle2 className="size-3" /> Valid</> : <><AlertTriangle className="size-3" /> Invalid</>}
            </span>
          </div>
        </div>

        <div className="rounded-2xl ring-1 ring-border bg-card p-5 flex flex-col gap-2">
          <p className="text-sm font-bold uppercase tracking-wider text-primary">Data/day by subsystem</p>
          {totalPerDay > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={bySubsystem} dataKey="value" nameKey="subsystem" innerRadius={50} outerRadius={82} paddingAngle={2}>
                  {bySubsystem.map((d, i) => <Cell key={d.subsystem} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                </Pie>
                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12 }} />
                <Legend verticalAlign="top" wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : <p className="text-xs text-muted-foreground py-8 text-center">No data yet.</p>}
        </div>

        <div className="rounded-2xl ring-1 ring-border bg-card p-5 flex flex-col gap-2">
          <p className="text-sm font-bold uppercase tracking-wider text-primary">Top components by data/day</p>
          {totalPerDay > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={topComponents} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-muted-foreground/20" />
                <XAxis
                  dataKey="name" tick={{ fontSize: 10, fill: "currentColor" }} className="text-muted-foreground"
                  tickFormatter={(v: string) => (v.length > 12 ? `${v.slice(0, 12)}…` : v)}
                />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "currentColor" }} className="text-muted-foreground" />
                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12 }} />
                <Bar dataKey="value" name="Data/day" fill={CHART_COLORS[0]} radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="text-xs text-muted-foreground py-8 text-center">No data yet.</p>}
        </div>

        <div className="rounded-2xl ring-1 ring-border bg-card p-5 flex flex-col gap-2">
          <p className="text-sm font-bold uppercase tracking-wider text-primary">Stored vs sent distribution</p>
          {totalStored + totalSent > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={[{ name: "Stored", value: totalStored }, { name: "Sent", value: totalSent }]}
                  dataKey="value" nameKey="name" innerRadius={50} outerRadius={82} paddingAngle={2}
                >
                  <Cell fill={CHART_COLORS[0]} />
                  <Cell fill={CHART_COLORS[1]} />
                </Pie>
                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12 }} />
                <Legend verticalAlign="top" wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : <p className="text-xs text-muted-foreground py-8 text-center">No data yet.</p>}
        </div>

        <div className="rounded-2xl ring-1 ring-border bg-card p-5 flex flex-col gap-3 sm:col-span-2">
          <p className="text-sm font-bold uppercase tracking-wider text-primary">Subsystem data breakdown</p>
          {bySubsystem.length > 0 ? (
            <div className="flex flex-col gap-3">
              {bySubsystem.map((d) => (
                <div key={d.subsystem} className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide"
                      style={{ background: `${d.color}26`, color: d.color }}
                    >
                      {d.subsystem}
                    </span>
                    <span className="text-xs font-bold">{formatKB(d.value)}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${Math.max(1, totalPerDay > 0 ? (d.value / Math.max(...bySubsystem.map((x) => x.value), 1)) * 100 : 0)}%`, background: d.color }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : <p className="text-xs text-muted-foreground">No data yet.</p>}
        </div>
      </div>
    </div>
  );
}

export function PowerBudgetTab({ state, attemptId, onSaved }: { state: DesignState; attemptId: string; onSaved: (s: DesignState) => void }) {
  const [rows, setRows] = useState(Object.fromEntries(state.components.map((c) => [c.id, {
    voltage_v: c.power_entry?.voltage_v ?? c.voltage_v ?? 0, current_ma: c.power_entry?.current_ma ?? c.current_ma ?? 0,
  }])));
  const [cells, setCells] = useState(state.selected_solar_cells);
  const [savingIds, setSavingIds] = useState<Set<string>>(new Set());
  const [savingCells, setSavingCells] = useState(false);
  const [saveError, setSaveError] = useState("");

  // Auto-saves 500ms after the last edit — same debounce as the other budget
  // tabs, no manual per-row "Save"/"Set" buttons.
  const pending = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const setRow = (id: string, patch: Partial<(typeof rows)[string]>) => {
    const next = { ...rows[id], ...patch };
    setRows((p) => ({ ...p, [id]: next }));
    if (pending.current[id]) clearTimeout(pending.current[id]);
    pending.current[id] = setTimeout(async () => {
      setSavingIds((s) => new Set(s).add(id));
      setSaveError("");
      try {
        onSaved(await savePowerBudget(attemptId, id, next));
      } catch (err) {
        setSaveError(errorDetail(err, "Couldn't save the power budget."));
      } finally {
        setSavingIds((s) => { const n = new Set(s); n.delete(id); return n; });
      }
    }, 500);
  };
  const cellsPending = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pushCells = useCallback((next: number) => {
    if (cellsPending.current) clearTimeout(cellsPending.current);
    cellsPending.current = setTimeout(async () => {
      setSavingCells(true);
      setSaveError("");
      try {
        onSaved(await updateDesign(attemptId, { selected_solar_cells: next }));
      } catch (err) {
        setSaveError(errorDetail(err, "Couldn't save the solar cell count."));
      } finally {
        setSavingCells(false);
      }
    }, 500);
  }, [attemptId, onSaved]);
  const setCellsValue = (next: number) => { setCells(next); pushCells(next); };

  useEffect(() => () => {
    Object.values(pending.current).forEach(clearTimeout);
    if (cellsPending.current) clearTimeout(cellsPending.current);
  }, []);

  if (state.components.length === 0) {
    return (
      <Card className="p-5">
        <p className="text-sm text-muted-foreground">Add components first — the power budget is computed from what you pick.</p>
      </Card>
    );
  }

  // Mirrors calc_power_budget (backend/app/services/missions/design/calculators.py)
  // exactly, over the live row/cell values — same live-total pattern already
  // used by ConopsTab/DataBudgetTab.
  const orbitsPerDay = state.orbits_per_day ?? 1;
  const powerPerCell = state.dashboard.power.power_per_solar_cell_w;
  const powerRows = state.components.map((c) => {
    const activeMin = state.modes.reduce((sum, m) => sum + (c.on_mode_ids.includes(m.id) ? m.duration_min : 0), 0);
    const r = rows[c.id];
    const v = r?.voltage_v ?? 0;
    const i = r?.current_ma ?? 0;
    const power = v * i;
    const energyOrbit = (power * activeMin) / 60;
    const isActive = c.on_mode_ids.length > 0;
    const missing = isActive && (!v || !i);
    return { component: c, activeMin, power, energyOrbit, isActive, missing };
  });
  const totalPower = powerRows.reduce((s, r) => s + r.power, 0);
  const totalEnergyOrbit = powerRows.reduce((s, r) => s + r.energyOrbit, 0);
  const totalEnergyDay = totalEnergyOrbit * orbitsPerDay;
  const generatedMw = cells * powerPerCell * 1000;
  const marginMw = generatedMw - totalPower;
  const requiredCells = totalPower > 0 && powerPerCell > 0 ? Math.ceil(totalPower / 1000 / powerPerCell) : 0;
  const missingCount = powerRows.filter((r) => r.missing).length;

  const bySubsystem = Object.entries(
    powerRows.reduce<Record<string, number>>((acc, r) => {
      acc[r.component.subsystem] = (acc[r.component.subsystem] ?? 0) + r.power;
      return acc;
    }, {}),
  ).map(([subsystem, value], i) => ({ subsystem, value, color: CHART_COLORS[i % CHART_COLORS.length] }));

  const topComponents = [...powerRows]
    .sort((a, b) => b.energyOrbit - a.energyOrbit)
    .slice(0, 6)
    .map((r) => ({ name: r.component.component_name, value: r.energyOrbit }));

  const consumedW = totalPower / 1000;
  const generatedW = generatedMw / 1000;
  const deficitW = Math.max(0, consumedW - generatedW);

  return (
    <div className="flex flex-col gap-5">
      {missingCount > 0 && (
        <div className={`flex items-start gap-3 rounded-2xl ring-1 px-5 py-4 ${ALERT_TONE.warning}`}>
          <AlertTriangle className="size-5 shrink-0 mt-0.5 text-amber-500" />
          <p className="text-sm leading-relaxed">
            <b>{missingCount}</b> active component{missingCount === 1 ? "" : "s"} {missingCount === 1 ? "is" : "are"} missing voltage or
            current values. Please fill in all inputs.
          </p>
        </div>
      )}

      <div className="rounded-2xl ring-1 ring-border bg-primary/5 p-5 flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Zap className="size-4 text-primary" />
          <p className="text-sm font-bold uppercase tracking-wider text-primary">How power budget works</p>
        </div>
        <div className="grid sm:grid-cols-3 gap-3 text-xs">
          <p><b>Power (mW)</b> = Voltage (V) &times; Current (mA)</p>
          <p><b>Energy/orbit (mWh)</b> = Power &times; Active time &divide; 60</p>
          <p><b>Energy/day (mWh)</b> = Energy/orbit &times; Orbits per day</p>
          <p><b>Required solar cells</b> = &lceil;Total power (W) &divide; Power per cell (W)&rceil;</p>
          <p><b>Generated power (W)</b> = Selected cells &times; Power per cell</p>
          <p><b>Power margin (W)</b> = Generated power &minus; Total consumption</p>
        </div>
      </div>

      <Card className="p-5 flex flex-col gap-4">
        <p className="text-sm font-bold uppercase tracking-wider text-primary">EPS / power budget table</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 pr-3 font-medium text-muted-foreground">Component</th>
                <th className="px-2 py-2 font-medium text-muted-foreground text-center">Voltage (V)</th>
                <th className="px-2 py-2 font-medium text-muted-foreground text-center">Current (mA)</th>
                <th className="px-2 py-2 font-medium text-muted-foreground text-center">Power (mW)</th>
                <th className="px-2 py-2 font-medium text-muted-foreground text-center">Status</th>
                <th className="px-2 py-2 font-medium text-muted-foreground text-center">Active time (min)</th>
                <th className="px-2 py-2 font-medium text-muted-foreground text-center">Energy/orbit (mWh)</th>
              </tr>
            </thead>
            <tbody>
              {powerRows.map(({ component: c, activeMin, power, energyOrbit, missing }) => (
                <tr key={c.id} className={`border-b border-border/50 ${missing ? "bg-amber-500/5" : ""}`}>
                  <td className="py-2.5 pr-3">
                    <div className="flex items-center gap-2.5">
                      {c.image_url
                        ? <img src={c.image_url} alt="" className="size-8 rounded-lg object-cover shrink-0 ring-1 ring-border" />
                        : (
                          <div className="size-8 rounded-lg shrink-0 ring-1 ring-border bg-muted flex items-center justify-center">
                            <Box className="size-4 text-muted-foreground" strokeWidth={1.5} />
                          </div>
                        )}
                      <div className="flex flex-col gap-0.5">
                        <span className="font-medium">{c.component_name}</span>
                        <span className="w-fit px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-primary/10 text-primary">
                          {c.subsystem}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td className="px-2 py-2">
                    <div className="w-20">
                      <input
                        type="number" className={compactInputCls} value={rows[c.id]?.voltage_v ?? 0}
                        onChange={(e) => setRow(c.id, { voltage_v: Number(e.target.value) })}
                      />
                    </div>
                  </td>
                  <td className="px-2 py-2">
                    <div className="w-20">
                      <input
                        type="number" className={compactInputCls} value={rows[c.id]?.current_ma ?? 0}
                        onChange={(e) => setRow(c.id, { current_ma: Number(e.target.value) })}
                      />
                    </div>
                  </td>
                  <td className="px-2 py-2 text-center font-mono text-xs font-bold text-primary">{power.toFixed(2)}</td>
                  <td className="px-2 py-2 text-center">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      missing ? "bg-amber-500/15 text-amber-600 dark:text-amber-400" : "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                    }`}
                    >
                      {missing ? "Missing input" : "OK"}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-center font-mono text-xs text-muted-foreground">{activeMin.toFixed(1)}</td>
                  <td className="px-2 py-2 text-center font-mono text-xs font-bold text-primary">{energyOrbit.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {([...savingIds].length > 0 || savingCells) && <p className="text-xs text-primary">&middot; Saving&hellip;</p>}
        {saveError && <p className="text-xs text-destructive">{saveError}</p>}
      </Card>

      {/* Solar panel sizing */}
      <div className="flex flex-col gap-3">
        <p className="text-sm font-bold uppercase tracking-wider text-primary">Solar panel sizing</p>
        <div className="grid sm:grid-cols-3 gap-4 items-start">
          <div className="grid grid-cols-2 gap-4 sm:col-span-1">
            <div className="rounded-2xl ring-1 ring-border bg-card p-4 flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">Power per solar cell</span>
              <span className="text-lg font-extrabold">{powerPerCell.toFixed(1)} W</span>
              <span className="text-[10px] text-muted-foreground">Fixed admin value</span>
            </div>
            <div className="rounded-2xl ring-1 ring-border bg-card p-4 flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">Generated power</span>
              <span className="text-lg font-extrabold text-emerald-600 dark:text-emerald-400">{generatedW.toFixed(2)} W</span>
              <span className="text-[10px] text-muted-foreground">Selected cells &times; cell power</span>
            </div>
            <div className="rounded-2xl ring-1 ring-border bg-card p-4 flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">Total consumption</span>
              <span className="text-lg font-extrabold">{consumedW.toFixed(3)} W</span>
              <span className="text-[10px] text-muted-foreground">From all components</span>
            </div>
            <div className="rounded-2xl ring-1 ring-border bg-card p-4 flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">Power margin</span>
              <span className={`text-lg font-extrabold ${marginMw >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`}>
                {marginMw >= 0 ? "+" : ""}{(marginMw / 1000).toFixed(3)} W
              </span>
              <span className="text-[10px] text-muted-foreground">Generated &minus; consumed</span>
            </div>
          </div>

          <div className="rounded-2xl ring-1 ring-border bg-card p-5 flex flex-col gap-3 sm:col-span-2">
            <div>
              <p className="text-sm font-bold uppercase tracking-wider text-primary">Your solar panel design</p>
              <p className="text-xs text-muted-foreground mt-1">
                Enter the number of solar cells you want to include in your mission design. The system checks if it's enough to power
                all selected components.
              </p>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className={labelCls}>Selected number of solar cells (your design)</label>
              <div className="max-w-[200px]">
                <input
                  type="number" className={inputCls} value={cells}
                  onChange={(e) => setCellsValue(Number(e.target.value))}
                />
              </div>
            </div>
            {totalPower === 0 ? (
              <div className={`flex items-start gap-3 rounded-2xl ring-1 px-5 py-4 ${ALERT_TONE.warning}`}>
                <AlertTriangle className="size-5 shrink-0 mt-0.5 text-amber-500" />
                <p className="text-sm leading-relaxed">Enter voltage/current in the table, then choose your solar cell count.</p>
              </div>
            ) : cells < requiredCells ? (
              <div className={`flex items-start gap-3 rounded-2xl ring-1 px-5 py-4 ${ALERT_TONE.warning}`}>
                <AlertTriangle className="size-5 shrink-0 mt-0.5 text-amber-500" />
                <p className="text-sm leading-relaxed">
                  <b>Not enough power</b> &mdash; Your {cells} solar cell{cells === 1 ? "" : "s"} generate{cells === 1 ? "s" : ""} {generatedW.toFixed(2)} W,
                  short of the {consumedW.toFixed(3)} W required. Deficit: {deficitW.toFixed(3)} W.
                </p>
              </div>
            ) : (
              <div className={`flex items-start gap-3 rounded-2xl ring-1 px-5 py-4 ${ALERT_TONE.success}`}>
                <CheckCircle2 className="size-5 shrink-0 mt-0.5 text-emerald-500" />
                <p className="text-sm leading-relaxed">
                  <b>Enough power</b> &mdash; Your {cells} solar cell{cells === 1 ? "" : "s"} generate{cells === 1 ? "s" : ""} {generatedW.toFixed(2)} W,
                  which exceeds the {consumedW.toFixed(3)} W required. Margin: +{(marginMw / 1000).toFixed(3)} W.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Power summary */}
      <div className="grid sm:grid-cols-5 gap-4">
        <div className="rounded-2xl ring-1 ring-border bg-card p-4 flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Total power (mW)</span>
          <span className="text-lg font-extrabold">{totalPower.toFixed(1)}</span>
        </div>
        <div className="rounded-2xl ring-1 ring-border bg-card p-4 flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Total power (W)</span>
          <span className="text-lg font-extrabold">{(totalPower / 1000).toFixed(3)}</span>
        </div>
        <div className="rounded-2xl ring-1 ring-border bg-card p-4 flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Energy/orbit</span>
          <span className="text-lg font-extrabold">{totalEnergyOrbit.toFixed(2)} <span className="text-xs font-normal text-muted-foreground">mWh</span></span>
        </div>
        <div className="rounded-2xl ring-1 ring-border bg-card p-4 flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Orbits/day</span>
          <span className="text-lg font-extrabold">{orbitsPerDay.toFixed(1)}</span>
        </div>
        <div className="rounded-2xl ring-1 ring-border bg-card p-4 flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Energy/day</span>
          <span className="text-lg font-extrabold">{totalEnergyDay.toFixed(1)} <span className="text-xs font-normal text-muted-foreground">mWh</span></span>
        </div>
      </div>

      {/* Charts */}
      <div className="grid sm:grid-cols-3 gap-4 items-start">
        <div className="rounded-2xl ring-1 ring-border bg-card p-5 flex flex-col gap-2">
          <p className="text-sm font-bold uppercase tracking-wider text-primary">Power by subsystem</p>
          {totalPower > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={bySubsystem} dataKey="value" nameKey="subsystem" innerRadius={50} outerRadius={82} paddingAngle={2}>
                  {bySubsystem.map((d, i) => <Cell key={d.subsystem} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                </Pie>
                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12 }} />
                <Legend verticalAlign="top" wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : <p className="text-xs text-muted-foreground py-8 text-center">No data yet.</p>}
        </div>

        <div className="rounded-2xl ring-1 ring-border bg-card p-5 flex flex-col gap-2">
          <p className="text-sm font-bold uppercase tracking-wider text-primary">Top components by energy/orbit</p>
          {totalEnergyOrbit > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={topComponents} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-muted-foreground/20" />
                <XAxis
                  dataKey="name" tick={{ fontSize: 10, fill: "currentColor" }} className="text-muted-foreground"
                  tickFormatter={(v: string) => (v.length > 12 ? `${v.slice(0, 12)}…` : v)}
                />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "currentColor" }} className="text-muted-foreground" />
                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12 }} />
                <Bar dataKey="value" name="Energy/orbit" fill={CHART_COLORS[0]} radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="text-xs text-muted-foreground py-8 text-center">No data yet.</p>}
        </div>

        <div className="rounded-2xl ring-1 ring-border bg-card p-5 flex flex-col gap-2">
          <p className="text-sm font-bold uppercase tracking-wider text-primary">Generated vs consumed power</p>
          {consumedW > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                {generatedW >= consumedW ? (
                  // Enough (or exact) power: split what's GENERATED into the
                  // part consumed vs the surplus margin — matches the legacy
                  // screen's own "Consumed (W) / Margin (W)" donut exactly.
                  <Pie
                    data={[{ name: "Consumed", value: consumedW }, { name: "Margin", value: generatedW - consumedW }]}
                    dataKey="value" nameKey="name" innerRadius={50} outerRadius={82} paddingAngle={2}
                  >
                    <Cell fill={CHART_COLORS[3]} />
                    <Cell fill="#10b981" />
                  </Pie>
                ) : (
                  // Not enough power: split what's CONSUMED into the part
                  // covered by generation vs the uncovered deficit.
                  <Pie
                    data={[{ name: "Generated", value: generatedW }, { name: "Deficit", value: consumedW - generatedW }]}
                    dataKey="value" nameKey="name" innerRadius={50} outerRadius={82} paddingAngle={2}
                  >
                    <Cell fill="#10b981" />
                    <Cell fill={CHART_COLORS[3]} />
                  </Pie>
                )}
                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12 }} />
                <Legend verticalAlign="top" wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : <p className="text-xs text-muted-foreground py-8 text-center">No data yet.</p>}
        </div>
      </div>

      <div className="rounded-2xl ring-1 ring-border bg-card p-5 flex flex-col gap-3">
        <p className="text-sm font-bold uppercase tracking-wider text-primary">Power by subsystem (mW)</p>
        {bySubsystem.length > 0 ? (
          <div className="flex flex-col gap-3">
            {bySubsystem.map((d) => (
              <div key={d.subsystem} className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span
                    className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide"
                    style={{ background: `${d.color}26`, color: d.color }}
                  >
                    {d.subsystem}
                  </span>
                  <span className="text-xs font-bold">{d.value.toFixed(1)} mW</span>
                </div>
                <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${(d.value / Math.max(...bySubsystem.map((x) => x.value), 1)) * 100}%`, background: d.color }}
                  />
                </div>
              </div>
            ))}
          </div>
        ) : <p className="text-xs text-muted-foreground">No data yet.</p>}
      </div>
    </div>
  );
}

/** Energy & battery (7D-2, D4) — the step that closes F8.
 *
 * The power budget checks one instant. This checks a whole orbit, and the
 * illumination fraction it needs is already in the student's own CONOPS:
 * sunlit time is whatever they did *not* allocate to the eclipse mode. The
 * only new input is the battery, and the limit it's checked against is
 * variant-owned, not student-editable (the F4 lesson).
 */
export function EnergyBudgetTab({ state, attemptId, onSaved }: { state: DesignState; attemptId: string; onSaved: (s: DesignState) => void }) {
  const [capacity, setCapacity] = useState(state.battery_capacity_wh ?? 0);
  const [saving, setSaving] = useState(false);
  const e = state.dashboard.energy;

  const save = async () => {
    setSaving(true);
    try { onSaved(await updateDesign(attemptId, { battery_capacity_wh: Number(capacity) })); }
    finally { setSaving(false); }
  };

  const Row = ({ label, value, ok, detail }: { label: string; value: string; ok: boolean; detail: string }) => (
    <div className="flex flex-col gap-1 px-4 py-3 rounded-xl ring-1 ring-border">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className={`font-mono text-lg font-semibold ${ok ? "text-emerald-500" : "text-destructive"}`}>{value}</span>
      <span className="text-[11px] text-muted-foreground leading-relaxed">{detail}</span>
    </div>
  );

  return (
    <div className="flex flex-col gap-4">
      <Card className="p-5 flex flex-col gap-3">
        <div>
          <p className="text-base font-bold">Size the battery</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Everything still running when the spacecraft flies into Earth's shadow comes out of the
            battery. Your CONOPS says that lasts{" "}
            <b className="text-foreground">{e.eclipse_minutes.toFixed(0)} minutes</b> of every orbit.
          </p>
        </div>
        <div className="flex items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className={labelCls}>Battery capacity (Wh)</label>
            <input type="number" step="0.1" className={`${inputCls} w-36`} value={capacity}
              onChange={(ev) => setCapacity(Number(ev.target.value))} />
          </div>
          <Button size="sm" onClick={() => void save()} disabled={saving}>{saving ? "Saving..." : "Save"}</Button>
        </div>
      </Card>

      <div className="grid sm:grid-cols-2 gap-3">
        <Row
          label="Energy balance per orbit"
          value={`${e.energy_margin_mwh >= 0 ? "+" : ""}${e.energy_margin_mwh.toFixed(0)} mWh`}
          ok={e.energy_balance_ok}
          detail={`Generating ${e.generated_per_orbit_mwh.toFixed(0)} mWh in ${e.sunlit_minutes.toFixed(0)} min of sunlight, consuming ${e.consumed_per_orbit_mwh.toFixed(0)} mWh over the full orbit.`}
        />
        <Row
          label="Depth of discharge"
          value={`${e.depth_of_discharge_pct.toFixed(0)}%`}
          ok={e.depth_of_discharge_ok}
          detail={`Eclipse draws ${e.eclipse_draw_mwh.toFixed(0)} mWh from a ${(e.battery_capacity_mwh / 1000).toFixed(1)} Wh battery. This mission allows ${e.max_depth_of_discharge_pct.toFixed(0)}%.`}
        />
      </div>

      <Card className="p-4">
        <p className="text-xs leading-relaxed text-muted-foreground">
          <b className="text-foreground">Why depth of discharge is a hard limit.</b> Taking a lithium cell
          deep every orbit — sixteen times a day, for years — wears it out long before the mission ends.
          It is a lifetime constraint, not a survival one, which is why passing the energy balance is not
          enough on its own. The cheapest fix is almost always turning the payload off in eclipse rather
          than carrying a bigger battery.
        </p>
      </Card>
    </div>
  );
}

export function MassBudgetTab({ state, attemptId, onSaved }: { state: DesignState; attemptId: string; onSaved: (s: DesignState) => void }) {
  const [rows, setRows] = useState(Object.fromEntries(state.components.map((c) => [c.id, {
    quantity: c.mass_entry?.quantity ?? c.quantity, mass_per_unit_g: c.mass_entry?.mass_per_unit_g ?? c.mass_per_unit_g ?? 0,
    length_mm: c.mass_entry?.length_mm ?? c.length_mm ?? 0, width_mm: c.mass_entry?.width_mm ?? c.width_mm ?? 0, height_mm: c.mass_entry?.height_mm ?? c.height_mm ?? 0,
  }])));
  const [saving, setSaving] = useState<string | null>(null);

  const save = async (id: string) => {
    setSaving(id);
    try { onSaved(await saveMassBudget(attemptId, id, rows[id])); } finally { setSaving(null); }
  };

  return (
    <Card className="p-5 flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 text-sm">
        <p>Total mass: <b>{state.dashboard.mass.total_mass_kg.toFixed(3)} kg</b> of {state.dashboard.mass.max_allowed_mass_kg} kg</p>
        <p>Volume: <b>{state.dashboard.mass.total_volume_cm3.toFixed(1)} cm&sup3;</b> of {state.dashboard.mass.available_internal_volume_cm3} cm&sup3;</p>
      </div>
      {state.components.map((c) => (
        <div key={c.id} className="flex flex-wrap items-end gap-3 p-3 rounded-xl ring-1 ring-border">
          <div className="text-sm font-medium min-w-[120px]">{c.component_name}</div>
          <div className="flex flex-col gap-1"><label className={labelCls}>Qty</label>
            <input type="number" className={`${inputCls} w-24`} value={rows[c.id]?.quantity ?? 1}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], quantity: Number(e.target.value) } }))} /></div>
          <div className="flex flex-col gap-1"><label className={labelCls}>Mass (g)</label>
            <input type="number" className={inputCls} value={rows[c.id]?.mass_per_unit_g ?? 0}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], mass_per_unit_g: Number(e.target.value) } }))} /></div>
          <div className="flex flex-col gap-1"><label className={labelCls}>L (mm)</label>
            <input type="number" className={`${inputCls} w-24`} value={rows[c.id]?.length_mm ?? 0}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], length_mm: Number(e.target.value) } }))} /></div>
          <div className="flex flex-col gap-1"><label className={labelCls}>W (mm)</label>
            <input type="number" className={`${inputCls} w-24`} value={rows[c.id]?.width_mm ?? 0}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], width_mm: Number(e.target.value) } }))} /></div>
          <div className="flex flex-col gap-1"><label className={labelCls}>H (mm)</label>
            <input type="number" className={`${inputCls} w-24`} value={rows[c.id]?.height_mm ?? 0}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], height_mm: Number(e.target.value) } }))} /></div>
          <Button size="sm" onClick={() => void save(c.id)} disabled={saving === c.id}>{saving === c.id ? "..." : "Save"}</Button>
        </div>
      ))}
    </Card>
  );
}

export function CostBudgetTab({ state, attemptId, onSaved }: { state: DesignState; attemptId: string; onSaved: (s: DesignState) => void }) {
  const [rows, setRows] = useState(Object.fromEntries(state.components.map((c) => [c.id, {
    quantity: c.cost_entry?.quantity ?? c.quantity, cost_per_unit_aed: c.cost_entry?.cost_per_unit_aed ?? c.cost_per_unit_aed ?? 0,
  }])));
  const [saving, setSaving] = useState<string | null>(null);

  const save = async (id: string) => {
    setSaving(id);
    try { onSaved(await saveCostBudget(attemptId, id, rows[id])); } finally { setSaving(null); }
  };

  return (
    <Card className="p-5 flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 text-sm">
        <p>Total cost: <b>{state.dashboard.cost.total_cost_aed.toFixed(0)} AED</b></p>
        <p>Budget margin: <b className={state.dashboard.cost.cost_margin_aed >= 0 ? "text-emerald-500" : "text-destructive"}>{state.dashboard.cost.cost_margin_aed.toFixed(0)} AED</b> of {state.dashboard.cost.maximum_budget_aed} AED</p>
      </div>
      {state.components.map((c) => (
        <div key={c.id} className="flex flex-wrap items-end gap-3 p-3 rounded-xl ring-1 ring-border">
          <div className="text-sm font-medium min-w-[140px]">{c.component_name}</div>
          <div className="flex flex-col gap-1"><label className={labelCls}>Qty</label>
            <input type="number" className={`${inputCls} w-24`} value={rows[c.id]?.quantity ?? 1}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], quantity: Number(e.target.value) } }))} /></div>
          <div className="flex flex-col gap-1"><label className={labelCls}>Cost/unit (AED)</label>
            <input type="number" className={inputCls} value={rows[c.id]?.cost_per_unit_aed ?? 0}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], cost_per_unit_aed: Number(e.target.value) } }))} /></div>
          <Button size="sm" onClick={() => void save(c.id)} disabled={saving === c.id}>{saving === c.id ? "..." : "Save"}</Button>
        </div>
      ))}
    </Card>
  );
}

// ── Link ─────────────────────────────────────────────────────────────────

export function LinkBudgetTab({ state, attemptId, onSaved }: { state: DesignState; attemptId: string; onSaved: (s: DesignState) => void }) {
  const [band, setBand] = useState(state.link_entry?.band_profile ?? "UHF");
  const preset = state.band_presets[band];
  const [fields, setFields] = useState({
    downlink_frequency_mhz: state.link_entry?.downlink_frequency_mhz ?? preset?.downlink_frequency_mhz ?? 437.5,
    uplink_frequency_mhz: state.link_entry?.uplink_frequency_mhz ?? preset?.uplink_frequency_mhz ?? 145.8,
    satellite_antenna_gain_dbi: state.link_entry?.satellite_antenna_gain_dbi ?? preset?.satellite_antenna_gain_dbi ?? 2.0,
    data_rate_kbps: state.link_entry?.data_rate_kbps ?? preset?.data_rate_kbps ?? 9.6,
    required_signal_quality_db: state.link_entry?.required_signal_quality_db ?? preset?.required_signal_quality_db ?? 9.6,
  });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [formulasOpen, setFormulasOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const link = state.dashboard.link;

  // Recalculate as you type. The old form only recomputed on an explicit
  // Save, so finding a link that closes meant guess → click → read → guess
  // again, with no sense of which direction was helping. The budget is a
  // trade you feel by moving one number at a time; a 500 ms debounce keeps
  // the server the single source of truth without a request per keystroke.
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);
  const push = useCallback((nextBand: string, next: typeof fields) => {
    if (pending.current) clearTimeout(pending.current);
    pending.current = setTimeout(async () => {
      setSaving(true);
      setSaveError("");
      try {
        onSaved(await saveLinkBudget(attemptId, { band_profile: nextBand, notes: null, ...next }));
      } catch (err) {
        setSaveError(errorDetail(err, "Couldn't save the link budget."));
      } finally {
        setSaving(false);
      }
    }, 500);
  }, [attemptId, onSaved]);

  useEffect(() => () => { if (pending.current) clearTimeout(pending.current); }, []);

  const setField = (key: keyof typeof fields, value: number) => {
    const next = { ...fields, [key]: value };
    setFields(next);
    push(band, next);
  };

  const applyPreset = (b: string) => {
    setBand(b);
    const p = state.band_presets[b];
    const next = p ?? fields;
    if (p) setFields(p);
    push(b, next);
  };

  const shortBy = link.good_threshold_db - link.margin_db;

  const FIELD_HINTS: Record<keyof typeof fields, string> = {
    downlink_frequency_mhz: "Higher frequency spreads more over distance — costs margin.",
    uplink_frequency_mhz: "Not used in the downlink margin; recorded for completeness.",
    satellite_antenna_gain_dbi: "More gain, more margin. The cheapest dB you can buy.",
    data_rate_kbps: "Doubling the rate costs about 3 dB. The trade students miss.",
    required_signal_quality_db: "What your modulation needs to decode cleanly.",
  };

  const StatusIcon = link.status === "Good Link" ? CheckCircle2 : link.status === "Weak Link" ? AlertTriangle : XCircle;
  const statusToneKey = link.status === "Good Link" ? "success" : link.status === "Weak Link" ? "warning" : "error";
  const statusTextColor = link.status === "Good Link"
    ? "text-emerald-500" : link.status === "Weak Link" ? "text-amber-500" : "text-destructive";

  // Live detail breakdown — free_space_path_loss_db/noise_power_dbm above are
  // the exact backend formula; distance/transmit power stay the read-only
  // variant thresholds already on state.dashboard.link (never student-owned,
  // matching every other budget tab's P7-6 threshold treatment). This is new
  // content with no server equivalent, so unlike the headline stat above (which
  // stays on the server-debounced link.margin_db, per this tab's existing
  // "server is the source of truth" design) it recomputes live as you type.
  const fspl = freeSpacePathLossDb(fields.downlink_frequency_mhz, link.assumed_distance_km);
  const eirp = link.transmit_power_dbm + fields.satellite_antenna_gain_dbi;
  const rx = eirp - fspl;
  const noise = noisePowerDbm(fields.data_rate_kbps);
  const actualSnr = rx - noise;
  const liveMargin = actualSnr - fields.required_signal_quality_db;

  const detailRows: { label: string; value: number; unit: string; formula: string; bold?: boolean }[] = [
    { label: "EIRP", value: eirp, unit: "dBm", formula: "Tx Power + Antenna Gain" },
    { label: "Free Space Path Loss", value: fspl, unit: "dB", formula: "20·log(d) + 20·log(f) − 147.55" },
    { label: "Received Power", value: rx, unit: "dBm", formula: "EIRP − FSPL" },
    { label: "Noise Power", value: noise, unit: "dBm", formula: "10·log(k·T·BW) + 30" },
    { label: "Actual Signal Quality", value: actualSnr, unit: "dB", formula: "Received Power − Noise Power" },
    { label: "Required Signal Quality", value: fields.required_signal_quality_db, unit: "dB", formula: "(student input)" },
    { label: "System Link Margin", value: liveMargin, unit: "dB", formula: "Actual SNR − Required SNR", bold: true },
  ];

  return (
    <div className="flex flex-col gap-5">
      <div className="grid lg:grid-cols-2 gap-5 items-start">
        {/* Link configuration */}
        <Card className="p-5 flex flex-col gap-5">
          <p className="text-sm font-bold uppercase tracking-wider text-primary">Link configuration</p>

          <div className="flex flex-col gap-2">
            <label className={labelCls}>Step 1: choose band / profile</label>
            <div className="flex gap-2">
              {Object.keys(state.band_presets).map((b) => (
                <button
                  key={b} type="button" onClick={() => applyPreset(b)}
                  className={`px-4 py-2 rounded-xl text-sm font-bold transition-colors ${
                    band === b ? "bg-primary text-primary-foreground" : "ring-1 ring-border text-muted-foreground hover:bg-muted/50"
                  }`}
                >
                  {b}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <label className={labelCls}>Step 2: satellite transmitter &amp; frequency</label>
            <div className="grid sm:grid-cols-2 gap-4">
              {(Object.keys(fields) as (keyof typeof fields)[]).map((key) => (
                <div key={key} className="flex flex-col gap-1.5">
                  <label className={labelCls}>{key.replace(/_/g, " ")}</label>
                  <input
                    type="number" step="any" className={inputCls} value={fields[key]}
                    onChange={(e) => setField(key, Number(e.target.value))}
                  />
                  <span className="text-[10px] text-muted-foreground leading-snug">{FIELD_HINTS[key]}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <label className={labelCls}>Step 3: ground station settings</label>
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="rounded-xl ring-1 ring-border bg-muted/30 p-3 flex flex-col gap-0.5">
                <span className="text-xs text-muted-foreground">Assumed distance</span>
                <span className="text-base font-bold">{link.assumed_distance_km.toLocaleString()} km</span>
                <span className="text-[10px] text-muted-foreground">Set by your instructor</span>
              </div>
              <div className="rounded-xl ring-1 ring-border bg-muted/30 p-3 flex flex-col gap-0.5">
                <span className="text-xs text-muted-foreground">Satellite transmit power</span>
                <span className="text-base font-bold">{link.transmit_power_dbm.toFixed(0)} dBm</span>
                <span className="text-[10px] text-muted-foreground">Set by your instructor</span>
              </div>
            </div>
          </div>

          <div className="rounded-xl ring-1 ring-border overflow-hidden">
            <button
              type="button" onClick={() => setFormulasOpen((v) => !v)}
              className="w-full flex items-center gap-2 px-3.5 py-2.5 hover:bg-muted/50 transition-colors text-left"
            >
              <FileText className="size-3.5 text-primary shrink-0" />
              <span className="flex-1 text-xs font-bold uppercase tracking-wide text-primary">Show formulas</span>
              <ChevronRight className={`size-4 shrink-0 text-muted-foreground transition-transform ${formulasOpen ? "rotate-90" : ""}`} />
            </button>
            {formulasOpen && (
              <div className="px-3.5 pb-3.5 pt-1 flex flex-col gap-1.5 border-t border-border/60 text-xs font-mono">
                <p>EIRP = Tx Power + Antenna Gain</p>
                <p>FSPL = 20&middot;log(d) + 20&middot;log(f) &minus; 147.55</p>
                <p>Received Power = EIRP &minus; FSPL</p>
                <p>Noise Power = 10&middot;log(k&middot;T&middot;BW) + 30</p>
                <p>Margin = (Received Power &minus; Noise Power) &minus; Required Signal Quality</p>
              </div>
            )}
          </div>

          {saveError && <p className="text-xs text-destructive">{saveError}</p>}
        </Card>

        {/* Margin + charts */}
        <div className="flex flex-col gap-5">
          <div className={`rounded-2xl ring-1 px-6 py-6 flex flex-col items-center text-center gap-1.5 ${ALERT_TONE[statusToneKey]}`}>
            <p className="text-sm font-bold uppercase tracking-wider text-primary">System link margin</p>
            <p className={`font-display text-5xl font-extrabold ${statusTextColor}`}>
              {link.margin_db >= 0 ? "+" : ""}{link.margin_db.toFixed(2)}
            </p>
            <p className="text-xs text-muted-foreground">dB</p>
            <span className={`px-3 py-1 rounded-full text-xs font-bold flex items-center gap-1.5 ${
              link.status === "Good Link" ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                : link.status === "Weak Link" ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
                : "bg-destructive/15 text-destructive"
            }`}
            >
              <StatusIcon className="size-3.5" /> {link.status}
            </span>
            <p className="text-xs text-muted-foreground max-w-xs">
              {link.status === "Good Link"
                ? `${(link.margin_db - link.good_threshold_db).toFixed(1)} dB of headroom above the requirement.`
                : `Short by ${shortBy.toFixed(1)} dB. Raise the antenna gain, lower the data rate, or move to a lower frequency.`}
              {" "}{saving ? "Recalculating…" : ""}
            </p>
          </div>

          <div className="rounded-2xl ring-1 ring-border bg-card p-5 flex flex-col gap-2">
            <p className="text-sm font-bold uppercase tracking-wider text-primary">Signal quality comparison</p>
            <ResponsiveContainer width="100%" height={140}>
              <BarChart
                layout="vertical"
                data={[{ name: "Required SNR", value: fields.required_signal_quality_db }, { name: "Actual SNR", value: actualSnr }]}
                margin={{ top: 8, right: 16, left: 8, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-muted-foreground/20" />
                <XAxis type="number" tick={{ fontSize: 11, fill: "currentColor" }} className="text-muted-foreground" />
                <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 11, fill: "currentColor" }} className="text-muted-foreground" />
                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12 }} />
                <Bar dataKey="value" radius={[0, 6, 6, 0]}>
                  <Cell fill={CHART_COLORS[5]} />
                  <Cell fill={CHART_COLORS[4]} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="rounded-2xl ring-1 ring-border bg-card p-5 flex flex-col gap-2">
            <p className="text-sm font-bold uppercase tracking-wider text-primary">Link margin (dB)</p>
            <ResponsiveContainer width="100%" height={100}>
              <BarChart
                layout="vertical" data={[{ name: "Margin", value: liveMargin }]}
                margin={{ top: 8, right: 16, left: 8, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-muted-foreground/20" />
                <XAxis
                  type="number" domain={[Math.min(-10, link.weak_threshold_db - 5), Math.max(20, link.good_threshold_db + 5)]}
                  tick={{ fontSize: 11, fill: "currentColor" }} className="text-muted-foreground"
                />
                <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 11, fill: "currentColor" }} className="text-muted-foreground" />
                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12 }} />
                <Bar
                  dataKey="value" radius={[0, 6, 6, 0]}
                  fill={liveMargin >= link.good_threshold_db ? "#10b981" : liveMargin >= link.weak_threshold_db ? CHART_COLORS[2] : CHART_COLORS[3]}
                />
              </BarChart>
            </ResponsiveContainer>
            <p className="text-[10px] text-muted-foreground text-center">
              dB &mdash; {link.weak_threshold_db} dB = minimum, &gt;{link.good_threshold_db} dB = good
            </p>
          </div>
        </div>
      </div>

      <div className="rounded-2xl ring-1 ring-border bg-card overflow-hidden">
        <button
          type="button" onClick={() => setDetailsOpen((v) => !v)}
          className="w-full flex items-center gap-2 px-5 py-4 hover:bg-muted/50 transition-colors text-left"
        >
          <Search className="size-4 text-primary shrink-0" />
          <span className="flex-1 text-sm font-bold uppercase tracking-wider text-primary">Show detailed calculations</span>
          <ChevronRight className={`size-4 shrink-0 text-muted-foreground transition-transform ${detailsOpen ? "rotate-90" : ""}`} />
        </button>
        {detailsOpen && (
          <div className="px-5 pb-5 overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 pr-3 font-medium text-muted-foreground">Parameter</th>
                  <th className="px-2 py-2 font-medium text-muted-foreground text-right">Value</th>
                  <th className="px-2 py-2 font-medium text-muted-foreground text-center">Unit</th>
                  <th className="text-left px-2 py-2 font-medium text-muted-foreground">Formula</th>
                </tr>
              </thead>
              <tbody>
                {detailRows.map((row) => (
                  <tr key={row.label} className={`border-b border-border/50 ${row.bold ? "font-bold" : ""}`}>
                    <td className="py-2 pr-3">{row.label}</td>
                    <td className={`px-2 py-2 text-right font-mono ${row.bold ? "text-primary" : ""}`}>{row.value.toFixed(4)}</td>
                    <td className="px-2 py-2 text-center text-muted-foreground">{row.unit}</td>
                    <td className="px-2 py-2 text-muted-foreground font-mono text-xs">{row.formula}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Dashboard ────────────────────────────────────────────────────────────

/** Export the whole design as JSON (D6). Madar had this and it mattered:
 * it is the only way a student walks away with the numbers, and the only
 * way an instructor can look at a design outside the app. */
function exportDesignJson(state: DesignState) {
  const payload = {
    exported_at: new Date().toISOString(),
    design: {
      name: state.design_name, objective: state.design_objective,
      orbit_type: state.orbit_type, orbit_duration_min: state.orbit_duration_min,
      orbits_per_day: state.orbits_per_day, cubesat_size: state.selected_cubesat_size,
      solar_cells: state.selected_solar_cells, battery_capacity_wh: state.battery_capacity_wh,
      variant: state.variant_label,
    },
    components: state.components.map((c) => ({
      name: c.component_name, subsystem: c.subsystem, quantity: c.quantity,
      mass_per_unit_g: c.mass_per_unit_g, voltage_v: c.voltage_v, current_ma: c.current_ma,
      cost_per_unit_aed: c.cost_per_unit_aed,
      dimensions_mm: [c.length_mm, c.width_mm, c.height_mm],
      on_modes: c.on_mode_ids.map((id) => state.modes.find((m) => m.id === id)?.mode_name ?? id),
      data: c.data_entry, power: c.power_entry, mass: c.mass_entry, cost: c.cost_entry,
    })),
    conops: state.modes.map((m) => ({ mode: m.mode_name, duration_min: m.duration_min })),
    link: state.link_entry,
    report: {
      overall: state.dashboard.overall,
      kpis: state.dashboard.kpis,
      margins: state.dashboard.margins,
      alerts: state.dashboard.alerts,
      recommendations: state.dashboard.recommendations,
    },
    assumptions: state.assumptions,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${(state.design_name || "cubesat-design").replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

const MARGIN_TONE: Record<string, string> = {
  good: "ring-emerald-500/30 bg-emerald-500/5",
  tight: "ring-amber-500/30 bg-amber-500/5",
  fail: "ring-destructive/30 bg-destructive/5",
  incomplete: "ring-border",
};

const MARGIN_TEXT: Record<string, string> = {
  good: "text-emerald-500",
  tight: "text-amber-500",
  fail: "text-destructive",
  incomplete: "text-muted-foreground",
};

const ALERT_TONE: Record<string, string> = {
  error: "ring-destructive/30 bg-destructive/5",
  warning: "ring-amber-500/30 bg-amber-500/5",
  success: "ring-emerald-500/30 bg-emerald-500/5",
  info: "ring-border",
};

const CHART_COLORS = ["#A77DFF", "#6DD3FB", "#F7B267", "#F25F5C", "#70C1B3", "#9381FF", "#5FAD56"];

/** A proportion-of-whole breakdown — segmented bar + color-coded legend, no
 * chart library. Originally subsystem-only ("SubsystemChart"); generalized
 * (2026-09) so ConopsTab's mode-duration and active-time breakdowns can
 * reuse the exact same widget instead of a second bespoke chart. */
function ShareChart({ title, unit, data }: {
  title: string; unit: string; data: { label: string; value: number }[];
}) {
  if (data.length === 0) {
    return (
      <div className="rounded-2xl ring-1 ring-border bg-card p-5 text-center text-xs text-muted-foreground">
        {title} — no data yet
      </div>
    );
  }
  const total = data.reduce((a, d) => a + d.value, 0);
  return (
    <div className="rounded-2xl ring-1 ring-border bg-card p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-bold uppercase tracking-wider text-primary">{title}</p>
        <p className="text-xs font-mono text-muted-foreground">
          {total >= 1000 ? total.toLocaleString(undefined, { maximumFractionDigits: 0 }) : total.toFixed(1)} {unit}
        </p>
      </div>
      <div className="flex h-3 rounded-full overflow-hidden gap-px bg-border">
        {data.map((d, i) => (
          <div key={d.label} style={{ width: `${(d.value / total) * 100}%`, background: CHART_COLORS[i % CHART_COLORS.length] }} />
        ))}
      </div>
      <div className="flex flex-col gap-2">
        {data.map((d, i) => (
          <div key={d.label} className="flex items-center gap-2 text-xs">
            <span className="size-2.5 rounded-sm shrink-0" style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
            <span className="flex-1 text-foreground">{d.label}</span>
            <span className="font-mono text-muted-foreground">
              {d.value >= 1000 ? d.value.toLocaleString(undefined, { maximumFractionDigits: 0 }) : d.value.toFixed(1)} {unit}
            </span>
            <span className="font-mono text-muted-foreground w-9 text-right">{((d.value / total) * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** The mission report (7D-3) — Madar's payoff screen, rebuilt.
 *
 * Almost every number here was already in the API response and simply
 * never rendered; what's new is the judgement layer, which is where the
 * mission actually teaches on failure. `onGoToTab` lets a module card send
 * the student to the step that needs work — the design analog of the
 * operate debrief pointing at the fault you missed. */
export function DashboardTab({ state, onGoToTab }: { state: DesignState; onGoToTab: (tab: string) => void }) {
  const d = state.dashboard;
  const o = d.overall;

  return (
    <div className="flex flex-col gap-5">
      {/* verdict */}
      <Card className={`p-5 flex flex-wrap items-center justify-between gap-3 ring-1 ${
        o.all_valid ? "ring-emerald-500/30" : o.errors > 0 ? "ring-destructive/30" : "ring-border"}`}>
        <div className="flex items-center gap-3">
          {o.all_valid
            ? <CheckCircle2 className="size-7 text-emerald-500 shrink-0" />
            : <XCircle className={`size-7 shrink-0 ${o.errors > 0 ? "text-destructive" : "text-muted-foreground"}`} />}
          <div>
            <p className="text-base font-bold">{o.label}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {o.errors} failing · {o.warnings} tight · {o.incomplete} not started
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs font-mono text-muted-foreground">
          <span>{d.kpis.total_components} components</span>
          <span>{Number(d.kpis.total_mass_kg).toFixed(3)} kg</span>
          <span>{Number(d.kpis.total_power_mw).toFixed(0)} mW</span>
          <span>{Number(d.kpis.total_cost_aed).toLocaleString(undefined, { maximumFractionDigits: 0 })} AED</span>
        </div>
      </Card>

      {/* alerts */}
      {d.alerts.length > 0 && (
        <div className="flex flex-col gap-2">
          {d.alerts.map((a, i) => (
            <div key={i} className={`flex items-start gap-2.5 rounded-xl ring-1 px-4 py-3 ${ALERT_TONE[a.severity]}`}>
              {a.severity === "success"
                ? <CheckCircle2 className="size-4 shrink-0 mt-0.5 text-emerald-500" />
                : <XCircle className={`size-4 shrink-0 mt-0.5 ${a.severity === "error" ? "text-destructive" : a.severity === "warning" ? "text-amber-500" : "text-muted-foreground"}`} />}
              <p className="text-xs leading-relaxed">{a.message}</p>
            </div>
          ))}
        </div>
      )}

      {/* margins — the table Madar had, with interpretations */}
      <Card className="p-5 flex flex-col gap-3">
        <div>
          <p className="text-base font-bold">Margins</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            What you have left of every resource, and what that means.
          </p>
        </div>
        <div className="flex flex-col gap-2">
          {d.margins.map((m) => (
            <div key={m.key} className={`rounded-xl ring-1 px-4 py-3 flex flex-col gap-1 ${MARGIN_TONE[m.status]}`}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-medium">{m.label}</span>
                <span className={`font-mono text-sm font-semibold shrink-0 ${MARGIN_TEXT[m.status]}`}>
                  {m.status === "incomplete" ? "—" : `${m.value >= 0 && m.status !== "fail" ? "" : ""}${
                    Math.abs(m.value) >= 1000
                      ? m.value.toLocaleString(undefined, { maximumFractionDigits: 0 })
                      : m.value.toFixed(2)} ${m.unit}`}
                </span>
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">{m.interpretation}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* recommendations — the teaching half */}
      {d.recommendations.length > 0 && (
        <Card className="p-5 flex flex-col gap-3">
          <div>
            <p className="text-base font-bold">What to change</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              These are the mistakes your numbers look like. Each one is a real trade — none of them is free.
            </p>
          </div>
          <div className="flex flex-col gap-2.5">
            {d.recommendations.map((r) => (
              <div key={r.key} className="rounded-xl ring-1 ring-border px-4 py-3 flex flex-col gap-1.5">
                <p className="text-sm font-medium">{r.title}</p>
                <p className="text-xs leading-relaxed">{r.message}</p>
                <p className="text-[11px] text-muted-foreground leading-relaxed">{r.why}</p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* module cards */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {d.module_cards.map((c) => (
          <button
            key={c.key} onClick={() => onGoToTab(c.tab)}
            className={`text-left rounded-xl ring-1 px-4 py-3 flex flex-col gap-2 hover:opacity-90 transition-opacity ${MARGIN_TONE[c.status]}`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium">{c.title}</span>
              <span className={`text-[10px] font-semibold uppercase tracking-wide ${MARGIN_TEXT[c.status]}`}>
                {c.status === "good" ? "ok" : c.status}
              </span>
            </div>
            <div className="flex flex-col gap-0.5 text-[11px] font-mono text-muted-foreground">
              {c.kpi1_label && <span>{c.kpi1_label}: <span className="text-foreground">{c.kpi1_value}</span></span>}
              {c.kpi2_label && <span>{c.kpi2_label}: <span className="text-foreground">{c.kpi2_value}</span></span>}
            </div>
          </button>
        ))}
      </div>

      {/* charts (D5 — three, not Madar's ten) */}
      <div className="grid sm:grid-cols-3 gap-3">
        <ShareChart title="Power by subsystem" unit="mW" data={d.charts.power_by_subsystem.map((s) => ({ label: s.subsystem, value: s.value }))} />
        <ShareChart title="Mass by subsystem" unit="g" data={d.charts.mass_by_subsystem.map((s) => ({ label: s.subsystem, value: s.value }))} />
        <ShareChart title="Cost by subsystem" unit="AED" data={d.charts.cost_by_subsystem.map((s) => ({ label: s.subsystem, value: s.value }))} />
      </div>

      {/* The chained written report (D6). Gated on *passing* the design —
          a report about a design that doesn't close has nothing to defend. */}
      {state.attempt_status === "passed" && (
        <Card className="p-5 flex flex-wrap items-center justify-between gap-3 ring-primary/30 bg-primary/5 print:hidden">
          <div className="min-w-0">
            <p className="text-base font-bold">Your design report is unlocked</p>
            <p className="text-xs text-muted-foreground mt-0.5 max-w-[60ch] leading-relaxed">
              Designing a spacecraft and explaining one are different skills. Export the JSON above and
              write it up — a review board reads the report, not the spreadsheet.
            </p>
          </div>
          <Link to="/learn/missions" className="shrink-0">
            <Button variant="outline" size="sm">Find it in Missions</Button>
          </Link>
        </Card>
      )}

      {/* export + print (D6) — a student keeps an artifact, an instructor
          can mark it offline. Madar had both; the port had neither. */}
      <div className="flex flex-wrap items-center gap-3 print:hidden">
        <Button variant="outline" size="sm" onClick={() => exportDesignJson(state)}>
          Export JSON
        </Button>
        <Button variant="outline" size="sm" onClick={() => window.print()}>
          Print report
        </Button>
        <span className="text-[11px] text-muted-foreground">
          Take the numbers with you — printing captures this whole report.
        </span>
      </div>

      {/* F9 */}
      <Card className="p-5 flex flex-col gap-2">
        <p className="text-base font-bold">What this model simplifies</p>
        <p className="text-xs text-muted-foreground">
          Knowing the limits of your analysis is part of knowing how to use it.
        </p>
        <ul className="flex flex-col gap-1.5 mt-1">
          {state.assumptions.map((a) => (
            <li key={a} className="text-[11px] leading-relaxed flex gap-2 text-muted-foreground">
              <span className="shrink-0">·</span><span>{a}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
