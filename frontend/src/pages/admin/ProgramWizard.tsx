/** Full-page guided program setup (replaces the flat "New program" modal for
 *  creation) — same shell and visual scale as `CohortWizard.tsx`, ported from
 *  the same approved Claude Design export. Shorter than the cohort wizard:
 *  a program has no sessions of its own, so there's no Sessions step and no
 *  per-session override view on the Roles step.
 *
 *  Deliberately NOT a draft-then-submit wizard: the program is created as
 *  soon as step 1 is confirmed, and every step after that reads/writes the
 *  real program through the same endpoints Programs.tsx's modal already
 *  uses (plus the new program-openings-defaults endpoint for roles).
 */
import { useEffect, useState, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Check, ChevronLeft, X } from "lucide-react"
import type { CompletionRuleType, PricingModel, Program, ProgramType } from "@/types/sessions"
import { createProgramApi, updateProgramApi } from "@/api/sessions/programs"
import { getMaterialsApi, getProgramOpeningsApi } from "@/api/sessions/openings"
import { ProgramRolesPanel } from "@/pages/admin/components/ProgramRolesPanel"
import { MaterialsPanel } from "@/pages/admin/components/MaterialsPanel"
import { useToast } from "@/components/ui/toast"
import { cn, getErrorMessage } from "@/lib/utils"
import { listLmsProgramsApi, createLmsProgramApi, getLmsProgramApi, type LmsProgram } from "@/api/lms_admin"
import { CreateChecklistPrompt, ProgramTemplateEditor } from "@/pages/lms-authoring/components/LmsChecklistAuthoring"
import { Spinner } from "@/pages/admin/components/common"

const STEP_LABELS = ["Program basics", "Roles & checklist", "LMS Checklist", "Materials", "Review & finish"]
const LAST_STEP = STEP_LABELS.length - 1
const OUTFIT = "'Outfit', ui-sans-serif, system-ui, sans-serif"
const CARD_SHADOW = "0 3px 0 hsl(var(--border)), 0 12px 24px -14px rgba(40,16,80,.28)"

const PROGRAM_TYPES: ProgramType[] = ["workshop", "course", "info_session", "competition"]
const PROGRAM_TYPE_LABEL: Record<ProgramType, string> = {
  workshop: "Workshop", course: "Course", info_session: "Info session", competition: "Competition",
}
const COMPLETION_RULE_LABEL: Record<CompletionRuleType, string> = {
  percentage: "% of sessions attended", session_count: "Number of sessions attended",
}

/* ═══════════════════════════ Shared chrome bits ═════════════════════════ */
/* (Same three pieces as CohortWizard.tsx — kept local rather than shared
 *  since the wizard shell itself isn't a reusable component.) */

function StepIntro({ eyebrow, title, lede, ledeWidth = 62, right }: {
  eyebrow: string; title: string; lede?: string; ledeWidth?: number; right?: ReactNode
}) {
  return (
    <div className="flex items-end justify-between flex-wrap" style={{ gap: 40, marginBottom: 44 }}>
      <div className="flex flex-col" style={{ gap: 14, minWidth: 0 }}>
        <p style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em" }} className="text-primary m-0">{eyebrow}</p>
        <h2 style={{ fontFamily: OUTFIT, fontSize: 52, fontWeight: 600, letterSpacing: "-0.035em", lineHeight: 1.05 }} className="text-foreground m-0">{title}</h2>
        {lede && <p style={{ fontSize: 18, maxWidth: `${ledeWidth}ch`, textWrap: "pretty" }} className="text-muted-foreground m-0">{lede}</p>}
      </div>
      {right}
    </div>
  )
}

function BigField({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col" style={{ gap: 12 }}>
      <span style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.09em" }} className="text-muted-foreground">{label}</span>
      {children}
      {hint && <span style={{ fontSize: 14 }} className="text-muted-foreground">{hint}</span>}
    </label>
  )
}

const bigInput: React.CSSProperties = {
  height: 56, padding: "0 20px", borderRadius: 16, fontSize: 17, width: "100%", boxSizing: "border-box",
}
const heroInput: React.CSSProperties = {
  height: 64, padding: "0 22px", borderRadius: 16, fontFamily: OUTFIT, fontSize: 24, fontWeight: 500, width: "100%", boxSizing: "border-box",
}

export default function ProgramWizard() {
  const navigate = useNavigate()

  const [step, setStep] = useState(0)
  const [skipped, setSkipped] = useState<Record<number, boolean>>({})
  const [program, setProgram] = useState<Program | null>(null)

  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => { document.body.style.overflow = prev }
  }, [])

  const goStep = (i: number) => setStep(Math.max(0, Math.min(LAST_STEP, i)))
  const advance = () => {
    setSkipped((s) => { const n = { ...s }; delete n[step]; return n })
    goStep(step + 1)
  }
  const skipThis = () => {
    setSkipped((s) => ({ ...s, [step]: true }))
    goStep(step + 1)
  }
  const canSkip = step > 0 && step < LAST_STEP
  const canBack = step > 0

  return (
    <div className="fixed inset-0 z-50 bg-background flex flex-col" style={{ fontSize: 16, lineHeight: 1.55 }}>
      <header
        className="shrink-0 flex items-center justify-between border-b border-border bg-card"
        style={{ padding: "26px 56px", gap: 48 }}
      >
        <div style={{ minWidth: 0 }}>
          <h1
            style={{ fontFamily: OUTFIT, fontSize: 28, fontWeight: 600, letterSpacing: "-0.03em", lineHeight: 1.2 }}
            className="text-foreground m-0 truncate"
          >
            Setting up: {program?.name || "New Program"}
          </h1>
          <p style={{ fontSize: 15, margin: "6px 0 0" }} className="text-muted-foreground">
            Step {step + 1} of {STEP_LABELS.length} — {STEP_LABELS[step]}
          </p>
        </div>
        <div className="flex items-center shrink-0" style={{ gap: 32 }}>
          <StepDots steps={STEP_LABELS} current={step} skipped={skipped} onGo={(i) => { if (i <= step || program) goStep(i) }} />
          <button
            onClick={() => navigate({ to: "/operations/programs" })}
            style={{ width: 44, height: 44 }}
            className="rounded-full flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            aria-label="Close"
          ><X size={22} /></button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto" style={{ padding: "56px 56px 72px" }}>
        {step === 0 && (
          <BasicsStep program={program} onSaved={(p) => { setProgram(p); advance() }} />
        )}
        {step === 1 && program && (
          <>
            <StepIntro
              eyebrow="Roles & checklist" title="Who runs a day, and what they do" ledeWidth={70}
              lede="Every new cohort of this program starts with these roles and this checklist — a one-time copy at creation, not a live link. Editing this later never reaches a cohort that already exists."
            />
            <ProgramRolesPanel program={program} />
          </>
        )}
        {step === 2 && program && (
          <>
            <StepIntro
              eyebrow="LMS Checklist" title="What does a student need to complete?" ledeWidth={70}
              lede="Every cohort of this program shares this one checklist — courses, mission runs, quizzes, submissions, whatever this program needs done. Edit it any time from the Programs page or a cohort's own LMS tab."
            />
            <LmsChecklistStep program={program} />
          </>
        )}
        {step === 3 && program && (
          <>
            <StepIntro
              eyebrow="Materials" title="What instructors open on the day" ledeWidth={70}
              lede="Cohorts and sessions inherit these live unless one of them sets its own — unlike roles, materials still follow the program as it changes."
            />
            <MaterialsPanel owner={{ program_id: program.id }} />
          </>
        )}
        {step === 4 && program && <ReviewStep program={program} />}
      </div>

      <footer
        className="shrink-0 flex items-center justify-between border-t border-border bg-card"
        style={{ padding: "20px 56px" }}
      >
        <div>
          {canBack && (
            <button
              onClick={() => goStep(step - 1)}
              style={{ height: 52, padding: "0 20px", borderRadius: 14, fontSize: 16, fontWeight: 500 }}
              className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            ><ChevronLeft size={16} /> Back</button>
          )}
        </div>
        <div className="flex flex-col items-end" style={{ gap: 8 }}>
          <div className="flex items-center" style={{ gap: 20 }}>
            {canSkip && (
              <button
                onClick={skipThis}
                style={{ height: 52, padding: "0 18px", fontSize: 16, fontWeight: 400, textDecoration: "underline", textDecorationColor: "hsl(var(--border))", textUnderlineOffset: 4 }}
                className="text-muted-foreground hover:text-foreground transition-colors"
              >Skip for now</button>
            )}
            {step < LAST_STEP ? (
              <WizardContinueButton step={step} program={program} onContinue={advance} />
            ) : (
              <button
                onClick={() => navigate({ to: "/operations/programs" })}
                style={{ height: 52, padding: "0 40px", borderRadius: 14, fontFamily: OUTFIT, fontSize: 18, fontWeight: 600 }}
                className="bg-primary text-primary-foreground hover:opacity-90 transition-opacity"
              >Done</button>
            )}
          </div>
          {step === 1 && <SkipNote>You can set roles later — cohorts will offer no roles until you do.</SkipNote>}
          {step === 2 && <SkipNote>You can create this checklist later — students won't see one until it exists.</SkipNote>}
          {step === 3 && <SkipNote>Cohorts and sessions will simply have no materials until you add some.</SkipNote>}
        </div>
      </footer>
    </div>
  )
}

function SkipNote({ children }: { children: ReactNode }) {
  return <p style={{ fontSize: 15, margin: 0 }} className="text-muted-foreground">{children}</p>
}

/** Step 1's own Continue is a plain button (advance() is enough — the form
 *  fields underneath already saved via BasicsStep's own submit). Steps 2-3
 *  have nothing that must complete before moving on. */
function WizardContinueButton({ step, program, onContinue }: { step: number; program: Program | null; onContinue: () => void }) {
  if (step === 0) return null // BasicsStep renders its own Continue (it must create/save first)
  return (
    <button
      onClick={onContinue}
      disabled={!program}
      style={{ height: 52, padding: "0 40px", borderRadius: 14, fontFamily: OUTFIT, fontSize: 18, fontWeight: 600 }}
      className="bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
    >Continue</button>
  )
}

function StepDots({ steps, current, skipped, onGo }: {
  steps: string[]; current: number; skipped: Record<number, boolean>; onGo: (i: number) => void
}) {
  return (
    <div className="flex items-center" style={{ gap: 14 }}>
      {steps.map((label, i) => {
        const isCurrent = i === current
        const isSkipped = !!skipped[i] && !isCurrent
        const isDone = i < current && !isSkipped
        return (
          <button
            key={label}
            type="button"
            title={`${i + 1}. ${label}`}
            onClick={() => onGo(i)}
            style={
              isCurrent
                ? { width: 34, height: 34, background: "hsl(var(--primary))", boxShadow: "0 0 0 6px hsl(var(--primary) / 0.10)" }
                : isDone
                ? { width: 26, height: 26, background: "hsl(var(--muted-foreground) / 0.4)" }
                : isSkipped
                ? { width: 26, height: 26, border: "2px solid hsl(var(--muted-foreground) / 0.5)" }
                : { width: 26, height: 26, border: "2px solid hsl(var(--border))" }
            }
            className="rounded-full flex items-center justify-center shrink-0 transition-all"
          >
            {isDone && <Check size={15} className="text-card" strokeWidth={3} />}
            {isSkipped && <span style={{ width: 12, height: 2 }} className="block bg-muted-foreground/70 rotate-45 rounded-full" />}
          </button>
        )
      })}
    </div>
  )
}

/* ════════════════════════ Step 1 — Program basics ═══════════════════════ */

function BasicsStep({ program, onSaved }: { program: Program | null; onSaved: (p: Program) => void }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [code, setCode] = useState(program?.code ?? "")
  const [name, setName] = useState(program?.name ?? "")
  const [programType, setProgramType] = useState<ProgramType>(program?.program_type ?? "workshop")
  const [pricingModel, setPricingModel] = useState<PricingModel>(program?.pricing_model ?? "free")
  const [price, setPrice] = useState(program?.price != null ? String(program.price) : "")
  const [defaultCapacity, setDefaultCapacity] = useState(program?.default_capacity != null ? String(program.default_capacity) : "")
  const [description, setDescription] = useState(program?.description ?? "")
  const [completionRuleType, setCompletionRuleType] = useState<CompletionRuleType>(program?.completion_rule_type ?? "percentage")
  const [completionRuleValue, setCompletionRuleValue] = useState(
    program?.completion_rule_value != null ? String(program.completion_rule_value) : "70",
  )
  const [error, setError] = useState("")

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        code: code.trim(),
        name: name.trim(),
        program_type: programType,
        pricing_model: pricingModel,
        description: description.trim() || undefined,
        price: price.trim() ? Number(price) : undefined,
        default_capacity: defaultCapacity.trim() ? Number(defaultCapacity) : undefined,
        completion_rule_type: completionRuleType,
        completion_rule_value: completionRuleValue.trim() ? Number(completionRuleValue) : undefined,
      }
      return program ? updateProgramApi(program.id, payload) : createProgramApi(payload)
    },
    onSuccess: (p) => { toast.success(program ? "Program updated" : "Program created"); qc.invalidateQueries({ queryKey: ["sessions-programs"] }); onSaved(p) },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to save program")),
  })

  const selectStyle: React.CSSProperties = { ...bigInput, cursor: "pointer" }

  return (
    <div className="flex flex-col" style={{ gap: 44 }}>
      <StepIntro
        eyebrow="Program basics" title="What is this program?"
        lede="Everything here becomes the default for every cohort you run under it. You can change any of it later."
      />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "32px 40px" }}>
        <div style={{ gridColumn: "span 2" }}>
          <BigField label="Program name">
            <input
              value={name} onChange={(e) => setName(e.target.value)} placeholder="CubeSat Workshop" autoFocus
              style={heroInput} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors"
            />
          </BigField>
        </div>

        <BigField label="Code" hint="A short, unique reference — e.g. for payment letters.">
          <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="SATKIT-WS-2026-Q3"
            style={bigInput} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors" />
        </BigField>

        <BigField label="Type">
          <select value={programType} onChange={(e) => setProgramType(e.target.value as ProgramType)}
            style={selectStyle} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors">
            {PROGRAM_TYPES.map((t) => <option key={t} value={t}>{PROGRAM_TYPE_LABEL[t]}</option>)}
          </select>
          {programType === "competition" && (
            <p style={{ fontSize: 14, margin: "8px 0 0" }} className="text-muted-foreground">Enables the judging tools (rubric, judges, leaderboard) on this program's cohorts.</p>
          )}
        </BigField>

        <BigField label="Pricing model">
          <div className="flex bg-muted" style={{ height: 56, padding: 5, gap: 5, borderRadius: 16 }}>
            <button type="button" onClick={() => setPricingModel("free")}
              style={{ flex: 1, borderRadius: 12, fontSize: 16, fontWeight: 600 }}
              className={cn("transition-colors", pricingModel === "free" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground")}>Free</button>
            <button type="button" onClick={() => setPricingModel("paid")}
              style={{ flex: 1, borderRadius: 12, fontSize: 16, fontWeight: 600 }}
              className={cn("transition-colors", pricingModel === "paid" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground")}>Paid</button>
          </div>
        </BigField>

        {pricingModel !== "free" && (
          <BigField label="Price (AED)">
            <input value={price} onChange={(e) => setPrice(e.target.value)} type="number" placeholder="250"
              style={bigInput} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors" />
          </BigField>
        )}

        <BigField label="Default capacity (optional)">
          <input value={defaultCapacity} onChange={(e) => setDefaultCapacity(e.target.value)} type="number" placeholder="20"
            style={bigInput} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors" />
        </BigField>

        <div style={{ gridColumn: "span 2" }}>
          <BigField label="Completion requirement">
            <div className="flex" style={{ gap: 16 }}>
              <select value={completionRuleType} onChange={(e) => setCompletionRuleType(e.target.value as CompletionRuleType)}
                style={{ ...selectStyle, flex: 1 }} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors">
                {(["percentage", "session_count"] as CompletionRuleType[]).map((t) => <option key={t} value={t}>{COMPLETION_RULE_LABEL[t]}</option>)}
              </select>
              <div className="relative shrink-0" style={{ width: 160 }}>
                <input
                  value={completionRuleValue} onChange={(e) => setCompletionRuleValue(e.target.value)}
                  type="number" min={0} max={completionRuleType === "percentage" ? 100 : undefined}
                  placeholder={completionRuleType === "percentage" ? "70" : "5"}
                  style={{ ...bigInput, paddingRight: 68 }} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors"
                />
                <span style={{ fontSize: 13, fontWeight: 600 }} className="absolute right-5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none">
                  {completionRuleType === "percentage" ? "%" : "sessions"}
                </span>
              </div>
            </div>
            <p style={{ fontSize: 15, margin: "8px 0 0" }} className="text-muted-foreground">
              {completionRuleType === "percentage"
                ? "A student must attend at least this % of a cohort's sessions to auto-earn a certificate."
                : "A student must attend at least this many sessions to auto-earn a certificate."}{" "}Ops can still hand a certificate to anyone manually.
            </p>
          </BigField>
        </div>

        <div style={{ gridColumn: "span 2" }}>
          <BigField label="Description (optional)">
            <textarea
              value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
              style={{ padding: "14px 20px", borderRadius: 16, fontSize: 16, lineHeight: 1.55, width: "100%", boxSizing: "border-box" }}
              className="border border-border bg-background text-foreground resize-y focus:outline-none focus:border-primary transition-colors"
            />
          </BigField>
        </div>
      </div>

      {error && <p style={{ fontSize: 15 }} className="text-red-500">{error}</p>}

      <div className="flex justify-end" style={{ paddingTop: 8 }}>
        <button
          onClick={() => { setError(""); save.mutate() }}
          disabled={!name.trim() || !code.trim() || save.isPending}
          style={{ height: 52, padding: "0 40px", borderRadius: 14, fontFamily: OUTFIT, fontSize: 18, fontWeight: 600 }}
          className="bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
        >{save.isPending ? "…" : "Continue"}</button>
      </div>
    </div>
  )
}

/* ═══════════════════════ Step 3 — LMS Checklist ═════════════════════════ */

/** Mirrors `ProgramWorkspace`'s own program-scope branch in
 * `LmsProgramAdmin.tsx` (create-prompt, then full inline authoring) — no
 * `isStaff`/`scope` machinery needed here, since this wizard is inherently
 * staff-only and `program.id` is already the real Sessions Program id. */
function LmsChecklistStep({ program }: { program: Program }) {
  const queryClient = useQueryClient()
  const { data: found = [], isLoading } = useQuery<LmsProgram[]>({
    queryKey: ["lms-program-for-program", program.id], queryFn: () => listLmsProgramsApi(program.id),
  })
  const [created, setCreated] = useState<LmsProgram | null>(null)
  const effective = created ?? found[0] ?? null

  const createMutation = useMutation({
    mutationFn: (name: string) => createLmsProgramApi({ program_id: program.id, name }),
    onSuccess: (p) => setCreated(p),
  })

  const refresh = async () => {
    const fresh = await getLmsProgramApi(effective!.id)
    setCreated(fresh)
    void queryClient.invalidateQueries({ queryKey: ["lms-program-for-program", program.id] })
  }

  if (isLoading) return <Spinner />
  if (!effective) {
    return <CreateChecklistPrompt onCreate={(name) => createMutation.mutate(name)} pending={createMutation.isPending} />
  }
  return <ProgramTemplateEditor program={effective} onChanged={refresh} readOnly={false} />
}

/* ══════════════════════ Step 5 — Review & finish ═══════════════════════ */

function ReviewStep({ program }: { program: Program }) {
  const { data: openings = [] } = useQuery({ queryKey: ["program-openings-defaults", program.id], queryFn: () => getProgramOpeningsApi(program.id) })
  const { data: materials = [] } = useQuery({ queryKey: ["materials", JSON.stringify({ program_id: program.id })], queryFn: () => getMaterialsApi({ program_id: program.id }) })
  const { data: lmsPrograms = [] } = useQuery<LmsProgram[]>({
    queryKey: ["lms-program-for-program", program.id], queryFn: () => listLmsProgramsApi(program.id),
  })
  const lmsProgram = lmsPrograms[0]

  const rows: { label: string; value: string }[] = [
    { label: "Name", value: program.name },
    { label: "Code", value: program.code },
    { label: "Type", value: PROGRAM_TYPE_LABEL[program.program_type] },
    { label: "Pricing", value: program.pricing_model === "free" ? "Free" : `AED ${program.price ?? "—"}` },
    { label: "Default capacity", value: program.default_capacity != null ? String(program.default_capacity) : "Not set" },
    {
      label: "Roles & checklist",
      value: openings.length === 0 ? "No roles set yet — new cohorts will offer none until you add some" : `${openings.length} role${openings.length === 1 ? "" : "s"} templated, copied into every new cohort`,
    },
    {
      label: "LMS Checklist",
      value: !lmsProgram
        ? "Not set up yet — students will see an empty checklist"
        : `${lmsProgram.items.length} step${lmsProgram.items.length === 1 ? "" : "s"} — shared by every cohort of this program`,
    },
    {
      label: "Materials",
      value: materials.length === 0 ? "None yet" : `${materials.length} item${materials.length === 1 ? "" : "s"} — cohorts and sessions inherit these live`,
    },
  ]

  return (
    <div className="flex flex-col" style={{ gap: 40 }}>
      <div className="flex items-end justify-between flex-wrap" style={{ gap: 40 }}>
        <div className="flex flex-col" style={{ gap: 14 }}>
          <p style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em" }} className="text-primary m-0">Review &amp; create</p>
          <h2 style={{ fontFamily: OUTFIT, fontSize: 56, fontWeight: 600, letterSpacing: "-0.035em", lineHeight: 1.05 }} className="text-foreground m-0">{program.name}</h2>
          <p style={{ fontSize: 18 }} className="text-muted-foreground m-0">{program.code}</p>
        </div>
        <p style={{ fontSize: 15, maxWidth: "34ch", margin: "0 0 6px" }} className="text-muted-foreground">You can change anything later from the Programs page.</p>
      </div>

      <div className="flex flex-col" style={{ gap: 14, padding: "2px 6px 6px 2px" }}>
        {rows.map((r) => (
          <div key={r.label}
            style={{ display: "grid", gridTemplateColumns: "280px minmax(0,1fr) auto", gap: 32, alignItems: "center", padding: "24px 28px", borderRadius: 16, boxShadow: CARD_SHADOW }}
            className="border border-border bg-card">
            <span style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.09em" }} className="text-muted-foreground">{r.label}</span>
            <span style={{ fontSize: 19 }} className="text-foreground">{r.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
