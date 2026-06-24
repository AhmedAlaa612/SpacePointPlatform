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
