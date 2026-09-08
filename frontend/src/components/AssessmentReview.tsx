import { useQuery } from "@tanstack/react-query"
import { CheckCircle2 } from "lucide-react"
import { Modal } from "@/pages/admin/components/common"
import { Spinner } from "@/components/ui/primitives"
import {
  getAttemptReviewForCohortCallApi,
  getAttemptReviewForSessionApi,
} from "@/api/instructor_assessment"
import type { AttemptQuestionReview } from "@/types/instructor_assessment"

/** Per-question assessment review — what got picked, what was correct, and
 *  why (2026-09). Shared between the instructor's own post-submit results
 *  page (`pages/instructors/TakeAssessment.tsx`) and the ops "view answers"
 *  drill-down from the staffing screens, so there's one rendering, not two. */
export function QuestionReviewList({ questions }: { questions: AttemptQuestionReview[] }) {
  return (
    <div className="flex flex-col gap-3">
      {questions.map((q, i) => (
        <div
          key={q.question_id}
          className={`rounded-2xl border p-4 flex flex-col gap-2 text-left ${
            q.is_correct ? "border-border bg-card" : "border-red-500/30 bg-red-500/5"
          }`}
        >
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] font-mono text-muted-foreground">Q{i + 1}</span>
            <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border border-border text-muted-foreground">
              {q.category}
            </span>
            {q.is_correct ? (
              <span className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 size={10} /> Correct
              </span>
            ) : (
              <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full bg-red-500 text-white">
                Incorrect
              </span>
            )}
          </div>

          <p className="text-sm font-medium leading-snug">{q.prompt}</p>
          {q.selected_index === null && (
            <p className="text-xs text-muted-foreground italic">Left unanswered.</p>
          )}

          <div className="flex flex-col gap-1">
            {q.options.map((text, oi) => {
              const isSelected = q.selected_index === oi
              const isCorrectOption = q.correct_index === oi
              return (
                <div
                  key={oi}
                  className={`px-3 py-1.5 rounded-lg text-xs flex items-center gap-2 ${
                    isCorrectOption
                      ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 font-medium"
                      : isSelected
                      ? "bg-red-500/10 text-red-700 dark:text-red-400"
                      : "text-muted-foreground"
                  }`}
                >
                  <span className="w-4 h-4 rounded flex items-center justify-center text-[10px] font-semibold shrink-0 bg-muted">
                    {String.fromCharCode(65 + oi)}
                  </span>
                  <span className="flex-1">{text}</span>
                  {isCorrectOption && <span className="text-[10px] shrink-0">Correct answer</span>}
                  {isSelected && !isCorrectOption && <span className="text-[10px] shrink-0">Their answer</span>}
                </div>
              )
            })}
          </div>

          {q.rationale && (
            <p className="text-xs text-muted-foreground border-t border-border pt-2 mt-1">{q.rationale}</p>
          )}
        </div>
      ))}
    </div>
  )
}

/** Ops-facing "view answers" drill-down from a staffing screen — either
 *  scope resolves to the same review; which one to call depends on which id
 *  the caller already has on hand (a single-session roster only has
 *  `session_id`, a cohort-call applicant table already has `cohort_call_id`
 *  directly). */
export function AssessmentReviewModal({ title, onClose, scope, id, userId }: {
  title: string
  onClose: () => void
  scope: "session" | "cohort-call"
  id: string
  userId: string
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["attempt-review", scope, id, userId],
    queryFn: () => scope === "session"
      ? getAttemptReviewForSessionApi(id, userId)
      : getAttemptReviewForCohortCallApi(id, userId),
    retry: false,
  })

  return (
    <Modal title={title} onClose={onClose} maxWidth="max-w-2xl">
      {isLoading ? (
        <Spinner />
      ) : isError || !data ? (
        <p className="text-sm text-muted-foreground py-8 text-center">
          No submitted assessment found for this opportunity.
        </p>
      ) : (
        <div className="flex flex-col gap-4 max-h-[70vh] overflow-y-auto pr-1">
          <div className="flex items-center justify-between px-1">
            <span className="text-sm text-muted-foreground">Score</span>
            <span className="font-display text-lg font-bold">{data.score} / {data.total}</span>
          </div>
          <QuestionReviewList questions={data.questions} />
        </div>
      )}
    </Modal>
  )
}
