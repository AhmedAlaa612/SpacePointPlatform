import { api } from "@/api/client"
import type { LibraryModule, TrainingModule } from "@/types/instructors"

export const listTrainingApi = () =>
  api.get<TrainingModule[]>("/instructors/training/modules").then((r) => r.data)

export const streamVideoApi = (videoId: string) =>
  api.get<{ url: string }>(`/instructors/training/videos/${videoId}/stream`).then((r) => r.data.url)

export const markVideoCompleteApi = (videoId: string) =>
  api.post<{ video_id: string; is_completed: boolean }>(`/instructors/training/videos/${videoId}/complete`).then((r) => r.data)

export const listLibraryApi = () =>
  api.get<LibraryModule[]>("/instructors/library").then((r) => r.data)

/** Resolved fresh per view, same posture as `streamVideoApi` — a hosted
 *  PDF's `file_url` from `listLibraryApi` comes back blank on purpose. */
export const getLibraryResourceUrlApi = (resourceId: string) =>
  api.get<{ url: string; video_info: import("@/components/video/VideoPlayer").VideoPlaybackInfo | null }>(
    `/instructors/library/resources/${resourceId}/url`,
  ).then((r) => r.data)
