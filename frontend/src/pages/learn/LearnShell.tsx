import { Outlet, useLocation } from "@tanstack/react-router";
import { LearnNav, type LearnNavActive } from "./LearnNav";

/**
 * The student shell (LMS D1) — deliberately NOT the portal's `AppShell`.
 *
 * Students are a separate surface that happens to ship in the same Vite app:
 * own navbar, own layout, no sidebar, no role switcher, no portal chrome. The
 * precedent is `ApplicantShell` (router.tsx:174-182), which does the same thing
 * for applicants.
 *
 * ⚠ Import discipline (LMS D1): nothing under `pages/learn/**` may import from
 * `pages/operations/**` or `components/layout/Sidebar`. Shared `components/ui/**`
 * and `lib/**` are fine (LearnNav pulls ThemeToggle and DomainIcon from there —
 * neither is Sidebar.tsx itself).
 *
 * Mobile-first: students are on phones. Content is full-bleed; each page owns
 * its own max-width/padding (desktop frames run to 1440px per the design).
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
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      <LearnNav active={active} />
      {/* pb-28 not pb-20: staff get a second row (Back to portal) under the
          tab icons, and the fixed bar's real height varies by role — sized
          for that taller case so nothing sits behind it either way. */}
      <main className="flex-1 pb-28 md:pb-0">
        <Outlet />
      </main>
    </div>
  );
}
