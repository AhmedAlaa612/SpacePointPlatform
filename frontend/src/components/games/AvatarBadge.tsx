import { cn } from "@/lib/utils"
import { AVATAR_ICON_BY_KEY } from "./avatarPresets"

/** One shared avatar visual, everywhere a participant's avatar shows up —
 * lobby roster, instructor roster grid, leaderboard rows, podium, the
 * picker grid itself. Renders the matching preset icon, or an initials
 * fallback when `avatar` is null/unrecognized. Sized via a prop rather
 * than four near-duplicate components, per the original design intent of
 * "one component at 32/44/96/132px, reused everywhere." */

const SIZE_CLASS: Record<number, string> = {
  32: "w-8 h-8", 44: "w-11 h-11", 96: "w-24 h-24", 132: "w-[132px] h-[132px]",
}
const ICON_SIZE: Record<number, number> = { 32: 16, 44: 22, 96: 46, 132: 64 }
const TEXT_SIZE: Record<number, string> = { 32: "text-xs", 44: "text-sm", 96: "text-2xl", 132: "text-4xl" }

export function AvatarBadge({
  avatar, nickname, size = 44,
}: {
  avatar: string | null | undefined
  nickname: string
  size?: 32 | 44 | 96 | 132
}) {
  const Icon = avatar ? AVATAR_ICON_BY_KEY[avatar] : undefined
  return (
    <div
      className={cn(
        "flex-none rounded-full flex items-center justify-center border border-primary/30 bg-primary/10 text-primary font-display font-bold overflow-hidden",
        SIZE_CLASS[size],
      )}
    >
      {Icon ? <Icon size={ICON_SIZE[size]} /> : <span className={TEXT_SIZE[size]}>{(nickname[0] ?? "?").toUpperCase()}</span>}
    </div>
  )
}
