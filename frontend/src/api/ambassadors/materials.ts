import { api } from "@/api/client"
import type { Material } from "@/types/ambassadors"

export const getMaterialsApi = (q?: string) =>
  api.get<Material[]>("/ambassadors/materials", { params: q ? { q } : undefined }).then((r) => r.data)

export const createMaterialApi = (data: {
  title: string
  description?: string
  link: string
  category?: string
}) => api.post<Material>("/ambassadors/materials", data).then((r) => r.data)

export const updateMaterialApi = (
  id: string,
  data: Partial<{ title: string; description: string; link: string; category: string }>
) => api.patch<Material>(`/ambassadors/materials/${id}`, data).then((r) => r.data)

export const deleteMaterialApi = (id: string) =>
  api.delete(`/ambassadors/materials/${id}`).then((r) => r.data)
