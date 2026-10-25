import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Trophy, Play, Radio } from "lucide-react"
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
    <div className="mx-auto max-w-[800px] px-5 sm:px-8 py-8 sm:py-12 flex flex-col gap-8">
      {/* Header with floating icon (no container wrapper) */}
      <div className="flex items-center gap-4">
        <Trophy className="size-11 sm:size-12 text-lms-cta dark:text-lms-accent stroke-[1.75] shrink-0" />
        <div>
          <h1 className="font-['Outfit'] text-2xl sm:text-3xl lg:text-4xl font-extrabold tracking-tight text-foreground">
            Live Quiz
          </h1>
          <p className="text-sm sm:text-base text-muted-foreground font-medium mt-0.5">
            Active quiz games hosted by your instructors right now.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-24 rounded-2xl bg-muted/40 animate-pulse border border-border/60" />
          ))}
        </div>
      ) : runs.length === 0 ? (
        <div className="lms-card rounded-2xl border border-border/80 dark:border-lms-accent-border/30 bg-muted/10 dark:bg-[#0d0915] p-12 text-center flex flex-col items-center gap-3 shadow-lg shadow-black/10">
          <Radio className="size-10 text-muted-foreground/60 stroke-[1.5] animate-pulse" />
          <h2 className="font-['Outfit'] text-lg font-bold text-foreground">
            No live games open right now
          </h2>
          <p className="text-sm text-muted-foreground max-w-md">
            When an instructor starts a live quiz session for your cohort, it will appear here instantly.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {runs.map((run) => (
            <div
              key={run.run_id}
              className="lms-card flex items-center justify-between gap-4 rounded-2xl border border-border/80 dark:border-lms-accent-border/30 bg-muted/10 dark:bg-[#0d0915] p-5 sm:p-6 transition-all duration-300 hover:shadow-xl hover:shadow-black/20 hover:border-lms-cta dark:hover:border-lms-accent"
            >
              <div className="min-w-0 flex-1 flex flex-col gap-1.5">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                    <span className="size-2 rounded-full bg-emerald-400 animate-ping" />
                    {run.status === "live" ? "Live" : "Lobby"}
                  </span>
                  {run.session_title && (
                    <span className="text-xs text-muted-foreground font-medium">
                      {run.session_title}
                    </span>
                  )}
                </div>
                <h3 className="font-['Outfit'] text-lg sm:text-xl font-bold text-foreground truncate">
                  {run.game_title}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => void navigate({ to: "/learn/games/$runId", params: { runId: run.run_id } })}
                className="lms-btn-primary h-11 px-6 rounded-xl font-bold text-sm flex items-center gap-2 shrink-0 cursor-pointer"
              >
                <Play size={15} className="fill-current" /> Join Game
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
