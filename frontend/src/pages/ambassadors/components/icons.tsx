import {
  Rocket, Star, Award, Trophy, Crown, Shield, Sparkles, Medal, Gem, Flame,
  Handshake, Briefcase, GraduationCap, Users, Radio, Satellite, Globe, Zap,
  type LucideIcon,
} from "lucide-react"

const MAP: Record<string, LucideIcon> = {
  Rocket, Star, Award, Trophy, Crown, Shield, Sparkles, Medal, Gem, Flame,
  Handshake, Briefcase, GraduationCap, Users, Radio, Satellite, Globe, Zap,
}

export function DynamicIcon({
  name,
  size = 20,
  className,
}: {
  name?: string | null
  size?: number
  className?: string
}) {
  const Icon = (name && MAP[name]) || Award
  return <Icon size={size} className={className} />
}

export const ICON_NAMES = Object.keys(MAP)
