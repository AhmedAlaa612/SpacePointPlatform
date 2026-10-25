import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Rocket, Search } from "lucide-react";
import { fetchMyChecklists } from "@/api/lms";
import { useAuth } from "@/context/AuthContext";
import { DomainIcon } from "@/components/ui/DomainIcon";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { cn } from "@/lib/utils";
import { NAV_ITEMS, type LearnNavActive } from "./nav/navItems";
import { BackToPortalButton, LearnNotificationsBell, LearnProfileMenu } from "./nav/LearnNavShared";

/** The Roadmap board redesign's fixed desktop sidebar (2026-09) — replaces
 * the old horizontal navbar on `md:` and up per the design spec ("just like
 * the portal we will be going with a sidebar instead of a navbar"). Can't
 * reuse `components/layout/Sidebar` (the portal's own) — `pages/learn/**`
 * may not import it (see LearnShell.tsx's docblock) — so this copies its
 * width, spacing and nav-link classes to match exactly (w-64, h-20 header,
 * px-4 py-6 nav padding, px-4 py-3 per-link padding, h-5 w-5 icons — the
 * client's own ask, "the sidebar needs to be the same size as the portal,
 * and the same spacing"), same precedent the old LearnNav.tsx already
 * established for the active-state classes alone. `LearnShell` offsets its
 * content column by the same w-64 width.
 *
 * Mobile is unchanged: `LearnMobileTabBar` (bottom tab bar) already matched
 * the wireframe, so it isn't touched by this redesign. */
export function LearnSidebar({ active }: { active: LearnNavActive }) {
  // Same query key LearnLanding/LearnChecklists use — one shared cache entry,
  // not a second fetch. Already ordered newest-first by the backend
  // (`list_student_assignments`), so [0] is "their latest program" with no
  // client-side sort of our own. Empty for anyone with no program (or a
  // non-student role previewing /learn) — the card just doesn't render.
  // Disabled for logged-out visitors: firing it without a token 401s, and
  // the api client's interceptor hard-redirects to /learn/login.
  const { user } = useAuth();
  const { data: checklists } = useQuery({
    queryKey: ["lms-my-checklists"],
    queryFn: fetchMyChecklists,
    enabled: !!user,
  });
  const myProgram = checklists?.[0] ?? null;

  return (
    <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 flex-col border-r border-border dark:border-[#a880ff]/15 bg-background md:flex print:hidden">
      <div className="flex h-20 shrink-0 items-center gap-2 border-b border-border dark:border-[#a880ff]/10 px-4">
        <Link to="/learn/home" aria-label="SpacePoint Learn" className="flex flex-1 items-center gap-2 overflow-hidden">
          <DomainIcon className="h-11 w-auto shrink-0" />
        </Link>
        <Link
          to="/learn/catalog"
          aria-label="Search courses"
          className="shrink-0 rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground"
        >
          <Search size={18} />
        </Link>
      </div>

      <nav className="flex flex-1 min-h-0 flex-col space-y-1.5 overflow-y-auto px-4 py-6">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = item.key === active;
          return (
            <Link
              key={item.key}
              to={item.to}
              className={cn(
                "flex items-center gap-3 rounded-[10px] px-4 py-2.5 text-sm transition-all border-[3px]",
                isActive
                  ? "lms-card font-bold text-foreground dark:text-white shadow-none"
                  : "border-transparent text-muted-foreground hover:bg-foreground/5 hover:text-foreground dark:hover:bg-[#a880ff]/10 dark:hover:text-white",
              )}
            >
              <Icon className={cn("h-5 w-5 shrink-0", isActive ? "text-lms-cta dark:text-lms-accent" : "")} />
              <span className="truncate">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="shrink-0 flex flex-col gap-3 px-4 pb-6 pt-3">
        {myProgram && (
          <Link
            to="/learn/checklists/$assignmentId"
            params={{ assignmentId: myProgram.assignment_id }}
            className="lms-card p-3.5 flex flex-col gap-2 transition-transform hover:-translate-y-0.5"
          >
            <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-lms-cta dark:text-lms-accent">
              <Rocket className="size-3" />
              {myProgram.cohort_name ?? "Your program"}
            </div>
            <div className="text-sm font-bold text-foreground truncate">
              {myProgram.name}
            </div>
            <div className="h-1.5 rounded-full bg-foreground/10 dark:bg-white/10 overflow-hidden">
              <div
                className="h-full rounded-full bg-lms-cta dark:bg-lms-accent transition-[width] duration-300"
                style={{ width: `${myProgram.pct}%` }}
              />
            </div>
          </Link>
        )}
        <div className="flex items-center gap-1 border-t border-border dark:border-[#a880ff]/10 pt-3">
          <ThemeToggle />
          {user ? (
            <>
              <LearnNotificationsBell align="left" side="top" />
              <LearnProfileMenu />
            </>
          ) : (
            <>
              <Link
                to="/learn/login"
                className="flex h-9 flex-1 items-center justify-center rounded-lg px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground"
              >
                Log in
              </Link>
              <Link
                to="/learn/signup"
                className="lms-btn-primary flex h-9 flex-1 items-center justify-center px-3 text-sm font-bold"
              >
                Sign up
              </Link>
            </>
          )}
        </div>
        <BackToPortalButton />
      </div>
    </aside>
  );
}
