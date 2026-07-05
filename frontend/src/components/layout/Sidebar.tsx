import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Bell,
  BookOpen,
  ChevronDown,
  ClipboardList,
  FileText,
  FolderOpen,
  GraduationCap,
  LayoutGrid,
  LayoutList,
  ListChecks,
  ListTodo,
  LogOut,
  Menu,
  Moon,
  PlayCircle,
  Settings as SettingsIcon,
  Share2,
  Sun,
  Target,
  Trophy,
  Users,
  Video,
  Wallet,
  X,
  type LucideIcon,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { getNotificationsApi, markAllReadApi } from "@/api/notifications";
import { getPaymentSummaryApi } from "@/api/instructors/payments";
import { ROLE_LABEL, type Notification, type Role } from "@/types/shared";
import { DomainIcon } from "@/components/ui/DomainIcon";
import { cn } from "@/lib/utils";

function toggleTheme() {
  const isDark = document.documentElement.classList.toggle("dark");
  localStorage.setItem("theme", isDark ? "dark" : "light");
}

interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
}

/** Per-label icon lookup so the (verbatim) nav-link branching stays terse. */
const ICONS: Record<string, LucideIcon> = {
  Dashboard: LayoutGrid,
  Board: LayoutGrid,
  Overview: LayoutGrid,
  Tracker: ListChecks,
  "Team Management": Users,
  "User Management": Users,
  Documents: FileText,
  Applications: ClipboardList,
  Settings: SettingsIcon,
  Leads: Target,
  Tasks: ListTodo,
  Network: Share2,
  Materials: FolderOpen,
  Leaderboard: Trophy,
  "My Sessions": GraduationCap,
  Training: PlayCircle,
  Library: BookOpen,
  Payments: Wallet,
  Status: Activity,
  Videos: Video,
  Modules: LayoutList,
  Application: ClipboardList,
};

const mk = (label: string, to: string): NavItem => ({ label, to, icon: ICONS[label] ?? FileText });

const DOMAIN_TITLE: Record<string, string> = {
  interns: "Interns",
  ambassadors: "Ambassadors",
  instructors: "Instructors",
  admin: "Admin",
};

/**
 * Nav-link set — computed from URL path domain + activeRole, VERBATIM from the
 * old Navbar (admin browsing /interns gets interns nav, etc.). Only difference:
 * each item now carries a lucide icon via `mk`.
 */
function getNavItems(pathname: string, activeRole: Role | null): NavItem[] {
  if (pathname.startsWith("/admin")) {
    return [
      mk("Dashboard", "/admin"),
      mk("User Management", "/admin/users"),
      mk("Documents", "/admin/documents"),
      mk("Applications", "/admin/applications"),
      mk("Settings", "/admin/settings"),
    ];
  }
  if (pathname.startsWith("/ambassadors")) {
    if (activeRole === "admin") return [];
    if (activeRole === "teacher") {
      return [
        mk("My Sessions", "/ambassadors/teacher-portal"),
        mk("Tasks", "/ambassadors/tasks"),
        mk("Materials", "/ambassadors/materials"),
        mk("Documents", "/ambassadors/documents"),
        mk("Leaderboard", "/ambassadors/leaderboard"),
      ];
    }
    return [
      mk("Dashboard", "/ambassadors"),
      mk("Leads", "/ambassadors/leads"),
      mk("Tasks", "/ambassadors/tasks"),
      mk("Network", "/ambassadors/network"),
      mk("Materials", "/ambassadors/materials"),
      mk("Documents", "/ambassadors/documents"),
      mk("Leaderboard", "/ambassadors/leaderboard"),
    ];
  }
  if (pathname.startsWith("/instructors")) {
    if (activeRole === "admin") return [];
    if (activeRole === "facilitator") {
      return [
        mk("Training", "/instructors/facilitator/training"),
        mk("Library", "/instructors/facilitator/library"),
        mk("Documents", "/instructors/documents"),
        mk("Application", "/instructors/facilitator/application"),
      ];
    }
    if (activeRole === "applicant") {
      return [
        mk("Status", "/instructors/status"),
        mk("Videos", "/instructors/videos"),
        mk("Modules", "/instructors/modules"),
      ];
    }
    return [
      mk("Dashboard", "/instructors/dashboard"),
      mk("Training", "/instructors/training"),
      mk("Library", "/instructors/library"),
      mk("Documents", "/instructors/documents"),
      mk("Payments", "/instructors/payments"),
    ];
  }
  if (pathname.startsWith("/interns")) {
    if (activeRole === "admin") {
      return [
        mk("Dashboard", "/interns"),
        mk("Tracker", "/interns/tracker"),
        mk("Team Management", "/interns/admin"),
      ];
    }
    return [
      mk("Board", "/interns"),
      mk("Tracker", "/interns/tracker"),
      mk("Documents", "/interns/documents"),
    ];
  }
  // Fallback based on activeRole (no domain in path yet).
  if (activeRole === "ambassador") {
    return [
      mk("Dashboard", "/ambassadors"),
      mk("Leads", "/ambassadors/leads"),
      mk("Tasks", "/ambassadors/tasks"),
      mk("Network", "/ambassadors/network"),
      mk("Materials", "/ambassadors/materials"),
      mk("Documents", "/ambassadors/documents"),
      mk("Leaderboard", "/ambassadors/leaderboard"),
    ];
  }
  if (activeRole === "teacher") {
    return [
      mk("My Sessions", "/ambassadors/teacher-portal"),
      mk("Tasks", "/ambassadors/tasks"),
      mk("Materials", "/ambassadors/materials"),
      mk("Documents", "/ambassadors/documents"),
      mk("Leaderboard", "/ambassadors/leaderboard"),
    ];
  }
  if (activeRole === "applicant") {
    return [
      mk("Status", "/instructors/status"),
      mk("Videos", "/instructors/videos"),
      mk("Modules", "/instructors/modules"),
    ];
  }
  if (activeRole === "instructor") {
    return [
      mk("Dashboard", "/instructors/dashboard"),
      mk("Training", "/instructors/training"),
      mk("Library", "/instructors/library"),
      mk("Documents", "/instructors/documents"),
      mk("Payments", "/instructors/payments"),
    ];
  }
  if (activeRole === "facilitator") {
    return [
      mk("Training", "/instructors/facilitator/training"),
      mk("Library", "/instructors/facilitator/library"),
      mk("Documents", "/instructors/documents"),
      mk("Application", "/instructors/facilitator/application"),
    ];
  }
  if (activeRole === "admin") {
    return [
      mk("Dashboard", "/admin"),
      mk("User Management", "/admin/users"),
      mk("Documents", "/admin/documents"),
      mk("Applications", "/admin/applications"),
      mk("Settings", "/admin/settings"),
    ];
  }
  if (activeRole === "intern" || activeRole === "leader") {
    return [
      mk("Board", "/interns"),
      mk("Tracker", "/interns/tracker"),
      mk("Documents", "/interns/documents"),
    ];
  }
  return [];
}

const isActive = (pathname: string, to: string) =>
  to === "/interns" || to === "/ambassadors" || to === "/admin" || to === "/instructors/dashboard"
    ? pathname === to
    : pathname.startsWith(to);

/* ─────────────────────────── sub-pieces ─────────────────────────── */

function ThemeToggle() {
  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="rounded-xl p-2.5 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground"
      aria-label="Toggle theme"
    >
      <Sun size={20} className="dark:hidden" />
      <Moon size={20} className="hidden dark:block" />
    </button>
  );
}

function NotificationsBell() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleClick = () => {
    const wasOpen = open;
    setOpen((v) => !v);
    if (!wasOpen && unread > 0) markAll.mutate();
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={handleClick}
        className="relative rounded-xl p-2.5 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground"
        aria-label="Notifications"
      >
        <Bell size={20} />
        {unread > 0 && (
          <span className="absolute right-1.5 top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[9px] font-bold text-primary-foreground">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
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
  );
}

function RoleSwitcher() {
  const { roles, activeRole, setActiveRole } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (roles.length <= 1 || !activeRole) return null;

  const choose = (r: Role) => {
    setActiveRole(r);
    setOpen(false);
    void navigate({ to: "/" });
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 rounded-xl border border-border bg-background/60 px-3 py-2 text-sm font-medium text-foreground hover:bg-foreground/5"
      >
        {ROLE_LABEL[activeRole]}
        <ChevronDown size={16} />
      </button>
      {open && (
        <ul className="absolute right-0 z-50 mt-2 w-44 overflow-hidden rounded-xl border border-border bg-popover py-1 shadow-lg">
          {roles.map((r) => (
            <li key={r}>
              <button
                type="button"
                onClick={() => choose(r)}
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
  );
}

function Avatar({ to, size = "md" }: { to: string; size?: "sm" | "md" }) {
  const { user } = useAuth();
  const initials = user?.full_name
    ? user.full_name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()
    : "?";
  const dim = size === "sm" ? "h-8 w-8 text-[11px]" : "h-10 w-10 text-xs";
  return (
    <Link
      to={to}
      className={cn(
        "flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-primary/30 bg-primary/10 font-bold font-display tracking-wide text-primary transition-opacity hover:opacity-80",
        dim,
      )}
      aria-label="Profile"
    >
      {user?.photo_url ? (
        <img src={user.photo_url} alt="Profile" className="h-full w-full object-cover" />
      ) : (
        initials
      )}
    </Link>
  );
}

function NavLinks({
  items,
  pathname,
  pendingSignature,
  onNavigate,
}: {
  items: NavItem[];
  pathname: string;
  pendingSignature: number;
  onNavigate?: () => void;
}) {
  return (
    <>
      {items.map((l) => {
        const active = isActive(pathname, l.to);
        const Icon = l.icon;
        const showBadge = l.to === "/instructors/payments" && pendingSignature > 0;
        return (
          <Link
            key={l.to}
            to={l.to}
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-3 rounded-xl px-4 py-3 text-sm transition-all",
              active
                ? "border border-primary/30 bg-primary/10 font-semibold text-primary"
                : "border border-transparent text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
            )}
          >
            <Icon className="h-5 w-5 shrink-0" />
            <span className="truncate">{l.label}</span>
            {showBadge && (
              <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-amber-500 px-1.5 text-[10px] font-bold text-black">
                {pendingSignature}
              </span>
            )}
          </Link>
        );
      })}
    </>
  );
}

/* ─────────────────────────── shell ─────────────────────────── */

export function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, activeRole, logout } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const navItems = getNavItems(pathname, activeRole);

  const { data: paySummary } = useQuery({
    queryKey: ["instructor-payment-summary"],
    queryFn: getPaymentSummaryApi,
    enabled: !!user && activeRole === "instructor",
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
  const pendingSignature = paySummary?.pending_signature ?? 0;

  const profileTo =
    activeRole === "admin"
      ? "/admin/profile"
      : activeRole === "ambassador" || activeRole === "teacher"
      ? "/ambassadors/profile"
      : activeRole === "applicant"
      ? "/instructors/status"
      : activeRole === "instructor" || activeRole === "facilitator"
      ? "/instructors/profile"
      : "/interns/profile";

  // Body scroll lock + Escape-to-close for the mobile drawer.
  useEffect(() => {
    if (!drawerOpen) return;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKey);
    };
  }, [drawerOpen]);

  // Close the drawer whenever the route changes.
  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  if (!user) return null;

  const activeItem = navItems.find((i) => isActive(pathname, i.to));
  const domain = pathname.split("/")[1];
  const pageTitle = activeItem?.label ?? DOMAIN_TITLE[domain] ?? "SpacePoint";
  const roleLabel = activeRole ? ROLE_LABEL[activeRole] : "";

  const handleLogout = () => {
    void logout();
    void navigate({ to: "/login" });
  };

  return (
    <div className="min-h-screen">
      {/* ── Desktop sidebar ─────────────────────────────────────── */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-white/10 bg-card/60 backdrop-blur-xl md:flex">
        <div className="flex h-20 items-center justify-center border-b border-white/10 px-4">
          <Link to="/" aria-label="SpacePoint home">
            <DomainIcon className="h-8 w-auto" />
          </Link>
        </div>
        <nav className="flex-1 space-y-2 overflow-y-auto px-4 py-6">
          <NavLinks items={navItems} pathname={pathname} pendingSignature={pendingSignature} />
        </nav>
        <div className="border-t border-white/10 px-4 py-6">
          <button
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center gap-3 rounded-xl px-4 py-3 text-sm text-muted-foreground transition-all hover:bg-foreground/5 hover:text-destructive"
          >
            <LogOut className="h-5 w-5 shrink-0" />
            Sign Out
          </button>
        </div>
      </aside>

      {/* ── Mobile drawer + overlay ─────────────────────────────── */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/60 transition-opacity md:hidden",
          drawerOpen ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={() => setDrawerOpen(false)}
      />
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-primary/15 bg-background/95 backdrop-blur-xl transition-transform duration-300 md:hidden",
          drawerOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-20 shrink-0 items-center justify-between border-b border-white/10 px-6">
          <DomainIcon className="h-7 w-auto" />
          <button
            type="button"
            onClick={() => setDrawerOpen(false)}
            className="p-1 text-muted-foreground transition-colors hover:text-foreground"
            aria-label="Close menu"
          >
            <X size={22} />
          </button>
        </div>
        {/* User-info strip */}
        <div className="flex shrink-0 items-center gap-3 border-b border-white/5 px-6 py-4">
          <Avatar to={profileTo} size="sm" />
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-foreground">{user.full_name}</p>
            {roleLabel && (
              <p className="text-xs font-medium uppercase tracking-wider text-primary">{roleLabel}</p>
            )}
          </div>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-4 py-4">
          <NavLinks
            items={navItems}
            pathname={pathname}
            pendingSignature={pendingSignature}
            onNavigate={() => setDrawerOpen(false)}
          />
          <RoleSwitcherMobile onNavigate={() => setDrawerOpen(false)} />
        </nav>
        <div className="shrink-0 border-t border-white/10 px-4 py-5">
          <button
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center gap-3 rounded-xl px-4 py-3 text-sm text-muted-foreground transition-all hover:bg-foreground/5 hover:text-destructive"
          >
            <LogOut className="h-5 w-5 shrink-0" />
            Sign Out
          </button>
        </div>
      </div>

      {/* ── Content column ──────────────────────────────────────── */}
      <div className="flex min-h-screen flex-col md:ml-64">
        {/* Mobile top bar */}
        <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center justify-between border-b border-white/10 bg-card/60 px-4 backdrop-blur-xl md:hidden">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            className="-ml-2 rounded-lg p-2 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground"
            aria-label="Open menu"
          >
            <Menu size={22} />
          </button>
          <Link to="/" className="absolute left-1/2 -translate-x-1/2" aria-label="SpacePoint home">
            <DomainIcon className="h-6 w-auto" />
          </Link>
          <div className="flex items-center gap-0.5">
            <ThemeToggle />
            <NotificationsBell />
            <Avatar to={profileTo} size="sm" />
          </div>
        </header>

        {/* Desktop top header */}
        <header className="sticky top-0 z-20 hidden h-20 shrink-0 items-center justify-between border-b border-white/5 bg-background/60 px-8 backdrop-blur-xl md:flex">
          <h2 className="font-display text-lg font-semibold capitalize text-foreground/90">{pageTitle}</h2>
          <div className="flex items-center gap-1.5">
            <NotificationsBell />
            <RoleSwitcher />
            <ThemeToggle />
            <div className="mx-1 text-right">
              <p className="text-sm font-semibold text-foreground">{user.full_name}</p>
              {roleLabel && (
                <p className="text-xs font-medium uppercase tracking-wider text-primary">{roleLabel}</p>
              )}
            </div>
            <Avatar to={profileTo} />
          </div>
        </header>

        <main className="flex-1 overflow-x-hidden p-4 sm:p-6 lg:p-10">{children}</main>
      </div>
    </div>
  );
}

/** Drawer-only role switch section (mobile), rendered inline in the nav list. */
function RoleSwitcherMobile({ onNavigate }: { onNavigate: () => void }) {
  const { roles, activeRole, setActiveRole } = useAuth();
  const navigate = useNavigate();
  if (roles.length <= 1 || !activeRole) return null;
  const choose = (r: Role) => {
    setActiveRole(r);
    onNavigate();
    void navigate({ to: "/" });
  };
  return (
    <div className="mt-2 border-t border-white/10 pt-3">
      <p className="px-4 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Switch role
      </p>
      {roles.map((r) => (
        <button
          key={r}
          type="button"
          onClick={() => choose(r)}
          className={cn(
            "block w-full rounded-xl px-4 py-2.5 text-left text-sm transition-colors hover:bg-foreground/5",
            r === activeRole ? "text-primary" : "text-foreground",
          )}
        >
          {ROLE_LABEL[r]}
        </button>
      ))}
    </div>
  );
}
