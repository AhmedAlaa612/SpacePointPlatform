import { api } from "@/api/client"
import type { User } from "@/types/shared"
import type { Teacher, Instructor, TeacherSession, LeaderboardEntry, PointsTransaction } from "@/types/ambassadors"

export const getUsersApi = (params?: { status?: string; role?: string }) =>
  api.get<User[]>("/ambassadors/admin/users", { params }).then((r) => r.data)

export const updateUserStatusApi = (id: string, status: "active" | "rejected") =>
  api.put<User>(`/ambassadors/admin/users/${id}/status`, { status }).then((r) => r.data)

export const createUserApi = (data: {
  full_name: string
  email: string
  password: string
  role: string
  country?: string
}) => api.post<User>("/ambassadors/admin/users", data).then((r) => r.data)

export const editUserApi = (
  id: string,
  data: Partial<{ full_name: string; email: string; password: string; role: string; country: string; status: string }>
) => api.patch<User>(`/ambassadors/admin/users/${id}`, data).then((r) => r.data)

export const deleteUserApi = (id: string) =>
  api.delete(`/ambassadors/admin/users/${id}`).then((r) => r.data)

export interface AmbassadorNetwork {
  ambassador: { id: string; full_name: string }
  teachers: Teacher[]
  instructors: Instructor[]
  sessions: TeacherSession[]
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

export interface ActivityEntry {
  created_at: string
  kind: "points" | "lead" | "task" | "session" | "signup"
  text: string
  actor: string | null
  amount: number | null
}

export const getActivityLogApi = (limit = 60) =>
  api.get<ActivityEntry[]>("/ambassadors/admin/activity", { params: { limit } }).then((r) => r.data)

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

export const getAdminLeaderboardApi = (season = false) =>
  api.get<LeaderboardEntry[]>("/ambassadors/admin/leaderboard", { params: { season } }).then((r) => r.data)

export const getPointsLogApi = () =>
  api.get<PointsTransaction[]>("/ambassadors/admin/points-log").then((r) => r.data)

export const getInstructorsApi = (status?: string) =>
  api.get<Instructor[]>("/ambassadors/admin/instructors", { params: status ? { status } : undefined }).then((r) => r.data)

export const updateInstructorStatusApi = (id: string, status: "active" | "rejected") =>
  api.put(`/ambassadors/admin/instructors/${id}/status`, { status }).then((r) => r.data)

export const getAllTeacherSessionsApi = () =>
  api.get<TeacherSession[]>("/ambassadors/admin/teacher-sessions").then((r) => r.data)

export const getSettingsApi = () =>
  api.get<Record<string, string>>("/ambassadors/admin/settings").then((r) => r.data)

export const updateSettingApi = (key: string, value: string) =>
  api.put(`/ambassadors/admin/settings/${key}`, { value }).then((r) => r.data)
