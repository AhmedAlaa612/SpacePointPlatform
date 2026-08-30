import axios, { type InternalAxiosRequestConfig } from "axios";
import type { AuthTokens } from "@/types/shared";

export const apiBaseUrl: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const baseURL = apiBaseUrl;

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

// A 401 from these endpoints is a verdict on the credentials just submitted,
// not an expired session: the login form itself must show "Invalid email or
// password" rather than being torn down by a redirect. Before this, a student
// fat-fingering their password on /learn/login was thrown at the portal's
// /login page with no error shown at all.
const CREDENTIAL_PATHS = ["/auth/login", "/auth/signup", "/auth/refresh", "/auth/instructor-apply"];

function isCredentialRequest(config?: InternalAxiosRequestConfig): boolean {
  const url = config?.url ?? "";
  const path = url.startsWith(baseURL) ? url.slice(baseURL.length) : url;
  return CREDENTIAL_PATHS.some((p) => path === p || path.startsWith(`${p}?`));
}

/** Students live on their own surface (`/learn`, own login page and shell), so
 *  an expired session there has to land back on /learn/login — sending them to
 *  the portal sign-in drops them into staff chrome they have no business in. */
function signInPathFor(pathname: string): string {
  return pathname === "/learn" || pathname.startsWith("/learn/") ? "/learn/login" : "/login";
}

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (
      error.response?.status === 401 &&
      original &&
      !original._retry &&
      !isCredentialRequest(original)
    ) {
      original._retry = true;
      refreshing = refreshing ?? refreshAccessToken();
      const newToken = await refreshing;
      refreshing = null;
      if (newToken) {
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      }
      const signIn = signInPathFor(location.pathname);
      if (location.pathname !== signIn) location.assign(signIn);
    }
    return Promise.reject(error);
  },
);
