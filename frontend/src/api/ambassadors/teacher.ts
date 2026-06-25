import { api } from "@/api/client"
import type { Achievement, TitleBrief } from "@/types/ambassadors"

export interface TeacherSummary {
  ambassador: { id: string; full_name: string; email: string; country: string | null } | null
  stats: { sessions_done: number; students_reached: number; pending: number; upcoming: number }
  points_balance: number
  achievements: Achievement[]
  current_title: TitleBrief | null
  next_title: TitleBrief | null
  points_to_next: number
  progress_to_next: number
}

export interface TeacherLeaderRow {
  id: string
  name: string
  country: string
  points: number
  students_reached: number
  sessions_done: number
}

export const getTeacherSummaryApi = () =>
  api.get<TeacherSummary>("/ambassadors/teacher/summary").then((r) => r.data)

export const getTeacherLeaderboardApi = () =>
  api.get<TeacherLeaderRow[]>("/ambassadors/teacher/leaderboard").then((r) => r.data)
