import { api } from "@/api/client"
import type { Task, Submission } from "@/types/interns"

// â”€â”€ Admin â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export const getAllTasksApi = () =>
  api.get<Task[]>("/interns/admin/tasks").then((r) => r.data)

export const createAdminTaskApi = (
  moduleId: string,
  data: { title: string; description?: string; due_date?: string; expected_time?: number }
) => api.post<Task>(`/interns/admin/modules/${moduleId}/tasks`, data).then((r) => r.data)

export const updateTaskApi = (
  taskId: string,
  data: Partial<{ title: string; description: string; due_date: string; status: string; expected_time: number; actual_time: number }>
) => api.patch<Task>(`/interns/admin/tasks/${taskId}`, data).then((r) => r.data)

export const deleteTaskApi = (taskId: string) =>
  api.delete(`/interns/admin/tasks/${taskId}`).then((r) => r.data)

export const assignAdminTaskApi = (taskId: string, userIds: string[]) =>
  api.post<Task>(`/interns/admin/tasks/${taskId}/assign`, { user_ids: userIds }).then((r) => r.data)

export const adminReviewSubmissionApi = (
  submissionId: string,
  data: { score: number; review_comment: string }
) => api.patch<Submission>(`/interns/admin/submissions/${submissionId}/review`, data).then((r) => r.data)

// â”€â”€ Leader â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export const getLeaderTasksApi = () =>
  api.get<Task[]>("/interns/leader/tasks").then((r) => r.data)

export const createLeaderTaskApi = (
  moduleId: string,
  data: { title: string; description?: string; due_date?: string; expected_time?: number }
) => api.post<Task>(`/interns/leader/modules/${moduleId}/tasks`, data).then((r) => r.data)

export const updateLeaderTaskApi = (
  taskId: string,
  data: Partial<{ title: string; description: string; due_date: string; status: string; expected_time: number }>
) => api.patch<Task>(`/interns/leader/tasks/${taskId}`, data).then((r) => r.data)

export const deleteLeaderTaskApi = (taskId: string) =>
  api.delete(`/interns/leader/tasks/${taskId}`).then((r) => r.data)

export const assignLeaderTaskApi = (taskId: string, userIds: string[]) =>
  api.post<Task>(`/interns/leader/tasks/${taskId}/assign`, { user_ids: userIds }).then((r) => r.data)

export const unassignLeaderTaskApi = (taskId: string, userId: string) =>
  api.delete<Task>(`/interns/leader/tasks/${taskId}/assign/${userId}`).then((r) => r.data)

export const leaderReviewSubmissionApi = (
  submissionId: string,
  data: { score: number; review_comment: string }
) => api.patch<Submission>(`/interns/leader/submissions/${submissionId}/review`, data).then((r) => r.data)

// â”€â”€ Intern â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export const getInternTasksApi = () =>
  api.get<Task[]>("/interns/intern/tasks").then((r) => r.data)

export const updateInternTaskStatusApi = (taskId: string, status: string) =>
  api.patch<Task>(`/interns/intern/tasks/${taskId}/status`, { status }).then((r) => r.data)

export const submitTaskWorkApi = (
  taskId: string,
  data: { link: string; note?: string; actual_time?: number }
) => api.post<Submission>(`/interns/intern/tasks/${taskId}/submit`, data).then((r) => r.data)
