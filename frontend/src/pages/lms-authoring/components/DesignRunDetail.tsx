import { Fragment, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { FileText } from "lucide-react"
import { Spinner } from "@/components/ui/primitives"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { attemptDesignDetailApi } from "@/api/missionsInstructor"
import type { DesignState } from "@/api/missionsDesign"
import { ensureAbsoluteUrl } from "@/lib/utils"

const N = (v: number | null | undefined, digits = 1) => (v == null ? "—" : v.toFixed(digits))

const MARGIN_TONE: Record<string, string> = {
  good: "ring-emerald-500/30 bg-emerald-500/5",
  tight: "ring-amber-500/30 bg-amber-500/5",
  fail: "ring-destructive/30 bg-destructive/5",
  incomplete: "ring-border",
}

/** Full read-only replica of the student's own design wizard (operator ask,
 * 2026-08-24: "open the run and see everything there with read only, just
 * like the student view") — every tab the student gets, minus any input or
 * save control, backed by the exact same `DesignState` payload
 * (`attemptDesignDetailApi`, `/missions/instructor/attempts/{id}/design-
 * detail`, reachable by ops too — see that endpoint's docstring). Nothing
 * here writes; it's a grading/review view, not a second editor.
 *
 * Shared between the student profile's "Mission runs" list
 * (`LmsStudentDetail`), the cohort review queue (`LmsProgramAdmin`), and
 * (Phase 3, 2026-09) the judge's team detail page — all key off the same
 * `MissionAttempt.id`, just through different, appropriately-scoped fetch
 * endpoints. `fetchFn`/`queryKeySuffix` default to the original ops-only
 * fetch, so every pre-existing call site is unaffected. */
export function DesignRunDetail({
  attemptId, fetchFn = attemptDesignDetailApi, queryKeySuffix,
}: { attemptId: string; fetchFn?: (attemptId: string) => Promise<DesignState>; queryKeySuffix?: string }) {
  const { data: detail, isLoading, error } = useQuery({
    queryKey: queryKeySuffix ? ["design-run-detail", attemptId, queryKeySuffix] : ["design-run-detail", attemptId],
    queryFn: () => fetchFn(attemptId),
  })
  const [tab, setTab] = useState("setup")
  const [expandedCustoms, setExpandedCustoms] = useState<Set<string>>(new Set())
  const toggleCustom = (id: string) =>
    setExpandedCustoms((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

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
                    <Fragment key={c.id}>
                      <tr className="border-b border-border/50 last:border-0">
                        <td className="py-1.5 pr-3 text-foreground">
                          {c.is_custom && (
                            <span className="mr-1.5 px-1.5 py-0.5 rounded text-[10px] font-bold bg-violet-500/15 text-violet-600 dark:text-violet-400">CUSTOM</span>
                          )}
                          {c.component_name}
                          {c.is_custom && (
                            <button
                              type="button"
                              onClick={() => toggleCustom(c.id)}
                              className="ml-2 text-[11px] font-semibold text-primary hover:underline"
                            >
                              {expandedCustoms.has(c.id) ? "Hide specs" : "Full specs"}
                            </button>
                          )}
                        </td>
                        <td className="py-1.5 pr-3 text-muted-foreground">{c.subsystem}</td>
                        <td className="py-1.5 pr-3 text-right text-foreground">{c.quantity}</td>
                        <td className="py-1.5 pr-3 text-right text-foreground">{c.mass_per_unit_g ?? "—"}</td>
                        <td className="py-1.5 pr-3 text-right text-foreground">
                          {c.voltage_v ?? "—"} / {c.current_ma ?? "—"}
                        </td>
                        <td className="py-1.5 pr-3 text-right text-foreground">{c.cost_per_unit_aed ?? "—"}</td>
                        <td className="py-1.5 text-muted-foreground">{c.on_mode_ids.map(modeName).join(", ") || "—"}</td>
                      </tr>
                      {c.is_custom && expandedCustoms.has(c.id) && (
                        <tr key={`${c.id}-specs`} className="border-b border-border/50">
                          <td colSpan={7} className="pb-2.5 text-muted-foreground">
                            <div className="flex flex-col gap-1 rounded-lg bg-muted/60 px-3 py-2">
                              {c.purpose_function && <p><span className="font-semibold text-foreground">Purpose:</span> {c.purpose_function}</p>}
                              {c.power_computed_mw != null && <p><span className="font-semibold text-foreground">Power:</span> {c.power_computed_mw.toFixed(1)} mW (auto: V × mA)</p>}
                              {c.pins_used && <p className="whitespace-pre-line"><span className="font-semibold text-foreground">Pins:</span> {c.pins_used}</p>}
                              {c.measurement_output && <p><span className="font-semibold text-foreground">Output:</span> {c.measurement_output}</p>}
                              {c.measurement_range && <p><span className="font-semibold text-foreground">Range:</span> {c.measurement_range}</p>}
                              {c.datasheet_reference && (
                                <div className="flex items-center gap-2 pt-1">
                                  <span className="font-semibold text-foreground">Datasheet:</span>{" "}
                                  <a
                                    href={ensureAbsoluteUrl(c.datasheet_reference)}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="h-7 px-2.5 rounded-md bg-primary/10 ring-1 ring-primary/30 inline-flex items-center justify-center gap-1.5 text-xs font-bold tracking-wide text-primary hover:bg-primary/15 transition-colors"
                                  >
                                    <FileText className="size-3" /> VIEW DATASHEET
                                  </a>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
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
                  <a href={ensureAbsoluteUrl(detail.poster_template_url)} target="_blank" rel="noreferrer" className="text-primary hover:underline underline-offset-4">
                    Open template ↗
                  </a>
                ) : <span className="text-muted-foreground">Not set</span>}
              </div>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-0.5">Their working poster</div>
                {detail.poster_url ? (
                  <a href={ensureAbsoluteUrl(detail.poster_url)} target="_blank" rel="noreferrer" className="text-primary hover:underline underline-offset-4">
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
