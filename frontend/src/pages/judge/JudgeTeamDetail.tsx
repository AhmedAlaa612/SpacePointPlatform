import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, ChevronDown, ChevronRight, ExternalLink, Lock } from "lucide-react"
import { Link, useParams } from "@tanstack/react-router"
import { getMyJudgeTeamApi, getMyJudgeTeamMissionRunDetailApi, submitMyJudgeScoreApi, type CompetitionMissionRun } from "@/api/competitions"
import { PageHeader, Spinner, EmptyState } from "@/components/ui/primitives"
import { useToast } from "@/components/ui/toast"
import { ensureAbsoluteUrl, getErrorMessage } from "@/lib/utils"
import { DesignRunDetail } from "@/pages/lms-authoring/components/DesignRunDetail"

const AUTOSAVE_DELAY_MS = 1200

function formatSubmittedAt(iso: string | null): string {
  if (!iso) return ""
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  })
}

const MISSION_RUN_STATUS_LABEL: Record<string, string> = {
  not_started: "Not started", in_progress: "In progress", submitted: "Submitted", passed: "Passed", failed: "Failed",
}

/** One team mission run, in the judge's own view (Phase 3, 2026-09) — a
 * thin wrapper around `DesignRunDetail`, pointed at the judge-scoped
 * fetch (`getMyJudgeTeamMissionRunDetailApi`) instead of the ops one it
 * defaults to, so this never touches the ops/instructor endpoint or its
 * permission check. Expand-on-click, same interaction ops already uses
 * for the same component elsewhere. */
function MissionRunRow({ teamId, run }: { teamId: string; run: CompetitionMissionRun }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="border border-border rounded-xl overflow-hidden">
      <button
        onClick={() => run.attempt_id && setExpanded((v) => !v)}
        disabled={!run.attempt_id}
        className="w-full flex items-center gap-2 p-3 hover:bg-muted/40 transition-colors text-left disabled:cursor-not-allowed disabled:hover:bg-transparent"
      >
        {run.attempt_id ? (
          expanded ? <ChevronDown size={14} className="shrink-0 text-muted-foreground" /> : <ChevronRight size={14} className="shrink-0 text-muted-foreground" />
        ) : (
          <span className="w-3.5 shrink-0" />
        )}
        <span className="text-sm font-medium text-foreground flex-1">{run.title}</span>
        <span className="text-xs text-muted-foreground">{MISSION_RUN_STATUS_LABEL[run.status] ?? run.status}</span>
      </button>
      {expanded && run.attempt_id && (
        <DesignRunDetail
          attemptId={run.attempt_id}
          fetchFn={(attemptId) => getMyJudgeTeamMissionRunDetailApi(teamId, attemptId)}
          queryKeySuffix="judge"
        />
      )}
    </div>
  )
}

/** Autosave keeps a draft around across sessions (debounced, same as
 * before) — but a draft never counts as "scored" (2026-08-27): only the
 * explicit Submit click sets `submitted`, which is what `already_scored`,
 * the leaderboard, and `judges_scored` actually read. Autosave always
 * sends `submitted: false`; the backend ratchets the flag forward only,
 * so it can never undo a deliberate submit either. */
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
  const [submitted, setSubmitted] = useState(false)
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
      setSubmitted(detail.own_score.submitted)
    } else if (detail.rubric) {
      setScores(Object.fromEntries(detail.rubric.criteria.map((c) => [c.key, 0])))
      setBonus(0)
      setLastSavedAt(null)
      setSubmitted(false)
    }
    setDirty(false)
    // Defer to the next tick so the hydration above doesn't itself trigger the autosave effect below.
    setTimeout(() => { hydrated.current = true })
  }, [detail])

  const saveMutation = useMutation({
    mutationFn: (finalize: boolean) =>
      submitMyJudgeScoreApi(teamId, { criterion_scores: scores, bonus_points: bonus, submitted: finalize }),
    onSuccess: (score) => {
      setLastSavedAt(score.submitted_at)
      setSubmitted(score.submitted)
      setDirty(false)
      queryClient.invalidateQueries({ queryKey: ["judge-teams"] })
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to save score — results may already be published")),
  })

  // Debounced autosave of the draft only — never marks the team scored.
  useEffect(() => {
    if (!hydrated.current || !detail?.rubric) return
    setDirty(true)
    if (autosaveTimer.current) clearTimeout(autosaveTimer.current)
    autosaveTimer.current = setTimeout(() => saveMutation.mutate(false), AUTOSAVE_DELAY_MS)
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
    : submitted && lastSavedAt
    ? `Submitted ${formatSubmittedAt(lastSavedAt)}`
    : lastSavedAt
    ? `Draft saved ${formatSubmittedAt(lastSavedAt)}`
    : null

  return (
    <div className="flex flex-col gap-5 max-w-2xl">
      <Link to="/judge" className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
        <ArrowLeft size={14} /> Teams
      </Link>

      <PageHeader title={detail.team.name} subtitle={detail.team.member_names.join(", ") || "No members yet"} />

      {detail.locked && (
        <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl border border-emerald-500/30 bg-emerald-500/10 text-xs text-emerald-700 dark:text-emerald-300">
          <Lock size={14} className="shrink-0 text-emerald-600 dark:text-emerald-400" />
          <span>
            Final submission locked{detail.locked_at ? ` on ${formatSubmittedAt(detail.locked_at)}` : ""}.
          </span>
        </div>
      )}

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-foreground">Submissions</h2>
        {detail.submissions.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing submitted yet.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {detail.submissions.map((s) => (
              <div key={s.item_id} className="flex flex-col gap-2 p-3 bg-card border border-border rounded-xl">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-foreground">{s.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {(s.submitted_url || s.submitted_text) && s.updated_at
                        ? `Submitted ${formatSubmittedAt(s.updated_at)}${s.updated_by_name ? ` by ${s.updated_by_name}` : ""}`
                        : s.status.replace("_", " ")}
                    </p>
                  </div>
                  {/* A plain (non-multi) item can itself be a text field
                      (2026-09-16) — rendered below the header, not as an
                      "Open" button, so it's here only for the link case. */}
                  {!s.submission_multi_link && s.submission_field_type !== "text" && (
                    s.submitted_url ? (
                      <a
                        href={ensureAbsoluteUrl(s.submitted_url)} target="_blank" rel="noreferrer"
                        className="flex items-center gap-1 text-xs font-medium text-primary hover:opacity-80"
                      >
                        Open <ExternalLink size={12} />
                      </a>
                    ) : (
                      <span className="text-xs text-muted-foreground">Not submitted</span>
                    )
                  )}
                </div>
                {!s.submission_multi_link && s.submission_field_type === "text" && (
                  s.submitted_text ? (
                    <p className="whitespace-pre-wrap text-sm text-foreground pl-1">{s.submitted_text}</p>
                  ) : (
                    <span className="text-xs text-muted-foreground pl-1">Not submitted</span>
                  )
                )}
                {/* Multi-field submission (2026-09-14, text fields added
                    2026-09-16) — every labeled field grouped under the one
                    submission, instead of a single "Open" button for a bare
                    url. A text field renders as plain (possibly multi-line)
                    text rather than a broken link. */}
                {s.submission_multi_link && (
                  s.submitted_links && s.submitted_links.length > 0 ? (
                    <div className="flex flex-col gap-1 pl-1">
                      {s.submitted_links.map((link, i) => (
                        link.text ? (
                          <div key={i} className="flex flex-col gap-0.5 text-xs">
                            {link.label && <span className="text-muted-foreground">{link.label}:</span>}
                            <p className="whitespace-pre-wrap max-w-[320px]">{link.text}</p>
                          </div>
                        ) : (
                          <a
                            key={i} href={ensureAbsoluteUrl(link.url ?? "")} target="_blank" rel="noreferrer"
                            className="flex items-center gap-1.5 text-xs font-medium text-primary hover:opacity-80"
                          >
                            {link.label && <span className="text-muted-foreground">{link.label}:</span>}
                            <span className="truncate max-w-[320px]">{link.url}</span>
                            <ExternalLink size={11} className="shrink-0" />
                          </a>
                        )
                      ))}
                    </div>
                  ) : (
                    <span className="text-xs text-muted-foreground">Not submitted</span>
                  )
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {detail.mission_runs.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold text-foreground">Design missions</h2>
          <div className="flex flex-col gap-2">
            {detail.mission_runs.map((run) => (
              <MissionRunRow key={run.mission_id} teamId={teamId} run={run} />
            ))}
          </div>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">Score</h2>
          {saveStatus && (
            <span className={`text-xs ${
              dirty && !saveMutation.isPending
                ? "text-amber-600 dark:text-amber-400"
                : submitted
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-muted-foreground"
            }`}>
              {saveStatus}
            </span>
          )}
        </div>
        {!detail.rubric ? (
          <p className="text-sm text-muted-foreground">No rubric configured for this competition yet — ask ops to set one up.</p>
        ) : (
          <>
            <p className="text-xs text-muted-foreground -mt-1">
              Your draft saves automatically as you type, but this team isn't marked scored until you click Submit.
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
                onClick={() => {
                  if (autosaveTimer.current) clearTimeout(autosaveTimer.current)
                  saveMutation.mutate(true)
                }}
                disabled={saveMutation.isPending}
                className="h-10 px-5 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
              >
                {saveMutation.isPending ? "Submitting…" : "Submit score"}
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  )
}
