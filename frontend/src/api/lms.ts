/** LMS student API (LM1-8) — thin wrappers over `/lms/*` (LM1-3) and the
 * video token/stream routes (LM1-6). Types mirror `schemas/lms.py` field for
 * field; `content` shapes match LMS_EXECUTION_PLAN.md §2's four kinds.
 */
import { api } from "./client";

export interface CourseCatalogItem {
  id: string;
  title: string;
  description: string | null;
  kind: "course" | "mission";
  image_url: string | null;
  level: "beginner" | "intermediate" | "advanced" | null;
  track: string | null;
  access_mode: "open" | "invite" | "paid"; // P1-7
  enrolled: boolean;
  locked: boolean; // 7B-2 — unmet prerequisites; independent of access_mode
}

/** 7B-2 — a unified course/mission prerequisite edge, evaluated for the
 * caller. `item_type: "mission"` has no course-side page to link to, so
 * it's rendered as plain text here (mirrors how a course prerequisite on a
 * mission's own page has no mission-side page to link to either). */
export interface CoursePrerequisite {
  item_type: "course" | "mission";
  item_id: string;
  title: string;
  satisfied: boolean;
}

export interface ModuleLock {
  module_id: string;
  title: string | null;
  position: number;
  locked: boolean;
  mandatory_total: number;
  mandatory_completed: number;
  total_items?: number;
}

export interface CourseDetail {
  id: string;
  title: string;
  description: string | null;
  kind: "course" | "mission";
  enrolled: boolean;
  completed: boolean;
  modules: ModuleLock[];
  image_url: string | null;
  outcomes: string[];
  level: "beginner" | "intermediate" | "advanced" | null;
  track: string | null;
  instructor_name: string | null;
  instructor_title: string | null;
  instructor_photo_url: string | null;
  access_mode: "open" | "invite" | "paid"; // P1-7
  locked: boolean; // 7B-2 — unmet prerequisites; independent of access_mode
  prerequisites: CoursePrerequisite[];
  // Stage S (Stripe Checkout) — integer minor units, matching Stripe's
  // unit_amount. Null unless access_mode === "paid".
  price_cents: number | null;
  currency: string;
}

export interface QuizOption {
  text: string;
}

export interface QuizQuestion {
  prompt: string;
  options: QuizOption[];
}

export type ModuleItemContent =
  | { body: string } // text
  | { pass_threshold: number; questions: QuizQuestion[] } // quiz
  | { title: string | null; cards: { term: string; definition: string }[] } // flashcards
  | { transcode_status: string | null; duration_seconds: number | null; video_id: string | null } // video
  | { filename: string | null; size_bytes: number | null } // attachment
  | {
      // mission (P5-5) — mission_title/mission_kind/points/attempt_status
      // are enriched by the backend per request, not authored content.
      mission_id: string;
      variant_id: string | null;
      mission_title: string | null;
      mission_kind: string | null;
      points: number | null;
      attempt_status: "in_progress" | "submitted" | "passed" | "failed" | "abandoned" | null;
    };

export interface ModuleItem {
  id: string;
  kind: "video" | "text" | "quiz" | "flashcards" | "attachment" | "mission";
  title: string | null;
  position: number;
  content: ModuleItemContent;
  status: "not_started" | "in_progress" | "completed" | "skipped" | null;
}

export interface ModuleDetail {
  id: string;
  course_id: string;
  title: string;
  position: number;
  items: ModuleItem[];
}

export interface QuizReviewQuestion {
  prompt: string | null;
  selected: number;
  correct: boolean;
  explanation: string | null;
  correct_text: string | null;
}

export interface QuizReview {
  score: number;
  passed: boolean;
  pass_threshold: number;
  attempts: number;
  best_score: number | null;
  questions: QuizReviewQuestion[];
}

export interface QuizAnswerCheck {
  correct: boolean;
  explanation: string | null;
  correct_text: string | null;
}

export interface ProgressResult {
  status: string;
  quiz_attempts: number;
  best_score: number | null;
  completed_at: string | null;
}

// ── video checkpoints (timeline notes + mid-video quizzes, 2026-08-07) ─────

export type CheckpointQuestionType = "mcq" | "multiselect" | "open";

export type CheckpointContent =
  | { body: string } // note
  | { question_type: CheckpointQuestionType; prompt: string; options: QuizOption[] | null }; // quiz

export interface VideoCheckpoint {
  id: string;
  start_seconds: number;
  end_seconds: number | null;
  kind: "note" | "quiz";
  content: CheckpointContent;
}

export interface CheckpointAnswerResult {
  correct: boolean | null;
  explanation: string | null;
}

// ── dashboard (LMS redesign, 2026-08-06) ────────────────────────────────────

export interface DashboardStats {
  in_progress: number;
  total_enrolled: number;
  modules_done: number;
}

export interface ResumePointer {
  course_id: string;
  course_title: string;
  module_id: string;
  module_title: string;
  next_item_id: string | null;
  mandatory_completed: number;
  mandatory_total: number;
}

export interface DashboardCourse {
  course_id: string;
  title: string;
  kind: "course" | "mission";
  status: "not_started" | "in_progress" | "completed";
  modules_done: number;
  modules_total: number;
  pct: number;
}

export interface MyCourses {
  stats: DashboardStats;
  resume: ResumePointer | null;
  courses: DashboardCourse[];
}

export async function fetchMyCourses(): Promise<MyCourses> {
  const { data } = await api.get<MyCourses>("/lms/my-courses");
  return data;
}

export interface ActivityItem {
  item_id: string;
  item_title: string | null;
  item_kind: "video" | "text" | "quiz" | "flashcards";
  course_id: string;
  course_title: string;
  completed_at: string | null;
}

export async function fetchMyActivity(): Promise<ActivityItem[]> {
  const { data } = await api.get<ActivityItem[]>("/lms/my-activity");
  return data;
}

// ── learning paths (self-paced ordered course sequences, 2026-08-08) ───────

export interface LearningPathCatalogItem {
  id: string;
  title: string;
  description: string | null;
  image_url: string | null;
  course_count: number;
  mission_count: number;
  total_duration_seconds: number;
  pct: number;
  /** True iff you have an active enrollment in at least one of the path's
   * courses — `pct` can't answer this (a just-started path is still 0%). */
  enrolled: boolean;
  access_mode: "open" | "invite" | "paid"; // mirrors CourseCatalogItem.access_mode
  // Bundle pricing (2026-08-21) — null price_cents means not purchasable.
  price_cents: number | null;
  currency: string;
  /** True iff you already have an active enrollment in every step's course —
   * a bundle purchase would have nothing left to grant. */
  fully_owned: boolean;
}

export interface LearningPathStep {
  position: number;
  course_id: string;
  title: string;
  kind: "course" | "mission";
  state: "done" | "current" | "mission" | "locked";
  pct: number;
  modules_done: number;
  modules_total: number;
}

export interface LearningPathDetail {
  id: string;
  title: string;
  description: string | null;
  image_url: string | null;
  pct: number;
  course_count: number;
  mission_count: number;
  total_duration_seconds: number;
  steps: LearningPathStep[];
  access_mode: "open" | "invite" | "paid";
  /** True iff you already hold an active enrollment in at least one step
   * course — lets the client tell a genuine self-enrol ("Start path") from
   * an already-granted invite/paid path ("Continue"), which should navigate
   * straight to the next step instead of re-POSTing to `/start`. */
  enrolled: boolean;
  price_cents: number | null;
  currency: string;
  fully_owned: boolean;
}

// ── completion certificates (2026-08-13) ──────────────────────────────────

export interface MyCertificate {
  id: string;
  type: "lms_course_completion" | "lms_path_completion";
  /** The course or learning path it was earned for. */
  title: string;
  course_id: string | null;
  learning_path_id: string | null;
  issued_at: string | null;
  /** Signed at query time — don't cache this beyond the request. */
  url: string | null;
}

export async function fetchMyCertificates(): Promise<MyCertificate[]> {
  const { data } = await api.get<MyCertificate[]>("/lms/my-certificates");
  return data;
}

export async function fetchLearningPaths(): Promise<LearningPathCatalogItem[]> {
  const { data } = await api.get<LearningPathCatalogItem[]>("/lms/learning-paths");
  return data;
}

export async function fetchLearningPath(pathId: string): Promise<LearningPathDetail> {
  const { data } = await api.get<LearningPathDetail>(`/lms/learning-paths/${pathId}`);
  return data;
}

export async function startLearningPath(pathId: string): Promise<LearningPathDetail> {
  const { data } = await api.post<LearningPathDetail>(`/lms/learning-paths/${pathId}/start`);
  return data;
}

// ── upcoming public programs (reuses /public/catalog — no LMS-specific
// backend needed). Includes both `planned` (not yet open — "Notify me") and
// `registration_open` ("Register now") public cohorts as of 2026-08-07. ───

export interface UpcomingProgramSession {
  meeting_date: string;
  starts_at: string | null;
  title: string | null;
}

export interface UpcomingProgram {
  cohort_id: string;
  program_name: string;
  program_type: string;
  description: string | null;
  starts_on: string | null;
  ends_on: string | null;
  location: string | null;
  location_name: string | null;
  location_address: string | null;
  location_maps_url: string | null;
  price_display: string;
  capacity: number | null;
  spots_left: number | null;
  is_limited: boolean;
  registration_endpoint: string;
  status: "planned" | "registration_open";
  interest_endpoint: string;
  sessions: UpcomingProgramSession[];
  instructors: string[];
  curriculum_titles: string[];
}

export async function fetchUpcomingPrograms(): Promise<UpcomingProgram[]> {
  const { data } = await api.get<UpcomingProgram[]>("/public/catalog");
  return data;
}

// ── cities (2026-08-08) — no-auth read for pre-account forms (apply,
// signup) that can't call the authenticated /inventory/cities. ───────────
export interface PublicCity {
  id: string;
  name: string;
  country: string;
  is_active: boolean;
  created_at: string | null;
}

export async function fetchPublicCities(): Promise<PublicCity[]> {
  const { data } = await api.get<PublicCity[]>("/public/cities");
  return data;
}

export interface PublicLeadInput {
  student_name: string;
  email: string;
  phone: string;
}

// Full registration — mirrors PublicRegistrationRequest field-for-field
// (backend/app/schemas/sessions/public_registration.py). Only student_name/
// email/phone are required; everything else is optional, matching the
// backend schema exactly.
export interface ProgramRegistrationInput {
  student_name: string;
  email: string;
  phone: string;
  city?: string;
  date_of_birth?: string; // YYYY-MM-DD
  grade?: string;
  organization_name?: string;
  parent_name?: string;
  parent_phone?: string;
  parent_email?: string;
}

export async function submitProgramRegistration(endpoint: string, body: ProgramRegistrationInput): Promise<{ message: string }> {
  const { data } = await api.post<{ message: string }>(endpoint, body);
  return data;
}

export async function submitProgramInterest(endpoint: string, body: PublicLeadInput): Promise<{ message: string }> {
  const { data } = await api.post<{ message: string }>(endpoint, body);
  return data;
}

export async function fetchCatalog(q?: string): Promise<CourseCatalogItem[]> {
  const { data } = await api.get<CourseCatalogItem[]>("/lms/catalog", { params: q ? { q } : undefined });
  return data;
}

export async function fetchCourse(courseId: string): Promise<CourseDetail> {
  const { data } = await api.get<CourseDetail>(`/lms/courses/${courseId}`);
  return data;
}

export async function enrollInCourse(courseId: string): Promise<void> {
  await api.post("/lms/enroll", { course_id: courseId });
}

// Stage S (Stripe Checkout, August Build Brief Branch 4).

export async function startCourseCheckout(courseId: string): Promise<{ checkout_url: string }> {
  const { data } = await api.post<{ checkout_url: string }>(`/lms/courses/${courseId}/checkout`, {});
  return data;
}

// Learning path bundle pricing (2026-08-21).
export async function startPathCheckout(pathId: string): Promise<{ checkout_url: string }> {
  const { data } = await api.post<{ checkout_url: string }>(`/lms/learning-paths/${pathId}/checkout`, {});
  return data;
}

export interface CheckoutFulfillResult {
  status: "pending" | "paid" | "refunded" | "disputed" | "failed";
  course_id: string | null;
  learning_path_id: string | null;
}

export async function fulfillCheckoutSession(sessionId: string): Promise<CheckoutFulfillResult> {
  const { data } = await api.post<CheckoutFulfillResult>(`/lms/checkout/session/${sessionId}/fulfill`, {});
  return data;
}

export async function fetchModule(moduleId: string): Promise<ModuleDetail> {
  const { data } = await api.get<ModuleDetail>(`/lms/modules/${moduleId}`);
  return data;
}

export async function fetchQuizQuestions(itemId: string): Promise<{ pass_threshold: number; questions: QuizQuestion[] }> {
  const { data } = await api.get<{ pass_threshold: number; questions: QuizQuestion[] }>(`/lms/items/${itemId}/quiz/questions`);
  return data;
}

export async function submitQuiz(itemId: string, answers: number[]): Promise<QuizReview> {
  const { data } = await api.post<QuizReview>(`/lms/items/${itemId}/quiz/submit`, { answers });
  return data;
}

export async function checkQuizAnswer(itemId: string, questionIndex: number, answer: number): Promise<QuizAnswerCheck> {
  const { data } = await api.post<QuizAnswerCheck>(`/lms/items/${itemId}/quiz/check`, { question_index: questionIndex, answer });
  return data;
}

export interface AttachmentUrl {
  url: string;
  filename: string | null;
}

export async function getAttachmentUrl(itemId: string): Promise<AttachmentUrl> {
  const { data } = await api.get<AttachmentUrl>(`/lms/items/${itemId}/attachment/url`);
  return data;
}

export type ProgressAction = "video-watched" | "text-viewed" | "quiz-attempt" | "flashcards-skipped" | "attachment-viewed";

export async function recordProgress(itemId: string, action: ProgressAction): Promise<ProgressResult> {
  const { data } = await api.post<ProgressResult>(`/lms/items/${itemId}/progress`, { action });
  return data;
}

// Token issuance and streaming go through the generic /videos/{video_id}/...
// surface (routers/video.py) — keyed by the Video row's own id, not the
// module item's id, since the same routes now serve every video-hosting
// feature (LMS module video, checklist guidelines, library, training), each
// with its own access check. The module item's `video_id` (in its `content`,
// see ContentVideo) is what supplies that id here.
export async function fetchVideoToken(videoId: string): Promise<{ token: string; expires_in_seconds: number }> {
  const { data } = await api.get<{ token: string; expires_in_seconds: number }>(
    `/videos/${videoId}/token`,
  );
  return data;
}

/** Absolute URL to the token-gated HLS playlist — hls.js loads this directly
 * (not through the `api` axios instance, which is for JSON calls). */
export function videoPlaylistUrl(videoId: string, token: string): string {
  const base = api.defaults.baseURL ?? "";
  return `${base}/videos/${videoId}/playlist?token=${encodeURIComponent(token)}`;
}

// Leaderboard (P2-4, linked into the frontend in Live Games Phase 2C 8-2 —
// display_name is the student's nickname, never a real name).
export interface LeaderboardEntry {
  rank: number;
  user_id: string;
  display_name: string;
  points: number;
}

export const getLeaderboardApi = (scope: "cohort" | "global", cohortId?: string) =>
  api.get<LeaderboardEntry[]>("/lms/leaderboard", { params: { scope, cohort_id: cohortId } })
    .then((r) => r.data);

export async function fetchCheckpoints(videoItemId: string): Promise<VideoCheckpoint[]> {
  const { data } = await api.get<VideoCheckpoint[]>(`/lms/items/${videoItemId}/checkpoints`);
  return data;
}

export async function submitCheckpointAnswer(
  videoItemId: string,
  checkpointId: string,
  answer: number | number[] | string,
): Promise<CheckpointAnswerResult> {
  const { data } = await api.post<CheckpointAnswerResult>(
    `/lms/items/${videoItemId}/checkpoints/${checkpointId}/answer`, { answer },
  );
  return data;
}

// ── LMS Program checklist (2026-08-21 redesign) ─────────────────────────────
// Distinct from the older /lms/my-programs (courses-only cohort view, still
// live — LearnMyCourses/etc.) and from LearnProgram.tsx's /learn/programs/
// $cohortId (the *public catalog's* program detail/registration page, an
// unrelated concept that happens to share the word "program") — this is the
// new checklist entity, `lms_program_assignments`. Mounted at
// /learn/checklists to keep well clear of that existing route.

export type LmsProgramItemType =
  | "course" | "mission_run" | "external_link" | "submission" | "pdf" | "manual" | "session" | "quiz" | "team_setup";
export type LmsProgramItemStatus = "pending" | "done" | "awaiting_confirmation";

export type LmsProgramItemScope = "individual" | "team";

/** One entry in a multi-field submission (2026-09-14) — see
 * LmsProgramChecklistItem.submission_multi_link. Exactly one of url/text is
 * ever populated, matching this entry's label's own field_type
 * (2026-09-16) — never both. */
export interface SubmissionLink {
  label: string | null;
  url: string | null;
  text: string | null;
}

/** One entry in ops's own fixed field set for a `submission_multi_link`
 * item (2026-09-14, text fields added 2026-09-16) — see
 * LmsProgramChecklistItem.submission_link_labels. field_type picks whether
 * this slot renders as a link input or a text area. */
export interface SubmissionLinkLabel {
  label: string;
  required: boolean;
  field_type: "text" | "link";
}

export interface LmsProgramChecklistItem {
  id: string;
  position: number;
  item_type: LmsProgramItemType;
  title: string;
  description: string | null;
  optional: boolean;
  requires_confirmation: boolean;
  status: LmsProgramItemStatus;
  course_id: string | null;
  mission_attempt_id: string | null;
  mission_id: string | null;
  mission_kind: string | null;
  external_url: string | null;
  submission_prompt: string | null;
  /** True once a `pdf` item has a file uploaded — fetch the actual URL
   * on demand via `getChecklistItemPdfUrlApi`, never baked in here. */
  has_pdf: boolean;
  submitted_url: string | null;
  /** The plain (non-multi) submission's own type — link (default) or text.
   * Only meaningful when submission_multi_link is false. */
  submission_field_type: "text" | "link";
  submitted_text: string | null;
  /** Ops's per-item toggle (2026-09-14) — when true this item takes
   * several labeled links instead of one; `submitted_links` carries the
   * real answer (`submitted_url` still mirrors the first link). */
  submission_multi_link: boolean;
  submitted_links: SubmissionLink[] | null;
  /** Ops's own fixed label set (2026-09-14), in the order ops entered them
   * — null when this item is either not multi-link or is an older
   * multi-link item authored before this existed (that one still takes
   * free-text, student-entered labels, none required). */
  submission_link_labels: SubmissionLinkLabel[] | null;
  /** submission-only cutoff — can no longer submit/replace past this;
   * already-submitted content and its confirmation are unaffected. */
  deadline_at: string | null;
  /** session-only fields — always self-contained, never a live link to a
   * real Sessions-domain row. */
  session_date: string | null;
  session_starts_at: string | null;
  session_location: string | null;
  session_meeting_url: string | null;
  // Competition domain (2026-08-24) — "individual" (the default, every
  // item before this existed) means the fields above are this student's
  // own. "team" means they're the whole team's shared fact: any member
  // wrote them, and updated_by_name/updated_at say who last did, since
  // there's no single "you" for a team row.
  scope: LmsProgramItemScope;
  updated_by_name: string | null;
  updated_at: string | null;
  // ── Roadmap board (2026-09) ────────────────────────────────────────────
  /** Which single Madar design phase a `mission_run` tile targets — null
   * means the whole mission. One of MISSION_STEP_KEYS (lib/roadmap.ts). */
  mission_step_key: string | null;
  gated: boolean;
  guideline_kind: "pdf" | "link" | "video" | null;
  guideline_url: string | null;
  /** True once a `video`-kind guideline has a real file uploaded through
   * the standardized video service — fetch the actual playback URL on
   * demand via `getChecklistItemGuidelineVideoUrlApi`, same
   * never-baked-in-here posture as `has_pdf`. `guideline_url` stays the
   * pasted embed link when this is false. */
  guideline_video_uploaded: boolean;
  /** Groups tiles into the board's row sections ("Checkpoint 1 — Learn &
   * plan"). Free text, matched by exact string. */
  checkpoint_label: string | null;
  poster_template_url?: string | null;
  /** Derived server-side (compute_lock_states) — true iff `gated` and some
   * earlier non-optional item on this checklist isn't `done` yet. */
  locked: boolean;
}

export interface LmsProgramAssignmentSummary {
  assignment_id: string;
  lms_program_id: string;
  name: string;
  cohort_id: string | null;
  cohort_name: string | null;
  items_total: number;
  items_done: number;
  pct: number;
  next_item_title: string | null;
  certificate_required: boolean;
  certificate_earned: boolean;
}

export interface LmsProgramChecklist {
  assignment_id: string;
  lms_program_id: string;
  name: string;
  description: string | null;
  image_url: string | null;
  poster_template_url?: string | null;
  cohort_id: string | null;
  cohort_name: string | null;
  team_name: string | null;
  // null means still editable — set once any teammate has hit "Final
  // Submit". Only ops can clear it again.
  team_final_locked_at: string | null;
  team_final_locked_by_name?: string | null;
  certificate_required: boolean;
  certificate_earned: boolean;
  items: LmsProgramChecklistItem[];
}

export async function fetchMyChecklists(): Promise<LmsProgramAssignmentSummary[]> {
  const { data } = await api.get<LmsProgramAssignmentSummary[]>("/lms/programs");
  return data;
}

export async function fetchChecklist(assignmentId: string): Promise<LmsProgramChecklist> {
  const { data } = await api.get<LmsProgramChecklist>(`/lms/programs/${assignmentId}`);
  return data;
}

export async function completeChecklistItem(assignmentId: string, itemId: string): Promise<LmsProgramChecklistItem> {
  const { data } = await api.post<LmsProgramChecklistItem>(`/lms/programs/${assignmentId}/items/${itemId}/complete`, {});
  return data;
}

export async function submitChecklistItem(assignmentId: string, itemId: string, url: string): Promise<LmsProgramChecklistItem> {
  const { data } = await api.post<LmsProgramChecklistItem>(`/lms/programs/${assignmentId}/items/${itemId}/submit`, { url });
  return data;
}

/** A plain (non-multi) item whose submission_field_type is "text" (2026-09-16)
 * takes this instead of submitChecklistItem's `url`. */
export async function submitChecklistItemText(assignmentId: string, itemId: string, text: string): Promise<LmsProgramChecklistItem> {
  const { data } = await api.post<LmsProgramChecklistItem>(`/lms/programs/${assignmentId}/items/${itemId}/submit`, { text });
  return data;
}

/** `submission_multi_link` item's paste-back — several labeled links in
 * one submission instead of one bare url. */
export async function submitChecklistItemLinks(
  assignmentId: string, itemId: string, links: SubmissionLink[],
): Promise<LmsProgramChecklistItem> {
  const { data } = await api.post<LmsProgramChecklistItem>(`/lms/programs/${assignmentId}/items/${itemId}/submit`, { links });
  return data;
}

/** A `team_setup` item's one action — see routers/lms/student.py's
 * set_team_name. Any teammate can call this as many times as they want
 * until the item's deadline — last write wins. Writes straight to the
 * team's real name, so the checklist's own top-level `team_name` (and
 * every other view that reads it) reflects it immediately. */
export async function setTeamNameChecklistItem(assignmentId: string, itemId: string, name: string): Promise<LmsProgramChecklistItem> {
  const { data } = await api.post<LmsProgramChecklistItem>(`/lms/programs/${assignmentId}/items/${itemId}/team-name`, { name });
  return data;
}

/** The FINAL GATE card's one action — see routers/lms/student.py's
 * final_submit_program. Any teammate can call this once every required
 * team-scoped item is done; one-way from the team's side, only ops can
 * undo it. Returns the refreshed checklist (team_final_locked_at now set). */
export async function finalSubmitChecklist(assignmentId: string): Promise<LmsProgramChecklist> {
  const { data } = await api.post<LmsProgramChecklist>(`/lms/programs/${assignmentId}/final-submit`, {});
  return data;
}

export async function getChecklistItemPdfUrlApi(assignmentId: string, itemId: string): Promise<string> {
  const { data } = await api.get<{ url: string }>(`/lms/programs/${assignmentId}/items/${itemId}/pdf-url`);
  return data.url;
}

export async function getChecklistItemGuidelineVideoUrlApi(
  assignmentId: string, itemId: string,
): Promise<{ url: string; video_info: import("@/components/video/VideoPlayer").VideoPlaybackInfo | null }> {
  const { data } = await api.get(`/lms/programs/${assignmentId}/items/${itemId}/guideline-video-url`);
  return data;
}
