/** Full-page guided cohort setup (replaces the flat "New cohort" modal for
 *  creation). Same full-page-overlay shell as the LMS's Madar phase drawer
 *  (`pages/learn/missions/MadarPhaseDrawer.tsx`) — one focused step at a
 *  time instead of tabs ops had to discover on their own.
 *
 *  Deliberately NOT a draft-then-submit wizard: the cohort is created as
 *  soon as step 1 is confirmed, and every step after that reads/writes the
 *  real cohort through the same endpoints the cohort detail page's tabs
 *  already use (sessions, `CohortRolesPanel`, `SessionOpeningsPanel`,
 *  `MaterialsPanel`, and the new `SessionChecklistPanel`). That is what
 *  makes "Skip for now" honest — the cohort already exists and already
 *  behaves correctly with nothing set at that level, exactly like it does
 *  today from the plain cohort page.
 */
import { useEffect, useMemo, useState } from "react"
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
import { Field, Spinner } from "@/pages/admin/components/common"
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

function pad(n: number) { return String(n).padStart(2, "0") }
function toISODate(d: Date) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` }
function fmtDate(iso: string) {
  const d = new Date(iso + "T00:00:00")
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" })
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
    <div className="fixed inset-0 z-50 bg-background flex flex-col">
      <header className="shrink-0 h-20 flex items-center justify-between gap-8 px-6 sm:px-10 border-b border-border">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Setting up</p>
          <h1 className="text-lg font-bold text-foreground truncate">{cohort?.name || "New Cohort"}</h1>
          <p className="text-xs text-muted-foreground mt-0.5">Step {step + 1} of {STEP_LABELS.length} — {STEP_LABELS[step]}</p>
        </div>
        <div className="flex items-center gap-5 shrink-0">
          <StepDots steps={STEP_LABELS} current={step} skipped={skipped} onGo={(i) => { if (i <= step || cohort) goStep(i) }} />
          <button
            onClick={() => navigate({ to: cohort ? "/operations/cohorts/$cohortId" : "/operations/cohorts", params: cohort ? { cohortId: cohort.id } : undefined })}
            className="w-9 h-9 rounded-full flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            aria-label="Close"
          ><X size={18} /></button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-6 sm:px-10 py-8">
        <div className="mx-auto w-full" style={{ maxWidth: step === 2 ? "1180px" : "720px" }}>
          {step === 0 && (
            <BasicsStep
              programs={programs} program={program} cohort={cohort}
              onSaved={(c) => { setCohort(c); advance() }}
            />
          )}
          {step === 1 && cohort && <SessionsStep cohort={cohort} />}
          {step === 2 && cohort && <RolesChecklistStep cohort={cohort} />}
          {step === 3 && cohort && (
            <MaterialsPanel
              owner={{ cohort_id: cohort.id }} level="cohort"
              inheritedNote="Sessions inherit these unless a session overrides them."
            />
          )}
          {step === 4 && cohort && <ReviewStep cohort={cohort} program={program} />}
        </div>
      </div>

      <footer className="shrink-0 h-20 flex items-center justify-between gap-4 px-6 sm:px-10 border-t border-border">
        <div>
          {canBack && (
            <button
              onClick={() => goStep(step - 1)}
              className="h-10 px-3 flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted rounded-xl transition-colors"
            ><ChevronLeft size={15} /> Back</button>
          )}
        </div>
        <div className="flex flex-col items-end gap-1">
          <div className="flex items-center gap-2">
            {canSkip && (
              <button onClick={skipThis} className="h-10 px-3 text-sm text-muted-foreground hover:text-foreground underline decoration-border underline-offset-4 transition-colors">
                Skip for now
              </button>
            )}
            {step < LAST_STEP ? (
              <BasicsContinueButton step={step} cohort={cohort} onContinue={advance} />
            ) : (
              <button
                onClick={() => navigate({ to: "/operations/cohorts/$cohortId", params: { cohortId: cohort!.id } })}
                className="h-10 px-6 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 transition-colors"
              >Done</button>
            )}
          </div>
          {step === 1 && <p className="text-xs text-muted-foreground">You can add sessions later from the cohort page.</p>}
          {step === 2 && <p className="text-xs text-muted-foreground">Every session uses the cohort&rsquo;s roles and checklist until you override one.</p>}
          {step === 3 && <p className="text-xs text-muted-foreground">Sessions will use the program&rsquo;s materials.</p>}
        </div>
      </footer>
    </div>
  )
}

/** Step 1's own Continue is a plain button (advance() is enough — the form
 *  fields underneath already saved via BasicsStep's own submit). Steps 2-4
 *  have nothing that must complete before moving on. */
function BasicsContinueButton({ step, cohort, onContinue }: { step: number; cohort: Cohort | null; onContinue: () => void }) {
  if (step === 0) return null // BasicsStep renders its own Continue (it must create/save first)
  return (
    <button
      onClick={onContinue}
      disabled={!cohort}
      className="h-10 px-6 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 transition-colors disabled:opacity-50"
    >Continue</button>
  )
}

function StepDots({ steps, current, skipped, onGo }: {
  steps: string[]; current: number; skipped: Record<number, boolean>; onGo: (i: number) => void
}) {
  return (
    <div className="flex items-center gap-2">
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
            className={cn(
              "rounded-full flex items-center justify-center shrink-0 transition-all",
              isCurrent && "w-3.5 h-3.5 bg-primary shadow-[0_0_0_4px_hsl(var(--primary)/0.18)]",
              isDone && "w-3 h-3 bg-muted-foreground/40",
              isSkipped && "w-3 h-3 border-[1.5px] border-muted-foreground/50",
              !isCurrent && !isDone && !isSkipped && "w-3 h-3 border border-border",
            )}
          >
            {isDone && <Check size={7} className="text-card" strokeWidth={4} />}
            {isSkipped && <span className="block w-2 h-[1.5px] bg-muted-foreground/70 rotate-45 rounded-full" />}
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

  return (
    <div className="flex flex-col gap-6">
      {cohort ? (
        <div className="inline-flex items-center gap-2 w-fit px-3 py-1.5 rounded-full bg-muted text-muted-foreground text-xs font-semibold">
          <Lock size={12} /> Program: {program?.name ?? "…"}
        </div>
      ) : (
        <Field label="Program">
          <select
            value={programId} onChange={(e) => setProgramId(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
          >
            <option value="">— Select a program —</option>
            {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
      )}

      <Field label="Cohort name">
        <input
          value={name} onChange={(e) => setName(e.target.value)} placeholder="Q3 Cohort A" autoFocus
          className="w-full h-11 px-3 border border-border bg-card text-foreground rounded-xl text-base focus:outline-none focus:border-primary transition-colors"
        />
      </Field>

      <div className="grid grid-cols-2 gap-4">
        <Field label="Starts on">
          <input value={startsOn} onChange={(e) => setStartsOn(e.target.value)} type="date"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        </Field>
        <Field label="Ends on">
          <input value={endsOn} onChange={(e) => setEndsOn(e.target.value)} type="date"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        </Field>
      </div>

      <Field label="Location (optional)">
        {addingLocation ? (
          <div className="flex flex-col gap-2 p-3 border border-border rounded-xl bg-muted/20">
            <input value={newLocName} onChange={(e) => setNewLocName(e.target.value)} placeholder="Location name" autoFocus
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
            <select value={newLocCityId} onChange={(e) => setNewLocCityId(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer">
              <option value="" disabled>City (required)</option>
              {cities.map((c: City) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            {newLocError && <p className="text-xs text-red-500">{newLocError}</p>}
            <div className="flex gap-2">
              <button type="button" onClick={() => { setNewLocError(""); createLocationMutation.mutate() }}
                disabled={!newLocName.trim() || !newLocCityId || createLocationMutation.isPending}
                className="h-9 px-4 bg-primary text-primary-foreground rounded-xl text-xs font-medium hover:opacity-90 transition-colors disabled:opacity-50">
                {createLocationMutation.isPending ? "…" : "Add"}
              </button>
              <button type="button" onClick={() => { setAddingLocation(false); setNewLocError(""); setNewLocName(""); setNewLocCityId("") }}
                className="h-9 px-3 flex items-center gap-1 border border-border rounded-xl text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
                <X size={13} /> Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <select value={locationId} onChange={(e) => { setLocationId(e.target.value); setWarehouseId("") }}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer">
              <option value="">— None —</option>
              {locations.map((l: Location) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
            {canCreateLocation && (
              <button type="button" onClick={() => setAddingLocation(true)}
                className="flex items-center gap-1 h-10 px-3 shrink-0 border border-border rounded-xl text-xs font-medium text-foreground hover:bg-muted transition-colors">
                <Plus size={12} /> New
              </button>
            )}
          </div>
        )}
        <p className="text-xs text-muted-foreground mt-1">The venue sessions inherit by default.</p>
      </Field>

      {locationId && (
        <Field label="Warehouse (optional)">
          <select value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer">
            <option value="">— Select a warehouse —</option>
            {warehouses.map((w: Warehouse) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </Field>
      )}

      <div className="grid grid-cols-3 gap-4">
        <Field label="Capacity (optional)">
          <input value={capacity} onChange={(e) => setCapacity(e.target.value)} type="number" placeholder="20"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        </Field>
        <Field label="Session duration (hrs)">
          <input value={durationHours} onChange={(e) => setDurationHours(e.target.value)} type="number" step="0.5" min="0" placeholder="e.g. 2"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        </Field>
        <Field label="Visibility">
          <div className="flex h-10 p-1 bg-muted rounded-xl gap-1">
            <button type="button" onClick={() => setVisibility("public")}
              className={cn("flex-1 rounded-lg text-xs font-semibold transition-colors", visibility === "public" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground")}>Public</button>
            <button type="button" onClick={() => setVisibility("private")}
              className={cn("flex-1 rounded-lg text-xs font-semibold transition-colors", visibility === "private" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground")}>Private</button>
          </div>
        </Field>
      </div>
      <p className="text-xs text-muted-foreground -mt-2">
        Every session in this cohort uses this duration unless it has its own override.
      </p>

      {error && <p className="text-xs text-red-500">{error}</p>}

      <div className="flex justify-end pt-2">
        <button
          onClick={() => { setError(""); save.mutate() }}
          disabled={!name.trim() || (!cohort && !programId) || save.isPending}
          className="h-10 px-6 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 transition-colors disabled:opacity-50"
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

  return (
    <div className="flex flex-col gap-6">
      <div className="flex h-10 p-1 bg-muted rounded-xl gap-1 w-fit">
        <button onClick={() => setMode("pattern")} className={cn("h-full px-4 rounded-lg text-xs font-semibold transition-colors", mode === "pattern" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground")}>Generate by pattern</button>
        <button onClick={() => setMode("manual")} className={cn("h-full px-4 rounded-lg text-xs font-semibold transition-colors", mode === "manual" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground")}>Pick dates manually</button>
      </div>

      {mode === "pattern" ? (
        <div className="grid sm:grid-cols-2 gap-6">
          <div className="flex flex-col gap-5">
            <Field label="Repeat on">
              <div className="flex gap-2 flex-wrap">
                {WEEKDAYS.map((label, i) => (
                  <button key={label} type="button"
                    onClick={() => setDays((d) => d.includes(i) ? d.filter((x) => x !== i) : [...d, i])}
                    className={cn("w-11 h-11 rounded-xl text-xs font-bold transition-colors",
                      days.includes(i) ? "bg-primary text-primary-foreground" : "border border-border text-muted-foreground")}
                  >{label[0]}</button>
                ))}
              </div>
            </Field>
            <Field label="For how many weeks">
              <input type="number" min={1} value={weeks} onChange={(e) => setWeeks(Math.max(1, Number(e.target.value) || 1))}
                className="w-32 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
              <p className="text-xs text-muted-foreground mt-1">
                {cohort.starts_on ? `Starting from the cohort's start date, ${fmtDate(cohort.starts_on)}.` : "Set a start date on step 1 first."}
              </p>
            </Field>
            <button onClick={() => { setError(""); generate.mutate() }} disabled={!cohort.starts_on || days.length === 0 || generate.isPending}
              className="w-fit h-10 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50">
              {generate.isPending ? "Generating…" : "Generate sessions"}
            </button>
          </div>
          <SessionsList sessions={sessions} isLoading={isLoading} onRemove={(id) => remove.mutate(id)} />
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 gap-6">
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-base font-semibold text-foreground">
                {calMonth.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
              </span>
              <div className="flex gap-1.5">
                <button onClick={() => setCalMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1))}
                  className="w-8 h-8 rounded-lg border border-border flex items-center justify-center text-muted-foreground hover:bg-muted"><ChevronLeft size={14} /></button>
                <button onClick={() => setCalMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1))}
                  className="w-8 h-8 rounded-lg border border-border flex items-center justify-center text-muted-foreground hover:bg-muted"><ChevronRight size={14} /></button>
              </div>
            </div>
            <div className="grid grid-cols-7 gap-1.5">
              {WEEKDAYS.map((d) => <div key={d} className="text-center text-[10px] font-bold uppercase text-muted-foreground pb-1">{d}</div>)}
              {calCells.map((c, i) => {
                if (!c.label) return <div key={i} />
                const existing = !c.iso
                const selected = c.iso ? pending.has(c.iso) : false
                return (
                  <button
                    key={i}
                    disabled={existing}
                    onClick={() => c.iso && togglePending(c.iso)}
                    className={cn(
                      "aspect-square rounded-lg text-sm font-medium transition-colors",
                      existing ? "text-muted-foreground/30 cursor-not-allowed" :
                        selected ? "bg-primary text-primary-foreground font-bold" : "border border-border text-foreground hover:bg-muted",
                    )}
                  >{c.label}</button>
                )
              })}
            </div>
            <p className="text-xs text-muted-foreground">Faded dates already have a session. Click a date to add or remove it.</p>
          </div>
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-foreground">{pending.size} selected</span>
              <button onClick={() => { setError(""); addManual.mutate() }} disabled={pending.size === 0 || addManual.isPending}
                className="h-9 px-4 bg-primary text-primary-foreground text-xs font-semibold rounded-xl hover:opacity-90 transition-colors disabled:opacity-50">
                {addManual.isPending ? "Adding…" : `Add ${pending.size || ""} session${pending.size === 1 ? "" : "s"}`}
              </button>
            </div>
            <SessionsList sessions={sessions} isLoading={isLoading} onRemove={(id) => remove.mutate(id)} />
          </div>
        </div>
      )}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}

function SessionsList({ sessions, isLoading, onRemove }: { sessions: Session[]; isLoading: boolean; onRemove: (id: string) => void }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">This cohort&rsquo;s sessions</span>
        <span className="text-sm font-bold text-primary">{sessions.length}</span>
      </div>
      <div className="max-h-[22rem] overflow-y-auto flex flex-col gap-1.5 pr-1">
        {isLoading ? <Spinner /> : sessions.length === 0 ? (
          <p className="text-sm text-muted-foreground italic">No sessions yet.</p>
        ) : sessions
          .slice()
          .sort((a, b) => a.meeting_date.localeCompare(b.meeting_date))
          .map((s, i) => (
            <div key={s.id} className="flex items-center justify-between gap-2 px-3 py-2 border border-border rounded-xl bg-card">
              <span className="text-sm text-foreground">
                <span className="text-muted-foreground font-mono text-xs mr-2">{String(i + 1).padStart(2, "0")}</span>
                {fmtDate(s.meeting_date)}
              </span>
              <button onClick={() => onRemove(s.id)} className="p-1 text-muted-foreground hover:text-red-600 transition-colors" aria-label="Remove session">
                <Trash2 size={14} />
              </button>
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
    <div className="grid gap-10" style={{ gridTemplateColumns: "minmax(0,55fr) minmax(0,45fr)" }}>
      <div>
        {selected ? (
          <div className="flex flex-col gap-6">
            <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-xl bg-primary/10 border border-primary/25">
              <span className="text-sm font-semibold text-foreground">Overriding: {fmtDate(selected.meeting_date)}</span>
              <button onClick={() => setSelectedId(null)} className="text-xs font-semibold text-primary hover:opacity-80">
                ← Back to cohort defaults
              </button>
            </div>
            <SessionOpeningsPanel sessionId={selected.id} />
            <div className="rounded-2xl border border-border bg-card p-4">
              <SessionChecklistPanel sessionId={selected.id} cohortId={cohort.id} programId={cohort.program_id} />
            </div>
          </div>
        ) : (
          <CohortRolesPanel cohort={cohort} />
        )}
      </div>

      <div className="flex flex-col gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">This cohort&rsquo;s sessions</p>
          <p className="text-xs text-muted-foreground mt-0.5">Pick one to override just that day.</p>
        </div>
        <div className="flex flex-col gap-2 max-h-[34rem] overflow-y-auto pr-1">
          {isLoading ? <Spinner /> : sessions.length === 0 ? (
            <p className="text-sm text-muted-foreground italic">No sessions yet — add some on the Sessions step first.</p>
          ) : sessions
            .slice()
            .sort((a, b) => a.meeting_date.localeCompare(b.meeting_date))
            .map((s, i) => (
              <button
                key={s.id}
                onClick={() => setSelectedId(s.id === selectedId ? null : s.id)}
                className={cn(
                  "text-left px-4 py-3 rounded-xl border transition-colors",
                  s.id === selectedId ? "border-primary bg-primary/5" : "border-border bg-card hover:border-muted-foreground/30",
                )}
              >
                <span className="text-sm font-semibold text-foreground">Session {i + 1}</span>
                <p className="text-xs text-muted-foreground mt-0.5">{fmtDate(s.meeting_date)}</p>
              </button>
            ))}
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
    <div className="flex flex-col gap-3">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center justify-between gap-4 px-5 py-4 border border-border rounded-2xl bg-card">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground w-40 shrink-0">{r.label}</span>
          <span className="text-sm text-foreground flex-1">{r.value}</span>
        </div>
      ))}
      <p className="text-xs text-muted-foreground text-right pt-2">You can change anything later from the cohort page.</p>
    </div>
  )
}
