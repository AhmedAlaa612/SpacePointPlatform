import { useEffect, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { CheckCircle2, ChevronRight, Circle, Lock, Search } from "lucide-react"
import { getMyJudgeCohortsApi, getMyJudgeTeamsApi, type CompetitionJudgeCohort, type CompetitionJudgeTeam } from "@/api/competitions"
import { PageHeader, Spinner, EmptyState } from "@/components/ui/primitives"

function formatLockTimestamp(iso: string | null | undefined): string {
  if (!iso) return ""
  const d = new Date(iso)
  return `${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })} ${d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`
}

type LockedFilter = "all" | "locked" | "unlocked"
type SortKey = "submissions" | "name" | "scored"

/** Judge landing page (Competition domain) — pick a cohort, see its teams,
 * jump into scoring. Teams are sorted by submissions (locked on top, mirroring
 * the Analysis tab), searchable by name/members, and filterable by locked status. */
export default function JudgeTeams() {
  const { data: cohorts = [], isLoading: cohortsLoading } = useQuery<CompetitionJudgeCohort[]>({
    queryKey: ["judge-cohorts"],
    queryFn: getMyJudgeCohortsApi,
  })
  const [cohortId, setCohortId] = useState<string | null>(null)
  const [mode, setMode] = useState<"participant" | "observer" | "all">("participant")
  const [search, setSearch] = useState("")
  const [lockedFilter, setLockedFilter] = useState<LockedFilter>("all")
  const [sort, setSort] = useState<SortKey>("submissions")

  useEffect(() => {
    if (!cohortId && cohorts.length > 0) setCohortId(cohorts[0].id)
  }, [cohorts, cohortId])

  const { data: teams = [], isLoading: teamsLoading } = useQuery<CompetitionJudgeTeam[]>({
    queryKey: ["judge-teams", cohortId, mode],
    queryFn: () => getMyJudgeTeamsApi(cohortId!, mode),
    enabled: !!cohortId,
  })

  const lockedCount = useMemo(() => teams.filter((t) => t.locked).length, [teams])
  const unlockedCount = teams.length - lockedCount

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase()
    const matching = teams.filter((team) => {
      if (lockedFilter === "locked" && !team.locked) return false
      if (lockedFilter === "unlocked" && team.locked) return false
      if (!q) return true
      return (
        team.name.toLowerCase().includes(q) ||
        (team.roster_team_id && team.roster_team_id.toLowerCase().includes(q)) ||
        (team.member_names && team.member_names.some((m) => m.toLowerCase().includes(q)))
      )
    })

    const sorted = [...matching]
    if (sort === "submissions") {
      sorted.sort((a, b) => {
        // Locked on top
        const lockDiff = (b.locked ? 1 : 0) - (a.locked ? 1 : 0)
        if (lockDiff !== 0) return lockDiff
        // Submissions completion %
        const pctDiff = (b.pct ?? 0) - (a.pct ?? 0)
        if (pctDiff !== 0) return pctDiff
        // Completed items count
        const doneDiff = (b.items_done ?? 0) - (a.items_done ?? 0)
        if (doneDiff !== 0) return doneDiff
        return a.name.localeCompare(b.name)
      })
    } else if (sort === "name") {
      sorted.sort((a, b) => a.name.localeCompare(b.name))
    } else if (sort === "scored") {
      sorted.sort((a, b) => {
        const scoredDiff = (a.already_scored ? 1 : 0) - (b.already_scored ? 1 : 0)
        if (scoredDiff !== 0) return scoredDiff
        const lockDiff = (b.locked ? 1 : 0) - (a.locked ? 1 : 0)
        if (lockDiff !== 0) return lockDiff
        return a.name.localeCompare(b.name)
      })
    }
    return sorted
  }, [teams, search, lockedFilter, sort])

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
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors cursor-pointer ${
                c.id === cohortId ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {c.name}
            </button>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-4">
        {/* Controls: Search, Mode filter, Filter by Locked, and Sort */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="relative flex-1 min-w-[200px] max-w-md">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by team or member name…"
              className="w-full h-9 pl-8 pr-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Mode filter (Students / Observers / All) */}
            <div className="flex items-center p-1 bg-muted/60 border border-border/80 rounded-xl text-xs">
              <button
                type="button"
                onClick={() => setMode("participant")}
                className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
                  mode === "participant"
                    ? "bg-background text-foreground shadow-xs font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Students
              </button>
              <button
                type="button"
                onClick={() => setMode("observer")}
                className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
                  mode === "observer"
                    ? "bg-background text-indigo-600 dark:text-indigo-400 shadow-xs font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Observers
              </button>
              <button
                type="button"
                onClick={() => setMode("all")}
                className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
                  mode === "all"
                    ? "bg-background text-foreground shadow-xs font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                All
              </button>
            </div>

            {/* Filter by locked */}
            {teams.length > 0 && (
              <div className="flex items-center p-1 bg-muted/60 border border-border/80 rounded-xl text-xs">
                <button
                  type="button"
                  onClick={() => setLockedFilter("all")}
                  className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
                    lockedFilter === "all"
                      ? "bg-background text-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  All ({teams.length})
                </button>
                <button
                  type="button"
                  onClick={() => setLockedFilter("locked")}
                  className={`flex items-center gap-1 px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
                    lockedFilter === "locked"
                      ? "bg-background text-emerald-600 dark:text-emerald-400 shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Lock size={12} />
                  Locked ({lockedCount})
                </button>
                <button
                  type="button"
                  onClick={() => setLockedFilter("unlocked")}
                  className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer ${
                    lockedFilter === "unlocked"
                      ? "bg-background text-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Unlocked ({unlockedCount})
                </button>
              </div>
            )}

            {/* Sort selector */}
            {teams.length > 0 && (
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value as SortKey)}
                className="h-9 px-2.5 border border-border bg-background rounded-xl text-xs font-medium text-foreground cursor-pointer focus:outline-none"
              >
                <option value="submissions">Sort: submissions</option>
                <option value="name">Sort: name</option>
                <option value="scored">Sort: scoring status</option>
              </select>
            )}
          </div>
        </div>

        {/* Content: Spinner, EmptyState, or Team List */}
        {teamsLoading ? (
          <Spinner />
        ) : teams.length === 0 ? (
          <div className="flex flex-col items-center gap-2">
            <EmptyState
              title={
                mode === "observer"
                  ? "No observer teams yet"
                  : mode === "participant"
                  ? "No student teams yet"
                  : "No teams yet"
              }
              hint={
                mode === "observer"
                  ? "Observer teams appear here once observers form teams for this cohort."
                  : mode === "participant"
                  ? "Student teams appear here once they're formed for this cohort. Switch to Observers to see observer teams."
                  : "Teams appear here once they're formed for this cohort."
              }
            />
            {mode === "participant" && (
              <button
                type="button"
                onClick={() => setMode("observer")}
                className="text-xs font-semibold text-primary hover:underline -mt-4 cursor-pointer"
              >
                Switch to Observers →
              </button>
            )}
          </div>
        ) : rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-8 bg-card border border-border rounded-2xl text-center">
            <p className="text-sm font-medium text-foreground">No teams match your search or filter</p>
            <p className="text-xs text-muted-foreground mt-1">Try clearing your search query or changing the filter</p>
            <button
              type="button"
              onClick={() => { setSearch(""); setLockedFilter("all") }}
              className="mt-3 text-xs font-semibold text-primary hover:underline cursor-pointer"
            >
              Reset filters
            </button>
          </div>
        ) : (
            <div className="flex flex-col gap-2">
              {rows.map((team) => {
                const done = team.items_done ?? 0
                const total = team.items_total ?? 0
                const pct = team.pct ?? (total > 0 ? Math.round((done / total) * 100) : 0)
                const memberCount = team.member_count ?? team.member_names?.length ?? 0

                return (
                  <Link
                    key={team.id}
                    to="/judge/teams/$teamId"
                    params={{ teamId: team.id }}
                    className="flex items-center justify-between p-3.5 sm:p-4 bg-card border border-border/70 rounded-2xl hover:border-primary/50 hover:bg-muted/20 transition-all gap-3 cursor-pointer"
                  >
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <div className="p-1 rounded-lg bg-muted/60 text-muted-foreground shrink-0">
                        <ChevronRight size={14} />
                      </div>

                      <div className="w-8 h-8 rounded-xl bg-primary/10 border border-primary/20 text-primary font-bold flex items-center justify-center text-xs shrink-0">
                        {team.name.trim().slice(0, 2).toUpperCase()}
                      </div>

                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                          <p className="text-sm font-semibold text-foreground truncate max-w-full">
                            {team.name}
                          </p>
                          {team.is_observer && (
                            <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border border-indigo-500/30">
                              Observer
                            </span>
                          )}
                          {team.roster_team_id && team.roster_team_id !== team.name && (
                            <span className="text-xs font-normal text-muted-foreground font-mono shrink-0">
                              ({team.roster_team_id})
                            </span>
                          )}
                          {team.locked && (
                            <span
                              className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 shrink-0"
                              title={team.locked_at ? `Locked on ${new Date(team.locked_at).toLocaleString()}` : "Final submission locked"}
                            >
                              <Lock size={11} />
                              Locked{team.locked_at ? ` at ${formatLockTimestamp(team.locked_at)}` : ""}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground truncate mt-0.5">
                          {memberCount} {memberCount === 1 ? "member" : "members"}
                        </p>
                      </div>
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center items-end gap-2 sm:gap-4 shrink-0">
                      <div className="w-24 sm:w-36 md:w-40 shrink-0">
                        <div className="flex items-center justify-between text-[11px] font-semibold tabular-nums mb-1">
                          <span className="text-muted-foreground">{done}/{total}</span>
                          <span className={pct === 100 ? "text-emerald-600 dark:text-emerald-400 font-bold" : "text-foreground font-bold"}>
                            {pct}%
                          </span>
                        </div>
                        <div className="h-2 rounded-full overflow-hidden bg-muted/60 border border-border/20">
                          <div
                            className="h-full rounded-full transition-all duration-300"
                            style={{
                              width: `${pct}%`,
                              backgroundColor: pct === 100 ? "#10b981" : "var(--primary, #9333ea)",
                            }}
                          />
                        </div>
                      </div>

                      <div className="flex items-center justify-end sm:min-w-[84px]">
                        {team.already_scored ? (
                          <span className="flex items-center gap-1 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                            <CheckCircle2 size={13} /> Scored
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-xs text-muted-foreground">
                            <Circle size={13} /> Not scored
                          </span>
                        )}
                      </div>
                    </div>
                  </Link>
                )
              })}
            </div>
          )}
        </div>
      </div>
    )
  }

