import { useState, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Layers,
  MessageSquare,
  RefreshCw,
  XCircle,
  HelpCircle,
  ArrowUpDown,
  Filter,
  Search,
} from "lucide-react"
import { getCohortTeamAnalyticsApi } from "@/api/competitions"
import { getCohortQuizAnalysisApi, type CohortQuizAnalysisOut } from "@/api/lms_admin"
import { AnalysisFunnelWidget } from "@/components/ui/AnalysisFunnelWidget"
import { EmptyState, Spinner } from "@/components/ui/primitives"
import { useAuth } from "@/context/AuthContext"
import {
  CompletionRateChart,
  MissionsBlock,
  SectionCard,
  computeBottleneck,
  useIsDark,
} from "@/pages/admin/components/CompetitionAnalysis"

export function CohortQuizAnalysisPanel({ cohortId }: { cohortId: string }) {
  const { currentUser, activeRole } = useAuth()
  const isInstructor = activeRole === "instructor" || currentUser?.role === "instructor"
  const isDark = useIsDark()
  const [selectedQuizId, setSelectedQuizId] = useState<string>("all")
  const [rosterMode, setRosterMode] = useState<"student" | "observer" | "all">("student")

  // Questions breakdown filter and sort states
  const [questionTopicFilter, setQuestionTopicFilter] = useState<string>("all")
  const [questionSortBy, setQuestionSortBy] = useState<
    "most_wrong" | "most_right" | "lowest_accuracy" | "highest_accuracy" | "total_answers"
  >("most_wrong")
  const [questionSearch, setQuestionSearch] = useState<string>("")
  const [expandedTextIds, setExpandedTextIds] = useState<Record<string, boolean>>({})

  const teamMode = rosterMode === "observer" ? "observer" : rosterMode === "all" ? "all" : "participant"

  const { data: teamAnalytics, isLoading: loadingTeam, refetch: refetchTeam, isRefetching: refetchingTeam } = useQuery({
    queryKey: ["competitions-team-analytics", cohortId, teamMode, isInstructor],
    queryFn: () => getCohortTeamAnalyticsApi(cohortId, teamMode, isInstructor),
  })

  const { data: analysis, isLoading: loadingQuiz, refetch: refetchQuiz, isRefetching: refetchingQuiz } = useQuery<CohortQuizAnalysisOut>({
    queryKey: ["cohort-quiz-analysis", cohortId, rosterMode],
    queryFn: () => getCohortQuizAnalysisApi(cohortId, rosterMode),
  })

  const isLoading = loadingTeam && loadingQuiz
  const isRefetching = refetchingTeam || refetchingQuiz
  const refetch = () => {
    void refetchTeam()
    void refetchQuiz()
  }

  // Extract all distinct topics from questions list
  const availableTopics = useMemo(() => {
    if (!analysis?.questions) return []
    const topicSet = new Set<string>()
    for (const q of analysis.questions) {
      if (selectedQuizId !== "all" && q.quiz_id !== selectedQuizId) continue
      if (q.topic) topicSet.add(q.topic)
    }
    return Array.from(topicSet).sort()
  }, [analysis?.questions, selectedQuizId])

  // Filter and sort questions list
  const filteredAndSortedQuestions = useMemo(() => {
    if (!analysis?.questions) return []
    let list = [...analysis.questions]

    // 1. Filter by Quiz (synced with top Evaluation Scope)
    if (selectedQuizId !== "all") {
      list = list.filter((q) => q.quiz_id === selectedQuizId)
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
          return (a.accuracy_pct ?? 0) - (b.accuracy_pct ?? 0)
        case "most_right":
          if (b.correct_count !== a.correct_count) {
            return b.correct_count - a.correct_count
          }
          return (b.accuracy_pct ?? 0) - (a.accuracy_pct ?? 0)
        case "lowest_accuracy":
          if (a.accuracy_pct !== b.accuracy_pct) {
            if (a.accuracy_pct === null) return 1
            if (b.accuracy_pct === null) return -1
            return a.accuracy_pct - b.accuracy_pct
          }
          return b.incorrect_count - a.incorrect_count
        case "highest_accuracy":
          if (b.accuracy_pct !== a.accuracy_pct) {
            if (a.accuracy_pct === null) return 1
            if (b.accuracy_pct === null) return -1
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
  }, [analysis?.questions, selectedQuizId, questionTopicFilter, questionSearch, questionSortBy])

  const rosterToggle = (
    <div className="flex items-center gap-1 p-1 rounded-xl border border-border bg-muted/40 w-fit">
      <button
        type="button"
        onClick={() => setRosterMode("student")}
        className={`px-3 py-1 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
          rosterMode === "student" ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"
        }`}
      >
        Students
      </button>
      <button
        type="button"
        onClick={() => setRosterMode("observer")}
        className={`px-3 py-1 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
          rosterMode === "observer" ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"
        }`}
      >
        Observers
      </button>
      <button
        type="button"
        onClick={() => setRosterMode("all")}
        className={`px-3 py-1 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
          rosterMode === "all" ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"
        }`}
      >
        All
      </button>
    </div>
  )

  if (isLoading) return <Spinner />

  const ind = teamAnalytics?.individual_summary
  const hasQuizData = Boolean(analysis && analysis.total_attempts > 0)

  const currentQuiz =
    selectedQuizId !== "all" && analysis
      ? analysis.quizzes.find((q) => q.quiz_id === selectedQuizId)
      : null

  const activeTopicBreakdown = currentQuiz
    ? currentQuiz.topic_breakdown
    : (analysis?.overall_topic_breakdown ?? {})

  const activeAttempts = currentQuiz ? currentQuiz.total_attempts : (analysis?.total_attempts ?? 0)
  const activeAvgScore = currentQuiz ? currentQuiz.average_score_pct : (analysis?.overall_average_score_pct ?? 0)
  const topicsCount = Object.keys(activeTopicBreakdown).length

  const registeredVal = ind?.registered_count ?? 0
  const startedVal = ind?.started_count ?? 0
  const completedVal = ind?.completed_count ?? 0

  const individualItems = (teamAnalytics?.items ?? []).filter((i) => !i.optional && i.scope === "individual")
  const individualMissions = (teamAnalytics?.missions ?? []).filter((m) => m.scope === "individual")
  const indBottleneck = computeBottleneck(individualItems)
  const indSubmittedCount = individualItems.reduce((acc, i) => acc + i.done + i.awaiting, 0)
  const indTotalPossible = individualItems.reduce((acc, i) => acc + i.total, 0)
  const indSubmissionRate =
    indTotalPossible > 0 ? Math.round((indSubmittedCount / indTotalPossible) * 1000) / 10 : 0

  return (
    <div className="flex flex-col gap-5">
      {/* Top Bar: Roster Mode + Quiz Scope + Refresh */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 bg-card border border-border rounded-xl">
        <div className="flex items-center gap-3 flex-wrap">
          {rosterToggle}
          {hasQuizData && analysis && analysis.quizzes.length > 0 && (
            <>
              <div className="h-5 w-px bg-border hidden sm:block" />
              <div className="flex items-center gap-2">
                <Layers size={15} className="text-muted-foreground" />
                <select
                  value={selectedQuizId}
                  onChange={(e) => {
                    setSelectedQuizId(e.target.value)
                    setQuestionTopicFilter("all")
                  }}
                  className="bg-background border border-border text-foreground text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary font-medium"
                >
                  <option value="all">All Quizzes ({analysis.total_attempts} submissions)</option>
                  {analysis.quizzes.map((q) => (
                    <option key={q.quiz_id} value={q.quiz_id}>
                      {q.quiz_title} ({q.total_attempts} submissions)
                    </option>
                  ))}
                </select>
              </div>
            </>
          )}
        </div>

        <button
          onClick={() => refetch()}
          disabled={isRefetching}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground bg-background border border-border rounded-lg transition disabled:opacity-50 cursor-pointer self-start sm:self-auto"
        >
          <RefreshCw size={13} className={isRefetching ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Executive Individual Funnel */}
      <AnalysisFunnelWidget
        stages={[
          { label: "Registered", value: registeredVal, weight: Math.max(registeredVal, 1) },
          { label: "Started", value: startedVal, weight: startedVal },
          { label: "Completed", value: completedVal, weight: completedVal },
        ]}
        sideCards={[
          {
            title: "Submission rate",
            badge: "Live",
            subtitle: `${indSubmittedCount} / ${indTotalPossible} items`,
            value: indTotalPossible > 0 ? `${indSubmissionRate}%` : "—",
            ok: indTotalPossible > 0 ? indSubmissionRate >= 60 : undefined,
          },
          {
            title: "Avg completion",
            subtitle: `${ind?.never_logged_in_count ?? 0} never logged in`,
            value: `${ind?.avg_pct ?? 0}%`,
            ok: (ind?.avg_pct ?? 0) >= 60,
          },
          {
            title: "Quiz mastery",
            subtitle: activeAttempts > 0 ? `${activeAttempts} submissions` : "No submissions yet",
            value: activeAttempts > 0 ? `${activeAvgScore}%` : "—",
            ok: activeAttempts > 0 ? activeAvgScore >= 70 : undefined,
          },
        ]}
      />

      {individualItems.length > 0 && (
        <SectionCard
          title="Individual items completion rate"
          action={
            indBottleneck ? (
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/30">
                <AlertTriangle size={13} />
                Bottleneck: {indBottleneck.title} (-{indBottleneck.dropPct}%)
              </span>
            ) : undefined
          }
        >
          <CompletionRateChart items={individualItems} isDark={isDark} />
        </SectionCard>
      )}

      {individualMissions.length > 0 && (
        <MissionsBlock missions={individualMissions} isDark={isDark} />
      )}

      {!hasQuizData || !analysis ? (
        <EmptyState
          title={
            rosterMode === "observer"
              ? "No observer quiz submissions yet"
              : rosterMode === "all"
              ? "No quiz submissions yet"
              : "No student quiz submissions yet"
          }
        />
      ) : (
        <>

      {/* ── Block 1: Strengths & Weaknesses by Topic Card ─────────────────── */}
      <div className="flex flex-col gap-4 p-5 bg-card border border-border rounded-2xl">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Topic Mastery</h3>
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

      {/* ── Block 2: Questions Breakdown (Right vs Wrong vs Timed Out) ─────── */}
      <div className="flex flex-col gap-4 p-5 bg-card border border-border rounded-2xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">Questions Breakdown</h3>
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium">
              {filteredAndSortedQuestions.length}
            </span>
          </div>
        </div>

        {/* Filter & Sort Controls */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 p-3 rounded-xl bg-muted/30 border border-border/70 text-xs">
          {/* Topic Filter */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wider flex items-center gap-1">
              <Filter size={11} /> Topic
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
              const wrongSelected = q.wrong_selected_count ?? q.incorrect_count
              const timeoutCount = q.timeout_count ?? 0
              const wrongPct = q.total_answers > 0 ? Math.round((wrongSelected / q.total_answers) * 100) : 0
              const timeoutPct = q.total_answers > 0 ? Math.round((timeoutCount / q.total_answers) * 100) : 0
              const textResponses = q.text_responses ?? []
              const qKey = `${q.question_id}-${q.quiz_id}-${idx}`
              const textExpanded = Boolean(expandedTextIds[qKey])
              return (
                <div
                  key={qKey}
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
                    {q.accuracy_pct === null ? (
                      <div className="flex items-center gap-3 flex-wrap">
                        <span className="inline-flex items-center gap-1 font-semibold text-primary bg-primary/10 px-2.5 py-1 rounded-full">
                          Open-ended
                        </span>
                        <span className="text-muted-foreground text-[11px] font-mono">
                          {q.total_answers} {q.total_answers === 1 ? "response" : "responses"}
                        </span>
                        {textResponses.length > 0 && (
                          <button
                            type="button"
                            onClick={() => setExpandedTextIds((prev) => ({ ...prev, [qKey]: !prev[qKey] }))}
                            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline cursor-pointer"
                          >
                            <MessageSquare size={12} />
                            {textExpanded ? "Hide responses" : `View responses (${textResponses.length})`}
                            {textExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                          </button>
                        )}
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 flex-wrap">
                        {/* Right Count */}
                        <span className="inline-flex items-center gap-1 font-semibold text-emerald-500 bg-emerald-500/10 px-2.5 py-1 rounded-full">
                          <CheckCircle2 size={13} />
                          {q.correct_count} Right ({q.accuracy_pct}%)
                        </span>

                        {/* Wrong Selected Count */}
                        <span className="inline-flex items-center gap-1 font-semibold text-rose-500 bg-rose-500/10 px-2.5 py-1 rounded-full">
                          <XCircle size={13} />
                          {wrongSelected} Wrong ({wrongPct}%)
                        </span>

                        {/* Timed Out Count */}
                        {timeoutCount > 0 && (
                          <span className="inline-flex items-center gap-1 font-semibold text-amber-500 bg-amber-500/10 px-2.5 py-1 rounded-full">
                            <Clock size={13} />
                            {timeoutCount} Timed Out ({timeoutPct}%)
                          </span>
                        )}

                        <span className="text-muted-foreground text-[11px] font-mono">
                          {q.total_answers} total
                        </span>
                      </div>
                    )}

                    {/* Visual 3-Segment Progress Bar */}
                    {q.accuracy_pct === null ? (
                      <div className="flex items-center gap-2 w-full sm:w-48 shrink-0 justify-end">
                        <span className="text-[11px] font-medium text-muted-foreground italic">
                          Ungraded
                        </span>
                      </div>
                    ) : (
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
                            title={`${wrongSelected} Wrong (${wrongPct}%)`}
                          />
                          {timeoutPct > 0 && (
                            <div
                              className="h-full bg-amber-500 transition-all"
                              style={{ width: `${timeoutPct}%` }}
                              title={`${timeoutCount} Timed Out (${timeoutPct}%)`}
                            />
                          )}
                        </div>
                        <span className="text-[11px] font-mono font-semibold text-muted-foreground shrink-0 w-8 text-right">
                          {q.accuracy_pct}%
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Expandable Open-Ended Text Responses */}
                  {q.accuracy_pct === null && textExpanded && textResponses.length > 0 && (
                    <div className="mt-1 pt-3 border-t border-border/60 flex flex-col gap-2 max-h-64 overflow-y-auto">
                      {textResponses.map((resp, rIdx) => (
                        <div key={`${resp.user_id}-${rIdx}`} className="p-2.5 rounded-lg bg-muted/40 border border-border/60 text-xs">
                          <span className="font-semibold text-foreground">{resp.student_name}: </span>
                          <span className="text-muted-foreground whitespace-pre-wrap">{resp.text}</span>
                        </div>
                      ))}
                    </div>
                  )}
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
        </>
      )}
    </div>
  )
}
