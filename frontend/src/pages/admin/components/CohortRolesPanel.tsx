/** The Roles tab (2026-08-28): responsibilities, rate and checklist together,
 *  per role, for one cohort — replacing the old rate-only block that used to
 *  sit at the top of the Staffing tab.
 *
 *  Rate and responsibilities share the same `cohort_openings` row (one per
 *  cohort+role) and save together through the existing openings-defaults
 *  endpoint. Checklist is a separate bucket entirely — its own endpoint,
 *  its own save — because a role can have zero, one, or many items and
 *  editing it is a whole-list replace, not a single-row field.
 *
 *  `large` (2026-09) renders the same data with the Cohort Wizard's bigger,
 *  collapsible-role-card visual language instead of the compact admin-table
 *  one — the wizard's own look, ported from the approved design, without
 *  changing how this panel looks on the plain cohort "Roles" tab that
 *  doesn't pass it. Data fetching/saving is identical either way; only the
 *  two render paths differ.
 */
import { useEffect, useState, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronDown, ChevronRight, ChevronUp, ImageIcon, Plus, Trash2 } from "lucide-react"
import type { Cohort } from "@/types/sessions"
import type { ChecklistItem } from "@/types/sessions"
import { getDeliveryRolesApi, getCohortOpeningsApi, getOpeningsApi, setCohortOpeningsApi } from "@/api/sessions/openings"
import { listChecklistItemsApi, setChecklistItemsApi, type ChecklistScope } from "@/api/sessions/day"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

const OUTFIT = "'Outfit', ui-sans-serif, system-ui, sans-serif"

type ChecklistDraftLine = {
  key: string
  title: string
  requires_proof: boolean
  is_required: boolean
}

function toDraftLines(items: ChecklistItem[]): ChecklistDraftLine[] {
  return items.map((i) => ({
    key: i.id, title: i.title, requires_proof: i.requires_proof, is_required: i.is_required,
  }))
}

/** What a blank bucket falls back to, for the preview-before-you-override
 *  display. `scope`/`ownerId` are the bucket actually being edited;
 *  `programId` is only meaningful for `scope: "cohorts"` (a program sits
 *  above a cohort in the chain — there's nothing above a program). */
async function fetchFallbackChecklistItems(
  scope: ChecklistScope,
  ownerId: string,
  programId?: string,
  roleId?: string | null,
): Promise<ChecklistItem[]> {
  if (roleId) {
    try {
      const sameLevelGeneral = await listChecklistItemsApi(scope, ownerId, null)
      if (sameLevelGeneral.length > 0) return sameLevelGeneral
    } catch {}
  }

  if (scope === "cohorts" && programId) {
    if (roleId) {
      try {
        const progRole = await listChecklistItemsApi("programs", programId, roleId)
        if (progRole.length > 0) return progRole
      } catch {}
    }
    try {
      const progGeneral = await listChecklistItemsApi("programs", programId, null)
      if (progGeneral.length > 0) return progGeneral
    } catch {}
  }
  return []
}

/** The data + mutation logic shared by both render sizes — nothing here
 *  changes between compact and large, only how it's drawn. */
function useRolesDraft(cohort: Cohort, sessionId?: string) {
  const qc = useQueryClient()
  const toast = useToast()
  const [error, setError] = useState("")
  const [draft, setDraft] = useState<RoleDraft[] | null>(null)

  const { data: roles = [] } = useQuery({
    queryKey: ["delivery-roles"],
    queryFn: () => getDeliveryRolesApi(),
  })
  const { data: openings = [], isLoading } = useQuery({
    queryKey: ["cohort-openings-defaults", cohort.id],
    queryFn: () => getCohortOpeningsApi(cohort.id),
  })
  // Shares its cache with SessionOpeningsPanel (same query key) when scoped
  // to a session — same reasoning as Reviews.tsx's shared "day-reviews" key.
  const { data: sessionOpenings, isLoading: sessionLoading } = useQuery({
    queryKey: ["session-openings", sessionId],
    queryFn: () => getOpeningsApi(sessionId!),
    enabled: !!sessionId,
  })
  const sessionRoleIds = sessionId ? new Set((sessionOpenings ?? []).map((o) => o.role_id)) : null
  // A role that's only visible here because *this session* added it as a
  // one-off — the cohort's own template (`openings`) has no row for it.
  // Saving anything on its card must never create one: that would silently
  // hand the role to every other session that's still inheriting the
  // cohort template wholesale, turning a single session's extra into a
  // cohort-wide default nobody asked for.
  const cohortRoleIds = new Set(openings.map((o) => o.role_id))
  const isSessionOnlyExtra = (roleId: string) =>
    !!sessionRoleIds && sessionRoleIds.has(roleId) && !cohortRoleIds.has(roleId)

  // Deliberately unfiltered by session — saving is a whole-cohort replace
  // (setCohortOpeningsApi deletes any role not present in the payload), so
  // the draft must carry every active role even when the render below only
  // *shows* the ones this session offers. Filtering here would silently
  // wipe out another session's role configuration on save.
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
    if (roles.length && !isLoading && !sessionLoading) setDraft(toDraft())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roles, openings, isLoading, sessionOpenings, sessionLoading])

  const save = useMutation({
    mutationFn: () => setCohortOpeningsApi({
      cohortId: cohort.id,
      openings: (draft ?? [])
        .filter((d) => !isSessionOnlyExtra(d.role_id))
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
      qc.invalidateQueries({ queryKey: ["cohort-openings-defaults", cohort.id] })
    },
    onError: (e: any) => setError(getErrorMessage(e, "Could not save roles")),
  })

  return {
    roles, draft, setDraft, isLoading: isLoading || sessionLoading || draft === null,
    sessionRoleIds, isSessionOnlyExtra, save, error, setError,
  }
}

/** One checklist bucket's editor — general (roleId omitted) or one role's
 *  own list, at any level (`scope`/`ownerId`: a cohort's own bucket, or —
 *  reused as-is by `ProgramRolesPanel` — a program's). Lazy: only fetches
 *  once expanded (or immediately, if `forceOpen` — the large layout's
 *  always-visible "Daily checklist"). */
export function ChecklistSection({
  scope, ownerId, programId, roleId, label, hint, large = false, forceOpen = false,
}: { scope: ChecklistScope; ownerId: string; programId?: string; roleId: string | null; label: string; hint: string; large?: boolean; forceOpen?: boolean }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [manualOpen, setManualOpen] = useState(false)
  const open = forceOpen || manualOpen
  const [draft, setDraft] = useState<ChecklistDraftLine[] | null>(null)
  const [isInherited, setIsInherited] = useState(false)
  const [isLoadingFallback, setIsLoadingFallback] = useState(false)
  const [error, setError] = useState("")

  const queryKey = ["checklist-items", scope, ownerId, roleId ?? "general"]
  const { data: items = [], isLoading } = useQuery({
    queryKey,
    queryFn: () => listChecklistItemsApi(scope, ownerId, roleId),
    enabled: open,
  })

  useEffect(() => {
    if (!open || draft !== null || isLoading) return

    if (items.length > 0) {
      setDraft(toDraftLines(items))
      setIsInherited(false)
    } else {
      setIsLoadingFallback(true)
      fetchFallbackChecklistItems(scope, ownerId, programId, roleId)
        .then((fb) => {
          setDraft(toDraftLines(fb))
          setIsInherited(fb.length > 0)
        })
        .catch(() => {
          setDraft([])
          setIsInherited(false)
        })
        .finally(() => setIsLoadingFallback(false))
    }
  }, [open, isLoading, items, draft, scope, ownerId, programId, roleId])

  const save = useMutation({
    mutationFn: () => setChecklistItemsApi(
      scope, ownerId,
      (draft ?? []).map((l, i) => ({
        title: l.title, requires_proof: l.requires_proof, is_required: l.is_required, sort_order: i + 1,
      })),
      roleId,
    ),
    onSuccess: () => {
      toast.success(`${label} checklist saved`)
      setError("")
      setIsInherited(false)
      qc.invalidateQueries({ queryKey })
    },
    onError: (e: any) => setError(getErrorMessage(e, "Could not save this checklist")),
  })

  const rows = draft ?? []
  const savedCount = open ? rows.length : undefined

  if (large) {
    return (
      <div className="flex flex-col" style={{ gap: 16 }}>
        {!forceOpen && (
          <button type="button" onClick={() => setManualOpen((v) => !v)} className="flex items-center justify-between text-left">
            <span style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.09em" }} className="flex items-center gap-2 text-muted-foreground">
              {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />} {label}
              {savedCount !== undefined && <span>&middot; {savedCount} item{savedCount === 1 ? "" : "s"}</span>}
            </span>
            <span style={{ fontSize: 14 }} className="text-muted-foreground">{hint}</span>
          </button>
        )}
        {open && (
          isLoading || isLoadingFallback || draft === null ? (
            <p style={{ fontSize: 16 }} className="text-muted-foreground">Loading&hellip;</p>
          ) : (
            <div className="flex flex-col" style={{ gap: 12 }}>
              {isInherited && rows.length > 0 && (
                <p style={{ fontSize: 14 }} className="text-muted-foreground italic">
                  Showing default inherited items. Edit and save to set a custom override for this cohort.
                </p>
              )}
              {rows.length === 0 && (
                <p style={{ fontSize: 15 }} className="text-muted-foreground">
                  Nothing set here yet &mdash; falls back to {roleId ? "the general checklist" : "the level above"}.
                </p>
              )}
              {rows.map((line, i) => (
                <div key={line.key} style={{ padding: "18px 22px", borderRadius: 16 }} className="flex items-center gap-4 border border-border bg-card">
                  <span style={{ fontSize: 17, flex: 1 }}>
                    <input
                      value={line.title}
                      placeholder="Checklist item"
                      onChange={(e) => setDraft(rows.map((r, j) => j === i ? { ...r, title: e.target.value } : r))}
                      style={{ fontSize: 17, height: 40 }}
                      className="w-full px-3 border border-border bg-background text-foreground rounded-xl focus:outline-none focus:border-primary transition-colors"
                    />
                  </span>
                  <label className="flex items-center gap-1.5 text-muted-foreground cursor-pointer whitespace-nowrap" style={{ fontSize: 14 }}>
                    <input
                      type="checkbox"
                      checked={line.is_required}
                      onChange={(e) => setDraft(rows.map((r, j) => j === i ? { ...r, is_required: e.target.checked } : r))}
                    />
                    Required
                  </label>
                  <label className="flex items-center gap-1.5 text-muted-foreground cursor-pointer whitespace-nowrap" style={{ fontSize: 14 }}>
                    <input
                      type="checkbox"
                      checked={line.requires_proof}
                      onChange={(e) => setDraft(rows.map((r, j) => j === i ? { ...r, requires_proof: e.target.checked } : r))}
                    />
                    <ImageIcon size={14} /> Needs photo
                  </label>
                  <button
                    type="button"
                    onClick={() => setDraft(rows.filter((_, j) => j !== i))}
                    className="text-muted-foreground hover:text-red-600 transition-colors shrink-0"
                    aria-label="Remove item"
                  ><Trash2 size={16} /></button>
                </div>
              ))}
              <div className="flex items-center" style={{ gap: 12, paddingTop: 4 }}>
                <button
                  type="button"
                  onClick={() => setDraft([...rows, {
                    key: `new-${Date.now()}-${rows.length}`, title: "", requires_proof: false, is_required: true,
                  }])}
                  style={{ height: 44, padding: "0 20px", borderRadius: 14, fontSize: 15, fontWeight: 500 }}
                  className="flex items-center gap-2 text-muted-foreground hover:text-foreground hover:bg-muted border border-dashed border-border transition-colors"
                ><Plus size={15} /> Add item</button>
                <button
                  type="button"
                  onClick={() => { setError(""); save.mutate() }}
                  disabled={save.isPending}
                  style={{ height: 44, padding: "0 22px", borderRadius: 14, fontSize: 15, fontWeight: 600 }}
                  className="bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-40 transition-opacity"
                >{save.isPending ? "Saving…" : "Save checklist"}</button>
              </div>
              {error && <p style={{ fontSize: 14 }} className="text-red-600 dark:text-red-400">{error}</p>}
            </div>
          )
        )}
      </div>
    )
  }

  return (
    <div className="border border-dashed border-border rounded-lg">
      <button
        type="button"
        onClick={() => setManualOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 px-3 py-2 text-left"
      >
        <span className="flex items-center gap-1.5 text-xs">
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          <span className="font-semibold text-foreground">{label}</span>
          <span className="text-muted-foreground">
            {savedCount !== undefined ? `· ${savedCount} item${savedCount === 1 ? "" : "s"}` : ""}
          </span>
        </span>
        <span className="text-[10px] text-muted-foreground hidden sm:inline">{hint}</span>
      </button>

      {open && (
        <div className="px-3 pb-3 flex flex-col gap-2 border-t border-dashed border-border pt-2">
          {isLoading || isLoadingFallback || draft === null ? (
            <p className="text-xs text-muted-foreground">Loading…</p>
          ) : (
            <>
              {isInherited && rows.length > 0 && (
                <p className="text-[11px] text-muted-foreground italic">
                  Showing default inherited items. Edit and save to set a custom override for this cohort.
                </p>
              )}
              {rows.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  Nothing set here yet — falls back to {roleId ? "the general checklist" : "the level above"}.
                </p>
              )}
              {rows.map((line, i) => (
                <div key={line.key} className="flex items-center gap-2 flex-wrap">
                  <input
                    value={line.title}
                    placeholder="Checklist item"
                    onChange={(e) => setDraft(rows.map((r, j) => j === i ? { ...r, title: e.target.value } : r))}
                    className="flex-1 min-w-[10rem] h-8 px-2 border border-border bg-background text-foreground rounded-md text-xs focus:outline-none focus:border-primary transition-colors"
                  />
                  <label className="flex items-center gap-1 text-[11px] text-muted-foreground cursor-pointer whitespace-nowrap">
                    <input
                      type="checkbox"
                      checked={line.is_required}
                      onChange={(e) => setDraft(rows.map((r, j) => j === i ? { ...r, is_required: e.target.checked } : r))}
                    />
                    Required
                  </label>
                  <label className="flex items-center gap-1 text-[11px] text-muted-foreground cursor-pointer whitespace-nowrap">
                    <input
                      type="checkbox"
                      checked={line.requires_proof}
                      onChange={(e) => setDraft(rows.map((r, j) => j === i ? { ...r, requires_proof: e.target.checked } : r))}
                    />
                    <ImageIcon size={11} /> Needs photo
                  </label>
                  <button
                    type="button"
                    onClick={() => setDraft(rows.filter((_, j) => j !== i))}
                    className="p-1.5 text-muted-foreground hover:text-red-600 transition-colors shrink-0"
                    aria-label="Remove item"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}

              <div className="flex items-center gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setDraft([...rows, {
                    key: `new-${Date.now()}-${rows.length}`, title: "", requires_proof: false, is_required: true,
                  }])}
                  className="h-7 px-2.5 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground border border-border rounded-md transition-colors"
                >
                  <Plus size={12} /> Add item
                </button>
                <button
                  type="button"
                  onClick={() => { setError(""); save.mutate() }}
                  disabled={save.isPending}
                  className="h-7 px-3 bg-primary text-primary-foreground text-xs font-medium rounded-md hover:opacity-90 disabled:opacity-40 transition-colors"
                >
                  {save.isPending ? "Saving…" : "Save checklist"}
                </button>
              </div>
              {error && <p className="text-[11px] text-red-600 dark:text-red-400">{error}</p>}
            </>
          )}
        </div>
      )}
    </div>
  )
}

interface RoleDraft {
  role_id: string
  slots: number
  amount_aed: string
  notes: string
  responsibilities_override: string
}

export function CohortRolesPanel({ cohort, sessionId, large = false }: {
  cohort: Cohort
  /** Scopes the role list to what this one session actually offers (its own
   *  openings, inherited from the cohort template when it hasn't overridden
   *  them) instead of every active role on the platform — used when this
   *  panel sits under a specific session's own "What this session is
   *  offering" editor, so removing a role there also drops its rate/
   *  responsibilities/checklist card from view here. Omitted on the plain
   *  cohort-wide Roles tab, where showing every role (even ones this cohort
   *  hasn't used yet) is the point — it's where defaults get set up ahead
   *  of time. */
  sessionId?: string
  /** The Cohort Wizard's bigger, collapsible-card look instead of the
   *  compact admin-table one. Same data, same saves — see file docstring. */
  large?: boolean
}) {
  const data = useRolesDraft(cohort, sessionId)
  if (data.isLoading) {
    return <p className={large ? "text-base text-muted-foreground py-1" : "text-xs text-muted-foreground py-1"}>Loading roles…</p>
  }
  return large
    ? <CohortRolesPanelLarge cohort={cohort} sessionId={sessionId} data={data} />
    : <CohortRolesPanelCompact cohort={cohort} sessionId={sessionId} data={data} />
}

type RolesData = ReturnType<typeof useRolesDraft>

function CohortRolesPanelCompact({ cohort, sessionId, data }: { cohort: Cohort; sessionId?: string; data: RolesData }) {
  const { roles, draft, setDraft, sessionRoleIds, isSessionOnlyExtra, save, error, setError } = data
  const rows = draft ?? []

  return (
    <div className="flex flex-col gap-4 py-1">
      <div>
        <p className="text-sm font-semibold text-foreground">Roles for this cohort</p>
        <p className="text-xs text-muted-foreground mt-0.5">
          Rate and responsibilities default from Delivery Settings — override either here, per role, for this cohort only.
          A role's own checklist replaces the general one for that role; leave it empty to keep using the general list.
          {sessionId && " Only showing roles this session is currently offering — remove one above and it drops from here too."}
        </p>
      </div>

      <ChecklistSection
        scope="cohorts" ownerId={cohort.id} programId={cohort.program_id} roleId={null} label="General checklist"
        hint="Applies to any role without its own list"
      />

      <div className="flex flex-col gap-3">
        {rows.map((d, i) => {
          if (sessionRoleIds && !sessionRoleIds.has(d.role_id)) return null
          const role = roles.find((r) => r.id === d.role_id)
          if (!role) return null

          if (isSessionOnlyExtra(d.role_id)) {
            return (
              <div key={d.role_id} className="border border-dashed border-border rounded-xl p-3">
                <span className="text-sm font-semibold text-foreground">{role.name}</span>
                <p className="text-xs text-muted-foreground mt-1">
                  Added just for this session — its rate and slots are set on the session's own offer
                  above. It isn't part of the cohort's shared roles, so there's no shared responsibilities
                  override or checklist to set for it here; add it on the cohort's own Roles tab first if
                  you want that.
                </p>
              </div>
            )
          }

          return (
            <div key={d.role_id} className="border border-border rounded-xl p-3 flex flex-col gap-2.5">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-foreground">{role.name}</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className="flex flex-col gap-1">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                    Rate / session (AED)
                  </span>
                  <input
                    type="number" min={0}
                    placeholder={role.default_rate_aed != null ? `Default: ${role.default_rate_aed}` : "No default set"}
                    value={d.amount_aed}
                    onChange={(e) => setDraft(rows.map((x, j) => j === i ? { ...x, amount_aed: e.target.value } : x))}
                    className="h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm tabular-nums focus:outline-none focus:border-primary transition-colors"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Slots</span>
                  <input
                    type="number" min={1}
                    value={d.slots}
                    onChange={(e) => setDraft(rows.map((x, j) =>
                      j === i ? { ...x, slots: Math.max(1, Number(e.target.value) || 1) } : x))}
                    className="h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm tabular-nums focus:outline-none focus:border-primary transition-colors"
                  />
                </label>
              </div>

              <label className="flex flex-col gap-1">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Responsibilities override
                </span>
                <textarea
                  rows={2}
                  placeholder={role.description ? `Default: ${role.description}` : "No default text set for this role"}
                  value={d.responsibilities_override}
                  onChange={(e) => setDraft(rows.map((x, j) =>
                    j === i ? { ...x, responsibilities_override: e.target.value } : x))}
                  className="px-2 py-1.5 border border-border bg-background text-foreground rounded-lg text-sm resize-y focus:outline-none focus:border-primary transition-colors"
                />
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Notes</span>
                <input
                  placeholder="Optional"
                  value={d.notes}
                  onChange={(e) => setDraft(rows.map((x, j) => j === i ? { ...x, notes: e.target.value } : x))}
                  className="h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm focus:outline-none focus:border-primary transition-colors"
                />
              </label>

              <ChecklistSection
                scope="cohorts" ownerId={cohort.id} programId={cohort.program_id} roleId={role.id} label={`${role.name} checklist`}
                hint="Replaces the general checklist for this role"
              />
            </div>
          )
        })}
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => { setError(""); save.mutate() }}
          disabled={save.isPending}
          className="h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:opacity-90 disabled:opacity-40 transition-colors"
        >
          {save.isPending ? "Saving…" : "Save rates & responsibilities"}
        </button>
      </div>
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}

/** The wizard's collapsible-card look: a role shows just its name, blurb and
 *  rate until you open "Rate, responsibilities & checklist" — matching the
 *  approved design instead of showing every editable field at once. */
function CohortRolesPanelLarge({ cohort, sessionId, data }: { cohort: Cohort; sessionId?: string; data: RolesData }) {
  const { roles, draft, setDraft, sessionRoleIds, isSessionOnlyExtra, save, error, setError } = data
  const [openRoleId, setOpenRoleId] = useState<string | null>(null)
  const rows = draft ?? []
  const label = (text: string): ReactNode => (
    <span style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em" }} className="text-muted-foreground">{text}</span>
  )
  const bigField: React.CSSProperties = { height: 48, padding: "0 16px", borderRadius: 14, fontSize: 17, width: "100%", boxSizing: "border-box" }

  return (
    <div className="flex flex-col" style={{ gap: 28 }}>
      <div className="flex flex-col" style={{ gap: 20 }}>
        <div className="flex items-baseline justify-between flex-wrap" style={{ gap: 16 }}>
          <span style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.09em" }} className="text-muted-foreground">Roles</span>
          <span style={{ fontSize: 15 }} className="text-muted-foreground">
            {sessionId ? "Turn a role off for this day on its own offer above." : "The cohort's default staffing. Every session inherits it."}
          </span>
        </div>

        {rows.map((d, i) => {
          if (sessionRoleIds && !sessionRoleIds.has(d.role_id)) return null
          const role = roles.find((r) => r.id === d.role_id)
          if (!role) return null

          if (isSessionOnlyExtra(d.role_id)) {
            return (
              <div key={d.role_id} style={{ borderRadius: 18, padding: "24px 28px" }} className="border border-dashed border-border">
                <span style={{ fontFamily: OUTFIT, fontSize: 22, fontWeight: 600 }} className="text-foreground">{role.name}</span>
                <p style={{ fontSize: 16, marginTop: 8 }} className="text-muted-foreground">
                  Added just for this session — its rate and slots are set on the session&rsquo;s own offer above.
                  Add it on the cohort&rsquo;s own Roles step first if you want a shared responsibilities override or checklist for it.
                </p>
              </div>
            )
          }

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
                  {sessionId ? "Rate follows the cohort's Roles step." : "Applies to every session, unless one overrides it."}
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
                    <span style={{ fontSize: 14 }} className="text-muted-foreground">Leave as-is to keep the program default.</span>
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
                    scope="cohorts" ownerId={cohort.id} programId={cohort.program_id} roleId={role.id} label={`${role.name} checklist`}
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
          scope="cohorts" ownerId={cohort.id} programId={cohort.program_id} roleId={null} label="General checklist"
          hint="Applies to any role without its own list" large forceOpen
        />
      </div>
    </div>
  )
}
