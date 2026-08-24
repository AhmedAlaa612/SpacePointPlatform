import { useState } from "react"
import { isAxiosError } from "axios"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "@tanstack/react-router"
import { ArrowLeft, ChevronDown, Plus, X } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useAuth } from "@/context/AuthContext"
import {
  getStudentProfileApi, listUserEnrollmentsApi, grantCourseEnrollmentApi, revokeCourseEnrollmentApi,
  getStudentDesignRunsApi, type StudentDesignRun,
  getStudentProfileInstructorApi, listUserEnrollmentsInstructorApi, getStudentDesignRunsInstructorApi,
  getStudentCourseProgressApi,
} from "@/api/lms_admin"
import { attemptDesignDetailApi } from "@/api/missionsInstructor"
import { ItemPicker } from "@/pages/lms-authoring/components/ItemPicker"
import { AVATAR_PRESETS } from "@/components/games/avatarPresets"
import { updateUserApi } from "@/api/admin/users"

/** Student profile (2026-08-12) — nickname, programs attended, and the
 * courses they're currently on, with assign/remove in one place. This is
 * the reverse direction of `AssignPanel` (course/mission fixed, staff
 * picked) — here the student is fixed and the course is picked, so it's a
 * small dedicated section rather than forcing `AssignPanel` to be
 * bidirectional.
 *
 * Instructor access (2026-08-22, Programs/Cohort Missions merge) — reads
 * everything the same as ops, scoped server-side to their own cohorts'
 * students; identity edits and course assign/revoke stay ops-only (those
 * hit `/admin/users` and `/lms/admin/courses/{id}/enrollments`, neither
 * widened for this), so those controls are hidden rather than disabled. */
const RUN_STATUS_STYLE: Record<StudentDesignRun["status"], string> = {
  passed: "bg-emerald-500/10 text-emerald-500",
  failed: "bg-red-500/10 text-red-500",
  submitted: "bg-amber-500/10 text-amber-600",
  in_progress: "bg-primary/10 text-primary",
  abandoned: "bg-muted text-muted-foreground",
}

const RUN_STATUS_LABEL: Record<StudentDesignRun["status"], string> = {
  passed: "Passed", failed: "Failed", submitted: "Submitted",
  in_progress: "In progress", abandoned: "Abandoned",
}

const MARGIN_TONE: Record<string, string> = {
  good: "ring-emerald-500/30 bg-emerald-500/5",
  tight: "ring-amber-500/30 bg-amber-500/5",
  fail: "ring-destructive/30 bg-destructive/5",
  incomplete: "ring-border",
}

export default function LmsStudentDetail() {
  const { userId } = useParams({ strict: false }) as { userId: string }
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { currentUser } = useAuth()
  const isStaff = currentUser?.role !== "instructor"
  const [courseId, setCourseId] = useState("")
  const [nickname, setNickname] = useState<string | null>(null)
  const [identityError, setIdentityError] = useState("")
  const [expandedRuns, setExpandedRuns] = useState<Record<string, boolean>>({})

  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ["lms-admin-student-profile", userId],
    queryFn: () => (isStaff ? getStudentProfileApi(userId) : getStudentProfileInstructorApi(userId)),
  })
  const { data: enrollments = [], isLoading: enrollmentsLoading } = useQuery({
    queryKey: ["lms-admin-user-enrollments", userId],
    queryFn: () => (isStaff ? listUserEnrollmentsApi(userId) : listUserEnrollmentsInstructorApi(userId)),
  })
  const { data: designRuns, isLoading: designRunsLoading } = useQuery({
    queryKey: ["lms-admin-student-design-runs", userId],
    queryFn: () => (isStaff ? getStudentDesignRunsApi(userId) : getStudentDesignRunsInstructorApi(userId)),
  })

  const invalidateEnrollments = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-user-enrollments", userId] })

  const enrollMutation = useMutation({
    mutationFn: (course_id: string) => grantCourseEnrollmentApi(course_id, userId),
    onSuccess: () => { setCourseId(""); invalidateEnrollments() },
  })
  const revokeMutation = useMutation({
    mutationFn: (enrollmentId: string) => revokeCourseEnrollmentApi(enrollmentId),
    onSuccess: invalidateEnrollments,
  })

  // Nickname and avatar are what a student is called in front of a class,
  // and until now only the student could change either — from inside a game
  // lobby. A generated callsign occasionally lands somewhere unusable, and
  // "ask them to open a lobby and fix it themselves" is not a moderation
  // tool.
  const saveIdentity = useMutation({
    mutationFn: (patch: { nickname?: string; avatar?: string }) => updateUserApi(userId, patch),
    onSuccess: () => {
      setIdentityError("")
      setNickname(null)
      void queryClient.invalidateQueries({ queryKey: ["lms-admin-student-profile", userId] })
      void queryClient.invalidateQueries({ queryKey: ["lms-admin-students"] })
    },
    onError: (err) => setIdentityError(
      (isAxiosError(err) && typeof err.response?.data?.detail === "string")
        ? err.response.data.detail
        : "Couldn't save that.",
    ),
  })

  if (profileLoading || !profile) return <Spinner />

  const activeEnrollments = enrollments.filter((e) => e.status === "active")

  return (
    <div className="flex flex-col gap-6">
      <button
        // Staff has a full students roster to go back to (`/students`
        // declares a validateSearch (?invite_code=), so TanStack requires
        // the search object here with every key present — undefined = back
        // to the unfiltered list). Instructors never had a roster page of
        // their own to land on — the only page they can actually reach is
        // Programs, where the student link that got them here lives.
        onClick={() => void (isStaff
          ? navigate({ to: "/lms-authoring/students", search: { invite_code: undefined } })
          : navigate({ to: "/lms-authoring/curriculum" }))}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors w-fit"
      >
        <ArrowLeft size={14} /> {isStaff ? "Students" : "Programs"}
      </button>

      <PageHeader
        title={profile.full_name}
        subtitle={profile.email}
        action={profile.nickname ? (
          <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-primary/10 text-primary">{profile.nickname}</span>
        ) : undefined}
      />

      {isStaff && (
        <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl">
          <div>
            <h3 className="text-sm font-medium text-foreground">Game identity</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              What this student is called on a leaderboard. Their real name stays a staff-only
              reveal either way.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1.5">
              <label className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Nickname</label>
              <input
                value={nickname ?? profile.nickname ?? ""}
                onChange={(e) => setNickname(e.target.value)}
                placeholder="SpaceOtter77"
                className="h-9 px-3 w-56 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </div>
            <button
              onClick={() => saveIdentity.mutate({ nickname: (nickname ?? "").trim() })}
              disabled={saveIdentity.isPending || nickname === null || !nickname.trim()}
              className="h-9 px-4 rounded-xl text-sm font-medium bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-40"
            >
              Save nickname
            </button>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Avatar</label>
            <div className="flex flex-wrap gap-1.5">
              {AVATAR_PRESETS.map((preset) => {
                const Icon = preset.icon
                const active = profile.avatar === preset.key
                return (
                  <button
                    key={preset.key}
                    onClick={() => saveIdentity.mutate({ avatar: preset.key })}
                    disabled={saveIdentity.isPending}
                    title={preset.label}
                    className={`size-10 rounded-xl border flex items-center justify-center transition-colors disabled:opacity-50 ${
                      active
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border text-muted-foreground hover:bg-muted"}`}
                  >
                    <Icon size={16} />
                  </button>
                )
              })}
            </div>
          </div>
          {identityError && <p className="text-xs text-destructive">{identityError}</p>}
        </div>
      )}

      <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl">
        <h3 className="text-sm font-medium text-foreground">Programs attended</h3>
        {profile.programs.length === 0 ? (
          <EmptyState title="No programs yet" hint="This student has no active or past registrations." />
        ) : (
          <div className="flex flex-col gap-2">
            {profile.programs.map((p) => (
              <div key={p.registration_id} className="flex items-center justify-between p-3 bg-background border border-border rounded-xl">
                <div>
                  <p className="text-sm text-foreground">{p.program_name}</p>
                  <p className="text-xs text-muted-foreground">{p.cohort_name}</p>
                </div>
                {p.starts_on && (
                  <span className="text-xs text-muted-foreground shrink-0">
                    {p.starts_on}{p.ends_on ? ` – ${p.ends_on}` : ""}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl">
        <h3 className="text-sm font-medium text-foreground">Courses</h3>

        {enrollmentsLoading ? (
          <Spinner />
        ) : activeEnrollments.length === 0 ? (
          <EmptyState title="Not enrolled in any course" hint={isStaff ? "Assign one below." : undefined} />
        ) : (
          <div className="flex flex-col gap-2">
            {activeEnrollments.map((e) => (
              <CourseProgressRow key={e.id} userId={userId} courseId={e.course_id} title={e.course_title} source={e.source} isStaff={isStaff}
                onRevoke={isStaff ? () => revokeMutation.mutate(e.id) : undefined} revokePending={revokeMutation.isPending}
              />
            ))}
          </div>
        )}

        {isStaff && (
          <div className="flex items-center gap-2 pt-1 border-t border-border">
            <ItemPicker type="course" value={courseId} onChange={setCourseId} />
            <button
              onClick={() => courseId && enrollMutation.mutate(courseId)}
              disabled={!courseId || enrollMutation.isPending}
              className="flex items-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors disabled:opacity-50"
            >
              <Plus size={14} /> Assign
            </button>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl">
        <h3 className="text-sm font-medium text-foreground">Mission runs</h3>

        {designRunsLoading ? (
          <Spinner />
        ) : !designRuns || designRuns.runs.length === 0 ? (
          <EmptyState title="No design mission runs yet" hint="This student hasn't started a design mission." />
        ) : (
          <div className="flex flex-col gap-2">
            {designRuns.runs.map((run) => {
              const expanded = !!expandedRuns[run.attempt_id]
              return (
                <div key={run.attempt_id} className="bg-background border border-border rounded-xl overflow-hidden">
                  <button
                    onClick={() => setExpandedRuns((prev) => ({ ...prev, [run.attempt_id]: !prev[run.attempt_id] }))}
                    className="w-full flex items-center justify-between p-3 text-left"
                  >
                    <div className="min-w-0">
                      <p className="text-sm text-foreground truncate">{run.design_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {run.variant_label}
                        {run.started_at && <> · {new Date(run.started_at).toLocaleDateString()}</>}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${RUN_STATUS_STYLE[run.status]}`}>
                        {RUN_STATUS_LABEL[run.status]}
                      </span>
                      <ChevronDown size={14} className={`text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`} />
                    </div>
                  </button>
                  {expanded && <DesignRunDetail attemptId={run.attempt_id} />}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

const N = (v: number | null | undefined, digits = 1) => (v == null ? "—" : v.toFixed(digits))

/** Full read-only replica of the student's own design wizard (operator ask,
 * 2026-08-24: "open the run and see everything there with read only, just
 * like the student view") — every tab the student gets, minus any input or
 * save control, backed by the exact same `DesignState` payload
 * (`attemptDesignDetailApi`, `/missions/instructor/attempts/{id}/design-
 * detail`, reachable by ops too — see that endpoint's docstring). Nothing
 * here writes; it's a grading/review view, not a second editor. */
function DesignRunDetail({ attemptId }: { attemptId: string }) {
  const { data: detail, isLoading, error } = useQuery({
    queryKey: ["lms-admin-design-run-detail", attemptId],
    queryFn: () => attemptDesignDetailApi(attemptId),
  })
  const [tab, setTab] = useState("setup")

  if (isLoading) return <div className="px-3 pb-3"><Spinner /></div>
  if (error || !detail) {
    return <p className="px-3 pb-3 text-xs text-muted-foreground">Couldn't load this run's detail.</p>
  }

  const modeName = (id: string) => detail.modes.find((m) => m.id === id)?.mode_name ?? id

  return (
    <div className="px-3 pb-3 border-t border-border pt-3">
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap h-auto">
          <TabsTrigger value="setup">Setup</TabsTrigger>
          <TabsTrigger value="components">Components</TabsTrigger>
          {detail.modes.length > 0 && <TabsTrigger value="conops">CONOPS</TabsTrigger>}
          <TabsTrigger value="budgets">Budgets</TabsTrigger>
          <TabsTrigger value="report">Report</TabsTrigger>
          {(detail.poster_url || detail.poster_template_url) && <TabsTrigger value="poster">Poster</TabsTrigger>}
        </TabsList>

        <TabsContent value="setup">
          <div className="flex flex-col gap-3 text-xs pt-1">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-0.5">Mission name</div>
              <div className="text-sm text-foreground font-medium">{detail.design_name || "—"}</div>
            </div>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-0.5">Objective</div>
              <p className="text-foreground whitespace-pre-line">{detail.design_objective || "—"}</p>
            </div>
            <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-muted-foreground pt-1">
              <span>Variant: <span className="text-foreground">{detail.variant_label}</span></span>
              <span>CubeSat: <span className="text-foreground">{detail.selected_cubesat_size}</span></span>
              {detail.orbit_type && <span>Orbit: <span className="text-foreground">{detail.orbit_type}</span></span>}
              {detail.orbit_duration_min != null && <span>{detail.orbit_duration_min} min/orbit</span>}
              {detail.orbits_per_day != null && <span>{detail.orbits_per_day} orbits/day</span>}
              <span>Solar cells: <span className="text-foreground">{detail.selected_solar_cells}</span></span>
              {detail.battery_capacity_wh != null && <span>Battery: <span className="text-foreground">{detail.battery_capacity_wh} Wh</span></span>}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="components">
          {detail.components.length === 0 ? (
            <p className="text-xs text-muted-foreground pt-1">No components added yet.</p>
          ) : (
            <div className="overflow-x-auto pt-1">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="text-left font-medium py-1.5 pr-3">Component</th>
                    <th className="text-left font-medium py-1.5 pr-3">Subsystem</th>
                    <th className="text-right font-medium py-1.5 pr-3">Qty</th>
                    <th className="text-right font-medium py-1.5 pr-3">Mass (g)</th>
                    <th className="text-right font-medium py-1.5 pr-3">V / mA</th>
                    <th className="text-right font-medium py-1.5 pr-3">Cost (AED)</th>
                    <th className="text-left font-medium py-1.5">On modes</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.components.map((c) => (
                    <tr key={c.id} className="border-b border-border/50 last:border-0">
                      <td className="py-1.5 pr-3 text-foreground">{c.component_name}</td>
                      <td className="py-1.5 pr-3 text-muted-foreground">{c.subsystem}</td>
                      <td className="py-1.5 pr-3 text-right text-foreground">{c.quantity}</td>
                      <td className="py-1.5 pr-3 text-right text-foreground">{c.mass_per_unit_g ?? "—"}</td>
                      <td className="py-1.5 pr-3 text-right text-foreground">
                        {c.voltage_v ?? "—"} / {c.current_ma ?? "—"}
                      </td>
                      <td className="py-1.5 pr-3 text-right text-foreground">{c.cost_per_unit_aed ?? "—"}</td>
                      <td className="py-1.5 text-muted-foreground">{c.on_mode_ids.map(modeName).join(", ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>

        {detail.modes.length > 0 && (
          <TabsContent value="conops">
            <div className="flex flex-col gap-3 pt-1">
              <div className="flex flex-col gap-1">
                {detail.modes.map((m) => (
                  <div key={m.id} className="flex items-baseline gap-2 text-xs">
                    <span className="font-medium text-foreground shrink-0">{m.mode_name}</span>
                    <span className="text-muted-foreground shrink-0">{m.duration_min} min</span>
                    {m.description && <span className="text-muted-foreground truncate">{m.description}</span>}
                  </div>
                ))}
                <p className="text-[11px] text-muted-foreground mt-1">
                  Total: {detail.dashboard.conops.total_mode_duration_min.toFixed(1)} min
                  {detail.orbit_duration_min != null && ` of ${detail.orbit_duration_min} min/orbit`}
                </p>
              </div>
              {detail.components.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left py-1.5 pr-3 font-medium text-muted-foreground">Component</th>
                        {detail.modes.map((m) => (
                          <th key={m.id} className="px-2 py-1.5 font-medium text-muted-foreground text-center">{m.mode_name}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {detail.components.map((c) => (
                        <tr key={c.id} className="border-b border-border/50">
                          <td className="py-1.5 pr-3 text-foreground">{c.component_name}</td>
                          {detail.modes.map((m) => (
                            <td key={m.id} className="px-2 py-1.5 text-center">
                              {c.on_mode_ids.includes(m.id) ? "●" : "—"}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </TabsContent>
        )}

        <TabsContent value="budgets">
          <div className="flex flex-col gap-4 pt-1 text-xs">
            <BudgetSection title="Data" totals={[
              ["Total/orbit", `${N(detail.dashboard.data.total_per_orbit_kb)} KB`],
              ["Total/day", `${N(detail.dashboard.data.total_per_day_kb)} KB`],
              ["Storage remaining", `${N(detail.dashboard.data.storage_remaining_kb)} of ${N(detail.dashboard.data.max_storage_kb, 0)} KB`],
            ]}>
              {detail.components.filter((c) => c.data_entry).map((c) => (
                <BudgetRow key={c.id} name={c.component_name} fields={[
                  ["Size/measurement", `${c.data_entry!.data_size_per_measurement_kb} KB`],
                  ["Measurements/min", c.data_entry!.measurements_per_minute],
                  ["Storage", c.data_entry!.storage_mode],
                ]} />
              ))}
            </BudgetSection>

            <BudgetSection title="Power" totals={[
              ["Total power", `${N(detail.dashboard.power.total_power_mw, 0)} mW`],
              ["Margin", `${N(detail.dashboard.power.power_margin_mw, 0)} mW`],
              ["Solar cells", `${detail.dashboard.power.selected_solar_cells} selected / ${detail.dashboard.power.required_solar_cells} required`],
            ]}>
              {detail.components.filter((c) => c.power_entry).map((c) => (
                <BudgetRow key={c.id} name={c.component_name} fields={[
                  ["Voltage", `${c.power_entry!.voltage_v ?? "—"} V`],
                  ["Current", `${c.power_entry!.current_ma ?? "—"} mA`],
                ]} />
              ))}
            </BudgetSection>

            <BudgetSection title="Energy" totals={[
              ["Balance/orbit", `${detail.dashboard.energy.energy_margin_mwh >= 0 ? "+" : ""}${N(detail.dashboard.energy.energy_margin_mwh, 0)} mWh`],
              ["Depth of discharge", `${N(detail.dashboard.energy.depth_of_discharge_pct, 0)}% of ${N(detail.dashboard.energy.max_depth_of_discharge_pct, 0)}% allowed`],
              ["Eclipse", `${N(detail.dashboard.energy.eclipse_minutes, 0)} min`],
            ]} />

            <BudgetSection title="Link" totals={[
              ["Status", detail.dashboard.link.status],
              ["Margin", `${N(detail.dashboard.link.margin_db, 2)} dB (need ${N(detail.dashboard.link.good_threshold_db, 1)})`],
              ["Band", detail.link_entry?.band_profile ?? "—"],
            ]}>
              {detail.link_entry && (
                <BudgetRow name="Configured link" fields={[
                  ["Downlink", `${detail.link_entry.downlink_frequency_mhz} MHz`],
                  ["Antenna gain", `${detail.link_entry.satellite_antenna_gain_dbi} dBi`],
                  ["Data rate", `${detail.link_entry.data_rate_kbps} kbps`],
                ]} />
              )}
            </BudgetSection>

            <BudgetSection title="Mass" totals={[
              ["Total mass", `${N(detail.dashboard.mass.total_mass_kg, 3)} kg of ${detail.dashboard.mass.max_allowed_mass_kg} kg`],
              ["Volume", `${N(detail.dashboard.mass.total_volume_cm3)} of ${detail.dashboard.mass.available_internal_volume_cm3} cm³`],
            ]}>
              {detail.components.filter((c) => c.mass_entry).map((c) => (
                <BudgetRow key={c.id} name={c.component_name} fields={[
                  ["Qty", c.mass_entry!.quantity ?? c.quantity],
                  ["Mass/unit", `${c.mass_entry!.mass_per_unit_g ?? "—"} g`],
                  ["Dims", `${c.mass_entry!.length_mm ?? "—"}×${c.mass_entry!.width_mm ?? "—"}×${c.mass_entry!.height_mm ?? "—"} mm`],
                ]} />
              ))}
            </BudgetSection>

            <BudgetSection title="Cost" totals={[
              ["Total cost", `${N(detail.dashboard.cost.total_cost_aed, 0)} AED`],
              ["Margin", `${N(detail.dashboard.cost.cost_margin_aed, 0)} of ${detail.dashboard.cost.maximum_budget_aed} AED`],
            ]}>
              {detail.components.filter((c) => c.cost_entry).map((c) => (
                <BudgetRow key={c.id} name={c.component_name} fields={[
                  ["Qty", c.cost_entry!.quantity ?? c.quantity],
                  ["Cost/unit", `${c.cost_entry!.cost_per_unit_aed ?? "—"} AED`],
                  ...(c.cost_entry!.vendor ? [["Vendor", c.cost_entry!.vendor] as [string, string]] : []),
                ]} />
              ))}
            </BudgetSection>
          </div>
        </TabsContent>

        <TabsContent value="report">
          <div className="flex flex-col gap-4 pt-1">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm font-semibold text-foreground">{detail.dashboard.overall.label}</span>
              <span className="text-xs text-muted-foreground">
                {detail.dashboard.overall.errors} failing · {detail.dashboard.overall.warnings} tight · {detail.dashboard.overall.incomplete} not started
              </span>
            </div>

            {detail.dashboard.alerts.length > 0 && (
              <div className="flex flex-col gap-1.5">
                {detail.dashboard.alerts.map((a, i) => (
                  <p key={i} className={`text-xs rounded-lg ring-1 px-3 py-2 ${MARGIN_TONE[a.severity === "error" ? "fail" : a.severity === "warning" ? "tight" : a.severity === "success" ? "good" : "incomplete"]}`}>
                    {a.message}
                  </p>
                ))}
              </div>
            )}

            {detail.dashboard.margins.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {detail.dashboard.margins.map((m) => (
                  <div key={m.key} title={m.interpretation} className={`rounded-lg ring-1 px-2.5 py-1.5 text-xs ${MARGIN_TONE[m.status] ?? "ring-border"}`}>
                    <span className="font-medium text-foreground">{m.label}</span>
                    <span className="text-muted-foreground ml-1.5">{m.status === "incomplete" ? "—" : `${m.value.toFixed(1)} ${m.unit}`}</span>
                  </div>
                ))}
              </div>
            )}

            {detail.dashboard.recommendations.length > 0 && (
              <div className="flex flex-col gap-2">
                {detail.dashboard.recommendations.map((r) => (
                  <div key={r.key} className="rounded-lg ring-1 ring-border px-3 py-2">
                    <p className="text-xs font-medium text-foreground">{r.title}</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">{r.message}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </TabsContent>

        {(detail.poster_url || detail.poster_template_url) && (
          <TabsContent value="poster">
            <div className="flex flex-col gap-3 pt-1 text-xs">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-0.5">Cohort template</div>
                {detail.poster_template_url ? (
                  <a href={detail.poster_template_url} target="_blank" rel="noreferrer" className="text-primary hover:underline underline-offset-4">
                    Open template ↗
                  </a>
                ) : <span className="text-muted-foreground">Not set</span>}
              </div>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-0.5">Their working poster</div>
                {detail.poster_url ? (
                  <a href={detail.poster_url} target="_blank" rel="noreferrer" className="text-primary hover:underline underline-offset-4">
                    Open their poster ↗
                  </a>
                ) : <span className="text-muted-foreground">Not linked yet</span>}
              </div>
            </div>
          </TabsContent>
        )}
      </Tabs>
    </div>
  )
}

function BudgetSection({ title, totals, children }: {
  title: string; totals: [string, string][]; children?: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-muted-foreground">
        {totals.map(([label, value]) => (
          <span key={label}>{label}: <span className="text-foreground">{value}</span></span>
        ))}
      </div>
      {children && <div className="flex flex-col gap-1.5 mt-0.5">{children}</div>}
    </div>
  )
}

function BudgetRow({ name, fields }: { name: string; fields: [string, string | number][] }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 rounded-lg ring-1 ring-border/60 px-2.5 py-1.5">
      <span className="font-medium text-foreground shrink-0">{name}</span>
      {fields.map(([label, value]) => (
        <span key={label} className="text-muted-foreground">{label}: <span className="text-foreground">{value}</span></span>
      ))}
    </div>
  )
}

function CourseProgressRow({
  userId, courseId, title, source, isStaff, onRevoke, revokePending,
}: {
  userId: string; courseId: string; title: string | null; source: string; isStaff: boolean
  onRevoke?: () => void; revokePending: boolean
}) {
  const [open, setOpen] = useState(false)

  return (
    <div className="bg-background border border-border rounded-xl overflow-hidden">
      <div className="flex items-center justify-between p-3">
        <button onClick={() => setOpen((v) => !v)} className="flex items-center gap-2 min-w-0 flex-1 text-left cursor-pointer">
          <ChevronDown size={13} className={`shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
          <span className="text-sm text-foreground truncate">
            {title ?? "Untitled course"}
            <span className="ml-2 text-xs text-muted-foreground uppercase tracking-wide">{source}</span>
          </span>
        </button>
        {isStaff && onRevoke && (
          <button
            onClick={onRevoke}
            disabled={revokePending}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors disabled:opacity-50 shrink-0"
            title="Remove access"
          >
            <X size={14} />
          </button>
        )}
      </div>
      {open && <CourseProgressDetail userId={userId} courseId={courseId} isStaff={isStaff} />}
    </div>
  )
}

function CourseProgressDetail({ userId, courseId, isStaff }: { userId: string; courseId: string; isStaff: boolean }) {
  const { data: progress, isLoading } = useQuery({
    queryKey: ["lms-admin-student-course-progress", userId, courseId, isStaff],
    queryFn: () => getStudentCourseProgressApi(userId, courseId, isStaff ? "admin" : "instructor"),
  })

  if (isLoading) return <div className="px-3 pb-3"><Spinner /></div>
  if (!progress) return null

  return (
    <div className="px-3 pb-3 border-t border-border pt-2 flex flex-col gap-1.5">
      {progress.modules.length === 0 ? (
        <p className="text-xs text-muted-foreground">No modules on this course.</p>
      ) : progress.modules.map((m) => (
        <div key={m.module_id} className="flex items-center gap-2 text-xs">
          <span className={`w-2 h-2 rounded-full shrink-0 ${m.mandatory_completed >= m.mandatory_total && m.mandatory_total > 0 ? "bg-emerald-500" : "bg-muted-foreground/30"}`} />
          <span className="flex-1 text-foreground truncate">{m.title ?? "Untitled module"}</span>
          <span className="text-muted-foreground shrink-0">{m.mandatory_completed}/{m.mandatory_total}</span>
          {m.locked && <span className="text-muted-foreground shrink-0">locked</span>}
        </div>
      ))}
    </div>
  )
}
