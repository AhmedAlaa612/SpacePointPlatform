import { api } from "./client"

export interface UpcomingBirthdayUser {
  id: string
  full_name: string
  email: string
  roles: string[]
  birthdate: string
  days_until: number
  next_birthday: string
  photo_url?: string | null
  status: string
  has_sent_this_year: boolean
}

export interface BirthdayEmailLog {
  id: string
  user_id: string
  user_full_name: string
  user_email: string
  user_roles: string[]
  sent_at: string
  sent_at_year: number
  birth_year_referenced?: number | null
  nasa_image_url?: string | null
  nasa_title?: string | null
  nasa_explanation?: string | null
  status: "sent" | "failed" | "skipped" | string
  error_message?: string | null
}

export interface BirthdayLogsResponse {
  items: BirthdayEmailLog[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface BirthdayStats {
  total_with_birthdays: number
  sent_this_year: number
  upcoming_7_days: number
  upcoming_30_days: number
  failed_count: number
}

export const getUpcomingBirthdaysApi = (days: number = 30) =>
  api.get<UpcomingBirthdayUser[]>("/admin/birthdays/upcoming", { params: { days } }).then((r) => r.data)

export const getBirthdayLogsApi = (params?: { page?: number; page_size?: number; status?: string }) =>
  api.get<BirthdayLogsResponse>("/admin/birthdays/logs", { params }).then((r) => r.data)

export const retryBirthdayEmailApi = (logIdOrUserId: string) =>
  api.post<BirthdayEmailLog>(`/admin/birthdays/retry/${logIdOrUserId}`).then((r) => r.data)

export const getBirthdayStatsApi = () =>
  api.get<BirthdayStats>("/admin/birthdays/stats").then((r) => r.data)
