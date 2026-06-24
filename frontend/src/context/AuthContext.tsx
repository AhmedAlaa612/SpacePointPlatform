import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { Role, User } from "@/types/shared";
import { fetchMe, login as apiLogin, logout as apiLogout } from "@/api/auth";
import { tokens } from "@/api/client";

const ACTIVE_ROLE = "active_role";

interface AuthContextValue {
  user: User | null;
  roles: Role[];
  activeRole: Role | null;
  loading: boolean;
  setActiveRole: (role: Role) => void;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  hasRole: (role: Role) => boolean;
  isAdmin: boolean;
  // Compatibility aliases for ported domain frontends (interns, ambassadors…):
  // `currentUser.role` is the active role; `isLoading`/`setCurrentUser` mirror state.
  currentUser: (User & { role: Role | null }) | null;
  isLoading: boolean;
  setCurrentUser: (u: User) => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

/** Pick a valid active role: the stored one if the user still has it, else their first role. */
function resolveActiveRole(user: User): Role | null {
  const stored = localStorage.getItem(ACTIVE_ROLE) as Role | null;
  if (stored && user.roles.includes(stored)) return stored;
  return user.roles[0] ?? null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeRole, setActiveRoleState] = useState<Role | null>(
    () => localStorage.getItem(ACTIVE_ROLE) as Role | null,
  );

  const applyActiveRole = useCallback((role: Role | null) => {
    if (role) localStorage.setItem(ACTIVE_ROLE, role);
    else localStorage.removeItem(ACTIVE_ROLE);
    setActiveRoleState(role);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!tokens.access) {
        setLoading(false);
        return;
      }
      try {
        const me = await fetchMe();
        if (cancelled) return;
        setUser(me);
        applyActiveRole(resolveActiveRole(me));
      } catch {
        tokens.clear();
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [applyActiveRole]);

  const setActiveRole = useCallback(
    (role: Role) => applyActiveRole(role),
    [applyActiveRole],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const me = await apiLogin(email, password);
      setUser(me);
      applyActiveRole(resolveActiveRole(me));
      return me;
    },
    [applyActiveRole],
  );

  const logout = useCallback(async () => {
    await apiLogout();
    applyActiveRole(null);
    setUser(null);
  }, [applyActiveRole]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      roles: user?.roles ?? [],
      activeRole,
      loading,
      setActiveRole,
      login,
      logout,
      hasRole: (role: Role) => !!user?.roles.includes(role),
      isAdmin: !!user?.roles.includes("admin"),
      currentUser: user ? { ...user, role: activeRole } : null,
      isLoading: loading,
      setCurrentUser: (u: User) => setUser(u),
    }),
    [user, activeRole, loading, setActiveRole, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
