import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "@tanstack/react-router"
import { isAxiosError } from "axios"
import { AlertCircle, Check, CheckCircle2, Clock, Lightbulb, Sparkles, Trophy, XCircle } from "lucide-react"
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
    <div className={`flex items-center gap-2 font-display text-3xl sm:text-4xl font-black tracking-tight ${remaining <= 5 ? "text-destructive animate-pulse" : "text-foreground"}`}>
      <Clock className={`size-6 sm:size-7 ${remaining <= 5 ? "text-destructive" : "text-primary"}`} />
      <span>{remaining}s</span>
    </div>
  )
}

function TopicBreakdownBars({ breakdown }: { breakdown: Record<string, { correct: number; total: number }> }) {
  const topics = Object.entries(breakdown)
  if (topics.length === 0) return null
  return (
    <div className="flex flex-col gap-3">
      {topics.map(([topic, { correct, total }]) => {
        const pct = total > 0 ? Math.round((correct / total) * 100) : 0
        return (
          <div key={topic} className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between text-sm sm:text-base">
              <span className="font-semibold text-foreground">{topic}</span>
              <span className="text-xs font-mono font-bold text-muted-foreground bg-muted px-2.5 py-0.5 rounded-md border border-border/40">
                {correct}/{total}
              </span>
            </div>
            <div className="h-3 rounded-full bg-muted overflow-hidden p-0.5 border border-border/30">
              <div
                className="h-full bg-primary rounded-full transition-all duration-500"
                style={{ width: `${pct}%` }}
              />
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
  const [selectedIndices, setSelectedIndices] = useState<number[]>([])
  const [textAnswer, setTextAnswer] = useState("")
  const textAnswerRef = useRef("")
  textAnswerRef.current = textAnswer
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
    setSelectedIndices([])
    setTextAnswer("")
    textAnswerRef.current = ""
    setLocked(false)
    lockedRef.current = false
    questionStartRef.current = Date.now()
  }, [index])

  const recordAnswer = (
    selectedIndex: number | null,
    timedOut: boolean,
    textVal?: string | null,
    multiIndices?: number[] | null,
  ) => {
    if (lockedRef.current || !attempt) return
    lockedRef.current = true
    const question = attempt.questions[index]
    const elapsed = Math.round((Date.now() - questionStartRef.current) / 1000)
    const isTextarea = question.question_type === "textarea"
    const isMultiselect = question.question_type === "multiselect" || question.question_type === "multiple_choice"
    const rawText = textVal !== undefined ? textVal : textAnswerRef.current
    const finalTrimmedText = isTextarea ? (rawText?.trim() || null) : null

    const finalMultiIndices = isMultiselect
      ? (multiIndices !== undefined ? multiIndices : selectedIndices)
      : (selectedIndex !== null ? [selectedIndex] : null)

    const updated: CohortQuizAnswerInput[] = [
      ...answers,
      {
        question_id: question.question_id,
        selected_option_index: selectedIndex,
        selected_option_indices: finalMultiIndices,
        text_answer: finalTrimmedText,
        time_taken_seconds: elapsed,
        timed_out: timedOut,
      },
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
    const msg = errorDetail(attemptError, "Couldn't load this quiz.")
    const isDeadline = msg.toLowerCase().includes("deadline")
    return (
      <div className="mx-auto max-w-xl px-5 py-16 flex flex-col items-center gap-4 text-center">
        {isDeadline ? (
          <div className="p-3 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-500 mb-1">
            <Clock size={36} />
          </div>
        ) : (
          <div className="p-3 rounded-full bg-destructive/10 text-destructive mb-1">
            <AlertCircle size={36} />
          </div>
        )}
        <h2 className="font-display text-2xl font-bold text-foreground">
          {isDeadline ? "Deadline Passed" : "Quiz Unavailable"}
        </h2>
        <p className="text-sm text-muted-foreground">{msg}</p>
        <div className="flex gap-2 mt-2">
          {!isDeadline && <Button variant="outline" onClick={() => void refetchAttempt()}>Try again</Button>}
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
      <div className="mx-auto max-w-3xl lg:max-w-4xl px-5 py-8 flex flex-col gap-8">
        <div className="flex flex-col items-center gap-3 text-center py-4">
          <div className="size-16 rounded-3xl bg-primary/10 border-2 border-primary/30 flex items-center justify-center shadow-xl shadow-black/20">
            <Trophy className="size-8 text-primary" />
          </div>
          <h1 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight">Quiz complete!</h1>
          {resultData.total > 0 && resultData.score !== null ? (
            <p className="font-display text-5xl sm:text-6xl font-black text-primary">
              {resultData.score} / {resultData.total}
            </p>
          ) : (
            <p className="text-base sm:text-lg text-muted-foreground font-medium">
              All responses recorded successfully.
            </p>
          )}
        </div>

        {resultData.topic_breakdown && (
          <div className="flex flex-col gap-3 p-5 sm:p-6 rounded-2xl border-2 border-border bg-card shadow-xl shadow-black/20">
            <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <Sparkles size={14} className="text-primary" /> Performance by topic
            </p>
            <TopicBreakdownBars breakdown={resultData.topic_breakdown} />
          </div>
        )}

        <div className="flex flex-col gap-5">
          <h2 className="text-xs font-bold uppercase tracking-wider text-muted-foreground px-1">
            Question breakdown ({resultData.questions.length} questions)
          </h2>
          {resultData.questions.map((q, i) => {
            const isTextarea = q.question_type === "textarea"
            const isMultiselect = q.question_type === "multiselect" || q.question_type === "multiple_choice"
            const isOpinion = !isTextarea && q.is_correct === null
            const cardBorder = isTextarea
              ? "border-purple-500/40 bg-card hover:border-purple-500/60"
              : isOpinion
              ? "border-blue-500/40 bg-card hover:border-blue-500/60"
              : q.is_correct
              ? "border-emerald-500/40 bg-card hover:border-emerald-500/60"
              : "border-red-500/40 bg-card hover:border-red-500/60"

            return (
              <div
                key={q.question_id}
                className={`rounded-2xl border-2 p-5 sm:p-6 flex flex-col gap-4 text-left shadow-xl shadow-black/20 transition-all ${cardBorder}`}
              >
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-lg bg-muted text-foreground border border-border/50">
                      Q{i + 1}
                    </span>
                    <span className="text-xs font-semibold uppercase tracking-wider px-2.5 py-1 rounded-full border border-border bg-muted/50 text-muted-foreground">
                      {q.topic}
                    </span>
                    {q.is_optional && (
                      <span className="text-xs font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-500">
                        Optional
                      </span>
                    )}
                  </div>
                  {isTextarea ? (
                    <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full bg-purple-500/15 text-purple-400 border-2 border-purple-500/30">
                      Open Response
                    </span>
                  ) : isOpinion ? (
                    <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full bg-blue-500/15 text-blue-400 border-2 border-blue-500/30">
                      {isMultiselect ? "Multiple Choice (Opinion)" : "Opinion"}
                    </span>
                  ) : q.is_correct ? (
                    <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full bg-emerald-500/15 text-emerald-400 border-2 border-emerald-500/30">
                      <CheckCircle2 size={13} /> Correct
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full bg-red-500/15 text-red-400 border-2 border-red-500/30">
                      <XCircle size={13} /> Incorrect
                    </span>
                  )}
                </div>

                <p className="text-base sm:text-lg font-semibold leading-relaxed text-foreground">{q.prompt}</p>

                {isTextarea ? (
                  <div className="flex flex-col gap-2 p-4 rounded-xl bg-muted/40 border border-border/70">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Your Response:</span>
                    {q.text_answer ? (
                      <p className="text-sm sm:text-base text-foreground whitespace-pre-wrap leading-relaxed">
                        {q.text_answer}
                      </p>
                    ) : (
                      <p className="text-sm text-muted-foreground italic flex items-center gap-1.5">
                        <AlertCircle size={14} /> Left unanswered.
                      </p>
                    )}
                  </div>
                ) : (
                  <>
                    {q.selected_index === null && (!q.selected_indices || q.selected_indices.length === 0) && (
                      <p className="text-sm text-amber-500/90 font-medium italic flex items-center gap-1.5">
                        <AlertCircle size={14} /> Left unanswered.
                      </p>
                    )}

                    <div className="flex flex-col gap-2.5 pt-1">
                      {q.options.map((text, oi) => {
                        const isSelected = q.selected_indices && q.selected_indices.length > 0
                          ? q.selected_indices.includes(oi)
                          : q.selected_index === oi
                        const isCorrectOption = q.correct_indices && q.correct_indices.length > 0
                          ? q.correct_indices.includes(oi)
                          : q.correct_index === oi

                        let optionStyle = "bg-muted/40 text-muted-foreground border border-border/40"
                        let badgeStyle = "bg-muted text-muted-foreground"

                        if (isOpinion) {
                          if (isSelected) {
                            optionStyle = "bg-blue-500/15 text-blue-400 dark:text-blue-300 font-medium border-2 border-blue-500/40"
                            badgeStyle = "bg-blue-500/25 text-blue-300 border border-blue-500/30"
                          }
                        } else {
                          if (isCorrectOption) {
                            optionStyle = "bg-emerald-500/15 text-emerald-400 dark:text-emerald-300 font-medium border-2 border-emerald-500/40"
                            badgeStyle = "bg-emerald-500/25 text-emerald-300 border border-emerald-500/30"
                          } else if (isSelected) {
                            optionStyle = "bg-red-500/15 text-red-400 dark:text-red-300 font-medium border-2 border-red-500/40"
                            badgeStyle = "bg-red-500/25 text-red-300 border border-red-500/30"
                          }
                        }

                        return (
                          <div
                            key={oi}
                            className={`px-4 py-3.5 rounded-xl text-sm sm:text-base flex items-center gap-3.5 transition-all ${optionStyle}`}
                          >
                            <span
                              className={`w-7 h-7 rounded-lg text-xs font-bold flex items-center justify-center shrink-0 ${badgeStyle}`}
                            >
                              {String.fromCharCode(65 + oi)}
                            </span>
                            <span className="flex-1 leading-snug">{text}</span>
                            {isOpinion && isSelected && (
                              <span className="text-xs font-bold shrink-0 px-2.5 py-1 rounded-lg bg-blue-500/20 text-blue-300 border border-blue-500/30">
                                Your choice
                              </span>
                            )}
                            {!isOpinion && isCorrectOption && isSelected && (
                              <span className="text-xs font-bold shrink-0 px-2.5 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                                Correct answer
                              </span>
                            )}
                            {!isOpinion && isCorrectOption && !isSelected && (
                              <span className="text-xs font-bold shrink-0 px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-400/80 border border-emerald-500/20 italic">
                                Missed
                              </span>
                            )}
                            {!isOpinion && isSelected && !isCorrectOption && (
                              <span className="text-xs font-bold shrink-0 px-2.5 py-1 rounded-lg bg-red-500/20 text-red-300 border border-red-500/30">
                                Your answer
                              </span>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </>
                )}

                {q.explanation && (
                  <div className="mt-1 p-4 rounded-xl bg-muted/50 border border-border/60 flex flex-col gap-1.5">
                    <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                      <Lightbulb size={14} className="text-amber-400 shrink-0" /> Explanation
                    </p>
                    <p className="text-xs sm:text-sm text-foreground/90 leading-relaxed font-medium">{q.explanation}</p>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        <div className="flex flex-col sm:flex-row gap-3 pt-2">
          <Button onClick={() => void navigate({ to: "/learn/catalog" })} className="h-12 text-base font-bold flex-1">
            Browse courses
          </Button>
          <Button variant="outline" onClick={() => void navigate({ to: `/learn/checklists/${assignmentId}` })} className="h-12 text-base font-bold flex-1">
            Back to your program
          </Button>
        </div>
      </div>
    )
  }

  const question = attempt.questions[index]
  if (!question) return null

  return (
    <div className="mx-auto max-w-3xl lg:max-w-4xl px-5 py-8 flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
            Question {index + 1} of {attempt.questions.length}
          </span>
          <div className="flex items-center gap-1.5">
            {attempt.questions.map((_, i) => {
              const isCurrent = i === index
              const isPast = i < index
              return (
                <div
                  key={i}
                  className={`h-2.5 rounded-full transition-all duration-300 ${
                    isCurrent
                      ? "w-7 bg-primary ring-2 ring-primary/30"
                      : isPast
                      ? "w-2.5 bg-primary/60"
                      : "w-2.5 bg-muted-foreground/25 dark:bg-muted-foreground/20"
                  }`}
                />
              )
            })}
          </div>
        </div>
        {!locked && question.time_limit_seconds > 0 && (
          <Countdown
            seconds={question.time_limit_seconds} questionKey={question.question_id}
            onExpire={() => {
              if (question.question_type === "textarea") {
                recordAnswer(null, true, textAnswerRef.current)
              } else if (question.question_type === "multiselect" || question.question_type === "multiple_choice") {
                recordAnswer(null, true, null, selectedIndices)
              } else {
                recordAnswer(null, true)
              }
            }}
          />
        )}
        {!locked && question.time_limit_seconds <= 0 && (
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground bg-muted/40 border border-border px-3 py-1.5 rounded-xl">
            <Clock size={13} className="text-primary" /> Untimed
          </div>
        )}
      </div>
      <h1 className="font-display text-2xl sm:text-3xl lg:text-4xl font-semibold leading-tight tracking-normal text-foreground">{question.prompt}</h1>
      {question.question_type === "textarea" ? (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <textarea
              value={textAnswer}
              onChange={(e) => setTextAnswer(e.target.value)}
              disabled={locked}
              placeholder="Write your response here..."
              rows={6}
              maxLength={2000}
              className="w-full p-4 rounded-2xl border-2 border-border bg-card text-foreground text-base focus:outline-none focus:border-primary transition-all resize-y disabled:opacity-60 placeholder:text-muted-foreground/60 leading-relaxed font-sans"
              autoFocus
            />
            <div className="flex items-center justify-between text-xs text-muted-foreground px-1">
              <span>{textAnswer.length} / 2000 characters</span>
              <span className="italic">
                {question.is_optional ? "Open-ended question (Optional)" : "Open-ended question (Required)"}
              </span>
            </div>
          </div>

          <div className="flex justify-end">
            <Button
              onClick={() => recordAnswer(null, false, textAnswer)}
              disabled={locked || (!question.is_optional && !textAnswer.trim())}
              className="h-11 px-6 rounded-xl font-semibold text-sm"
            >
              {textAnswer.trim()
                ? "Submit Answer & Next"
                : question.is_optional
                ? "Skip & Next"
                : "Submit Answer & Next"}
            </Button>
          </div>
        </div>
      ) : (question.question_type === "multiselect" || question.question_type === "multiple_choice") ? (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between px-1 text-xs text-muted-foreground">
            <span className="font-semibold uppercase tracking-wider text-primary">
              Multiple Choice — Select all that apply
            </span>
            <span>
              {question.is_optional ? "(Optional)" : "(Required)"}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3">
            {question.options.map((text, i) => {
              const isChecked = selectedIndices.includes(i)
              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => {
                    if (locked) return
                    setSelectedIndices((prev) =>
                      prev.includes(i) ? prev.filter((idx) => idx !== i) : [...prev, i].sort((a, b) => a - b)
                    )
                  }}
                  disabled={locked}
                  className={`min-h-[64px] py-3.5 px-5 rounded-2xl border-2 text-left text-base font-medium text-foreground transition-all flex items-center gap-4 cursor-pointer ${
                    isChecked ? "border-primary bg-primary/10" : "border-border bg-card"
                  } ${!locked ? "hover:border-primary/50 active:scale-[0.98]" : "disabled:opacity-60"}`}
                >
                  <span
                    className={`w-7 h-7 flex-none flex items-center justify-center rounded-lg border-2 transition-colors ${
                      isChecked
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-muted-foreground/40 bg-background"
                    }`}
                  >
                    {isChecked && <Check size={16} className="stroke-[3]" />}
                  </span>
                  <span className="w-8 h-8 flex-none flex items-center justify-center rounded-xl border border-border bg-muted/30 text-xs font-bold text-muted-foreground">
                    {String.fromCharCode(65 + i)}
                  </span>
                  <span className="flex-1 text-base leading-snug">{text}</span>
                </button>
              )
            })}
          </div>

          <div className="flex justify-end pt-2">
            <Button
              onClick={() => recordAnswer(null, false, null, selectedIndices)}
              disabled={locked || (!question.is_optional && selectedIndices.length === 0)}
              className="h-11 px-6 rounded-xl font-semibold text-sm"
            >
              {selectedIndices.length > 0
                ? "Submit Answer & Next"
                : question.is_optional
                ? "Skip & Next"
                : "Submit Answer & Next"}
            </Button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3">
          {question.options.map((text, i) => {
            const isMine = selected === i
            return (
              <button
                key={i}
                onClick={() => recordAnswer(i, false)}
                disabled={locked}
                className={`min-h-[64px] py-3.5 px-5 rounded-2xl border-2 text-left text-base font-medium text-foreground transition-all flex items-center gap-4 ${
                  isMine ? "border-primary bg-primary/10" : "border-border bg-card"
                } ${!locked ? "hover:border-primary/50 active:scale-[0.98]" : "disabled:opacity-60"}`}
              >
                <span className="w-8 h-8 flex-none flex items-center justify-center rounded-xl border-2 border-current text-sm font-bold">
                  {String.fromCharCode(65 + i)}
                </span>
                <span className="flex-1 text-base leading-snug">{text}</span>
              </button>
            )
          })}
        </div>
      )}
      {locked && (
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <Clock size={12} /> {selected === null && !textAnswer.trim() ? "Time's up" : "Submitted"} — next question…
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
