import { api } from "@/api/client"
import type { Title } from "@/types/ambassadors"

export const getTitlesApi = (audience?: string) =>
  api.get<Title[]>("/ambassadors/titles", { params: audience ? { audience } : undefined }).then((r) => r.data)

export const createTitleApi = (data: Omit<Title, "id">) =>
  api.post<Title>("/ambassadors/titles", data).then((r) => r.data)

export const updateTitleApi = (id: string, data: Partial<Omit<Title, "id">>) =>
  api.patch<Title>(`/ambassadors/titles/${id}`, data).then((r) => r.data)

export const deleteTitleApi = (id: string) =>
  api.delete(`/ambassadors/titles/${id}`).then((r) => r.data)
