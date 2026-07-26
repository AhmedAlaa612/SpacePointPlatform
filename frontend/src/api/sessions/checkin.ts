import { api } from "@/api/client"

export interface CheckInResult {
  attendance_id: string
  att_status: string
  method: string
  recorded_at: string
  student_name: string
  program_name: string | null
  cohort_name: string | null
}

export const checkInApi = (data: { token: string; session_id: string }) =>
  api.post<CheckInResult>("/sessions/checkin", data).then((r) => r.data)

export interface TodaySession {
  id: string
  cohort_id: string
  cohort_name: string
  program_name: string
  meeting_date: string
  starts_at: string | null
  title: string | null
}

export const getTodaysSessionsApi = () =>
  api.get<TodaySession[]>("/sessions/today").then((r) => r.data)
