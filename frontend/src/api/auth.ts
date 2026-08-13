import { api, tokens } from "./client";
import type { AuthTokens, User } from "@/types/shared";
import type { TitleBrief, Achievement } from "@/types/ambassadors";

export async function login(email: string, password: string): Promise<User> {
  const { data } = await api.post<AuthTokens & { user: User }>("/auth/login", { email, password });
  tokens.set(data);
  return data.user;
}

export async function signup(data: {
  full_name: string;
  email: string;
  password: string;
  phone?: string;
  date_of_birth?: string;
  invite_code?: string;
  parent_name?: string;
  parent_phone?: string;
  parent_email?: string;
  country?: string;
  city_id?: string;
  city_other?: string;
}): Promise<User> {
  const { data: res } = await api.post<AuthTokens & { user: User }>("/auth/signup", data);
  tokens.set(res);
  return res.user;
}

export async function setPassword(token: string, new_password: string): Promise<void> {
  await api.post("/auth/set-password", { token, new_password });
}

export async function fetchMe(): Promise<User> {
  const { data } = await api.get<User>("/auth/me");
  return data;
}

export async function logout(): Promise<void> {
  try {
    await api.post("/auth/logout");
  } finally {
    tokens.clear();
  }
}

export async function changePassword(new_password: string, current_password?: string): Promise<void> {
  await api.post("/auth/change-password", { new_password, current_password });
}

export async function getUserProfileApi(userId: string): Promise<User> {
  const { data } = await api.get<User>(`/auth/users/${userId}`)
  return data
}

export async function getUserStatsApi(userId: string): Promise<UserStats> {
  const { data } = await api.get<UserStats>(`/auth/users/${userId}/stats`)
  return data
}

export interface UserStats {
  ambassador?: AmbassadorCardStats
  teacher?: TeacherCardStats
  instructor?: InstructorCardStats
}

// These are re-exported so ProfileStatsCards.tsx can use them as prop types
export interface AmbassadorCardStats {
  students_reached: number
  sessions_done: number
  active_teachers: number
  converted_leads: number
  completed_tasks: number
  active_instructors: number
  points_balance: number
  current_title: TitleBrief | null
  next_title: TitleBrief | null
  points_to_next: number
  progress_to_next: number
  achievements: Achievement[]
}

export interface TeacherCardStats {
  stats: { sessions_done: number; students_reached: number; upcoming: number }
  points_balance: number
  current_title: TitleBrief | null
  next_title: TitleBrief | null
  points_to_next: number
  progress_to_next: number
  achievements: Achievement[]
}

export interface InstructorCardStats {
  total_earned_aed: number
  total_hours: number
  total_sessions: number
  pending_signature: number
  completed_videos: number
  total_videos: number
}

export async function updatePhotoApi(photo: File): Promise<User> {
  const form = new FormData()
  form.append("photo", photo)
  const { data } = await api.post<User>("/auth/me/photo", form)
  return data
}

export async function updateMeApi(
  data: Partial<{
    full_name: string
    phone: string
    country: string
    linkedin_url: string
    city_id: string
    city_other: string
    city_of_residence_id: string
    deliver_city_ids: string[]
    has_own_transportation: boolean
  }>,
): Promise<User> {
  const { data: res } = await api.patch<User>("/auth/me", data)
  return res
}

export async function rerollNicknameApi(): Promise<User> {
  const { data } = await api.post<User>("/auth/me/nickname/reroll")
  return data
}

/** `kind` scopes the check to one code pool (2026-08-13) so a student
 * batch code doesn't validate green on the instructor application form. */
export const validateInviteApi = (code: string, kind?: "instructor" | "student") =>
  api.get<{ ambassador_name: string; valid: boolean }>(`/auth/invite/${code}`, {
    params: kind ? { kind } : undefined,
  }).then((r) => r.data)

export async function applyInstructorApi(data: {
  full_name: string
  phone?: string
  email: string
  password: string
  invite_code?: string
  university?: string
  highest_degree?: string
  highest_degree_other?: string
  city_of_residence_id?: string
  deliver_city_ids?: string[]
  background_areas?: string[]
  background_other?: string
  has_own_transportation?: boolean
  country?: string
}, cv?: File | null): Promise<User> {
  // Unlike apply/teacher-apply, this creates an active user immediately
  // (status starts the pipeline, not a pending-admin-approval gate) and
  // auto-logs them in, so it stores tokens the same way login() does.
  // Multipart: fields ride in a `payload` JSON part so the CV can be
  // submitted in the same request.
  const form = new FormData();
  form.append("payload", JSON.stringify(data));
  if (cv) form.append("cv", cv);
  const { data: res } = await api.post<AuthTokens & { user: User }>("/auth/instructor-apply", form);
  tokens.set(res);
  return res.user;
}

