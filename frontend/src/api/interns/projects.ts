import { api } from "@/api/client"
import type { Project } from "@/types/interns"

export const getProjectsApi = () =>
  api.get<Project[]>("/interns/admin/projects").then((r) => r.data)

export const getLeaderProjectsApi = () =>
  api.get<Project[]>("/interns/leader/projects").then((r) => r.data)

export const getInternProjectsApi = () =>
  api.get<Project[]>("/interns/intern/projects").then((r) => r.data)

export const getProjectApi = (id: string) =>
  api.get<Project>(`/interns/admin/projects/${id}`).then((r) => r.data)

export const createProjectApi = (data: { title: string; description?: string }) =>
  api.post<Project>("/interns/admin/projects", data).then((r) => r.data)

export const updateProjectApi = (id: string, data: Partial<{ title: string; description: string; status: string }>) =>
  api.patch<Project>(`/interns/admin/projects/${id}`, data).then((r) => r.data)

export const deleteProjectApi = (id: string) =>
  api.delete(`/interns/admin/projects/${id}`).then((r) => r.data)

export const assignTeamToProjectApi = (projectId: string, teamId: string) =>
  api.post<Project>(`/interns/admin/projects/${projectId}/teams`, null, { params: { team_id: teamId } }).then((r) => r.data)

export const removeTeamFromProjectApi = (projectId: string, teamId: string) =>
  api.delete<Project>(`/interns/admin/projects/${projectId}/teams/${teamId}`).then((r) => r.data)
