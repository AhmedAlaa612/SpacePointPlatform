import { api } from "@/api/client"
import type { Badge } from "@/types/ambassadors"

export const getBadgesApi = () => api.get<Badge[]>("/ambassadors/badges").then((r) => r.data)

export const getCriteriaTypesApi = () =>
  api.get<Record<string, string[]>>("/ambassadors/badges/criteria-types").then((r) => r.data)

export const createBadgeApi = (data: Omit<Badge, "id" | "code"> & { code?: string }) =>
  api.post<Badge>("/ambassadors/badges", data).then((r) => r.data)

export const updateBadgeApi = (id: string, data: Partial<Omit<Badge, "id" | "code">>) =>
  api.patch<Badge>(`/ambassadors/badges/${id}`, data).then((r) => r.data)

export const deleteBadgeApi = (id: string) =>
  api.delete(`/ambassadors/badges/${id}`).then((r) => r.data)
