import { Outlet, useNavigate } from "@tanstack/react-router";
import { useAuth } from "@/context/AuthContext";
import { GraduationCap, LogOut } from "lucide-react";

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
 * and `lib/**` are fine. Holding that line is what keeps extracting this into
 * its own Vite app a folder move rather than an untangling job.
 *
 * Mobile-first: students are on phones.
 */
export function LearnShell() {
  const { currentUser, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    void navigate({ to: "/learn/login" });
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      <header className="sticky top-0 z-10 border-b border-border bg-card">
        <div className="mx-auto max-w-3xl px-4 h-14 flex items-center justify-between gap-3">
          <button
            onClick={() => void navigate({ to: "/learn" })}
            className="flex items-center gap-2 font-semibold cursor-pointer"
          >
            <GraduationCap size={20} className="text-primary" />
            <span>Learn</span>
          </button>

          {currentUser && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground hidden sm:inline">
                {currentUser.full_name || currentUser.email}
              </span>
              <button
                onClick={() => void handleLogout()}
                className="p-2 rounded-lg text-muted-foreground hover:text-foreground cursor-pointer"
                aria-label="Log out"
              >
                <LogOut size={16} />
              </button>
            </div>
          )}
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-3xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
