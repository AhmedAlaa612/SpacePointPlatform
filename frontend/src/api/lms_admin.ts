/** LMS authoring API (LM1-13) — thin wrappers over `/lms/admin/*` (LM1-5) +
 * the video upload route (LM1-6). Types mirror `schemas/lms_admin.py`. */
import { api } from "@/api/client";

export type CourseKind = "course" | "mission";
export type CourseLevel = "beginner" | "intermediate" | "advanced";
export type ModuleItemKind = "video" | "text" | "quiz" | "flashcards" | "attachment";

export interface AdminCourse {
  id: string;
  title: string;
  description: string | null;
  kind: CourseKind;
  is_published: boolean;
  created_by: string;
  created_at: string | null;
  image_url: string | null;
  outcomes: string[];
  level: CourseLevel | null;
  track: string | null;
  instructor_id: string | null;
  instructor_name: string | null;
  instructor_title: string | null;
}

export interface InstructorOption {
  id: string;
  full_name: string;
  photo_url: string | null;
}

export interface StaffOption {
  id: string;
  full_name: string;
  email: string;
  roles: string[];
}

export interface AdminEnrollment {
  id: string;
  user_id: string;
  student_name: string;
  student_email: string;
  course_id: string;
  course_title: string | null;
  source: string;
  status: string;
  granted_by: string | null;
  expires_at: string | null;
  created_at: string | null;
}

export interface BulkGrantResult {
  granted: number;
  already_enrolled: number;
  skipped_no_account: number;
}

export interface StudentSummary {
  id: string;
  full_name: string;
  nickname: string | null;
  email: string;
  invite_code: string | null;
  invite_label: string | null;
}

export interface InviteCode {
  id: string;
  code: string;
  label: string | null;
  is_active: boolean;
  max_uses: number;
  used_count: number;
  expires_at: string | null;
  created_at: string | null;
  /** Accounts actually created on this code (counted from users, not the
   * `used_count` counter, which only ever increments). */
  signups: number;
}

export interface StudentProgram {
  registration_id: string;
  cohort_id: string;
  program_name: string;
  cohort_name: string;
  starts_on: string | null;
  ends_on: string | null;
}

export interface StudentProfile {
  id: string;
  full_name: string;
  nickname: string | null;
  email: string;
  programs: StudentProgram[];
}

export interface CourseMetadataInput {
  outcomes?: string[];
  level?: CourseLevel | null;
  track?: string | null;
  instructor_id?: string | null;
  instructor_title?: string | null;
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

export type VideoTranscodeStatus = "pending" | "processing" | "ready" | "failed";

export type AdminItemContent =
  | { body: string }
  | { pass_threshold: number; questions: AdminQuizQuestion[] }
  | { title: string | null; cards: { term: string; definition: string }[] }
  | { transcode_status: VideoTranscodeStatus | null; transcode_error: string | null; duration_seconds: number | null }
  // Empty until uploaded (same two-step shape as video) — every field optional
  // rather than a second union member, since {} and the populated shape are
  // both valid at different points in the same item's life.
  | { bucket?: string; path?: string; filename?: string; size_bytes?: number };

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

// ── video checkpoints (timeline notes + mid-video quizzes, 2026-08-07) ─────

export type CheckpointKind = "note" | "quiz";
export type CheckpointQuestionType = "mcq" | "multiselect" | "open";

export interface AdminCheckpointNoteContent {
  body: string;
}

export interface AdminCheckpointQuizContent {
  question_type: CheckpointQuestionType;
  prompt: string;
  explanation?: string | null;
  options?: AdminQuizOption[] | null;
}

export type AdminCheckpointContent = AdminCheckpointNoteContent | AdminCheckpointQuizContent;

export interface AdminCheckpoint {
  id: string;
  item_id: string;
  start_seconds: number;
  end_seconds: number | null;
  kind: CheckpointKind;
  content: AdminCheckpointContent;
}

// ── courses ──────────────────────────────────────────────────────────────

export const listCoursesApi = () => api.get<AdminCourse[]>("/lms/admin/courses").then((r) => r.data);
export const getCourseApi = (id: string) => api.get<AdminCourse>(`/lms/admin/courses/${id}`).then((r) => r.data);
export const createCourseApi = (
  data: { title: string; description?: string; kind?: CourseKind } & CourseMetadataInput,
) => api.post<AdminCourse>("/lms/admin/courses", data).then((r) => r.data);
export const updateCourseApi = (
  id: string, data: Partial<{ title: string; description: string; kind: CourseKind }> & CourseMetadataInput,
) => api.patch<AdminCourse>(`/lms/admin/courses/${id}`, data).then((r) => r.data);
export const publishCourseApi = (id: string) => api.post<AdminCourse>(`/lms/admin/courses/${id}/publish`).then((r) => r.data);
export const unpublishCourseApi = (id: string) => api.post<AdminCourse>(`/lms/admin/courses/${id}/unpublish`).then((r) => r.data);
export const deleteCourseApi = (id: string) => api.delete<void>(`/lms/admin/courses/${id}`).then((r) => r.data);
export const uploadCourseImageApi = (id: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post<AdminCourse>(`/lms/admin/courses/${id}/image`, form).then((r) => r.data);
};
export const listInstructorOptionsApi = () =>
  api.get<InstructorOption[]>("/lms/admin/instructors").then((r) => r.data);

// ── modules ──────────────────────────────────────────────────────────────

export const listModulesApi = (courseId: string) =>
  api.get<AdminModule[]>(`/lms/admin/courses/${courseId}/modules`).then((r) => r.data);
export const getModuleApi = (id: string) =>
  api.get<AdminModule>(`/lms/admin/modules/${id}`).then((r) => r.data);
export const createModuleApi = (courseId: string, data: { title: string; position?: number }) =>
  api.post<AdminModule>(`/lms/admin/courses/${courseId}/modules`, data).then((r) => r.data);
export const updateModuleApi = (id: string, data: Partial<{ title: string; position: number }>) =>
  api.patch<AdminModule>(`/lms/admin/modules/${id}`, data).then((r) => r.data);
export const deleteModuleApi = (id: string) => api.delete<void>(`/lms/admin/modules/${id}`).then((r) => r.data);
export const reorderModulesApi = (courseId: string, moduleIds: string[]) =>
  api.post<AdminModule[]>(`/lms/admin/courses/${courseId}/modules/reorder`, { module_ids: moduleIds }).then((r) => r.data);

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
export const reorderItemsApi = (moduleId: string, itemIds: string[]) =>
  api.post<AdminItem[]>(`/lms/admin/modules/${moduleId}/items/reorder`, { item_ids: itemIds }).then((r) => r.data);

// ── video ────────────────────────────────────────────────────────────────

export interface VideoUploadResult {
  item_id: string;
  transcode_status: string;
  dispatch: "queued" | "inline" | "dropped";
}

export const uploadVideoApi = (
  itemId: string,
  file: File,
  opts?: { onProgress?: (pct: number) => void; signal?: AbortSignal },
) => {
  const form = new FormData();
  form.append("file", file);
  return api
    .post<VideoUploadResult>(`/lms/admin/items/${itemId}/video`, form, {
      signal: opts?.signal,
      onUploadProgress: (evt) => {
        if (opts?.onProgress && evt.total) opts.onProgress(Math.round((evt.loaded / evt.total) * 100));
      },
    })
    .then((r) => r.data);
};

// ── attachment (PDF reader, 2026-08-09) ─────────────────────────────────────

export const uploadAttachmentApi = (
  itemId: string,
  file: File,
  opts?: { onProgress?: (pct: number) => void; signal?: AbortSignal },
) => {
  const form = new FormData();
  form.append("file", file);
  return api
    .post<AdminItem>(`/lms/admin/items/${itemId}/attachment`, form, {
      signal: opts?.signal,
      onUploadProgress: (evt) => {
        if (opts?.onProgress && evt.total) opts.onProgress(Math.round((evt.loaded / evt.total) * 100));
      },
    })
    .then((r) => r.data);
};

export const listCheckpointsApi = (videoItemId: string) =>
  api.get<AdminCheckpoint[]>(`/lms/admin/items/${videoItemId}/checkpoints`).then((r) => r.data);
export const createCheckpointApi = (
  videoItemId: string,
  data: { start_seconds: number; end_seconds?: number | null; kind: CheckpointKind; content: object },
) => api.post<AdminCheckpoint>(`/lms/admin/items/${videoItemId}/checkpoints`, data).then((r) => r.data);
export const updateCheckpointApi = (
  id: string,
  data: Partial<{ start_seconds: number; end_seconds: number | null; content: object }>,
) => api.patch<AdminCheckpoint>(`/lms/admin/checkpoints/${id}`, data).then((r) => r.data);
export const deleteCheckpointApi = (id: string) => api.delete<void>(`/lms/admin/checkpoints/${id}`).then((r) => r.data);

// ── program curriculum ──────────────────────────────────────────────────

export const listCurriculumApi = (programId: string) =>
  api.get<CurriculumEntry[]>(`/lms/admin/programs/${programId}/curriculum`).then((r) => r.data);
export const addCurriculumEntryApi = (programId: string, data: { course_id: string; position?: number }) =>
  api.post<CurriculumEntry>(`/lms/admin/programs/${programId}/curriculum`, data).then((r) => r.data);
export const removeCurriculumEntryApi = (programId: string, courseId: string) =>
  api.delete<void>(`/lms/admin/programs/${programId}/curriculum/${courseId}`).then((r) => r.data);

// ── learning paths (self-paced ordered course sequences, 2026-08-08) ───────

export interface AdminLearningPath {
  id: string;
  title: string;
  description: string | null;
  is_published: boolean;
  created_by: string;
  created_at: string | null;
  image_url: string | null;
}

export interface LearningPathStepEntry {
  id: string;
  learning_path_id: string;
  course_id: string;
  position: number;
}

// ── staff assignment (2026-08-12) ───────────────────────────────────────────

export const searchStaffApi = (params: { role?: string; q?: string } = {}) =>
  api.get<StaffOption[]>("/lms/admin/users", { params }).then((r) => r.data);

export const listCourseRosterApi = (courseId: string) =>
  api.get<AdminEnrollment[]>(`/lms/admin/courses/${courseId}/roster`).then((r) => r.data);

export const grantCourseEnrollmentApi = (courseId: string, userId: string) =>
  api.post<AdminEnrollment>(`/lms/admin/courses/${courseId}/enrollments`, { user_id: userId }).then((r) => r.data);

export const bulkGrantCourseEnrollmentApi = (courseId: string, body: { role?: string; cohort_id?: string }) =>
  api.post<BulkGrantResult>(`/lms/admin/courses/${courseId}/enrollments/bulk`, body).then((r) => r.data);

export const revokeCourseEnrollmentApi = (enrollmentId: string) =>
  api.post<AdminEnrollment>(`/lms/admin/enrollments/${enrollmentId}/revoke`).then((r) => r.data);

// ── student management (2026-08-12) ─────────────────────────────────────────

export const searchStudentsApi = (params: { q?: string; invite_code?: string } = {}) =>
  api.get<StudentSummary[]>("/lms/admin/students", { params }).then((r) => r.data);

// ── student invite codes (2026-08-13) ───────────────────────────────────────

export const listInviteCodesApi = () =>
  api.get<InviteCode[]>("/lms/admin/invite-codes").then((r) => r.data);

export const createInviteCodeApi = (data: {
  code: string; label?: string | null; max_uses?: number; is_active?: boolean;
}) => api.post<InviteCode>("/lms/admin/invite-codes", data).then((r) => r.data);

export const updateInviteCodeApi = (id: string, data: Partial<{
  code: string; label: string | null; max_uses: number; is_active: boolean;
}>) => api.patch<InviteCode>(`/lms/admin/invite-codes/${id}`, data).then((r) => r.data);

export const deleteInviteCodeApi = (id: string) =>
  api.delete<void>(`/lms/admin/invite-codes/${id}`).then((r) => r.data);

export const getStudentProfileApi = (userId: string) =>
  api.get<StudentProfile>(`/lms/admin/students/${userId}`).then((r) => r.data);

export const listUserEnrollmentsApi = (userId: string) =>
  api.get<AdminEnrollment[]>(`/lms/admin/users/${userId}/enrollments`).then((r) => r.data);

export const listLearningPathsApi = () =>
  api.get<AdminLearningPath[]>("/lms/admin/learning-paths").then((r) => r.data);
export const getLearningPathApi = (id: string) =>
  api.get<AdminLearningPath>(`/lms/admin/learning-paths/${id}`).then((r) => r.data);
export const createLearningPathApi = (data: { title: string; description?: string }) =>
  api.post<AdminLearningPath>("/lms/admin/learning-paths", data).then((r) => r.data);
export const updateLearningPathApi = (
  id: string, data: Partial<{ title: string; description: string; is_published: boolean }>,
) => api.patch<AdminLearningPath>(`/lms/admin/learning-paths/${id}`, data).then((r) => r.data);
export const deleteLearningPathApi = (id: string) =>
  api.delete<void>(`/lms/admin/learning-paths/${id}`).then((r) => r.data);
export const uploadLearningPathImageApi = (id: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post<AdminLearningPath>(`/lms/admin/learning-paths/${id}/image`, form).then((r) => r.data);
};

export const listLearningPathStepsApi = (pathId: string) =>
  api.get<LearningPathStepEntry[]>(`/lms/admin/learning-paths/${pathId}/steps`).then((r) => r.data);
export const addLearningPathStepApi = (pathId: string, data: { course_id: string; position?: number }) =>
  api.post<LearningPathStepEntry>(`/lms/admin/learning-paths/${pathId}/steps`, data).then((r) => r.data);
export const removeLearningPathStepApi = (pathId: string, courseId: string) =>
  api.delete<void>(`/lms/admin/learning-paths/${pathId}/steps/${courseId}`).then((r) => r.data);
