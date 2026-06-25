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
