/** LMS authoring API (LM1-13) — thin wrappers over `/lms/admin/*` (LM1-5) +
 * the video upload route (LM1-6). Types mirror `schemas/lms_admin.py`. */
import { api } from "@/api/client";
import type { VideoPlaybackInfo } from "@/components/video/VideoPlayer";

export type CourseKind = "course" | "mission";
export type CourseLevel = "beginner" | "intermediate" | "advanced";
export type ModuleItemKind = "video" | "text" | "quiz" | "flashcards" | "attachment";

export interface AdminCourse {
  id: string;
  title: string;
  description: string | null;
  kind: CourseKind;
  is_published: boolean;
  created_by?: string | null;
  created_by_name?: string | null;
  created_at?: string | null;


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
  // Per-course certificate opt-out (2026-09-14). Default true. False stops
  // a new completion certificate from being issued for this course; never
  // revokes one already issued, never blocks a learning-path certificate.
  certificate_enabled: boolean;
  average_rating?: number | null;
  ratings_count?: number;
}

export interface CourseRatingDetail {
  id: string;
  user_id: string;
  student_name: string;
  student_email?: string | null;
  student_photo_url?: string | null;
  rating: number;
  review_text?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CourseRatingsSummary {
  course_id: string;
  average_rating: number | null;
  total_count: number;
  distribution: Record<string, number>;
  ratings: CourseRatingDetail[];
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

/** A path's named-individual assignment row (2026-09-15) — unlike a course
 * enrollment, a path grant is several Enrollment rows under the hood (one
 * per step), so `user_id` itself is the identity revoke takes, not a
 * synthetic id. `steps_owned`/`steps_total` distinguish a full grant from
 * a partial one (e.g. a step added to the path after the grant). */
export interface LearningPathRosterRow {
  user_id: string;
  student_name: string;
  student_email: string;
  status: string;
  steps_owned: number;
  steps_total: number;
}

export interface StudentSummary {
  id: string;
  full_name: string;
  nickname: string | null;
  email: string;
  invite_code: string | null;
  invite_label: string | null;
  invite_codes?: { code: string; label: string | null; kind: string; redeemed_at: string }[];
  school_name: string | null;
  grade: string | null;
  status: string | null;
  created_at: string | null;
  /** Set the moment a login actually succeeds — null means this account
   * (self-signup or ops-created) has never once been logged into. */
  last_login_at: string | null;
}

export interface InviteCode {
  id: string;
  code: string;
  /** student|observer (observer added 2026-10 — external tester batches). */
  kind: string;
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
  registration_id: string | null;
  assignment_id: string | null;
  cohort_id: string;
  program_name: string;
  cohort_name: string;
  starts_on: string | null;
  ends_on: string | null;
  mode: string;
  team_id: string | null;
  team_name: string | null;
  team_join_code: string | null;
}

export interface StudentTeam {
  team_id: string;
  team_name: string;
  cohort_id: string | null;
  cohort_name: string | null;
  join_code: string | null;
  is_observer: boolean;
}

export interface StudentCertificate {
  id: string;
  type: string;
  title: string;
  generated_at: string | null;
  url: string | null;
  cohort_id: string | null;
  course_id: string | null;
}

export interface StudentProfile {
  id: string;
  full_name: string;
  nickname: string | null;
  avatar: string | null;
  email: string;
  is_observer?: boolean;
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
  certificate_enabled?: boolean;
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
  image_url?: string | null;
  options: AdminQuizOption[];
}

export type VideoTranscodeStatus = "pending" | "processing" | "ready" | "failed";

export type AdminItemContent =
  | { body: string }
  | { pass_threshold: number; questions: AdminQuizQuestion[]; random_count?: number | null }
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
export const getCourseRatingsApi = (courseId: string) =>
  api.get<CourseRatingsSummary>(`/lms/admin/courses/${courseId}/ratings`).then((r) => r.data);
export const createCourseApi = (
  data: { title: string; description?: string; kind?: CourseKind } & CourseMetadataInput,
) => api.post<AdminCourse>("/lms/admin/courses", data).then((r) => r.data);
export const updateCourseApi = (
  id: string, data: Partial<{ title: string; description: string; kind: CourseKind }> & CourseMetadataInput,
) => api.patch<AdminCourse>(`/lms/admin/courses/${id}`, data).then((r) => r.data);
export const publishCourseApi = (id: string) => api.post<AdminCourse>(`/lms/admin/courses/${id}/publish`).then((r) => r.data);
export const unpublishCourseApi = (id: string) => api.post<AdminCourse>(`/lms/admin/courses/${id}/unpublish`).then((r) => r.data);
export const submitCourseForReviewApi = (id: string) =>
  api.post<{ message: string }>(`/lms/admin/courses/${id}/submit-review`).then((r) => r.data);
export const deleteCourseApi = (id: string) => api.delete<void>(`/lms/admin/courses/${id}`).then((r) => r.data);
export const uploadCourseImageApi = (id: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post<AdminCourse>(`/lms/admin/courses/${id}/image`, form).then((r) => r.data);
};
export const listInstructorOptionsApi = () =>
  api.get<InstructorOption[]>("/lms/admin/instructors").then((r) => r.data);

// Per-course R2/VPS video migration visibility (2026-09) — mirrors
// scripts/video_migrate_to_r2.py's --status/--reencode as an API so
// migrating one course at a time doesn't need an SSH session.
export interface CourseVideoBackend {
  course_id: string;
  title: string;
  r2: number;
  vps: number;
}
export const getCoursesVideoBackendStatusApi = () =>
  api.get<CourseVideoBackend[]>("/lms/admin/courses/video-backend-status").then((r) => r.data);
export const migrateCourseVideosToR2Api = (courseId: string) =>
  api.post<{ queued: number; already_on_r2: number; still_processing: number }>(
    `/lms/admin/courses/${courseId}/videos/migrate-to-r2`,
  ).then((r) => r.data);

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

export const getAdminAttachmentUrlApi = (itemId: string) =>
  api.get<{ url: string; filename: string | null }>(`/lms/admin/items/${itemId}/attachment/url`).then((r) => r.data);

export const getAdminVideoPlaybackApi = (itemId: string) =>
  api.get<{ url: string; video_info: any }>(`/lms/admin/items/${itemId}/video/playback`).then((r) => r.data);

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

export type LmsProgramItemType =
  | "course" | "mission_run" | "external_link" | "submission" | "pdf" | "manual" | "session" | "quiz" | "team_setup" | "checkpoint" | "arcade_game";
/** individual (default): per-student progress. team: the whole Team shares
 * one progress row — only valid for submission/external_link/manual/
 * mission_run/team_setup items (enforced server-side in
 * services/lms/program.py). `team_setup` is always team — there's no
 * individual variant, so authoring it never offers the choice. */
export type LmsProgramItemScope = "individual" | "team";

/** One entry in ops's own fixed field set for a `submission_multi_link`
 * item (2026-09-14, text fields added 2026-09-16) — see
 * `LmsProgramItem.submission_link_labels`. field_type picks whether the
 * student sees a link input or a text area for this slot. */
export interface LmsProgramItemLinkLabel {
  label: string;
  required: boolean;
  field_type: "text" | "link";
}

export interface LmsProgramItem {
  id: string;
  position: number;
  item_type: LmsProgramItemType;
  title: string;
  description: string | null;
  optional: boolean;
  requires_confirmation: boolean;
  scope: LmsProgramItemScope;
  course_id: string | null;
  mission_id: string | null;
  /** `Mission.kind` for a mission_run item — null otherwise. Only
   * kind === "design" missions have build steps/gates to configure;
   * anything else has nothing for StepsTab/GatesTab to show. */
  mission_kind: string | null;
  variant_id: string | null;
  external_url: string | null;
  arcade_game_id?: string | null;
  arcade_game_key?: string | null;
  arcade_game_title?: string | null;
  arcade_game_mode?: "explorer" | "engineer" | "either" | null;
  submission_prompt: string | null;
  /** The plain (non-multi) submission's own type — link (default) or text.
   * Only meaningful when submission_multi_link is false. */
  submission_field_type: "text" | "link";
  /** Ops's per-item toggle (2026-09-14) — a submission item takes several
   * labeled links instead of one (e.g. Member 1/Member 2/Team link). */
  submission_multi_link: boolean;
  /** Ops's own fixed label set for this item (2026-09-14), in the order
   * ops entered them — null keeps (or reverts to) free-text,
   * student-entered labels. */
  submission_link_labels: LmsProgramItemLinkLabel[] | null;
  /** True once a `pdf` item has a file uploaded — fetch the actual URL
   * on demand via `getLmsProgramItemPdfUrlApi`, never baked in here. */
  has_pdf: boolean;
  /** submission-only cutoff — the backend rejects a new/replaced
   * submission past this, but never blocks confirming one already in. */
  deadline_at: string | null;
  /** session-only fields — always self-contained, never a live link to a
   * real Sessions-domain row (see the model's own comment). */
  session_date: string | null;
  session_starts_at: string | null;
  session_location: string | null;
  session_meeting_url: string | null;
  /** A `quiz` item's fixed question set — see `app/models/lms/cohort_quiz.py`. */
  cohort_quiz_template_id: string | null;
  /** "N questions" badge — only populated for a `quiz` item. */
  cohort_quiz_question_count: number | null;
  // ── Roadmap board (2026-09) ────────────────────────────────────────────
  /** Which single Madar design phase a `mission_run` item targets — null
   * means the whole mission. See MISSION_STEP_KEYS below. */
  mission_step_key: string | null;
  /** Locked until every earlier non-optional item on this checklist is done. */
  gated: boolean;
  guideline_kind: "pdf" | "link" | "video" | null;
  guideline_url: string | null;
  /** True once a `video`-kind guideline has a real file uploaded through
   * the standardized video service — same never-baked-in-here posture as
   * `has_pdf`. `guideline_url` stays the pasted embed link when false. */
  guideline_video_uploaded: boolean;
  /** Groups tiles into the board's row sections ("Checkpoint 1 — Learn &
   * plan") — free text, matched by exact string. */
  checkpoint_label: string | null;
  /** Team formation — max members for a team_setup item, null = unlimited. */
  max_team_size: number | null;
}

/** Mirrors the backend's MISSION_STEP_KEYS (services/lms/program.py) — the
 * eight real Madar design phases plus `setup`/`report`, whose completion is
 * inferred rather than read off a gate/selection row. `data_budget`,
 * `link_budget` and `cost_budget` are still selectable here (Madar itself
 * still has them) even though the client asked to hide them from this
 * competition's roadmap — that's done by simply not authoring items for
 * them, not by removing them from the vocabulary. */
export const MISSION_STEP_KEYS: { value: string; label: string }[] = [
  { value: "setup", label: "Name the mission" },
  { value: "components", label: "Components" },
  { value: "conops", label: "CONOPS" },
  { value: "power_budget", label: "Power budget" },
  { value: "mass_budget", label: "Mass budget" },
  { value: "data_budget", label: "Data budget" },
  { value: "link_budget", label: "Link budget" },
  { value: "cost_budget", label: "Cost budget" },
  { value: "report", label: "Report" },
  { value: "poster", label: "Mission poster" },
];

export interface LmsProgramItemInput {
  item_type: LmsProgramItemType;
  title: string;
  description?: string | null;
  optional?: boolean;
  requires_confirmation?: boolean;
  scope?: LmsProgramItemScope;
  course_id?: string | null;
  mission_id?: string | null;
  variant_id?: string | null;
  external_url?: string | null;
  submission_prompt?: string | null;
  submission_field_type?: "text" | "link";
  submission_multi_link?: boolean;
  submission_link_labels?: LmsProgramItemLinkLabel[] | null;
  deadline_at?: string | null;
  session_date?: string | null;
  session_starts_at?: string | null;
  session_location?: string | null;
  session_meeting_url?: string | null;
  cohort_quiz_template_id?: string | null;
  arcade_game_id?: string | null;
  arcade_game_mode?: "explorer" | "engineer" | "either" | null;
  position?: number | null;
  mission_step_key?: string | null;
  gated?: boolean;
  guideline_kind?: "pdf" | "link" | "video" | null;
  guideline_url?: string | null;
  checkpoint_label?: string | null;
  max_team_size?: number | null;
}

export interface LmsProgram {
  id: string;
  program_id: string | null;
  name: string;
  description: string | null;
  certificate_required: boolean;
  poster_template_url?: string | null;
  image_url: string | null;
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
  poster_template_url?: string | null;
  inherited_poster_template_url?: string | null;
  items: LmsProgramItem[];
}

export const listLmsProgramsApi = (programId?: string) =>
  api.get<LmsProgram[]>("/lms/admin/programs", { params: programId ? { program_id: programId } : undefined }).then((r) => r.data);
export const createLmsProgramApi = (data: { program_id?: string | null; name: string; description?: string | null; certificate_required?: boolean; poster_template_url?: string | null }) =>
  api.post<LmsProgram>("/lms/admin/programs", data).then((r) => r.data);
export const getLmsProgramApi = (id: string) =>
  api.get<LmsProgram>(`/lms/admin/programs/${id}`).then((r) => r.data);
export const updateLmsProgramApi = (id: string, data: Partial<{ name: string; description: string | null; certificate_required: boolean; poster_template_url: string | null }>) =>
  api.patch<LmsProgram>(`/lms/admin/programs/${id}`, data).then((r) => r.data);
export const deleteLmsProgramApi = (id: string) =>
  api.delete<void>(`/lms/admin/programs/${id}`).then((r) => r.data);
export const updateCohortPosterTemplateApi = (cohortId: string, posterTemplateUrl: string | null) =>
  api.patch<LmsProgramCohortEffective>(`/lms/admin/cohorts/${cohortId}/poster-template`, { poster_template_url: posterTemplateUrl }).then((r) => r.data);
export const uploadLmsProgramImageApi = (id: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post<LmsProgram>(`/lms/admin/programs/${id}/image`, form).then((r) => r.data);
};

export const addLmsProgramItemApi = (lmsProgramId: string, data: LmsProgramItemInput) =>
  api.post<LmsProgramItem>(`/lms/admin/programs/${lmsProgramId}/items`, data).then((r) => r.data);
export const updateLmsProgramItemApi = (lmsProgramId: string, itemId: string, data: LmsProgramItemInput) =>
  api.patch<LmsProgramItem>(`/lms/admin/programs/${lmsProgramId}/items/${itemId}`, data).then((r) => r.data);
export const deleteLmsProgramItemApi = (lmsProgramId: string, itemId: string) =>
  api.delete<void>(`/lms/admin/programs/${lmsProgramId}/items/${itemId}`).then((r) => r.data);
export const reorderLmsProgramItemsApi = (lmsProgramId: string, itemIds: string[]) =>
  api.post<LmsProgramItem[]>(`/lms/admin/programs/${lmsProgramId}/items/reorder`, { item_ids: itemIds }).then((r) => r.data);

// Flat by item_id — same LmsProgramItem row regardless of whether it's
// program- or cohort-override-owned, so no need for a separate owner-scoped
// path (mirrors routers/lms/admin.py's own item_id-only routes).
export const uploadLmsProgramItemPdfApi = (itemId: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post<LmsProgramItem>(`/lms/admin/items/${itemId}/pdf`, form).then((r) => r.data);
};
export const deleteLmsProgramItemPdfApi = (itemId: string) =>
  api.delete<LmsProgramItem>(`/lms/admin/items/${itemId}/pdf`).then((r) => r.data);
export const getLmsProgramItemPdfUrlApi = (itemId: string) =>
  api.get<{ url: string }>(`/lms/admin/items/${itemId}/pdf-url`).then((r) => r.data.url);

export const attachLmsProgramItemGuidelineVideoEmbedApi = (itemId: string, url: string) =>
  api.post<LmsProgramItem>(`/lms/admin/items/${itemId}/guideline/video/embed`, { url }).then((r) => r.data);
export const uploadLmsProgramItemGuidelineVideoApi = (itemId: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post<LmsProgramItem>(`/lms/admin/items/${itemId}/guideline/video/upload`, form).then((r) => r.data);
};
export const deleteLmsProgramItemGuidelineVideoApi = (itemId: string) =>
  api.delete<LmsProgramItem>(`/lms/admin/items/${itemId}/guideline/video`).then((r) => r.data);
export const getLmsProgramItemGuidelineVideoUrlApi = (itemId: string) =>
  api.get<{ url: string; video_info: VideoPlaybackInfo }>(`/lms/admin/items/${itemId}/guideline/video/url`)
    .then((r) => r.data);

export const getCohortProgramOverrideApi = (cohortId: string) =>
  api.get<LmsProgramCohortEffective>(`/lms/admin/cohorts/${cohortId}/program-override`).then((r) => r.data);
export const addCohortOverrideItemApi = (cohortId: string, data: LmsProgramItemInput) =>
  api.post<LmsProgramItem>(`/lms/admin/cohorts/${cohortId}/program-override/items`, data).then((r) => r.data);
export const updateCohortOverrideItemApi = (cohortId: string, itemId: string, data: LmsProgramItemInput) =>
  api.patch<LmsProgramItem>(`/lms/admin/cohorts/${cohortId}/program-override/items/${itemId}`, data).then((r) => r.data);
export const deleteCohortOverrideItemApi = (cohortId: string, itemId: string) =>
  api.delete<void>(`/lms/admin/cohorts/${cohortId}/program-override/items/${itemId}`).then((r) => r.data);
export const reorderCohortOverrideItemsApi = (cohortId: string, itemIds: string[]) =>
  api.post<LmsProgramItem[]>(`/lms/admin/cohorts/${cohortId}/program-override/items/reorder`, { item_ids: itemIds }).then((r) => r.data);
/** One-off catch-up for a cohort edited before 2026-08-27 — every add now
 * backfills already-assigned students automatically, but this fixes
 * cohorts a checklist step was added to before that shipped. */
export const resyncCohortProgramAssignmentsApi = (cohortId: string) =>
  api.post<{ items_added: number }>(`/lms/admin/cohorts/${cohortId}/program-override/resync`).then((r) => r.data);

// Instructor mirrors (2026-08-23, fixes a real 403 — instructors had no way
// to even read their own cohort's checklist). Same shape, cohort-scoped;
// write is server-restricted to mission_run items for a plain instructor —
// see `routers/lms/instructor.py`'s own comment for the exact boundary.
export const getCohortProgramOverrideInstructorApi = (cohortId: string) =>
  api.get<LmsProgramCohortEffective>(`/lms/instructor/cohorts/${cohortId}/program-override`).then((r) => r.data);
export const addCohortOverrideItemInstructorApi = (cohortId: string, data: LmsProgramItemInput) =>
  api.post<LmsProgramItem>(`/lms/instructor/cohorts/${cohortId}/program-override/items`, data).then((r) => r.data);
export const updateCohortOverrideItemInstructorApi = (cohortId: string, itemId: string, data: LmsProgramItemInput) =>
  api.patch<LmsProgramItem>(`/lms/instructor/cohorts/${cohortId}/program-override/items/${itemId}`, data).then((r) => r.data);
export const deleteCohortOverrideItemInstructorApi = (cohortId: string, itemId: string) =>
  api.delete<void>(`/lms/instructor/cohorts/${cohortId}/program-override/items/${itemId}`).then((r) => r.data);

// ── instructor progress (cohort-scoped roster + confirm) ────────────────────

export interface PendingConfirmation {
  item_id: string;
  title: string;
  submitted_url: string | null;
  submission_field_type: "text" | "link";
  submitted_text: string | null;
  submission_multi_link: boolean;
  submitted_links: { label: string | null; url: string | null; text: string | null }[] | null;
}

export interface LmsProgramRosterRow {
  assignment_id: string;
  user_id: string;
  student_name: string;
  name: string;
  /** participant|observer (observer added 2026-10) — the roster's
   * `[Students | Observers]` toggle filters on this. */
  mode: string;
  items_total: number;
  items_done: number;
  pct: number;
  next_item_title: string | null;
  certificate_required: boolean;
  certificate_earned: boolean;
  pending_confirmations: PendingConfirmation[];
}

export type RosterMode = "participant" | "observer" | "all";

export const getCohortProgramProgressApi = (cohortId: string, mode: RosterMode = "participant") =>
  api.get<LmsProgramRosterRow[]>(`/lms/instructor/cohorts/${cohortId}/program-progress`, {
    params: { mode },
  }).then((r) => r.data);
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

export const getProgramProgressApi = (lmsProgramId: string, mode: RosterMode = "participant") =>
  api.get<LmsProgramRosterRow[]>(`/lms/instructor/programs/${lmsProgramId}/progress`, {
    params: { mode },
  }).then((r) => r.data);

export interface LmsAssignmentItemDetail {
  item_id: string;
  title: string;
  item_type: LmsProgramItemType;
  status: string;
  submitted_url: string | null;
  submission_field_type: "text" | "link";
  submitted_text: string | null;
  submission_multi_link: boolean;
  submitted_links: { label: string | null; url: string | null; text: string | null }[] | null;
  completed_at: string | null;
  mission_attempt_id: string | null;
  confirmed_by_user_id: string | null;
  mission_step_key?: string | null;
  mission_kind: string | null;
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
  created_by?: string | null;
  created_by_name?: string | null;
  created_at?: string | null;


  image_url: string | null;
  access_mode: "open" | "invite" | "paid";
  // Bundle pricing (2026-08-21) — null price_cents means not purchasable.
  price_cents: number | null;
  currency: string;
}

export interface LearningPathMetadataInput {
  title?: string;
  description?: string;
  access_mode?: "open" | "invite" | "paid";
  price_cents?: number | null;
  currency?: string;
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

// Named-individual path assignment (2026-09-15) — the path equivalent of
// listCourseRosterApi/grantCourseEnrollmentApi/revokeCourseEnrollmentApi.
export const listLearningPathRosterApi = (pathId: string) =>
  api.get<LearningPathRosterRow[]>(`/lms/admin/learning-paths/${pathId}/roster`).then((r) => r.data);

export const grantLearningPathEnrollmentApi = (pathId: string, userId: string) =>
  api.post<LearningPathRosterRow>(
    `/lms/admin/learning-paths/${pathId}/enrollments`, { user_id: userId },
  ).then((r) => r.data);

export const revokeLearningPathEnrollmentApi = (pathId: string, userId: string) =>
  api.post<void>(`/lms/admin/learning-paths/${pathId}/enrollments/${userId}/revoke`).then((r) => r.data);

// ── student management (2026-08-12) ─────────────────────────────────────────

export const searchStudentsApi = (
  params: {
    q?: string;
    invite_code?: string;
    login_status?: "all" | "never" | "has_logged_in";
    mode?: "student" | "observer" | "all";
  } = {},
) => api.get<StudentSummary[]>("/lms/admin/students", { params }).then((r) => r.data);

export const updateStudentAccountApi = (userId: string, data: { email: string; full_name?: string }) =>
  api.patch<StudentProfile>(`/lms/admin/students/${userId}/account`, data).then((r) => r.data);
export const getStudentPasswordLinkApi = (userId: string) =>
  api.post<{ link: string }>(`/lms/admin/students/${userId}/set-password-link`).then((r) => r.data);
export const enrollStudentCohortApi = (userId: string, cohortId: string) =>
  api.post<{ detail: string }>(`/lms/admin/students/${userId}/cohorts`, { cohort_id: cohortId }).then((r) => r.data);
export const unenrollStudentCohortApi = (userId: string, cohortId: string) =>
  api.post<{ detail: string }>(`/lms/admin/students/${userId}/cohorts/${cohortId}/unenroll`).then((r) => r.data);
export const getStudentTeamsApi = (userId: string) =>
  api.get<StudentTeam[]>(`/lms/admin/students/${userId}/teams`).then((r) => r.data);
export const getStudentCertificatesApi = (userId: string) =>
  api.get<StudentCertificate[]>(`/lms/admin/students/${userId}/certificates`).then((r) => r.data);

// ── student invite codes (2026-08-13) ───────────────────────────────────────

export const listInviteCodesApi = () =>
  api.get<InviteCode[]>("/lms/admin/invite-codes").then((r) => r.data);

export const createInviteCodeApi = (data: {
  code: string; label?: string | null; max_uses?: number; is_active?: boolean;
  kind?: "student" | "observer";
  expires_at?: string | null;
}) => api.post<InviteCode>("/lms/admin/invite-codes", data).then((r) => r.data);

export const updateInviteCodeApi = (id: string, data: Partial<{
  code: string; label: string | null; max_uses: number; is_active: boolean;
  expires_at: string | null;
}>) => api.patch<InviteCode>(`/lms/admin/invite-codes/${id}`, data).then((r) => r.data);

export const deleteInviteCodeApi = (id: string) =>
  api.delete<void>(`/lms/admin/invite-codes/${id}`).then((r) => r.data);

export interface TryAsObserverPayload {
  team_action?: "none" | "join" | "create";
  team_id?: string;
  team_name?: string;
}

export interface ObserverTeamSummary {
  id: string;
  name: string;
  member_count: number;
  member_names: string[];
  is_my_team: boolean;
}

/** Staff authoring access (2026-10, observer mode) — "Try as
 * Observer". Creates (or reuses) the caller's own mode='observer'
 * assignment for this cohort and returns its id; the caller navigates to
 * `/learn/checklists/{assignment_id}`. */
export const tryAsObserverApi = (cohortId: string, payload?: TryAsObserverPayload) =>
  api.post<{ assignment_id: string; team_id?: string | null }>(
    `/lms/admin/cohorts/${cohortId}/try-as-observer`,
    payload ?? {},
  ).then((r) => r.data);

export const getObserverTeamsApi = (cohortId: string) =>
  api.get<ObserverTeamSummary[]>(`/lms/admin/cohorts/${cohortId}/observer-teams`).then((r) => r.data);

// ── invite-code course/path/program grants (2026-08-21, program added
// 2026-09-15) ─────────────────────────────────────────────────────────────
// "This code batch gets these courses/paths/program free" — applies
// immediately to everyone who's ever used the code, and to every future
// signup on it. A "program" grant is stored as a cohort_id, not an
// lms_program_id — an LmsProgram is never assigned standalone, only
// resolved from a cohort (which program that cashes out to can change if
// the cohort's own override changes) — see the backend model's own
// docstring.

export interface InviteCodeGrant {
  id: string;
  product_type: "course" | "learning_path" | "lms_program";
  course_id: string | null;
  course_title: string | null;
  learning_path_id: string | null;
  learning_path_title: string | null;
  cohort_id: string | null;
  cohort_name: string | null;
  lms_program_name: string | null;
  created_at: string | null;
}

export const listInviteCodeGrantsApi = (codeId: string) =>
  api.get<InviteCodeGrant[]>(`/lms/admin/invite-codes/${codeId}/grants`).then((r) => r.data);

export const createInviteCodeGrantApi = (
  codeId: string, data: { course_id?: string; learning_path_id?: string; cohort_id?: string },
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

// ── cohort-quiz strengths/weaknesses (2026-09) ──────────────────────────────

export interface CohortQuizTopicBreakdown {
  topic_breakdown: Record<string, { correct: number; total: number }>;
}

export const getStudentQuizBreakdownApi = (userId: string) =>
  api.get<CohortQuizTopicBreakdown>(`/lms/admin/students/${userId}/quiz-breakdown`).then((r) => r.data);

export const getStudentQuizBreakdownInstructorApi = (userId: string) =>
  api.get<CohortQuizTopicBreakdown>(`/lms/instructor/students/${userId}/quiz-breakdown`).then((r) => r.data);

export interface CohortQuizAnalysisQuiz {
  quiz_id: string;
  quiz_title: string;
  total_attempts: number;
  total_score: number;
  total_possible: number;
  average_score_pct: number;
  topic_breakdown: Record<string, { correct: number; total: number }>;
}

export interface CohortQuizQuestionAnalysis {
  question_id: string;
  quiz_id: string;
  quiz_title: string;
  topic: string;
  prompt: string;
  difficulty?: string | null;
  correct_count: number;
  incorrect_count: number;
  total_answers: number;
  accuracy_pct: number | null;
}

export interface CohortQuizAnalysisOut {
  cohort_id: string;
  total_attempts: number;
  overall_average_score_pct: number;
  overall_topic_breakdown: Record<string, { correct: number; total: number }>;
  quizzes: CohortQuizAnalysisQuiz[];
  questions?: CohortQuizQuestionAnalysis[];
}

export const getCohortQuizAnalysisApi = (cohortId: string, mode?: string) =>
  api.get<CohortQuizAnalysisOut>(`/lms/admin/cohorts/${cohortId}/quiz-analysis`, {
    params: mode ? { mode } : {},
  }).then((r) => r.data);

export const listLearningPathsApi = () =>
  api.get<AdminLearningPath[]>("/lms/admin/learning-paths").then((r) => r.data);
export const getLearningPathApi = (id: string) =>
  api.get<AdminLearningPath>(`/lms/admin/learning-paths/${id}`).then((r) => r.data);
export const createLearningPathApi = (data: LearningPathMetadataInput & { title: string }) =>
  api.post<AdminLearningPath>("/lms/admin/learning-paths", data).then((r) => r.data);
export const updateLearningPathApi = (
  id: string,
  data: Partial<LearningPathMetadataInput & { is_published: boolean }>,
) => api.patch<AdminLearningPath>(`/lms/admin/learning-paths/${id}`, data).then((r) => r.data);
export const submitLearningPathForReviewApi = (id: string) =>
  api.post<{ message: string }>(`/lms/admin/learning-paths/${id}/submit-review`).then((r) => r.data);
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

export const uploadQuizImageApi = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post<{ url: string; path: string }>("/lms/admin/quiz-images", form, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then((r) => r.data);
};
