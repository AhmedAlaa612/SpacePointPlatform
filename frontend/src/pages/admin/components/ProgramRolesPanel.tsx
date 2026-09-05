/** A program's default role template (2026-09) — the Program Wizard's
 *  "Roles & checklist" step. Same collapsible-role-card visual language as
 *  `CohortRolesPanel`'s `large` mode (ported from the approved design),
 *  reusing its exported `ChecklistSection` as-is (`scope="programs"`).
 *
 *  Simpler than `CohortRolesPanel` in one real way: a program has no
 *  sessions, so there is no per-session override view and no "session-only
 *  extra role" case to render.
 *
 *  **Copy, not inheritance** (operator decision, 2026-09): saving here only
 *  ever affects `program_openings`, a one-time seed `create_cohort` copies
 *  into a new cohort's own `cohort_openings` rows. Editing this template
 *  later never reaches a cohort that already exists — see the backend
 *  `ProgramOpening` model's docstring. That is why this panel has no
 *  "inherited from program" language anywhere: there is nothing beneath a
 *  program in this particular chain to say is inheriting it.
 */
import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronDown, ChevronUp } from "lucide-react"
import type { Program } from "@/types/sessions"
import { getDeliveryRolesApi, getProgramOpeningsApi, setProgramOpeningsApi } from "@/api/sessions/openings"
import { ChecklistSection } from "@/pages/admin/components/CohortRolesPanel"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

const OUTFIT = "'Outfit', ui-sans-serif, system-ui, sans-serif"

interface RoleDraft {
  role_id: string
  slots: number
  amount_aed: string
  notes: string
  responsibilities_override: string
}

export function ProgramRolesPanel({ program }: { program: Program }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [error, setError] = useState("")
  const [draft, setDraft] = useState<RoleDraft[] | null>(null)
  const [openRoleId, setOpenRoleId] = useState<string | null>(null)

  const { data: roles = [] } = useQuery({ queryKey: ["delivery-roles"], queryFn: () => getDeliveryRolesApi() })
  const { data: openings = [], isLoading } = useQuery({
    queryKey: ["program-openings-defaults", program.id],
    queryFn: () => getProgramOpeningsApi(program.id),
  })

  const toDraft = () => roles
    .filter((r) => r.is_active)
    .map((r) => {
      const o = openings.find((x) => x.role_id === r.id)
      return {
        role_id: r.id,
        slots: o?.slots ?? 1,
        amount_aed: o?.amount_aed != null ? String(o.amount_aed) : "",
        notes: o?.notes ?? "",
        responsibilities_override: o?.responsibilities_override ?? o?.role_description ?? r.description ?? "",
      }
    })

  useEffect(() => {
    if (roles.length && !isLoading) setDraft(toDraft())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roles, openings, isLoading])

  const rows = draft ?? []

  const save = useMutation({
    mutationFn: () => setProgramOpeningsApi({
      programId: program.id,
      openings: rows
        .filter((d) => d.amount_aed !== "" || d.notes || d.responsibilities_override || d.slots !== 1)
        .map((d) => ({
          role_id: d.role_id,
          slots: d.slots,
          amount_aed: d.amount_aed === "" ? null : Number(d.amount_aed),
          notes: d.notes || null,
          responsibilities_override: d.responsibilities_override || null,
        })),
    }),
    onSuccess: () => {
      toast.success("Roles saved")
      setError("")
      qc.invalidateQueries({ queryKey: ["program-openings-defaults", program.id] })
    },
    onError: (e: any) => setError(getErrorMessage(e, "Could not save roles")),
  })

  const label = (text: string) => (
    <span style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em" }} className="text-muted-foreground">{text}</span>
  )
  const bigField: React.CSSProperties = { height: 48, padding: "0 16px", borderRadius: 14, fontSize: 17, width: "100%", boxSizing: "border-box" }

  if (isLoading || draft === null) {
    return <p className="text-base text-muted-foreground py-1">Loading roles…</p>
  }

  return (
    <div className="flex flex-col" style={{ gap: 28 }}>
      <div className="flex flex-col" style={{ gap: 20 }}>
        <div className="flex items-baseline justify-between flex-wrap" style={{ gap: 16 }}>
          <span style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.09em" }} className="text-muted-foreground">Roles</span>
          <span style={{ fontSize: 15 }} className="text-muted-foreground">Every new cohort of this program starts with these, once.</span>
        </div>

        {rows.map((d, i) => {
          const role = roles.find((r) => r.id === d.role_id)
          if (!role) return null
          const open = openRoleId === role.id
          return (
            <div key={d.role_id}
              style={{ borderRadius: 18, padding: "24px 28px", boxShadow: "0 3px 0 hsl(var(--border)), 0 12px 24px -14px rgba(40,16,80,.28)" }}
              className={open ? "flex flex-col border-[1.5px] border-primary bg-card" : "flex flex-col border border-border bg-card"}
            >
              <div className="flex items-start justify-between" style={{ gap: 24 }}>
                <div className="flex flex-col" style={{ gap: 8, minWidth: 0 }}>
                  <span style={{ fontFamily: OUTFIT, fontSize: 22, fontWeight: 600 }} className="text-foreground">{role.name}</span>
                  <p style={{ fontSize: 16, textWrap: "pretty" }} className="text-muted-foreground m-0">
                    {d.responsibilities_override || role.description || "No default text set for this role."}
                  </p>
                </div>
                <div className="flex flex-col items-end shrink-0" style={{ gap: 6 }}>
                  <span style={{ fontFamily: OUTFIT, fontSize: 24, fontWeight: 600, letterSpacing: "-0.02em" }} className="text-foreground tabular-nums">
                    {d.amount_aed ? `AED ${d.amount_aed}` : role.default_rate_aed != null ? `AED ${role.default_rate_aed}` : "No rate set"}
                  </span>
                  <span style={{ fontSize: 14 }} className="text-muted-foreground">per session &middot; {d.slots} slot{d.slots === 1 ? "" : "s"}</span>
                </div>
              </div>

              <div className="flex items-center justify-between" style={{ gap: 16, paddingTop: 14, marginTop: 14, borderTop: "1px solid hsl(var(--border))" }}>
                <span style={{ fontSize: 15 }} className="text-muted-foreground">
                  Copied into every new cohort of this program — editing it later won&rsquo;t change ones that already exist.
                </span>
                <button
                  type="button"
                  onClick={() => setOpenRoleId(open ? null : role.id)}
                  style={{ height: 38, padding: "0 14px", borderRadius: 12, fontSize: 15, fontWeight: 600 }}
                  className="flex items-center gap-2 text-primary hover:bg-primary/10 transition-colors"
                >
                  Rate, responsibilities &amp; checklist {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </button>
              </div>

              {open && (
                <div className="flex flex-col" style={{ gap: 20, paddingTop: 20, marginTop: 6, borderTop: "1px dashed hsl(var(--border))" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 16 }}>
                    <label className="flex flex-col" style={{ gap: 8 }}>
                      {label("Rate / session (AED)")}
                      <input
                        type="number" min={0}
                        placeholder={role.default_rate_aed != null ? `Default: ${role.default_rate_aed}` : "No default set"}
                        value={d.amount_aed}
                        onChange={(e) => setDraft(rows.map((x, j) => j === i ? { ...x, amount_aed: e.target.value } : x))}
                        style={{ ...bigField, fontFamily: OUTFIT, fontWeight: 600 }} className="border border-border bg-background text-foreground tabular-nums focus:outline-none focus:border-primary transition-colors"
                      />
                    </label>
                    <label className="flex flex-col" style={{ gap: 8 }}>
                      {label("Slots")}
                      <input
                        type="number" min={1}
                        value={d.slots}
                        onChange={(e) => setDraft(rows.map((x, j) =>
                          j === i ? { ...x, slots: Math.max(1, Number(e.target.value) || 1) } : x))}
                        style={{ ...bigField, fontFamily: OUTFIT, fontWeight: 600 }} className="border border-border bg-background text-foreground tabular-nums focus:outline-none focus:border-primary transition-colors"
                      />
                    </label>
                  </div>

                  <label className="flex flex-col" style={{ gap: 8 }}>
                    {label("Responsibilities override")}
                    <textarea
                      rows={3}
                      placeholder={role.description ? `Default: ${role.description}` : "No default text set for this role"}
                      value={d.responsibilities_override}
                      onChange={(e) => setDraft(rows.map((x, j) =>
                        j === i ? { ...x, responsibilities_override: e.target.value } : x))}
                      style={{ padding: "14px 16px", borderRadius: 14, fontSize: 16, lineHeight: 1.55, width: "100%", boxSizing: "border-box" }}
                      className="border border-border bg-background text-foreground resize-y focus:outline-none focus:border-primary transition-colors"
                    />
                    <span style={{ fontSize: 14 }} className="text-muted-foreground">Leave as-is to keep the role&rsquo;s platform default.</span>
                  </label>

                  <label className="flex flex-col" style={{ gap: 8 }}>
                    {label("Notes")}
                    <input
                      placeholder="Optional"
                      value={d.notes}
                      onChange={(e) => setDraft(rows.map((x, j) => j === i ? { ...x, notes: e.target.value } : x))}
                      style={bigField} className="border border-border bg-background text-foreground focus:outline-none focus:border-primary transition-colors"
                    />
                  </label>

                  <ChecklistSection
                    scope="programs" ownerId={program.id} roleId={role.id} label={`${role.name} checklist`}
                    hint="Replaces the general checklist for this role" large
                  />
                </div>
              )}
            </div>
          )
        })}

        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => { setError(""); save.mutate() }}
            disabled={save.isPending}
            style={{ height: 48, padding: "0 28px", borderRadius: 14, fontFamily: OUTFIT, fontSize: 16, fontWeight: 600 }}
            className="bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-40 transition-opacity"
          >{save.isPending ? "Saving…" : "Save roles"}</button>
        </div>
        {error && <p style={{ fontSize: 15 }} className="text-red-600 dark:text-red-400">{error}</p>}
      </div>

      <div className="flex flex-col" style={{ gap: 20 }}>
        <div className="flex items-baseline justify-between" style={{ gap: 16 }}>
          <span style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.09em" }} className="text-muted-foreground">Daily checklist</span>
          <span style={{ fontSize: 14 }} className="text-muted-foreground">Applies to any role without its own list</span>
        </div>
        <ChecklistSection
          scope="programs" ownerId={program.id} roleId={null} label="General checklist"
          hint="Applies to any role without its own list" large forceOpen
        />
      </div>
    </div>
  )
}
