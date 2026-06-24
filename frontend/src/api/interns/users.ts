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
}) => api.post<User>("/interns/admin/users", data).then((r) => r.data)

export const updateUserApi = (id: string, data: Partial<{ full_name: string; email: string; password: string; phone: string; role: string }>) =>
  api.patch<User>(`/interns/admin/users/${id}`, data).then((r) => r.data)

export const deleteUserApi = (id: string) =>
  api.delete(`/interns/admin/users/${id}`).then((r) => r.data)
