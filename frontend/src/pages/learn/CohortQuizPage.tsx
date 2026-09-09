import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "@tanstack/react-router"
import { isAxiosError } from "axios"
import { CheckCircle2, Clock, Trophy, XCircle } from "lucide-react"
import { getCohortQuizResultApi, startCohortQuizApi, submitCohortQuizApi } from "@/api/cohort_quiz"
import type { CohortQuizAnswerInput } from "@/types/cohort_quiz"
import { Spinner } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

/** Visible per-question countdown, drift-free (`Date.now()`-based, not a
 * decrementing counter) — same shape as `GamePlay.tsx`'s `Countdown`, the
 * only other place in the LMS with a per-question timer. `onExpire` here
 * auto-advances with a blank answer instead of locking for a live reveal
 * (this is solo, not a broadcast game). */
function Countdown({ seconds, questionKey, onExpire }: { seconds: number; questionKey: string; onExpire: () => void }) {
  const [remaining, setRemaining] = useState(seconds)
  const firedRef = useRef(false)

  useEffect(() => {
    setRemaining(seconds)
    firedRef.current = false
    const start = Date.now()
    const id = setInterval(() => {
      const left = Math.max(0, seconds - Math.floor((Date.now() - start) / 1000))
      setRemaining(left)
      if (left === 0 && !firedRef.current) {
        firedRef.current = true
        onExpire()
        clearInterval(id)
      }
    }, 250)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [questionKey, seconds])

  return (
    <span className={`font-display text-xl font-extrabold ${remaining <= 5 ? "text-destructive" : "text-foreground"}`}>
      {remaining}s
    </span>
  )
}

function TopicBreakdownBars({ breakdown }: { breakdown: Record<string, { correct: number; total: number }> }) {
  const topics = Object.entries(breakdown)
  if (topics.length === 0) return null
  return (
    <div className="flex flex-col gap-2">
      {topics.map(([topic, { correct, total }]) => {
        const pct = total > 0 ? Math.round((correct / total) * 100) : 0
        return (
          <div key={topic} className="flex flex-col gap-1">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-foreground">{topic}</span>
              <span className="text-muted-foreground">{correct}/{total}</span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div className="h-full bg-primary rounded-full" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

/** The cohort knowledge-quiz taking/result screen (2026-09) — one question
 * at a time with a visible, per-question countdown (auto-submits blank and
 * advances on timeout), then a review + topic breakdown. Reached from the
 * roadmap board's task drawer (`TaskDrawer.tsx`'s `quiz` nav target). All
 * answers are submitted at once at the end (same shape as the instructor-
 * assessment domain's own attempt submit) — there is no per-question submit
 * endpoint. */
export default function CohortQuizPage() {
  const { assignmentId, itemId } = useParams({ strict: false }) as { assignmentId: string; itemId: string }
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [index, setIndex] = useState(0)
  const [answers, setAnswers] = useState<CohortQuizAnswerInput[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [locked, setLocked] = useState(false)
  const questionStartRef = useRef<number>(Date.now())

  const {
    data: attempt, isLoading: attemptLoading, isError: attemptErrored, error: attemptError, refetch: refetchAttempt,
  } = useQuery({
    queryKey: ["cohort-quiz-attempt", assignmentId, itemId],
    queryFn: () => startCohortQuizApi(assignmentId, itemId),
    retry: false,
    // The attempt is a frozen snapshot the whole point of get-or-create is
    // to never reshuffle — an automatic refetch (e.g. on window refocus
    // after an alt-tab mid-quiz) could return a `questions` array shorter
    // than the in-progress `index` if a question was edited/retired in
    // the meantime, blanking the page. Never refetch behind the student's
    // back; a real retry only happens via the explicit error-state button.
    staleTime: Infinity, refetchOnWindowFocus: false, refetchOnReconnect: false,
  })

  const { data: result, isLoading: resultLoading } = useQuery({
    queryKey: ["cohort-quiz-result", assignmentId, itemId],
    queryFn: () => getCohortQuizResultApi(assignmentId, itemId),
    enabled: attempt?.status === "submitted",
  })

  const submitMutation = useMutation({
    mutationFn: (finalAnswers: CohortQuizAnswerInput[]) => submitCohortQuizApi(assignmentId, itemId, finalAnswers),
    onSuccess: () => {
      // Including the attempt query itself, not just the result — its
      // cached `status: "in_progress"` would otherwise still read as
      // in-progress (with `staleTime: Infinity`) if the student leaves and
      // reopens this quiz within the cache's gcTime, showing the
      // question-answering UI again instead of the now-submitted result.
      queryClient.invalidateQueries({ queryKey: ["cohort-quiz-attempt", assignmentId, itemId] })
      queryClient.invalidateQueries({ queryKey: ["cohort-quiz-result", assignmentId, itemId] })
      queryClient.invalidateQueries({ queryKey: ["lms-checklist", assignmentId] })
    },
  })

  // A synchronous guard, not just the `locked` state: a click and the
  // Countdown's onExpire can both fire in the same tick (the exact moment
  // the timer hits 0s), and both would still read the same stale
  // `locked === false` from their own render's closure before React gets a
  // chance to re-render and disable the buttons — double-recording the
  // question and desyncing `answers` from `attempt.total`.
  const lockedRef = useRef(false)

  useEffect(() => {
    setSelected(null)
    setLocked(false)
    lockedRef.current = false
    questionStartRef.current = Date.now()
  }, [index])

  const recordAnswer = (selectedIndex: number | null, timedOut: boolean) => {
    if (lockedRef.current || !attempt) return
    lockedRef.current = true
    const question = attempt.questions[index]
    const elapsed = Math.round((Date.now() - questionStartRef.current) / 1000)
    const updated: CohortQuizAnswerInput[] = [
      ...answers,
      { question_id: question.question_id, selected_option_index: selectedIndex, time_taken_seconds: elapsed, timed_out: timedOut },
    ]
    setAnswers(updated)
    setSelected(selectedIndex)
    setLocked(true)
    setTimeout(() => {
      if (index + 1 < attempt.questions.length) {
        setIndex((i) => i + 1)
      } else {
        submitMutation.mutate(updated)
      }
    }, 350)
  }

  if (attemptErrored) {
    return (
      <div className="mx-auto max-w-[420px] px-5 py-16 flex flex-col items-center gap-4 text-center">
        <p className="text-sm text-muted-foreground">{errorDetail(attemptError, "Couldn't load this quiz.")}</p>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => void refetchAttempt()}>Try again</Button>
          <Button variant="outline" onClick={() => void navigate({ to: `/learn/checklists/${assignmentId}` })}>Back to your program</Button>
        </div>
      </div>
    )
  }
  if (attemptLoading || !attempt) return <div className="p-8"><Spinner /></div>

  const isSubmitted = attempt.status === "submitted" || submitMutation.isSuccess
  const resultData = submitMutation.data ?? result

  if (isSubmitted) {
    if (resultLoading && !resultData) return <div className="p-8"><Spinner /></div>
    if (!resultData) return null
    return (
      <div className="mx-auto max-w-[560px] px-5 py-8 flex flex-col gap-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <Trophy className="size-9 text-primary" />
          <h1 className="font-display text-2xl font-extrabold">Quiz complete!</h1>
          <p className="font-display text-3xl font-extrabold text-primary">{resultData.score} / {resultData.total}</p>
        </div>

        {resultData.topic_breakdown && (
          <div className="flex flex-col gap-2 p-4 rounded-2xl border border-border bg-card">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">By topic</p>
            <TopicBreakdownBars breakdown={resultData.topic_breakdown} />
          </div>
        )}

        <div className="flex flex-col gap-3">
          {resultData.questions.map((q, i) => (
            <div
              key={q.question_id}
              className={`rounded-2xl border p-4 flex flex-col gap-2 text-left ${
                q.is_correct ? "border-border bg-card" : "border-red-500/30 bg-red-500/5"
              }`}
            >
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-mono text-muted-foreground">Q{i + 1}</span>
                <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border border-border text-muted-foreground">
                  {q.topic}
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
              {q.selected_index === null && <p className="text-xs text-muted-foreground italic">Left unanswered.</p>}
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
                      {isSelected && !isCorrectOption && <span className="text-[10px] shrink-0">Your answer</span>}
                    </div>
                  )
                })}
              </div>
              {q.explanation && <p className="text-xs text-muted-foreground border-t border-border pt-2 mt-1">{q.explanation}</p>}
            </div>
          ))}
        </div>

        <div className="flex flex-col gap-2 pt-2">
          <Button onClick={() => void navigate({ to: "/learn/catalog" })} className="h-12 text-base">
            Browse courses
          </Button>
          <Button variant="outline" onClick={() => void navigate({ to: `/learn/checklists/${assignmentId}` })} className="h-12 text-base">
            Back to your program
          </Button>
        </div>
      </div>
    )
  }

  const question = attempt.questions[index]
  if (!question) return null

  return (
    <div className="mx-auto max-w-[560px] px-5 py-8 flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          Question {index + 1} of {attempt.questions.length}
        </span>
        {!locked && (
          <Countdown
            seconds={question.time_limit_seconds} questionKey={question.question_id}
            onExpire={() => recordAnswer(null, true)}
          />
        )}
      </div>
      <h1 className="font-display text-xl font-bold leading-snug">{question.prompt}</h1>
      <div className="grid grid-cols-1 gap-3">
        {question.options.map((text, i) => {
          const isMine = selected === i
          return (
            <button
              key={i}
              onClick={() => recordAnswer(i, false)}
              disabled={locked}
              className={`h-16 px-5 rounded-2xl border-2 text-left text-base font-semibold text-foreground transition-all flex items-center gap-3 ${
                isMine ? "border-primary bg-primary/10" : "border-border bg-card"
              } ${!locked ? "hover:border-primary/50 active:scale-[0.98]" : "disabled:opacity-60"}`}
            >
              <span className="w-7 h-7 flex-none flex items-center justify-center rounded-lg border-2 border-current text-xs">
                {String.fromCharCode(65 + i)}
              </span>
              <span className="flex-1">{text}</span>
            </button>
          )
        })}
      </div>
      {locked && (
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <Clock size={12} /> {selected === null ? "Time's up" : "Locked in"} — next question…
        </p>
      )}
      {submitMutation.isPending && (
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <XCircle size={12} className="animate-pulse" /> Submitting…
        </p>
      )}
      {submitMutation.isError && (
        <div className="flex items-center justify-between gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-2">
          <p className="text-xs text-destructive">{errorDetail(submitMutation.error, "Couldn't submit your answers.")}</p>
          <Button size="sm" variant="outline" onClick={() => submitMutation.mutate(answers)}>Try again</Button>
        </div>
      )}
    </div>
  )
}
