import { api } from "@/api/client"
import type { Task } from "@/types/interns"

/** Admin: view any user's task tracker */
export const getAdminTrackerApi = (userId: string) =>
  api.get<Task[]>(`/interns/admin/tracker/${userId}`).then((r) => r.data)

/** Leader: view a team member's task tracker */
export const getLeaderTrackerApi = (userId: string) =>
  api.get<Task[]>(`/interns/leader/tracker/${userId}`).then((r) => r.data)

/** Intern: own tracker â€” reuses the assigned-tasks endpoint */
export const getInternTrackerApi = () =>
  api.get<Task[]>("/interns/intern/tasks").then((r) => r.data)
