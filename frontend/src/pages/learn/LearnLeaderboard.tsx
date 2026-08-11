import { useQuery } from "@tanstack/react-query"
import { Medal, Rocket, Trophy } from "lucide-react"
import { getLeaderboardApi } from "@/api/lms"
import { useAuth } from "@/context/AuthContext"
import { cn } from "@/lib/utils"

const MEDAL_SHADES = [
  "text-amber-500",
  "text-zinc-400",
  "text-amber-700 dark:text-amber-600",
]

/** 8-2 (Live Games Phase 2C, 2026-08-12) — the Stage 2 leaderboard,
 * finally linked into the frontend now that D6 (display-name policy) has
 * a real answer: nicknames (8-1). Global scope only for this first cut —
 * cohort scoping needs a "my cohort" picker /lms/my-programs never got a
 * frontend wrapper for either; out of scope for what 8-2 asked for. */
export default function LearnLeaderboard() {
  const { currentUser } = useAuth()
  const { data: rows = [], isLoading } = useQuery({
    queryKey: ["lms-leaderboard", "global"],
    queryFn: () => getLeaderboardApi("global"),
  })

  return (
    <div className="mx-auto max-w-[720px] px-5 sm:px-8 py-6 sm:py-10 flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-primary/30 bg-primary/10 text-primary">
          <Trophy className="size-5" />
        </div>
        <div>
          <h1 className="font-display text-2xl font-extrabold tracking-tight">Leaderboard</h1>
          <p className="text-sm text-muted-foreground">Top explorers by points earned, ranked by callsign.</p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-16 rounded-2xl bg-muted animate-pulse" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-2xl border border-border bg-card p-10 text-center text-sm text-muted-foreground">
          No one's scored any points yet — be the first.
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {rows.map((row) => {
            const isMe = row.user_id === currentUser?.id
            return (
              <div
                key={row.user_id}
                className={cn(
                  "flex items-center gap-4 rounded-2xl border p-4",
                  isMe ? "border-primary/40 bg-primary/5" : "border-border bg-card",
                )}
              >
                <span className="w-8 shrink-0 text-center font-display text-lg font-bold text-muted-foreground">
                  {row.rank <= 3 ? <Medal className={cn("mx-auto size-5", MEDAL_SHADES[row.rank - 1])} /> : row.rank}
                </span>
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-primary/30 bg-primary/10 text-primary">
                  <Rocket className="size-5" />
                </span>
                <span className="min-w-0 flex-1 truncate text-sm font-semibold">
                  {row.display_name}{isMe && <span className="ml-1.5 font-normal text-muted-foreground">(you)</span>}
                </span>
                <span className="font-display text-lg font-bold">{row.points.toLocaleString()}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
