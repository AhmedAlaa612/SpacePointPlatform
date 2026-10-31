import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, Clock, FileText, Lock, Unlock, XCircle } from "lucide-react"
import {
  getCohortPreQuizStatusApi,
  getSessionPreQuizStatusApi,
  reviewPreQuizAttemptQuestionApi,
  unlockCohortCooldownApi,
  type PhaseTrial,
  type PreSessionQuizAttempt,
  type PreSessionQuizQuestion,
} from "@/api/sessions/pre_session_quiz"
import { ConnectorTableWidget } from "@/components/quiz/ConnectorTableWidget"
import { Button } from "@/components/ui/button"
import { useToast } from "@/components/ui/toast"
import { cn, getErrorMessage } from "@/lib/utils"
import { PreSessionQuizAssignmentBar } from "./PreSessionQuizAssignmentBar"

export function SessionPreQuizOpsPanel({
  sessionId,
  cohortId,
}: {
  sessionId?: string
  cohortId?: string
}) {
  const { data: status, isLoading } = useQuery({
    queryKey: ["pre-quiz-ops-status", sessionId, cohortId],
    queryFn: () => (sessionId ? getSessionPreQuizStatusApi(sessionId) : getCohortPreQuizStatusApi(cohortId!)),
    enabled: Boolean(sessionId || cohortId),
  })

  const attempts = status?.all_attempts ?? []
  const preset = status?.preset
  const totalPending = attempts.reduce((acc, a) => acc + (a.pending_review_count || 0), 0)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-foreground">
              Instructor Pre-Cohort Readiness Pipeline &amp; Submissions
            </h3>
            {totalPending > 0 && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30">
                {totalPending} Pending Review
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Monitor pipeline phase progress, audit active time spent, review written and tricky &ldquo;Other&rdquo; answers, or unlock cooldowns.
          </p>
        </div>
      </div>

      {sessionId ? (
        <PreSessionQuizAssignmentBar scope="sessions" ownerId={sessionId} />
      ) : cohortId ? (
        <PreSessionQuizAssignmentBar scope="cohorts" ownerId={cohortId} />
      ) : null}

      {isLoading ? (
        <p className="text-xs text-muted-foreground py-3">Loading readiness submissions…</p>
      ) : !status?.has_quiz || !preset ? (
        <div className="py-6 text-center text-xs text-muted-foreground border border-dashed border-border rounded-xl">
          No readiness pipeline preset is assigned to this {cohortId ? "cohort" : "session"}.
        </div>
      ) : attempts.length === 0 ? (
        <div className="py-6 text-center text-xs text-muted-foreground border border-dashed border-border rounded-xl">
          Assigned preset: <strong className="text-foreground">{preset.name}</strong> ({preset.phases?.length || 0} phases) — No instructor has started the pipeline yet.
        </div>
      ) : (
        <div className="space-y-4">
          {attempts.map((attempt) => (
            <AttemptReviewCard
              key={attempt.id}
              attempt={attempt}
              questions={preset.questions || []}
              trials={status?.trials ? status.trials.filter((t) => t.attempt_id === attempt.id) : []}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function AttemptReviewCard({
  attempt,
  questions,
  trials,
}: {
  attempt: PreSessionQuizAttempt
  questions: PreSessionQuizQuestion[]
  trials: PhaseTrial[]
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [expanded, setExpanded] = useState(attempt.pending_review_count > 0)
  const [commentByQ, setCommentByQ] = useState<Record<string, string>>({})

  const isLocked =
    attempt.status === "cooldown_locked" ||
    (attempt.locked_until ? new Date(attempt.locked_until).getTime() > Date.now() : false)

  const reviewMut = useMutation({
    mutationFn: ({
      questionId,
      isCorrect,
      comment,
    }: {
      questionId: string
      isCorrect: boolean
      comment?: string
    }) =>
      reviewPreQuizAttemptQuestionApi(attempt.id, {
        question_id: questionId,
        is_correct: isCorrect,
        review_comment: comment || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pre-quiz-ops-status"] })
      qc.invalidateQueries({ queryKey: ["session-pre-quiz-status"] })
      toast.success("Answer review saved and score updated!")
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to save review")),
  })

  const unlockMut = useMutation({
    mutationFn: () => unlockCohortCooldownApi(attempt.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pre-quiz-ops-status"] })
      qc.invalidateQueries({ queryKey: ["session-pre-quiz-status"] })
      toast.success("Cooldown unlocked! Instructor can now retry the phase immediately.")
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to unlock cooldown")),
  })

  const formatSeconds = (sec: number) => {
    const mins = Math.floor(sec / 60)
    const secs = sec % 60
    if (mins === 0) return `${secs}s`
    return `${mins}m ${secs}s`
  }

  return (
    <div className="rounded-2xl border border-border bg-card overflow-hidden shadow-2xs">
      {/* Summary Header */}
      <div className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-muted/20">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold text-foreground">
              {attempt.user_name || "Instructor"}
            </span>

            {/* Status Badge */}
            {attempt.status === "completed" ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
                <CheckCircle2 size={12} />
                Completed (Ready for Delivery)
              </span>
            ) : isLocked ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30">
                <Lock size={12} />
                Cooldown Locked
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-500/30">
                In Progress (Phase {(attempt.current_phase_index ?? 0) + 1})
              </span>
            )}

            {attempt.pending_review_count > 0 && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30">
                {attempt.pending_review_count} Pending Review
              </span>
            )}
          </div>

          <div className="flex items-center gap-3 text-[11px] text-muted-foreground mt-1 flex-wrap">
            <span className="flex items-center gap-1 font-medium">
              <Clock size={12} />
              Total Active Time: {formatSeconds(attempt.total_duration_seconds ?? 0)}
            </span>
            <span>·</span>
            <span>Total Trials: {trials.length}</span>
            {attempt.submitted_at && (
              <>
                <span>·</span>
                <span>Completed: {new Date(attempt.submitted_at).toLocaleString()}</span>
              </>
            )}
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 shrink-0">
          {isLocked && (
            <Button
              size="sm"
              variant="outline"
              disabled={unlockMut.isPending}
              onClick={() => unlockMut.mutate()}
              className="h-8 px-3 text-xs font-bold border-amber-500/40 text-amber-600 dark:text-amber-400 hover:bg-amber-500/10 cursor-pointer flex items-center gap-1.5"
            >
              <Unlock size={13} />
              {unlockMut.isPending ? "Unlocking…" : "Unlock Cooldown Now"}
            </Button>
          )}

          <Button
            size="sm"
            variant="ghost"
            onClick={() => setExpanded((v) => !v)}
            className="h-8 px-3 text-xs font-semibold cursor-pointer"
          >
            {expanded ? "Hide Details" : "View Trials & Answers"}
          </Button>
        </div>
      </div>

      {/* Expanded Trials & Answers */}
      {expanded && (
        <div className="border-t border-border p-4 space-y-5 bg-card">
          {/* Phase Trials History Table */}
          {trials.length > 0 && (
            <div className="flex flex-col gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <Clock size={13} />
                Phase Trials Audit Log ({trials.length})
              </span>

              <div className="overflow-x-auto rounded-xl border border-border">
                <table className="w-full text-left text-xs">
                  <thead className="bg-muted/40 border-b border-border text-[11px] font-bold text-muted-foreground uppercase tracking-wider">
                    <tr>
                      <th className="px-3 py-2">Phase</th>
                      <th className="px-3 py-2">Trial #</th>
                      <th className="px-3 py-2">Time Spent</th>
                      <th className="px-3 py-2">Score</th>
                      <th className="px-3 py-2">Result</th>
                      <th className="px-3 py-2">Timestamp</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {trials.map((t) => (
                      <tr key={t.id} className="hover:bg-muted/20">
                        <td className="px-3 py-2 font-semibold text-foreground">
                          {t.phase_type === "explore_datasheets"
                            ? "Phase 1: Explore Datasheets"
                            : t.phase_type === "subsystem_matching"
                            ? "Phase 2: Subsystem Matching"
                            : `Phase ${t.phase_index + 1}: Quiz`}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">Trial {t.trial_number}</td>
                        <td className="px-3 py-2 font-medium">{formatSeconds(t.duration_seconds)}</td>
                        <td className="px-3 py-2 font-bold text-foreground">
                          {t.score_pct}% ({t.score}/{t.total})
                        </td>
                        <td className="px-3 py-2">
                          {t.passed ? (
                            <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-600 dark:text-emerald-400">
                              <CheckCircle2 size={12} />
                              Passed
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[11px] font-bold text-red-500">
                              <XCircle size={12} />
                              Failed
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground text-[11px]">
                          {new Date(t.submitted_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Submitted Answers Review */}
          <div className="flex flex-col gap-3">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <FileText size={13} />
              Question &amp; Answer Submissions
            </span>

            {questions.map((q, idx) => {
              const ans = attempt.answers?.find((a) => a.question_id === q.id)
              if (!ans) return null

              const currentComment =
                commentByQ[q.id] !== undefined ? commentByQ[q.id] : ans.review_comment ?? ""

              return (
                <div
                  key={q.id}
                  className={cn(
                    "p-3.5 rounded-xl border bg-card space-y-3",
                    ans.status === "pending_review"
                      ? "border-amber-500/50 ring-1 ring-amber-500/20"
                      : "border-border"
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <span className="text-xs font-bold text-primary mr-2">Q{idx + 1}.</span>
                      <span className="text-xs sm:text-sm font-bold text-foreground">{q.title}</span>
                      <p className="text-xs text-muted-foreground mt-0.5 whitespace-pre-wrap">{q.prompt}</p>
                    </div>

                    {ans.status === "correct" ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 shrink-0">
                        Correct
                      </span>
                    ) : ans.status === "pending_review" ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30 shrink-0">
                        Pending Review
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold bg-red-500/15 text-red-500 border border-red-500/30 shrink-0">
                        Incorrect
                      </span>
                    )}
                  </div>

                  {/* Pinout Table Answer */}
                  {q.question_type === "pinout_table" && q.table_config && !ans.chose_other && (
                    <ConnectorTableWidget
                      config={q.table_config}
                      mode="review"
                      selectedCells={ans.selected_cells ?? []}
                    />
                  )}

                  {/* Multiple Choice Answer */}
                  {q.question_type === "mcq" && !ans.chose_other && (
                    <div className="p-2.5 rounded-lg border border-border bg-muted/20 text-xs flex items-center justify-between">
                      <span className="font-semibold text-foreground">
                        Selected Option:{" "}
                        {ans.selected_option_index !== undefined && ans.selected_option_index !== null
                          ? q.options[ans.selected_option_index]?.text || `Option ${ans.selected_option_index + 1}`
                          : "None"}
                      </span>
                    </div>
                  )}

                  {/* Written Scenario Response */}
                  {q.question_type === "written" && (
                    <div className="p-3 rounded-xl border border-primary/25 bg-primary/5 space-y-2.5">
                      <div className="text-xs font-bold text-primary">Instructor Written Diagnostic Answer:</div>
                      <p className="text-xs text-foreground bg-card p-3 rounded-lg border border-border whitespace-pre-wrap">
                        {ans.written_text || "No written response provided."}
                      </p>

                      {q.explanation && (
                        <div className="text-[11px] text-muted-foreground bg-card/60 p-2.5 rounded-lg border border-border/60">
                          <strong className="text-foreground">Ops Grading Guidelines &amp; Rubric:</strong>{" "}
                          {q.explanation}
                        </div>
                      )}

                      <div className="pt-1 flex flex-col sm:flex-row sm:items-center gap-2">
                        <input
                          type="text"
                          value={currentComment}
                          onChange={(e) =>
                            setCommentByQ((prev) => ({ ...prev, [q.id]: e.target.value }))
                          }
                          placeholder="Optional review feedback comment for instructor..."
                          className="flex-1 h-8 px-2.5 rounded-lg border border-border bg-background text-xs text-foreground focus:outline-none focus:border-primary"
                        />
                        <div className="flex items-center gap-2 shrink-0">
                          <Button
                            size="sm"
                            disabled={reviewMut.isPending}
                            onClick={() =>
                              reviewMut.mutate({
                                questionId: q.id,
                                isCorrect: true,
                                comment: currentComment,
                              })
                            }
                            className="h-8 px-3 text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white cursor-pointer"
                          >
                            Approve (Correct)
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={reviewMut.isPending}
                            onClick={() =>
                              reviewMut.mutate({
                                questionId: q.id,
                                isCorrect: false,
                                comment: currentComment,
                              })
                            }
                            className="h-8 px-3 text-xs font-bold border-red-500/40 text-red-500 hover:bg-red-500/10 cursor-pointer"
                          >
                            Mark Incorrect
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Written "Other" Answer on Pinout / Tricky Question */}
                  {ans.chose_other && (
                    <div className="p-3 rounded-xl border border-amber-500/30 bg-amber-500/10 space-y-2.5">
                      <div className="text-xs font-bold text-amber-600 dark:text-amber-400">
                        Instructor Selected &ldquo;Other&rdquo; — Written Explanation:
                      </div>
                      <p className="text-xs text-foreground bg-card p-2.5 rounded-lg border border-border whitespace-pre-wrap">
                        {ans.other_text || "No text provided."}
                      </p>

                      {q.explanation && (
                        <div className="text-[11px] text-muted-foreground bg-card/60 p-2 rounded-lg border border-border/60">
                          <strong className="text-foreground">Expected Discrepancy Reference:</strong>{" "}
                          {q.explanation}
                        </div>
                      )}

                      <div className="pt-1 flex flex-col sm:flex-row sm:items-center gap-2">
                        <input
                          type="text"
                          value={currentComment}
                          onChange={(e) =>
                            setCommentByQ((prev) => ({ ...prev, [q.id]: e.target.value }))
                          }
                          placeholder="Optional review feedback comment..."
                          className="flex-1 h-8 px-2.5 rounded-lg border border-border bg-background text-xs text-foreground focus:outline-none focus:border-primary"
                        />
                        <div className="flex items-center gap-2 shrink-0">
                          <Button
                            size="sm"
                            disabled={reviewMut.isPending}
                            onClick={() =>
                              reviewMut.mutate({
                                questionId: q.id,
                                isCorrect: true,
                                comment: currentComment,
                              })
                            }
                            className="h-8 px-3 text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white cursor-pointer"
                          >
                            Approve (Correct)
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={reviewMut.isPending}
                            onClick={() =>
                              reviewMut.mutate({
                                questionId: q.id,
                                isCorrect: false,
                                comment: currentComment,
                              })
                            }
                            className="h-8 px-3 text-xs font-bold border-red-500/40 text-red-500 hover:bg-red-500/10 cursor-pointer"
                          >
                            Mark Incorrect
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}

                  {ans.reviewed_at && (
                    <div className="text-[11px] text-muted-foreground">
                      Reviewed on {new Date(ans.reviewed_at).toLocaleString()}
                      {ans.review_comment ? ` · "${ans.review_comment}"` : ""}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
