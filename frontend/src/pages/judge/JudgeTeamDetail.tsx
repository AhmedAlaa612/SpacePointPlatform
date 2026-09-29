import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, ChevronDown, ChevronRight, ExternalLink, Lock } from "lucide-react"
import { Link, useParams } from "@tanstack/react-router"
import { getMyJudgeTeamApi, getMyJudgeTeamMissionRunDetailApi, submitMyJudgeScoreApi, type CompetitionMissionRun } from "@/api/competitions"
import { PageHeader, Spinner, EmptyState } from "@/components/ui/primitives"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
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
        <span className="text-base font-medium text-foreground flex-1">{run.title}</span>
        <span className="text-sm text-muted-foreground">{MISSION_RUN_STATUS_LABEL[run.status] ?? run.status}</span>
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
  const [comments, setComments] = useState<Record<string, string>>({})
  const [bonus, setBonus] = useState(0)
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const autosaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const hydrated = useRef(false)

  // Leaf keys this judge actually scores: flat judge criteria by their own
  // key, parents-with-subs by `parent.sub` leaves. Operations-graded
  // criteria are never part of the payload — the backend rejects them.
  const leafKey = (parent: string, sub?: string) => (sub ? `${parent}.${sub}` : parent)

  useEffect(() => {
    if (!detail) return
    hydrated.current = false
    const saved = detail.own_score?.criterion_scores ?? {}
    const savedComments = detail.own_score?.criterion_comments ?? {}
    if (detail.rubric) {
      const next: Record<string, number> = {}
      const nextComments: Record<string, string> = {}
      for (const c of detail.rubric.criteria) {
        if ((c.scored_by ?? "judge") !== "judge") continue
        const subs = c.sub_criteria ?? []
        if (subs.length > 0) {
          for (const s of subs) next[leafKey(c.key, s.key)] = Number(saved[leafKey(c.key, s.key)] ?? 0)
        } else {
          next[c.key] = Number(saved[c.key] ?? 0)
        }
        nextComments[c.key] = savedComments[c.key] ?? ""
      }
      setScores(next)
      setComments(nextComments)
      setBonus(detail.own_score?.bonus_points ?? 0)
      setLastSavedAt(detail.own_score?.submitted_at ?? null)
      setSubmitted(detail.own_score?.submitted ?? false)
    } else if (detail.own_score) {
      setScores(detail.own_score.criterion_scores)
      setComments(detail.own_score.criterion_comments ?? {})
      setBonus(detail.own_score.bonus_points)
      setLastSavedAt(detail.own_score.submitted_at)
      setSubmitted(detail.own_score.submitted)
    }
    setDirty(false)
    // Defer to the next tick so the hydration above doesn't itself trigger the autosave effect below.
    setTimeout(() => { hydrated.current = true })
  }, [detail])

  const saveMutation = useMutation({
    mutationFn: (finalize: boolean) =>
      submitMyJudgeScoreApi(teamId, {
        criterion_scores: scores,
        criterion_comments: Object.fromEntries(
          Object.entries(comments).filter(([, v]) => v.trim()),
        ),
        bonus_points: bonus,
        submitted: finalize,
      }),
    onSuccess: (score, finalize) => {
      setLastSavedAt(score.submitted_at)
      setSubmitted(score.submitted)
      setDirty(false)
      queryClient.invalidateQueries({ queryKey: ["judge-teams"] })
      if (finalize) toast.success("Score submitted — this team is marked as scored")
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
  }, [scores, bonus, comments])

  if (isLoading) return <Spinner />
  if (!detail) return <EmptyState title="Team not found" />

  const judgeCriteria = detail.rubric?.criteria.filter((c) => (c.scored_by ?? "judge") === "judge") ?? []
  const operationsCriteria =
    detail.rubric?.criteria.filter((c) => (c.scored_by ?? "judge") === "operations") ?? []
  const opsScores = detail.ops_criterion_scores ?? {}

  const parentTotal = (criterionKey: string, subs: { key: string }[]) =>
    subs.reduce((s, sub) => s + (Number(scores[leafKey(criterionKey, sub.key)]) || 0), 0)

  // The judge's own total: flat criteria + sub leaves, plus bonus.
  const total =
    judgeCriteria.reduce((s, c) => {
      const subs = c.sub_criteria ?? []
      return s + (subs.length > 0 ? parentTotal(c.key, subs) : Number(scores[c.key]) || 0)
    }, 0) + (Number(bonus) || 0)

  // Submit stays locked until every judge-scored leaf has points — a 0 is
  // treated as "not scored yet", so drafts can sit at zero but the deliberate
  // submit can't go through half-empty without an explicit confirmation.
  const unscoredCount = judgeCriteria.reduce((n, c) => {
    const subs = c.sub_criteria ?? []
    if (subs.length > 0) {
      return n + subs.filter((s) => !(Number(scores[leafKey(c.key, s.key)]) > 0)).length
    }
    return n + (Number(scores[c.key]) > 0 ? 0 : 1)
  }, 0)

  const doSubmit = () => {
    if (autosaveTimer.current) clearTimeout(autosaveTimer.current)
    setConfirmOpen(false)
    saveMutation.mutate(true)
  }

  // Operations contribution for context (read-only — graded by the SpacePoint team).
  const operationsTotal = operationsCriteria.reduce((s, c) => {
    const subs = c.sub_criteria ?? []
    if (subs.length > 0) {
      const parent = Number(opsScores[c.key])
      if (Number.isFinite(parent)) return s + parent
      return s + subs.reduce((ss, sub) => ss + (Number(opsScores[leafKey(c.key, sub.key)]) || 0), 0)
    }
    return s + (Number(opsScores[c.key]) || 0)
  }, 0)

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
    <div className="flex flex-col gap-5 max-w-2xl lg:max-w-none">
      <Link to="/judge" className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
        <ArrowLeft size={14} /> Teams
      </Link>

      <PageHeader title={detail.team.name} subtitle={detail.team.member_names.join(", ") || "No members yet"} />

      {detail.locked && (
        <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl border border-emerald-500/30 bg-emerald-500/10 text-sm text-emerald-700 dark:text-emerald-300">
          <Lock size={14} className="shrink-0 text-emerald-600 dark:text-emerald-400" />
          <span>
            Final submission locked{detail.locked_at ? ` on ${formatSubmittedAt(detail.locked_at)}` : ""}.
          </span>
        </div>
      )}

      <div className="flex flex-col gap-5 lg:grid lg:grid-cols-2 lg:items-start">
        <div className="flex flex-col gap-5 min-w-0 lg:order-2">
      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-bold text-foreground">Submissions</h2>
        {detail.submissions.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing submitted yet.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {detail.submissions.map((s) => (
              <div key={s.item_id} className="flex flex-col gap-2 p-3 bg-card border border-border rounded-xl">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-base font-medium text-foreground">{s.title}</p>
                    <p className="text-sm text-muted-foreground">
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
                        className="flex items-center gap-1 text-sm font-medium text-primary hover:opacity-80"
                      >
                        Open <ExternalLink size={12} />
                      </a>
                    ) : (
                      <span className="text-sm text-muted-foreground">Not submitted</span>
                    )
                  )}
                </div>
                {!s.submission_multi_link && s.submission_field_type === "text" && (
                  s.submitted_text ? (
                    <p className="whitespace-pre-wrap text-base text-foreground pl-1">{s.submitted_text}</p>
                  ) : (
                    <span className="text-sm text-muted-foreground pl-1">Not submitted</span>
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
                          <div key={i} className="flex flex-col gap-0.5 text-sm">
                            {link.label && <span className="text-muted-foreground">{link.label}:</span>}
                            <p className="whitespace-pre-wrap max-w-[320px]">{link.text}</p>
                          </div>
                        ) : (
                          <a
                            key={i} href={ensureAbsoluteUrl(link.url ?? "")} target="_blank" rel="noreferrer"
                            className="flex items-center gap-1.5 text-sm font-medium text-primary hover:opacity-80"
                          >
                            {link.label && <span className="text-muted-foreground">{link.label}:</span>}
                            <span className="truncate max-w-[320px]">{link.url}</span>
                            <ExternalLink size={11} className="shrink-0" />
                          </a>
                        )
                      ))}
                    </div>
                  ) : (
                    <span className="text-sm text-muted-foreground">Not submitted</span>
                  )
                )}
                </div>
              ))}
            </div>
          )}
        </section>

      {detail.mission_runs.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-lg font-bold text-foreground">Design missions</h2>
          <div className="flex flex-col gap-2">
            {detail.mission_runs.map((run) => (
              <MissionRunRow key={run.mission_id} teamId={teamId} run={run} />
            ))}
          </div>
        </section>
      )}

        </div>
        <div className="min-w-0 lg:sticky lg:top-4 lg:order-1">
      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-foreground">Score</h2>
          {saveStatus && (
            <span className={`text-sm ${
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
            <p className="text-sm text-muted-foreground -mt-1">
              Your draft saves automatically as you type, but this team isn't marked scored until you click Submit.
              {operationsCriteria.length > 0 && (
                <> Criteria graded by the SpacePoint team are shown for context and can't be edited.</>
              )}
            </p>
            {judgeCriteria.map((c) => {
              const subs = c.sub_criteria ?? []
              if (subs.length === 0) {
                return (
                  <div key={c.key} className="flex flex-col gap-1.5">
                    <div className="flex items-center gap-3">
                      <label className="flex-1 text-base font-semibold text-foreground">{c.label}</label>
                      <input
                        type="number" min={0} max={c.max_points}
                        value={scores[c.key] ?? 0}
                        onChange={(e) => setScores((s) => ({ ...s, [c.key]: Number(e.target.value) }))}
                        className="w-24 h-11 px-2 border border-border bg-card text-foreground rounded-lg text-base font-semibold text-center focus:outline-none focus:border-primary"
                      />
                    <span className="w-20 text-sm text-muted-foreground">/ {c.max_points}</span>
                  </div>
                  <input
                    value={comments[c.key] ?? ""}
                      onChange={(e) => setComments((prev) => ({ ...prev, [c.key]: e.target.value }))}
                      placeholder="Comment (optional)"
                      className="h-11 px-3 border border-border bg-card text-foreground rounded-lg text-base placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary"
                    />
                  </div>
                )
              }
              const computed = parentTotal(c.key, subs)
              return (
                <div key={c.key} className="flex flex-col gap-1.5 border border-border rounded-xl p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-base font-semibold text-foreground">{c.label}</span>
                    <span className="text-sm text-muted-foreground tabular-nums">
                      <span className="font-bold text-foreground text-base">{computed}</span> / {c.max_points} · auto
                    </span>
                  </div>
                  {subs.map((sub) => (
                      <div key={sub.key} className="flex items-center gap-3 pl-4">
                        <label className="flex-1 text-base font-medium text-muted-foreground">{sub.label}</label>
                      <input
                        type="number" min={0} max={sub.max_points}
                        value={scores[leafKey(c.key, sub.key)] ?? 0}
                        onChange={(e) =>
                          setScores((s) => ({ ...s, [leafKey(c.key, sub.key)]: Number(e.target.value) }))
                        }
                        className="w-24 h-11 px-2 border border-border bg-card text-foreground rounded-lg text-base font-semibold text-center focus:outline-none focus:border-primary"
                      />
                      <span className="w-20 text-sm text-muted-foreground">/ {sub.max_points}</span>
                    </div>
                  ))}
                  <input
                    value={comments[c.key] ?? ""}
                    onChange={(e) => setComments((prev) => ({ ...prev, [c.key]: e.target.value }))}
                    placeholder="Comment for operations (optional)"
                    className="h-11 px-3 border border-border bg-card text-foreground rounded-lg text-base placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary"
                  />
                </div>
              )
            })}
            {operationsCriteria.map((c) => {
              const subs = c.sub_criteria ?? []
              const parentValue = (() => {
                if (subs.length === 0) return Number(opsScores[c.key] ?? 0)
                const parent = Number(opsScores[c.key])
                if (Number.isFinite(parent)) return parent
                return subs.reduce((s, sub) => s + (Number(opsScores[leafKey(c.key, sub.key)]) || 0), 0)
              })()
              return (
                <div
                  key={c.key}
                  title="Graded by SpacePoint team"
                  className="flex flex-col gap-1.5 border border-foreground/25 bg-foreground/[0.04] rounded-xl p-3 cursor-not-allowed"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-base font-semibold text-foreground">{c.label}</span>
                    <span className="text-sm text-muted-foreground tabular-nums">
                      <span className="font-bold text-foreground text-base">{parentValue}</span> / {c.max_points}
                    </span>
                  </div>
                  {subs.length > 0 ? (
                    subs.map((sub) => (
                      <div key={sub.key} className="flex items-center gap-3 pl-4">
                      <label className="flex-1 text-sm font-medium text-foreground">{sub.label}</label>
                        <input
                          type="number" disabled
                          value={Number(opsScores[leafKey(c.key, sub.key)] ?? 0)}
                          title="Graded by SpacePoint team"
                        className="w-24 h-11 px-2 border border-foreground/15 bg-muted/40 text-muted-foreground rounded-lg text-base font-semibold text-center cursor-not-allowed"
                        />
                        <span className="w-20 text-sm text-muted-foreground">/ {sub.max_points}</span>
                      </div>
                    ))
                  ) : (
                    <div className="flex items-center gap-3">
                      <span className="flex-1 text-base text-muted-foreground">Score</span>
                      <input
                        type="number" disabled
                        value={Number(opsScores[c.key] ?? 0)}
                        title="Graded by SpacePoint team"
                        className="w-24 h-11 px-2 border border-foreground/15 bg-muted/40 text-muted-foreground rounded-lg text-base font-semibold text-center cursor-not-allowed"
                      />
                      <span className="w-20 text-sm text-muted-foreground">/ {c.max_points}</span>
                    </div>
                  )}
                </div>
              )
            })}
            <div className="flex items-center gap-3">
              <label className="flex-1 text-base font-semibold text-foreground">Bonus points</label>
              <input
                type="number" min={0}
                value={bonus}
                onChange={(e) => setBonus(Number(e.target.value))}
                className="w-20 h-9 px-2 border border-border bg-card text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
              />
              <span className="w-16 text-xs text-muted-foreground" />
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-border">
              <span className="text-lg font-bold text-foreground">
                Total: {total}
                {operationsCriteria.length > 0 && (
                  <span className="font-normal text-muted-foreground text-sm"> + {operationsTotal} (SpacePoint team)</span>
                )}
              </span>
              <button
                onClick={() => {
                  if (unscoredCount > 0) setConfirmOpen(true)
                  else doSubmit()
                }}
                disabled={saveMutation.isPending}
                className="h-11 px-6 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
              >
                {saveMutation.isPending ? "Submitting…" : "Submit score"}
              </button>
            </div>
            {unscoredCount > 0 && (
              <p className="text-sm text-amber-600 dark:text-amber-400 -mt-1">
                {unscoredCount} {unscoredCount === 1 ? "criterion" : "criteria"} still at 0 — submitting now will ask
                you to confirm.
              </p>
            )}
          </>
        )}
      </section>
        </div>
      </div>

      <Dialog open={confirmOpen} onOpenChange={(v) => !v && setConfirmOpen(false)}>
        <DialogContent className="max-w-md p-6 bg-card border-border">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-foreground">
              Submit with {unscoredCount} unscored {unscoredCount === 1 ? "criterion" : "criteria"}?
            </DialogTitle>
            <p className="text-sm text-muted-foreground mt-1">
              {unscoredCount === 1
                ? "One criterion is still at 0. If that's a deliberate zero, go ahead — otherwise keep scoring."
                : `${unscoredCount} criteria are still at 0. If those are deliberate zeros, go ahead — otherwise keep scoring.`}
            </p>
          </DialogHeader>
          <div className="flex justify-end gap-2 mt-4">
            <button
              onClick={() => setConfirmOpen(false)}
              className="h-10 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
            >
              Keep scoring
            </button>
            <button
              onClick={doSubmit}
              disabled={saveMutation.isPending}
              className="h-10 px-5 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
            >
              {saveMutation.isPending ? "Submitting…" : "Submit anyway"}
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
