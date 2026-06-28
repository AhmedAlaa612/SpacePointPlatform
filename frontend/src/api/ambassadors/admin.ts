import { api } from "@/api/client"
import type { LeaderboardEntry, PointsTransaction } from "@/types/ambassadors"

// Note: no Users CRUD here — that's generic (the `users` table isn't
// domain-specific) and already lives at /interns/admin/users. Instructor
// *approval* lives solely in /instructors/admin — everything instructor-shaped
// below is read-only.

export interface AmbassadorNetwork {
  ambassador: { id: string; full_name: string }
  teachers: { id: string; full_name: string; email: string; status: string }[]
  instructors: { id: string; full_name: string; email: string; status: string }[]
  sessions: { id: string; teacher_id: string; title: string; status: string; date: string | null; attended_students: number; teacher_name: string | null }[]
}

export const getAmbassadorNetworkApi = (id: string) =>
  api.get<AmbassadorNetwork>(`/ambassadors/admin/ambassadors/${id}/network`).then((r) => r.data)

export interface FullNetwork {
  ambassadors: {
    id: string
    full_name: string
    teachers: { id: string; full_name: string; status: string; sessions_done: number }[]
    instructors: { id: string; full_name: string; status: string }[]
  }[]
}

export const getFullNetworkApi = () =>
  api.get<FullNetwork>("/ambassadors/admin/network").then((r) => r.data)

export interface AdminInstructor {
  id: string
  full_name: string
  email: string
  status: string
  invited_by_id: string | null
  ambassador_name: string | null
  created_at: string | null
}

export const getInstructorsApi = () =>
  api.get<AdminInstructor[]>("/ambassadors/admin/instructors").then((r) => r.data)

export interface ActivityEntry {
  created_at: string
  kind: "points" | "lead" | "task" | "session" | "signup"
  text: string
  actor: string | null
  amount: number | null
}

export const getActivityLogApi = (limit = 60) =>
  api.get<ActivityEntry[]>("/ambassadors/admin/activity", { params: { limit } }).then((r) => r.data)

export const updateUserStatusApi = (id: string, status: "active" | "rejected") =>
  api.put(`/ambassadors/admin/users/${id}/status`, { status }).then((r) => r.data)

export interface PointsLogEntry {
  id: string
  amount: number
  type: string
  reason: string
  created_at: string
}

export const getAmbassadorPointsLogApi = (id: string) =>
  api.get<PointsLogEntry[]>(`/ambassadors/admin/users/${id}/points-log`).then((r) => r.data)

export const getAmbassadorStatsApi = (id: string) =>
  api.get<any>(`/ambassadors/admin/users/${id}/ambassador-stats`).then((r) => r.data)

export const getTeacherStatsApi = (id: string) =>
  api.get<any>(`/ambassadors/admin/users/${id}/teacher-stats`).then((r) => r.data)

export const getAdminLeaderboardApi = (season = false) =>
  api.get<LeaderboardEntry[]>("/ambassadors/admin/leaderboard", { params: { season } }).then((r) => r.data)

export const getPointsLogApi = () =>
  api.get<PointsTransaction[]>("/ambassadors/admin/points-log").then((r) => r.data)

export const getSettingsApi = () =>
  api.get<Record<string, string>>("/ambassadors/admin/settings").then((r) => r.data)

export const updateSettingApi = (key: string, value: string) =>
  api.put(`/ambassadors/admin/settings/${key}`, { value }).then((r) => r.data)
