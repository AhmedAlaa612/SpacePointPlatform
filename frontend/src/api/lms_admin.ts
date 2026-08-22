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
  access_mode: "open" | "invite" | "paid";
  access_days: number | null;
  // Stage S (Stripe Checkout) — integer minor units, matching Stripe's
  // unit_amount. Only meaningful when access_mode === "paid".
  price_cents: number | null;
  currency: string;
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
  school_name: string | null;
  grade: string | null;
  status: string | null;
  created_at: string | null;
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
  avatar: string | null;
  email: string;
  programs: StudentProgram[];
}

export interface CourseMetadataInput {
  outcomes?: string[];
  level?: CourseLevel | null;
  track?: string | null;
  instructor_id?: string | null;
  instructor_title?: string | null;
  access_mode?: "open" | "invite" | "paid";
  price_cents?: number | null;
  currency?: string;
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

// ── LMS Program checklist (2026-08-21 redesign) ─────────────────────────────
// Replaces the old program_curriculum flat course list (above, removed) —
// see backend/app/models/lms/program.py's module docstring for the full shape.

export type LmsProgramItemType = "course" | "mission_run" | "external_link" | "submission" | "article" | "manual";

export interface LmsProgramItem {
  id: string;
  position: number;
  item_type: LmsProgramItemType;
  title: string;
  description: string | null;
  optional: boolean;
  requires_confirmation: boolean;
  course_id: string | null;
  mission_id: string | null;
  variant_id: string | null;
  external_url: string | null;
  submission_prompt: string | null;
}

export interface LmsProgramItemInput {
  item_type: LmsProgramItemType;
  title: string;
  description?: string | null;
  optional?: boolean;
  requires_confirmation?: boolean;
  course_id?: string | null;
  mission_id?: string | null;
  variant_id?: string | null;
  external_url?: string | null;
  submission_prompt?: string | null;
  position?: number | null;
}

export interface LmsProgram {
  id: string;
  program_id: string | null;
  name: string;
  description: string | null;
  certificate_required: boolean;
  items: LmsProgramItem[];
}

export interface LmsProgramCohortEffective {
  cohort_id: string;
  lms_program_id: string;
  /** True when this is the program's own checklist shown as an editable
   * starting point — no override exists yet. Editing it forks a real
   * per-cohort override server-side (2026-08-22); the UI doesn't need to
   * call anything extra for that, just edit and refetch. */
  is_inherited: boolean;
  items: LmsProgramItem[];
}

export const listLmsProgramsApi = (programId?: string) =>
  api.get<LmsProgram[]>("/lms/admin/programs", { params: programId ? { program_id: programId } : undefined }).then((r) => r.data);
export const createLmsProgramApi = (data: { program_id?: string | null; name: string; description?: string | null; certificate_required?: boolean }) =>
  api.post<LmsProgram>("/lms/admin/programs", data).then((r) => r.data);
export const getLmsProgramApi = (id: string) =>
  api.get<LmsProgram>(`/lms/admin/programs/${id}`).then((r) => r.data);
export const updateLmsProgramApi = (id: string, data: Partial<{ name: string; description: string | null; certificate_required: boolean }>) =>
  api.patch<LmsProgram>(`/lms/admin/programs/${id}`, data).then((r) => r.data);
export const deleteLmsProgramApi = (id: string) =>
  api.delete<void>(`/lms/admin/programs/${id}`).then((r) => r.data);

export const addLmsProgramItemApi = (lmsProgramId: string, data: LmsProgramItemInput) =>
  api.post<LmsProgramItem>(`/lms/admin/programs/${lmsProgramId}/items`, data).then((r) => r.data);
export const updateLmsProgramItemApi = (lmsProgramId: string, itemId: string, data: LmsProgramItemInput) =>
  api.patch<LmsProgramItem>(`/lms/admin/programs/${lmsProgramId}/items/${itemId}`, data).then((r) => r.data);
export const deleteLmsProgramItemApi = (lmsProgramId: string, itemId: string) =>
  api.delete<void>(`/lms/admin/programs/${lmsProgramId}/items/${itemId}`).then((r) => r.data);

export const getCohortProgramOverrideApi = (cohortId: string) =>
  api.get<LmsProgramCohortEffective>(`/lms/admin/cohorts/${cohortId}/program-override`).then((r) => r.data);
export const addCohortOverrideItemApi = (cohortId: string, data: LmsProgramItemInput) =>
  api.post<LmsProgramItem>(`/lms/admin/cohorts/${cohortId}/program-override/items`, data).then((r) => r.data);
export const updateCohortOverrideItemApi = (cohortId: string, itemId: string, data: LmsProgramItemInput) =>
  api.patch<LmsProgramItem>(`/lms/admin/cohorts/${cohortId}/program-override/items/${itemId}`, data).then((r) => r.data);
export const deleteCohortOverrideItemApi = (cohortId: string, itemId: string) =>
  api.delete<void>(`/lms/admin/cohorts/${cohortId}/program-override/items/${itemId}`).then((r) => r.data);

// ── instructor progress (cohort-scoped roster + confirm) ────────────────────

export interface PendingConfirmation {
  item_id: string;
  title: string;
  submitted_url: string | null;
}

export interface LmsProgramRosterRow {
  assignment_id: string;
  user_id: string;
  student_name: string;
  name: string;
  items_total: number;
  items_done: number;
  pct: number;
  next_item_title: string | null;
  certificate_required: boolean;
  certificate_earned: boolean;
  pending_confirmations: PendingConfirmation[];
}

export const getCohortProgramProgressApi = (cohortId: string) =>
  api.get<LmsProgramRosterRow[]>(`/lms/instructor/cohorts/${cohortId}/program-progress`).then((r) => r.data);
export const confirmChecklistItemApi = (cohortId: string, assignmentId: string, itemId: string) =>
  api.post<LmsProgramRosterRow>(
    `/lms/instructor/cohorts/${cohortId}/program-progress/${assignmentId}/items/${itemId}/confirm`, {},
  ).then((r) => r.data);

// ── program-merge additions (2026-08-22) — program-wide roster, per-item
// detail, instructor-reachable programs, and instructor mirrors of the
// student-profile endpoints below. `/lms/instructor/*` works for staff too
// (the backend dependency lets ops/facilitator/admin through unrestricted),
// so these are the ones the merged Programs page should call regardless of
// role — only checklist *authoring* (add/edit/delete items) stays on the
// `/lms/admin/*` functions above, which 403 for a plain instructor.

export const getMyReachableProgramsApi = () =>
  api.get<LmsProgram[]>("/lms/instructor/programs").then((r) => r.data);

export const getProgramProgressApi = (lmsProgramId: string) =>
  api.get<LmsProgramRosterRow[]>(`/lms/instructor/programs/${lmsProgramId}/progress`).then((r) => r.data);

export interface LmsAssignmentItemDetail {
  item_id: string;
  title: string;
  item_type: LmsProgramItemType;
  status: string;
  submitted_url: string | null;
  completed_at: string | null;
  mission_attempt_id: string | null;
  confirmed_by_user_id: string | null;
}

export const getAssignmentItemsApi = (cohortId: string, assignmentId: string) =>
  api.get<LmsAssignmentItemDetail[]>(
    `/lms/instructor/cohorts/${cohortId}/program-progress/${assignmentId}/items`,
  ).then((r) => r.data);

export const getStudentProfileInstructorApi = (userId: string) =>
  api.get<StudentProfile>(`/lms/instructor/students/${userId}`).then((r) => r.data);

export const listUserEnrollmentsInstructorApi = (userId: string) =>
  api.get<AdminEnrollment[]>(`/lms/instructor/students/${userId}/enrollments`).then((r) => r.data);

export const getStudentDesignRunsInstructorApi = (userId: string) =>
  api.get<StudentDesignRunsOut>(`/lms/instructor/students/${userId}/design-runs`).then((r) => r.data);

export interface CourseProgressModule {
  module_id: string;
  title: string | null;
  position: number;
  locked: boolean;
  mandatory_total: number;
  mandatory_completed: number;
}

export interface CourseProgressQuiz {
  item_id: string;
  title: string | null;
  status: string;
  attempts: number;
  best_score: number | null;
}

export interface StudentCourseProgress {
  course_id: string;
  course_title: string | null;
  completed: boolean;
  modules: CourseProgressModule[];
  quizzes: CourseProgressQuiz[];
}

export const getStudentCourseProgressApi = (userId: string, courseId: string, role: "admin" | "instructor") =>
  api.get<StudentCourseProgress>(
    `/lms/${role === "admin" ? "admin" : "instructor"}/students/${userId}/courses/${courseId}/progress`,
  ).then((r) => r.data);

// ── learning paths (self-paced ordered course sequences, 2026-08-08) ───────

export interface AdminLearningPath {
  id: string;
  title: string;
  description: string | null;
  is_published: boolean;
  created_by: string;
  created_at: string | null;
  image_url: string | null;
  // Bundle pricing (2026-08-21) — null price_cents means not purchasable.
  price_cents: number | null;
  currency: string;
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

// Same one-shot cohort/role grant, but for a learning-path bundle — enrols
// every step's course at once (2026-08-21).
export const bulkGrantLearningPathEnrollmentApi = (pathId: string, body: { role?: string; cohort_id?: string }) =>
  api.post<BulkGrantResult>(`/lms/admin/learning-paths/${pathId}/enrollments/bulk`, body).then((r) => r.data);

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

// ── invite-code course/path grants (2026-08-21) ─────────────────────────────
// "This code batch gets these courses/paths free" — applies immediately to
// everyone who's ever used the code, and to every future signup on it.

export interface InviteCodeGrant {
  id: string;
  product_type: "course" | "learning_path";
  course_id: string | null;
  course_title: string | null;
  learning_path_id: string | null;
  learning_path_title: string | null;
  created_at: string | null;
}

export const listInviteCodeGrantsApi = (codeId: string) =>
  api.get<InviteCodeGrant[]>(`/lms/admin/invite-codes/${codeId}/grants`).then((r) => r.data);

export const createInviteCodeGrantApi = (
  codeId: string, data: { course_id?: string; learning_path_id?: string },
) => api.post<{ grant: InviteCodeGrant; accounts_enrolled: number }>(
  `/lms/admin/invite-codes/${codeId}/grants`, data,
).then((r) => r.data);

export const deleteInviteCodeGrantApi = (codeId: string, grantId: string) =>
  api.delete<void>(`/lms/admin/invite-codes/${codeId}/grants/${grantId}`).then((r) => r.data);

export const getStudentProfileApi = (userId: string) =>
  api.get<StudentProfile>(`/lms/admin/students/${userId}`).then((r) => r.data);

export const listUserEnrollmentsApi = (userId: string) =>
  api.get<AdminEnrollment[]>(`/lms/admin/users/${userId}/enrollments`).then((r) => r.data);

// ── student design-mission run history (2026-08-16) ─────────────────────────

export interface StudentDesignRun {
  attempt_id: string;
  design_name: string;
  design_objective: string | null;
  variant_label: string;
  status: "in_progress" | "submitted" | "passed" | "failed" | "abandoned";
  attempt_no: number;
  started_at: string | null;
  steps: Record<string, boolean> | null;
}

export interface StudentDesignRunsOut {
  step_labels: { key: string; label: string }[];
  runs: StudentDesignRun[];
}

export const getStudentDesignRunsApi = (userId: string) =>
  api.get<StudentDesignRunsOut>(`/lms/admin/students/${userId}/design-runs`).then((r) => r.data);

export const listLearningPathsApi = () =>
  api.get<AdminLearningPath[]>("/lms/admin/learning-paths").then((r) => r.data);
export const getLearningPathApi = (id: string) =>
  api.get<AdminLearningPath>(`/lms/admin/learning-paths/${id}`).then((r) => r.data);
export const createLearningPathApi = (
  data: { title: string; description?: string; price_cents?: number | null; currency?: string },
) => api.post<AdminLearningPath>("/lms/admin/learning-paths", data).then((r) => r.data);
export const updateLearningPathApi = (
  id: string,
  data: Partial<{
    title: string; description: string; is_published: boolean; price_cents: number | null; currency: string;
  }>,
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
