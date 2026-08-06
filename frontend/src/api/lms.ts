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
}

export interface ModuleLock {
  module_id: string;
  title: string | null;
  position: number;
  locked: boolean;
  mandatory_total: number;
  mandatory_completed: number;
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
  | { transcode_status: string | null; duration_seconds: number | null }; // video

export interface ModuleItem {
  id: string;
  kind: "video" | "text" | "quiz" | "flashcards";
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
}

export interface QuizReview {
  score: number;
  passed: boolean;
  pass_threshold: number;
  attempts: number;
  best_score: number | null;
  questions: QuizReviewQuestion[];
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

// ── upcoming public programs (reuses /public/catalog — no LMS-specific
// backend needed; "public" + "registration_open" is exactly "public and
// upcoming") ─────────────────────────────────────────────────────────────

export interface UpcomingProgram {
  cohort_id: string;
  program_name: string;
  program_type: string;
  description: string | null;
  starts_on: string | null;
  ends_on: string | null;
  location: string | null;
  price_display: string;
  spots_left: number | null;
  is_limited: boolean;
  registration_endpoint: string;
}

export async function fetchUpcomingPrograms(): Promise<UpcomingProgram[]> {
  const { data } = await api.get<UpcomingProgram[]>("/public/catalog");
  return data;
}

export async function fetchCatalog(): Promise<CourseCatalogItem[]> {
  const { data } = await api.get<CourseCatalogItem[]>("/lms/catalog");
  return data;
}

export async function fetchCourse(courseId: string): Promise<CourseDetail> {
  const { data } = await api.get<CourseDetail>(`/lms/courses/${courseId}`);
  return data;
}

export async function enrollInCourse(courseId: string): Promise<void> {
  await api.post("/lms/enroll", { course_id: courseId });
}

export async function fetchModule(moduleId: string): Promise<ModuleDetail> {
  const { data } = await api.get<ModuleDetail>(`/lms/modules/${moduleId}`);
  return data;
}

export async function submitQuiz(itemId: string, answers: number[]): Promise<QuizReview> {
  const { data } = await api.post<QuizReview>(`/lms/items/${itemId}/quiz/submit`, { answers });
  return data;
}

export type ProgressAction = "video-watched" | "text-viewed" | "quiz-attempt" | "flashcards-skipped";

export async function recordProgress(itemId: string, action: ProgressAction): Promise<ProgressResult> {
  const { data } = await api.post<ProgressResult>(`/lms/items/${itemId}/progress`, { action });
  return data;
}

export async function fetchVideoToken(itemId: string): Promise<{ token: string; expires_in_seconds: number }> {
  const { data } = await api.get<{ token: string; expires_in_seconds: number }>(
    `/lms/items/${itemId}/video/token`,
  );
  return data;
}

/** Absolute URL to the token-gated HLS playlist — hls.js loads this directly
 * (not through the `api` axios instance, which is for JSON calls). */
export function videoPlaylistUrl(itemId: string, token: string): string {
  const base = api.defaults.baseURL ?? "";
  return `${base}/lms/videos/${itemId}/playlist?token=${encodeURIComponent(token)}`;
}

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
