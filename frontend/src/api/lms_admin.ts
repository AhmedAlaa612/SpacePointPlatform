/** LMS authoring API (LM1-13) — thin wrappers over `/lms/admin/*` (LM1-5) +
 * the video upload route (LM1-6). Types mirror `schemas/lms_admin.py`. */
import { api } from "@/api/client";

export type CourseKind = "course" | "mission";
export type ModuleItemKind = "video" | "text" | "quiz" | "flashcards";

export interface AdminCourse {
  id: string;
  title: string;
  description: string | null;
  kind: CourseKind;
  is_published: boolean;
  created_by: string;
  created_at: string | null;
}

export interface AdminModule {
  id: string;
  course_id: string;
  title: string;
  position: number;
}

export interface AdminQuizOption {
  text: string;
  is_correct: boolean;
}

export interface AdminQuizQuestion {
  prompt: string;
  explanation: string | null;
  options: AdminQuizOption[];
}

export type AdminItemContent =
  | { body: string }
  | { pass_threshold: number; mid_video_at_seconds: number | null; questions: AdminQuizQuestion[] }
  | { title: string | null; cards: { term: string; definition: string }[] }
  | Record<string, never>; // video — real state lives in module_videos

export interface AdminItem {
  id: string;
  module_id: string;
  kind: ModuleItemKind;
  title: string | null;
  is_required: boolean;
  position: number;
  content: AdminItemContent;
}

export interface CurriculumEntry {
  id: string;
  program_id: string;
  course_id: string;
  position: number;
}

// ── courses ──────────────────────────────────────────────────────────────

export const listCoursesApi = () => api.get<AdminCourse[]>("/lms/admin/courses").then((r) => r.data);
export const getCourseApi = (id: string) => api.get<AdminCourse>(`/lms/admin/courses/${id}`).then((r) => r.data);
export const createCourseApi = (data: { title: string; description?: string; kind?: CourseKind }) =>
  api.post<AdminCourse>("/lms/admin/courses", data).then((r) => r.data);
export const updateCourseApi = (id: string, data: Partial<{ title: string; description: string; kind: CourseKind }>) =>
  api.patch<AdminCourse>(`/lms/admin/courses/${id}`, data).then((r) => r.data);
export const publishCourseApi = (id: string) => api.post<AdminCourse>(`/lms/admin/courses/${id}/publish`).then((r) => r.data);
export const unpublishCourseApi = (id: string) => api.post<AdminCourse>(`/lms/admin/courses/${id}/unpublish`).then((r) => r.data);
export const deleteCourseApi = (id: string) => api.delete<void>(`/lms/admin/courses/${id}`).then((r) => r.data);

// ── modules ──────────────────────────────────────────────────────────────

export const listModulesApi = (courseId: string) =>
  api.get<AdminModule[]>(`/lms/admin/courses/${courseId}/modules`).then((r) => r.data);
export const createModuleApi = (courseId: string, data: { title: string; position?: number }) =>
  api.post<AdminModule>(`/lms/admin/courses/${courseId}/modules`, data).then((r) => r.data);
export const updateModuleApi = (id: string, data: Partial<{ title: string; position: number }>) =>
  api.patch<AdminModule>(`/lms/admin/modules/${id}`, data).then((r) => r.data);
export const deleteModuleApi = (id: string) => api.delete<void>(`/lms/admin/modules/${id}`).then((r) => r.data);

// ── items ────────────────────────────────────────────────────────────────

export const listItemsApi = (moduleId: string) =>
  api.get<AdminItem[]>(`/lms/admin/modules/${moduleId}/items`).then((r) => r.data);
export const createItemApi = (
  moduleId: string,
  data: { kind: ModuleItemKind; title?: string; is_required?: boolean; position?: number; content: object },
) => api.post<AdminItem>(`/lms/admin/modules/${moduleId}/items`, data).then((r) => r.data);
export const updateItemApi = (
  id: string,
  data: Partial<{ title: string; is_required: boolean; position: number; content: object }>,
) => api.patch<AdminItem>(`/lms/admin/items/${id}`, data).then((r) => r.data);
export const deleteItemApi = (id: string) => api.delete<void>(`/lms/admin/items/${id}`).then((r) => r.data);

// ── video ────────────────────────────────────────────────────────────────

export interface VideoUploadResult {
  item_id: string;
  transcode_status: string;
  dispatch: "queued" | "inline" | "dropped";
}

export const uploadVideoApi = (itemId: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post<VideoUploadResult>(`/lms/admin/items/${itemId}/video`, form).then((r) => r.data);
};

// ── program curriculum ──────────────────────────────────────────────────

export const listCurriculumApi = (programId: string) =>
  api.get<CurriculumEntry[]>(`/lms/admin/programs/${programId}/curriculum`).then((r) => r.data);
export const addCurriculumEntryApi = (programId: string, data: { course_id: string; position?: number }) =>
  api.post<CurriculumEntry>(`/lms/admin/programs/${programId}/curriculum`, data).then((r) => r.data);
export const removeCurriculumEntryApi = (programId: string, courseId: string) =>
  api.delete<void>(`/lms/admin/programs/${programId}/curriculum/${courseId}`).then((r) => r.data);
