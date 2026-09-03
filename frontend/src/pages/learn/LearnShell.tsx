import { Outlet, useLocation } from "@tanstack/react-router";
import { LearnSidebar } from "./LearnSidebar";
import { LearnMobileTabBar } from "./nav/LearnMobileTabBar";
import type { LearnNavActive } from "./nav/navItems";

/**
 * The student shell (LMS D1) — deliberately NOT the portal's `AppShell`.
 *
 * Students are a separate surface that happens to ship in the same Vite app:
 * own nav, own layout, no role switcher, no portal chrome. The precedent is
 * `ApplicantShell` (router.tsx:174-182), which does the same thing for
 * applicants.
 *
 * ⚠ Import discipline (LMS D1): nothing under `pages/learn/**` may import from
 * `pages/operations/**` or `components/layout/Sidebar` (the *portal's* one).
 * Shared `components/ui/**` and `lib/**` are fine — `LearnSidebar` is its own,
 * separate component under `pages/learn/**`, not a reuse of that one (see its
 * own docblock for why it can't be).
 *
 * Desktop (2026-09, Roadmap board redesign): a fixed `LearnSidebar` replaces
 * the old horizontal navbar — sized to match the portal's own sidebar
 * exactly (w-64, same spacing — client's own ask) rather than the design
 * wireframe's narrower 196px. The content column is offset by that same
 * width. Mobile is unchanged: still the bottom tab bar, full-bleed content
 * (desktop frames run to 1440px per the design).
 */
export function LearnShell() {
  const { pathname } = useLocation();
  const active: LearnNavActive =
    pathname.startsWith("/learn/catalog") ? "catalog"
    : pathname.startsWith("/learn/missions") ? "missions"
    : pathname.startsWith("/learn/paths") ? "paths"
    : pathname.startsWith("/learn/checklists") ? "checklists"
    : pathname.startsWith("/learn/my-courses") ? "my-courses"
    : pathname.startsWith("/learn/games") ? "games"
    : pathname.startsWith("/learn/leaderboard") ? "leaderboard"
    : pathname.startsWith("/learn/profile") ? "profile"
    : "home";

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col md:flex-row">
      <LearnSidebar active={active} />
      <LearnMobileTabBar active={active} />
      {/* pb-28 not pb-20 on mobile: staff get a second row (Back to
          portal) under the tab icons, and the fixed bar's real height
          varies by role — sized for that taller case so nothing sits
          behind it either way. md:ml-64 matches LearnSidebar's own
          width, offsetting for the fixed desktop sidebar instead of a
          static top navbar. min-w-0 is required alongside flex-1: a
          flex item's default min-width is `auto` (its content's
          intrinsic width), not 0 — without this, any wide-ish content
          a page renders (a hero image, a horizontally-scrolling row)
          refuses to shrink to the available width and blows out the
          whole layout instead of clipping/scrolling inside itself,
          which is what produced the page-wide horizontal scrollbar.
          print:ml-0/pb-0 to match the sidebar/tab bar going print:hidden
          below — a page's own "Print report" button (e.g. the design
          mission's Report tab) should print just that content, not the
          shell chrome around it, which a fixed-position "cover it on
          screen" trick doesn't reliably keep off the printed page. */}
      <main className="flex-1 min-w-0 pb-28 md:pb-0 md:ml-64 print:ml-0 print:pb-0">
        <Outlet />
      </main>
    </div>
  );
}
