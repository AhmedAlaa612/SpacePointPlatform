import { api } from "@/api/client"
import type { Epic } from "@/types/interns"

export interface MindMapLayout {
  id: string
  epic_id: string
  layout: Record<string, { x: number; y: number }>
  updated_at: string
}

export interface TaskNote {
  task_id: string
  note: string | null
  updated_at: string
}

// ── Layout ────────────────────────────────────────────────────────────────────

export const getLayoutApi = (epicId: string, role: "admin" | "leader" | "intern") =>
  api.get<MindMapLayout>(`/interns/${role}/epics/${epicId}/mind-map`).then((r) => r.data)

export const saveLayoutApi = (
  epicId: string,
  layout: Record<string, { x: number; y: number }>,
  role: "admin" | "leader"
) => api.patch<MindMapLayout>(`/interns/${role}/epics/${epicId}/mind-map`, { layout }).then((r) => r.data)

// ── Epic fetch ────────────────────────────────────────────────────────────────

export const getEpicForMapApi = (epicId: string, role: "admin" | "leader" | "intern") =>
  api.get<Epic>(`/interns/${role}/epics/${epicId}`).then((r) => r.data)

// ── Task notes ────────────────────────────────────────────────────────────────

export const getTaskNoteApi = (taskId: string, role: "admin" | "leader" | "intern") =>
  api.get<TaskNote>(`/interns/${role}/tasks/${taskId}/mind-map-note`).then((r) => r.data)

export const updateTaskNoteApi = (taskId: string, note: string) =>
  api.patch<TaskNote>(`/interns/intern/tasks/${taskId}/mind-map-note`, { note }).then((r) => r.data)
