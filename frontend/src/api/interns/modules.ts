import { api } from "@/api/client"
import type { Module } from "@/types/interns"

type Role = "admin" | "leader"

export const createModuleApi = (
  epicId: string,
  data: { title: string; description?: string },
  role: Role
) => api.post<Module>(`/interns/${role}/epics/${epicId}/modules`, data).then((r) => r.data)

export const updateModuleApi = (
  moduleId: string,
  data: Partial<{ title: string; description: string }>,
  role: Role
) => api.patch<Module>(`/interns/${role}/modules/${moduleId}`, data).then((r) => r.data)

export const deleteModuleApi = (moduleId: string, role: Role) =>
  api.delete(`/interns/${role}/modules/${moduleId}`).then((r) => r.data)
