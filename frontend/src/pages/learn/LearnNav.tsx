import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Home, GraduationCap, Bell, LogOut, Rocket, Search, Trophy, User, Gamepad2, ArrowLeftRight, ClipboardCheck,
} from "lucide-react";
import { DomainIcon } from "@/components/ui/DomainIcon";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/context/AuthContext";
import { getNotificationsApi, markAllReadApi } from "@/api/notifications";
import { cn } from "@/lib/utils";
import { roleHomePath } from "@/lib/roleHome";

/** `catalog`, `paths` and `profile` are still reachable pages — they just
 * aren't nav entries any more (2026-08-12): discovery moved onto the landing
 * page's rails, and Profile was a duplicate of the avatar menu top-right.
 * They keep their keys so those pages can still mark themselves active. */
export type LearnNavActive = "home" | "catalog" | "missions" | "paths" | "checklists" | "my-courses" | "games" | "leaderboard" | "profile";

const NAV_ITEMS: { key: LearnNavActive; label: string; to: string; icon: typeof Home }[] = [
  { key: "home", label: "Home", to: "/learn", icon: Home },
  { key: "my-courses", label: "My Learning", to: "/learn/my-courses", icon: GraduationCap },
  { key: "checklists", label: "Programs", to: "/learn/checklists", icon: ClipboardCheck },
  { key: "missions", label: "Missions", to: "/learn/missions", icon: Rocket },
  { key: "games", label: "Live Quiz", to: "/learn/games", icon: Gamepad2 },
  { key: "leaderboard", label: "Leaderboard", to: "/learn/leaderboard", icon: Trophy },
];

/** Horizontal nav for LearnShell (design 1b) — can't reuse Sidebar.tsx (D1:
 * vertical, and pages/learn/** must not import it). Copies its nav-link
 * active-state classes only. Collapses to a bottom tab bar on mobile (1m). */
export function LearnNav({ active }: { active: LearnNavActive }) {
  return (
    <>
      <header className="sticky top-0 z-20 hidden md:block border-b border-border bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-[72px] max-w-[1440px] items-center gap-9 px-6">
          <Link to="/learn" aria-label="SpacePoint Learn" className="shrink-0">
            <DomainIcon className="h-9 w-auto" />
          </Link>

          <nav className="flex items-center gap-1.5">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = item.key === active;
              return (
                <Link
                  key={item.key}
                  to={item.to}
                  className={cn(
                    "flex items-center gap-2 rounded-xl px-3.5 h-10 text-sm transition-all",
                    isActive
                      ? "border border-primary/30 bg-primary/10 font-semibold text-primary"
                      : "border border-transparent text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
                  )}
                >
                  <Icon className="h-[19px] w-[19px] shrink-0" />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-1.5">
            <BackToPortalButton />
            <LearnNavSearch />
            <ThemeToggle />
            <LearnNotificationsBell />
            <LearnProfileMenu />
          </div>
        </div>
      </header>

      <LearnMobileTabBar active={active} />
    </>
  );
}

/** Staff browsing /learn had no way back except hand-editing the URL —
 * students have no portal home to return to (roleHomePath maps them right
 * back to /learn), so this only renders for everyone else. */
function BackToPortalButton() {
  const { currentUser } = useAuth();
  if (!currentUser?.role || currentUser.role === "student") return null;
  return (
    <Link
      to={roleHomePath(currentUser.role)}
      className="flex items-center gap-1.5 rounded-xl px-3 h-9 text-sm text-muted-foreground border border-transparent transition-colors hover:bg-foreground/5 hover:text-foreground"
    >
      <ArrowLeftRight className="h-4 w-4 shrink-0" />
      <span className="hidden lg:inline">Back to portal</span>
    </Link>
  );
}

function LearnNavSearch() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const submit = () => {
    const q = value.trim();
    void navigate({ to: "/learn/catalog", search: (q ? { tab: "courses", q } : { tab: "courses" }) as never });
    setOpen(false);
    setValue("");
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => { setOpen(true); setTimeout(() => inputRef.current?.focus(), 0); }}
        className="rounded-xl p-2.5 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground cursor-pointer"
        aria-label="Search courses"
      >
        <Search size={19} />
      </button>
    );
  }

  return (
    <div className="relative flex items-center">
      <Search className="absolute left-3 size-4 text-muted-foreground pointer-events-none" />
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") submit(); if (e.key === "Escape") setOpen(false); }}
        onBlur={() => { if (!value) setOpen(false); }}
        placeholder="Search courses..."
        className="w-56 h-10 pl-9 pr-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
      />
    </div>
  );
}

function LearnNotificationsBell() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const { data: notifications = [] } = useQuery({
    queryKey: ["notifications"],
    queryFn: getNotificationsApi,
    enabled: !!user,
    staleTime: 20_000,
    refetchInterval: 30_000,
  });

  const markAll = useMutation({
    mutationFn: markAllReadApi,
    onSuccess: () =>
      queryClient.setQueryData<typeof notifications>(["notifications"], (old = []) =>
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

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => {
          const wasOpen = open;
          setOpen((v) => !v);
          if (!wasOpen && unread > 0) markAll.mutate();
        }}
        className="relative rounded-xl p-2.5 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground cursor-pointer"
        aria-label="Notifications"
      >
        <Bell size={19} />
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
                <div key={n.id} className={cn("border-b border-border/50 px-4 py-3 last:border-0", !n.is_read && "bg-muted/50")}>
                  <p className="text-sm font-medium text-foreground">{n.title}</p>
                  {n.body && <p className="mt-0.5 text-xs text-muted-foreground">{n.body}</p>}
                  <p className="mt-1 text-xs text-muted-foreground/70">{new Date(n.created_at).toLocaleDateString()}</p>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function LearnProfileMenu() {
  const { currentUser, logout } = useAuth();
  const navigate = useNavigate();
  const initials = currentUser?.full_name
    ? currentUser.full_name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()
    : "?";

  const handleLogout = async () => {
    await logout();
    void navigate({ to: "/learn/login" });
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="ml-1 flex items-center gap-2.5 rounded-xl p-1 pr-2.5 hover:bg-foreground/5 transition-colors cursor-pointer">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-primary/30 bg-primary/10 font-display text-xs font-bold text-primary">
            {initials}
          </span>
          <span className="hidden lg:block text-left">
            <span className="block text-sm font-medium text-foreground leading-tight">{currentUser?.full_name}</span>
            <span className="block text-[11px] text-muted-foreground leading-tight">Explorer</span>
          </span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem onClick={() => void navigate({ to: "/learn/profile" })}>
          <User className="size-3.5" /> Profile
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => void handleLogout()} variant="destructive">
          <LogOut className="size-3.5" /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function LearnMobileTabBar({ active }: { active: LearnNavActive }) {
  const { currentUser } = useAuth();
  const isStaff = !!currentUser?.role && currentUser.role !== "student";

  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 flex flex-col md:hidden border-t border-border bg-background/95 backdrop-blur-xl pb-[env(safe-area-inset-bottom)]">
      <div className="flex items-stretch">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = item.key === active;
          return (
            <Link
              key={item.key}
              to={item.to}
              className={cn(
                "flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] font-medium transition-colors",
                isActive ? "text-primary" : "text-muted-foreground",
              )}
            >
              <Icon className="h-5 w-5" />
              {item.label}
            </Link>
          );
        })}
      </div>
      <div className="flex items-center justify-between border-t border-border/50 px-2 py-1.5">
        {isStaff ? (
          <Link
            to={roleHomePath(currentUser!.role)}
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors"
          >
            <ArrowLeftRight className="h-3.5 w-3.5" />
            Back to portal
          </Link>
        ) : (
          <span />
        )}
        <div className="flex items-center gap-0.5">
          <ThemeToggle />
          <LearnNotificationsBell />
          <LearnProfileMenu />
        </div>
      </div>
    </nav>
  );
}
