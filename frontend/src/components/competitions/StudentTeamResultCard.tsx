import { useQuery } from "@tanstack/react-query"
import {
  Award,
  CheckCircle2,
  Clock,
  FileText,
  Layers,
  MessageSquare,
  Quote,
  ShieldCheck,
  Trophy,
} from "lucide-react"
import { getStudentCompetitionResultApi, type CompetitionStudentResult } from "@/api/competitions"

interface StudentTeamResultCardProps {
  cohortId: string
}

export function StudentTeamResultCard({ cohortId }: StudentTeamResultCardProps) {
  const { data: result, isLoading } = useQuery<CompetitionStudentResult>({
    queryKey: ["competitions-student-result", cohortId],
    queryFn: () => getStudentCompetitionResultApi(cohortId),
    staleTime: 60_000,
  })

  if (isLoading || !result || !result.published) {
    return null
  }

  const isTop10 = result.qualification?.toLowerCase().includes("top 10")
  const isTopTier = result.qualification?.toLowerCase().includes("top")

  const hasScore = result.final_score !== null && result.final_score !== undefined
  const hasRank = result.rank !== null && result.rank !== undefined
  const hasCriteria = !!result.criteria_breakdown && result.criteria_breakdown.length > 0
  const hasOpsBreakdown = !!result.ops_breakdown && result.ops_breakdown.length > 0
  const hasOpsScore = result.ops_score !== null && result.ops_score !== undefined
  const hasOpsComments = !!result.ops_comments?.trim()
  const hasJudgeGeneralComments = !!result.judge_comments && result.judge_comments.length > 0
  const hasJudgeCriteriaComments = !!result.judge_criteria_comments && result.judge_criteria_comments.length > 0
  const hasJudgeComments = hasJudgeGeneralComments || hasJudgeCriteriaComments

  return (
    <div className="relative overflow-hidden rounded-2xl border border-primary/20 bg-gradient-to-br from-card via-card to-primary/5 p-5 sm:p-6 shadow-sm flex flex-col gap-6">
      {/* Top Banner / Summary */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-start gap-3.5">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary border border-primary/20">
            {isTop10 ? <Trophy className="size-6 text-amber-500" /> : <Award className="size-6 text-primary" />}
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-display text-lg sm:text-xl font-bold text-foreground">
                {result.team_name}
              </h3>
              {result.qualification && (
                <span
                  className={`inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider rounded-full px-2.5 py-0.5 border ${
                    isTop10
                      ? "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30"
                      : isTopTier
                      ? "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/30"
                      : "bg-muted text-muted-foreground border-border"
                  }`}
                >
                  <CheckCircle2 size={12} /> {result.qualification}
                </span>
              )}
              {result.timing_badge && (
                <span className={`inline-flex items-center gap-1 text-xs font-medium rounded-full px-2.5 py-0.5 border ${
                  (result.timing_adjustment ?? 0) < 0
                    ? "text-rose-700 dark:text-rose-400 bg-rose-500/10 border-rose-500/30"
                    : "text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/30"
                }`}>
                  <Clock size={12} /> {result.timing_badge}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Official Competition Result · Published Evaluation
            </p>
          </div>
        </div>

        {/* Score & Rank Highlights */}
        {(hasScore || hasRank) && (
          <div className="flex items-center sm:justify-end gap-6 pt-3 sm:pt-0 border-t sm:border-t-0 border-border/50">
            {hasRank && (
              <div className="flex flex-col items-start sm:items-end">
                <div className="text-[11px] uppercase font-semibold tracking-wider text-muted-foreground flex items-center gap-1">
                  <Trophy size={11} className="text-primary" /> Placement
                </div>
                <div className="font-display text-xl sm:text-2xl font-extrabold text-foreground tabular-nums">
                  #{result.rank}
                  {result.total_teams && (
                    <span className="text-xs font-medium text-muted-foreground ml-1 font-sans">
                      of {result.total_teams}
                    </span>
                  )}
                </div>
              </div>
            )}

            {hasScore && (
              <div className="flex flex-col items-start sm:items-end border-l pl-5 sm:pl-6 border-border/60">
                <div className="text-[11px] uppercase font-semibold tracking-wider text-muted-foreground">
                  Final Score
                </div>
                <div className="font-display text-2xl sm:text-3xl font-extrabold text-foreground tabular-nums">
                  {result.final_score}
                  {result.score_percent !== null && result.score_percent !== undefined && (
                    <span className="text-xs font-semibold text-muted-foreground ml-1.5 font-sans">
                      ({result.score_percent}%)
                    </span>
                  )}
                </div>
                {result.timing_adjustment ? (
                  <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">
                    +{result.timing_adjustment} timing adjustment
                  </span>
                ) : null}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Criteria Breakdown Section */}
      {hasCriteria && (
        <div className="flex flex-col gap-3 pt-4 border-t border-border/60">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
                <Layers size={14} />
              </div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">
                Rubric Criteria Breakdown
              </h4>
            </div>
            <span className="text-[11px] text-muted-foreground font-medium">
              Judges' average awarded points
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {result.criteria_breakdown!.map((criterion) => {
              const awarded = criterion.average_points ?? 0
              const max = criterion.max_points
              const pct = max > 0 ? Math.min(100, Math.max(0, Math.round((awarded / max) * 100))) : 0

              return (
                <div
                  key={criterion.key}
                  className="rounded-xl border border-border/70 bg-card/60 p-3.5 flex flex-col gap-2 shadow-xs"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-sm font-semibold text-foreground leading-tight">
                      {criterion.label}
                    </span>
                    <span className="text-xs font-bold text-foreground tabular-nums whitespace-nowrap">
                      {criterion.average_points !== null && criterion.average_points !== undefined
                        ? criterion.average_points
                        : "—"}{" "}
                      <span className="font-normal text-muted-foreground">/ {max} pts</span>
                    </span>
                  </div>

                  {/* Progress bar */}
                  <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full transition-all duration-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>

                  {/* Sub-criteria if present */}
                  {criterion.subs && criterion.subs.length > 0 && (
                    <div className="mt-1 pt-2 border-t border-border/40 flex flex-col gap-1">
                      {criterion.subs.map((sub) => (
                        <div key={sub.key} className="flex items-center justify-between text-xs text-muted-foreground">
                          <span className="truncate pr-2">{sub.label}</span>
                          <span className="tabular-nums shrink-0 font-medium">
                            {sub.awarded_points !== null && sub.awarded_points !== undefined
                              ? `${sub.awarded_points} / ${sub.max_points}`
                              : `Max ${sub.max_points} pts`}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Operations Evaluation Section */}
      {(hasOpsBreakdown || hasOpsScore) && (
        <div className="flex flex-col gap-3 pt-4 border-t border-border/60">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                <ShieldCheck size={14} />
              </div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">
                Operations Evaluation
              </h4>
            </div>
            {hasOpsScore && (
              <span className="text-xs font-bold text-foreground tabular-nums">
                {result.ops_score}
                {result.ops_max_points ? (
                  <span className="font-normal text-muted-foreground"> / {result.ops_max_points} pts</span>
                ) : (
                  <span className="font-normal text-muted-foreground"> pts</span>
                )}
              </span>
            )}
          </div>

          {hasOpsBreakdown && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {result.ops_breakdown!.map((criterion) => {
                const awarded = criterion.awarded_points ?? 0
                const max = criterion.max_points
                const pct = max > 0 ? Math.min(100, Math.max(0, Math.round((awarded / max) * 100))) : 0

                return (
                  <div
                    key={criterion.key}
                    className="rounded-xl border border-border/70 bg-card/60 p-3.5 flex flex-col gap-2 shadow-xs"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-semibold text-foreground leading-tight">
                        {criterion.label}
                      </span>
                      <span className="text-xs font-bold text-foreground tabular-nums whitespace-nowrap">
                        {criterion.awarded_points !== null && criterion.awarded_points !== undefined
                          ? criterion.awarded_points
                          : "—"}{" "}
                        <span className="font-normal text-muted-foreground">/ {max} pts</span>
                      </span>
                    </div>

                    <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full bg-emerald-500 rounded-full transition-all duration-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Operations Comments & Notes Section */}
      {hasOpsComments && (
        <div className="flex flex-col gap-2.5 pt-4 border-t border-border/60">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
              <MessageSquare size={14} />
            </div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">
              Operations Feedback
            </h4>
          </div>
          <div className="rounded-xl border border-primary/20 bg-primary/[0.04] p-4 text-sm text-foreground leading-relaxed whitespace-pre-wrap">
            {result.ops_comments}
          </div>
        </div>
      )}

      {/* Judges' Qualitative Comments Section */}
      {hasJudgeComments && (
        <div className="flex flex-col gap-3 pt-4 border-t border-border/60">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">
              <FileText size={14} />
            </div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">
              Judges' Qualitative Comments
            </h4>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {result.judge_comments?.map((comment, idx) => (
              <div
                key={`judge-note-${idx}`}
                className="rounded-xl border border-border/70 bg-card/70 p-4 flex flex-col gap-2 shadow-xs"
              >
                <div className="flex items-center gap-1.5 text-xs text-primary font-medium">
                  <Quote size={12} className="opacity-80" />
                  <span>Judge Note #{idx + 1}</span>
                </div>
                <p className="text-xs sm:text-sm text-foreground/90 italic leading-relaxed whitespace-pre-wrap">
                  "{comment}"
                </p>
              </div>
            ))}

            {result.judge_criteria_comments?.map((item, idx) => (
              <div
                key={`judge-crit-comment-${idx}`}
                className="rounded-xl border border-border/70 bg-card/70 p-3.5 flex flex-col gap-1.5 shadow-xs"
              >
                <span className="text-xs font-semibold text-primary">{item.criterion}</span>
                <p className="text-xs text-foreground/90 italic leading-relaxed whitespace-pre-wrap">
                  "{item.comment}"
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
