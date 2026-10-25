import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftRight, Bell, LogOut, User } from "lucide-react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { TutorialLauncherMenu } from "@/components/ui/SpacePointTourCard";
import { useAuth } from "@/context/AuthContext";
import { getNotificationsApi, markAllReadApi } from "@/api/notifications";
import { cn } from "@/lib/utils";
import { roleHomePath } from "@/lib/roleHome";

/** Shared between LearnSidebar (desktop) and LearnMobileTabBar — split out
 * of the old LearnNav.tsx (2026-09, Roadmap board redesign: navbar → fixed
 * sidebar on desktop) so neither surface duplicates this logic. */

/** Staff browsing /learn had no way back except hand-editing the URL —
 * students have no portal home to return to (roleHomePath maps them right
 * back to /learn), so this only renders for everyone else. */
export function BackToPortalButton({ compact }: { compact?: boolean }) {
  const { currentUser } = useAuth();
  if (!currentUser?.role || currentUser.role === "student") return null;
  return (
    <Link
      to={roleHomePath(currentUser.role)}
      data-tour="learn-back-to-portal"
      className={cn(
        "flex items-center gap-1.5 rounded-xl px-3 h-9 text-sm text-muted-foreground border border-transparent transition-colors hover:bg-foreground/5 hover:text-foreground",
        compact && "px-2.5",
      )}
    >
      <ArrowLeftRight className="h-4 w-4 shrink-0" />
      {!compact && <span className="hidden lg:inline">Back to portal</span>}
    </Link>
  );
}

export function LearnTutorialButton({
  align = "right",
  side = "top",
}: {
  align?: "left" | "right";
  side?: "top" | "bottom";
}) {
  return (
    <TutorialLauncherMenu
      tourAttr="learn-tutorial-btn"
      compact
      align={align}
      side={side}
    />
  );
}

export function LearnNotificationsBell({
  align = "right", side = "bottom",
}: {
  align?: "left" | "right";
  /** "bottom" (default, opens below the trigger) or "top" (opens above
   * it) — the sidebar's own bell sits pinned at the bottom of the
   * viewport, so it needs "top" to stay on screen. */
  side?: "top" | "bottom";
}) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const { data: notifications = [] } = useQuery({
    queryKey: ["notifications"],
    queryFn: getNotificationsApi,
    enabled: !!user,
    staleTime: 30_000,
    refetchInterval: 60_000,
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
        <div
          className={cn(
            "absolute z-50 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-border bg-popover shadow-lg",
            align === "left" ? "left-0" : "right-0",
            side === "top" ? "bottom-full mb-2" : "top-full mt-2",
          )}
        >
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

export function LearnProfileMenu() {
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
        <button className="flex items-center gap-2.5 rounded-xl p-1 pr-2.5 hover:bg-foreground/5 transition-colors cursor-pointer">
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
