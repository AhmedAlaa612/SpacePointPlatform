import { useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { ChevronDown, LogOut, Moon, Sun } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { ROLE_DOMAIN, ROLE_LABEL, type Role } from "@/types/shared";
import { cn } from "@/lib/utils";
import { roleLogo } from "@/lib/logos";
import { Button } from "@/components/ui/button";

function toggleTheme() {
  const isDark = document.documentElement.classList.toggle("dark");
  localStorage.setItem("theme", isDark ? "dark" : "light");
}

interface NavLink {
  to: string;
  label: string;
  exact?: boolean;
}

export function Navbar() {
  const { user, roles, activeRole, setActiveRole, logout, isAdmin } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  if (!user) return null;

  const domain = activeRole ? ROLE_DOMAIN[activeRole] : null;

  // Per-domain nav links. Admin has no dedicated domain UI yet (Phase 5), so
  // they get the interns nav for now. Other domains are added as phases land.
  const links: NavLink[] =
    domain === "interns" || isAdmin
      ? [
          { to: "/interns", label: "Board", exact: true },
          { to: "/interns/tracker", label: "Tracker" },
          { to: "/interns/calendar", label: "Calendar" },
          { to: "/interns/leaderboard", label: "Leaderboard" },
          { to: "/interns/profile", label: "Profile" },
          ...(isAdmin ? [{ to: "/interns/admin", label: "Admin" }] : []),
        ]
      : [];

  function chooseRole(role: Role) {
    setActiveRole(role);
    setMenuOpen(false);
    void navigate({ to: "/" });
  }

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-card/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-4 px-4">
        <div className="flex items-center gap-4">
          <Link to="/" className="flex shrink-0 items-center" aria-label="SpacePoint home">
            <img src={roleLogo(activeRole)} alt="SpacePoint" className="h-7 w-auto" />
          </Link>
          <nav className="hidden items-center gap-1 md:flex">
            {links.map((l) => (
              <Link
                key={l.to}
                to={l.to}
                activeOptions={{ exact: l.exact ?? false }}
                className="rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                activeProps={{ className: "bg-muted text-foreground" }}
              >
                {l.label}
              </Link>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-2">
          {roles.length > 1 && activeRole && (
            <div className="relative">
              <button
                type="button"
                onClick={() => setMenuOpen((o) => !o)}
                className="flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground hover:bg-muted"
              >
                {ROLE_LABEL[activeRole]}
                <ChevronDown className="h-4 w-4" />
              </button>
              {menuOpen && (
                <ul className="absolute right-0 mt-1 w-44 overflow-hidden rounded-md border border-border bg-popover py-1 shadow-lg">
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

          <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
            <Sun className="h-5 w-5 dark:hidden" />
            <Moon className="hidden h-5 w-5 dark:block" />
          </Button>

          <Button variant="ghost" size="icon" onClick={() => void logout()} aria-label="Log out">
            <LogOut className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </header>
  );
}
