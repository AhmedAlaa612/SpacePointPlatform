import { api } from "@/api/client"
import type { CalendarResult } from "@/types/sessions"

export const getCalendarApi = (from: string, to: string, scope: "ops" | "instructor") =>
  api.get<CalendarResult>("/sessions/calendar", { params: { from, to, scope } }).then((r) => r.data)
