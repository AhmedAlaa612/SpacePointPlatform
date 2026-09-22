import { useQuery } from "@tanstack/react-query"
import { Award, CheckCircle2, Trophy } from "lucide-react"
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

  return (
    <div className="relative overflow-hidden rounded-2xl border border-primary/20 bg-gradient-to-br from-card via-card to-primary/5 p-5 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-start gap-3.5">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary border border-primary/20">
            {isTop10 ? <Trophy className="size-6 text-amber-500" /> : <Award className="size-6 text-primary" />}
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-display text-lg font-bold text-foreground">{result.team_name}</h3>
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
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Official Qualifiers Result · Final evaluation score
            </p>
          </div>
        </div>

        <div className="flex items-baseline sm:flex-col sm:items-end gap-2 sm:gap-0 pl-15 sm:pl-0 border-t sm:border-t-0 pt-3 sm:pt-0 border-border/50">
          <div className="text-xs uppercase font-medium tracking-wider text-muted-foreground">Final Score</div>
          <div className="font-display text-2xl font-extrabold text-foreground tabular-nums">
            {result.final_score !== null ? result.final_score : "—"}
            {result.score_percent !== null && (
              <span className="text-sm font-semibold text-muted-foreground ml-1.5 font-sans">
                ({result.score_percent}%)
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
