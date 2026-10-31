/** Full-page guided cohort setup (replaces the flat "New cohort" modal for
 *  creation). Same full-page-overlay shell as the LMS's Madar phase drawer
 *  (`pages/learn/missions/MadarPhaseDrawer.tsx`) — one focused step at a
 *  time instead of tabs ops had to discover on their own.
 *
 *  Visual scale is balanced and clean, fitting standard density:
 *  Outfit display headlines, 42-46px inputs, centered max-width container.
 *
 *  Deliberately NOT a draft-then-submit wizard: the cohort is created as
 *  soon as step 1 is confirmed, and every step after that reads/writes the
 *  real cohort through the same endpoints the cohort detail page's tabs
 *  already use.
 */
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Check, ChevronLeft, ChevronRight, Clock, Info, Lock, Mail, Pencil, Phone, Plus, Trash2, X } from "lucide-react"
import type { Cohort, CohortAssignment, CohortVisibility, Program, Registration, Session } from "@/types/sessions"
import type { City, Location, Warehouse } from "@/types/inventory"
import { getProgramsApi } from "@/api/sessions/programs"
import { getLocationsApi, getWarehousesApi, createLocationApi, getCitiesApi } from "@/api/inventory"
import {
  cloneCohortApi, createCohortApi, updateCohortApi, generateSessionsApi, getCohortsApi, getSessionsApi, addSessionApi, deleteSessionApi,
  getRegistrationsApi,
} from "@/api/sessions/cohorts"
import { getCohortOpeningsApi, getDeliveryRolesApi, getMaterialsApi, setCohortOpeningsApi } from "@/api/sessions/openings"
import { listCohortAssignmentsApi, listCohortCallsApi, type CohortCall } from "@/api/sessions/staffing"
import { Spinner, EmptyState } from "@/pages/admin/components/common"
import { CohortRolesPanel } from "@/pages/admin/components/CohortRolesPanel"
import { SessionOpeningsPanel } from "@/pages/admin/components/SessionOpeningsPanel"
import { SessionChecklistPanel } from "@/pages/admin/components/SessionChecklistPanel"
import { MaterialsPanel } from "@/pages/admin/components/MaterialsPanel"
import { BulkAssignInstructorModal } from "@/pages/admin/components/BulkAssignInstructorModal"
import { BulkOpenCallModal } from "@/pages/admin/components/BulkOpenCallModal"
import { AssessmentAssignmentPanel } from "@/pages/admin/components/AssessmentAssignmentPanel"
import { DeskRegisterModal } from "@/pages/admin/components/DeskRegisterModal"
import { EditStudentModal } from "@/pages/admin/components/EditStudentModal"
import { ImportListModal } from "@/pages/admin/components/ImportList"
import { useToast } from "@/components/ui/toast"
import { useAuth } from "@/context/AuthContext"
import { cn, getErrorMessage } from "@/lib/utils"
import { listLmsProgramsApi, createLmsProgramApi, getCohortProgramOverrideApi, type LmsProgram } from "@/api/lms_admin"
import { CohortOverrideEditor } from "@/pages/lms-authoring/components/LmsChecklistAuthoring"
import { RubricTab, JudgesTab } from "@/pages/admin/CompetitionJudging"
import { SubmissionWindowsModal } from "@/components/competitions/SubmissionWindowsModal"

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] // index = backend's 0..6 (Monday first)
const OUTFIT = "'Outfit', ui-sans-serif, system-ui, sans-serif"
const CARD_SHADOW = "0 3px 0 hsl(var(--border)), 0 10px 20px -5px rgba(0,0,0,.35), 0 2px 6px -1px rgba(0,0,0,.20)"

function pad(n: number) { return String(n).padStart(2, "0") }
function toISODate(d: Date) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` }
function fmtDate(iso: string) {
  const d = new Date(iso + "T00:00:00")
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" })
}

/* ═══════════════════════════ Shared chrome bits ═════════════════════════ */

function StepIntro({ eyebrow, title, lede, ledeWidth = 62, right }: {
  eyebrow: string; title: string; lede?: string; ledeWidth?: number; right?: ReactNode
}) {
  return (
    <div className="flex items-end justify-between flex-wrap gap-4 sm:gap-5 mb-5 sm:mb-7">
      <div className="flex flex-col gap-1.5 min-w-0">
        <p style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }} className="text-primary m-0">{eyebrow}</p>
        <h2 style={{ fontFamily: OUTFIT }} className="text-foreground m-0 text-2xl sm:text-3xl font-semibold tracking-tight leading-tight">{title}</h2>
        {lede && <p style={{ fontSize: 15, maxWidth: `${ledeWidth}ch`, textWrap: "pretty" }} className="text-muted-foreground m-0">{lede}</p>}
      </div>
      {right}
    </div>
  )
}

/** Field label */
function BigField({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col" style={{ gap: 6 }}>
      <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }} className="text-muted-foreground">{label}</span>
      {children}
      {hint && <span style={{ fontSize: 13 }} className="text-muted-foreground">{hint}</span>}
    </label>
  )
}

const bigInput: React.CSSProperties = {
  height: 42, padding: "0 14px", borderRadius: 10, fontSize: 14, width: "100%", boxSizing: "border-box",
}
const heroInput: React.CSSProperties = {
  height: 46, padding: "0 16px", borderRadius: 10, fontFamily: OUTFIT, fontSize: 17, fontWeight: 500, width: "100%", boxSizing: "border-box",
}

export default function CohortWizard() {
  const navigate = useNavigate()

  const [step, setStep] = useState(0)
  const [skipped, setSkipped] = useState<Record<number, boolean>>({})
  const [cohort, setCohort] = useState<Cohort | null>(null)

  const [basicsForm, setBasicsForm] = useState<{ save: () => void; isPending: boolean; canSubmit: boolean }>({ save: () => {}, isPending: false, canSubmit: false })
  const [templateForm, setTemplateForm] = useState<{ save: () => void; isPending: boolean; canSubmit: boolean }>({ save: () => {}, isPending: false, canSubmit: true })
  // The Roles & checklist step (2026-09 fix): the panel shows every active
  // Delivery Settings role as a live preview before anything is saved — if
  // nobody clicks its own "Save roles" button, no CohortOpening row ever
  // gets created, and every session in the cohort ends up with no roles to
  // staff at all (openings_for_session has no fallback below the cohort
  // tier). `ensure()` persists real rows for whatever's currently shown —
  // each role at its own live defaults (null rate/notes/override, so it
  // still inherits DeliveryRole changes exactly like a row someone saved by
  // hand would) — the moment the wizard actually leaves this step, whether
  // by clicking Continue or Skip. It's a no-op once anything already exists.
  const [rolesForm, setRolesForm] = useState<{ ensure: () => Promise<void> }>({ ensure: async () => {} })

  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => { document.body.style.overflow = prev }
  }, [])

  const { data: programs = [] } = useQuery({ queryKey: ["sessions-programs"], queryFn: getProgramsApi })
  const program = programs.find((p) => p.id === cohort?.program_id)
  const isComp = Boolean(program?.is_competition || cohort?.program_is_competition)

  const stepLabels = useMemo(() => {
    const list = [
      "Template or scratch",
      "Cohort basics",
      "Sessions",
      "Roles & checklist",
      "LMS Checklist",
      "Materials",
      "Staffing",
      "Students",
    ]
    if (isComp) {
      list.push("Judging & Competition")
    }
    list.push("Review & finish")
    return list
  }, [isComp])
  const lastStep = stepLabels.length - 1

  const goStep = (i: number) => setStep(Math.max(0, Math.min(lastStep, i)))
  const advance = async () => {
    if (step === 3) await rolesForm.ensure()
    setSkipped((s) => { const n = { ...s }; delete n[step]; return n })
    goStep(step + 1)
  }
  const skipThis = async () => {
    if (step === 3) await rolesForm.ensure()
    setSkipped((s) => ({ ...s, [step]: true }))
    goStep(step + 1)
  }
  const canSkip = step > 1 && step < lastStep
  const canBack = step > 0

  return (
    <div className="fixed inset-0 z-50 bg-background flex flex-col" style={{ fontSize: 14, lineHeight: 1.5 }}>
      <header className="shrink-0 relative border-b border-border bg-card px-4 py-3 sm:px-10 sm:py-4">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h1
              style={{ fontFamily: OUTFIT }}
              className="text-foreground m-0 text-base sm:text-xl font-semibold tracking-tight truncate"
            >
              Setting up: {cohort?.name || "New Cohort"}
            </h1>
            <p className="text-xs sm:text-sm text-muted-foreground mt-0.5 truncate">
              Step {step + 1} of {stepLabels.length} — {stepLabels[step]}
            </p>
          </div>
          <div className="flex items-center gap-3 sm:gap-6 shrink-0">
            <div className="hidden sm:block">
              <StepDots steps={stepLabels} current={step} skipped={skipped} onGo={(i) => { if (i <= step || cohort) goStep(i) }} />
            </div>
            <button
              onClick={() => navigate({ to: cohort ? "/operations/cohorts/$cohortId" : "/operations/cohorts", params: cohort ? { cohortId: cohort.id } : undefined })}
              className="w-8 h-8 sm:w-9 sm:h-9 rounded-full flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              aria-label="Close"
            ><X size={18} /></button>
          </div>
        </div>
        {/* Mobile progress bar along bottom of header */}
        <div className="sm:hidden absolute bottom-0 left-0 right-0 h-1 bg-muted/60 overflow-hidden">
          <div
            className="h-full bg-primary transition-all duration-300"
            style={{ width: `${((step + 1) / stepLabels.length) * 100}%` }}
          />
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-4 sm:px-10 sm:py-8">
        {step === 0 && (
          <TemplateStep
            programs={programs}
            cohort={cohort}
            onCloned={(c) => { setCohort(c); advance() }}
            onFresh={advance}
            onFormChange={setTemplateForm}
          />
        )}
        {step === 1 && (
          <BasicsStep
            programs={programs} program={program} cohort={cohort}
            onSaved={(c) => { setCohort(c); advance() }}
            onFormChange={setBasicsForm}
          />
        )}
        {step === 2 && cohort && <SessionsStep cohort={cohort} />}
        {step === 3 && cohort && <RolesChecklistStep cohort={cohort} onFormChange={setRolesForm} />}
        {step === 4 && cohort && program && (
          <>
            <StepIntro
              eyebrow="LMS Checklist" title="What does students' checklist look like?" ledeWidth={70}
              lede="Build the cohort's checklist below — it starts as a copy of the program's, and editing it here only affects this cohort."
            />
            <LmsChecklistStep cohort={cohort} program={program} />
          </>
        )}
        {step === 5 && cohort && (
          <>
            <StepIntro
              eyebrow="Materials" title="What instructors open on the day" ledeWidth={70}
              lede="The program's materials are used as-is. Add anything here and this cohort uses your list instead — it replaces the inherited one rather than adding to it."
            />
            <MaterialsPanel
              owner={{ cohort_id: cohort.id }} level="cohort"
              inheritedNote="Sessions inherit these unless a session overrides them."
            />
          </>
        )}
        {step === 6 && cohort && (
          <>
            <StepIntro
              eyebrow="Staffing" title="Who's running each session?" ledeWidth={70}
              lede="Assign an instructor directly, or open a call and staff it from whoever applies — both work the same way they do from the cohort page."
            />
            <StaffingStep cohort={cohort} />
          </>
        )}
        {step === 7 && cohort && (
          <>
            <StepIntro
              eyebrow="Students" title="Who is registered?" ledeWidth={70}
              lede="Add students one at a time, or import a whole list at once."
            />
            <StudentsStep cohort={cohort} />
          </>
        )}
        {isComp && step === 8 && cohort && <CompetitionJudgingStep cohort={cohort} />}
        {step === lastStep && cohort && <ReviewStep cohort={cohort} program={program} />}
      </div>

      <footer
        className="shrink-0 flex items-center justify-between border-t border-border bg-card px-4 py-3 sm:px-10 sm:py-3.5"
      >
        <div>
          {canBack && (
            <button
              onClick={() => goStep(step - 1)}
              style={{ height: 38, borderRadius: 8, fontSize: 13, fontWeight: 500 }}
              className="flex items-center gap-1.5 px-3 sm:px-4 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            ><ChevronLeft size={15} /> Back</button>
          )}
        </div>
        <div className="flex flex-col items-end gap-1">
          <div className="flex items-center gap-2 sm:gap-3">
            {canSkip && (
              <button
                onClick={skipThis}
                style={{ height: 38, fontSize: 13, textDecoration: "underline", textDecorationColor: "hsl(var(--border))", textUnderlineOffset: 4 }}
                className="px-2 sm:px-3 text-muted-foreground hover:text-foreground transition-colors"
              >Skip for now</button>
            )}
            {step < lastStep ? (
              <WizardContinueButton step={step} cohort={cohort} onContinue={advance} basicsForm={basicsForm} templateForm={templateForm} />
            ) : (
              <div className="flex items-center gap-2">
                {Boolean(program?.is_competition || cohort?.program_is_competition) && (
                  <button
                    onClick={() => navigate({ to: "/operations/cohorts/$cohortId/judging", params: { cohortId: cohort!.id } })}
                    style={{ height: 38, fontFamily: OUTFIT, fontWeight: 600 }}
                    className="px-4 sm:px-6 rounded-lg text-sm sm:text-base border border-primary text-primary hover:bg-primary/10 transition-colors"
                  >Open Judging Dashboard</button>
                )}
                <button
                  onClick={() => navigate({ to: "/operations/cohorts/$cohortId", params: { cohortId: cohort!.id } })}
                  style={{ height: 38, fontFamily: OUTFIT, fontWeight: 600 }}
                  className="px-4 sm:px-7 rounded-lg text-sm sm:text-base bg-primary text-primary-foreground hover:opacity-90 transition-opacity"
                >Done</button>
              </div>
            )}
          </div>
          <div className="hidden sm:block">
            {step === 2 && <SkipNote>You can add sessions later from the cohort page.</SkipNote>}
            {step === 3 && <SkipNote>Every session uses the cohort&rsquo;s roles and checklist until you override one.</SkipNote>}
            {step === 4 && <SkipNote>You can set this up later from the program or this cohort&rsquo;s own LMS tab.</SkipNote>}
            {step === 5 && <SkipNote>Sessions will use the program&rsquo;s materials.</SkipNote>}
            {step === 6 && <SkipNote>You can staff sessions any time from the cohort&rsquo;s Staffing tab.</SkipNote>}
            {step === 7 && <SkipNote>You can add students any time from the cohort&rsquo;s Students tab.</SkipNote>}
            {isComp && step === 8 && <SkipNote>You can fine-tune rubric and judges any time from the Judging tab.</SkipNote>}
          </div>
        </div>
      </footer>
    </div>
  )
}

function SkipNote({ children }: { children: ReactNode }) {
  return <p style={{ fontSize: 13, margin: 0 }} className="text-muted-foreground">{children}</p>
}

function WizardContinueButton({ step, cohort, onContinue, basicsForm, templateForm }: {
  step: number; cohort: Cohort | null; onContinue: () => void;
  basicsForm: { save: () => void; isPending: boolean; canSubmit: boolean }
  templateForm: { save: () => void; isPending: boolean; canSubmit: boolean }
}) {
  if (step === 0) {
    return (
      <button
        onClick={templateForm.save}
        disabled={!templateForm.canSubmit || templateForm.isPending}
        style={{ height: 38, borderRadius: 8, fontFamily: OUTFIT, fontWeight: 600 }}
        className="px-4 sm:px-7 text-sm sm:text-base bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
      >{templateForm.isPending ? "…" : "Continue"}</button>
    )
  }
  if (step === 1) {
    return (
      <button
        onClick={basicsForm.save}
        disabled={!basicsForm.canSubmit || basicsForm.isPending}
        style={{ height: 38, borderRadius: 8, fontFamily: OUTFIT, fontWeight: 600 }}
        className="px-4 sm:px-7 text-sm sm:text-base bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
      >{basicsForm.isPending ? "…" : "Continue"}</button>
    )
  }
  return (
    <button
      onClick={onContinue}
      disabled={!cohort}
      style={{ height: 38, borderRadius: 8, fontFamily: OUTFIT, fontWeight: 600 }}
      className="px-4 sm:px-7 text-sm sm:text-base bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
    >Continue</button>
  )
}

function StepDots({ steps, current, skipped, onGo }: {
  steps: string[]; current: number; skipped: Record<number, boolean>; onGo: (i: number) => void
}) {
  return (
    <div className="flex items-center" style={{ gap: 10 }}>
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
                ? { width: 26, height: 26, background: "hsl(var(--primary))", boxShadow: "0 0 0 4px hsl(var(--primary) / 0.12)" }
                : isDone
                ? { width: 22, height: 22, background: "hsl(var(--muted-foreground) / 0.4)" }
                : isSkipped
                ? { width: 22, height: 22, border: "2px solid hsl(var(--muted-foreground) / 0.5)" }
                : { width: 22, height: 22, border: "2px solid hsl(var(--border))" }
            }
            className="rounded-full flex items-center justify-center shrink-0 transition-all"
          >
            {isDone && <Check size={13} className="text-card" strokeWidth={3} />}
            {isSkipped && <span style={{ width: 10, height: 2 }} className="block bg-muted-foreground/70 rotate-45 rounded-full" />}
          </button>
        )
      })}
    </div>
  )
}

/* ════════════════════════ Step 0 — Template or scratch ═══════════════════════ */

const COHORT_CARRY_OPTIONS: { key: string; label: string; competitionOnly?: boolean }[] = [
  { key: "basics", label: "Basics (location, capacity, duration, visibility, poster URL)" },
  { key: "windows", label: "Submission windows / timing brackets", competitionOnly: true },
  { key: "roles", label: "Delivery roles defaults" },
  { key: "materials", label: "Materials override" },
  { key: "assessment", label: "Assessment assignment" },
  { key: "checklist", label: "LMS Checklist override (copies custom tasks/missions)" },
  { key: "rubric", label: "Competition Rubric (scoring criteria & breakdown)", competitionOnly: true },
  { key: "judges", label: "Competition Judges (assign silently with zero email notifications)", competitionOnly: true },
]

function TemplateStep({ programs, cohort, onCloned, onFresh, onFormChange }: {
  programs: Program[]; cohort: Cohort | null; onCloned: (c: Cohort) => void; onFresh: () => void;
  onFormChange: (form: { save: () => void; isPending: boolean; canSubmit: boolean }) => void
}) {
  const toast = useToast()
  const qc = useQueryClient()
  const [mode, setMode] = useState<"fresh" | "clone">("fresh")
  const [targetProgramId, setTargetProgramId] = useState(cohort?.program_id ?? "")
  const [sourceId, setSourceId] = useState("")
  const [name, setName] = useState("")
  const [startsOn, setStartsOn] = useState("")
  const [endsOn, setEndsOn] = useState("")
  const [carry, setCarry] = useState<string[]>(["basics", "windows", "roles", "materials", "assessment", "checklist", "rubric", "judges"])
  const [error, setError] = useState("")

  const { data: allCohorts = [] } = useQuery({ queryKey: ["sessions-cohorts-all"], queryFn: () => getCohortsApi() })
  const targetProgram = programs.find((p) => p.id === targetProgramId)
  const isTargetCompetition = Boolean(targetProgram?.is_competition)

  const source = allCohorts.find((c) => c.id === sourceId)
  const sourceProgram = programs.find((p) => p.id === source?.program_id)
  const isSourceCompetition = Boolean(sourceProgram?.is_competition || source?.program_is_competition)

  // Competition features (rubric, judges, submission windows) can only carry over
  // when both source and target are competitions.
  const allowCompetitionCarry = Boolean(source && targetProgram && isSourceCompetition && isTargetCompetition)

  // Sort cohorts so they are easy to find: by program name then cohort name
  const sortedCohorts = useMemo(() => {
    return [...allCohorts].sort((a, b) => {
      const pA = programs.find((p) => p.id === a.program_id)?.name ?? a.program_name ?? ""
      const pB = programs.find((p) => p.id === b.program_id)?.name ?? b.program_name ?? ""
      const cmpProg = pA.localeCompare(pB)
      if (cmpProg !== 0) return cmpProg
      return a.name.localeCompare(b.name)
    })
  }, [allCohorts, programs])

  useEffect(() => {
    if (source && !name) setName(`${source.name} (Copy)`)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceId])

  useEffect(() => {
    if (!allowCompetitionCarry) {
      setCarry((prev) => prev.filter((k) => k !== "rubric" && k !== "judges" && k !== "windows"))
    } else {
      setCarry(["basics", "windows", "roles", "materials", "assessment", "checklist", "rubric", "judges"])
    }
  }, [allowCompetitionCarry])

  const clone = useMutation({
    mutationFn: () => cloneCohortApi(sourceId, {
      name: name.trim(), program_id: targetProgramId,
      starts_on: startsOn || null, ends_on: endsOn || null, carry,
    }),
    onSuccess: (c) => {
      toast.success("Cohort cloned from template")
      qc.invalidateQueries({ queryKey: ["sessions-cohorts"] })
      onCloned(c)
    },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to clone cohort")),
  })

  const toggleCarry = (key: string) =>
    setCarry((c) => (c.includes(key) ? c.filter((k) => k !== key) : [...c, key]))

  const canSubmit = mode === "fresh" || Boolean(sourceId && targetProgramId && name.trim())

  useEffect(() => {
    onFormChange({
      save: () => {
        if (mode === "fresh") {
          onFresh()
          return
        }
        setError("")
        clone.mutate()
      },
      isPending: clone.isPending,
      canSubmit,
    })
  }, [mode, sourceId, targetProgramId, name, startsOn, endsOn, carry, clone.isPending, canSubmit])

  const visibleOptions = COHORT_CARRY_OPTIONS.filter((o) => !o.competitionOnly || allowCompetitionCarry)

  return (
    <div className="flex flex-col" style={{ gap: 28 }}>
      <StepIntro
        eyebrow="Template or scratch" title="Start fresh or clone a template?"
        lede="Clone an existing cohort — even from another program or between different program types — to carry its settings into a new cohort. You can edit everything after cloning."
      />
      <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
        <button
          type="button" onClick={() => setMode("fresh")}
          style={{ flex: 1, borderRadius: 10, padding: "12px 16px", fontSize: 14, fontWeight: 600, textAlign: "left" }}
          className={cn("border transition-colors", mode === "fresh" ? "border-primary bg-primary/5 text-foreground" : "border-border text-muted-foreground")}
        >○ Start fresh from scratch</button>
        <button
          type="button" onClick={() => setMode("clone")}
          style={{ flex: 1, borderRadius: 10, padding: "12px 16px", fontSize: 14, fontWeight: 600, textAlign: "left" }}
          className={cn("border transition-colors", mode === "clone" ? "border-primary bg-primary/5 text-foreground" : "border-border text-muted-foreground")}
        >● Clone an existing cohort as template</button>
      </div>

      {mode === "clone" && (
        <div className="flex flex-col" style={{ gap: 16 }}>
          <BigField
            label="Template cohort"
            hint={
              source
                ? `Template type: ${isSourceCompetition ? "Competition" : "Standard Workshop/Course"}`
                : "Select any existing cohort across programs as template"
            }
          >
            <select
              value={sourceId}
              onChange={(e) => {
                const newSourceId = e.target.value
                setSourceId(newSourceId)
                if (!targetProgramId && newSourceId) {
                  const picked = allCohorts.find((c) => c.id === newSourceId)
                  if (picked) setTargetProgramId(picked.program_id)
                }
              }}
              style={{ ...bigInput, cursor: "pointer" }}
              className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors"
            >
              <option value="">
                {allCohorts.length === 0 ? "— No cohorts available —" : "— Select a template cohort —"}
              </option>
              {sortedCohorts.map((c) => {
                const prog = programs.find((p) => p.id === c.program_id)
                const pname = prog?.name ?? c.program_name ?? "Unknown program"
                const isComp = Boolean(prog?.is_competition || c.program_is_competition)
                return (
                  <option key={c.id} value={c.id}>
                    [{isComp ? "Competition" : "Standard"}] [{pname}] — {c.name}
                  </option>
                )
              })}
            </select>
          </BigField>

          <BigField
            label="Target program"
            hint={
              targetProgram
                ? `Selected target type: ${targetProgram.is_competition ? "Competition" : "Standard Workshop/Course"}`
                : "Choose the target program the cloned cohort belongs to"
            }
          >
            <select
              value={targetProgramId} onChange={(e) => setTargetProgramId(e.target.value)}
              style={{ ...bigInput, cursor: "pointer" }}
              className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors"
            >
              <option value="">— Select target program —</option>
              {programs.map((p) => (
                <option key={p.id} value={p.id}>
                  [{p.is_competition ? "Competition" : "Standard"}] {p.name}
                </option>
              ))}
            </select>
          </BigField>

          {source && targetProgram && isSourceCompetition !== isTargetCompetition && (
            <div className="p-3.5 rounded-xl border border-border bg-muted/40 text-sm flex items-start gap-2.5">
              <Info size={16} className="text-primary mt-0.5 shrink-0" />
              <div>
                {isSourceCompetition && !isTargetCompetition ? (
                  <>
                    <span className="font-medium text-foreground">Cloning Competition into Standard Workshop:</span>{" "}
                    <span className="text-muted-foreground">
                      All general settings, checklist, materials, and roles will be cloned. Competition-specific features (rubric, judges, submission windows) are excluded.
                    </span>
                  </>
                ) : (
                  <>
                    <span className="font-medium text-foreground">Cloning Standard Workshop into Competition:</span>{" "}
                    <span className="text-muted-foreground">
                      All settings, checklist, materials, and roles will be cloned. You can set up competition features (rubric, judges, submission windows) in the subsequent steps.
                    </span>
                  </>
                )}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6">
            <BigField label="New cohort name">
              <input
                value={name} onChange={(e) => setName(e.target.value)} placeholder="New cohort name"
                style={heroInput} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors"
              />
            </BigField>
            <BigField label="Starts on">
              <input value={startsOn} onChange={(e) => setStartsOn(e.target.value)} type="date"
                style={bigInput} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors" />
            </BigField>
            <BigField label="Ends on">
              <input value={endsOn} onChange={(e) => setEndsOn(e.target.value)} type="date"
                style={bigInput} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors" />
            </BigField>
          </div>
          <div className="flex flex-col" style={{ gap: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }} className="text-muted-foreground">Carry over</span>
            {visibleOptions.map((o) => (
              <label key={o.key} className="flex items-center gap-2 text-foreground cursor-pointer select-none" style={{ fontSize: 14 }}>
                <input
                  type="checkbox"
                  checked={carry.includes(o.key)}
                  onChange={() => toggleCarry(o.key)}
                  className="rounded border-border accent-primary w-4 h-4 cursor-pointer"
                />
                <span>{o.label}</span>
              </label>
            ))}
          </div>
          {error && <p style={{ fontSize: 14 }} className="text-red-500">{error}</p>}
        </div>
      )}
    </div>
  )
}

/* ════════════════════════ Step 1 — Cohort basics ═══════════════════════ */

function BasicsStep({ programs, program, cohort, onSaved, onFormChange }: {
  programs: Program[]; program?: Program; cohort: Cohort | null; onSaved: (c: Cohort) => void;
  onFormChange: (form: { save: () => void; isPending: boolean; canSubmit: boolean }) => void
}) {
  const toast = useToast()
  const qc = useQueryClient()
  const { hasRole } = useAuth()
  const [programId, setProgramId] = useState(cohort?.program_id ?? "")
  const [name, setName] = useState(cohort?.name ?? "")
  const [startsOn, setStartsOn] = useState(cohort?.starts_on ?? "")
  const [endsOn, setEndsOn] = useState(cohort?.ends_on ?? "")
  const [locationId, setLocationId] = useState(cohort?.location_id ?? "")
  const [warehouseId, setWarehouseId] = useState(cohort?.warehouse_id ?? "")
  const [capacity, setCapacity] = useState(cohort?.capacity != null ? String(cohort.capacity) : "")
  const [durationHours, setDurationHours] = useState(cohort?.duration_hours != null ? String(cohort.duration_hours) : "")
  const [visibility, setVisibility] = useState<CohortVisibility>(cohort?.visibility ?? "public")
  const [keepCourseAccessAfterCompletion, setKeepCourseAccessAfterCompletion] = useState(
    cohort?.keep_course_access_after_completion ?? program?.keep_course_access_after_completion ?? true,
  )
  const [error, setError] = useState("")

  const { data: locations = [] } = useQuery({ queryKey: ["inv-locations"], queryFn: () => getLocationsApi() })
  const { data: warehouses = [] } = useQuery({ queryKey: ["inv-warehouses"], queryFn: () => getWarehousesApi() })

  const canCreateLocation = hasRole("operations") || hasRole("admin")
  const [addingLocation, setAddingLocation] = useState(false)
  const [newLocName, setNewLocName] = useState("")
  const [newLocCityId, setNewLocCityId] = useState("")
  const [newLocError, setNewLocError] = useState("")
  const { data: cities = [] } = useQuery({ queryKey: ["inv-cities"], queryFn: () => getCitiesApi(), enabled: addingLocation })

  const createLocationMutation = useMutation({
    mutationFn: () => createLocationApi({ name: newLocName.trim(), city_id: newLocCityId, address: null, maps_url: null }),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["inv-locations"] })
      setLocationId(created.id); setWarehouseId(""); setAddingLocation(false); setNewLocName(""); setNewLocCityId("")
    },
    onError: (e: any) => setNewLocError(getErrorMessage(e, "Could not create the location")),
  })

  const save = useMutation({
    mutationFn: () => cohort
      ? updateCohortApi(cohort.id, {
          name: name.trim(), starts_on: startsOn || null, ends_on: endsOn || null,
          location_id: locationId || null, warehouse_id: warehouseId || null,
          capacity: capacity.trim() ? Number(capacity) : null,
          duration_hours: durationHours.trim() ? Number(durationHours) : null,
          visibility,
          keep_course_access_after_completion: keepCourseAccessAfterCompletion,
        })
      : createCohortApi({
          program_id: programId, name: name.trim(), starts_on: startsOn || undefined, ends_on: endsOn || undefined,
          location_id: locationId || undefined, warehouse_id: warehouseId || undefined,
          capacity: capacity.trim() ? Number(capacity) : undefined,
          duration_hours: durationHours.trim() ? Number(durationHours) : undefined,
          visibility,
          keep_course_access_after_completion: keepCourseAccessAfterCompletion,
        }),
    onSuccess: (c) => { toast.success(cohort ? "Cohort updated" : "Cohort created"); qc.invalidateQueries({ queryKey: ["sessions-cohorts"] }); onSaved(c) },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to save cohort")),
  })

  const canSubmit = Boolean(name.trim() && (cohort || programId))

  useEffect(() => {
    onFormChange({
      save: () => { setError(""); save.mutate() },
      isPending: save.isPending,
      canSubmit,
    })
  }, [name, programId, cohort, save.isPending, canSubmit, startsOn, endsOn, locationId, warehouseId, capacity, durationHours, visibility, keepCourseAccessAfterCompletion])

  const selectStyle: React.CSSProperties = { ...bigInput, cursor: "pointer" }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (canSubmit && !save.isPending) {
          setError("")
          save.mutate()
        }
      }}
      className="flex flex-col" style={{ gap: 28 }}
    >
      <StepIntro
        eyebrow="Cohort basics" title="What is this run of the program?"
        lede="Everything here becomes the default for every session in the cohort. You can change any of it later."
        right={
          cohort ? (
            <div className="flex flex-col shrink-0" style={{ gap: 4, paddingLeft: 20, borderLeft: "2px solid hsl(var(--primary))" }}>
              <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }} className="text-muted-foreground">Program</span>
              <span style={{ fontFamily: OUTFIT, fontSize: 18, fontWeight: 600, letterSpacing: "-0.01em" }} className="flex items-center gap-2 text-foreground">
                {program?.name ?? "…"} <Lock size={15} className="text-muted-foreground" />
              </span>
            </div>
          ) : undefined
        }
      />

      {!cohort && (
        <BigField label="Program">
          <select
            value={programId}
            onChange={(e) => {
              const nextId = e.target.value
              setProgramId(nextId)
              const prog = programs.find((p) => p.id === nextId)
              if (prog) {
                setKeepCourseAccessAfterCompletion(prog.keep_course_access_after_completion ?? true)
              }
            }}
            style={selectStyle}
            className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors"
          >
            <option value="">— Select a program —</option>
            {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </BigField>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6">
        <div className="col-span-1 sm:col-span-2">
          <BigField label="Cohort name">
            <input
              value={name} onChange={(e) => setName(e.target.value)} placeholder="Q3 Cohort A" autoFocus
              style={heroInput} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors"
            />
          </BigField>
        </div>

        <BigField label="Starts on">
          <input value={startsOn} onChange={(e) => setStartsOn(e.target.value)} type="date"
            style={bigInput} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors" />
        </BigField>
        <BigField label="Ends on">
          <input value={endsOn} onChange={(e) => setEndsOn(e.target.value)} type="date"
            style={bigInput} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors" />
        </BigField>

        <div className="col-span-1 sm:col-span-2">
          <BigField label="Location (optional)">
            {addingLocation ? (
              <div className="flex flex-col rounded-xl bg-muted/20 border border-border" style={{ gap: 8, padding: 12 }}>
                <input value={newLocName} onChange={(e) => setNewLocName(e.target.value)} placeholder="Location name" autoFocus
                  style={bigInput} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors" />
                <select value={newLocCityId} onChange={(e) => setNewLocCityId(e.target.value)}
                  style={selectStyle} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors">
                  <option value="" disabled>City (required)</option>
                  {cities.map((c: City) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                {newLocError && <p style={{ fontSize: 13 }} className="text-red-500">{newLocError}</p>}
                <div className="flex" style={{ gap: 8 }}>
                  <button type="button" onClick={() => { setNewLocError(""); createLocationMutation.mutate() }}
                    disabled={!newLocName.trim() || !newLocCityId || createLocationMutation.isPending}
                    style={{ height: 38, padding: "0 18px", borderRadius: 8, fontSize: 14, fontWeight: 600 }}
                    className="bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50">
                    {createLocationMutation.isPending ? "…" : "Add"}
                  </button>
                  <button type="button" onClick={() => { setAddingLocation(false); setNewLocError(""); setNewLocName(""); setNewLocCityId("") }}
                    style={{ height: 38, padding: "0 14px", borderRadius: 8, fontSize: 14, fontWeight: 500 }}
                    className="flex items-center gap-1.5 border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
                    <X size={15} /> Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex" style={{ gap: 10 }}>
                <select value={locationId} onChange={(e) => { setLocationId(e.target.value); setWarehouseId("") }}
                  style={selectStyle} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors">
                  <option value="">— None —</option>
                  {locations.map((l: Location) => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
                {canCreateLocation && (
                  <button type="button" onClick={() => setAddingLocation(true)}
                    style={{ height: 42, padding: "0 16px", borderRadius: 10, fontSize: 14, fontWeight: 500 }}
                    className="flex items-center gap-1.5 shrink-0 border border-border text-foreground hover:bg-muted transition-colors">
                    <Plus size={15} /> New location
                  </button>
                )}
              </div>
            )}
            <p style={{ fontSize: 13, margin: "6px 0 0" }} className="text-muted-foreground">The venue sessions inherit by default.</p>
          </BigField>
        </div>

        {locationId && (
          <div style={{ gridColumn: "span 2" }}>
            <BigField label="Warehouse (optional)">
              <select value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}
                style={selectStyle} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors">
                <option value="">— Select a warehouse —</option>
                {warehouses.map((w: Warehouse) => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
            </BigField>
          </div>
        )}

        <BigField label="Capacity (optional)">
          <input value={capacity} onChange={(e) => setCapacity(e.target.value)} type="number" placeholder="20"
            style={bigInput} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors" />
        </BigField>
        <BigField label="Session duration (hrs)">
          <input value={durationHours} onChange={(e) => setDurationHours(e.target.value)} type="number" step="0.5" min="0" placeholder="e.g. 2"
            style={bigInput} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors" />
        </BigField>
        <BigField label="Visibility">
          <div className="flex bg-muted" style={{ height: 42, padding: 3, gap: 3, borderRadius: 10 }}>
            <button type="button" onClick={() => setVisibility("public")}
              style={{ flex: 1, borderRadius: 8, fontSize: 14, fontWeight: 600 }}
              className={cn("transition-colors", visibility === "public" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground")}>Public</button>
            <button type="button" onClick={() => setVisibility("private")}
              style={{ flex: 1, borderRadius: 8, fontSize: 14, fontWeight: 600 }}
              className={cn("transition-colors", visibility === "private" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground")}>Private</button>
          </div>
        </BigField>
        <p style={{ fontSize: 13, maxWidth: "60ch", alignSelf: "end" }} className="text-muted-foreground m-0">
          Every session in this cohort uses this duration unless it has its own override. Shown to instructors before they apply, and feeds the payment letter&rsquo;s hours.
        </p>

        <div className="col-span-1 sm:col-span-2">
          <label className="flex items-center gap-2.5 text-foreground cursor-pointer select-none" style={{ fontSize: 14 }}>
            <input
              type="checkbox"
              checked={keepCourseAccessAfterCompletion}
              onChange={(e) => setKeepCourseAccessAfterCompletion(e.target.checked)}
              className="rounded border-border accent-primary w-4 h-4 cursor-pointer"
            />
            <span>Keep course access after completion</span>
          </label>
        </div>
      </div>

      {error && <p style={{ fontSize: 14 }} className="text-red-500">{error}</p>}
    </form>
  )
}

/* ════════════════════════ Step 2 — Sessions ═══════════════════════════ */

function SessionsStep({ cohort }: { cohort: Cohort }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [mode, setMode] = useState<"pattern" | "manual">("manual")
  const [days, setDays] = useState<number[]>([1, 3]) // Tue, Thu
  const [weeks, setWeeks] = useState(8)
  const [calMonth, setCalMonth] = useState(() => cohort.starts_on ? new Date(cohort.starts_on + "T00:00:00") : new Date())
  const [pending, setPending] = useState<Set<string>>(new Set())
  const [error, setError] = useState("")

  const sessionsKey = ["wizard-sessions", cohort.id]
  const { data: sessions = [], isLoading } = useQuery({ queryKey: sessionsKey, queryFn: () => getSessionsApi(cohort.id) })

  const generate = useMutation({
    mutationFn: () => generateSessionsApi(cohort.id, { weekdays: days, count: weeks, starts_at: null }),
    onSuccess: (r) => { toast.success(`${r.created.length} sessions created${r.skipped ? `, ${r.skipped} already existed` : ""}`); qc.invalidateQueries({ queryKey: sessionsKey }) },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to generate sessions")),
  })

  const addManual = useMutation({
    mutationFn: async () => {
      for (const iso of pending) await addSessionApi(cohort.id, { meeting_date: iso })
    },
    onSuccess: () => { toast.success(`${pending.size} session${pending.size === 1 ? "" : "s"} added`); setPending(new Set()); qc.invalidateQueries({ queryKey: sessionsKey }) },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to add one or more sessions")),
  })

  const remove = useMutation({
    mutationFn: (sessionId: string) => deleteSessionApi(cohort.id, sessionId),
    onSuccess: () => { toast.success("Session removed"); qc.invalidateQueries({ queryKey: sessionsKey }) },
    onError: (e: any) => setError(getErrorMessage(e, "Could not remove that session — it may already have activity")),
  })

  const togglePending = (iso: string) => setPending((s) => {
    const next = new Set(s)
    if (next.has(iso)) next.delete(iso)
    else next.add(iso)
    return next
  })

  const calCells = useMemo(() => {
    const year = calMonth.getFullYear(), month = calMonth.getMonth()
    const first = new Date(year, month, 1)
    const firstWeekday = (first.getDay() + 6) % 7 // Monday-first offset
    const daysInMonth = new Date(year, month + 1, 0).getDate()
    const existing = new Set(sessions.map((s) => s.meeting_date))
    const cells: { iso: string | null; label: string }[] = []
    for (let i = 0; i < firstWeekday; i++) cells.push({ iso: null, label: "" })
    for (let d = 1; d <= daysInMonth; d++) {
      const iso = toISODate(new Date(year, month, d))
      cells.push({ iso: existing.has(iso) ? null : iso, label: String(d) })
    }
    return cells
  }, [calMonth, sessions])

  const segStyle = (on: boolean): React.CSSProperties => ({
    height: 40, padding: "0 18px", borderRadius: 8, fontSize: 14, fontWeight: 600,
    background: on ? "hsl(var(--card))" : "transparent", color: on ? "hsl(var(--foreground))" : "hsl(var(--muted-foreground))",
    boxShadow: on ? "0 1px 3px rgba(0,0,0,.08)" : "none",
  })

  return (
    <div className="flex flex-col" style={{ gap: 28 }}>
      <StepIntro
        eyebrow="Sessions" title="When does this cohort meet?"
        lede="Generate the whole run from a weekly pattern, or pick the dates by hand."
        right={
          <div className="flex shrink-0 bg-muted w-full sm:w-auto" style={{ padding: 4, gap: 4, borderRadius: 10 }}>
            <button onClick={() => setMode("manual")} style={{ ...segStyle(mode === "manual"), flex: 1 }}>Pick dates manually</button>
            <button onClick={() => setMode("pattern")} style={{ ...segStyle(mode === "pattern"), flex: 1 }}>Generate by pattern</button>
          </div>
        }
      />

      {mode === "pattern" ? (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.6fr)] gap-6 lg:gap-9 items-start">
          <div className="flex flex-col" style={{ gap: 24 }}>
            <BigField label="Which days">
              <div className="flex flex-wrap" style={{ gap: 8 }}>
                {WEEKDAYS.map((label, i) => (
                  <button key={label} type="button"
                    onClick={() => setDays((d) => d.includes(i) ? d.filter((x) => x !== i) : [...d, i])}
                    style={{ width: 64, height: 42, borderRadius: 10, fontSize: 14, fontWeight: 600 }}
                    className={cn("transition-colors",
                      days.includes(i) ? "bg-primary/10 border-[1.5px] border-primary text-primary" : "border border-border text-muted-foreground")}
                  >{label}</button>
                ))}
              </div>
            </BigField>
            <div className="flex items-end flex-wrap" style={{ gap: 16 }}>
              <BigField label="How many weeks">
                <input type="number" min={1} value={weeks} onChange={(e) => setWeeks(Math.max(1, Number(e.target.value) || 1))}
                  style={{ ...heroInput, width: 140 }} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors" />
              </BigField>
              <p style={{ fontSize: 13, maxWidth: "34ch", margin: "0 0 6px" }} className="text-muted-foreground">
                {cohort.starts_on ? `Counting from the cohort's start date, ${fmtDate(cohort.starts_on)}.` : "Set a start date on step 1 first."}
              </p>
            </div>
            <button onClick={() => { setError(""); generate.mutate() }} disabled={!cohort.starts_on || days.length === 0 || generate.isPending}
              style={{ alignSelf: "flex-start", height: 40, padding: "0 20px", borderRadius: 8, fontSize: 14, fontWeight: 600 }}
              className="border border-border text-foreground hover:bg-muted transition-colors disabled:opacity-50">
              {generate.isPending ? "Generating…" : "Generate sessions"}
            </button>
          </div>
          <SessionsList sessions={sessions} isLoading={isLoading} onRemove={(id) => remove.mutate(id)} countLabel="Preview" count={sessions.length} />
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.6fr)] gap-6 lg:gap-9 items-start">
          <div className="flex flex-col" style={{ gap: 16 }}>
            <div className="flex items-center justify-between">
              <span style={{ fontFamily: OUTFIT, fontSize: 20, fontWeight: 600, letterSpacing: "-0.01em" }} className="text-foreground">
                {calMonth.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
              </span>
              <div className="flex" style={{ gap: 6 }}>
                <button onClick={() => setCalMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1))}
                  style={{ width: 34, height: 34, borderRadius: 8 }} className="border border-border flex items-center justify-center text-muted-foreground hover:bg-muted transition-colors"><ChevronLeft size={18} /></button>
                <button onClick={() => setCalMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1))}
                  style={{ width: 34, height: 34, borderRadius: 8 }} className="border border-border flex items-center justify-center text-muted-foreground hover:bg-muted transition-colors"><ChevronRight size={18} /></button>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0,1fr))", gap: 6 }}>
              {WEEKDAYS.map((d) => <div key={d} style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", paddingBottom: 4 }} className="text-center text-muted-foreground">{d[0]}</div>)}
              {calCells.map((c, i) => {
                if (!c.label) return <div key={i} />
                const existing = !c.iso
                const selected = c.iso ? pending.has(c.iso) : false
                return (
                  <button
                    key={i}
                    disabled={existing}
                    onClick={() => c.iso && togglePending(c.iso)}
                    style={{ height: 42, borderRadius: 8, fontSize: 15, fontVariantNumeric: "tabular-nums", fontWeight: selected ? 700 : 400 }}
                    className={cn(
                      "transition-colors",
                      existing ? "text-muted-foreground/30 cursor-not-allowed border border-transparent" :
                        selected ? "bg-primary text-primary-foreground border border-primary" : "border border-transparent text-foreground hover:bg-muted",
                    )}
                  >{c.label}</button>
                )
              })}
            </div>
            <p style={{ fontSize: 13 }} className="text-muted-foreground">Click a date on the calendar to add it. Faded dates already have a session.</p>
          </div>
          <div className="flex flex-col" style={{ gap: 16 }}>
            <div className="flex items-baseline justify-between" style={{ gap: 12 }}>
              <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }} className="text-muted-foreground">Picked</span>
              <span style={{ fontFamily: OUTFIT, fontSize: 18, fontWeight: 600 }} className="text-primary">{pending.size} selected</span>
            </div>
            <button onClick={() => { setError(""); addManual.mutate() }} disabled={pending.size === 0 || addManual.isPending}
              style={{ alignSelf: "flex-start", height: 40, padding: "0 20px", borderRadius: 8, fontSize: 14, fontWeight: 600 }}
              className="bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50">
              {addManual.isPending ? "Adding…" : `Add ${pending.size || ""} session${pending.size === 1 ? "" : "s"}`}
            </button>
            <SessionsList sessions={sessions} isLoading={isLoading} onRemove={(id) => remove.mutate(id)} countLabel="This cohort's sessions" count={sessions.length} />
          </div>
        </div>
      )}
      {error && <p style={{ fontSize: 14 }} className="text-red-500">{error}</p>}
    </div>
  )
}

function SessionsList({ sessions, isLoading, onRemove, countLabel, count }: {
  sessions: Session[]; isLoading: boolean; onRemove: (id: string) => void; countLabel: string; count: number
}) {
  return (
    <div className="flex flex-col" style={{ gap: 14 }}>
      <div className="flex items-baseline justify-between" style={{ gap: 12 }}>
        <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }} className="text-muted-foreground">{countLabel}</span>
        <span style={{ fontFamily: OUTFIT, fontSize: 18, fontWeight: 600 }} className="text-primary">{count} sessions</span>
      </div>
      <div className="overflow-y-auto flex flex-col" style={{ gap: 10, maxHeight: "48vh", padding: "2px 4px 4px 2px" }}>
        {isLoading ? <Spinner /> : sessions.length === 0 ? (
          <p style={{ fontSize: 14 }} className="text-muted-foreground italic">No sessions yet.</p>
        ) : sessions
          .slice()
          .sort((a, b) => a.meeting_date.localeCompare(b.meeting_date))
          .map((s, i) => (
            <div key={s.id}
              style={{ padding: "12px 16px", borderRadius: 10, boxShadow: CARD_SHADOW }}
              className="flex items-center justify-between border border-border bg-card">
              <span style={{ fontFamily: OUTFIT, fontSize: 16, fontWeight: 600, letterSpacing: "-0.01em" }} className="text-foreground">
                {fmtDate(s.meeting_date)}
              </span>
              <div className="flex items-center" style={{ gap: 12 }}>
                <span style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", fontVariantNumeric: "tabular-nums" }} className="text-muted-foreground">
                  Session {i + 1}
                </span>
                <button onClick={() => onRemove(s.id)} style={{ width: 28, height: 28 }} className="flex items-center justify-center rounded-lg text-muted-foreground hover:text-red-600 hover:bg-muted transition-colors" aria-label="Remove session">
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))}
      </div>
    </div>
  )
}

/* ═══════════════════ Step 3 — Roles & checklist ════════════════════════ */

function RolesChecklistStep({ cohort, onFormChange }: {
  cohort: Cohort
  onFormChange: (form: { ensure: () => Promise<void> }) => void
}) {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["wizard-sessions", cohort.id], queryFn: () => getSessionsApi(cohort.id),
  })
  const selected = sessions.find((s) => s.id === selectedId) ?? null

  // Same query key CohortRolesPanel's own useRolesDraft uses — shared cache,
  // not a second network round trip.
  const { data: openings = [] } = useQuery({
    queryKey: ["cohort-openings-defaults", cohort.id], queryFn: () => getCohortOpeningsApi(cohort.id),
  })
  const { data: roles = [] } = useQuery({
    queryKey: ["delivery-roles"], queryFn: () => getDeliveryRolesApi(),
  })

  useEffect(() => {
    onFormChange({
      ensure: async () => {
        // Something already exists (saved by hand, or a previous visit to
        // this step already ensured it) — never overwrite a real choice
        // with blanket defaults.
        if (openings.length > 0) return
        const active = roles.filter((r) => r.is_active)
        if (active.length === 0) return
        await setCohortOpeningsApi({
          cohortId: cohort.id,
          openings: active.map((r) => ({
            role_id: r.id, slots: 1, amount_aed: null, notes: null, responsibilities_override: null,
          })),
        })
        qc.invalidateQueries({ queryKey: ["cohort-openings-defaults", cohort.id] })
      },
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cohort.id, openings, roles])

  return (
    <div className="flex flex-col" style={{ gap: 28 }}>
      <StepIntro
        eyebrow="Roles & checklist" title="Who runs a day, and what they do" ledeWidth={70}
        lede="These are the cohort's defaults. Pick a session on the right only if that one day needs to differ."
      />
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,55fr)_minmax(0,45fr)] gap-6 lg:gap-9 items-start">
        <div className="flex flex-col" style={{ gap: 20 }}>
          {selected ? (
            <div
              style={{ padding: "12px 16px", borderRadius: 10, background: "hsl(var(--primary) / 0.10)", border: "1px solid hsl(var(--primary) / 0.22)" }}
              className="flex items-center justify-between"
            >
              <span style={{ fontFamily: OUTFIT, fontSize: 16, fontWeight: 600 }} className="text-foreground">Overriding: {fmtDate(selected.meeting_date)}</span>
              <button onClick={() => setSelectedId(null)} style={{ fontSize: 14, fontWeight: 600 }} className="text-primary hover:opacity-80 shrink-0 transition-opacity">
                Reset to cohort default
              </button>
            </div>
          ) : (
            <div style={{ height: 32, padding: "0 14px", borderRadius: 999, fontSize: 13, fontWeight: 600 }} className="inline-flex self-start items-center bg-muted border border-border text-muted-foreground">
              Inherited from program
            </div>
          )}

          {selected ? (
            <div className="flex flex-col" style={{ gap: 24 }}>
              <SessionOpeningsPanel sessionId={selected.id} large />
              <SessionChecklistPanel sessionId={selected.id} cohortId={cohort.id} programId={cohort.program_id} large />
            </div>
          ) : (
            <CohortRolesPanel cohort={cohort} large />
          )}
        </div>

        <div className="flex flex-col" style={{ gap: 14, position: "sticky", top: 0 }}>
          <div className="flex flex-col" style={{ gap: 4 }}>
            <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }} className="text-muted-foreground">This cohort&rsquo;s sessions</span>
            <span style={{ fontSize: 13 }} className="text-muted-foreground">Pick one to override just that day.</span>
          </div>
          <div className="flex flex-col overflow-y-auto" style={{ gap: 10, maxHeight: "32rem", padding: "2px 4px 4px 2px" }}>
            {isLoading ? <Spinner /> : sessions.length === 0 ? (
              <p style={{ fontSize: 14 }} className="text-muted-foreground italic">No sessions yet — add some on the Sessions step first.</p>
            ) : sessions
              .slice()
              .sort((a, b) => a.meeting_date.localeCompare(b.meeting_date))
              .map((s, i) => {
                const isSel = s.id === selectedId
                return (
                  <button
                    key={s.id}
                    onClick={() => setSelectedId(isSel ? null : s.id)}
                    style={{
                      padding: "12px 16px", borderRadius: 10, textAlign: "left",
                      background: isSel ? "hsl(var(--primary) / 0.10)" : "hsl(var(--card))",
                      border: isSel ? "1.5px solid hsl(var(--primary))" : "1px solid hsl(var(--border))",
                      boxShadow: isSel ? "0 3px 0 hsl(var(--primary)), 0 10px 20px -5px rgba(40,16,80,.45)" : CARD_SHADOW,
                    }}
                    className="flex items-center justify-between transition-colors"
                  >
                    <span className="flex flex-col" style={{ gap: 2 }}>
                      <span style={{ fontFamily: OUTFIT, fontSize: 15, fontWeight: 600 }} className="text-foreground">Session {i + 1}</span>
                      <span style={{ fontSize: 13 }} className="text-muted-foreground">{fmtDate(s.meeting_date)}</span>
                    </span>
                    {isSel && <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em" }} className="text-primary">Selected</span>}
                  </button>
                )
              })}
          </div>
        </div>
      </div>
    </div>
  )
}

/* ══════════════════════ Step 5 — Review & finish ═══════════════════════ */

/** Lighter than `ProgramWizard.tsx`'s own `LmsChecklistStep` — the real
 * checklist lives on the program (`LmsProgram.program_id` is unique, shared
 * by every cohort of it), so there's nothing cohort-specific to author
 * here. Just: does one exist yet, and if not, a single one-click "create
 * an empty shell" action — no name field, no item authoring. Building the
 * actual checklist happens on the Program wizard/page, or per-cohort tweaks
 * later from this cohort's own LMS tab (`CohortDetail.tsx`). */
function LmsChecklistStep({ cohort, program }: { cohort: Cohort; program: Program }) {
  const queryClient = useQueryClient()
  const { data: found = [], isLoading } = useQuery<LmsProgram[]>({
    queryKey: ["lms-program-for-program", program.id], queryFn: () => listLmsProgramsApi(program.id),
  })
  const [created, setCreated] = useState<LmsProgram | null>(null)
  const effective = created ?? found[0] ?? null

  const createMutation = useMutation({
    mutationFn: () => createLmsProgramApi({ program_id: program.id, name: `${program.name} Checklist` }),
    onSuccess: (p) => {
      setCreated(p)
      void queryClient.invalidateQueries({ queryKey: ["lms-program-for-program", program.id] })
    },
  })

  if (isLoading) return <Spinner />

  if (!effective) {
    return (
      <div className="flex flex-col" style={{ gap: 16, maxWidth: "60ch" }}>
        <p style={{ fontSize: 15 }} className="text-muted-foreground m-0">This program has no LMS checklist yet.</p>
        <button
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
          style={{ height: 42, padding: "0 20px", borderRadius: 10, fontFamily: OUTFIT, fontSize: 15, fontWeight: 600, width: "fit-content" }}
          className="bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          <Plus size={15} className="inline mr-1.5" style={{ verticalAlign: -2 }} />
          {createMutation.isPending ? "Creating…" : "Create an empty LMS checklist for this program"}
        </button>
      </div>
    )
  }

  // A checklist exists for the program — build/edit *this cohort's* own
  // checklist right here, same component CohortDetail.tsx's LMS tab uses.
  // Starts as an editable view of the program's own checklist; editing
  // anything forks a real per-cohort override server-side, transparently.
  return <CohortOverrideEditor cohortId={cohort.id} isStaff readOnly={false} hideResync />
}

/* ═══════════════════════════ Step 6 — Staffing ══════════════════════════ */
/* The two direct-action entry points, same modals the cohort page's       */
/* Sessions-tab bulk toolbar already uses — not the full applicant/call    */
/* review flow, which stays on the cohort page.                            */

function StaffingStep({ cohort }: { cohort: Cohort }) {
  const queryClient = useQueryClient()
  const { data: sessions = [] } = useQuery({ queryKey: ["wizard-sessions", cohort.id], queryFn: () => getSessionsApi(cohort.id) })
  const { data: assignments = [] } = useQuery<CohortAssignment[]>({
    queryKey: ["cohort-assignments", cohort.id], queryFn: () => listCohortAssignmentsApi(cohort.id),
  })
  const { data: calls = [] } = useQuery<CohortCall[]>({
    queryKey: ["cohort-calls", cohort.id], queryFn: () => listCohortCallsApi(cohort.id),
  })
  const [selectedSessionIds, setSelectedSessionIds] = useState<string[]>([])
  const [modal, setModal] = useState<"assign" | "call" | null>(null)

  const toggleSession = (id: string) =>
    setSelectedSessionIds((prev) => prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id])

  const done = () => {
    setModal(null)
    void queryClient.invalidateQueries({ queryKey: ["wizard-sessions", cohort.id] })
    void queryClient.invalidateQueries({ queryKey: ["cohort-assignments", cohort.id] })
    void queryClient.invalidateQueries({ queryKey: ["cohort-calls", cohort.id] })
  }

  // Aggregate session instructor assignments by (userName + roleName)
  const aggregatedStaffing = useMemo(() => {
    const map = new Map<string, { userName: string; roleName: string; sessionIds: Set<string> }>()
    for (const s of sessions) {
      for (const i of s.instructors ?? []) {
        const key = `${i.full_name.toLowerCase().trim()}||${(i.role || "").toLowerCase().trim()}`
        const existing = map.get(key)
        if (existing) {
          existing.sessionIds.add(s.id)
        } else {
          map.set(key, {
            userName: i.full_name,
            roleName: i.role,
            sessionIds: new Set([s.id]),
          })
        }
      }
    }
    return Array.from(map.values())
  }, [sessions])

  // Same panel the cohort page's own Assessment tab uses — reused as-is
  // (2026-09-13) so overriding the program's seeded default doesn't require
  // leaving the wizard. Shown regardless of whether sessions exist yet: it
  // gates who can apply once a call opens, not the calls themselves.
  const assessmentPanel = (
    <div className="pb-5 border-b border-border">
      <AssessmentAssignmentPanel cohortId={cohort.id} />
    </div>
  )

  if (sessions.length === 0) {
    return (
      <div className="flex flex-col" style={{ gap: 20 }}>
        {assessmentPanel}
        <EmptyState title="No sessions yet" hint="Add sessions on the Sessions step first — there's nothing to staff yet." />
      </div>
    )
  }

  return (
    <div className="flex flex-col" style={{ gap: 20 }}>
      {assessmentPanel}
      <div className="flex flex-wrap gap-2">
        {sessions.map((s) => {
          const isSelected = selectedSessionIds.includes(s.id)
          const staffedNames = s.instructors?.map((i) => i.full_name).join(", ")
          const isOpenCall = s.staffing_status === "open_call"
          return (
            <button
              key={s.id} type="button" onClick={() => toggleSession(s.id)}
              style={{ height: 38, padding: "0 14px", borderRadius: 10, fontSize: 13, fontWeight: 500 }}
              className={cn(
                "border transition-all flex items-center gap-2 cursor-pointer select-none",
                isSelected
                  ? "bg-primary text-primary-foreground border-primary shadow-sm"
                  : "border-border bg-card text-foreground hover:bg-muted"
              )}
            >
              <span>{s.meeting_date}{s.title ? ` · ${s.title}` : ""}</span>
              {staffedNames && (
                <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", isSelected ? "bg-primary-foreground/20 text-primary-foreground" : "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20")}>
                  ✓ {staffedNames}
                </span>
              )}
              {!staffedNames && isOpenCall && (
                <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", isSelected ? "bg-primary-foreground/20 text-primary-foreground" : "bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/20")}>
                  Call open
                </span>
              )}
            </button>
          )
        })}
      </div>

      <div className="flex flex-col sm:flex-row gap-2.5 sm:gap-3">
        <button
          onClick={() => setModal("assign")}
          disabled={selectedSessionIds.length === 0}
          style={{ height: 42, padding: "0 20px", borderRadius: 10, fontFamily: OUTFIT, fontSize: 14, fontWeight: 600 }}
          className="bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50 cursor-pointer w-full sm:w-auto"
        >Assign instructor ({selectedSessionIds.length})</button>
        <button
          onClick={() => setModal("call")}
          disabled={selectedSessionIds.length === 0}
          style={{ height: 42, padding: "0 20px", borderRadius: 10, fontSize: 14, fontWeight: 500 }}
          className="border border-border bg-card text-foreground hover:bg-muted transition-colors disabled:opacity-50 cursor-pointer w-full sm:w-auto"
        >Open a call ({selectedSessionIds.length})</button>
      </div>

      {calls.length > 0 && (
        <div className="flex flex-col gap-2">
          <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }} className="text-muted-foreground">
            Open Calls ({calls.length})
          </span>
          <div className="flex flex-col gap-2">
            {calls.map((c) => (
              <div key={c.id} className="border border-border bg-card rounded-xl p-3 flex items-center justify-between gap-3">
                <div className="flex flex-col gap-0.5 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-foreground truncate">
                      {c.label || "Grouped Session Call"}
                    </span>
                    <span className={cn(
                      "text-[10px] font-bold px-2 py-0.5 rounded-full border shrink-0",
                      c.status === "open"
                        ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                        : "bg-muted text-muted-foreground border-border"
                    )}>
                      {c.status === "open" ? "Open" : "Closed"}
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground truncate">
                    {c.sessions.length} session(s): {c.sessions.map((s) => s.meeting_date).join(", ")}
                    {c.target_user_ids.length > 0 ? ` · Restricted to ${c.target_user_ids.length} instructor(s)` : " · Public call"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-col gap-2">
        <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }} className="text-muted-foreground">
          Staffed so far
        </span>
        {aggregatedStaffing.length === 0 && assignments.length === 0 && calls.length === 0 ? (
          <p style={{ fontSize: 14 }} className="text-muted-foreground m-0">Nobody staffed yet.</p>
        ) : (
          <div className="flex flex-col gap-2.5">
            {aggregatedStaffing.map((item) => (
              <div key={item.userName + item.roleName} className="border border-border bg-card rounded-xl p-3.5 flex flex-col gap-2.5">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-semibold text-foreground truncate">{item.userName}</span>
                  <span className="text-xs font-semibold px-3 py-1 rounded-full bg-primary/10 text-primary border border-primary/20 shrink-0">
                    {item.roleName}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {sessions.map((s) => {
                    const isAssigned = item.sessionIds.has(s.id)
                    return (
                      <span
                        key={s.id}
                        className={cn(
                          "px-2.5 py-1 rounded-lg text-xs border transition-all select-none",
                          isAssigned
                            ? "bg-primary/20 text-primary border-primary/30 font-semibold shadow-2xs"
                            : "bg-muted/30 text-muted-foreground/50 border-border/30 opacity-50"
                        )}
                      >
                        {s.meeting_date}{s.title ? ` · ${s.title}` : ""}
                      </span>
                    )
                  })}
                </div>
              </div>
            ))}
            {assignments.map((a) => (
              <div key={a.id} className="border border-border bg-card rounded-xl px-4 py-3 flex items-center justify-between">
                <div className="flex flex-col">
                  <span className="text-sm font-semibold text-foreground">{a.full_name}</span>
                  <span className="text-xs text-muted-foreground">Cohort Roster</span>
                </div>
                <span className="text-xs font-semibold px-3 py-1 rounded-lg bg-muted text-muted-foreground border border-border">
                  {a.role_name}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {modal === "assign" && (
        <BulkAssignInstructorModal cohort={cohort} sessionIds={selectedSessionIds} onClose={() => setModal(null)} onDone={done} />
      )}
      {modal === "call" && (
        <BulkOpenCallModal cohort={cohort} sessionIds={selectedSessionIds} onClose={() => setModal(null)} onDone={done} />
      )}
    </div>
  )
}

/* ═══════════════════════════ Step 7 — Students ══════════════════════════ */

function StudentsStep({ cohort }: { cohort: Cohort }) {
  const queryClient = useQueryClient()
  const { data: sessions = [] } = useQuery({ queryKey: ["wizard-sessions", cohort.id], queryFn: () => getSessionsApi(cohort.id) })
  const { data: registrations = [] } = useQuery<Registration[]>({
    queryKey: ["wizard-registrations", cohort.id], queryFn: () => getRegistrationsApi(cohort.id),
  })
  const [modal, setModal] = useState<"desk" | "import" | null>(null)
  const [editingRegistration, setEditingRegistration] = useState<Registration | null>(null)

  const done = () => {
    setModal(null)
    setEditingRegistration(null)
    void queryClient.invalidateQueries({ queryKey: ["wizard-registrations", cohort.id] })
  }

  return (
    <div className="flex flex-col" style={{ gap: 20 }}>
      <div className="flex flex-col sm:flex-row gap-2.5 sm:gap-3">
        <button
          onClick={() => setModal("desk")}
          style={{ height: 42, padding: "0 20px", borderRadius: 10, fontFamily: OUTFIT, fontSize: 15, fontWeight: 600 }}
          className="bg-primary text-primary-foreground hover:opacity-90 transition-opacity w-full sm:w-auto"
        >Add a student…</button>
        <button
          onClick={() => setModal("import")}
          style={{ height: 42, padding: "0 20px", borderRadius: 10, fontSize: 15, fontWeight: 500 }}
          className="border border-border text-foreground hover:bg-muted transition-colors w-full sm:w-auto"
        >Import a list…</button>
      </div>

      <div className="flex flex-col" style={{ gap: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }} className="text-muted-foreground">
          Registered so far ({registrations.length})
        </span>
        {registrations.length === 0 ? (
          <p style={{ fontSize: 14 }} className="text-muted-foreground m-0">Nobody registered yet.</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {registrations.map((r) => (
              <div
                key={r.id}
                onClick={() => setEditingRegistration(r)}
                className="border border-border bg-card hover:border-primary/50 hover:shadow-xs cursor-pointer rounded-xl p-4 flex flex-col gap-3 transition-all group relative"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="w-9 h-9 rounded-full bg-primary/10 text-primary flex items-center justify-center font-semibold text-sm shrink-0 uppercase">
                      {r.student_name ? r.student_name.charAt(0) : "S"}
                    </div>
                    <span style={{ fontFamily: OUTFIT }} className="font-semibold text-base text-foreground truncate group-hover:text-primary transition-colors">
                      {r.student_name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {r.status && (
                      <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-muted text-muted-foreground border border-border shrink-0 capitalize">
                        {r.status.replace(/_/g, " ")}
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        setEditingRegistration(r)
                      }}
                      className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors opacity-70 group-hover:opacity-100"
                      title="Edit student info"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <div className="flex flex-col gap-1.5 text-sm text-muted-foreground pt-1.5 border-t border-border/50">
                  <div className="flex items-center gap-2 text-xs">
                    <Mail className="w-3.5 h-3.5 shrink-0 text-muted-foreground/70" />
                    <span className="truncate">{r.student_email || "No email address"}</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <Phone className="w-3.5 h-3.5 shrink-0 text-muted-foreground/70" />
                    <span>{r.student_phone || "No phone number"}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {modal === "desk" && <DeskRegisterModal cohort={cohort} sessions={sessions} onClose={() => setModal(null)} onSuccess={done} />}
      {modal === "import" && <ImportListModal cohort={cohort} onClose={() => setModal(null)} onImported={done} />}
      {editingRegistration && (
        <EditStudentModal
          registration={editingRegistration}
          onClose={() => setEditingRegistration(null)}
          onSuccess={done}
        />
      )}
    </div>
  )
}

function CompetitionJudgingStep({ cohort }: { cohort: Cohort }) {
  const [activeTab, setActiveTab] = useState<"rubric" | "judges">("rubric")
  const [windowsModalOpen, setWindowsModalOpen] = useState(false)

  return (
    <div className="flex flex-col gap-6 max-w-5xl">
      <StepIntro
        eyebrow="Judging & Competition"
        title="Setup Rubric, Judges & Timing Windows"
        ledeWidth={70}
        lede="Set your scoring criteria, invite judges, and configure submission timing windows for this stage. You can edit everything later."
        right={
          <button
            type="button"
            onClick={() => setWindowsModalOpen(true)}
            className="flex items-center gap-1.5 h-9 px-3.5 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors shrink-0 shadow-sm"
          >
            <Clock size={14} className="text-primary" /> Submission Windows
          </button>
        }
      />

      <div className="flex items-center gap-2 border-b border-border pb-3">
        <button
          type="button"
          onClick={() => setActiveTab("rubric")}
          className={cn(
            "px-4 py-2 rounded-xl text-sm font-medium transition-colors",
            activeTab === "rubric" ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:text-foreground hover:bg-muted"
          )}
        >
          Rubric Criteria
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("judges")}
          className={cn(
            "px-4 py-2 rounded-xl text-sm font-medium transition-colors",
            activeTab === "judges" ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:text-foreground hover:bg-muted"
          )}
        >
          Judges
        </button>
      </div>

      <div className="mt-1">
        {activeTab === "rubric" && <RubricTab cohortId={cohort.id} />}
        {activeTab === "judges" && <JudgesTab cohortId={cohort.id} />}
      </div>

      <SubmissionWindowsModal
        cohortId={cohort.id}
        open={windowsModalOpen}
        onClose={() => setWindowsModalOpen(false)}
      />
    </div>
  )
}

function ReviewStep({ cohort, program }: { cohort: Cohort; program?: Program }) {
  const { data: sessions = [] } = useQuery({ queryKey: ["wizard-sessions", cohort.id], queryFn: () => getSessionsApi(cohort.id) })
  const { data: openings = [] } = useQuery({ queryKey: ["cohort-openings-defaults", cohort.id], queryFn: () => getCohortOpeningsApi(cohort.id) })
  const { data: materials = [] } = useQuery({ queryKey: ["materials", JSON.stringify({ cohort_id: cohort.id })], queryFn: () => getMaterialsApi({ cohort_id: cohort.id }) })
  const { data: override } = useQuery({
    queryKey: ["lms-cohort-override", cohort.id], queryFn: () => getCohortProgramOverrideApi(cohort.id),
    retry: false,
  })
  const { data: assignments = [] } = useQuery<CohortAssignment[]>({
    queryKey: ["cohort-assignments", cohort.id], queryFn: () => listCohortAssignmentsApi(cohort.id),
  })
  const { data: calls = [] } = useQuery<CohortCall[]>({
    queryKey: ["cohort-calls", cohort.id], queryFn: () => listCohortCallsApi(cohort.id),
  })
  const { data: registrations = [] } = useQuery<Registration[]>({
    queryKey: ["wizard-registrations", cohort.id], queryFn: () => getRegistrationsApi(cohort.id),
  })

  const sorted = sessions.slice().sort((a, b) => a.meeting_date.localeCompare(b.meeting_date))
  const rows: { label: string; value: string }[] = [
    { label: "Name", value: cohort.name },
    { label: "Program", value: program?.name ?? "—" },
    { label: "Dates", value: cohort.starts_on ? `${fmtDate(cohort.starts_on)}${cohort.ends_on ? ` – ${fmtDate(cohort.ends_on)}` : ""}` : "Not set" },
    { label: "Location", value: cohort.location_name ?? "Not set" },
    { label: "Capacity · duration", value: `${cohort.capacity ?? "—"} students · ${cohort.duration_hours ?? "—"} hrs / session` },
    { label: "Visibility", value: cohort.visibility === "public" ? "Public" : "Private" },
    { label: "Course access after completion", value: cohort.keep_course_access_after_completion ? "Yes" : "No" },
    {
      label: "Sessions",
      value: sorted.length === 0 ? "None yet — add them from the cohort page"
        : `${sorted.length} session${sorted.length === 1 ? "" : "s"} · ${fmtDate(sorted[0].meeting_date)} to ${fmtDate(sorted[sorted.length - 1].meeting_date)}`,
    },
    {
      label: "Roles & checklist",
      value: openings.length === 0 ? "Using program/platform defaults" : `${openings.length} role${openings.length === 1 ? "" : "s"} customized for this cohort`,
    },
    {
      label: "LMS Checklist",
      value: !override ? "Not set up yet — this cohort's students will see an empty checklist"
        : `${override.items.length} step${override.items.length === 1 ? "" : "s"}${override.is_inherited ? " (shared with every cohort of this program)" : " (customized for this cohort)"}`,
    },
    {
      label: "Materials",
      value: materials.length === 0 ? "Inherited from program" : `${materials.length} item${materials.length === 1 ? "" : "s"} set for this cohort`,
    },
    {
      label: "Staffing",
      value: (() => {
        const sessionInstructorsCount = sessions.reduce((acc, s) => acc + (s.instructors?.length ?? 0), 0)
        const callsCount = calls.length
        if (sessionInstructorsCount === 0 && assignments.length === 0 && callsCount === 0) return "Nobody staffed yet"
        const parts: string[] = []
        if (sessionInstructorsCount > 0) parts.push(`${sessionInstructorsCount} instructor assignment${sessionInstructorsCount === 1 ? "" : "s"}`)
        if (assignments.length > 0) parts.push(`${assignments.length} roster instructor${assignments.length === 1 ? "" : "s"}`)
        if (callsCount > 0) parts.push(`${callsCount} open call${callsCount === 1 ? "" : "s"}`)
        return parts.join(", ")
      })(),
    },
    {
      label: "Students",
      value: registrations.length === 0 ? "Nobody registered yet" : `${registrations.length} student${registrations.length === 1 ? "" : "s"} registered`,
    },
    ...(Boolean(program?.is_competition || cohort.program_is_competition) ? [{
      label: "Judging & Competition",
      value: "Rubric, timing windows and judges can be managed from the Judging Dashboard",
    }] : []),
  ]

  return (
    <div className="flex flex-col" style={{ gap: 28 }}>
      <div className="flex items-end justify-between flex-wrap gap-4 sm:gap-5">
        <div className="flex flex-col gap-1.5 min-w-0">
          <p style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }} className="text-primary m-0">Review &amp; create</p>
          <h2 style={{ fontFamily: OUTFIT }} className="text-foreground m-0 text-2xl sm:text-3xl font-semibold tracking-tight leading-tight">{cohort.name}</h2>
          <p style={{ fontSize: 15 }} className="text-muted-foreground m-0">{program?.name ?? ""}</p>
        </div>
        <p style={{ fontSize: 13, maxWidth: "34ch", margin: "0 0 4px" }} className="text-muted-foreground">You can change anything later from the cohort page.</p>
      </div>

      <div className="flex flex-col gap-2.5 p-0.5">
        {rows.map((r) => (
          <div key={r.label}
            style={{ boxShadow: CARD_SHADOW }}
            className="border border-border bg-card grid grid-cols-1 sm:grid-cols-[200px_minmax(0,1fr)] gap-1.5 sm:gap-5 items-start sm:items-center p-3.5 sm:px-4 sm:py-3.5 rounded-xl">
            <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }} className="text-muted-foreground">{r.label}</span>
            <span style={{ fontSize: 15 }} className="text-foreground break-words">{r.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
