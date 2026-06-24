import { api } from "@/api/client"
import type { Team, User } from "@/types/interns"

export const getTeamsApi = () =>
  api.get<Team[]>("/interns/admin/teams").then((r) => r.data)

export const createTeamApi = (data: { name: string; leader_id?: string }) =>
  api.post<Team>("/interns/admin/teams", data).then((r) => r.data)

export const updateTeamApi = (id: string, data: Partial<{ name: string; leader_id: string }>) =>
  api.patch<Team>(`/interns/admin/teams/${id}`, data).then((r) => r.data)

export const getTeamMembersApi = (teamId: string) =>
  api.get<User[]>(`/interns/teams/${teamId}/members`).then((r) => r.data)

export const getLeaderTeamMembersApi = () =>
  api.get<User[]>("/interns/leader/team/members").then((r) => r.data)

export const getLeaderTeamApi = () =>
  api.get<Team>("/interns/leader/team").then((r) => r.data)

export const getInternTeamApi = () =>
  api.get<Team>("/interns/intern/team").then((r) => r.data)

export const addTeamMemberApi = (teamId: string, userId: string) =>
  api.post<Team>(`/interns/admin/teams/${teamId}/members`, null, { params: { user_id: userId } }).then((r) => r.data)

export const removeTeamMemberApi = (teamId: string, userId: string) =>
  api.delete<Team>(`/interns/admin/teams/${teamId}/members/${userId}`).then((r) => r.data)
