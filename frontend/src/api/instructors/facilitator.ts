import { api } from "@/api/client"
import type { LibraryModule, TrainingModule } from "@/types/instructors"

export const facilitatorListTrainingApi = () =>
  api.get<TrainingModule[]>("/instructors/facilitator/training/modules").then((r) => r.data)

export const createTrainingModuleApi = (data: { title: string; description?: string; sort_order?: number }) =>
  api.post<TrainingModule>("/instructors/facilitator/training/modules", data).then((r) => r.data)

export const deleteTrainingModuleApi = (moduleId: string) =>
  api.delete(`/instructors/facilitator/training/modules/${moduleId}`).then((r) => r.data)

export const uploadTrainingVideoApi = (params: {
  moduleId: string; title: string; file: File; description?: string; notes?: string; sortOrder?: number
}) => {
  const form = new FormData()
  form.append("file", params.file)
  const qs = new URLSearchParams({
    module_id: params.moduleId, title: params.title,
    ...(params.description ? { description: params.description } : {}),
    ...(params.notes ? { notes: params.notes } : {}),
    ...(params.sortOrder ? { sort_order: String(params.sortOrder) } : {}),
  })
  return api.post(`/instructors/facilitator/training/videos?${qs}`, form).then((r) => r.data)
}

export const deleteTrainingVideoApi = (videoId: string) =>
  api.delete(`/instructors/facilitator/training/videos/${videoId}`).then((r) => r.data)

export const facilitatorListLibraryApi = () =>
  api.get<LibraryModule[]>("/instructors/facilitator/library/modules").then((r) => r.data)

export const createLibraryModuleApi = (data: { name: string; description?: string }) =>
  api.post<LibraryModule>("/instructors/facilitator/library/modules", data).then((r) => r.data)

export const deleteLibraryModuleApi = (moduleId: string) =>
  api.delete(`/instructors/facilitator/library/modules/${moduleId}`).then((r) => r.data)

export const uploadLibraryResourceApi = (params: { moduleId: string; title: string; file: File; description?: string }) => {
  const form = new FormData()
  form.append("file", params.file)
  const qs = new URLSearchParams({
    module_id: params.moduleId, title: params.title,
    ...(params.description ? { description: params.description } : {}),
  })
  return api.post(`/instructors/facilitator/library?${qs}`, form).then((r) => r.data)
}

export const deleteLibraryResourceApi = (resourceId: string) =>
  api.delete(`/instructors/facilitator/library/${resourceId}`).then((r) => r.data)
