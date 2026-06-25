import { api } from "@/api/client"
import type { ApplicationQuestion, TeacherApplication } from "@/types/ambassadors"

// Public — no auth
export const getTeacherApplicationQuestionsApi = () =>
  api.get<ApplicationQuestion[]>("/ambassadors/public/teacher-application-questions").then((r) => r.data)

// Ambassador — manage own network's applications
export const listMyTeacherApplicationsApi = (status?: string) =>
  api.get<TeacherApplication[]>("/ambassadors/network/teacher-applications", { params: status ? { status } : undefined }).then((r) => r.data)

export const getMyTeacherApplicationApi = (id: string) =>
  api.get<TeacherApplication>(`/ambassadors/network/teacher-applications/${id}`).then((r) => r.data)

export const approveTeacherApplicationApi = (id: string) =>
  api.put<TeacherApplication>(`/ambassadors/network/teacher-applications/${id}/approve`).then((r) => r.data)

export const rejectTeacherApplicationApi = (id: string) =>
  api.put<TeacherApplication>(`/ambassadors/network/teacher-applications/${id}/reject`).then((r) => r.data)
