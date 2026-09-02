import { Link } from "@tanstack/react-router";
import { Search, Zap } from "lucide-react";
import { DomainIcon } from "@/components/ui/DomainIcon";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { cn } from "@/lib/utils";
import { NAV_ITEMS, type LearnNavActive } from "./nav/navItems";
import { BackToPortalButton, LearnNotificationsBell, LearnProfileMenu } from "./nav/LearnNavShared";
import { useBoardProgress } from "./nav/boardProgressContext";

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
  const { progress } = useBoardProgress();
  const pct = progress && progress.total > 0 ? Math.round((100 * progress.liveCount) / progress.total) : 0;

  return (
    <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 flex-col border-r border-border bg-background md:flex">
      <div className="flex h-20 shrink-0 items-center gap-2 border-b border-border px-4">
        <Link to="/learn" aria-label="SpacePoint Learn" className="flex flex-1 items-center gap-2 overflow-hidden">
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

      <nav className="flex flex-1 flex-col space-y-2 overflow-y-auto px-4 py-6">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = item.key === active;
          return (
            <Link
              key={item.key}
              to={item.to}
              className={cn(
                "flex items-center gap-3 rounded-xl px-4 py-3 text-sm transition-all",
                isActive
                  ? "border border-primary/30 bg-primary/10 font-semibold text-primary"
                  : "border border-transparent text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
              )}
            >
              <Icon className="h-5 w-5 shrink-0" />
              <span className="truncate">{item.label}</span>
            </Link>
          );
        })}

        <div className="mt-auto flex flex-col gap-3 pt-4">
          {progress && (
            <div className="flex flex-col gap-1.5 rounded-xl border border-primary/20 bg-primary/5 px-4 py-3">
              <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
                <Zap className="size-3" /> Board power
              </div>
              <div className="text-[11px] text-muted-foreground">
                {progress.liveCount} of {progress.total} traces live
              </div>
              <div className="h-[6px] rounded-full bg-border overflow-hidden">
                <div
                  className="h-full rounded-full bg-primary transition-[width] duration-300"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )}

          <div className="flex items-center gap-1 border-t border-border pt-3">
            <ThemeToggle />
            <LearnNotificationsBell />
            <LearnProfileMenu />
          </div>
          <BackToPortalButton />
        </div>
      </nav>
    </aside>
  );
}
