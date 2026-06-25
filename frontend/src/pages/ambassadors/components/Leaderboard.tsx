import { Medal } from "lucide-react"
import type { LeaderboardEntry } from "@/types/ambassadors"
import { cn } from "@/lib/utils"
import { EmptyState } from "./common"

// Monochrome podium shades for ranks 1, 2, 3.
const MEDAL_SHADES = [
  "text-zinc-900 dark:text-zinc-100",
  "text-zinc-500 dark:text-zinc-400",
  "text-zinc-400 dark:text-zinc-500",
]

export function LeaderboardTable({
  rows,
  highlightId,
  myRank,
  onRowClick,
}: {
  rows: LeaderboardEntry[]
  highlightId?: string
  myRank?: number
  onRowClick?: (id: string) => void
}) {
  if (!rows.length) return <EmptyState title="No leaderboard data yet" />

  const inTop = highlightId ? rows.some((r) => r.id === highlightId) : true

  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full text-sm min-w-[640px]">
        <thead>
          <tr className="text-left text-muted-foreground border-b border-gray-100 dark:border-zinc-800">
            <th className="py-2.5 pr-3 font-semibold">#</th>
            <th className="py-2.5 pr-3 font-semibold">Ambassador</th>
            <th className="py-2.5 pr-3 font-semibold">Country</th>
            <th className="py-2.5 pr-3 font-semibold text-center">Teachers</th>
            <th className="py-2.5 pr-3 font-semibold text-center">Sessions</th>
            <th className="py-2.5 pr-3 font-semibold text-center">Students</th>
            <th className="py-2.5 pr-3 font-semibold text-center">Converted</th>
            <th className="py-2.5 pr-3 font-semibold text-right">Points</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const me = r.id === highlightId
            return (
              <tr
                key={r.id}
                onClick={onRowClick ? () => onRowClick(r.id) : undefined}
                className={cn(
                  "border-b border-gray-50 dark:border-zinc-900 last:border-0",
                  me && "bg-snuff/20 dark:bg-snuff/10",
                  onRowClick && "cursor-pointer hover:bg-gray-50 dark:hover:bg-zinc-800/50"
                )}
              >
                <td className="py-2.5 pr-3 font-bold text-muted-foreground">
                  {i < 3 ? <Medal size={18} className={cn("inline", MEDAL_SHADES[i])} strokeWidth={2.2} /> : `#${i + 1}`}
                </td>
                <td className="py-2.5 pr-3 font-semibold text-foreground">{r.name}{me && " (you)"}</td>
                <td className="py-2.5 pr-3 text-muted-foreground">{r.country}</td>
                <td className="py-2.5 pr-3 text-center text-foreground">{r.teachers}</td>
                <td className="py-2.5 pr-3 text-center text-green-600 dark:text-green-400 font-semibold">{r.sessions_done}</td>
                <td className="py-2.5 pr-3 text-center text-foreground">{r.students_reached}</td>
                <td className="py-2.5 pr-3 text-center text-blue-600 dark:text-blue-400 font-semibold">{r.converted_leads}</td>
                <td className="py-2.5 pr-3 text-right font-bold text-affair dark:text-heliotrope">{r.points.toLocaleString()}</td>
              </tr>
            )
          })}
          {!inTop && myRank && (
            <tr className="border-t-2 border-heliotrope bg-snuff/30 dark:bg-snuff/15">
              <td className="py-2.5 pr-3 font-bold text-affair dark:text-heliotrope">#{myRank}</td>
              <td className="py-2.5 pr-3 font-semibold text-foreground" colSpan={7}>You</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
