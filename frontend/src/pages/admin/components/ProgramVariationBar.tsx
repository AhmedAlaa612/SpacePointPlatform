import { useState, useMemo } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Copy, Layers, Pencil, Plus, Settings2, Star, Trash2 } from "lucide-react"
import type { CompletionRuleType, PricingModel, Program, ProgramVariation } from "@/types/sessions"
import {
  createProgramVariationApi,
  deleteProgramVariationApi,
  getProgramsApi,
  updateProgramVariationApi,
  type VariationCarryBucket,
} from "@/api/sessions/programs"
import { getCohortsApi } from "@/api/sessions/cohorts"
import { listAssessmentConfigsApi } from "@/api/instructor_assessment"
import { Modal } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { cn, getErrorMessage } from "@/lib/utils"

const CARRY_OPTIONS: { key: VariationCarryBucket; label: string }[] = [
  { key: "days", label: "Days & Delivery Checklists" },
  { key: "roles", label: "Role Rates & Slots" },
  { key: "pre_quiz", label: "Pre-Session Quiz" },
  { key: "lms", label: "LMS Checklist" },
  { key: "component_config", label: "CubeSat Components" },
  { key: "hints", label: "Hint Stations" },
  { key: "materials", label: "Materials" },
  { key: "assessment", label: "Assessment Gate" },
  { key: "certificate", label: "Certificate Templates" },
  { key: "rubric", label: "Judging Rubric" },
  { key: "scalars", label: "Duration, Capacity & Pricing" },
]

export function ProgramVariationBar({
  program,
  variations,
  selectedVariationId,
  onSelectVariation,
  editingBase,
  onToggleEditingBase,
}: {
  program: Program
  variations: ProgramVariation[]
  selectedVariationId: string | null
  onSelectVariation: (id: string | null) => void
  editingBase: boolean
  onToggleEditingBase: (base: boolean) => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [createOpen, setCreateOpen] = useState(false)
  const [editingVar, setEditingVar] = useState<ProgramVariation | null>(null)

  const selected = variations.find((v) => v.id === selectedVariationId) ?? null

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ["program-variations", program.id] })
    qc.invalidateQueries({ queryKey: ["program-template", program.id] })
    qc.invalidateQueries({ queryKey: ["program-openings-defaults", program.id] })
  }

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteProgramVariationApi(program.id, id),
    onSuccess: () => {
      toast.success("Variation deleted")
      invalidateAll()
      onSelectVariation(null)
    },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Could not delete variation")),
  })

  const setDefaultMut = useMutation({
    mutationFn: (id: string) => updateProgramVariationApi(program.id, id, { is_default: true }),
    onSuccess: () => {
      toast.success("Default variation updated")
      invalidateAll()
    },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Could not update default")),
  })

  return (
    <div className="rounded-xl border border-border bg-card px-4 py-3 flex flex-col gap-2.5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          <span className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-muted-foreground shrink-0">
            <Layers size={13} className="text-primary" /> Variations
          </span>

          {variations.length === 0 ? (
            <span className="text-xs text-muted-foreground">
              Using Program Base defaults — add a variation for 4-Day vs 3-Day formats
            </span>
          ) : (
            <div className="flex items-center gap-1.5 flex-wrap">
              {variations.map((v) => {
                const active = !editingBase && selectedVariationId === v.id
                return (
                  <button
                    key={v.id}
                    type="button"
                    onClick={() => {
                      onToggleEditingBase(false)
                      onSelectVariation(v.id)
                    }}
                    className={cn(
                      "inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-semibold border transition-colors cursor-pointer",
                      active
                        ? "bg-primary text-primary-foreground border-primary shadow-sm"
                        : "bg-background text-foreground border-border hover:border-primary/50",
                      !v.is_active && "opacity-60",
                    )}
                  >
                    {v.is_default && (
                      <Star size={11} className={active ? "fill-current" : "fill-amber-400 text-amber-500"} />
                    )}
                    <span>{v.name}</span>
                    <span className={cn("text-[10px] font-medium", active ? "text-primary-foreground/80" : "text-muted-foreground")}>
                      · {v.days_count}d
                    </span>
                  </button>
                )
              })}

              <button
                type="button"
                onClick={() => onToggleEditingBase(true)}
                className={cn(
                  "inline-flex items-center gap-1 h-8 px-3 rounded-lg text-xs font-medium border border-dashed transition-colors cursor-pointer",
                  editingBase
                    ? "bg-muted text-foreground border-foreground/40 font-semibold"
                    : "text-muted-foreground border-border hover:text-foreground",
                )}
                title="View or edit shared Program Base defaults"
              >
                <Settings2 size={12} /> Program Base
              </button>
            </div>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {selected && !editingBase && (
            <>
              {!selected.is_default && (
                <button
                  type="button"
                  onClick={() => setDefaultMut.mutate(selected.id)}
                  disabled={setDefaultMut.isPending}
                  className="h-8 px-2.5 rounded-lg border border-border bg-background text-xs font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                  title="Set as default variation when creating a new cohort"
                >
                  Set default
                </button>
              )}
              <button
                type="button"
                onClick={() => setEditingVar(selected)}
                className="h-8 px-2.5 rounded-lg border border-border bg-background text-xs font-medium text-foreground hover:bg-muted transition-colors inline-flex items-center gap-1 cursor-pointer"
                title="Edit variation defaults & settings"
              >
                <Pencil size={12} /> Edit
              </button>
              <button
                type="button"
                onClick={() => {
                  const msg = selected.cohorts_count > 0
                    ? `Delete "${selected.name}"? ${selected.cohorts_count} existing cohort(s) will stay intact and keep their sessions.`
                    : `Delete variation "${selected.name}"?`
                  if (confirm(msg)) deleteMut.mutate(selected.id)
                }}
                disabled={deleteMut.isPending}
                className="h-8 w-8 rounded-lg border border-border bg-background text-rose-500 hover:bg-rose-500/10 transition-colors inline-flex items-center justify-center cursor-pointer"
                title="Delete variation"
              >
                <Trash2 size={13} />
              </button>
            </>
          )}

          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition-opacity cursor-pointer"
          >
            <Plus size={13} /> New Variation
          </button>
        </div>
      </div>

      {selected && !editingBase && (
        <div className="flex items-center gap-3 flex-wrap text-[11px] text-muted-foreground pt-1 border-t border-border/60">
          <span>
            Editing variation <strong className="text-foreground">{selected.name}</strong>
          </span>
          {selected.duration_hours != null && <span>· {selected.duration_hours}h/day</span>}
          {selected.default_capacity != null && <span>· {selected.default_capacity} seats</span>}
          {selected.pricing_model && (
            <span>· {selected.pricing_model === "free" ? "Free" : `AED ${selected.price ?? program.price ?? 0}`}</span>
          )}
          {selected.cohorts_count > 0 && <span>· Used by {selected.cohorts_count} cohort{selected.cohorts_count === 1 ? "" : "s"}</span>}
          <span className="ml-auto hidden sm:inline">Blank settings inherit from Program Base</span>
        </div>
      )}

      {createOpen && (
        <CreateVariationModal
          program={program}
          variations={variations}
          onClose={() => setCreateOpen(false)}
          onCreated={(v) => {
            invalidateAll()
            onToggleEditingBase(false)
            onSelectVariation(v.id)
            setCreateOpen(false)
          }}
        />
      )}

      {editingVar && (
        <EditVariationModal
          program={program}
          variation={editingVar}
          onClose={() => setEditingVar(null)}
          onSaved={() => {
            invalidateAll()
            setEditingVar(null)
          }}
        />
      )}
    </div>
  )
}

function CreateVariationModal({
  program,
  variations,
  onClose,
  onCreated,
}: {
  program: Program
  variations: ProgramVariation[]
  onClose: () => void
  onCreated: (v: ProgramVariation) => void
}) {
  const toast = useToast()
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [mode, setMode] = useState<"blank" | "duplicate" | "from_cohort">(
    variations.length > 0 ? "duplicate" : "blank",
  )
  const [sourceVariationId, setSourceVariationId] = useState(variations[0]?.id ?? "")
  const [sourceProgramId, setSourceProgramId] = useState(program.id)
  const [sourceCohortId, setSourceCohortId] = useState("")
  const [carry, setCarry] = useState<VariationCarryBucket[]>(() => CARRY_OPTIONS.map((c) => c.key))
  const [isDefault, setIsDefault] = useState(variations.length === 0)
  const [durationHours, setDurationHours] = useState("")
  const [capacity, setCapacity] = useState("")

  const { data: allPrograms = [] } = useQuery({
    queryKey: ["sessions-programs"],
    queryFn: getProgramsApi,
    enabled: mode === "from_cohort",
  })

  const { data: rawCohorts = [], isLoading: loadingCohorts } = useQuery({
    queryKey: ["cohorts-for-var-import", sourceProgramId],
    queryFn: () => getCohortsApi(sourceProgramId || undefined),
    enabled: mode === "from_cohort" && !!sourceProgramId,
  })

  const eligibleCohorts = useMemo(
    () =>
      rawCohorts.filter((c) => {
        const s = String(c.status).toLowerCase()
        const n = c.name.trim().toLowerCase()
        return s !== "draft" && !n.startsWith("[template]") && n !== "template"
      }),
    [rawCohorts],
  )

  const effectiveSourceCohortId =
    sourceCohortId && eligibleCohorts.some((c) => c.id === sourceCohortId)
      ? sourceCohortId
      : eligibleCohorts[0]?.id ?? ""

  const toggleCarry = (k: VariationCarryBucket) => {
    setCarry((prev) => (prev.includes(k) ? prev.filter((x) => x !== k) : [...prev, k]))
  }

  const createMut = useMutation({
    mutationFn: () =>
      createProgramVariationApi(program.id, {
        name: name.trim(),
        description: description.trim() || null,
        is_default: isDefault,
        mode,
        source_variation_id: mode === "duplicate" ? sourceVariationId || null : null,
        source_cohort_id: mode === "from_cohort" ? effectiveSourceCohortId || null : null,
        carry,
        duration_hours: durationHours.trim() ? Number(durationHours) : null,
        default_capacity: capacity.trim() ? Number(capacity) : null,
      }),
    onSuccess: (created) => {
      toast.success(`Created variation "${created.name}"`)
      onCreated(created)
    },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Failed to create variation")),
  })

  const canSubmit =
    Boolean(name.trim()) &&
    (mode !== "duplicate" || Boolean(sourceVariationId)) &&
    (mode !== "from_cohort" || Boolean(effectiveSourceCohortId))

  return (
    <Modal title="New Program Variation" onClose={onClose} maxWidth="max-w-lg">
      <div className="flex flex-col gap-3.5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Variation Name
            </span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. 4-Day Full, 3-Day Express, School Edition"
              autoFocus
              className="h-9 px-3 rounded-lg border border-border bg-background text-sm text-foreground focus:outline-none focus:border-primary"
            />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Notes (optional)
            </span>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="When should ops pick this variation?"
              className="h-9 px-3 rounded-lg border border-border bg-background text-sm text-foreground focus:outline-none focus:border-primary"
            />
          </label>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Starting Point
          </span>
          <div className="grid grid-cols-3 gap-2">
            {(
              [
                ["blank", "Blank", "Inherit base"],
                ["duplicate", "Duplicate", "Another variation"],
                ["from_cohort", "From Cohort", "Any program run"],
              ] as const
            ).map(([k, title, sub]) => {
              const disabled = k === "duplicate" && variations.length === 0
              return (
                <button
                  key={k}
                  type="button"
                  disabled={disabled}
                  onClick={() => setMode(k)}
                  className={cn(
                    "p-2.5 rounded-xl border text-left transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed",
                    mode === k
                      ? "border-primary bg-primary/10 ring-1 ring-primary text-foreground"
                      : "border-border bg-background text-muted-foreground hover:text-foreground",
                  )}
                >
                  <p className="text-xs font-semibold flex items-center gap-1">
                    {k === "from_cohort" && <Copy size={11} className="text-primary" />}
                    {title}
                  </p>
                  <p className="text-[11px] text-muted-foreground truncate">{sub}</p>
                </button>
              )
            })}
          </div>
        </div>

        {mode === "duplicate" && (
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Copy From Variation
            </span>
            <select
              value={sourceVariationId}
              onChange={(e) => setSourceVariationId(e.target.value)}
              className="h-9 px-3 rounded-lg border border-border bg-background text-xs font-medium text-foreground focus:outline-none focus:border-primary"
            >
              {variations.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name} ({v.days_count} days)
                </option>
              ))}
            </select>
          </label>
        )}

        {mode === "from_cohort" && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3 rounded-xl border border-border bg-muted/20">
            <label className="flex flex-col gap-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Source Program
              </span>
              <select
                value={sourceProgramId}
                onChange={(e) => {
                  setSourceProgramId(e.target.value)
                  setSourceCohortId("")
                }}
                className="h-9 px-2.5 rounded-lg border border-border bg-background text-xs font-medium text-foreground focus:outline-none focus:border-primary"
              >
                {allPrograms.length === 0 && <option value={program.id}>{program.name}</option>}
                {allPrograms.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}{p.id === program.id ? " (Current)" : ""}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Source Cohort
              </span>
              <select
                value={effectiveSourceCohortId}
                onChange={(e) => setSourceCohortId(e.target.value)}
                disabled={loadingCohorts || eligibleCohorts.length === 0}
                className="h-9 px-2.5 rounded-lg border border-border bg-background text-xs font-medium text-foreground focus:outline-none focus:border-primary disabled:opacity-50"
              >
                {eligibleCohorts.length === 0 ? (
                  <option value="">No cohorts in selected program</option>
                ) : (
                  eligibleCohorts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}{c.starts_on ? ` (${c.starts_on})` : ""}
                    </option>
                  ))
                )}
              </select>
            </label>
          </div>
        )}

        {mode !== "blank" && (
          <div className="flex flex-col gap-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Include From Source
            </span>
            <div className="grid grid-cols-2 gap-1.5">
              {CARRY_OPTIONS.map((opt) => (
                <label key={opt.key} className="flex items-center gap-2 text-xs text-foreground cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={carry.includes(opt.key)}
                    onChange={() => toggleCarry(opt.key)}
                    className="accent-primary"
                  />
                  <span className="truncate">{opt.label}</span>
                </label>
              ))}
            </div>
          </div>
        )}

        {mode === "blank" && (
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Duration / Day (hrs)
              </span>
              <input
                type="number"
                step="0.5"
                value={durationHours}
                onChange={(e) => setDurationHours(e.target.value)}
                placeholder={program.duration_hours != null ? `Base: ${program.duration_hours}` : "Inherit"}
                className="h-9 px-3 rounded-lg border border-border bg-background text-sm text-foreground"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Capacity
              </span>
              <input
                type="number"
                value={capacity}
                onChange={(e) => setCapacity(e.target.value)}
                placeholder={program.default_capacity != null ? `Base: ${program.default_capacity}` : "Inherit"}
                className="h-9 px-3 rounded-lg border border-border bg-background text-sm text-foreground"
              />
            </label>
          </div>
        )}

        <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer select-none">
          <input
            type="checkbox"
            checked={isDefault}
            onChange={(e) => setIsDefault(e.target.checked)}
            className="accent-primary"
          />
          Set as default variation for new cohorts
        </label>

        <div className="flex justify-end gap-2 pt-2 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-3 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-muted cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => createMut.mutate()}
            disabled={!canSubmit || createMut.isPending}
            className="h-9 px-4 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 disabled:opacity-50 cursor-pointer"
          >
            {createMut.isPending ? "Creating…" : "Create Variation"}
          </button>
        </div>
      </div>
    </Modal>
  )
}

function EditVariationModal({
  program,
  variation,
  onClose,
  onSaved,
}: {
  program: Program
  variation: ProgramVariation
  onClose: () => void
  onSaved: () => void
}) {
  const toast = useToast()
  const [name, setName] = useState(variation.name)
  const [description, setDescription] = useState(variation.description ?? "")
  const [isActive, setIsActive] = useState(variation.is_active)
  const [isDefault, setIsDefault] = useState(variation.is_default)
  const [durationHours, setDurationHours] = useState(variation.duration_hours != null ? String(variation.duration_hours) : "")
  const [capacity, setCapacity] = useState(variation.default_capacity != null ? String(variation.default_capacity) : "")
  const [pricingModel, setPricingModel] = useState<string>(variation.pricing_model ?? "")
  const [price, setPrice] = useState(variation.price != null ? String(variation.price) : "")
  const [ruleType, setRuleType] = useState<string>(variation.completion_rule_type ?? "")
  const [ruleValue, setRuleValue] = useState(variation.completion_rule_value != null ? String(variation.completion_rule_value) : "")
  const [posterUrl, setPosterUrl] = useState(variation.poster_template_url ?? "")
  const [assessmentId, setAssessmentId] = useState(variation.default_assessment_config_id ?? "")

  const { data: configs = [] } = useQuery({
    queryKey: ["assessment-configs"],
    queryFn: listAssessmentConfigsApi,
  })

  const saveMut = useMutation({
    mutationFn: () =>
      updateProgramVariationApi(program.id, variation.id, {
        name: name.trim(),
        description: description.trim() || null,
        is_active: isActive,
        is_default: isDefault,
        duration_hours: durationHours.trim() ? Number(durationHours) : null,
        default_capacity: capacity.trim() ? Number(capacity) : null,
        pricing_model: (pricingModel || null) as PricingModel | null,
        price: price.trim() ? Number(price) : null,
        completion_rule_type: (ruleType || null) as CompletionRuleType | null,
        completion_rule_value: ruleValue.trim() ? Number(ruleValue) : null,
        poster_template_url: posterUrl.trim() || null,
        default_assessment_config_id: assessmentId || null,
      }),
    onSuccess: () => {
      toast.success("Variation settings saved")
      onSaved()
    },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Failed to save variation")),
  })

  return (
    <Modal title={`Edit Variation — ${variation.name}`} onClose={onClose} maxWidth="max-w-lg">
      <div className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">
          Leave any field blank to inherit the Program Base default.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className="text-[11px] font-semibold uppercase text-muted-foreground">Name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-9 px-3 rounded-lg border border-border bg-background text-sm text-foreground"
            />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className="text-[11px] font-semibold uppercase text-muted-foreground">Description</span>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="h-9 px-3 rounded-lg border border-border bg-background text-sm text-foreground"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold uppercase text-muted-foreground">Duration / Day (hrs)</span>
            <input
              type="number"
              step="0.5"
              value={durationHours}
              onChange={(e) => setDurationHours(e.target.value)}
              placeholder={program.duration_hours != null ? `Base: ${program.duration_hours}` : "Inherit"}
              className="h-9 px-3 rounded-lg border border-border bg-background text-sm text-foreground"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold uppercase text-muted-foreground">Capacity</span>
            <input
              type="number"
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
              placeholder={program.default_capacity != null ? `Base: ${program.default_capacity}` : "Inherit"}
              className="h-9 px-3 rounded-lg border border-border bg-background text-sm text-foreground"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold uppercase text-muted-foreground">Pricing Model</span>
            <select
              value={pricingModel}
              onChange={(e) => setPricingModel(e.target.value)}
              className="h-9 px-2.5 rounded-lg border border-border bg-background text-sm text-foreground"
            >
              <option value="">Inherit ({program.pricing_model})</option>
              <option value="paid">Paid</option>
              <option value="free">Free</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold uppercase text-muted-foreground">Price (AED)</span>
            <input
              type="number"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder={program.price != null ? `Base: ${program.price}` : "Inherit"}
              className="h-9 px-3 rounded-lg border border-border bg-background text-sm text-foreground"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold uppercase text-muted-foreground">Completion Rule</span>
            <select
              value={ruleType}
              onChange={(e) => setRuleType(e.target.value)}
              className="h-9 px-2.5 rounded-lg border border-border bg-background text-sm text-foreground"
            >
              <option value="">Inherit ({program.completion_rule_type})</option>
              <option value="percentage">% of sessions</option>
              <option value="session_count">Session count</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold uppercase text-muted-foreground">Completion Value</span>
            <input
              type="number"
              value={ruleValue}
              onChange={(e) => setRuleValue(e.target.value)}
              placeholder={`Base: ${program.completion_rule_value}`}
              className="h-9 px-3 rounded-lg border border-border bg-background text-sm text-foreground"
            />
          </label>

          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className="text-[11px] font-semibold uppercase text-muted-foreground">Assessment Gate Override</span>
            <select
              value={assessmentId}
              onChange={(e) => setAssessmentId(e.target.value)}
              className="h-9 px-2.5 rounded-lg border border-border bg-background text-sm text-foreground"
            >
              <option value="">Inherit from Program Base</option>
              {configs.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className="text-[11px] font-semibold uppercase text-muted-foreground">Poster Template URL</span>
            <input
              type="url"
              value={posterUrl}
              onChange={(e) => setPosterUrl(e.target.value)}
              placeholder={program.poster_template_url || "Inherit from Program Base"}
              className="h-9 px-3 rounded-lg border border-border bg-background text-sm text-foreground"
            />
          </label>
        </div>

        <div className="flex items-center gap-4 pt-1">
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer select-none">
            <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} className="accent-primary" />
            Active for new cohorts
          </label>
          <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer select-none">
            <input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} className="accent-primary" />
            Default variation
          </label>
        </div>

        <div className="flex justify-end gap-2 pt-2 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-3 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-muted cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => saveMut.mutate()}
            disabled={!name.trim() || saveMut.isPending}
            className="h-9 px-4 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 disabled:opacity-50 cursor-pointer"
          >
            {saveMut.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </Modal>
  )
}
