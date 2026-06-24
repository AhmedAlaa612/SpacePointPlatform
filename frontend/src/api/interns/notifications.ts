import { api } from "@/api/client"
import type { Notification } from "@/types/interns"

export const getNotificationsApi = () =>
  api.get<Notification[]>("/notifications/me").then((r) => r.data)

export const markReadApi = (id: string) =>
  api.patch<Notification>(`/notifications/${id}/read`).then((r) => r.data)

export const markAllReadApi = () =>
  api.post("/notifications/read-all").then((r) => r.data)
