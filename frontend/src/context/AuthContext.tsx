import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { OrgSandboxRole, Role, User } from "@/types/shared";
import { fetchMe, login as apiLogin, logout as apiLogout } from "@/api/auth";
import { tokens } from "@/api/client";

const ACTIVE_ROLE = "active_role";
const ACTIVE_ORG_ROLE = "active_org_role";

interface AuthContextValue {
  user: User | null;
  roles: Role[];
  activeRole: Role | null;
  orgRoles: OrgSandboxRole[];
  switchableOrgRoles: OrgSandboxRole[];
  activeOrgRole: OrgSandboxRole | null;
  loading: boolean;
  setActiveRole: (role: Role) => void;
  setActiveOrgRole: (orgRole: OrgSandboxRole) => void;
  setActiveWorkspace: (role: Role, orgRole?: OrgSandboxRole | null) => void;
  refreshMe: () => Promise<User | null>;
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

export function resolveUserOrgRoles(user: User | null): OrgSandboxRole[] {
  if (!user) return [];
  const raw = (user.org_roles ?? []).filter(Boolean) as OrgSandboxRole[];
  if (raw.length > 0) return raw;
  if (user.org_role) return [user.org_role];
  if (user.roles.includes("organization")) return ["coordinator"];
  return [];
}

export function switchableOrgRolesFor(orgRoles: OrgSandboxRole[]): OrgSandboxRole[] {
  const nonObserver = orgRoles.filter((r) => r !== "observer");
  return nonObserver.length > 0 ? nonObserver : orgRoles;
}

/** Pick a valid active role: the stored one if the user still has it, else their first role.
 * `observer` is a testing label, never a workspace — it is skipped even when
 * stored or first, so a judge/instructor turned observer keeps their real
 * home instead of landing on the role fallback. */
function resolveActiveRole(user: User): Role | null {
  const stored = localStorage.getItem(ACTIVE_ROLE) as Role | null;
  if (stored && stored !== "observer" && user.roles.includes(stored)) return stored;
  return user.roles.find((r) => r !== "observer") ?? user.roles[0] ?? null;
}

function resolveActiveOrgRole(user: User): OrgSandboxRole | null {
  if (!user.roles.includes("organization")) return null;
  const switchable = switchableOrgRolesFor(resolveUserOrgRoles(user));
  if (switchable.length === 0) return null;
  const stored = localStorage.getItem(ACTIVE_ORG_ROLE) as OrgSandboxRole | null;
  if (stored && switchable.includes(stored)) return stored;
  return switchable[0];
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeRole, setActiveRoleState] = useState<Role | null>(
    () => localStorage.getItem(ACTIVE_ROLE) as Role | null,
  );
  const [activeOrgRole, setActiveOrgRoleState] = useState<OrgSandboxRole | null>(
    () => localStorage.getItem(ACTIVE_ORG_ROLE) as OrgSandboxRole | null,
  );

  const applyActiveRole = useCallback((role: Role | null) => {
    if (role) localStorage.setItem(ACTIVE_ROLE, role);
    else localStorage.removeItem(ACTIVE_ROLE);
    setActiveRoleState(role);
  }, []);

  const applyActiveOrgRole = useCallback((orgRole: OrgSandboxRole | null) => {
    if (orgRole) localStorage.setItem(ACTIVE_ORG_ROLE, orgRole);
    else localStorage.removeItem(ACTIVE_ORG_ROLE);
    setActiveOrgRoleState(orgRole);
  }, []);

  const syncUser = useCallback(
    (me: User) => {
      setUser(me);
      applyActiveRole(resolveActiveRole(me));
      applyActiveOrgRole(resolveActiveOrgRole(me));
    },
    [applyActiveRole, applyActiveOrgRole],
  );

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
        syncUser(me);
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
  }, [syncUser]);

  const setActiveRole = useCallback(
    (role: Role) => {
      applyActiveRole(role);
      if (role === "organization" && user) {
        applyActiveOrgRole(resolveActiveOrgRole(user));
      }
    },
    [applyActiveRole, applyActiveOrgRole, user],
  );

  const setActiveOrgRole = useCallback(
    (orgRole: OrgSandboxRole) => {
      applyActiveOrgRole(orgRole);
    },
    [applyActiveOrgRole],
  );

  const setActiveWorkspace = useCallback(
    (role: Role, orgRole?: OrgSandboxRole | null) => {
      applyActiveRole(role);
      if (orgRole !== undefined && orgRole !== null) {
        applyActiveOrgRole(orgRole);
      } else if (role === "organization" && user) {
        applyActiveOrgRole(resolveActiveOrgRole(user));
      }
    },
    [applyActiveRole, applyActiveOrgRole, user],
  );

  const refreshMe = useCallback(async () => {
    if (!tokens.access) return null;
    const me = await fetchMe();
    syncUser(me);
    return me;
  }, [syncUser]);

  const login = useCallback(
    async (email: string, password: string) => {
      const me = await apiLogin(email, password);
      syncUser(me);
      return me;
    },
    [syncUser],
  );

  const logout = useCallback(async () => {
    await apiLogout();
    applyActiveRole(null);
    applyActiveOrgRole(null);
    setUser(null);
  }, [applyActiveRole, applyActiveOrgRole]);

  const orgRoles = useMemo(() => resolveUserOrgRoles(user), [user]);
  const switchableOrgRoles = useMemo(() => switchableOrgRolesFor(orgRoles), [orgRoles]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      roles: user?.roles ?? [],
      activeRole,
      orgRoles,
      switchableOrgRoles,
      activeOrgRole,
      loading,
      setActiveRole,
      setActiveOrgRole,
      setActiveWorkspace,
      refreshMe,
      login,
      logout,
      hasRole: (role: Role) => !!user?.roles.includes(role),
      isAdmin: !!user?.roles.includes("admin"),
      currentUser: user ? { ...user, role: activeRole } : null,
      isLoading: loading,
      setCurrentUser: (u: User) => setUser(u),
    }),
    [
      user,
      activeRole,
      orgRoles,
      switchableOrgRoles,
      activeOrgRole,
      loading,
      setActiveRole,
      setActiveOrgRole,
      setActiveWorkspace,
      refreshMe,
      login,
      logout,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
