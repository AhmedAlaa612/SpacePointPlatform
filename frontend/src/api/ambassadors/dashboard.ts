import { api } from "@/api/client"
import type { DashboardStats, PointsTransaction, Achievement } from "@/types/ambassadors"

export const getDashboardStatsApi = () =>
  api.get<DashboardStats>("/ambassadors/dashboard/stats").then((r) => r.data)

export const getMyPointsApi = () =>
  api.get<PointsTransaction[]>("/ambassadors/points/me").then((r) => r.data)

export const getMyAchievementsApi = () =>
  api.get<Achievement[]>("/ambassadors/achievements/me").then((r) => r.data)
