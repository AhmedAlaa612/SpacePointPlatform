import { Link } from "@tanstack/react-router"

export function SessionsSubNav({ activeTab }: { activeTab: "my" | "available" | "calendar" }) {
  return (
    <div className="flex items-center gap-1.5 border-b border-border pb-2 mb-4 overflow-x-auto">
      <Link
        to="/instructors/my-sessions"
        className={`px-3.5 py-1.5 text-xs font-semibold rounded-xl transition-colors whitespace-nowrap ${
          activeTab === "my"
            ? "bg-primary text-primary-foreground shadow-xs"
            : "text-muted-foreground hover:bg-muted hover:text-foreground"
        }`}
      >
        My Assigned Sessions
      </Link>
      <Link
        to="/instructors/available-sessions"
        className={`px-3.5 py-1.5 text-xs font-semibold rounded-xl transition-colors whitespace-nowrap ${
          activeTab === "available"
            ? "bg-primary text-primary-foreground shadow-xs"
            : "text-muted-foreground hover:bg-muted hover:text-foreground"
        }`}
      >
        Available Sessions
      </Link>
      <Link
        to="/sessions/calendar"
        className={`px-3.5 py-1.5 text-xs font-semibold rounded-xl transition-colors whitespace-nowrap ${
          activeTab === "calendar"
            ? "bg-primary text-primary-foreground shadow-xs"
            : "text-muted-foreground hover:bg-muted hover:text-foreground"
        }`}
      >
        Sessions Calendar
      </Link>
    </div>
  )
}
