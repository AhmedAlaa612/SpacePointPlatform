import { api } from "@/api/client"
import type { User, TokenResponse } from "@/types/interns"

export const loginApi = (email: string, password: string) =>
  api.post<TokenResponse>("/auth/login", { email, password }).then((r) => r.data)

export const getMeApi = () =>
  api.get<User>("/interns/users/me").then((r) => r.data)

export const updateMeApi = (data: Partial<{ full_name: string; phone: string; email: string }>) =>
  api.patch<User>("/interns/users/me", data).then((r) => r.data)
