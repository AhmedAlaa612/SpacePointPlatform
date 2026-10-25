import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  getSessionPreQuizStatusApi,
  reviewPreQuizAttemptQuestionApi,
  type PreSessionQuizAttempt,
  type PreSessionQuizQuestion,
} from "@/api/sessions/pre_session_quiz"
import { ConnectorTableWidget } from "@/components/quiz/ConnectorTableWidget"
import { Button } from "@/components/ui/button"
import { useToast } from "@/components/ui/toast"
import { cn, getErrorMessage } from "@/lib/utils"
import { PreSessionQuizAssignmentBar } from "./PreSessionQuizAssignmentBar"

export function SessionPreQuizOpsPanel({ sessionId }: { sessionId: string }) {
  const { data: status, isLoading } = useQuery({
    queryKey: ["session-pre-quiz-status", sessionId],
    queryFn: () => getSessionPreQuizStatusApi(sessionId),
  })

  const attempts = status?.all_attempts ?? []
  const preset = status?.preset
  const totalPending = attempts.reduce((acc, a) => acc + a.pending_review_count, 0)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-foreground">
              Pre-Session Instructor Quiz &amp; Submissions
            </h3>
            {totalPending > 0 && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30">
                {totalPending} Pending Review
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            View instructor pre-session quiz scores and review any &ldquo;Other&rdquo; written explanations.
          </p>
        </div>
      </div>

      <PreSessionQuizAssignmentBar scope="sessions" ownerId={sessionId} />

      {isLoading ? (
        <p className="text-xs text-muted-foreground py-3">Loading quiz submissions…</p>
      ) : !status?.has_quiz || !preset ? (
        <div className="py-6 text-center text-xs text-muted-foreground border border-dashed border-border rounded-xl">
          No pre-session quiz is assigned to this session.
        </div>
      ) : attempts.length === 0 ? (
        <div className="py-6 text-center text-xs text-muted-foreground border border-dashed border-border rounded-xl">
          Assigned preset: <strong className="text-foreground">{preset.name}</strong> ({preset.questions.length} Qs) — No instructor has submitted the quiz yet.
        </div>
      ) : (
        <div className="space-y-3">
          {attempts.map((attempt) => (
            <AttemptReviewCard
              key={attempt.id}
              attempt={attempt}
              questions={preset.questions}
              sessionId={sessionId}
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
  sessionId,
}: {
  attempt: PreSessionQuizAttempt
  questions: PreSessionQuizQuestion[]
  sessionId: string
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [expanded, setExpanded] = useState(attempt.pending_review_count > 0)
  const [commentByQ, setCommentByQ] = useState<Record<string, string>>({})

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
      qc.invalidateQueries({ queryKey: ["session-pre-quiz-status", sessionId] })
      toast.success("Answer review saved and score updated!")
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to save review")),
  })

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      {/* Summary Row */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full px-4 py-3 flex items-center justify-between gap-3 hover:bg-muted/40 transition-colors text-left cursor-pointer"
      >
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs sm:text-sm font-bold text-foreground truncate">
              {attempt.user_name || "Instructor"}
            </span>
            <span className="text-[11px] font-medium text-primary">
              {expanded ? "(Hide Details)" : "(View Answers)"}
            </span>
          </div>
          {attempt.submitted_at && (
            <p className="text-[11px] text-muted-foreground">
              Submitted {new Date(attempt.submitted_at).toLocaleString()}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {attempt.pending_review_count > 0 && (
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30">
              {attempt.pending_review_count} Pending Review
            </span>
          )}
          <span className="px-2.5 py-1 rounded-lg bg-muted text-xs font-bold text-foreground">
            Score: {attempt.final_score} / {attempt.total_questions}
          </span>
        </div>
      </button>

      {/* Expanded Questions & Review Controls */}
      {expanded && (
        <div className="border-t border-border p-4 space-y-4 bg-muted/10">
          {questions.map((q, idx) => {
            const ans = attempt.answers.find((a) => a.question_id === q.id)
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
                    : "border-border",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <span className="text-xs font-bold text-primary mr-2">Q{idx + 1}.</span>
                    <span className="text-xs sm:text-sm font-bold text-foreground">{q.title}</span>
                    <p className="text-xs text-muted-foreground mt-0.5">{q.prompt}</p>
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

                {/* Written "Other" Answer & Ops Review Controls */}
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
                        <strong className="text-foreground">Expected Explanation Reference:</strong>{" "}
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
                        placeholder="Optional review feedback comment for the instructor..."
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
      )}
    </div>
  )
}
