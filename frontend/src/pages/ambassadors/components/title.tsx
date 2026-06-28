import type { TitleBrief, Achievement } from "@/types/ambassadors"
import { DynamicIcon } from "./icons"
import { cn } from "@/lib/utils"

export function TitleBadge({
  title,
  size = "md",
}: {
  title: TitleBrief | null
  size?: "sm" | "md"
}) {
  if (!title) {
    return <span className="text-sm text-muted-foreground">Unranked</span>
  }
  const color = title.color || "#a880ff"
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-semibold border",
        size === "sm" ? "px-2.5 py-0.5 text-xs" : "px-3 py-1 text-sm"
      )}
      style={{ color, borderColor: `${color}55`, backgroundColor: `${color}14` }}
    >
      <DynamicIcon name={title.icon} size={size === "sm" ? 13 : 16} />
      {title.name}
    </span>
  )
}

export function TitleProgress({
  current,
  next,
  pointsToNext,
  progress,
}: {
  current: TitleBrief | null
  next: TitleBrief | null
  pointsToNext: number
  progress: number
}) {
  const color = current?.color || "#a880ff"
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <TitleBadge title={current} />
        {next && <TitleBadge title={next} size="sm" />}
      </div>
      <div className="h-2.5 w-full rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${Math.round(progress * 100)}%`, backgroundColor: color }}
        />
      </div>
      <p className="text-xs text-muted-foreground mt-2">
        {next
          ? `${pointsToNext.toLocaleString()} points to ${next.name}`
          : "Highest title reached — legendary!"}
      </p>
    </div>
  )
}

export function AchievementGrid({ achievements }: { achievements: Achievement[] }) {
  if (!achievements.length) return null
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      {achievements.map((a) => (
        <div
          key={a.code}
          className={cn(
            "rounded-xl border p-3 flex flex-col items-center text-center gap-1.5 transition-colors",
            a.earned
              ? "border-heliotrope/40 bg-snuff/15"
              : "border-border bg-muted/30 opacity-60"
          )}
          title={a.description}
        >
          <div
            className={cn(
              "w-10 h-10 rounded-full flex items-center justify-center",
              a.earned ? "bg-heliotrope/15 text-affair dark:text-heliotrope" : "bg-muted text-muted-foreground text-muted-foreground"
            )}
          >
            <DynamicIcon name={a.icon} size={18} />
          </div>
          <p className="text-xs font-semibold text-foreground leading-tight">{a.label}</p>
          <p className="text-[10px] text-muted-foreground dark:text-zinc-400 leading-tight">{a.description}</p>
        </div>
      ))}

    </div>
  )
}
