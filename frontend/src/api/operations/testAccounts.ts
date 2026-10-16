import { api } from "@/api/client";
import type { Role, User } from "@/types/shared";

export interface CreateTestUserPayload {
  full_name: string;
  email: string;
  password: string;
  roles: Role[];
  phone?: string;
}

export interface UpdateTestUserPayload {
  full_name?: string;
  email?: string;
  password?: string;
  roles?: Role[];
  status?: string;
  phone?: string;
}

export interface TestApplicationItem {
  id: string;
  full_name: string;
  email: string;
  role: string;
  status: string;
  created_at: string;
}

export const getTestUsersApi = async (): Promise<User[]> => {
  const { data } = await api.get("/operations/test-accounts/users");
  return data;
};

export const getTestApplicationsApi = async (): Promise<TestApplicationItem[]> => {
  const { data } = await api.get("/operations/test-accounts/applications");
  return data;
};

export const createTestUserApi = async (payload: CreateTestUserPayload): Promise<User> => {
  const { data } = await api.post("/operations/test-accounts/users", payload);
  return data;
};

export const updateTestUserApi = async (id: string, payload: UpdateTestUserPayload): Promise<User> => {
  const { data } = await api.patch(`/operations/test-accounts/users/${id}`, payload);
  return data;
};

export const getTestUserResetLinkApi = async (
  id: string
): Promise<{ user_id: string; email: string; reset_url: string }> => {
  const { data } = await api.post(`/operations/test-accounts/users/${id}/reset-link`);
  return data;
};

export const cascadeDeleteTestUserApi = async (id: string) => {
  const { data } = await api.delete(`/operations/test-accounts/users/${id}`);
  return data;
};

export const cascadeDeleteTestEmailApi = async (email: string) => {
  const { data } = await api.delete("/operations/test-accounts/by-email", { params: { email } });
  return data;
};
