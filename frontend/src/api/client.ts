import axios, { type InternalAxiosRequestConfig } from "axios";
import type { AuthTokens } from "@/types/shared";

const baseURL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const api = axios.create({ baseURL });

const ACCESS = "access_token";
const REFRESH = "refresh_token";

/** Token storage — single source of truth for auth credentials. */
export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS);
  },
  get refresh() {
    return localStorage.getItem(REFRESH);
  },
  set({ access_token, refresh_token }: { access_token: string; refresh_token?: string }) {
    localStorage.setItem(ACCESS, access_token);
    if (refresh_token) localStorage.setItem(REFRESH, refresh_token);
  },
  clear() {
    localStorage.removeItem(ACCESS);
    localStorage.removeItem(REFRESH);
  },
};

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokens.access;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// De-duplicate concurrent refreshes so a burst of 401s only refreshes once.
let refreshing: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refresh_token = tokens.refresh;
  if (!refresh_token) return null;
  try {
    const { data } = await axios.post<AuthTokens>(`${baseURL}/auth/refresh`, { refresh_token });
    tokens.set(data);
    return data.access_token;
  } catch {
    tokens.clear();
    return null;
  }
}

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      refreshing = refreshing ?? refreshAccessToken();
      const newToken = await refreshing;
      refreshing = null;
      if (newToken) {
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      }
      if (location.pathname !== "/login") location.assign("/login");
    }
    return Promise.reject(error);
  },
);
