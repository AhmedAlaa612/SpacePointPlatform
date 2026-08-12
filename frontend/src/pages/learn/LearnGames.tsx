import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Trophy, Play } from "lucide-react"
import { getJoinableRunsApi } from "@/api/games_play"

/** Live Quiz — student entry point (Live Games Phase 2C, 8-8, D5): its
 * own top-level surface, not a course-module item. Lists any game
 * currently open (lobby or live) for a cohort the student is registered
 * in — joining just drops them straight into the play screen, which
 * itself handles the lobby wait if the instructor hasn't hit Start yet. */
export default function LearnGames() {
  const navigate = useNavigate()
  const { data: runs = [], isLoading } = useQuery({
    queryKey: ["games-joinable"],
    queryFn: getJoinableRunsApi,
    refetchInterval: 5000,
  })

  return (
    <div className="mx-auto max-w-[720px] px-5 sm:px-8 py-6 sm:py-10 flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-primary/30 bg-primary/10 text-primary">
          <Trophy className="size-5" />
        </div>
        <div>
          <h1 className="font-display text-2xl font-extrabold tracking-tight">Live Quiz</h1>
          <p className="text-sm text-muted-foreground">Games your instructor has open right now.</p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-20 rounded-2xl bg-muted animate-pulse" />
          ))}
        </div>
      ) : runs.length === 0 ? (
        <div className="rounded-2xl border border-border bg-card p-10 text-center text-sm text-muted-foreground">
          Nothing open right now — check back once your instructor starts one.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {runs.map((run) => (
            <div key={run.run_id} className="flex items-center gap-4 rounded-2xl border border-border bg-card p-4">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-foreground truncate">{run.game_title}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {run.status === "live" ? "In progress" : "Waiting to start"}
                  {run.session_title ? ` · ${run.session_title}` : ""}
                </p>
              </div>
              <button
                onClick={() => void navigate({ to: "/learn/games/$runId", params: { runId: run.run_id } })}
                className="h-10 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-semibold hover:opacity-90 transition-colors flex items-center gap-1.5 shrink-0"
              >
                <Play size={14} /> Join
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
