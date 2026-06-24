import { api } from "@/api/client"
import type { Epic } from "@/types/interns"

// Admin
export const getAllEpicsApi = () =>
  api.get<Epic[]>("/interns/admin/epics").then((r) => r.data)

export const getProjectEpicsApi = (projectId: string) =>
  api.get<Epic[]>(`/interns/admin/projects/${projectId}/epics`).then((r) => r.data)

export const createEpicApi = (
  projectId: string,
  data: { title: string; description?: string; team_id: string }
) => api.post<Epic>(`/interns/admin/projects/${projectId}/epics`, data).then((r) => r.data)

export const updateEpicApi = (
  epicId: string,
  data: Partial<{ title: string; description: string; status: string }>
) => api.patch<Epic>(`/interns/admin/epics/${epicId}`, data).then((r) => r.data)

export const deleteEpicApi = (epicId: string) =>
  api.delete(`/interns/admin/epics/${epicId}`).then((r) => r.data)

// Leader
export const getLeaderEpicsApi = () =>
  api.get<Epic[]>("/interns/leader/epics").then((r) => r.data)

export const updateLeaderEpicApi = (
  epicId: string,
  data: Partial<{ title: string; description: string; status: string }>
) => api.patch<Epic>(`/interns/leader/epics/${epicId}`, data).then((r) => r.data)
