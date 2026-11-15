import { api } from "@/api/client"

export type DashboardRange = "1h" | "24h" | "7d" | "30d" | "all"
export type MilestoneKindFilter = "all" | "course" | "mission" | "quiz" | "team"

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

export interface DashboardFunnel {
  enrolled: number
  active: number
  completed: number
}

export interface ActiveTeamsSummary {
  active: number
  total: number
  locked: number
}

export interface TopInviteCode {
  code: string
  label: string | null
  redeemed: number
  active: number
}

export interface ActiveProgramProgress {
  cohort_id: string
  cohort_name: string
  students: number
  completed_pct: number
  active_pct: number
  not_started_pct: number
  engaged_pct: number
}

export interface StudentMilestone {
  id: string
  kind: "course" | "mission" | "quiz" | "team"
  title: string
  actor_name: string
  meta: string | null
  tone: "green" | "purple" | "rose" | "neutral"
  link: string | null
  timestamp: string
}

export interface PaginatedMilestones {
  items: StudentMilestone[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface WarehouseInventoryDelta {
  warehouse_id: string
  warehouse_name: string
  added: number
  removed: number
}

export interface WarehouseMovementRow {
  id: string
  item_label: string
  qty_display: string
  tone: "green" | "rose" | "purple"
  warehouse_label: string
  reason: string
  actor_name: string | null
  created_at: string
}

export interface OpsDashboardOverview {
  range: DashboardRange
  active_cohorts: number
  upcoming_sessions_7d: number
  active_learners: number
  learner_trend: number[]
  learner_delta_label: string
  funnel: DashboardFunnel
  active_teams: ActiveTeamsSummary
  avg_course_completion_pct: number
  avg_mission_completion_pct: number
  top_invite_codes: TopInviteCode[]
  active_programs: ActiveProgramProgress[]
  milestones: PaginatedMilestones
  warehouses: WarehouseInventoryDelta[]
  recent_movements: WarehouseMovementRow[]
}

export const getOpsDashboardApi = () =>
  api.get<OpsDashboardData>("/sessions/dashboard").then((r) => r.data)

export const getOpsDashboardOverviewApi = (params: {
  range: DashboardRange
  kind: MilestoneKindFilter
  page: number
  page_size?: number
}) =>
  api
    .get<OpsDashboardOverview>("/sessions/dashboard/overview", { params })
    .then((r) => r.data)
