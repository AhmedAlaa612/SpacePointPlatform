import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus, Pencil, Trash2 } from "lucide-react"
import type { Program, ProgramType, PricingModel, CompletionRuleType } from "@/types/sessions"
import { getProgramsApi, createProgramApi, updateProgramApi, deleteProgramApi } from "@/api/sessions/programs"
import { Modal, Field, ModalActions, Spinner } from "@/pages/admin/components/common"

const PROGRAM_TYPES: ProgramType[] = ["workshop", "course", "info_session"]
const PRICING_MODELS: PricingModel[] = ["paid", "free"]
const COMPLETION_RULE_TYPES: CompletionRuleType[] = ["percentage", "session_count"]

const PROGRAM_TYPE_LABEL: Record<ProgramType, string> = {
  workshop: "Workshop",
  course: "Course",
  info_session: "Info session",
}

const PRICING_MODEL_LABEL: Record<PricingModel, string> = {
  paid: "Paid",
  free: "Free",
}

const COMPLETION_RULE_LABEL: Record<CompletionRuleType, string> = {
  percentage: "% of sessions attended",
  session_count: "Number of sessions attended",
}

/* ================================================================== */
/* Programs page                                                       */
/* ================================================================== */
export default function Programs() {
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [editProgram, setEditProgram] = useState<Program | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  // The API refuses to delete a program that has cohorts (it would cascade
  // them, and their registrations, away) — surface that reason rather than
  // failing silently.
  const deleteMutation = useMutation({
    mutationFn: deleteProgramApi,
    onSuccess: () => {
      setDeleteError(null)
      queryClient.invalidateQueries({ queryKey: ["sessions-programs"] })
    },
    onError: (e: any) => setDeleteError(e?.response?.data?.detail ?? "Failed to delete program"),
  })

  const { data: programs = [], isLoading } = useQuery<Program[]>({
    queryKey: ["sessions-programs"],
    queryFn: getProgramsApi,
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground tracking-tight">Programs</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Workshop/course/info-session templates that cohorts run against</p>
        </div>
        <button
          onClick={() => setCreateOpen(true)}
          className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
        >
          <Plus size={14} /> New program
        </button>
      </div>

      {deleteError && (
        <div className="text-xs text-red-600 dark:text-red-400 bg-red-500/10 border border-red-500/30 rounded-xl px-3 py-2">
          {deleteError}
        </div>
      )}

      <div className="flex flex-col gap-2">
        {programs.map((p) => (
          <div
            key={p.id}
            className="flex items-center justify-between p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-medium text-foreground truncate">{p.name}</p>
                {!p.active && (
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-muted text-muted-foreground">Inactive</span>
                )}
              </div>
              <p className="text-xs text-muted-foreground truncate">
                {p.code} · {PROGRAM_TYPE_LABEL[p.program_type]} ·{" "}
                {p.pricing_model === "free" ? "Free" : `AED ${p.price ?? "—"}`}
              </p>
            </div>
            <div className="flex items-center gap-1 flex-shrink-0 ml-3">
              <button
                onClick={() => setEditProgram(p)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                title="Edit program"
              >
                <Pencil size={14} />
              </button>
              <button
                onClick={() => {
                  if (confirm(`Delete the program "${p.name}"? This only works if it has no cohorts.`)) {
                    deleteMutation.mutate(p.id)
                  }
                }}
                disabled={deleteMutation.isPending}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                title="Delete program"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}
        {programs.length === 0 && (
          <div className="flex items-center justify-center h-32 border border-dashed border-border rounded-2xl">
            <p className="text-sm text-muted-foreground">No programs yet</p>
          </div>
        )}
      </div>

      {createOpen && (
        <ProgramModal
          onClose={() => setCreateOpen(false)}
          onSuccess={() => { queryClient.invalidateQueries({ queryKey: ["sessions-programs"] }); setCreateOpen(false) }}
        />
      )}
      {editProgram && (
        <ProgramModal
          program={editProgram}
          onClose={() => setEditProgram(null)}
          onSuccess={() => { queryClient.invalidateQueries({ queryKey: ["sessions-programs"] }); setEditProgram(null) }}
        />
      )}
    </div>
  )
}

/* ================================================================== */
/* Create/edit program modal                                           */
/* ================================================================== */
function ProgramModal({ program, onClose, onSuccess }: {
  program?: Program; onClose: () => void; onSuccess: () => void
}) {
  const isEdit = !!program
  const [code, setCode] = useState(program?.code ?? "")
  const [name, setName] = useState(program?.name ?? "")
  const [programType, setProgramType] = useState<ProgramType>(program?.program_type ?? "workshop")
  const [pricingModel, setPricingModel] = useState<PricingModel>(program?.pricing_model ?? "free")
  const [price, setPrice] = useState(program?.price != null ? String(program.price) : "")
  const [defaultCapacity, setDefaultCapacity] = useState(program?.default_capacity != null ? String(program.default_capacity) : "")
  const [description, setDescription] = useState(program?.description ?? "")
  const [active, setActive] = useState(program?.active ?? true)
  const [completionRuleType, setCompletionRuleType] = useState<CompletionRuleType>(program?.completion_rule_type ?? "percentage")
  const [completionRuleValue, setCompletionRuleValue] = useState(
    program?.completion_rule_value != null ? String(program.completion_rule_value) : "70",
  )
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () => {
      const payload = {
        code: code.trim(),
        name: name.trim(),
        program_type: programType,
        pricing_model: pricingModel,
        description: description.trim() || undefined,
        price: price.trim() ? Number(price) : undefined,
        default_capacity: defaultCapacity.trim() ? Number(defaultCapacity) : undefined,
        active,
        completion_rule_type: completionRuleType,
        completion_rule_value: completionRuleValue.trim() ? Number(completionRuleValue) : undefined,
      }
      return isEdit ? updateProgramApi(program!.id, payload) : createProgramApi(payload)
    },
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to save program"),
  })

  return (
    <Modal title={isEdit ? `Edit program — ${program!.name}` : "New program"} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="Code">
          <input
            value={code} onChange={(e) => setCode(e.target.value)} placeholder="SATKIT-WS-2026-Q3" autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Name">
          <input
            value={name} onChange={(e) => setName(e.target.value)} placeholder="CubeSat Workshop"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Type">
          <select
            value={programType} onChange={(e) => setProgramType(e.target.value as ProgramType)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
          >
            {PROGRAM_TYPES.map((t) => <option key={t} value={t}>{PROGRAM_TYPE_LABEL[t]}</option>)}
          </select>
        </Field>
        <Field label="Pricing model">
          <select
            value={pricingModel} onChange={(e) => setPricingModel(e.target.value as PricingModel)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
          >
            {PRICING_MODELS.map((m) => <option key={m} value={m}>{PRICING_MODEL_LABEL[m]}</option>)}
          </select>
        </Field>
        {pricingModel !== "free" && (
          <Field label="Price (AED)">
            <input
              value={price} onChange={(e) => setPrice(e.target.value)} type="number" placeholder="250"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
        )}
        <Field label="Default capacity (optional)">
          <input
            value={defaultCapacity} onChange={(e) => setDefaultCapacity(e.target.value)} type="number" placeholder="20"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Completion requirement">
          <div className="flex gap-2">
            <select
              value={completionRuleType} onChange={(e) => setCompletionRuleType(e.target.value as CompletionRuleType)}
              className="flex-1 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              {COMPLETION_RULE_TYPES.map((t) => <option key={t} value={t}>{COMPLETION_RULE_LABEL[t]}</option>)}
            </select>
            <input
              value={completionRuleValue} onChange={(e) => setCompletionRuleValue(e.target.value)}
              type="number" min={0} max={completionRuleType === "percentage" ? 100 : undefined}
              placeholder={completionRuleType === "percentage" ? "70" : "5"}
              className="w-24 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            {completionRuleType === "percentage"
              ? "A student must attend at least this % of a cohort's sessions to auto-earn a certificate."
              : "A student must attend at least this many sessions to auto-earn a certificate."}
            {" "}Ops can still hand a certificate to anyone manually.
          </p>
        </Field>
        <Field label="Description (optional)">
          <textarea
            value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
            className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors resize-none"
          />
        </Field>
        {isEdit && (
          <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
            Active
          </label>
        )}
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()}
          loading={mutation.isPending} disabled={!code.trim() || !name.trim()}
          label={isEdit ? "Save changes" : "Create program"}
        />
      </div>
    </Modal>
  )
}
