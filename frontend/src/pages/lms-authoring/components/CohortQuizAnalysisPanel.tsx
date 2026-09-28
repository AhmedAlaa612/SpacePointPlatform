import { useState, useMemo, useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  BookOpen,
  CheckCircle2,
  ChevronRight,
  Layers,
  RefreshCw,
  Trophy,
  XCircle,
  HelpCircle,
  ArrowUpDown,
  Filter,
  Search,
} from "lucide-react"
import { getCohortQuizAnalysisApi, type CohortQuizAnalysisOut } from "@/api/lms_admin"
import { EmptyState, Spinner } from "@/components/ui/primitives"

export function CohortQuizAnalysisPanel({ cohortId }: { cohortId: string }) {
  const [selectedQuizId, setSelectedQuizId] = useState<string>("all")

  // Questions breakdown filter and sort states
  const [questionQuizFilter, setQuestionQuizFilter] = useState<string>("all")
  const [questionTopicFilter, setQuestionTopicFilter] = useState<string>("all")
  const [questionSortBy, setQuestionSortBy] = useState<
    "most_wrong" | "most_right" | "lowest_accuracy" | "highest_accuracy" | "total_answers"
  >("most_wrong")
  const [questionSearch, setQuestionSearch] = useState<string>("")

  const { data: analysis, isLoading, refetch, isRefetching } = useQuery<CohortQuizAnalysisOut>({
    queryKey: ["cohort-quiz-analysis", cohortId],
    queryFn: () => getCohortQuizAnalysisApi(cohortId),
  })

  // Sync questions quiz filter when top scope selector changes
  useEffect(() => {
    setQuestionQuizFilter(selectedQuizId)
  }, [selectedQuizId])

  // Extract all distinct topics from questions list
  const availableTopics = useMemo(() => {
    if (!analysis?.questions) return []
    const topicSet = new Set<string>()
    for (const q of analysis.questions) {
      if (q.topic) topicSet.add(q.topic)
    }
    return Array.from(topicSet).sort()
  }, [analysis?.questions])

  // Filter and sort questions list
  const filteredAndSortedQuestions = useMemo(() => {
    if (!analysis?.questions) return []
    let list = [...analysis.questions]

    // 1. Filter by Quiz
    if (questionQuizFilter !== "all") {
      list = list.filter((q) => q.quiz_id === questionQuizFilter)
    }

    // 2. Filter by Topic
    if (questionTopicFilter !== "all") {
      list = list.filter((q) => q.topic === questionTopicFilter)
    }

    // 3. Filter by Search Query
    if (questionSearch.trim()) {
      const qLower = questionSearch.toLowerCase().trim()
      list = list.filter(
        (q) =>
          q.prompt.toLowerCase().includes(qLower) ||
          q.topic.toLowerCase().includes(qLower) ||
          q.quiz_title.toLowerCase().includes(qLower)
      )
    }

    // 4. Sort
    list.sort((a, b) => {
      switch (questionSortBy) {
        case "most_wrong":
          if (b.incorrect_count !== a.incorrect_count) {
            return b.incorrect_count - a.incorrect_count
          }
          return a.accuracy_pct - b.accuracy_pct
        case "most_right":
          if (b.correct_count !== a.correct_count) {
            return b.correct_count - a.correct_count
          }
          return b.accuracy_pct - a.accuracy_pct
        case "lowest_accuracy":
          if (a.accuracy_pct !== b.accuracy_pct) {
            return a.accuracy_pct - b.accuracy_pct
          }
          return b.incorrect_count - a.incorrect_count
        case "highest_accuracy":
          if (b.accuracy_pct !== a.accuracy_pct) {
            return b.accuracy_pct - a.accuracy_pct
          }
          return b.correct_count - a.correct_count
        case "total_answers":
          return b.total_answers - a.total_answers
        default:
          return 0
      }
    })

    return list
  }, [analysis?.questions, questionQuizFilter, questionTopicFilter, questionSearch, questionSortBy])

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

      {/* ── Block 1: Strengths & Weaknesses by Topic Card ─────────────────── */}
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

      {/* ── Block 2: Questions Breakdown (Right vs Wrong Analysis) ────────── */}
      <div className="flex flex-col gap-4 p-5 bg-card border border-border rounded-2xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-foreground">Questions Performance Breakdown</h3>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium">
                {filteredAndSortedQuestions.length} Questions
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Inspect student responses per question, analyze question difficulty, and identify common misconceptions.
            </p>
          </div>
        </div>

        {/* Filter & Sort Controls */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 p-3 rounded-xl bg-muted/30 border border-border/70 text-xs">
          {/* Quiz Filter */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wider flex items-center gap-1">
              <Layers size={11} /> Filter by Quiz
            </label>
            <select
              value={questionQuizFilter}
              onChange={(e) => setQuestionQuizFilter(e.target.value)}
              className="h-8 bg-background border border-border text-foreground text-xs rounded-lg px-2.5 focus:outline-none focus:ring-1 focus:ring-primary truncate"
            >
              <option value="all">All Quizzes</option>
              {analysis.quizzes.map((q) => (
                <option key={q.quiz_id} value={q.quiz_id}>
                  {q.quiz_title}
                </option>
              ))}
            </select>
          </div>

          {/* Topic Filter */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wider flex items-center gap-1">
              <Filter size={11} /> Filter by Topic
            </label>
            <select
              value={questionTopicFilter}
              onChange={(e) => setQuestionTopicFilter(e.target.value)}
              className="h-8 bg-background border border-border text-foreground text-xs rounded-lg px-2.5 focus:outline-none focus:ring-1 focus:ring-primary truncate"
            >
              <option value="all">All Topics ({availableTopics.length})</option>
              {availableTopics.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          {/* Sort By */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wider flex items-center gap-1">
              <ArrowUpDown size={11} /> Sort Questions By
            </label>
            <select
              value={questionSortBy}
              onChange={(e) => setQuestionSortBy(e.target.value as any)}
              className="h-8 bg-background border border-border text-foreground text-xs rounded-lg px-2.5 focus:outline-none focus:ring-1 focus:ring-primary font-medium"
            >
              <option value="most_wrong">Most Wrong Answers First</option>
              <option value="most_right">Most Right Answers First</option>
              <option value="lowest_accuracy">Hardest Questions First (Lowest % Correct)</option>
              <option value="highest_accuracy">Easiest Questions First (Highest % Correct)</option>
              <option value="total_answers">Most Total Responses</option>
            </select>
          </div>

          {/* Search Prompt */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wider flex items-center gap-1">
              <Search size={11} /> Search Questions
            </label>
            <div className="relative">
              <input
                type="text"
                value={questionSearch}
                onChange={(e) => setQuestionSearch(e.target.value)}
                placeholder="Search prompt or keyword..."
                className="w-full h-8 pl-7 pr-2.5 bg-background border border-border text-foreground text-xs rounded-lg placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60" />
            </div>
          </div>
        </div>

        {/* Questions List */}
        {filteredAndSortedQuestions.length === 0 ? (
          <div className="p-8 text-center border border-dashed border-border rounded-xl text-xs text-muted-foreground">
            <HelpCircle size={28} className="mx-auto text-muted-foreground/40 mb-2" />
            No questions match the selected filters.
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {filteredAndSortedQuestions.map((q, idx) => {
              const wrongPct = q.total_answers > 0 ? Math.round((q.incorrect_count / q.total_answers) * 100) : 0
              return (
                <div
                  key={`${q.question_id}-${q.quiz_id}-${idx}`}
                  className="p-4 rounded-xl bg-card border border-border hover:border-border/80 transition-all flex flex-col gap-3"
                >
                  {/* Question Header & Prompt */}
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                    <div className="flex items-start gap-2.5 min-w-0">
                      <span className="shrink-0 w-6 h-6 rounded-lg bg-muted text-muted-foreground font-mono text-xs flex items-center justify-center font-bold">
                        {idx + 1}
                      </span>
                      <p className="text-xs sm:text-sm font-medium text-foreground leading-relaxed">
                        {q.prompt}
                      </p>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0 self-start sm:self-auto">
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-muted text-muted-foreground border border-border">
                        {q.topic}
                      </span>
                      {q.difficulty && (
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-md bg-muted/60 text-muted-foreground border border-border capitalize">
                          {q.difficulty}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Subtitle with Quiz info */}
                  <div className="text-[11px] text-muted-foreground flex items-center gap-1.5">
                    <span>Quiz:</span>
                    <span className="font-medium text-foreground">{q.quiz_title}</span>
                  </div>

                  {/* Breakdown Bars & Counters */}
                  <div className="pt-2 border-t border-border/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                    <div className="flex items-center gap-3">
                      {/* Right Count */}
                      <span className="inline-flex items-center gap-1 font-semibold text-emerald-500 bg-emerald-500/10 px-2.5 py-1 rounded-lg">
                        <CheckCircle2 size={13} />
                        {q.correct_count} Right ({q.accuracy_pct}%)
                      </span>

                      {/* Wrong Count */}
                      <span className="inline-flex items-center gap-1 font-semibold text-rose-500 bg-rose-500/10 px-2.5 py-1 rounded-lg">
                        <XCircle size={13} />
                        {q.incorrect_count} Wrong ({wrongPct}%)
                      </span>

                      <span className="text-muted-foreground text-[11px] font-mono">
                        {q.total_answers} total takes
                      </span>
                    </div>

                    {/* Visual Segmented Progress Bar */}
                    <div className="flex items-center gap-2 w-full sm:w-48 shrink-0">
                      <div className="h-2 w-full rounded-full bg-muted overflow-hidden flex">
                        <div
                          className="h-full bg-emerald-500 transition-all"
                          style={{ width: `${q.accuracy_pct}%` }}
                          title={`${q.correct_count} Correct (${q.accuracy_pct}%)`}
                        />
                        <div
                          className="h-full bg-rose-500 transition-all"
                          style={{ width: `${wrongPct}%` }}
                          title={`${q.incorrect_count} Incorrect (${wrongPct}%)`}
                        />
                      </div>
                      <span className="text-[11px] font-mono font-semibold text-muted-foreground shrink-0 w-8 text-right">
                        {q.accuracy_pct}%
                      </span>
                    </div>
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
