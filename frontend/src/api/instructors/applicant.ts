import { api } from "@/api/client"
import type { ApplicationStatusOut, ChecklistModule, VideoSubmission } from "@/types/instructors"

export const listVideosApi = () =>
  api.get<VideoSubmission[]>("/instructors/videos").then((r) => r.data)

export const updateVideoApi = (
  videoNo: number,
  data: { youtube_url?: string; summary_text: string; submit: boolean },
) => api.put<VideoSubmission>(`/instructors/videos/${videoNo}`, data).then((r) => r.data)

export const listModulesApi = () =>
  api.get<ChecklistModule[]>("/instructors/modules").then((r) => r.data)

export const moduleDetailApi = (moduleId: string) =>
  api.get<ChecklistModule>(`/instructors/modules/${moduleId}`).then((r) => r.data)

export const toggleChecklistItemApi = (itemId: string) =>
  api.put<{ id: string; is_completed: boolean }>(`/instructors/checklist/items/${itemId}/toggle`).then((r) => r.data)

export const submitModuleApi = (moduleId: string, file: File, notesText?: string) => {
  // notes_text is a query param, not a form field — FastAPI reads plain
  // scalar params as query params when the endpoint also takes an
  // UploadFile, unless explicitly declared with Form(...) (verified
  // empirically; see Phase 3.5 notes).
  const form = new FormData()
  form.append("file", file)
  const qs = notesText ? `?notes_text=${encodeURIComponent(notesText)}` : ""
  return api.post(`/instructors/modules/${moduleId}/submit${qs}`, form).then((r) => r.data)
}

export const submitApplicationApi = () =>
  api.post<ApplicationStatusOut>("/instructors/application/submit").then((r) => r.data)

export const reopenApplicationApi = () =>
  api.post<ApplicationStatusOut>("/instructors/application/reopen").then((r) => r.data)

export const submitPresentationApi = (videoLink: string) =>
  api.post<ApplicationStatusOut>("/instructors/presentation/submit", { video_link: videoLink }).then((r) => r.data)

export const getApplicationStatusApi = () =>
  api.get<ApplicationStatusOut>("/instructors/status").then((r) => r.data)
