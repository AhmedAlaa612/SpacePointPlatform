/** A session's own checklist override (I5-6 follow-up) — the missing rung
 *  on the program -> cohort -> session ladder `CohortRolesPanel`'s
 *  `ChecklistSection` already covers for programs and cohorts. Same
 *  override-not-merge shape, same endpoint family (`checklist-items` with
 *  `scope=sessions`), just one level further down.
 *
 *  Deliberately general-only (no per-role split) — a session override is
 *  for "this one day needs an extra step", not for re-deriving the whole
 *  role structure one day at a time. A role's own checklist still comes
 *  from the cohort's Roles tab.
 *
 *  `large` (2026-09) is the Cohort Wizard's bigger scale — see
 *  CohortRolesPanel.tsx's docstring for why this is a prop, not a fork.
 */
import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ImageIcon, Plus, Trash2 } from "lucide-react"
import type { ChecklistItem } from "@/types/sessions"
import { listChecklistItemsApi, setChecklistItemsApi } from "@/api/sessions/day"
import { useToast } from "@/components/ui/toast"
import { cn, getErrorMessage } from "@/lib/utils"

const OUTFIT = "'Outfit', ui-sans-serif, system-ui, sans-serif"

type DraftLine = { key: string; title: string; requires_proof: boolean; is_required: boolean }

const toDraft = (items: ChecklistItem[]): DraftLine[] =>
  items.map((i) => ({ key: i.id, title: i.title, requires_proof: i.requires_proof, is_required: i.is_required }))

/** What a blank session bucket falls back to, for the preview-before-you-
 *  override display: the cohort's general list, else the program's. */
async function fallbackFor(cohortId: string, programId?: string): Promise<ChecklistItem[]> {
  try {
    const cohortGeneral = await listChecklistItemsApi("cohorts", cohortId, null)
    if (cohortGeneral.length > 0) return cohortGeneral
  } catch {}
  if (programId) {
    try {
      const programGeneral = await listChecklistItemsApi("programs", programId, null)
      if (programGeneral.length > 0) return programGeneral
    } catch {}
  }
  return []
}

export function SessionChecklistPanel({ sessionId, cohortId, programId, large = false }: {
  sessionId: string
  cohortId: string
  programId?: string
  large?: boolean
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [draft, setDraft] = useState<DraftLine[] | null>(null)
  const [isInherited, setIsInherited] = useState(false)
  const [loadingFallback, setLoadingFallback] = useState(false)
  const [error, setError] = useState("")

  const queryKey = ["checklist-items", "sessions", sessionId]
  const { data: items = [], isLoading } = useQuery({
    queryKey, queryFn: () => listChecklistItemsApi("sessions", sessionId, null),
  })

  useEffect(() => {
    setDraft(null)
    setIsInherited(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  useEffect(() => {
    if (draft !== null || isLoading) return
    if (items.length > 0) {
      setDraft(toDraft(items))
      setIsInherited(false)
    } else {
      setLoadingFallback(true)
      fallbackFor(cohortId, programId)
        .then((fb) => { setDraft(toDraft(fb)); setIsInherited(fb.length > 0) })
        .catch(() => { setDraft([]); setIsInherited(false) })
        .finally(() => setLoadingFallback(false))
    }
  }, [items, isLoading, draft, cohortId, programId])

  const save = useMutation({
    mutationFn: () => setChecklistItemsApi(
      "sessions", sessionId,
      (draft ?? []).map((l, i) => ({
        title: l.title, requires_proof: l.requires_proof, is_required: l.is_required, sort_order: i + 1,
      })),
      null,
    ),
    onSuccess: () => { toast.success("Session checklist saved"); setError(""); setIsInherited(false); qc.invalidateQueries({ queryKey }) },
    onError: (e: any) => setError(getErrorMessage(e, "Could not save this checklist")),
  })

  const rows = draft ?? []
  const loading = isLoading || loadingFallback || draft === null

  if (!large) {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-semibold text-foreground">This session&rsquo;s checklist</p>
          <span className={
            "text-[10px] font-semibold px-1.5 py-0.5 rounded-full border shrink-0 " +
            (isInherited ? "bg-muted text-muted-foreground border-border" : "bg-primary/10 text-primary border-primary/20")
          }>
            {isInherited ? "Inherited from cohort" : rows.length > 0 ? "Overridden for this session" : "Inherited from cohort"}
          </span>
        </div>
        <p className="text-xs text-muted-foreground -mt-1.5">
          Empty means this session uses the cohort&rsquo;s checklist. Save anything here and it replaces the
          cohort&rsquo;s list for this session only.
        </p>

        {loading ? (
          <p className="text-xs text-muted-foreground">Loading&hellip;</p>
        ) : (
          <>
            {isInherited && rows.length > 0 && (
              <p className="text-[11px] text-muted-foreground italic">
                Showing the cohort&rsquo;s checklist. Edit and save to override it for just this session.
              </p>
            )}
            {rows.length === 0 && (
              <p className="text-xs text-muted-foreground">Nothing above this session — falls back to the program.</p>
            )}
            {rows.map((line, i) => (
              <div key={line.key} className="flex items-center gap-2 flex-wrap">
                <input
                  value={line.title}
                  placeholder="Checklist item"
                  onChange={(e) => setDraft(rows.map((r, j) => j === i ? { ...r, title: e.target.value } : r))}
                  className="flex-1 min-w-[10rem] h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm focus:outline-none focus:border-primary transition-colors"
                />
                <label className="flex items-center gap-1 text-[11px] text-muted-foreground cursor-pointer whitespace-nowrap">
                  <input
                    type="checkbox" checked={line.is_required}
                    onChange={(e) => setDraft(rows.map((r, j) => j === i ? { ...r, is_required: e.target.checked } : r))}
                  />
                  Required
                </label>
                <label className="flex items-center gap-1 text-[11px] text-muted-foreground cursor-pointer whitespace-nowrap">
                  <input
                    type="checkbox" checked={line.requires_proof}
                    onChange={(e) => setDraft(rows.map((r, j) => j === i ? { ...r, requires_proof: e.target.checked } : r))}
                  />
                  <ImageIcon size={11} /> Needs photo
                </label>
                <button
                  type="button"
                  onClick={() => setDraft(rows.filter((_, j) => j !== i))}
                  className="p-1.5 text-muted-foreground hover:text-red-600 transition-colors shrink-0"
                  aria-label="Remove item"
                ><Trash2 size={13} /></button>
              </div>
            ))}

            <div className="flex items-center gap-2 pt-1">
              <button
                type="button"
                onClick={() => setDraft([...rows, { key: `new-${Date.now()}-${rows.length}`, title: "", requires_proof: false, is_required: true }])}
                className="h-8 px-2.5 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground border border-border rounded-lg transition-colors"
              ><Plus size={12} /> Add item</button>
              <button
                type="button"
                onClick={() => { setError(""); save.mutate() }}
                disabled={save.isPending}
                className="h-8 px-3 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:opacity-90 disabled:opacity-40 transition-colors"
              >{save.isPending ? "Saving…" : "Save checklist"}</button>
            </div>
            {error && <p className="text-[11px] text-red-600 dark:text-red-400">{error}</p>}
          </>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col" style={{ gap: 20 }}>
      <div className="flex items-baseline justify-between" style={{ gap: 16 }}>
        <span style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.09em" }} className="text-muted-foreground">Daily checklist</span>
        <span
          style={{ height: 28, padding: "0 12px", borderRadius: 999, fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em" }}
          className={cn("inline-flex items-center border", isInherited || rows.length === 0 ? "bg-muted text-muted-foreground border-border" : "bg-primary/10 text-primary border-primary/20")}
        >
          {isInherited || rows.length === 0 ? "Inherited from cohort" : "Overridden for this session"}
        </span>
      </div>
      <p style={{ fontSize: 15 }} className="text-muted-foreground -mt-2">
        Empty means this session uses the cohort&rsquo;s checklist. Save anything here and it replaces the cohort&rsquo;s list for this session only.
      </p>

      {loading ? (
        <p style={{ fontSize: 16 }} className="text-muted-foreground">Loading&hellip;</p>
      ) : (
        <>
          {isInherited && rows.length > 0 && (
            <p style={{ fontSize: 14 }} className="text-muted-foreground italic">
              Showing the cohort&rsquo;s checklist. Edit and save to override it for just this session.
            </p>
          )}
          {rows.length === 0 && (
            <p style={{ fontSize: 15 }} className="text-muted-foreground">Nothing above this session &mdash; falls back to the program.</p>
          )}
          {rows.map((line, i) => (
            <div key={line.key} style={{ padding: "18px 22px", borderRadius: 16 }} className="flex items-center gap-4 border border-border bg-card">
              <input
                value={line.title}
                placeholder="Checklist item"
                onChange={(e) => setDraft(rows.map((r, j) => j === i ? { ...r, title: e.target.value } : r))}
                style={{ fontSize: 17, height: 40, flex: 1 }}
                className="min-w-[10rem] px-3 border border-border bg-background text-foreground rounded-xl focus:outline-none focus:border-primary transition-colors"
              />
              <label className="flex items-center gap-1.5 text-muted-foreground cursor-pointer whitespace-nowrap" style={{ fontSize: 14 }}>
                <input
                  type="checkbox" checked={line.is_required}
                  onChange={(e) => setDraft(rows.map((r, j) => j === i ? { ...r, is_required: e.target.checked } : r))}
                />
                Required
              </label>
              <label className="flex items-center gap-1.5 text-muted-foreground cursor-pointer whitespace-nowrap" style={{ fontSize: 14 }}>
                <input
                  type="checkbox" checked={line.requires_proof}
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
              onClick={() => setDraft([...rows, { key: `new-${Date.now()}-${rows.length}`, title: "", requires_proof: false, is_required: true }])}
              style={{ height: 44, padding: "0 20px", borderRadius: 14, fontSize: 15, fontWeight: 500 }}
              className="flex items-center gap-2 text-muted-foreground hover:text-foreground hover:bg-muted border border-dashed border-border transition-colors"
            ><Plus size={15} /> Add item</button>
            <button
              type="button"
              onClick={() => { setError(""); save.mutate() }}
              disabled={save.isPending}
              style={{ height: 44, padding: "0 22px", borderRadius: 14, fontFamily: OUTFIT, fontSize: 15, fontWeight: 600 }}
              className="bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-40 transition-opacity"
            >{save.isPending ? "Saving…" : "Save checklist"}</button>
          </div>
          {error && <p style={{ fontSize: 14 }} className="text-red-600 dark:text-red-400">{error}</p>}
        </>
      )}
    </div>
  )
}
