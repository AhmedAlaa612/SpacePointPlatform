/** Full-page guided cohort setup (replaces the flat "New cohort" modal for
 *  creation). Same full-page-overlay shell as the LMS's Madar phase drawer
 *  (`pages/learn/missions/MadarPhaseDrawer.tsx`) — one focused step at a
 *  time instead of tabs ops had to discover on their own.
 *
 *  Visual scale is deliberately its own thing, not the compact admin-table
 *  density the rest of `pages/admin` uses: big Outfit display headlines,
 *  56-64px inputs, full-width fluid grids — a one-off "editorial" pass the
 *  boss signed off on for this screen specifically (ported from the
 *  approved Claude Design export). The panels it embeds (CohortRolesPanel,
 *  SessionOpeningsPanel, SessionChecklistPanel, MaterialsPanel) keep their
 *  normal compact style — they're shared components other real screens
 *  use, not this wizard's own chrome to restyle.
 *
 *  Deliberately NOT a draft-then-submit wizard: the cohort is created as
 *  soon as step 1 is confirmed, and every step after that reads/writes the
 *  real cohort through the same endpoints the cohort detail page's tabs
 *  already use.
 */
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Check, ChevronLeft, ChevronRight, Lock, Plus, Trash2, X } from "lucide-react"
import type { Cohort, CohortVisibility, Program, Session } from "@/types/sessions"
import type { City, Location, Warehouse } from "@/types/inventory"
import { getProgramsApi } from "@/api/sessions/programs"
import { getLocationsApi, getWarehousesApi, createLocationApi, getCitiesApi } from "@/api/inventory"
import {
  createCohortApi, updateCohortApi, generateSessionsApi, getSessionsApi, addSessionApi, deleteSessionApi,
} from "@/api/sessions/cohorts"
import { getCohortOpeningsApi, getMaterialsApi } from "@/api/sessions/openings"
import { Spinner } from "@/pages/admin/components/common"
import { CohortRolesPanel } from "@/pages/admin/components/CohortRolesPanel"
import { SessionOpeningsPanel } from "@/pages/admin/components/SessionOpeningsPanel"
import { SessionChecklistPanel } from "@/pages/admin/components/SessionChecklistPanel"
import { MaterialsPanel } from "@/pages/admin/components/MaterialsPanel"
import { useToast } from "@/components/ui/toast"
import { useAuth } from "@/context/AuthContext"
import { cn, getErrorMessage } from "@/lib/utils"

const STEP_LABELS = ["Cohort basics", "Sessions", "Roles & checklist", "Materials", "Review & finish"]
const LAST_STEP = STEP_LABELS.length - 1
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] // index = backend's 0..6 (Monday first)
const OUTFIT = "'Outfit', ui-sans-serif, system-ui, sans-serif"
const CARD_SHADOW = "0 3px 0 hsl(var(--border)), 0 12px 24px -14px rgba(40,16,80,.28)"

function pad(n: number) { return String(n).padStart(2, "0") }
function toISODate(d: Date) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` }
function fmtDate(iso: string) {
  const d = new Date(iso + "T00:00:00")
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" })
}

/* ═══════════════════════════ Shared chrome bits ═════════════════════════ */

/** Eyebrow + big Outfit headline + lede, at the top of every step — same
 *  three-line pattern the design uses throughout. */
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

/** Big field label — the design's 13px/uppercase/.09em, distinct from the
 *  compact admin `Field` used inside the embedded shared panels. */
function BigField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col" style={{ gap: 12 }}>
      <span style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.09em" }} className="text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}

const bigInput: React.CSSProperties = {
  height: 56, padding: "0 20px", borderRadius: 16, fontSize: 17, width: "100%", boxSizing: "border-box",
}
const heroInput: React.CSSProperties = {
  height: 64, padding: "0 22px", borderRadius: 16, fontFamily: OUTFIT, fontSize: 24, fontWeight: 500, width: "100%", boxSizing: "border-box",
}

export default function CohortWizard() {
  const navigate = useNavigate()

  const [step, setStep] = useState(0)
  const [skipped, setSkipped] = useState<Record<number, boolean>>({})
  const [cohort, setCohort] = useState<Cohort | null>(null)

  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => { document.body.style.overflow = prev }
  }, [])

  const { data: programs = [] } = useQuery({ queryKey: ["sessions-programs"], queryFn: getProgramsApi })
  const program = programs.find((p) => p.id === cohort?.program_id)

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
            Setting up: {cohort?.name || "New Cohort"}
          </h1>
          <p style={{ fontSize: 15, margin: "6px 0 0" }} className="text-muted-foreground">
            Step {step + 1} of {STEP_LABELS.length} — {STEP_LABELS[step]}
          </p>
        </div>
        <div className="flex items-center shrink-0" style={{ gap: 32 }}>
          <StepDots steps={STEP_LABELS} current={step} skipped={skipped} onGo={(i) => { if (i <= step || cohort) goStep(i) }} />
          <button
            onClick={() => navigate({ to: cohort ? "/operations/cohorts/$cohortId" : "/operations/cohorts", params: cohort ? { cohortId: cohort.id } : undefined })}
            style={{ width: 44, height: 44 }}
            className="rounded-full flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            aria-label="Close"
          ><X size={22} /></button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto" style={{ padding: "56px 56px 72px" }}>
        {step === 0 && (
          <BasicsStep
            programs={programs} program={program} cohort={cohort}
            onSaved={(c) => { setCohort(c); advance() }}
          />
        )}
        {step === 1 && cohort && <SessionsStep cohort={cohort} />}
        {step === 2 && cohort && <RolesChecklistStep cohort={cohort} />}
        {step === 3 && cohort && (
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
        {step === 4 && cohort && <ReviewStep cohort={cohort} program={program} />}
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
              <WizardContinueButton step={step} cohort={cohort} onContinue={advance} />
            ) : (
              <button
                onClick={() => navigate({ to: "/operations/cohorts/$cohortId", params: { cohortId: cohort!.id } })}
                style={{ height: 52, padding: "0 40px", borderRadius: 14, fontFamily: OUTFIT, fontSize: 18, fontWeight: 600 }}
                className="bg-primary text-primary-foreground hover:opacity-90 transition-opacity"
              >Done</button>
            )}
          </div>
          {step === 1 && <SkipNote>You can add sessions later from the cohort page.</SkipNote>}
          {step === 2 && <SkipNote>Every session uses the cohort&rsquo;s roles and checklist until you override one.</SkipNote>}
          {step === 3 && <SkipNote>Sessions will use the program&rsquo;s materials.</SkipNote>}
        </div>
      </footer>
    </div>
  )
}

function SkipNote({ children }: { children: ReactNode }) {
  return <p style={{ fontSize: 15, margin: 0 }} className="text-muted-foreground">{children}</p>
}

/** Step 1's own Continue is a plain button (advance() is enough — the form
 *  fields underneath already saved via BasicsStep's own submit). Steps 2-4
 *  have nothing that must complete before moving on. */
function WizardContinueButton({ step, cohort, onContinue }: { step: number; cohort: Cohort | null; onContinue: () => void }) {
  if (step === 0) return null // BasicsStep renders its own Continue (it must create/save first)
  return (
    <button
      onClick={onContinue}
      disabled={!cohort}
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

/* ════════════════════════ Step 1 — Cohort basics ═══════════════════════ */

function BasicsStep({ programs, program, cohort, onSaved }: {
  programs: Program[]; program?: Program; cohort: Cohort | null; onSaved: (c: Cohort) => void
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
        })
      : createCohortApi({
          program_id: programId, name: name.trim(), starts_on: startsOn || undefined, ends_on: endsOn || undefined,
          location_id: locationId || undefined, warehouse_id: warehouseId || undefined,
          capacity: capacity.trim() ? Number(capacity) : undefined,
          duration_hours: durationHours.trim() ? Number(durationHours) : undefined,
          visibility,
        }),
    onSuccess: (c) => { toast.success(cohort ? "Cohort updated" : "Cohort created"); qc.invalidateQueries({ queryKey: ["sessions-cohorts"] }); onSaved(c) },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to save cohort")),
  })

  const selectStyle: React.CSSProperties = { ...bigInput, cursor: "pointer" }

  return (
    <div className="flex flex-col" style={{ gap: 44 }}>
      <StepIntro
        eyebrow="Cohort basics" title="What is this run of the program?"
        lede="Everything here becomes the default for every session in the cohort. You can change any of it later."
        right={
          cohort ? (
            <div className="flex flex-col shrink-0" style={{ gap: 6, paddingLeft: 28, borderLeft: "2px solid hsl(var(--primary))" }}>
              <span style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.09em" }} className="text-muted-foreground">Program</span>
              <span style={{ fontFamily: OUTFIT, fontSize: 26, fontWeight: 600, letterSpacing: "-0.02em" }} className="flex items-center gap-2.5 text-foreground">
                {program?.name ?? "…"} <Lock size={18} className="text-muted-foreground" />
              </span>
            </div>
          ) : undefined
        }
      />

      {!cohort && (
        <BigField label="Program">
          <select value={programId} onChange={(e) => setProgramId(e.target.value)} style={selectStyle} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors">
            <option value="">— Select a program —</option>
            {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </BigField>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "32px 40px" }}>
        <div style={{ gridColumn: "span 2" }}>
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

        <div style={{ gridColumn: "span 2" }}>
          <BigField label="Location (optional)">
            {addingLocation ? (
              <div className="flex flex-col rounded-2xl bg-muted/20 border border-border" style={{ gap: 10, padding: 16 }}>
                <input value={newLocName} onChange={(e) => setNewLocName(e.target.value)} placeholder="Location name" autoFocus
                  style={bigInput} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors" />
                <select value={newLocCityId} onChange={(e) => setNewLocCityId(e.target.value)}
                  style={selectStyle} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors">
                  <option value="" disabled>City (required)</option>
                  {cities.map((c: City) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                {newLocError && <p style={{ fontSize: 15 }} className="text-red-500">{newLocError}</p>}
                <div className="flex" style={{ gap: 10 }}>
                  <button type="button" onClick={() => { setNewLocError(""); createLocationMutation.mutate() }}
                    disabled={!newLocName.trim() || !newLocCityId || createLocationMutation.isPending}
                    style={{ height: 48, padding: "0 22px", borderRadius: 14, fontSize: 16, fontWeight: 600 }}
                    className="bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50">
                    {createLocationMutation.isPending ? "…" : "Add"}
                  </button>
                  <button type="button" onClick={() => { setAddingLocation(false); setNewLocError(""); setNewLocName(""); setNewLocCityId("") }}
                    style={{ height: 48, padding: "0 18px", borderRadius: 14, fontSize: 16, fontWeight: 500 }}
                    className="flex items-center gap-1.5 border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
                    <X size={16} /> Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex" style={{ gap: 12 }}>
                <select value={locationId} onChange={(e) => { setLocationId(e.target.value); setWarehouseId("") }}
                  style={selectStyle} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors">
                  <option value="">— None —</option>
                  {locations.map((l: Location) => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
                {canCreateLocation && (
                  <button type="button" onClick={() => setAddingLocation(true)}
                    style={{ height: 56, padding: "0 24px", borderRadius: 16, fontSize: 16, fontWeight: 500 }}
                    className="flex items-center gap-2 shrink-0 border border-border text-foreground hover:bg-muted transition-colors">
                    <Plus size={16} /> New location
                  </button>
                )}
              </div>
            )}
            <p style={{ fontSize: 15, margin: "8px 0 0" }} className="text-muted-foreground">The venue sessions inherit by default.</p>
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
          <div className="flex bg-muted" style={{ height: 56, padding: 5, gap: 5, borderRadius: 16 }}>
            <button type="button" onClick={() => setVisibility("public")}
              style={{ flex: 1, borderRadius: 12, fontSize: 16, fontWeight: 600 }}
              className={cn("transition-colors", visibility === "public" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground")}>Public</button>
            <button type="button" onClick={() => setVisibility("private")}
              style={{ flex: 1, borderRadius: 12, fontSize: 16, fontWeight: 600 }}
              className={cn("transition-colors", visibility === "private" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground")}>Private</button>
          </div>
        </BigField>
        <p style={{ fontSize: 15, maxWidth: "60ch", alignSelf: "end" }} className="text-muted-foreground m-0">
          Every session in this cohort uses this duration unless it has its own override. Shown to instructors before they apply, and feeds the payment letter&rsquo;s hours.
        </p>
      </div>

      {error && <p style={{ fontSize: 15 }} className="text-red-500">{error}</p>}

      <div className="flex justify-end" style={{ paddingTop: 8 }}>
        <button
          onClick={() => { setError(""); save.mutate() }}
          disabled={!name.trim() || (!cohort && !programId) || save.isPending}
          style={{ height: 52, padding: "0 40px", borderRadius: 14, fontFamily: OUTFIT, fontSize: 18, fontWeight: 600 }}
          className="bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
        >{save.isPending ? "…" : "Continue"}</button>
      </div>
    </div>
  )
}

/* ════════════════════════ Step 2 — Sessions ═══════════════════════════ */

function SessionsStep({ cohort }: { cohort: Cohort }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [mode, setMode] = useState<"pattern" | "manual">("pattern")
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
    height: 56, padding: "0 28px", borderRadius: 12, fontSize: 16, fontWeight: 600,
    background: on ? "hsl(var(--card))" : "transparent", color: on ? "hsl(var(--foreground))" : "hsl(var(--muted-foreground))",
    boxShadow: on ? "0 1px 3px rgba(0,0,0,.10)" : "none",
  })

  return (
    <div className="flex flex-col" style={{ gap: 40 }}>
      <StepIntro
        eyebrow="Sessions" title="When does this cohort meet?"
        lede="Generate the whole run from a weekly pattern, or pick the dates by hand."
        right={
          <div className="flex shrink-0 bg-muted" style={{ padding: 5, gap: 5, borderRadius: 16 }}>
            <button onClick={() => setMode("manual")} style={segStyle(mode === "manual")}>Pick dates manually</button>
            <button onClick={() => setMode("pattern")} style={segStyle(mode === "pattern")}>Generate by pattern</button>
          </div>
        }
      />

      {mode === "pattern" ? (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(360px,0.6fr)", gap: 56, alignItems: "start" }}>
          <div className="flex flex-col" style={{ gap: 36 }}>
            <BigField label="Which days">
              <div className="flex flex-wrap" style={{ gap: 12 }}>
                {WEEKDAYS.map((label, i) => (
                  <button key={label} type="button"
                    onClick={() => setDays((d) => d.includes(i) ? d.filter((x) => x !== i) : [...d, i])}
                    style={{ width: 82, height: 56, borderRadius: 16, fontSize: 16, fontWeight: 600 }}
                    className={cn("transition-colors",
                      days.includes(i) ? "bg-primary/10 border-[1.5px] border-primary text-primary" : "border border-border text-muted-foreground")}
                  >{label}</button>
                ))}
              </div>
            </BigField>
            <div className="flex items-end flex-wrap" style={{ gap: 24 }}>
              <BigField label="How many weeks">
                <input type="number" min={1} value={weeks} onChange={(e) => setWeeks(Math.max(1, Number(e.target.value) || 1))}
                  style={{ ...heroInput, width: 200 }} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors" />
              </BigField>
              <p style={{ fontSize: 15, maxWidth: "34ch", margin: "0 0 8px" }} className="text-muted-foreground">
                {cohort.starts_on ? `Counting from the cohort's start date, ${fmtDate(cohort.starts_on)}.` : "Set a start date on step 1 first."}
              </p>
            </div>
            <button onClick={() => { setError(""); generate.mutate() }} disabled={!cohort.starts_on || days.length === 0 || generate.isPending}
              style={{ alignSelf: "flex-start", height: 52, padding: "0 24px", borderRadius: 14, fontSize: 16, fontWeight: 600 }}
              className="border border-border text-foreground hover:bg-muted transition-colors disabled:opacity-50">
              {generate.isPending ? "Generating…" : "Generate sessions"}
            </button>
          </div>
          <SessionsList sessions={sessions} isLoading={isLoading} onRemove={(id) => remove.mutate(id)} countLabel="Preview" count={sessions.length} />
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(360px,0.6fr)", gap: 56, alignItems: "start" }}>
          <div className="flex flex-col" style={{ gap: 20 }}>
            <div className="flex items-center justify-between">
              <span style={{ fontFamily: OUTFIT, fontSize: 26, fontWeight: 600, letterSpacing: "-0.02em" }} className="text-foreground">
                {calMonth.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
              </span>
              <div className="flex" style={{ gap: 10 }}>
                <button onClick={() => setCalMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1))}
                  style={{ width: 44, height: 44, borderRadius: 12 }} className="border border-border flex items-center justify-center text-muted-foreground hover:bg-muted transition-colors"><ChevronLeft size={20} /></button>
                <button onClick={() => setCalMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1))}
                  style={{ width: 44, height: 44, borderRadius: 12 }} className="border border-border flex items-center justify-center text-muted-foreground hover:bg-muted transition-colors"><ChevronRight size={20} /></button>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0,1fr))", gap: 8 }}>
              {WEEKDAYS.map((d) => <div key={d} style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", paddingBottom: 8 }} className="text-center text-muted-foreground">{d[0]}</div>)}
              {calCells.map((c, i) => {
                if (!c.label) return <div key={i} />
                const existing = !c.iso
                const selected = c.iso ? pending.has(c.iso) : false
                return (
                  <button
                    key={i}
                    disabled={existing}
                    onClick={() => c.iso && togglePending(c.iso)}
                    style={{ height: 60, borderRadius: 14, fontSize: 18, fontVariantNumeric: "tabular-nums", fontWeight: selected ? 700 : 400 }}
                    className={cn(
                      "transition-colors",
                      existing ? "text-muted-foreground/30 cursor-not-allowed border border-transparent" :
                        selected ? "bg-primary text-primary-foreground border border-primary" : "border border-transparent text-foreground hover:bg-muted",
                    )}
                  >{c.label}</button>
                )
              })}
            </div>
            <p style={{ fontSize: 15 }} className="text-muted-foreground">Click a date on the calendar to add it. Faded dates already have a session.</p>
          </div>
          <div className="flex flex-col" style={{ gap: 20 }}>
            <div className="flex items-baseline justify-between" style={{ gap: 12 }}>
              <span style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.09em" }} className="text-muted-foreground">Picked</span>
              <span style={{ fontFamily: OUTFIT, fontSize: 22, fontWeight: 600 }} className="text-primary">{pending.size} selected</span>
            </div>
            <button onClick={() => { setError(""); addManual.mutate() }} disabled={pending.size === 0 || addManual.isPending}
              style={{ alignSelf: "flex-start", height: 52, padding: "0 24px", borderRadius: 14, fontSize: 16, fontWeight: 600 }}
              className="bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50">
              {addManual.isPending ? "Adding…" : `Add ${pending.size || ""} session${pending.size === 1 ? "" : "s"}`}
            </button>
            <SessionsList sessions={sessions} isLoading={isLoading} onRemove={(id) => remove.mutate(id)} countLabel="This cohort's sessions" count={sessions.length} />
          </div>
        </div>
      )}
      {error && <p style={{ fontSize: 15 }} className="text-red-500">{error}</p>}
    </div>
  )
}

function SessionsList({ sessions, isLoading, onRemove, countLabel, count }: {
  sessions: Session[]; isLoading: boolean; onRemove: (id: string) => void; countLabel: string; count: number
}) {
  return (
    <div className="flex flex-col" style={{ gap: 20 }}>
      <div className="flex items-baseline justify-between" style={{ gap: 12 }}>
        <span style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.09em" }} className="text-muted-foreground">{countLabel}</span>
        <span style={{ fontFamily: OUTFIT, fontSize: 22, fontWeight: 600 }} className="text-primary">{count} sessions</span>
      </div>
      <div className="overflow-y-auto flex flex-col" style={{ gap: 14, maxHeight: "56vh", padding: "4px 6px 6px 2px" }}>
        {isLoading ? <Spinner /> : sessions.length === 0 ? (
          <p style={{ fontSize: 17 }} className="text-muted-foreground italic">No sessions yet.</p>
        ) : sessions
          .slice()
          .sort((a, b) => a.meeting_date.localeCompare(b.meeting_date))
          .map((s, i) => (
            <div key={s.id}
              style={{ padding: "22px 26px", borderRadius: 18, boxShadow: CARD_SHADOW }}
              className="flex items-center justify-between border border-border bg-card">
              <span style={{ fontFamily: OUTFIT, fontSize: 22, fontWeight: 600, letterSpacing: "-0.02em" }} className="text-foreground">
                {fmtDate(s.meeting_date)}
              </span>
              <div className="flex items-center" style={{ gap: 16 }}>
                <span style={{ fontSize: 14, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em", fontVariantNumeric: "tabular-nums" }} className="text-muted-foreground">
                  Session {i + 1}
                </span>
                <button onClick={() => onRemove(s.id)} style={{ width: 32, height: 32 }} className="flex items-center justify-center rounded-lg text-muted-foreground hover:text-red-600 hover:bg-muted transition-colors" aria-label="Remove session">
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
      </div>
    </div>
  )
}

/* ═══════════════════ Step 3 — Roles & checklist ════════════════════════ */

function RolesChecklistStep({ cohort }: { cohort: Cohort }) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["wizard-sessions", cohort.id], queryFn: () => getSessionsApi(cohort.id),
  })
  const selected = sessions.find((s) => s.id === selectedId) ?? null

  return (
    <div className="flex flex-col" style={{ gap: 40 }}>
      <StepIntro
        eyebrow="Roles & checklist" title="Who runs a day, and what they do" ledeWidth={70}
        lede="These are the cohort's defaults. Pick a session on the right only if that one day needs to differ."
      />
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,55fr) minmax(0,45fr)", gap: 56, alignItems: "start" }}>
        <div className="flex flex-col" style={{ gap: 24 }}>
          {selected ? (
            <div
              style={{ padding: "20px 26px", borderRadius: 18, background: "hsl(var(--primary) / 0.10)", border: "1px solid hsl(var(--primary) / 0.22)" }}
              className="flex items-center justify-between"
            >
              <span style={{ fontFamily: OUTFIT, fontSize: 20, fontWeight: 600 }} className="text-foreground">Overriding: {fmtDate(selected.meeting_date)}</span>
              <button onClick={() => setSelectedId(null)} style={{ fontSize: 16, fontWeight: 600 }} className="text-primary hover:opacity-80 shrink-0 transition-opacity">
                Reset to cohort default
              </button>
            </div>
          ) : (
            <div style={{ height: 40, padding: "0 20px", borderRadius: 999, fontSize: 15, fontWeight: 600 }} className="inline-flex self-start items-center bg-muted border border-border text-muted-foreground">
              Inherited from program
            </div>
          )}

          {selected ? (
            <div className="flex flex-col" style={{ gap: 32 }}>
              <SessionOpeningsPanel sessionId={selected.id} large />
              <SessionChecklistPanel sessionId={selected.id} cohortId={cohort.id} programId={cohort.program_id} large />
            </div>
          ) : (
            <CohortRolesPanel cohort={cohort} large />
          )}
        </div>

        <div className="flex flex-col" style={{ gap: 20, position: "sticky", top: 0 }}>
          <div className="flex flex-col" style={{ gap: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.09em" }} className="text-muted-foreground">This cohort&rsquo;s sessions</span>
            <span style={{ fontSize: 15 }} className="text-muted-foreground">Pick one to override just that day.</span>
          </div>
          <div className="flex flex-col overflow-y-auto" style={{ gap: 16, maxHeight: "34rem", padding: "2px 6px 6px 2px" }}>
            {isLoading ? <Spinner /> : sessions.length === 0 ? (
              <p style={{ fontSize: 17 }} className="text-muted-foreground italic">No sessions yet — add some on the Sessions step first.</p>
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
                      padding: "18px 22px", borderRadius: 18, textAlign: "left",
                      background: isSel ? "hsl(var(--primary) / 0.10)" : "hsl(var(--card))",
                      border: isSel ? "1.5px solid hsl(var(--primary))" : "1px solid hsl(var(--border))",
                      boxShadow: isSel ? "0 3px 0 hsl(var(--primary) / 0.22), 0 12px 24px -14px rgba(40,16,80,.28)" : CARD_SHADOW,
                    }}
                    className="flex items-center justify-between transition-colors"
                  >
                    <span className="flex flex-col" style={{ gap: 3 }}>
                      <span style={{ fontFamily: OUTFIT, fontSize: 19, fontWeight: 600 }} className="text-foreground">Session {i + 1}</span>
                      <span style={{ fontSize: 15 }} className="text-muted-foreground">{fmtDate(s.meeting_date)}</span>
                    </span>
                    {isSel && <span style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em" }} className="text-primary">Selected</span>}
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

function ReviewStep({ cohort, program }: { cohort: Cohort; program?: Program }) {
  const { data: sessions = [] } = useQuery({ queryKey: ["wizard-sessions", cohort.id], queryFn: () => getSessionsApi(cohort.id) })
  const { data: openings = [] } = useQuery({ queryKey: ["cohort-openings-defaults", cohort.id], queryFn: () => getCohortOpeningsApi(cohort.id) })
  const { data: materials = [] } = useQuery({ queryKey: ["materials", JSON.stringify({ cohort_id: cohort.id })], queryFn: () => getMaterialsApi({ cohort_id: cohort.id }) })

  const sorted = sessions.slice().sort((a, b) => a.meeting_date.localeCompare(b.meeting_date))
  const rows: { label: string; value: string }[] = [
    { label: "Name", value: cohort.name },
    { label: "Program", value: program?.name ?? "—" },
    { label: "Dates", value: cohort.starts_on ? `${fmtDate(cohort.starts_on)}${cohort.ends_on ? ` – ${fmtDate(cohort.ends_on)}` : ""}` : "Not set" },
    { label: "Location", value: cohort.location_name ?? "Not set" },
    { label: "Capacity · duration", value: `${cohort.capacity ?? "—"} students · ${cohort.duration_hours ?? "—"} hrs / session` },
    { label: "Visibility", value: cohort.visibility === "public" ? "Public" : "Private" },
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
      label: "Materials",
      value: materials.length === 0 ? "Inherited from program" : `${materials.length} item${materials.length === 1 ? "" : "s"} set for this cohort`,
    },
  ]

  return (
    <div className="flex flex-col" style={{ gap: 40 }}>
      <div className="flex items-end justify-between flex-wrap" style={{ gap: 40 }}>
        <div className="flex flex-col" style={{ gap: 14 }}>
          <p style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em" }} className="text-primary m-0">Review &amp; create</p>
          <h2 style={{ fontFamily: OUTFIT, fontSize: 56, fontWeight: 600, letterSpacing: "-0.035em", lineHeight: 1.05 }} className="text-foreground m-0">{cohort.name}</h2>
          <p style={{ fontSize: 18 }} className="text-muted-foreground m-0">{program?.name ?? ""}</p>
        </div>
        <p style={{ fontSize: 15, maxWidth: "34ch", margin: "0 0 6px" }} className="text-muted-foreground">You can change anything later from the cohort page.</p>
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
