/** The Roles tab (2026-08-28): responsibilities, rate and checklist together,
 *  per role, for one cohort — replacing the old rate-only block that used to
 *  sit at the top of the Staffing tab.
 *
 *  Rate and responsibilities share the same `cohort_openings` row (one per
 *  cohort+role) and save together through the existing openings-defaults
 *  endpoint. Checklist is a separate bucket entirely — its own endpoint,
 *  its own save — because a role can have zero, one, or many items and
 *  editing it is a whole-list replace, not a single-row field.
 */
import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronDown, ChevronRight, ImageIcon, Plus, Trash2 } from "lucide-react"
import type { Cohort } from "@/types/sessions"
import type { ChecklistItem } from "@/types/sessions"
import { getDeliveryRolesApi, getCohortOpeningsApi, getOpeningsApi, setCohortOpeningsApi } from "@/api/sessions/openings"
import { listChecklistItemsApi, setChecklistItemsApi } from "@/api/sessions/day"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

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

async function fetchFallbackChecklistItems(
  cohortId: string,
  programId?: string,
  roleId?: string | null,
): Promise<ChecklistItem[]> {
  if (roleId) {
    try {
      const cohortGeneral = await listChecklistItemsApi("cohorts", cohortId, null)
      if (cohortGeneral.length > 0) return cohortGeneral
    } catch {}

    if (programId) {
      try {
        const progRole = await listChecklistItemsApi("programs", programId, roleId)
        if (progRole.length > 0) return progRole
      } catch {}

      try {
        const progGeneral = await listChecklistItemsApi("programs", programId, null)
        if (progGeneral.length > 0) return progGeneral
      } catch {}
    }
  } else if (programId) {
    try {
      const progGeneral = await listChecklistItemsApi("programs", programId, null)
      if (progGeneral.length > 0) return progGeneral
    } catch {}
  }
  return []
}

/** One checklist bucket's editor — general (roleId omitted) or one role's
 *  own list. Lazy: only fetches once expanded. */
function ChecklistSection({
  cohortId, programId, roleId, label, hint,
}: { cohortId: string; programId?: string; roleId: string | null; label: string; hint: string }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<ChecklistDraftLine[] | null>(null)
  const [isInherited, setIsInherited] = useState(false)
  const [isLoadingFallback, setIsLoadingFallback] = useState(false)
  const [error, setError] = useState("")

  const queryKey = ["checklist-items", "cohorts", cohortId, roleId ?? "general"]
  const { data: items = [], isLoading } = useQuery({
    queryKey,
    queryFn: () => listChecklistItemsApi("cohorts", cohortId, roleId),
    enabled: open,
  })

  useEffect(() => {
    if (!open || draft !== null || isLoading) return

    if (items.length > 0) {
      setDraft(toDraftLines(items))
      setIsInherited(false)
    } else {
      setIsLoadingFallback(true)
      fetchFallbackChecklistItems(cohortId, programId, roleId)
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
  }, [open, isLoading, items, draft, cohortId, programId, roleId])

  const save = useMutation({
    mutationFn: () => setChecklistItemsApi(
      "cohorts", cohortId,
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

  return (
    <div className="border border-dashed border-border rounded-lg">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
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

export function CohortRolesPanel({ cohort, sessionId }: {
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
}) {
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

  const rows = draft ?? []

  const save = useMutation({
    mutationFn: () => setCohortOpeningsApi({
      cohortId: cohort.id,
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
      qc.invalidateQueries({ queryKey: ["cohort-openings-defaults", cohort.id] })
    },
    onError: (e: any) => setError(getErrorMessage(e, "Could not save roles")),
  })

  if (isLoading || sessionLoading || draft === null) {
    return <p className="text-xs text-muted-foreground py-1">Loading roles…</p>
  }

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
        cohortId={cohort.id} programId={cohort.program_id} roleId={null} label="General checklist"
        hint="Applies to any role without its own list"
      />

      <div className="flex flex-col gap-3">
        {rows.map((d, i) => {
          // `i` stays the true index into `rows` (the full, unfiltered
          // draft) even though a session-scoped view skips rendering some
          // of them — every onChange below writes back through that same
          // index, so a hidden role's draft entry is never touched.
          if (sessionRoleIds && !sessionRoleIds.has(d.role_id)) return null
          const role = roles.find((r) => r.id === d.role_id)
          if (!role) return null
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
                cohortId={cohort.id} programId={cohort.program_id} roleId={role.id} label={`${role.name} checklist`}
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
