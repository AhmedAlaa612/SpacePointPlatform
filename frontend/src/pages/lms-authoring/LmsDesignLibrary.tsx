/** The CubeSat component library manager (Design v2, 7D-7).
 *
 * Madar had this and the port dropped it, so adding or correcting a
 * component meant a developer editing a seed script and re-running it. This
 * puts it back in the browser.
 *
 * Two things about it are deliberate and worth knowing before you edit:
 *
 * 1. **There is no delete.** Only retire. Madar's delete cascaded — removing
 *    a component wiped it from every student's design along with their
 *    budget entries (F1, rated Critical). Retiring hides it from new
 *    designs and touches nothing that exists.
 * 2. **This catalog is global.** Every design mission reads it, so an edit
 *    is seen everywhere. Finished designs keep the specs they were built
 *    with (F2 snapshots), but a live in-progress design picks up the new
 *    value. The "used in N designs" count is there so you can see the blast
 *    radius before changing a spec.
 */
import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { AlertTriangle, Plus, Search, Upload } from "lucide-react";
import * as XLSX from "xlsx";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  bulkImportLibrary, createLibraryComponent, listLibrary, setLibraryRetired,
  updateLibraryComponent, uploadLibraryImage, SUBSYSTEMS,
  type LibraryComponentAdmin, type LibraryComponentInput,
} from "@/api/missionsLibrary";

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail;
  return fallback;
}

const inputCls = "h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors w-full";
const labelCls = "text-[10px] font-semibold uppercase tracking-wide text-muted-foreground";

const NUMERIC_FIELDS = new Set([
  "length_mm", "width_mm", "height_mm", "scaled_mass_g", "voltage_v", "current_ma", "assumed_cost_usd",
]);

const EDITABLE: { key: keyof LibraryComponentInput; label: string; wide?: boolean }[] = [
  { key: "component_name", label: "Name", wide: true },
  { key: "subsystem", label: "Subsystem" },
  { key: "component_code", label: "Code" },
  { key: "tag", label: "Tag" },
  { key: "example_role", label: "Role", wide: true },
  { key: "scaled_description", label: "Description", wide: true },
  { key: "key_specs", label: "Key specs", wide: true },
  { key: "scaled_mass_g", label: "Mass (g)" },
  { key: "voltage_v", label: "Voltage (V)" },
  { key: "current_ma", label: "Current (mA)" },
  { key: "assumed_cost_usd", label: "Cost (USD)" },
  { key: "length_mm", label: "L (mm)" },
  { key: "width_mm", label: "W (mm)" },
  { key: "height_mm", label: "H (mm)" },
  { key: "data_size", label: "Data size" },
  { key: "temperature_range", label: "Temp range" },
  { key: "datasheet_url", label: "Datasheet URL", wide: true },
  { key: "notes", label: "Notes", wide: true },
];

function Editor({ initial, onSave, onCancel, saving }: {
  initial: Partial<LibraryComponentAdmin>;
  onSave: (body: LibraryComponentInput) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<Record<string, string>>(() =>
    Object.fromEntries(EDITABLE.map((f) => [f.key, initial[f.key] == null ? "" : String(initial[f.key])])));

  const submit = () => {
    const body: Record<string, unknown> = {};
    for (const f of EDITABLE) {
      const raw = (form[f.key] ?? "").trim();
      if (NUMERIC_FIELDS.has(f.key)) body[f.key] = raw === "" ? null : Number(raw);
      else body[f.key] = raw === "" ? null : raw;
    }
    onSave(body as LibraryComponentInput);
  };

  return (
    <div className="grid sm:grid-cols-4 gap-3 p-4 rounded-xl ring-1 ring-primary/30 bg-primary/5">
      {EDITABLE.map((f) => (
        <div key={f.key} className={`flex flex-col gap-1 ${f.wide ? "sm:col-span-2" : ""}`}>
          <label className={labelCls}>{f.label}</label>
          {f.key === "subsystem" ? (
            <select className={inputCls} value={form.subsystem ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, subsystem: e.target.value }))}>
              <option value="">Select...</option>
              {SUBSYSTEMS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          ) : (
            <input
              className={inputCls}
              type={NUMERIC_FIELDS.has(f.key) ? "number" : "text"}
              value={form[f.key] ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
            />
          )}
        </div>
      ))}
      <div className="sm:col-span-4 flex items-center gap-2">
        <Button size="sm" onClick={submit} disabled={saving || !form.component_name?.trim() || !form.subsystem}>
          {saving ? "Saving..." : "Save"}
        </Button>
        <Button size="sm" variant="outline" onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
}

export default function LmsDesignLibrary() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [subsystem, setSubsystem] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const imageRefs = useRef<Record<string, HTMLInputElement | null>>({});

  // react-query, matching the rest of `/lms-authoring` — and it keeps the
  // fetch out of an effect, which this repo's lint rules disallow.
  const { data: rows = [], isLoading: loading } = useQuery({
    queryKey: ["design-library", subsystem, search],
    queryFn: () => listLibrary({ subsystem: subsystem || undefined, search: search || undefined }),
  });
  const load = () => void queryClient.invalidateQueries({ queryKey: ["design-library"] });

  const handleSave = async (id: string | null, body: LibraryComponentInput) => {
    setSaving(true);
    setError("");
    try {
      if (id) await updateLibraryComponent(id, body);
      else await createLibraryComponent(body);
      setEditingId(null);
      setCreating(false);
      load();
    } catch (err) {
      setError(errorDetail(err, "Couldn't save this component."));
    } finally {
      setSaving(false);
    }
  };

  const handleRetire = async (row: LibraryComponentAdmin) => {
    setError("");
    try {
      await setLibraryRetired(row.id, row.is_active);
      load();
    } catch (err) {
      setError(errorDetail(err, "Couldn't change this component's status."));
    }
  };

  const handleImage = async (id: string, file: File) => {
    setError("");
    try {
      await uploadLibraryImage(id, file);
      load();
    } catch (err) {
      setError(errorDetail(err, "Couldn't upload that image."));
    }
  };

  /** Spreadsheet parsing happens here, not on the server: `xlsx` is already
   * a frontend dependency, and a malformed sheet fails in the uploader's own
   * browser where they can see it rather than as a 500. */
  const handleBulk = async (file: File) => {
    setError("");
    setNotice("");
    try {
      const wb = XLSX.read(await file.arrayBuffer());
      const sheet = wb.Sheets[wb.SheetNames[0]];
      const raw = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet);
      const components = raw.map((r) => {
        const out: Record<string, unknown> = {};
        for (const [k, v] of Object.entries(r)) {
          const key = k.trim().toLowerCase().replace(/[\s-]+/g, "_");
          if (v === "" || v == null) continue;
          out[key] = NUMERIC_FIELDS.has(key) ? Number(v) : String(v);
        }
        return out;
      }).filter((r) => r.component_name && r.subsystem) as LibraryComponentInput[];

      if (components.length === 0) {
        setError("No usable rows found. The sheet needs at least 'component_name' and 'subsystem' columns.");
        return;
      }
      const result = await bulkImportLibrary(components);
      setNotice(`Imported ${result.created} new, updated ${result.updated}.` +
        (result.errors.length ? ` ${result.errors.length} row(s) skipped.` : ""));
      load();
    } catch (err) {
      setError(errorDetail(err, "Couldn't read that spreadsheet."));
    }
  };

  return (
    <div className="mx-auto max-w-[1200px] px-5 sm:px-8 py-6 flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-extrabold tracking-tight">Component library</h1>
          <p className="text-xs text-muted-foreground mt-1 max-w-[70ch] leading-relaxed">
            The shared CubeSat catalog every design mission reads. Edits are visible to all of them —
            finished designs keep the specs they were built with, but a design still in progress will
            pick up the change.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileRef} type="file" accept=".xlsx,.xls,.csv" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleBulk(f); e.target.value = ""; }}
          />
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => fileRef.current?.click()}>
            <Upload className="size-3.5" /> Import spreadsheet
          </Button>
          <Button size="sm" className="gap-1.5" onClick={() => { setCreating(true); setEditingId(null); }}>
            <Plus className="size-3.5" /> Add component
          </Button>
        </div>
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}
      {notice && <p className="text-xs text-emerald-600 dark:text-emerald-400">{notice}</p>}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
          <input
            className={`${inputCls} pl-9`} placeholder="Search by name or code"
            value={search} onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select className={`${inputCls} w-auto`} value={subsystem} onChange={(e) => setSubsystem(e.target.value)}>
          <option value="">All subsystems</option>
          {SUBSYSTEMS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {creating && (
        <Editor initial={{}} saving={saving} onCancel={() => setCreating(false)}
          onSave={(body) => void handleSave(null, body)} />
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : (
        <div className="flex flex-col gap-2">
          {rows.length === 0 && <p className="text-sm text-muted-foreground">No components match.</p>}
          {rows.map((row) => (
            <Card key={row.id} className={`p-4 flex flex-col gap-3 ${row.is_active ? "" : "opacity-60"}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-3 min-w-0">
                  {row.image_url
                    ? <img src={row.image_url} alt="" className="size-11 rounded-lg object-cover ring-1 ring-border shrink-0" />
                    : <div className="size-11 rounded-lg ring-1 ring-border bg-muted shrink-0" />}
                  <div className="min-w-0">
                    <p className="text-sm font-semibold">
                      {row.component_name}
                      {!row.is_active && <span className="ml-2 text-[10px] uppercase tracking-wide text-muted-foreground">retired</span>}
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      {row.subsystem}
                      {row.component_code && ` · ${row.component_code}`}
                      {` · ${row.scaled_mass_g ?? 0}g · ${row.voltage_v ?? 0}V/${row.current_ma ?? 0}mA · $${row.assumed_cost_usd ?? 0}`}
                    </p>
                    {row.example_role && <p className="text-[11px] text-primary mt-0.5">{row.example_role}</p>}
                    <p className="text-[10px] text-muted-foreground mt-1">
                      Used in {row.used_in_designs} design{row.used_in_designs === 1 ? "" : "s"}
                      {row.updated_by_name && ` · last edited by ${row.updated_by_name}`}
                      {row.updated_at && ` on ${new Date(row.updated_at).toLocaleDateString()}`}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <input
                    ref={(el) => { imageRefs.current[row.id] = el; }}
                    type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleImage(row.id, f); e.target.value = ""; }}
                  />
                  <Button size="sm" variant="outline" onClick={() => imageRefs.current[row.id]?.click()}>Image</Button>
                  <Button size="sm" variant="outline"
                    onClick={() => { setEditingId(editingId === row.id ? null : row.id); setCreating(false); }}>
                    {editingId === row.id ? "Close" : "Edit"}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => void handleRetire(row)}>
                    {row.is_active ? "Retire" : "Restore"}
                  </Button>
                </div>
              </div>

              {editingId === row.id && (
                <>
                  {row.used_in_designs > 0 && (
                    <div className="flex items-start gap-2 rounded-xl ring-1 ring-amber-500/30 bg-amber-500/5 px-3 py-2">
                      <AlertTriangle className="size-3.5 text-amber-500 shrink-0 mt-0.5" />
                      <p className="text-[11px] leading-relaxed">
                        {row.used_in_designs} design{row.used_in_designs === 1 ? " has" : "s have"} used this
                        component. Completed designs keep the specs they were built with, but any design still
                        in progress will pick up whatever you change here.
                      </p>
                    </div>
                  )}
                  <Editor initial={row} saving={saving} onCancel={() => setEditingId(null)}
                    onSave={(body) => void handleSave(row.id, body)} />
                </>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
