import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, ExternalLink } from "lucide-react"
import { Link, useParams } from "@tanstack/react-router"
import { getMyJudgeTeamApi, submitMyJudgeScoreApi } from "@/api/competitions"
import { PageHeader, Spinner, EmptyState } from "@/components/ui/primitives"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

const AUTOSAVE_DELAY_MS = 1200

function formatSubmittedAt(iso: string | null): string {
  if (!iso) return ""
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  })
}

/** A judge may score a team across several separate sessions (operator ask,
 * 2026-08-24) — scores autosave on every change (debounced) instead of
 * requiring one explicit "submit" that could lose an interrupted session's
 * work. `submitMyJudgeScoreApi` already upserts, so autosaving is just
 * calling it more often; the visible status line is what makes that safe
 * to trust instead of a silent background write. */
export default function JudgeTeamDetail() {
  const { teamId } = useParams({ strict: false }) as { teamId: string }
  const toast = useToast()
  const queryClient = useQueryClient()

  const { data: detail, isLoading } = useQuery({
    queryKey: ["judge-team-detail", teamId],
    queryFn: () => getMyJudgeTeamApi(teamId),
  })

  const [scores, setScores] = useState<Record<string, number>>({})
  const [bonus, setBonus] = useState(0)
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const autosaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const hydrated = useRef(false)

  useEffect(() => {
    if (!detail) return
    hydrated.current = false
    if (detail.own_score) {
      setScores(detail.own_score.criterion_scores)
      setBonus(detail.own_score.bonus_points)
      setLastSavedAt(detail.own_score.submitted_at)
    } else if (detail.rubric) {
      setScores(Object.fromEntries(detail.rubric.criteria.map((c) => [c.key, 0])))
      setBonus(0)
      setLastSavedAt(null)
    }
    setDirty(false)
    // Defer to the next tick so the hydration above doesn't itself trigger the autosave effect below.
    setTimeout(() => { hydrated.current = true })
  }, [detail])

  const saveMutation = useMutation({
    mutationFn: () => submitMyJudgeScoreApi(teamId, { criterion_scores: scores, bonus_points: bonus }),
    onSuccess: (score) => {
      setLastSavedAt(score.submitted_at)
      setDirty(false)
      queryClient.invalidateQueries({ queryKey: ["judge-teams"] })
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to save score — results may already be published")),
  })

  // Debounced autosave: any score/bonus change while the rubric is loaded
  // schedules a save, restarting the timer on every further keystroke.
  useEffect(() => {
    if (!hydrated.current || !detail?.rubric) return
    setDirty(true)
    if (autosaveTimer.current) clearTimeout(autosaveTimer.current)
    autosaveTimer.current = setTimeout(() => saveMutation.mutate(), AUTOSAVE_DELAY_MS)
    return () => { if (autosaveTimer.current) clearTimeout(autosaveTimer.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scores, bonus])

  if (isLoading) return <Spinner />
  if (!detail) return <EmptyState title="Team not found" />

  const total = Object.values(scores).reduce((s, v) => s + (Number(v) || 0), 0) + (Number(bonus) || 0)

  const saveStatus = saveMutation.isPending
    ? "Saving…"
    : dirty
    ? "Unsaved changes"
    : lastSavedAt
    ? `Saved ${formatSubmittedAt(lastSavedAt)}`
    : null

  return (
    <div className="flex flex-col gap-5 max-w-2xl">
      <Link to="/judge" className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
        <ArrowLeft size={14} /> Teams
      </Link>

      <PageHeader title={detail.team.name} subtitle={detail.team.member_names.join(", ") || "No members yet"} />

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-foreground">Submissions</h2>
        {detail.submissions.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing submitted yet.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {detail.submissions.map((s) => (
              <div key={s.item_id} className="flex items-center justify-between p-3 bg-card border border-border rounded-xl">
                <div>
                  <p className="text-sm font-medium text-foreground">{s.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {s.submitted_url && s.updated_at
                      ? `Submitted ${formatSubmittedAt(s.updated_at)}${s.updated_by_name ? ` by ${s.updated_by_name}` : ""}`
                      : s.status.replace("_", " ")}
                  </p>
                </div>
                {s.submitted_url ? (
                  <a
                    href={s.submitted_url} target="_blank" rel="noreferrer"
                    className="flex items-center gap-1 text-xs font-medium text-primary hover:opacity-80"
                  >
                    Open <ExternalLink size={12} />
                  </a>
                ) : (
                  <span className="text-xs text-muted-foreground">Not submitted</span>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">Score</h2>
          {saveStatus && (
            <span className={`text-xs ${dirty && !saveMutation.isPending ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground"}`}>
              {saveStatus}
            </span>
          )}
        </div>
        {!detail.rubric ? (
          <p className="text-sm text-muted-foreground">No rubric configured for this competition yet — ask ops to set one up.</p>
        ) : (
          <>
            <p className="text-xs text-muted-foreground -mt-1">
              Scores save automatically as you type — pick this team back up any time, nothing is lost.
            </p>
            {detail.rubric.criteria.map((c) => (
              <div key={c.key} className="flex items-center gap-3">
                <label className="flex-1 text-sm text-foreground">{c.label}</label>
                <input
                  type="number" min={0} max={c.max_points}
                  value={scores[c.key] ?? 0}
                  onChange={(e) => setScores((s) => ({ ...s, [c.key]: Number(e.target.value) }))}
                  className="w-20 h-9 px-2 border border-border bg-card text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
                />
                <span className="w-16 text-xs text-muted-foreground">/ {c.max_points}</span>
              </div>
            ))}
            <div className="flex items-center gap-3">
              <label className="flex-1 text-sm text-foreground">Bonus points</label>
              <input
                type="number" min={0}
                value={bonus}
                onChange={(e) => setBonus(Number(e.target.value))}
                className="w-20 h-9 px-2 border border-border bg-card text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
              />
              <span className="w-16 text-xs text-muted-foreground" />
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-border">
              <span className="text-sm font-semibold text-foreground">Total: {total}</span>
              <button
                onClick={() => { if (autosaveTimer.current) clearTimeout(autosaveTimer.current); saveMutation.mutate() }}
                disabled={saveMutation.isPending || !dirty}
                className="h-10 px-5 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
              >
                {saveMutation.isPending ? "Saving…" : "Save now"}
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  )
}
