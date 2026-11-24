import { api } from "./client";

export interface BookLesson {
  spread: string;
  title_en: string;
  title_ar: string | null;
  game_keys: string[];
}

export interface BookChapter {
  key: string;
  code: string | null;
  part: string | null;
  title_en: string;
  title_ar: string | null;
  lessons: BookLesson[];
}

export interface BookProfile {
  key: string;
  label_en: string;
  label_ar: string | null;
  subtitle_en: string | null;
  subtitle_ar: string | null;
  default_lang: string | null;
  groups: string[];
}

export interface BookProgress {
  current_spread: string | null;
  current_chapter: string | null;
  active_profile: string | null;
  visited_spreads: string[];
  stars: Record<string, number>;
  stars_earned: number;
  stars_possible: number;
  completion_pct: number;
  last_read_at: string | null;
}

export interface BookCatalogItem {
  id: string;
  slug: string;
  title: string;
  title_ar: string | null;
  subtitle: string | null;
  author_name: string | null;
  cover_url: string | null;
  cover_page_url?: string | null;
  languages: string[];
  access_mode: "open" | "invite" | "paid";
  price_cents: number | null;
  currency: string;
  enrolled: boolean;
  is_preview: boolean;
  completion_pct: number;
  stars_earned: number;
  stars_possible: number;
  chapter_count: number;
}

export interface BookDetail extends BookCatalogItem {
  description: string | null;
  access_days: number | null;
  bundle_version: number;
  is_published: boolean;
  default_profile: string;
  outline: BookChapter[];
  profiles: BookProfile[];
  progress: BookProgress | null;
}

export interface BookReaderSession {
  book_id: string;
  title: string;
  title_ar: string | null;
  bundle_version: number;
  token: string;
  bundle_url: string;
  can_teacher: boolean;
  default_profile: string;
  languages: string[];
  outline: BookChapter[];
  profiles: BookProfile[];
  progress: BookProgress | null;
}

export interface BookProgressSyncPayload {
  current_spread?: string | null;
  current_chapter?: string | null;
  active_profile?: string | null;
  visited_spreads?: string[];
  stars?: Record<string, number>;
  stars_earned?: number;
  stars_possible?: number;
  completion_pct?: number;
  raw_state?: Record<string, unknown>;
}

export interface BookExercisePayload {
  chapter_key?: string | null;
  exercise_key: string;
  exercise_type: "game" | "quiz" | "your_turn" | "notebook" | "lab";
  prompt_text?: string | null;
  answer_json: Record<string, unknown>;
  is_correct?: boolean | null;
  score_stars?: number | null;
  max_stars?: number | null;
}

export interface AdminBook {
  id: string;
  slug: string;
  title: string;
  title_ar: string | null;
  subtitle: string | null;
  description: string | null;
  author_name: string | null;
  cover_url: string | null;
  cover_page_url?: string | null;
  languages: string[];
  bundle_version: number;
  bundle_entry: string;
  bundle_storage_backend: string | null;
  bundle_size_bytes: number | null;
  outline: BookChapter[];
  profiles: BookProfile[];
  default_profile: string;
  access_mode: "open" | "invite" | "paid";
  access_days: number | null;
  price_cents: number | null;
  currency: string;
  is_published: boolean;
  enrollments_count: number;
  active_readers_count: number;
  avg_completion_pct: number;
  created_at: string;
  updated_at: string;
}

export interface AdminBookCreatePayload {
  title: string;
  title_ar?: string | null;
  slug?: string | null;
  subtitle?: string | null;
  description?: string | null;
  author_name?: string | null;
  languages?: string[];
  access_mode?: "open" | "invite" | "paid";
  access_days?: number | null;
  price_cents?: number | null;
  currency?: string;
  default_profile?: string;
}

export interface AdminBookUpdatePayload extends Partial<AdminBookCreatePayload> {
  outline?: BookChapter[];
  profiles?: BookProfile[];
}

export interface AdminBookBundleUploadResult {
  book_id: string;
  bundle_version: number;
  bundle_entry: string;
  bundle_storage_backend: string;
  bundle_size_bytes: number;
  files_uploaded: number;
  chapters_detected: number;
  profiles_detected: number;
}

export interface BookEnrollmentRow {
  id: string;
  user_id: string;
  full_name: string;
  email: string;
  source: string;
  status: string;
  expires_at: string | null;
  completion_pct: number;
  stars_earned: number;
  last_read_at: string | null;
  created_at: string;
}

export interface BookAnalytics {
  book_id: string;
  total_enrolled: number;
  active_readers: number;
  avg_completion_pct: number;
  total_responses: number;
  exercise_accuracy_pct: number | null;
  learners: {
    user_id: string;
    full_name: string;
    email: string;
    completion_pct: number;
    stars_earned: number;
    stars_possible: number;
    current_chapter: string | null;
    exercises_answered: number;
    exercises_correct: number;
    notebook_count: number;
    last_read_at: string | null;
  }[];
  exercises: {
    exercise_key: string;
    chapter_key: string | null;
    exercise_type: string;
    prompt_text: string | null;
    responses_count: number;
    correct_count: number;
    accuracy_pct: number | null;
    avg_stars: number | null;
    total_attempts: number;
  }[];
  notebooks: {
    user_id: string;
    student_name: string;
    student_email: string;
    chapter_key: string | null;
    exercise_key: string;
    prompt_text: string | null;
    answer_text: string;
    updated_at: string;
  }[];
}

// ── Student & Public APIs ────────────────────────────────────────────────────

export async function fetchPublicBooks(q?: string): Promise<BookCatalogItem[]> {
  const { data } = await api.get<BookCatalogItem[]>("/lms/books/public", { params: q ? { q } : undefined });
  return data;
}

export async function fetchPublicBookDetail(bookId: string): Promise<BookDetail> {
  const { data } = await api.get<BookDetail>(`/lms/books/public/${bookId}`);
  return data;
}

export async function fetchBooks(q?: string): Promise<BookCatalogItem[]> {
  const { data } = await api.get<BookCatalogItem[]>("/lms/books", { params: q ? { q } : undefined });
  return data;
}

export async function fetchBookDetail(bookId: string): Promise<BookDetail> {
  const { data } = await api.get<BookDetail>(`/lms/books/${bookId}`);
  return data;
}

export async function enrollInBook(bookId: string): Promise<{ enrolled: boolean }> {
  const { data } = await api.post<{ enrolled: boolean }>(`/lms/books/${bookId}/enroll`, {});
  return data;
}

export async function startBookCheckout(bookId: string): Promise<{ checkout_url: string }> {
  const { data } = await api.post<{ checkout_url: string }>(`/lms/books/${bookId}/checkout`, {});
  return data;
}

export async function createBookReaderSession(
  bookId: string,
  params?: { profile?: string; chapter?: string; spread?: string; theme?: "light" | "dark"; lang?: "en" | "ar" },
): Promise<BookReaderSession> {
  const { data } = await api.post<BookReaderSession>(`/lms/books/${bookId}/reader-session`, {}, { params });
  return data;
}

export async function syncBookProgress(bookId: string, payload: BookProgressSyncPayload): Promise<BookProgress> {
  const { data } = await api.put<BookProgress>(`/lms/books/${bookId}/progress`, payload);
  return data;
}

export async function submitBookExercise(bookId: string, payload: BookExercisePayload): Promise<void> {
  await api.post(`/lms/books/${bookId}/exercises`, payload);
}

// ── Admin / Ops Authoring APIs ───────────────────────────────────────────────

export async function adminListBooksApi(): Promise<AdminBook[]> {
  const { data } = await api.get<AdminBook[]>("/lms/admin/books");
  return data;
}

export async function adminCreateBookApi(payload: AdminBookCreatePayload): Promise<AdminBook> {
  const { data } = await api.post<AdminBook>("/lms/admin/books", payload);
  return data;
}

export async function adminGetBookApi(bookId: string): Promise<AdminBook> {
  const { data } = await api.get<AdminBook>(`/lms/admin/books/${bookId}`);
  return data;
}

export async function adminUpdateBookApi(bookId: string, payload: AdminBookUpdatePayload): Promise<AdminBook> {
  const { data } = await api.patch<AdminBook>(`/lms/admin/books/${bookId}`, payload);
  return data;
}

export async function adminPublishBookApi(bookId: string): Promise<AdminBook> {
  const { data } = await api.post<AdminBook>(`/lms/admin/books/${bookId}/publish`, {});
  return data;
}

export async function adminUnpublishBookApi(bookId: string): Promise<AdminBook> {
  const { data } = await api.post<AdminBook>(`/lms/admin/books/${bookId}/unpublish`, {});
  return data;
}

export async function adminDeleteBookApi(bookId: string): Promise<void> {
  await api.delete(`/lms/admin/books/${bookId}`);
}

export async function adminUploadBookCoverApi(bookId: string, file: File): Promise<AdminBook> {
  const fd = new FormData();
  fd.append("file", file);
  const { data } = await api.post<AdminBook>(`/lms/admin/books/${bookId}/cover`, fd);
  return data;
}

export async function adminUploadBookBundleApi(bookId: string, file: File): Promise<AdminBookBundleUploadResult> {
  const fd = new FormData();
  fd.append("file", file);
  const { data } = await api.post<AdminBookBundleUploadResult>(`/lms/admin/books/${bookId}/bundle`, fd);
  return data;
}

export async function adminListBookEnrollmentsApi(bookId: string): Promise<BookEnrollmentRow[]> {
  const { data } = await api.get<BookEnrollmentRow[]>(`/lms/admin/books/${bookId}/enrollments`);
  return data;
}

export async function adminGrantBookEnrollmentApi(bookId: string, payload: { email?: string; user_id?: string }): Promise<BookEnrollmentRow> {
  const { data } = await api.post<BookEnrollmentRow>(`/lms/admin/books/${bookId}/enrollments`, payload);
  return data;
}

export async function adminBulkGrantBookEnrollmentApi(
  bookId: string,
  role: string,
): Promise<{ granted: number; already_enrolled: number }> {
  const { data } = await api.post<{ granted: number; already_enrolled: number }>(
    `/lms/admin/books/${bookId}/enrollments/bulk`,
    { role },
  );
  return data;
}

export async function adminRevokeBookEnrollmentApi(bookId: string, userId: string): Promise<void> {
  await api.delete(`/lms/admin/books/${bookId}/enrollments/${userId}`);
}

export async function adminGetBookAnalyticsApi(bookId: string, cohortId?: string): Promise<BookAnalytics> {
  const { data } = await api.get<BookAnalytics>(`/lms/admin/books/${bookId}/analytics`, {
    params: cohortId ? { cohort_id: cohortId } : undefined,
  });
  return data;
}

export async function adminExportBookCsvApi(bookId: string, cohortId?: string): Promise<Blob> {
  const { data } = await api.get<Blob>(`/lms/admin/books/${bookId}/analytics/export.csv`, {
    params: cohortId ? { cohort_id: cohortId } : undefined,
    responseType: "blob",
  });
  return data;
}
