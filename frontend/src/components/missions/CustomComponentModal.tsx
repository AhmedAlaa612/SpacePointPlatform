/** Custom component creation and editing modal (student-defined parts).
 *
 * Collects the 10 MADAR custom specs plus required physical/budget inputs
 * (mass, dimensions, cost in AED) and an optional component image.
 * Power is shown as a read-only auto-calculation (voltage x current, 1V x 1mA = 1mW).
 *
 * Supports both CREATE mode (creates part and adds to mission design)
 * and EDIT mode (updates definition, specs, image and syncs design snapshots).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Image as ImageIcon, Trash2, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  CUSTOM_SUBSYSTEMS,
  createCustomComponent,
  updateCustomComponent,
  uploadCustomComponentImage,
  type DesignCustomComponent,
  type DesignState,
} from "@/api/missionsDesign";
import { isAxiosError } from "axios";

const inputCls = "h-12 px-4 border border-border bg-card text-foreground rounded-xl text-base focus:outline-none focus:border-primary transition-colors w-full";
const labelCls = "text-sm font-semibold uppercase tracking-wide text-muted-foreground";

export interface CustomComponentForm {
  component_name: string;
  subsystem: string;
  purpose_function: string;
  voltage_v: string;
  current_ma: string;
  pins_used: string;
  measurement_output: string;
  measurement_range: string;
  datasheet_reference: string;
  mass_g: string;
  length_mm: string;
  width_mm: string;
  height_mm: string;
  cost_aed: string;
  quantity: string;
}

const EMPTY: CustomComponentForm = {
  component_name: "", subsystem: "Payload", purpose_function: "",
  voltage_v: "", current_ma: "", pins_used: "", measurement_output: "",
  measurement_range: "", datasheet_reference: "",
  mass_g: "", length_mm: "", width_mm: "", height_mm: "",
  cost_aed: "", quantity: "1",
};

function num(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function CustomComponentModal({
  attemptId,
  open,
  onOpenChange,
  onCreated,
  initialComponent,
  onUpdated,
}: {
  attemptId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (s: DesignState) => void;
  initialComponent?: DesignCustomComponent | null;
  onUpdated?: (c: DesignCustomComponent) => void;
}) {
  const isEdit = !!initialComponent;
  const [form, setForm] = useState<CustomComponentForm>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [removeExistingImage, setRemoveExistingImage] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sync state whenever modal opens or initialComponent changes
  useEffect(() => {
    if (open) {
      setError("");
      setImageFile(null);
      setRemoveExistingImage(false);
      if (initialComponent) {
        setForm({
          component_name: initialComponent.component_name || "",
          subsystem: initialComponent.subsystem || "Payload",
          purpose_function: initialComponent.purpose_function || "",
          voltage_v: String(initialComponent.voltage_v ?? ""),
          current_ma: String(initialComponent.current_ma ?? ""),
          pins_used: initialComponent.pins_used || "",
          measurement_output: initialComponent.measurement_output || "",
          measurement_range: initialComponent.measurement_range || "",
          datasheet_reference: initialComponent.datasheet_reference || "",
          mass_g: String(initialComponent.mass_g ?? ""),
          length_mm: String(initialComponent.length_mm ?? ""),
          width_mm: String(initialComponent.width_mm ?? ""),
          height_mm: String(initialComponent.height_mm ?? ""),
          cost_aed: String(initialComponent.cost_aed ?? ""),
          quantity: "1",
        });
        setImagePreview(initialComponent.image_url || null);
      } else {
        setForm(EMPTY);
        setImagePreview(null);
      }
    }
  }, [open, initialComponent]);

  const set = (key: keyof CustomComponentForm, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  // Handle local image file selection
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 4 * 1024 * 1024) {
      setError("Image must be under 4 MB.");
      return;
    }
    const suffix = file.name.split(".").pop()?.toLowerCase();
    if (!suffix || !["png", "jpg", "jpeg", "webp"].includes(suffix)) {
      setError("Image must be PNG, JPG or WebP.");
      return;
    }
    setError("");
    setImageFile(file);
    setRemoveExistingImage(false);
    const objectUrl = URL.createObjectURL(file);
    setImagePreview(objectUrl);
  };

  const handleRemoveImage = () => {
    setImageFile(null);
    setImagePreview(null);
    setRemoveExistingImage(true);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // Read-only preview — the server computes the real value at snapshot time.
  const powerPreview = useMemo(() => {
    const v = num(form.voltage_v);
    const i = num(form.current_ma);
    if (v == null || i == null) return null;
    const mw = v * i;
    return { mw, w: mw / 1000 };
  }, [form.voltage_v, form.current_ma]);

  const submit = async () => {
    setSaving(true);
    setError("");
    try {
      let imageBucket: string | null | undefined = undefined;
      let imagePath: string | null | undefined = undefined;

      // If a new image was chosen, upload it first
      if (imageFile) {
        const uploadRes = await uploadCustomComponentImage(attemptId, imageFile);
        imageBucket = uploadRes.image_bucket;
        imagePath = uploadRes.image_path;
      } else if (removeExistingImage) {
        imageBucket = null;
        imagePath = null;
      }

      if (isEdit && initialComponent) {
        // Edit existing custom component
        const updatePayload: Record<string, any> = {
          component_name: form.component_name.trim(),
          subsystem: form.subsystem,
          purpose_function: form.purpose_function.trim(),
          voltage_v: Number(form.voltage_v),
          current_ma: Number(form.current_ma),
          pins_used: form.pins_used.trim(),
          measurement_output: form.measurement_output.trim(),
          measurement_range: form.measurement_range.trim() || null,
          datasheet_reference: form.datasheet_reference.trim() || null,
          mass_g: Number(form.mass_g),
          length_mm: Number(form.length_mm),
          width_mm: Number(form.width_mm),
          height_mm: Number(form.height_mm),
          cost_aed: Number(form.cost_aed),
        };
        if (imageBucket !== undefined) updatePayload.image_bucket = imageBucket;
        if (imagePath !== undefined) updatePayload.image_path = imagePath;

        const updated = await updateCustomComponent(attemptId, initialComponent.id, updatePayload);
        onOpenChange(false);
        onUpdated?.(updated);
      } else {
        // Create new custom component
        const state = await createCustomComponent(attemptId, {
          component_name: form.component_name.trim(),
          subsystem: form.subsystem,
          purpose_function: form.purpose_function.trim(),
          voltage_v: Number(form.voltage_v),
          current_ma: Number(form.current_ma),
          pins_used: form.pins_used.trim(),
          measurement_output: form.measurement_output.trim(),
          measurement_range: form.measurement_range.trim() || null,
          datasheet_reference: form.datasheet_reference.trim() || null,
          mass_g: Number(form.mass_g),
          length_mm: Number(form.length_mm),
          width_mm: Number(form.width_mm),
          height_mm: Number(form.height_mm),
          cost_aed: Number(form.cost_aed),
          quantity: Math.max(1, Math.floor(Number(form.quantity) || 1)),
          image_bucket: imageBucket ?? null,
          image_path: imagePath ?? null,
        });
        setForm(EMPTY);
        setImageFile(null);
        setImagePreview(null);
        onOpenChange(false);
        onCreated?.(state);
      }
    } catch (err) {
      if (isAxiosError(err)) {
        const detail = err.response?.data?.detail;
        if (typeof detail === "string") { setError(detail); }
        else if (Array.isArray(detail)) {
          setError(detail.map((d) => `${(d.loc ?? []).join(".")}: ${d.msg}`).join("; "));
        } else { setError(isEdit ? "Couldn't update this component. Check highlighted fields." : "Couldn't create this component. Check the highlighted requirements."); }
      } else {
        setError(isEdit ? "Couldn't update this component. Check highlighted fields." : "Couldn't create this component. Check the highlighted requirements.");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[720px] max-w-[95vw] w-[95vw] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? `Edit "${initialComponent.component_name}"` : "Customize component for MADAR Mission"}</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground -mt-2">
          {isEdit
            ? "Update your custom part specs, description, or component image."
            : "Define your custom payload, sensor, or subsystem module. Visible only to you (and your team) and staff."}
        </p>

        <div className="flex flex-col gap-6 mt-2">
          {/* Section 1: identity & image */}
          <div className="flex flex-col gap-3">
            <p className="text-sm font-bold uppercase tracking-wider text-primary">Identity &amp; architecture</p>
            <div className="flex flex-col gap-2">
              <label className={labelCls}>1. Component name *</label>
              <input className={inputCls} value={form.component_name} onChange={(e) => set("component_name", e.target.value)} placeholder="e.g. Optical Camera Sensor HS-100" maxLength={128} />
            </div>
            <div className="flex flex-col gap-2">
              <label className={labelCls}>2. Module / type (subsystem) *</label>
              <select className={`${inputCls} cursor-pointer`} value={form.subsystem} onChange={(e) => set("subsystem", e.target.value)}>
                {CUSTOM_SUBSYSTEMS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-2">
              <label className={labelCls}>3. Purpose / function</label>
              <textarea className={`${inputCls} h-auto min-h-[84px] py-3`} value={form.purpose_function} onChange={(e) => set("purpose_function", e.target.value)} placeholder="What does it do during the mission?" />
            </div>

            {/* Optional Component Image */}
            <div className="flex flex-col gap-2">
              <label className={labelCls}>Component Image (optional)</label>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={handleFileChange}
              />
              {imagePreview ? (
                <div className="flex items-center gap-4 p-3 rounded-xl border border-border bg-card">
                  <img
                    src={imagePreview}
                    alt="Component preview"
                    className="size-16 rounded-lg object-cover ring-1 ring-border shrink-0"
                  />
                  <div className="flex flex-col gap-1 min-w-0">
                    <p className="text-sm font-semibold truncate">
                      {imageFile ? imageFile.name : "Custom component image"}
                    </p>
                    <p className="text-xs text-muted-foreground">PNG, JPG, or WebP up to 4MB</p>
                    <div className="flex items-center gap-2 mt-1">
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs"
                        onClick={() => fileInputRef.current?.click()}
                      >
                        Change image
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-7 text-xs text-destructive hover:text-destructive gap-1"
                        onClick={handleRemoveImage}
                      >
                        <Trash2 className="size-3" /> Remove
                      </Button>
                    </div>
                  </div>
                </div>
              ) : (
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="flex flex-col items-center justify-center gap-2 p-5 border-2 border-dashed border-border rounded-xl cursor-pointer hover:border-primary/50 transition-colors bg-muted/20 hover:bg-muted/40"
                >
                  <div className="size-10 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                    <ImageIcon className="size-5" />
                  </div>
                  <div className="text-center">
                    <p className="text-sm font-medium text-foreground">Click to upload component photo / graphic</p>
                    <p className="text-xs text-muted-foreground mt-0.5">PNG, JPG or WebP (max 4 MB)</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Section 2: electrical */}
          <div className="flex flex-col gap-3 border-t border-border/60 pt-5">
            <p className="text-sm font-bold uppercase tracking-wider text-primary">Electrical &amp; interface</p>
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="flex flex-col gap-2">
                <label className={labelCls}>4. Operating voltage (V) *</label>
                <input type="number" className={inputCls} value={form.voltage_v} onChange={(e) => set("voltage_v", e.target.value)} placeholder="e.g. 3.3" />
              </div>
              <div className="flex flex-col gap-2">
                <label className={labelCls}>5. Current consumption (mA) *</label>
                <input type="number" className={inputCls} value={form.current_ma} onChange={(e) => set("current_ma", e.target.value)} placeholder="e.g. 150" />
              </div>
            </div>
            <div className="flex items-center gap-2 rounded-xl bg-primary/5 ring-1 ring-primary/20 px-4 py-3 text-sm">
              <Zap className="size-4 text-primary shrink-0" />
              {powerPreview
                ? <span>Power: {form.voltage_v}V × {form.current_ma}mA = <b>{powerPreview.mw.toFixed(1)} mW</b> ({powerPreview.w.toFixed(3)} W) — auto-calculated</span>
                : <span className="text-muted-foreground">Power auto-calculates from voltage × current.</span>}
            </div>
            <div className="flex flex-col gap-2">
              <label className={labelCls}>6. Pins used (names / functions) *</label>
              <textarea className={`${inputCls} h-auto min-h-[72px] py-3`} value={form.pins_used} onChange={(e) => set("pins_used", e.target.value)} placeholder="Pin 1: 3V3, Pin 2: GND, Pin 3: SPI_MOSI…" />
            </div>
          </div>

          {/* Section 3: data */}
          <div className="flex flex-col gap-3 border-t border-border/60 pt-5">
            <p className="text-sm font-bold uppercase tracking-wider text-primary">Instrument data &amp; datasheet</p>
            <div className="flex flex-col gap-2">
              <label className={labelCls}>7. Measurement / output *</label>
              <input className={inputCls} value={form.measurement_output} onChange={(e) => set("measurement_output", e.target.value)} placeholder="What data or signal does it provide?" />
            </div>
            <div className="flex flex-col gap-2">
              <label className={labelCls}>8. Measurement range</label>
              <input className={inputCls} value={form.measurement_range} onChange={(e) => set("measurement_range", e.target.value)} placeholder="e.g. 400nm – 900nm (VNIR)" />
            </div>
            <div className="flex flex-col gap-2">
              <label className={labelCls}>10. Datasheet reference (link / name)</label>
              <input className={inputCls} value={form.datasheet_reference} onChange={(e) => set("datasheet_reference", e.target.value)} placeholder="https://… or manufacturer document name" maxLength={512} />
            </div>
          </div>

          {/* Section 4: physical & budget (required) */}
          <div className="flex flex-col gap-3 border-t border-border/60 pt-5">
            <p className="text-sm font-bold uppercase tracking-wider text-primary">Physical &amp; budget (required)</p>
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="flex flex-col gap-2">
                <label className={labelCls}>Mass (g) *</label>
                <input type="number" className={inputCls} value={form.mass_g} onChange={(e) => set("mass_g", e.target.value)} placeholder="e.g. 65" />
              </div>
              <div className="flex flex-col gap-2">
                <label className={labelCls}>Cost (AED) *</label>
                <input type="number" className={inputCls} value={form.cost_aed} onChange={(e) => set("cost_aed", e.target.value)} placeholder="e.g. 450" />
              </div>
              <div className="flex flex-col gap-2">
                <label className={labelCls}>Length (mm) *</label>
                <input type="number" className={inputCls} value={form.length_mm} onChange={(e) => set("length_mm", e.target.value)} placeholder="e.g. 38" />
              </div>
              <div className="flex flex-col gap-2">
                <label className={labelCls}>Width (mm) *</label>
                <input type="number" className={inputCls} value={form.width_mm} onChange={(e) => set("width_mm", e.target.value)} placeholder="e.g. 38" />
              </div>
              <div className="flex flex-col gap-2">
                <label className={labelCls}>Height (mm) *</label>
                <input type="number" className={inputCls} value={form.height_mm} onChange={(e) => set("height_mm", e.target.value)} placeholder="e.g. 25" />
              </div>
              {!isEdit && (
                <div className="flex flex-col gap-2">
                  <label className={labelCls}>Quantity</label>
                  <input type="number" className={inputCls} value={form.quantity} onChange={(e) => set("quantity", e.target.value)} min={1} />
                </div>
              )}
            </div>
          </div>

          {error && <p className="text-xs text-destructive">{error}</p>}

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Cancel</Button>
            <Button onClick={() => void submit()} disabled={saving}>
              {saving ? (isEdit ? "Saving changes…" : "Creating…") : (isEdit ? "Save changes" : "Create component")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
