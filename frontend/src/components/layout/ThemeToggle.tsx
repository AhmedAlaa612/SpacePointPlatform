import { Moon, Sun } from "lucide-react";

export function toggleTheme() {
  const isDark = document.documentElement.classList.toggle("dark");
  localStorage.setItem("theme", isDark ? "dark" : "light");
}

export function ThemeToggle({ className }: { className?: string }) {
  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={
        className ??
        "rounded-xl p-2.5 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground"
      }
      aria-label="Toggle theme"
    >
      <Sun size={20} className="dark:hidden" />
      <Moon size={20} className="hidden dark:block" />
    </button>
  );
}
