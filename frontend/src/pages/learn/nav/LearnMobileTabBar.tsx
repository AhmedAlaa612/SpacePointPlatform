import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeftRight, Home, Rocket } from "lucide-react";
import { fetchMyChecklists } from "@/api/lms";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";
import { roleHomePath } from "@/lib/roleHome";
import { MOBILE_TAB_ITEMS, NAV_ITEMS, type LearnNavActive } from "./navItems";
import { LearnNotificationsBell, LearnProfileMenu } from "./LearnNavShared";

/** Extracted verbatim out of the old LearnNav.tsx (2026-09, Roadmap board
 * redesign: desktop navbar → fixed sidebar, mobile keeps this bottom tab
 * bar unchanged — it already matched the wireframe). */
export function LearnMobileTabBar({ active }: { active: LearnNavActive }) {
  const { currentUser } = useAuth();
  const isStaff = !!currentUser?.role && currentUser.role !== "student";
  // Same query key LearnSidebar/LearnLanding/LearnChecklists all share — one
  // cached fetch, not a new one. Already ordered newest-first by the
  // backend, so [0] is the student's latest program; null for anyone with
  // none (or a non-student role), and the button just doesn't render.
  const { data: checklists } = useQuery({ queryKey: ["lms-my-checklists"], queryFn: fetchMyChecklists });
  const myProgram = checklists?.[0] ?? null;

  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 flex flex-col md:hidden border-t border-border bg-background/95 backdrop-blur-xl pb-[env(safe-area-inset-bottom)] print:hidden">
      <div className="flex items-stretch">
        {MOBILE_TAB_ITEMS.map((key) => {
          const item = NAV_ITEMS.find((navItem) => navItem.key === key)!;
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
          {myProgram && (
            <Link
              to="/learn/checklists/$assignmentId"
              params={{ assignmentId: myProgram.assignment_id }}
              aria-label="Go to your program"
              className="rounded-xl p-2.5 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground"
            >
              <Rocket size={20} />
            </Link>
          )}
          <Link
            to="/learn"
            aria-label="Home"
            className={cn(
              "rounded-xl p-2.5 transition-colors hover:bg-foreground/5 hover:text-foreground",
              active === "home" ? "text-primary" : "text-muted-foreground",
            )}
          >
            <Home size={20} />
          </Link>
          <ThemeToggle />
          <LearnNotificationsBell />
          <LearnProfileMenu />
        </div>
      </div>
    </nav>
  );
}
