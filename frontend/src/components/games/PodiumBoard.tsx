import { Medal, Trophy } from "lucide-react"
import { cn } from "@/lib/utils"

/** Final standings — podium blocks for the top 3, a ranked list for
 * everyone else (Live Games Phase 2C, 8-8b, D19). Shared between the
 * instructor's projected screen and each student's own phone; the two
 * differ only in what's passed in (`revealedNames`/`onToggleReveal` is
 * instructor-only, D9's global reveal; `ownParticipantId` is student-only,
 * highlighting their own row). Podium heights and left-to-right order
 * (2nd, 1st, 3rd) match the operator's own reference image. */

export interface PodiumEntry {
  participant_id: string
  nickname: string
  avatar: string | null
  score: number
}

const MEDAL_SHADES = ["text-amber-500", "text-zinc-400", "text-amber-700 dark:text-amber-600"]
const PODIUM_HEIGHTS = ["h-28", "h-36", "h-20"] // rendered in visual order: 2nd, 1st, 3rd
const PODIUM_ORDER = [1, 0, 2] // indices into a top-3 array, for the 2nd/1st/3rd layout

export function PodiumBoard({
  entries, ownParticipantId, revealedNames,
}: {
  entries: PodiumEntry[]
  ownParticipantId?: string
  revealedNames?: Record<string, string>
}) {
  const top3 = entries.slice(0, 3)
  const rest = entries.slice(3)

  const label = (e: PodiumEntry) => revealedNames?.[e.participant_id] ?? e.nickname

  return (
    <div className="flex flex-col gap-6">
      {top3.length > 0 && (
        <div className="flex items-end justify-center gap-3">
          {PODIUM_ORDER.filter((i) => top3[i]).map((i) => {
            const entry = top3[i]
            const isMe = entry.participant_id === ownParticipantId
            return (
              <div key={entry.participant_id} className="flex flex-col items-center gap-2 w-24">
                <Medal className={cn("size-6", MEDAL_SHADES[i])} />
                <p className={cn("text-xs font-semibold truncate w-full text-center", isMe && "text-primary")}>
                  {label(entry)}{isMe && " (you)"}
                </p>
                <p className="font-display text-sm font-bold">{entry.score}</p>
                <div
                  className={cn(
                    "w-full rounded-t-xl border-2 flex items-start justify-center pt-2",
                    PODIUM_HEIGHTS[i],
                    isMe ? "border-primary bg-primary/10" : "border-border bg-card",
                  )}
                >
                  <span className="font-display text-lg font-extrabold text-muted-foreground">{i + 1}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {rest.length > 0 && (
        <div className="flex flex-col gap-1.5">
          {rest.map((entry, i) => {
            const isMe = entry.participant_id === ownParticipantId
            return (
              <div
                key={entry.participant_id}
                className={cn(
                  "flex items-center gap-3 rounded-xl border p-3",
                  isMe ? "border-primary/40 bg-primary/5" : "border-border bg-card",
                )}
              >
                <span className="w-6 text-center text-sm font-bold text-muted-foreground">{i + 4}</span>
                <span className="flex-1 text-sm font-medium truncate">
                  {label(entry)}{isMe && <span className="ml-1.5 font-normal text-muted-foreground">(you)</span>}
                </span>
                <span className="font-display font-bold text-sm">{entry.score}</span>
              </div>
            )
          })}
        </div>
      )}

      {entries.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
          <Trophy className="size-8" /> No one scored any points.
        </div>
      )}
    </div>
  )
}
