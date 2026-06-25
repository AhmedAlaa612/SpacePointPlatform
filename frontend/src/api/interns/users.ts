import { api } from "@/api/client"
import type { User } from "@/types/interns"

export const getUsersApi = () =>
  api.get<User[]>("/interns/admin/users").then((r) => r.data)

export const createUserApi = (data: {
  full_name: string
  email: string
  password: string
  role: string
  phone?: string
}) => {
  const { role, ...rest } = data
  return api.post<User>("/interns/admin/users", { ...rest, roles: [role] }).then((r) => r.data)
}

export const updateUserApi = (id: string, data: Partial<{ full_name: string; email: string; password: string; phone: string; role: string }>) => {
  const { role, ...rest } = data
  const payload = role ? { ...rest, roles: [role] } : rest
  return api.patch<User>(`/interns/admin/users/${id}`, payload).then((r) => r.data)
}

export const deleteUserApi = (id: string) =>
  api.delete(`/interns/admin/users/${id}`).then((r) => r.data)

export const generateConfirmationLetterApi = (id: string) =>
  api.post<{ file_url: string }>(`/interns/admin/users/${id}/confirmation-letter`).then((r) => r.data)

export const generateCompletionLetterApi = (id: string) =>
  api.post<{ file_url: string }>(`/interns/admin/users/${id}/completion-letter`).then((r) => r.data)

export const generateCertificateApi = (id: string) =>
  api.post<{ file_url: string }>(`/interns/admin/users/${id}/certificate`).then((r) => r.data)
