import { api, tokens } from "./client";
import type { AuthTokens, User } from "@/types/shared";

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

export const applyAmbassadorApi = (data: {
  full_name: string
  email: string
  password: string
  country?: string
}) => api.post("/auth/apply", data).then((r) => r.data)

export const applyTeacherApi = (data: {
  full_name: string
  email: string
  password: string
  invite_code: string
  answers?: Record<string, any>
}) => api.post("/auth/teacher-apply", data).then((r) => r.data)

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

