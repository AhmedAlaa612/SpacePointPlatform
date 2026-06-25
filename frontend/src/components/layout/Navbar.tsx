import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, ChevronDown, LogOut, Menu, Moon, Sun, X } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { getNotificationsApi, markAllReadApi } from "@/api/notifications";
import { ROLE_DOMAIN, ROLE_LABEL, type Notification, type Role } from "@/types/shared";
import { roleLogo } from "@/lib/logos";
import { cn } from "@/lib/utils";

function toggleTheme() {
  const isDark = document.documentElement.classList.toggle("dark");
  localStorage.setItem("theme", isDark ? "dark" : "light");
}

interface NavItem {
  label: string;
  to: string;
}

export function Navbar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, roles, activeRole, setActiveRole, logout, isAdmin } = useAuth();
  const queryClient = useQueryClient();

  const [menuOpen, setMenuOpen] = useState(false); // mobile menu
  const [bellOpen, setBellOpen] = useState(false);
  const [roleOpen, setRoleOpen] = useState(false);
  const bellRef = useRef<HTMLDivElement>(null);
  const roleRef = useRef<HTMLDivElement>(null);

  const { data: notifications = [] } = useQuery<Notification[]>({
    queryKey: ["notifications"],
    queryFn: getNotificationsApi,
    enabled: !!user,
    staleTime: 20_000,
    refetchInterval: 30_000,
  });

  const markAll = useMutation({
    mutationFn: markAllReadApi,
    onSuccess: () =>
      queryClient.setQueryData<Notification[]>(["notifications"], (old = []) =>
        old.map((n) => ({ ...n, is_read: true })),
      ),
  });

  const unread = notifications.filter((n) => !n.is_read).length;

  // Close dropdowns when clicking outside.
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) setBellOpen(false);
      if (roleRef.current && !roleRef.current.contains(e.target as Node)) setRoleOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (!user) return null;

  const domain = activeRole ? ROLE_DOMAIN[activeRole] : null;
  let navLinks: NavItem[] = [];
  if (activeRole === "ambassador") {
    navLinks = [
      { label: "Dashboard", to: "/ambassadors" },
      { label: "Leads", to: "/ambassadors/leads" },
      { label: "Tasks", to: "/ambassadors/tasks" },
      { label: "Network", to: "/ambassadors/network" },
      { label: "Materials", to: "/ambassadors/materials" },
      { label: "Leaderboard", to: "/ambassadors/leaderboard" },
    ];
  } else if (activeRole === "teacher") {
    navLinks = [
      { label: "My Sessions", to: "/ambassadors/teacher-portal" },
      { label: "Tasks", to: "/ambassadors/tasks" },
      { label: "Materials", to: "/ambassadors/materials" },
      { label: "Leaderboard", to: "/ambassadors/leaderboard" },
    ];
  } else if (domain === "interns" || isAdmin) {
    navLinks = [
      { label: "Board", to: "/interns" },
      { label: "Tracker", to: "/interns/tracker" },
      ...(isAdmin ? [{ label: "Admin", to: "/interns/admin" }] : []),
    ];
  }

  const profileTo = (activeRole === "ambassador" || activeRole === "teacher")
    ? "/ambassadors/profile"
    : "/interns/profile";

  const initials = user.full_name
    ? user.full_name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()
    : "?";

  const isActive = (to: string) =>
    (to === "/interns" || to === "/ambassadors") ? pathname === to : pathname.startsWith(to);

  const handleBell = () => {
    const wasOpen = bellOpen;
    setBellOpen((v) => !v);
    if (!wasOpen && unread > 0) markAll.mutate();
  };

  const handleLogout = () => {
    void logout();
    void navigate({ to: "/login" });
  };

  const chooseRole = (r: Role) => {
    setActiveRole(r);
    setRoleOpen(false);
    setMenuOpen(false);
    void navigate({ to: "/" });
  };

  return (
    <nav className="sticky top-0 z-40 border-b border-border bg-card/95 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-card/80">
      <div className="mx-auto flex h-20 max-w-7xl items-center justify-between gap-2 px-4 sm:h-24 sm:px-6 lg:px-8">
        {/* Left: hamburger (mobile) + logo */}
        <div className="flex items-center gap-2">
          {navLinks.length > 0 && (
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground md:hidden"
              aria-label="Toggle menu"
            >
              {menuOpen ? <X size={22} /> : <Menu size={22} />}
            </button>
          )}
          <Link to="/" className="flex shrink-0 items-center" aria-label="SpacePoint home">
            <img src={roleLogo(activeRole)} alt="SpacePoint" className="h-10 w-auto sm:h-12" />
          </Link>
        </div>

        {/* Center: nav links (desktop) */}
        <div className="hidden items-center gap-1 md:flex">
          {navLinks.map((l) => (
            <Link
              key={l.to}
              to={l.to}
              className={cn(
                "rounded-xl px-4 py-2 text-sm font-semibold transition-colors",
                isActive(l.to)
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {l.label}
            </Link>
          ))}
        </div>

        {/* Right: bell, role switcher, theme, avatar, logout */}
        <div className="flex items-center gap-0.5 sm:gap-1.5">
          {/* Notifications */}
          <div ref={bellRef} className="relative">
            <button
              type="button"
              onClick={handleBell}
              className="relative rounded-xl p-2.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              aria-label="Notifications"
            >
              <Bell size={20} />
              {unread > 0 && (
                <span className="absolute right-1.5 top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[9px] font-bold text-primary-foreground">
                  {unread > 9 ? "9+" : unread}
                </span>
              )}
            </button>
            {bellOpen && (
              <div className="absolute right-0 top-full z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-border bg-popover shadow-lg">
                <div className="border-b border-border px-4 py-3">
                  <p className="text-sm font-semibold text-foreground">Notifications</p>
                </div>
                <div className="max-h-80 overflow-y-auto">
                  {notifications.length === 0 ? (
                    <p className="px-4 py-6 text-center text-sm text-muted-foreground">No notifications</p>
                  ) : (
                    notifications.map((n) => (
                      <div
                        key={n.id}
                        className={cn(
                          "border-b border-border/50 px-4 py-3 last:border-0",
                          !n.is_read && "bg-muted/50",
                        )}
                      >
                        <p className="text-sm font-medium text-foreground">{n.title}</p>
                        {n.body && <p className="mt-0.5 text-xs text-muted-foreground">{n.body}</p>}
                        <p className="mt-1 text-xs text-muted-foreground/70">
                          {new Date(n.created_at).toLocaleDateString()}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Role switcher (multi-role, desktop) */}
          {roles.length > 1 && activeRole && (
            <div ref={roleRef} className="relative hidden md:block">
              <button
                type="button"
                onClick={() => setRoleOpen((v) => !v)}
                className="flex items-center gap-1 rounded-xl border border-border bg-background px-3 py-2 text-sm font-medium text-foreground hover:bg-muted"
              >
                {ROLE_LABEL[activeRole]}
                <ChevronDown size={16} />
              </button>
              {roleOpen && (
                <ul className="absolute right-0 z-50 mt-2 w-44 overflow-hidden rounded-xl border border-border bg-popover py-1 shadow-lg">
                  {roles.map((r) => (
                    <li key={r}>
                      <button
                        type="button"
                        onClick={() => chooseRole(r)}
                        className={cn(
                          "block w-full px-3 py-2 text-left text-sm hover:bg-muted",
                          r === activeRole ? "text-primary" : "text-popover-foreground",
                        )}
                      >
                        {ROLE_LABEL[r]}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Theme toggle */}
          <button
            type="button"
            onClick={toggleTheme}
            className="rounded-xl p-2.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Toggle theme"
          >
            <Sun size={20} className="dark:hidden" />
            <Moon size={20} className="hidden dark:block" />
          </button>

          {/* Avatar → profile */}
          <Link
            to={profileTo}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-foreground text-xs font-bold tracking-wide text-background transition-opacity hover:opacity-80"
            aria-label="Profile"
          >
            {initials}
          </Link>

          {/* Logout (desktop) */}
          <button
            type="button"
            onClick={handleLogout}
            className="hidden rounded-xl p-2.5 text-muted-foreground transition-colors hover:bg-muted hover:text-destructive md:flex"
            aria-label="Log out"
          >
            <LogOut size={20} />
          </button>
        </div>
      </div>

      {/* Mobile slide-down menu */}
      {menuOpen && navLinks.length > 0 && (
        <div className="absolute inset-x-0 top-full z-50 border-b border-border bg-card px-4 py-2 shadow-lg md:hidden">
          {navLinks.map((l) => (
            <Link
              key={l.to}
              to={l.to}
              onClick={() => setMenuOpen(false)}
              className={cn(
                "mb-1 block rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                isActive(l.to) ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-muted",
              )}
            >
              {l.label}
            </Link>
          ))}

          {roles.length > 1 && activeRole && (
            <div className="mt-1 border-t border-border pt-2">
              <p className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Switch role
              </p>
              {roles.map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => chooseRole(r)}
                  className={cn(
                    "block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-muted",
                    r === activeRole ? "text-primary" : "text-foreground",
                  )}
                >
                  {ROLE_LABEL[r]}
                </button>
              ))}
            </div>
          )}

          <button
            type="button"
            onClick={handleLogout}
            className="mt-1 w-full rounded-lg px-3 py-2.5 text-left text-sm font-medium text-destructive hover:bg-destructive/10"
          >
            Sign out
          </button>
        </div>
      )}
    </nav>
  );
}
