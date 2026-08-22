import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, Link } from "@tanstack/react-router";
import { isAxiosError } from "axios";
import { CheckCircle2, ChevronRight, Rocket, Trash2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import DesignHandbookDrawer from "@/components/missions/DesignHandbook";
import PosterTab from "@/components/missions/PosterTab";
import {
  addDesignComponent, completeDesign, fetchDesignHandbook, fetchDesignLibrary, fetchDesignState,
  removeDesignComponent, saveConops, saveCostBudget, saveDataBudget, saveLinkBudget, saveMassBudget,
  savePowerBudget, updateDesign,
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

const inputCls = "h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors w-full";
const labelCls = "text-xs font-semibold uppercase tracking-wide text-muted-foreground";

/** The nine steps, with the dependency between them made visible (D2:
 * explain the order, don't enforce it). `needs` lists the steps whose data
 * this one is computed from — CONOPS feeds four separate budgets, which is
 * the single most important thing to communicate about the sequence. */
const DESIGN_TABS: {
  value: string; label: string; step?: string; needs?: string[]; blockedHint?: string;
}[] = [
  { value: "setup", label: "Setup" },
  { value: "components", label: "Components", step: "components" },
  {
    value: "conops", label: "CONOPS", step: "conops", needs: ["components"],
    blockedHint: "Add components first — the CONOPS matrix is a grid of components against modes.",
  },
  {
    value: "data", label: "Data", step: "data_budget", needs: ["conops"],
    blockedHint: "Set your CONOPS first — data volume is computed from how long each component is on.",
  },
  {
    value: "power", label: "Power", step: "power_budget", needs: ["conops"],
    blockedHint: "Set your CONOPS first — power draw is computed from how long each component is on.",
  },
  {
    value: "energy", label: "Energy", step: "energy_budget", needs: ["power_budget"],
    blockedHint: "Enter the power budget first — energy over an orbit is computed from it.",
  },
  { value: "link", label: "Link", step: "link_budget", needs: ["components"] },
  {
    value: "mass", label: "Mass", step: "mass_budget", needs: ["components"],
    blockedHint: "Add components first.",
  },
  {
    value: "cost", label: "Cost", step: "cost_budget", needs: ["components"],
    blockedHint: "Add components first.",
  },
  { value: "dashboard", label: "Report" },
];

/** The design-mission nine-step wizard (P7-5), ported from Madar's eleven
 * HTML pages. One fetch (`DesignState`) drives every tab; each save action
 * re-fetches the whole state so the dashboard is always current — this is
 * a workshop-scale tool, not a high-traffic one, so re-fetching the full
 * state per save is the simple, correct choice over hand-rolled partial
 * updates. */
export default function DesignMissionPage() {
  const { attemptId } = useParams({ strict: false }) as { attemptId: string };
  const [state, setState] = useState<DesignState | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("setup");
  const [completeError, setCompleteError] = useState("");
  const [completing, setCompleting] = useState(false);
  const [handbook, setHandbook] = useState<DesignHandbook | null>(null);

  const load = useCallback(() => {
    fetchDesignState(attemptId).then(setState).catch(() => setError("Couldn't load this design."));
  }, [attemptId]);

  useEffect(() => { load(); }, [load]);

  // Static for the life of the attempt — fetched once, not on every save.
  useEffect(() => { fetchDesignHandbook(attemptId).then(setHandbook).catch(() => {}); }, [attemptId]);

  const handleComplete = async () => {
    setCompleting(true);
    setCompleteError("");
    try {
      const next = await completeDesign(attemptId);
      setState(next);
      setTab("dashboard");
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

  return (
    <div className="mx-auto max-w-[1100px] px-5 sm:px-8 py-6 sm:py-8 flex flex-col gap-6">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Link to="/learn/missions" className="text-primary hover:opacity-80">Missions</Link>
        <ChevronRight className="size-3" />
        <span className="text-foreground">{state.design_name || "My CubeSat"}</span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-2">
          <div className="w-fit flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded-md bg-primary/10 text-primary">
            <Rocket className="size-3" /> Design Mission &middot; {state.variant_label}
          </div>
          <h1 className="font-display text-2xl sm:text-3xl font-extrabold tracking-tight">{state.design_name || "My CubeSat"}</h1>
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

      <CompletionMap state={state} visibleTabs={visibleTabs} onGoToTab={setTab} />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap">
          {visibleTabs.map((t) => {
            const step = t.step ? state.dashboard.steps[t.step] : undefined;
            // 2026-08-17 — two independent reasons a tab can be blocked:
            // a data dependency (D2: explain the order, don't enforce it —
            // still openable) or an instructor's explicit gate (a hard
            // block, backed by a 403 on the write endpoint, not just a
            // hint).
            const needsBlocked = t.needs?.some((k) => !state.dashboard.steps[k]?.has_data);
            const gateLocked = t.step ? state.step_gates?.[t.step] === false : false;
            const blocked = needsBlocked || gateLocked;
            const hint = gateLocked ? "Your instructor hasn't unlocked this step yet." : t.blockedHint;
            return (
              <TabsTrigger key={t.value} value={t.value} title={blocked ? hint : undefined}>
                <span className="flex items-center gap-1.5">
                  {t.label}
                  {blocked && <span className="text-[9px] text-amber-500">!</span>}
                  {step?.is_valid && <CheckCircle2 className="size-3 text-emerald-500" />}
                </span>
              </TabsTrigger>
            );
          })}
        </TabsList>

        <TabsContent value="setup"><SetupTab state={state} onSaved={setState} /></TabsContent>
        <TabsContent value="components"><ComponentsTab state={state} attemptId={attemptId} onChanged={setState} /></TabsContent>
        <TabsContent value="conops"><ConopsTab state={state} attemptId={attemptId} onSaved={setState} /></TabsContent>
        <TabsContent value="data"><DataBudgetTab state={state} attemptId={attemptId} onSaved={setState} /></TabsContent>
        <TabsContent value="power"><PowerBudgetTab state={state} attemptId={attemptId} onSaved={setState} /></TabsContent>
        <TabsContent value="energy"><EnergyBudgetTab state={state} attemptId={attemptId} onSaved={setState} /></TabsContent>
        <TabsContent value="link"><LinkBudgetTab state={state} attemptId={attemptId} onSaved={setState} /></TabsContent>
        <TabsContent value="mass"><MassBudgetTab state={state} attemptId={attemptId} onSaved={setState} /></TabsContent>
        <TabsContent value="cost"><CostBudgetTab state={state} attemptId={attemptId} onSaved={setState} /></TabsContent>
        <TabsContent value="dashboard"><DashboardTab state={state} onGoToTab={setTab} /></TabsContent>
      </Tabs>

      <DesignHandbookDrawer handbook={handbook} />
      <PosterTab state={state} attemptId={attemptId} onSaved={setState} />
    </div>
  );
}

// ── Setup ────────────────────────────────────────────────────────────────

function SetupTab({ state, onSaved }: { state: DesignState; onSaved: (s: DesignState) => void }) {
  const [name, setName] = useState(state.design_name);
  const [objective, setObjective] = useState(state.design_objective ?? "");
  const [orbitType, setOrbitType] = useState(state.orbit_type ?? "LEO");
  const [orbitDuration, setOrbitDuration] = useState(state.orbit_duration_min ?? 90);
  const [orbitsPerDay, setOrbitsPerDay] = useState(state.orbits_per_day ?? 15);
  const [cubesatSize, setCubesatSize] = useState(state.selected_cubesat_size);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState("");

  const save = async () => {
    setSaving(true);
    setSaveError("");
    setSaveSuccess(false);
    try {
      const next = await updateDesign(state.attempt_id, {
        design_name: name,
        design_objective: objective,
        orbit_type: orbitType,
        orbit_duration_min: Number(orbitDuration),
        orbits_per_day: Number(orbitsPerDay),
        selected_cubesat_size: cubesatSize,
      });
      onSaved(next);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      setSaveError(errorDetail(err, "Couldn't save mission setup."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="p-6 sm:p-7 flex flex-col gap-6 max-w-2xl mx-auto border border-border/80 shadow-sm">
      <div className="flex flex-col gap-1 border-b border-border/60 pb-3">
        <h2 className="font-display text-lg font-bold tracking-tight text-foreground">Mission Setup</h2>
        <p className="text-xs text-muted-foreground">
          Define your satellite's core identity, mission objective, and orbital specifications.
        </p>
      </div>

      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <label className={labelCls}>Mission Name</label>
          <input
            className={`${inputCls} h-10 px-3.5`}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. EduSat-1"
          />
        </div>

        <div className="flex flex-col gap-2">
          <label className={labelCls}>Objective</label>
          <textarea
            className={`${inputCls} h-auto min-h-[140px] p-3.5 leading-relaxed resize-y`}
            rows={5}
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            placeholder="Describe your mission objective, success criteria, lifetime, and operational goals..."
          />
        </div>
      </div>

      <div className="flex flex-col gap-4 border-t border-border/60 pt-5">
        <p className="text-xs font-semibold uppercase tracking-wider text-primary">Orbital & Satellite Specifications</p>

        <div className="grid sm:grid-cols-2 gap-4">
          <div className="flex flex-col gap-2">
            <label className={labelCls}>Orbit Type</label>
            <select className={`${inputCls} h-10 px-3.5 cursor-pointer`} value={orbitType} onChange={(e) => setOrbitType(e.target.value)}>
              {["LEO", "MEO", "GEO", "SSO", "Custom"].map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>

          <div className="flex flex-col gap-2">
            <label className={labelCls}>CubeSat Size</label>
            <select className={`${inputCls} h-10 px-3.5 cursor-pointer`} value={cubesatSize} onChange={(e) => setCubesatSize(e.target.value)}>
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
              className={`${inputCls} h-10 px-3.5`}
              value={orbitDuration}
              onChange={(e) => setOrbitDuration(Number(e.target.value))}
            />
          </div>

          <div className="flex flex-col gap-2">
            <label className={labelCls}>Orbits Per Day</label>
            <input
              type="number"
              className={`${inputCls} h-10 px-3.5`}
              value={orbitsPerDay}
              onChange={(e) => setOrbitsPerDay(Number(e.target.value))}
            />
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button className="h-10 px-6 font-semibold cursor-pointer" onClick={() => void save()} disabled={saving}>
          {saving ? "Saving..." : "Save Setup"}
        </Button>
        {saveSuccess && (
          <span className="text-xs font-semibold text-emerald-500 animate-in fade-in-0 duration-200">
            ✓ Mission setup saved!
          </span>
        )}
        {saveError && <p className="text-xs text-destructive">{saveError}</p>}
      </div>
    </Card>
  );
}

// ── Components ───────────────────────────────────────────────────────────

const SUBSYSTEMS = ["All", "ADCS", "CDHS", "EPS", "COMMS", "Payload", "Structure", "Thermal"];

function ComponentsTab({ state, attemptId, onChanged }: { state: DesignState; attemptId: string; onChanged: (s: DesignState) => void }) {
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

  const add = async (libraryComponentId: string) => {
    setError("");
    try {
      onChanged(await addDesignComponent(attemptId, libraryComponentId, 1));
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

  const bySubsystem = filteredLibrary.reduce<Record<string, DesignLibraryComponent[]>>((acc, c) => {
    (acc[c.subsystem] ??= []).push(c);
    return acc;
  }, {});

  return (
    <div className="flex flex-col gap-5">
      {error && <p className="text-xs text-destructive">{error}</p>}
      <Card className="p-5 flex flex-col gap-3">
        <p className="text-sm font-semibold">Your components ({state.components.length})</p>
        {state.components.length === 0 && <p className="text-xs text-muted-foreground">Add components from the library below.</p>}
        <div className="flex flex-col gap-2">
          {state.components.map((c) => (
            <div key={c.id} className="flex items-center gap-3 px-3.5 py-2.5 rounded-xl ring-1 ring-border">
              {c.image_url
                ? <img src={c.image_url} alt="" className="size-10 rounded-lg object-cover shrink-0 ring-1 ring-border" />
                : <div className="size-10 rounded-lg shrink-0 ring-1 ring-border bg-muted" />}
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium truncate">{c.component_name}</p>
                <p className="text-xs text-muted-foreground">{c.subsystem} &middot; {c.mass_per_unit_g ?? 0}g &middot; {c.voltage_v ?? 0}V/{c.current_ma ?? 0}mA</p>
              </div>
              <button onClick={() => void remove(c.id)} className="text-muted-foreground hover:text-destructive shrink-0"><Trash2 className="size-4" /></button>
            </div>
          ))}
        </div>
      </Card>
      <Card className="p-5 flex flex-col gap-4">
        <div>
          <p className="text-sm font-semibold">Component library</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Click a component to read its specs, then add it to your design. What you pick here decides
            every budget that follows.
          </p>
        </div>

        <div className="flex flex-col gap-2.5">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search components by name…"
            className={inputCls}
          />
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
        {Object.entries(bySubsystem).map(([subsystem, comps]) => (
          <div key={subsystem} className="flex flex-col gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{subsystem}</p>
            <div className="grid sm:grid-cols-2 gap-2">
              {comps.map((c) => (
                <LibraryCard key={c.id} component={c} onAdd={() => void add(c.id)} />
              ))}
            </div>
          </div>
        ))}
      </Card>
    </div>
  );
}

/** One library component, with the data the API has been sending all along
 * (7D-1). `DesignLibraryComponentOut` returns `example_role`,
 * `scaled_description`, `key_specs`, `temperature_range`, `datasheet_url`
 * and an image; the picker used to render name, mass, voltage and cost and
 * throw the rest away — so students chose parts from a spreadsheet with the
 * explanations deleted. No backend change was needed for any of this. */
function LibraryCard({ component: c, onAdd }: { component: DesignLibraryComponent; onAdd: () => void }) {
  const [open, setOpen] = useState(false);
  const dims = [c.length_mm, c.width_mm, c.height_mm];
  const hasDims = dims.every((d) => d != null && d > 0);

  return (
    <div className="rounded-xl ring-1 ring-border overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full text-left px-3.5 py-2.5 hover:bg-muted/50 transition-colors flex items-start gap-3"
      >
        {c.image_url && (
          <img src={c.image_url} alt="" className="size-10 rounded-lg object-cover shrink-0 ring-1 ring-border" />
        )}
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">{c.component_name}</span>
          {c.example_role && <span className="block text-xs text-primary mt-0.5">{c.example_role}</span>}
          <span className="block text-xs text-muted-foreground mt-0.5">
            {c.scaled_mass_g ?? 0}g &middot; {c.voltage_v ?? 0}V/{c.current_ma ?? 0}mA &middot; ${c.assumed_cost_usd ?? 0}
          </span>
        </span>
        <ChevronRight className={`size-4 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-90" : ""}`} />
      </button>

      {open && (
        <div className="px-3.5 pb-3.5 pt-1 flex flex-col gap-2.5 border-t border-border/60 text-xs">
          {c.scaled_description && <p className="leading-relaxed">{c.scaled_description}</p>}
          {c.key_specs && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-0.5">Key specs</p>
              <p className="font-mono text-[11px] leading-relaxed">{c.key_specs}</p>
            </div>
          )}
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[11px]">
            {hasDims && (
              <span><span className="text-muted-foreground">Size </span>{dims.join(" × ")} mm</span>
            )}
            {c.temperature_range && (
              <span><span className="text-muted-foreground">Temp </span>{c.temperature_range}</span>
            )}
            {c.data_size && (
              <span><span className="text-muted-foreground">Data </span>{c.data_size}</span>
            )}
            {c.component_code && (
              <span><span className="text-muted-foreground">Code </span>{c.component_code}</span>
            )}
          </div>
          {!hasDims && (
            <p className="text-[11px] text-amber-600 dark:text-amber-400">
              No dimensions on file — this component will contribute zero volume to your mass budget.
            </p>
          )}
          <div className="flex items-center gap-3 pt-1">
            <Button size="sm" onClick={onAdd}>Add to design</Button>
            {c.datasheet_url && (
              <a
                href={c.datasheet_url} target="_blank" rel="noreferrer"
                className="text-[11px] text-primary hover:opacity-80"
              >
                Datasheet ↗
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── CONOPS ───────────────────────────────────────────────────────────────

function ConopsTab({ state, attemptId, onSaved }: { state: DesignState; attemptId: string; onSaved: (s: DesignState) => void }) {
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

  const save = async () => {
    setSaving(true);
    setSaveError("");
    try {
      onSaved(await saveConops(attemptId, durations, cells));
    } catch (err) {
      setSaveError(errorDetail(err, "Couldn't save CONOPS."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Mode durations must sum to the orbit period ({state.orbit_duration_min ?? 0} min)</p>
        <p className={`text-xs font-medium ${Math.abs(diff) < 0.01 ? "text-emerald-500" : "text-destructive"}`}>
          Total: {total.toFixed(1)} min ({diff >= 0 ? "+" : ""}{diff.toFixed(1)})
        </p>
      </div>
      <div className="grid sm:grid-cols-2 gap-3">
        {state.modes.map((m) => (
          <div key={m.id} className="flex flex-col gap-1.5">
            <label className={labelCls}>{m.mode_name}</label>
            <input
              type="number" className={inputCls} value={durations[m.id] ?? 0}
              onChange={(e) => setDurations((prev) => ({ ...prev, [m.id]: Number(e.target.value) }))}
            />
          </div>
        ))}
      </div>

      {state.components.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 pr-3 font-medium text-muted-foreground">Component</th>
                {state.modes.map((m) => <th key={m.id} className="px-2 py-2 font-medium text-muted-foreground text-center">{m.mode_name}</th>)}
              </tr>
            </thead>
            <tbody>
              {state.components.map((c) => (
                <tr key={c.id} className="border-b border-border/50">
                  <td className="py-2 pr-3">{c.component_name}</td>
                  {state.modes.map((m) => (
                    <td key={m.id} className="px-2 py-2 text-center">
                      <input
                        type="checkbox" checked={cells[c.id]?.[m.id] ?? false}
                        onChange={(e) => setCells((prev) => ({ ...prev, [c.id]: { ...prev[c.id], [m.id]: e.target.checked } }))}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Button className="w-fit" onClick={() => void save()} disabled={saving}>{saving ? "Saving..." : "Save CONOPS"}</Button>
      {saveError && <p className="text-xs text-destructive">{saveError}</p>}
    </Card>
  );
}

// ── Budget tabs (data/power/mass/cost share the same per-component-row shape) ──

function DataBudgetTab({ state, attemptId, onSaved }: { state: DesignState; attemptId: string; onSaved: (s: DesignState) => void }) {
  const [rows, setRows] = useState(Object.fromEntries(state.components.map((c) => [c.id, {
    data_size_per_measurement_kb: c.data_entry?.data_size_per_measurement_kb ?? 0,
    measurements_per_minute: c.data_entry?.measurements_per_minute ?? 0,
    storage_mode: c.data_entry?.storage_mode ?? "Stored",
  }])));
  const [saving, setSaving] = useState<string | null>(null);

  const save = async (id: string) => {
    setSaving(id);
    try { onSaved(await saveDataBudget(attemptId, id, rows[id])); } finally { setSaving(null); }
  };

  return (
    <Card className="p-5 flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 text-sm">
        <p>Storage remaining: <b>{state.dashboard.data.storage_remaining_kb.toFixed(1)} KB</b> of {state.dashboard.data.max_storage_kb.toFixed(0)} KB</p>
        <p>Data/day: <b>{state.dashboard.data.total_per_day_kb.toFixed(1)} KB</b></p>
      </div>
      {state.components.map((c) => (
        <div key={c.id} className="flex flex-wrap items-end gap-3 p-3 rounded-xl ring-1 ring-border">
          <div className="text-sm font-medium min-w-[140px]">{c.component_name}</div>
          <div className="flex flex-col gap-1"><label className={labelCls}>Size/measurement (KB)</label>
            <input type="number" className={inputCls} value={rows[c.id]?.data_size_per_measurement_kb ?? 0}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], data_size_per_measurement_kb: Number(e.target.value) } }))} /></div>
          <div className="flex flex-col gap-1"><label className={labelCls}>Measurements/min</label>
            <input type="number" className={inputCls} value={rows[c.id]?.measurements_per_minute ?? 0}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], measurements_per_minute: Number(e.target.value) } }))} /></div>
          <div className="flex flex-col gap-1"><label className={labelCls}>Storage mode</label>
            <select className={inputCls} value={rows[c.id]?.storage_mode ?? "Stored"}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], storage_mode: e.target.value as "Stored" | "Sent" | "Both" } }))}>
              {["Stored", "Sent", "Both"].map((o) => <option key={o} value={o}>{o}</option>)}
            </select></div>
          <Button size="sm" onClick={() => void save(c.id)} disabled={saving === c.id}>{saving === c.id ? "..." : "Save"}</Button>
        </div>
      ))}
    </Card>
  );
}

function PowerBudgetTab({ state, attemptId, onSaved }: { state: DesignState; attemptId: string; onSaved: (s: DesignState) => void }) {
  const [rows, setRows] = useState(Object.fromEntries(state.components.map((c) => [c.id, {
    voltage_v: c.power_entry?.voltage_v ?? c.voltage_v ?? 0, current_ma: c.power_entry?.current_ma ?? c.current_ma ?? 0,
  }])));
  const [cells, setCells] = useState(state.selected_solar_cells);
  const [saving, setSaving] = useState<string | null>(null);
  const [savingCells, setSavingCells] = useState(false);

  const save = async (id: string) => {
    setSaving(id);
    try { onSaved(await savePowerBudget(attemptId, id, rows[id])); } finally { setSaving(null); }
  };
  const saveCells = async () => {
    setSavingCells(true);
    try { onSaved(await updateDesign(attemptId, { selected_solar_cells: cells })); } finally { setSavingCells(false); }
  };

  return (
    <Card className="p-5 flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 text-sm">
        <p>Total power: <b>{state.dashboard.power.total_power_mw.toFixed(0)} mW</b></p>
        <p>Margin: <b className={state.dashboard.power.power_margin_mw >= 0 ? "text-emerald-500" : "text-destructive"}>{state.dashboard.power.power_margin_mw.toFixed(0)} mW</b></p>
        <p>Required solar cells: <b>{state.dashboard.power.required_solar_cells}</b></p>
        <div className="flex items-center gap-2">
          <label className={labelCls}>Selected solar cells</label>
          <input type="number" className={`${inputCls} w-20`} value={cells} onChange={(e) => setCells(Number(e.target.value))} />
          <Button size="sm" onClick={() => void saveCells()} disabled={savingCells}>{savingCells ? "..." : "Set"}</Button>
        </div>
      </div>
      {state.components.map((c) => (
        <div key={c.id} className="flex flex-wrap items-end gap-3 p-3 rounded-xl ring-1 ring-border">
          <div className="text-sm font-medium min-w-[140px]">{c.component_name}</div>
          <div className="flex flex-col gap-1"><label className={labelCls}>Voltage (V)</label>
            <input type="number" className={inputCls} value={rows[c.id]?.voltage_v ?? 0}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], voltage_v: Number(e.target.value) } }))} /></div>
          <div className="flex flex-col gap-1"><label className={labelCls}>Current (mA)</label>
            <input type="number" className={inputCls} value={rows[c.id]?.current_ma ?? 0}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], current_ma: Number(e.target.value) } }))} /></div>
          <Button size="sm" onClick={() => void save(c.id)} disabled={saving === c.id}>{saving === c.id ? "..." : "Save"}</Button>
        </div>
      ))}
    </Card>
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
function EnergyBudgetTab({ state, attemptId, onSaved }: { state: DesignState; attemptId: string; onSaved: (s: DesignState) => void }) {
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
          <p className="text-sm font-semibold">Size the battery</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Everything still running when the spacecraft flies into Earth's shadow comes out of the
            battery. Your CONOPS says that lasts{" "}
            <b className="text-foreground">{e.eclipse_minutes.toFixed(0)} minutes</b> of every orbit.
          </p>
        </div>
        <div className="flex items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className={labelCls}>Battery capacity (Wh)</label>
            <input type="number" step="0.1" className={`${inputCls} w-32`} value={capacity}
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

function MassBudgetTab({ state, attemptId, onSaved }: { state: DesignState; attemptId: string; onSaved: (s: DesignState) => void }) {
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
            <input type="number" className={`${inputCls} w-16`} value={rows[c.id]?.quantity ?? 1}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], quantity: Number(e.target.value) } }))} /></div>
          <div className="flex flex-col gap-1"><label className={labelCls}>Mass (g)</label>
            <input type="number" className={inputCls} value={rows[c.id]?.mass_per_unit_g ?? 0}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], mass_per_unit_g: Number(e.target.value) } }))} /></div>
          <div className="flex flex-col gap-1"><label className={labelCls}>L (mm)</label>
            <input type="number" className={`${inputCls} w-20`} value={rows[c.id]?.length_mm ?? 0}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], length_mm: Number(e.target.value) } }))} /></div>
          <div className="flex flex-col gap-1"><label className={labelCls}>W (mm)</label>
            <input type="number" className={`${inputCls} w-20`} value={rows[c.id]?.width_mm ?? 0}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], width_mm: Number(e.target.value) } }))} /></div>
          <div className="flex flex-col gap-1"><label className={labelCls}>H (mm)</label>
            <input type="number" className={`${inputCls} w-20`} value={rows[c.id]?.height_mm ?? 0}
              onChange={(e) => setRows((p) => ({ ...p, [c.id]: { ...p[c.id], height_mm: Number(e.target.value) } }))} /></div>
          <Button size="sm" onClick={() => void save(c.id)} disabled={saving === c.id}>{saving === c.id ? "..." : "Save"}</Button>
        </div>
      ))}
    </Card>
  );
}

function CostBudgetTab({ state, attemptId, onSaved }: { state: DesignState; attemptId: string; onSaved: (s: DesignState) => void }) {
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
            <input type="number" className={`${inputCls} w-16`} value={rows[c.id]?.quantity ?? 1}
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

function LinkBudgetTab({ state, attemptId, onSaved }: { state: DesignState; attemptId: string; onSaved: (s: DesignState) => void }) {
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

  const closes = link.status === "Good Link";
  const shortBy = link.good_threshold_db - link.margin_db;

  const FIELD_HINTS: Record<keyof typeof fields, string> = {
    downlink_frequency_mhz: "Higher frequency spreads more over distance — costs margin.",
    uplink_frequency_mhz: "Not used in the downlink margin; recorded for completeness.",
    satellite_antenna_gain_dbi: "More gain, more margin. The cheapest dB you can buy.",
    data_rate_kbps: "Doubling the rate costs about 3 dB. The trade students miss.",
    required_signal_quality_db: "What your modulation needs to decode cleanly.",
  };

  return (
    <Card className="p-5 flex flex-col gap-4 max-w-xl">
      {/* The bar, not just the score. "Margin 0.61 dB / Failed Link" with no
          stated threshold is unanswerable — you cannot tell which way to move. */}
      <div className={`rounded-xl ring-1 px-4 py-3 flex flex-col gap-1 ${
        closes ? "ring-emerald-500/30 bg-emerald-500/5" : "ring-destructive/30 bg-destructive/5"}`}>
        <div className="flex items-baseline justify-between gap-2">
          <span className={`text-sm font-semibold ${closes ? "text-emerald-500" : "text-destructive"}`}>
            {link.status}
          </span>
          <span className="font-mono text-sm">
            {link.margin_db.toFixed(2)} dB
            <span className="text-muted-foreground"> / need {link.good_threshold_db.toFixed(1)} dB</span>
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          {closes
            ? `${(link.margin_db - link.good_threshold_db).toFixed(1)} dB of headroom above the requirement.`
            : `Short by ${shortBy.toFixed(1)} dB. Raise the antenna gain, lower the data rate, or move to a lower frequency — each is worth a few dB.`}
        </p>
        <p className="text-[10px] text-muted-foreground">
          Computed at {link.assumed_distance_km.toLocaleString()} km with a {link.transmit_power_dbm.toFixed(0)} dBm
          transmitter. {saving ? "Recalculating..." : "Updates as you type."}
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <label className={labelCls}>Band</label>
        <select className={inputCls} value={band} onChange={(e) => applyPreset(e.target.value)}>
          {Object.keys(state.band_presets).map((b) => <option key={b} value={b}>{b}</option>)}
        </select>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {(Object.keys(fields) as (keyof typeof fields)[]).map((key) => (
          <div key={key} className="flex flex-col gap-1.5">
            <label className={labelCls}>{key.replace(/_/g, " ")}</label>
            <input type="number" step="any" className={inputCls} value={fields[key]}
              onChange={(e) => setField(key, Number(e.target.value))} />
            <span className="text-[10px] text-muted-foreground leading-snug">{FIELD_HINTS[key]}</span>
          </div>
        ))}
      </div>
      {saveError && <p className="text-xs text-destructive">{saveError}</p>}
    </Card>
  );
}

// ── Dashboard ────────────────────────────────────────────────────────────

/** The completion map (7D-6) — Madar's "Satellite Stamps" grid, rebuilt.
 *
 * Nine tabs with no sense of progress is a worse experience than eight
 * stamps filling in, even though Madar's stamps were scored wrong: there,
 * a stamp meant "a row exists", so you earned the Power Budget badge by
 * saving a *failing* power budget (F11). Here a stamp is earned on the
 * step being **valid**, which is the fix that audit asked for — effort is
 * visible, but only correctness fills it in. */
function CompletionMap({ state, visibleTabs, onGoToTab }: { state: DesignState; visibleTabs: typeof DESIGN_TABS; onGoToTab: (tab: string) => void }) {
  const visibleStepKeys = new Set(visibleTabs.map((t) => t.step).filter((k): k is string => !!k));
  const allSteps = [
    { key: "components", label: "Components", tab: "components" },
    { key: "conops", label: "CONOPS", tab: "conops" },
    { key: "data_budget", label: "Data", tab: "data" },
    { key: "power_budget", label: "Power", tab: "power" },
    { key: "energy_budget", label: "Energy", tab: "energy" },
    { key: "link_budget", label: "Link", tab: "link" },
    { key: "downlink", label: "Downlink", tab: "dashboard" },
    { key: "mass_budget", label: "Mass", tab: "mass" },
    { key: "cost_budget", label: "Cost", tab: "cost" },
  ];
  // Downlink is never in visibleTabs (it's not a tab at all) — show it iff
  // it currently counts toward all_valid for this cohort's scope.
  const steps = allSteps.filter((s) => s.key === "downlink" ? state.dashboard.downlink_included : visibleStepKeys.has(s.key));
  const earned = steps.filter((s) => state.dashboard.steps[s.key]?.is_valid).length;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Progress</p>
        <p className="text-[11px] font-mono text-muted-foreground">{earned} / {steps.length} closed</p>
      </div>
      <div className="grid grid-cols-5 sm:grid-cols-9 gap-1.5">
        {steps.map((s) => {
          const st = state.dashboard.steps[s.key];
          const done = st?.is_valid;
          const started = st?.has_data;
          return (
            <button
              key={s.key} onClick={() => onGoToTab(s.tab)}
              title={done ? "Closed" : started ? "Started, not closing yet" : "Not started"}
              className={`flex flex-col items-center gap-1 py-2 rounded-xl ring-1 transition-colors ${
                done ? "ring-emerald-500/40 bg-emerald-500/10 text-emerald-500"
                  : started ? "ring-amber-500/30 bg-amber-500/5 text-amber-600 dark:text-amber-400"
                  : "ring-border text-muted-foreground hover:bg-muted/40"}`}
            >
              <span className="text-sm leading-none">{done ? "●" : started ? "◐" : "○"}</span>
              <span className="text-[9px] font-semibold uppercase tracking-wide">{s.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

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

function SubsystemChart({ title, unit, data }: {
  title: string; unit: string; data: { subsystem: string; value: number }[];
}) {
  if (data.length === 0) {
    return (
      <div className="rounded-xl ring-1 ring-border p-4 text-center text-xs text-muted-foreground">
        {title} — no data yet
      </div>
    );
  }
  const total = data.reduce((a, d) => a + d.value, 0);
  return (
    <div className="rounded-xl ring-1 ring-border p-4 flex flex-col gap-2">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</p>
      <div className="flex h-2.5 rounded-full overflow-hidden">
        {data.map((d, i) => (
          <div key={d.subsystem} style={{ width: `${(d.value / total) * 100}%`, background: CHART_COLORS[i % CHART_COLORS.length] }} />
        ))}
      </div>
      <div className="flex flex-col gap-1">
        {data.map((d, i) => (
          <div key={d.subsystem} className="flex items-center gap-2 text-[11px]">
            <span className="size-2 rounded-sm shrink-0" style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
            <span className="flex-1">{d.subsystem}</span>
            <span className="font-mono text-muted-foreground">
              {d.value >= 1000 ? d.value.toLocaleString(undefined, { maximumFractionDigits: 0 }) : d.value.toFixed(1)} {unit}
            </span>
            <span className="font-mono text-muted-foreground w-10 text-right">{((d.value / total) * 100).toFixed(0)}%</span>
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
function DashboardTab({ state, onGoToTab }: { state: DesignState; onGoToTab: (tab: string) => void }) {
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
            <p className="text-base font-semibold">{o.label}</p>
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
          <p className="text-sm font-semibold">Margins</p>
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
            <p className="text-sm font-semibold">What to change</p>
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
        <SubsystemChart title="Power by subsystem" unit="mW" data={d.charts.power_by_subsystem} />
        <SubsystemChart title="Mass by subsystem" unit="g" data={d.charts.mass_by_subsystem} />
        <SubsystemChart title="Cost by subsystem" unit="AED" data={d.charts.cost_by_subsystem} />
      </div>

      {/* The chained written report (D6). Gated on *passing* the design —
          a report about a design that doesn't close has nothing to defend. */}
      {state.attempt_status === "passed" && (
        <Card className="p-5 flex flex-wrap items-center justify-between gap-3 ring-primary/30 bg-primary/5 print:hidden">
          <div className="min-w-0">
            <p className="text-sm font-semibold">Your design report is unlocked</p>
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
        <p className="text-sm font-semibold">What this model simplifies</p>
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
