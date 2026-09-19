import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { CheckCircle2, Circle, Lock, Users } from "lucide-react"
import { getMyJudgeCohortsApi, getMyJudgeTeamsApi, type CompetitionJudgeCohort } from "@/api/competitions"
import { PageHeader, Spinner, EmptyState } from "@/components/ui/primitives"

function formatLockTimestamp(iso: string | null | undefined): string {
  if (!iso) return ""
  const d = new Date(iso)
  return `${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })} ${d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`
}

/** Judge landing page (Competition domain, 2026-08-24) — pick a cohort
 * (usually just one), see its teams, jump into scoring. A judge with no
 * `CompetitionJudge` row anywhere sees the empty state, not an error —
 * that's a normal state for an invited-but-not-yet-assigned account. */
export default function JudgeTeams() {
  const { data: cohorts = [], isLoading: cohortsLoading } = useQuery<CompetitionJudgeCohort[]>({
    queryKey: ["judge-cohorts"],
    queryFn: getMyJudgeCohortsApi,
  })
  const [cohortId, setCohortId] = useState<string | null>(null)

  useEffect(() => {
    if (!cohortId && cohorts.length > 0) setCohortId(cohorts[0].id)
  }, [cohorts, cohortId])

  const { data: teams = [], isLoading: teamsLoading } = useQuery({
    queryKey: ["judge-teams", cohortId],
    queryFn: () => getMyJudgeTeamsApi(cohortId!),
    enabled: !!cohortId,
  })

  if (cohortsLoading) return <Spinner />
  if (cohorts.length === 0) {
    return <EmptyState title="No competitions assigned yet" hint="Ask ops to add you as a judge for a cohort." />
  }

  const activeCohort = cohorts.find((c) => c.id === cohortId) ?? cohorts[0]

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Teams to judge"
        subtitle={activeCohort ? `${activeCohort.program_name} · ${activeCohort.name}` : undefined}
      />

      {cohorts.length > 1 && (
        <div className="flex gap-1 border-b border-border">
          {cohorts.map((c) => (
            <button
              key={c.id}
              onClick={() => setCohortId(c.id)}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                c.id === cohortId ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {c.name}
            </button>
          ))}
        </div>
      )}

      {teamsLoading ? (
        <Spinner />
      ) : teams.length === 0 ? (
        <EmptyState title="No teams yet" hint="Teams appear here once they're formed for this cohort." />
      ) : (
        <div className="flex flex-col gap-2">
          {teams.map((team) => (
            <Link
              key={team.id}
              to="/judge/teams/$teamId"
              params={{ teamId: team.id }}
              className="flex items-center justify-between p-4 bg-card border border-border rounded-2xl hover:border-primary/40 transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0">
                <Users size={16} className="text-muted-foreground shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{team.name}</p>
                  <p className="text-xs text-muted-foreground truncate">
                    {team.member_names.join(", ") || "No members yet"}
                  </p>
                </div>
              </div>
              <div className="flex flex-col items-end gap-1 shrink-0 text-right">
                {team.already_scored ? (
                  <span className="flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                    <CheckCircle2 size={14} /> Scored
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Circle size={14} /> Not scored
                  </span>
                )}
                {team.locked && (
                  <span
                    className="flex items-center gap-1 text-xs text-muted-foreground"
                    title={team.locked_at ? `Locked on ${new Date(team.locked_at).toLocaleString()}` : undefined}
                  >
                    <Lock size={13} className="text-emerald-600 dark:text-emerald-400" />
                    <span>Final submission locked{team.locked_at ? ` (${formatLockTimestamp(team.locked_at)})` : ""}</span>
                  </span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
