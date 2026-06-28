import { api } from "@/api/client"
import type { LibraryModule, TrainingModule } from "@/types/instructors"

export const facilitatorListTrainingApi = () =>
  api.get<TrainingModule[]>("/instructors/facilitator/training/modules").then((r) => r.data)

export const createTrainingModuleApi = (data: { title: string; description?: string; sort_order?: number }) =>
  api.post<TrainingModule>("/instructors/facilitator/training/modules", data).then((r) => r.data)

export const deleteTrainingModuleApi = (moduleId: string) =>
  api.delete(`/instructors/facilitator/training/modules/${moduleId}`).then((r) => r.data)

export const addTrainingVideoApi = (params: {
  moduleId: string; title: string; url: string; description?: string; notes?: string; sortOrder?: number
}) =>
  api.post(`/instructors/facilitator/training/videos`, {
    module_id: params.moduleId,
    title: params.title,
    url: params.url,
    description: params.description,
    notes: params.notes,
    sort_order: params.sortOrder ?? 1,
  }).then((r) => r.data)

export const updateTrainingVideoApi = (videoId: string, params: { title?: string; url?: string }) => {
  const qs = new URLSearchParams()
  if (params.title !== undefined) qs.set("title", params.title)
  if (params.url !== undefined) qs.set("url", params.url)
  return api.patch(`/instructors/facilitator/training/videos/${videoId}?${qs}`).then((r) => r.data)
}

export const deleteTrainingVideoApi = (videoId: string) =>
  api.delete(`/instructors/facilitator/training/videos/${videoId}`).then((r) => r.data)

export const facilitatorListLibraryApi = () =>
  api.get<LibraryModule[]>("/instructors/facilitator/library/modules").then((r) => r.data)

export const createLibraryModuleApi = (data: { name: string; description?: string }) =>
  api.post<LibraryModule>("/instructors/facilitator/library/modules", data).then((r) => r.data)

export const deleteLibraryModuleApi = (moduleId: string) =>
  api.delete(`/instructors/facilitator/library/modules/${moduleId}`).then((r) => r.data)

export const addLibraryLinkApi = (params: { moduleId: string; title: string; url: string; description?: string }) => {
  const qs = new URLSearchParams({ module_id: params.moduleId, title: params.title, url: params.url })
  if (params.description) qs.set("description", params.description)
  return api.post(`/instructors/facilitator/library/link?${qs}`).then((r) => r.data)
}

export const uploadLibraryResourceApi = (params: {
  moduleId: string; title: string; file: File; description?: string
}) => {
  const form = new FormData()
  form.append("file", params.file)
  const qs = new URLSearchParams({ module_id: params.moduleId, title: params.title })
  if (params.description) qs.set("description", params.description)
  return api.post(`/instructors/facilitator/library?${qs}`, form).then((r) => r.data)
}

export const updateLibraryResourceApi = (resourceId: string, params: { title?: string; url?: string }) => {
  const qs = new URLSearchParams()
  if (params.title !== undefined) qs.set("title", params.title)
  if (params.url !== undefined) qs.set("url", params.url)
  return api.patch(`/instructors/facilitator/library/${resourceId}?${qs}`).then((r) => r.data)
}

export const replaceLibraryFileApi = (resourceId: string, file: File, title?: string) => {
  const form = new FormData()
  form.append("file", file)
  const qs = new URLSearchParams()
  if (title) qs.set("title", title)
  return api.put(`/instructors/facilitator/library/${resourceId}/file?${qs}`, form).then((r) => r.data)
}

export const deleteLibraryResourceApi = (resourceId: string) =>
  api.delete(`/instructors/facilitator/library/${resourceId}`).then((r) => r.data)

// ── Application content: videos ──────────────────────────────

export const getApplicationVideosApi = () =>
  api.get<import("@/types/instructors").ApplicationVideoConfig[]>("/instructors/facilitator/application/videos").then((r) => r.data)

export const updateApplicationVideosApi = (videos: import("@/types/instructors").ApplicationVideoConfig[]) =>
  api.put("/instructors/facilitator/application/videos", { videos }).then((r) => r.data)

// ── Application content: checklist modules ───────────────────

export const listApplicationModulesApi = () =>
  api.get<import("@/types/instructors").ApplicationModule[]>("/instructors/facilitator/application/modules").then((r) => r.data)

export const createApplicationModuleApi = (data: { title: string; sort_order?: number }) =>
  api.post<import("@/types/instructors").ApplicationModule>("/instructors/facilitator/application/modules", data).then((r) => r.data)

export const updateApplicationModuleApi = (moduleId: string, data: { title?: string; sort_order?: number }) =>
  api.put<import("@/types/instructors").ApplicationModule>(`/instructors/facilitator/application/modules/${moduleId}`, data).then((r) => r.data)

export const deleteApplicationModuleApi = (moduleId: string) =>
  api.delete(`/instructors/facilitator/application/modules/${moduleId}`).then((r) => r.data)

export const createApplicationItemApi = (
  moduleId: string,
  data: { title: string; item_code: string; description?: string | null; is_required?: boolean; sort_order?: number },
) =>
  api.post<import("@/types/instructors").ApplicationChecklistItem>(
    `/instructors/facilitator/application/modules/${moduleId}/items`, data,
  ).then((r) => r.data)

export const updateApplicationItemApi = (
  itemId: string,
  data: { title?: string; item_code?: string; description?: string | null; is_required?: boolean; sort_order?: number },
) =>
  api.put<import("@/types/instructors").ApplicationChecklistItem>(
    `/instructors/facilitator/application/items/${itemId}`, data,
  ).then((r) => r.data)

export const deleteApplicationItemApi = (itemId: string) =>
  api.delete(`/instructors/facilitator/application/items/${itemId}`).then((r) => r.data)
