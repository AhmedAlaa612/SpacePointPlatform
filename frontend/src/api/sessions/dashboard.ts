import { api } from "@/api/client"

export interface OpsDashboardData {
  students_trained: number
  active_cohorts: number
  upcoming_meetings_7d: number
  attendance_rate_30d: number
  unpaid_count: number
  unpaid_sum: string
  registrations_7d: number
  open_calls_pending: number
}

export const getOpsDashboardApi = () =>
  api.get<OpsDashboardData>("/sessions/dashboard").then((r) => r.data)
