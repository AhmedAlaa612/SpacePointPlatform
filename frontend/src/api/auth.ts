import { api, tokens } from "./client";
import type { AuthTokens, User } from "@/types/shared";
import type { TitleBrief, Achievement } from "@/types/ambassadors";

export async function login(email: string, password: string): Promise<User> {
  const { data } = await api.post<AuthTokens & { user: User }>("/auth/login", { email, password });
  tokens.set(data);
  return data.user;
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
    city_of_residence: string
    deliver_cities: string[]
    has_own_transportation: boolean
  }>,
): Promise<User> {
  const { data: res } = await api.patch<User>("/auth/me", data)
  return res
}

export const validateInviteApi = (code: string) =>
  api.get<{ ambassador_name: string; valid: boolean }>(`/auth/invite/${code}`).then((r) => r.data)

export async function applyInstructorApi(data: {
  full_name: string
  email: string
  password: string
  invite_code: string
  university?: string
  highest_degree?: string
  highest_degree_other?: string
  city_of_residence?: string
  deliver_cities?: string[]
  background_areas?: string[]
  background_other?: string
  has_own_transportation?: boolean
  country?: string
}): Promise<User> {
  // Unlike apply/teacher-apply, this creates an active user immediately
  // (status starts the pipeline, not a pending-admin-approval gate) and
  // auto-logs them in, so it stores tokens the same way login() does.
  const { data: res } = await api.post<AuthTokens & { user: User }>("/auth/instructor-apply", data);
  tokens.set(res);
  return res.user;
}

