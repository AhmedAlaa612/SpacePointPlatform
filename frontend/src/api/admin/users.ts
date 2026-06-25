import { api } from "@/api/client"
import type { User } from "@/types/shared"

export const getUsersApi = () =>
  api.get<User[]>("/admin/users").then((r) => r.data)

export const createUserApi = (data: {
  full_name: string
  email: string
  password: string
  roles: string[]
  phone?: string
}) => api.post<User>("/admin/users", data).then((r) => r.data)

export const updateUserApi = (
  id: string,
  data: Partial<{ full_name: string; email: string; password: string; phone: string; roles: string[] }>
) => api.patch<User>(`/admin/users/${id}`, data).then((r) => r.data)

export const deleteUserApi = (id: string) =>
  api.delete(`/admin/users/${id}`).then((r) => r.data)
