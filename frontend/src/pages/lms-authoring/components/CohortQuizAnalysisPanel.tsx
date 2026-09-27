import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { BookOpen, CheckCircle2, ChevronRight, Layers, RefreshCw, Trophy } from "lucide-react"
import { getCohortQuizAnalysisApi, type CohortQuizAnalysisOut } from "@/api/lms_admin"
import { EmptyState, Spinner } from "@/components/ui/primitives"

export function CohortQuizAnalysisPanel({ cohortId }: { cohortId: string }) {
  const [selectedQuizId, setSelectedQuizId] = useState<string>("all")

  const { data: analysis, isLoading, refetch, isRefetching } = useQuery<CohortQuizAnalysisOut>({
    queryKey: ["cohort-quiz-analysis", cohortId],
    queryFn: () => getCohortQuizAnalysisApi(cohortId),
  })

  if (isLoading) return <Spinner />

  if (!analysis || analysis.total_attempts === 0) {
    return (
      <EmptyState
        title="No quiz submissions yet"
        hint="Once students complete and submit their cohort knowledge-quizzes, real-time topic levels and mastery breakdowns will appear here."
      />
    )
  }

  // Determine which topic breakdown to display (overall vs specific quiz)
  const currentQuiz =
    selectedQuizId !== "all"
      ? analysis.quizzes.find((q) => q.quiz_id === selectedQuizId)
      : null

  const activeTopicBreakdown = currentQuiz
    ? currentQuiz.topic_breakdown
    : analysis.overall_topic_breakdown

  const activeAttempts = currentQuiz ? currentQuiz.total_attempts : analysis.total_attempts
  const activeAvgScore = currentQuiz ? currentQuiz.average_score_pct : analysis.overall_average_score_pct
  const topicsCount = Object.keys(activeTopicBreakdown).length

  return (
    <div className="flex flex-col gap-6">
      {/* Metric Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="p-4 rounded-xl bg-card border border-border flex items-center justify-between">
          <div>
            <span className="text-xs uppercase font-medium text-muted-foreground">Total Submissions</span>
            <p className="text-2xl font-bold text-foreground mt-1">{activeAttempts}</p>
            <span className="text-[11px] text-muted-foreground">
              {selectedQuizId === "all" ? "Across all cohort quizzes" : "For selected quiz"}
            </span>
          </div>
          <div className="p-2.5 rounded-lg bg-primary/10 text-primary">
            <CheckCircle2 size={20} />
          </div>
        </div>

        <div className="p-4 rounded-xl bg-card border border-border flex items-center justify-between">
          <div>
            <span className="text-xs uppercase font-medium text-muted-foreground">Average Mastery</span>
            <p className="text-2xl font-bold text-foreground mt-1">{activeAvgScore}%</p>
            <span className="text-[11px] text-muted-foreground">Cohort performance grade</span>
          </div>
          <div className="p-2.5 rounded-lg bg-emerald-500/10 text-emerald-500">
            <Trophy size={20} />
          </div>
        </div>

        <div className="p-4 rounded-xl bg-card border border-border flex items-center justify-between">
          <div>
            <span className="text-xs uppercase font-medium text-muted-foreground">Topics Assessed</span>
            <p className="text-2xl font-bold text-foreground mt-1">{topicsCount}</p>
            <span className="text-[11px] text-muted-foreground">Curriculum knowledge areas</span>
          </div>
          <div className="p-2.5 rounded-lg bg-indigo-500/10 text-indigo-500">
            <BookOpen size={20} />
          </div>
        </div>
      </div>

      {/* Selector: Overall vs Individual Quiz */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 bg-card border border-border rounded-xl">
        <div className="flex items-center gap-2">
          <Layers size={16} className="text-muted-foreground" />
          <span className="text-xs font-semibold uppercase text-muted-foreground">Evaluation Scope:</span>
          <select
            value={selectedQuizId}
            onChange={(e) => setSelectedQuizId(e.target.value)}
            className="bg-background border border-border text-foreground text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary font-medium"
          >
            <option value="all">Overall Cohort (All Quizzes Combined)</option>
            {analysis.quizzes.map((q) => (
              <option key={q.quiz_id} value={q.quiz_id}>
                Quiz: {q.quiz_title} ({q.total_attempts} submissions)
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={() => refetch()}
          disabled={isRefetching}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground bg-background border border-border rounded-lg transition disabled:opacity-50"
        >
          <RefreshCw size={13} className={isRefetching ? "animate-spin" : ""} />
          Refresh Live Data
        </button>
      </div>

      {/* Strengths & Weaknesses by Topic Card */}
      <div className="flex flex-col gap-4 p-5 bg-card border border-border rounded-2xl">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Strengths & weaknesses by topic</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            {selectedQuizId === "all"
              ? "Summed live across every cohort knowledge-quiz submitted in this cohort."
              : `Summed live for "${currentQuiz?.quiz_title}".`}
          </p>
        </div>

        {topicsCount === 0 ? (
          <p className="text-xs text-muted-foreground py-4 text-center">
            No topic data tagged for this quiz.
          </p>
        ) : (
          <div className="flex flex-col gap-3.5">
            {Object.entries(activeTopicBreakdown).map(([topic, { correct, total }]) => {
              const pct = total > 0 ? Math.round((correct / total) * 100) : 0
              return (
                <div key={topic} className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-foreground">{topic}</span>
                    <span className="text-muted-foreground font-mono">
                      {correct}/{total} ({pct}%)
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-muted overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        pct >= 70 ? "bg-emerald-500" : pct >= 40 ? "bg-amber-500" : "bg-red-500"
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Quizzes Overview Table (when viewing overall) */}
      {selectedQuizId === "all" && analysis.quizzes.length > 0 && (
        <div className="flex flex-col gap-3 p-5 bg-card border border-border rounded-2xl">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Quizzes in this Cohort ({analysis.quizzes.length})
          </h4>
          <div className="divide-y divide-border border border-border rounded-xl overflow-hidden bg-background">
            {analysis.quizzes.map((q) => (
              <div
                key={q.quiz_id}
                onClick={() => setSelectedQuizId(q.quiz_id)}
                className="flex items-center justify-between p-3 hover:bg-muted/40 cursor-pointer transition text-xs"
              >
                <div className="flex items-center gap-2">
                  <span className="font-medium text-foreground">{q.quiz_title}</span>
                  <span className="text-[11px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                    {q.total_attempts} takes
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-semibold text-foreground">Avg: {q.average_score_pct}%</span>
                  <ChevronRight size={14} className="text-muted-foreground" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
