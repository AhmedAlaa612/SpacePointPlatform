import { api } from "@/api/client"
import type { Teacher, Instructor, TeacherSession, TeacherApplication } from "@/types/ambassadors"

export const getMyTeachersApi = () =>
  api.get<Teacher[]>("/ambassadors/network/teachers").then((r) => r.data)

export const getTeacherApi = (teacherId: string) =>
  api.get<Teacher>(`/ambassadors/network/teachers/${teacherId}`).then((r) => r.data)

export const getMyInstructorsApi = () =>
  api.get<Instructor[]>("/ambassadors/network/instructors").then((r) => r.data)

export const updateTeacherStatusApi = (id: string, status: "active" | "rejected") =>
  api.put<Teacher>(`/ambassadors/network/teachers/${id}/status`, { status }).then((r) => r.data)

export const getAllSessionsApi = () =>
  api.get<TeacherSession[]>("/ambassadors/network/all-sessions").then((r) => r.data)

export const getTeacherSessionsApi = (teacherId: string) =>
  api.get<TeacherSession[]>(`/ambassadors/network/teachers/${teacherId}/sessions`).then((r) => r.data)

export const createSessionApi = (
  teacherId: string,
  data: { title: string; description?: string; date: string; planned_students: number }
) => api.post<TeacherSession>(`/ambassadors/network/teachers/${teacherId}/sessions`, data).then((r) => r.data)

export const approveSessionApi = (id: string) =>
  api.put<TeacherSession>(`/ambassadors/network/sessions/${id}/approve`).then((r) => r.data)

export const rejectSessionApi = (id: string, reason?: string) =>
  api.put<TeacherSession>(`/ambassadors/network/sessions/${id}/reject`, { reason }).then((r) => r.data)

export const materialSentApi = (id: string, material_link?: string) =>
  api.put<TeacherSession>(`/ambassadors/network/sessions/${id}/material-sent`, { material_link }).then((r) => r.data)

export const markSessionDoneApi = (id: string, attended_students: number) =>
  api.put<TeacherSession>(`/ambassadors/network/sessions/${id}/done`, { attended_students }).then((r) => r.data)

export const editSessionApi = (
  id: string,
  data: Partial<{ title: string; description: string; date: string; planned_students: number }>,
) => api.patch<TeacherSession>(`/ambassadors/network/sessions/${id}`, data).then((r) => r.data)

export const cancelSessionApi = (id: string, reason?: string) =>
  api.put<TeacherSession>(`/ambassadors/network/sessions/${id}/cancel`, { reason }).then((r) => r.data)

export const deleteSessionApi = (id: string) =>
  api.delete(`/ambassadors/network/sessions/${id}`).then((r) => r.data)

// Teacher applications
export const getTeacherApplicationsApi = (status?: string) =>
  api.get<TeacherApplication[]>("/ambassadors/network/teacher-applications", { params: status ? { status } : undefined }).then((r) => r.data)

export const approveTeacherApplicationApi = (id: string) =>
  api.put<TeacherApplication>(`/ambassadors/network/teacher-applications/${id}/approve`).then((r) => r.data)

export const rejectTeacherApplicationApi = (id: string) =>
  api.put<TeacherApplication>(`/ambassadors/network/teacher-applications/${id}/reject`).then((r) => r.data)
