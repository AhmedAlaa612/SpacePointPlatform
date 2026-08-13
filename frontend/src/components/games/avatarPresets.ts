import { Bot, Compass, Flame, Moon, Orbit, Rocket, Satellite, Star, Telescope, Zap, type LucideIcon } from "lucide-react"

/** Icon presets only, no "use my photo" — mirrors `backend/app/services/games/avatars.py`'s
 * `AVATAR_PRESETS` exactly. Deliberate: a real photo next to a fake nickname
 * would undercut the platform's existing pseudonymity guarantee (real name
 * stays a staff-only reveal, D9) even though a photo isn't literally the
 * name field. */
export const AVATAR_PRESETS: { key: string; icon: LucideIcon; label: string }[] = [
  { key: "rocket", icon: Rocket, label: "Rocket" },
  { key: "satellite", icon: Satellite, label: "Satellite" },
  { key: "telescope", icon: Telescope, label: "Telescope" },
  { key: "orbit", icon: Orbit, label: "Orbit" },
  { key: "star", icon: Star, label: "Star" },
  { key: "moon", icon: Moon, label: "Moon" },
  { key: "zap", icon: Zap, label: "Lightning" },
  { key: "flame", icon: Flame, label: "Flame" },
  { key: "compass", icon: Compass, label: "Compass" },
  { key: "bot", icon: Bot, label: "Bot" },
]

export const AVATAR_ICON_BY_KEY: Record<string, LucideIcon> = Object.fromEntries(
  AVATAR_PRESETS.map((p) => [p.key, p.icon]),
)
