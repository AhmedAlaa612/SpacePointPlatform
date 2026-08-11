import { useCallback, useEffect, useState } from "react";
import { useParams, Link } from "@tanstack/react-router";
import { isAxiosError } from "axios";
import { CheckCircle2, ChevronRight, Lock, Rocket, Trash2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  addDesignComponent, completeDesign, fetchDesignLibrary, fetchDesignState, removeDesignComponent,
  saveConops, saveCostBudget, saveDataBudget, saveLinkBudget, saveMassBudget, savePowerBudget, updateDesign,
  type DesignLibraryComponent, type DesignState,
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

function StepBadge({ status }: { status: { has_data: boolean; is_valid: boolean } | undefined }) {
  if (!status || !status.has_data) return <span className="text-xs text-muted-foreground">Not started</span>;
  return status.is_valid
    ? <span className="flex items-center gap-1 text-xs text-emerald-500"><CheckCircle2 className="size-3.5" /> Valid</span>
    : <span className="flex items-center gap-1 text-xs text-destructive"><XCircle className="size-3.5" /> Needs work</span>;
}

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

  const load = useCallback(() => {
    fetchDesignState(attemptId).then(setState).catch(() => setError("Couldn't load this design."));
  }, [attemptId]);

  useEffect(() => { load(); }, [load]);

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

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap">
          <TabsTrigger value="setup">Setup</TabsTrigger>
          <TabsTrigger value="components">Components</TabsTrigger>
          <TabsTrigger value="conops">CONOPS</TabsTrigger>
          <TabsTrigger value="data">Data</TabsTrigger>
          <TabsTrigger value="power">Power</TabsTrigger>
          <TabsTrigger value="link">Link</TabsTrigger>
          <TabsTrigger value="mass">Mass</TabsTrigger>
          <TabsTrigger value="cost">Cost</TabsTrigger>
          <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
        </TabsList>

        <TabsContent value="setup"><SetupTab state={state} onSaved={setState} /></TabsContent>
        <TabsContent value="components"><ComponentsTab state={state} attemptId={attemptId} onChanged={setState} /></TabsContent>
        <TabsContent value="conops"><ConopsTab state={state} attemptId={attemptId} onSaved={setState} /></TabsContent>
        <TabsContent value="data"><DataBudgetTab state={state} attemptId={attemptId} onSaved={setState} /></TabsContent>
        <TabsContent value="power"><PowerBudgetTab state={state} attemptId={attemptId} onSaved={setState} /></TabsContent>
        <TabsContent value="link"><LinkBudgetTab state={state} attemptId={attemptId} onSaved={setState} /></TabsContent>
        <TabsContent value="mass"><MassBudgetTab state={state} attemptId={attemptId} onSaved={setState} /></TabsContent>
        <TabsContent value="cost"><CostBudgetTab state={state} attemptId={attemptId} onSaved={setState} /></TabsContent>
        <TabsContent value="dashboard"><DashboardTab state={state} /></TabsContent>
      </Tabs>
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
  const [saveError, setSaveError] = useState("");

  const save = async () => {
    setSaving(true);
    setSaveError("");
    try {
      const next = await updateDesign(state.attempt_id, {
        design_name: name, design_objective: objective, orbit_type: orbitType,
        orbit_duration_min: Number(orbitDuration), orbits_per_day: Number(orbitsPerDay),
        selected_cubesat_size: cubesatSize,
      });
      onSaved(next);
    } catch (err) {
      setSaveError(errorDetail(err, "Couldn't save mission setup."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="p-5 flex flex-col gap-4 max-w-xl">
      <div className="flex flex-col gap-1.5"><label className={labelCls}>Mission name</label><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></div>
      <div className="flex flex-col gap-1.5"><label className={labelCls}>Objective</label><textarea className={inputCls} rows={3} value={objective} onChange={(e) => setObjective(e.target.value)} /></div>
      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-1.5">
          <label className={labelCls}>Orbit type</label>
          <select className={inputCls} value={orbitType} onChange={(e) => setOrbitType(e.target.value)}>
            {["LEO", "MEO", "GEO", "SSO", "Custom"].map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label className={labelCls}>CubeSat size</label>
          <select className={inputCls} value={cubesatSize} onChange={(e) => setCubesatSize(e.target.value)}>
            {state.cubesat_presets.map((p) => <option key={p.size} value={p.size}>{p.size} ({p.max_mass_kg}kg, {p.available_volume_cm3}cm&sup3;)</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1.5"><label className={labelCls}>Orbit duration (min)</label><input type="number" className={inputCls} value={orbitDuration} onChange={(e) => setOrbitDuration(Number(e.target.value))} /></div>
        <div className="flex flex-col gap-1.5"><label className={labelCls}>Orbits per day</label><input type="number" className={inputCls} value={orbitsPerDay} onChange={(e) => setOrbitsPerDay(Number(e.target.value))} /></div>
      </div>
      <Button className="w-fit" onClick={() => void save()} disabled={saving}>{saving ? "Saving..." : "Save"}</Button>
      {saveError && <p className="text-xs text-destructive">{saveError}</p>}
    </Card>
  );
}

// ── Components ───────────────────────────────────────────────────────────

function ComponentsTab({ state, attemptId, onChanged }: { state: DesignState; attemptId: string; onChanged: (s: DesignState) => void }) {
  const [library, setLibrary] = useState<DesignLibraryComponent[]>([]);
  const [error, setError] = useState("");

  useEffect(() => { fetchDesignLibrary().then(setLibrary).catch(() => {}); }, []);

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

  const bySubsystem = library.reduce<Record<string, DesignLibraryComponent[]>>((acc, c) => {
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
            <div key={c.id} className="flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-xl ring-1 ring-border">
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">{c.component_name}</p>
                <p className="text-xs text-muted-foreground">{c.subsystem} &middot; {c.mass_per_unit_g ?? 0}g &middot; {c.voltage_v ?? 0}V/{c.current_ma ?? 0}mA</p>
              </div>
              <button onClick={() => void remove(c.id)} className="text-muted-foreground hover:text-destructive shrink-0"><Trash2 className="size-4" /></button>
            </div>
          ))}
        </div>
      </Card>
      <Card className="p-5 flex flex-col gap-4">
        <p className="text-sm font-semibold">Component library</p>
        {Object.entries(bySubsystem).map(([subsystem, comps]) => (
          <div key={subsystem} className="flex flex-col gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{subsystem}</p>
            <div className="grid sm:grid-cols-2 gap-2">
              {comps.map((c) => (
                <button
                  key={c.id} onClick={() => void add(c.id)}
                  className="text-left px-3.5 py-2.5 rounded-xl ring-1 ring-border hover:bg-muted/50 transition-colors"
                >
                  <p className="text-sm font-medium">{c.component_name}</p>
                  <p className="text-xs text-muted-foreground">{c.scaled_mass_g ?? 0}g &middot; {c.voltage_v ?? 0}V &middot; ${c.assumed_cost_usd ?? 0}</p>
                </button>
              ))}
            </div>
          </div>
        ))}
      </Card>
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

function LockedNotice() {
  return (
    <Card className="p-5 flex items-center gap-2 text-sm text-muted-foreground">
      <Lock className="size-4" /> Your instructor hasn't unlocked this step yet.
    </Card>
  );
}

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

  if (state.locked_steps.includes("data_budget")) return <LockedNotice />;

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

  if (state.locked_steps.includes("power_budget")) return <LockedNotice />;

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

  if (state.locked_steps.includes("mass_budget")) return <LockedNotice />;

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

  if (state.locked_steps.includes("cost_budget")) return <LockedNotice />;

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

  const applyPreset = (b: string) => {
    setBand(b);
    const p = state.band_presets[b];
    if (p) setFields(p);
  };

  const save = async () => {
    setSaving(true);
    setSaveError("");
    try {
      onSaved(await saveLinkBudget(attemptId, { band_profile: band, notes: null, ...fields }));
    } catch (err) {
      setSaveError(errorDetail(err, "Couldn't save the link budget."));
    } finally {
      setSaving(false);
    }
  };

  if (state.locked_steps.includes("link_budget")) return <LockedNotice />;

  return (
    <Card className="p-5 flex flex-col gap-4 max-w-xl">
      <div className="text-sm">
        Status: <b className={state.dashboard.link.status === "Good Link" ? "text-emerald-500" : "text-destructive"}>{state.dashboard.link.status}</b>
        {" "}&middot; Margin: <b>{state.dashboard.link.margin_db.toFixed(2)} dB</b>
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
            <input type="number" className={inputCls} value={fields[key]}
              onChange={(e) => setFields((p) => ({ ...p, [key]: Number(e.target.value) }))} />
          </div>
        ))}
      </div>
      <Button className="w-fit" onClick={() => void save()} disabled={saving}>{saving ? "Saving..." : "Save link budget"}</Button>
      {saveError && <p className="text-xs text-destructive">{saveError}</p>}
    </Card>
  );
}

// ── Dashboard ────────────────────────────────────────────────────────────

function DashboardTab({ state }: { state: DesignState }) {
  const d = state.dashboard;
  return (
    <div className="flex flex-col gap-4">
      <Card className="p-5 flex items-center gap-3">
        {d.all_valid ? <CheckCircle2 className="size-6 text-emerald-500" /> : <XCircle className="size-6 text-muted-foreground" />}
        <p className="text-sm font-semibold">{d.all_valid ? "Design is ready" : "Design is not ready yet"}</p>
      </Card>
      <Card className="p-5">
        <div className="grid sm:grid-cols-2 gap-3">
          {Object.entries(d.steps).map(([key, status]) => (
            <div key={key} className="flex items-center justify-between px-3.5 py-2.5 rounded-xl ring-1 ring-border">
              <span className="text-sm capitalize">{key.replace(/_/g, " ")}</span>
              <StepBadge status={status} />
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
