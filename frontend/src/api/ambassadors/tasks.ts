import { api } from "@/api/client"
import type { Task, AssignableUser } from "@/types/ambassadors"

export const getTasksApi = (view?: "assigned" | "created") =>
  api.get<Task[]>("/ambassadors/tasks", { params: view ? { view } : undefined }).then((r) => r.data)

export const getAssignableUsersApi = () =>
  api.get<AssignableUser[]>("/ambassadors/tasks/assignable-users").then((r) => r.data)

export const createTaskApi = (data: {
  assigned_to: string
  title: string
  description?: string
  deadline?: string | null
  points_reward: number
}) => api.post<Task>("/ambassadors/tasks", data).then((r) => r.data)

export const updateTaskStatusApi = (
  id: string,
  status: string,
  opts?: { edit_notes?: string; submission?: string },
) => api.put<Task>(`/ambassadors/tasks/${id}/status`, { status, ...opts }).then((r) => r.data)

export const editTaskApi = (
  id: string,
  data: Partial<{ title: string; description: string; deadline: string | null; points_reward: number }>,
) => api.patch<Task>(`/ambassadors/tasks/${id}`, data).then((r) => r.data)

export const deleteTaskApi = (id: string) =>
  api.delete(`/ambassadors/tasks/${id}`).then((r) => r.data)
