import { useEffect, useState } from "react"
import { useNavigate, useParams } from "@tanstack/react-router"
import { useMutation, useQuery } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2 } from "lucide-react"
import { Spinner } from "@/components/ui/primitives"
import { Progress } from "@/components/ui/progress"
import { QuestionReviewList } from "@/components/AssessmentReview"
import {
  getMyAssessmentAttemptApi,
  startAssessmentAttemptApi,
  submitAssessmentAttemptApi,
} from "@/api/instructor_assessment"
import type { AttemptResult } from "@/types/instructor_assessment"

/** Instructor-facing assessment flow (2026-09) — start -> question-by-
 *  question -> results. One randomized 15-question draw per opportunity
 *  (`cohortCallId`), persisted server-side so a refresh never reshuffles.
 *  Reached from AvailableSessions.tsx when registering interest is gated. */
export default function TakeAssessment() {
  const { cohortCallId } = useParams({ strict: false }) as { cohortCallId: string }
  const navigate = useNavigate()
  const [started, setStarted] = useState(false)

  const { data: existing, isLoading } = useQuery({
    queryKey: ["my-assessment-attempt", cohortCallId],
    queryFn: () => getMyAssessmentAttemptApi(cohortCallId),
  })

  const startMutation = useMutation({
    mutationFn: () => startAssessmentAttemptApi(cohortCallId),
    onSuccess: () => setStarted(true),
  })

  if (isLoading) return <Spinner />

  const attempt = startMutation.data ?? existing ?? null

  if (attempt?.status === "submitted") {
    return <AlreadySubmittedNotice />
  }

  if (!started && !attempt) {
    return (
      <div className="max-w-lg mx-auto flex flex-col gap-6 py-10">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight">Instructor Scenario Assessment</h1>
          <p className="text-sm text-muted-foreground mt-2">
            15 randomized judgment scenarios, drawn from the instructor question bank. Answer each one and submit
            to complete this step of your application.
          </p>
        </div>
        <button
          onClick={() => startMutation.mutate()}
          disabled={startMutation.isPending}
          className="h-11 px-6 bg-primary text-primary-foreground rounded-xl text-sm font-semibold hover:opacity-90 transition-colors disabled:opacity-50 self-start"
        >
          {startMutation.isPending ? "Starting…" : "Begin Assessment"}
        </button>
        <p className="text-xs text-muted-foreground">
          This assessment is required before your application for this opportunity is fully considered.
          Your score contributes to ranking — it doesn't by itself decide selection.
        </p>
      </div>
    )
  }

  if (attempt) {
    return <QuestionFlow attemptId={attempt.id} questions={attempt.questions} onFinished={() => void navigate({ to: "/instructors/available-sessions" })} />
  }

  return <Spinner />
}

function AlreadySubmittedNotice() {
  return (
    <div className="max-w-lg mx-auto flex flex-col items-center gap-3 py-16 text-center">
      <CheckCircle2 size={32} className="text-emerald-600 dark:text-emerald-400" />
      <h1 className="font-display text-xl font-bold">Assessment already submitted</h1>
      <p className="text-sm text-muted-foreground">You've already completed this assessment for this opportunity.</p>
    </div>
  )
}

/** The set of 15 questions and their option order are pinned server-side —
 *  a refresh never reshuffles them — but which ones you'd already answered
 *  used to live only in this component's state, so a refresh sent you back
 *  to question 1. Mirrored into localStorage (keyed by attemptId) so a
 *  refresh resumes exactly where you left off; cleared once submitted. */
function progressKey(attemptId: string) {
  return `ia-attempt-progress:${attemptId}`
}

function QuestionFlow({ attemptId, questions, onFinished }: {
  attemptId: string
  questions: { question_id: string; category: string; prompt: string; options: string[]; critical: boolean }[]
  onFinished: () => void
}) {
  const [index, setIndex] = useState<number>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(progressKey(attemptId)) ?? "null") as { index?: number } | null
      return Math.min(Math.max(saved?.index ?? 0, 0), questions.length - 1)
    } catch { return 0 }
  })
  const [answers, setAnswers] = useState<Record<string, number | null>>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(progressKey(attemptId)) ?? "null") as
        { answers?: Record<string, number | null> } | null
      return saved?.answers ?? {}
    } catch { return {} }
  })
  const [result, setResult] = useState<AttemptResult | null>(null)

  useEffect(() => {
    try {
      localStorage.setItem(progressKey(attemptId), JSON.stringify({ index, answers }))
    } catch { /* private browsing, quota, etc. — progress just won't survive a refresh */ }
  }, [attemptId, index, answers])

  const submitMutation = useMutation({
    mutationFn: () => submitAssessmentAttemptApi(attemptId, answers),
    onSuccess: (data) => {
      try { localStorage.removeItem(progressKey(attemptId)) } catch { /* nothing to clean up then */ }
      setResult(data)
    },
  })

  if (result) return <Results result={result} onDone={onFinished} />

  const current = questions[index]
  const selected = answers[current.question_id] ?? null
  const isLast = index === questions.length - 1

  return (
    <div className="max-w-lg mx-auto flex flex-col gap-4 py-8">
      <div className="flex items-center gap-3">
        <span className="text-xs font-mono text-muted-foreground whitespace-nowrap">
          Card {String(index + 1).padStart(2, "0")} / {questions.length}
        </span>
        <Progress value={((index + 1) / questions.length) * 100} className="flex-1" />
      </div>

      <div className="rounded-2xl bg-card border border-border p-6 flex flex-col gap-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border border-border text-muted-foreground">
            {current.category}
          </span>
          {current.critical && (
            <span className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full bg-red-500 text-white">
              <AlertTriangle size={10} /> Critical scenario
            </span>
          )}
        </div>

        <p className="font-display text-lg font-semibold leading-snug">{current.prompt}</p>

        <div className="flex flex-col gap-2">
          {current.options.map((text, i) => (
            <button
              key={i}
              onClick={() => setAnswers((prev) => ({ ...prev, [current.question_id]: i }))}
              className={`flex items-start gap-3 px-4 py-3 rounded-xl border text-left text-sm transition-colors ${
                selected === i ? "border-primary bg-primary/10" : "border-border hover:bg-muted"
              }`}
            >
              <span className={`w-6 h-6 rounded-md flex items-center justify-center text-xs font-semibold shrink-0 ${
                selected === i ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
              }`}>
                {String.fromCharCode(65 + i)}
              </span>
              {text}
            </button>
          ))}
        </div>

        <button
          onClick={() => {
            if (isLast) submitMutation.mutate()
            else setIndex((i) => i + 1)
          }}
          disabled={selected === null || submitMutation.isPending}
          className="h-11 px-6 bg-primary text-primary-foreground rounded-xl text-sm font-semibold hover:opacity-90 transition-colors disabled:opacity-50 self-end"
        >
          {isLast ? (submitMutation.isPending ? "Submitting…" : "Submit") : "Next"}
        </button>
      </div>
    </div>
  )
}

function Results({ result, onDone }: { result: AttemptResult; onDone: () => void }) {
  const pct = result.total ? Math.round(((result.score ?? 0) / result.total) * 100) : 0
  return (
    <div className="max-w-lg mx-auto flex flex-col items-center gap-6 py-10">
      <div className="text-center">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">Assessment complete</p>
        <p className="font-display text-5xl font-bold mt-2">{result.score} / {result.total}</p>
        <p className="text-sm font-mono text-muted-foreground mt-1">{pct}%</p>
      </div>

      <p className="text-xs text-muted-foreground text-center">
        This score contributes to your Instructor Priority Score for this opportunity.
      </p>

      <button
        onClick={onDone}
        className="h-11 px-6 bg-primary text-primary-foreground rounded-xl text-sm font-semibold hover:opacity-90 transition-colors"
      >
        Return to Available Sessions
      </button>

      {result.questions.length > 0 && (
        <div className="w-full flex flex-col gap-3 pt-4 border-t border-border">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Review your answers</p>
          <QuestionReviewList questions={result.questions} />
        </div>
      )}
    </div>
  )
}
