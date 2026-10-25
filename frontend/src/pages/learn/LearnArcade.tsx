import { useMemo, useState } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  Compass,
  Wrench,
  Search,
  CheckCircle2,
  Clock,
  Play,
  Box,
  Layers,
  X,
  Gamepad2,
} from "lucide-react";
import { fetchArcadeGamesApi } from "@/api/arcade";

const MODULE_TABS = [
  { key: "all", label: "All Modules" },
  { key: "1", label: "1 · Intro" },
  { key: "2", label: "2 · CDHS" },
  { key: "3", label: "3 · Power" },
  { key: "4", label: "4 · ADCS" },
  { key: "5", label: "5 · Comms" },
  { key: "6", label: "6 · Structures" },
  { key: "7", label: "7 · Thermal" },
  { key: "8", label: "8 · Launch & Ops" },
];

export default function LearnArcade() {
  const [mode, setMode] = useState<"explorer" | "engineer">("explorer");
  const [selectedModule, setSelectedModule] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  const { data: games = [], isLoading } = useQuery({
    queryKey: ["arcade-games"],
    queryFn: fetchArcadeGamesApi,
  });

  // Calculate stats based on active track
  const stats = useMemo(() => {
    let cleared = 0;
    let totalPoints = 0;
    let threeDCleared = 0;

    for (const g of games) {
      const modeData = mode === "engineer" ? g.engineer : g.explorer;
      if (modeData && modeData.passed) {
        cleared++;
        totalPoints += mode === "engineer" ? g.points_engineer : g.points_explorer;
        if (g.is_3d) threeDCleared++;
      }
    }

    const totalGames = games.length || 51;
    const percent = totalGames > 0 ? Math.round((cleared / totalGames) * 100) : 0;

    return { cleared, totalPoints, threeDCleared, totalGames, percent };
  }, [games, mode]);

  // Filter games based on tab and search
  const filteredGames = useMemo(() => {
    return games.filter((g) => {
      // Module filter
      if (selectedModule !== "all" && g.module_no !== selectedModule) {
        return false;
      }

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchesTitle = g.title.toLowerCase().includes(q);
        const matchesBlurb = g.blurb?.toLowerCase().includes(q) ?? false;
        const matchesModule = g.module_name.toLowerCase().includes(q);
        const matchesLesson =
          (g.lesson_explorer?.toLowerCase().includes(q) ?? false) ||
          (g.lesson_engineer?.toLowerCase().includes(q) ?? false);
        if (!matchesTitle && !matchesBlurb && !matchesModule && !matchesLesson) {
          return false;
        }
      }

      return true;
    });
  }, [games, selectedModule, searchQuery]);

  return (
    <div className="mx-auto max-w-[1360px] px-4 sm:px-6 lg:px-10 py-8 flex flex-col gap-8">
      {/* ── Top Hero & Stats ── */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-8 pt-2">
        <div className="flex flex-col gap-3 max-w-2xl">
          <h1 className="font-['Outfit'] text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-foreground">
            Satellite Engineering Simulators
          </h1>

          <p className="text-sm sm:text-base text-muted-foreground leading-relaxed">
            Experience the role of a satellite engineer. Solve problems across all 8 subsystems.
          </p>

          {/* Mode / Track Switcher */}
          <div className="flex items-center gap-2 pt-2">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mr-1">
              Active Track:
            </span>
            <div className="inline-flex rounded-full bg-card border border-border/80 dark:border-lms-accent-border/40 p-1">
              <button
                type="button"
                onClick={() => setMode("explorer")}
                className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                  mode === "explorer"
                    ? "bg-lms-cta text-white shadow-none"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Compass className="size-3.5" /> Explorer
              </button>
              <button
                type="button"
                onClick={() => setMode("engineer")}
                className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                  mode === "engineer"
                    ? "bg-lms-cta text-white shadow-none"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Wrench className="size-3.5" /> Engineer
              </button>
            </div>
          </div>
        </div>

        {/* Overall Progress Stats Box */}
        <div className="lms-card p-5 sm:p-6 min-w-[280px] lg:w-80 shrink-0 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Track Mastery
            </span>
            <span className="text-sm font-extrabold font-['Outfit'] tabular-nums text-lms-cta dark:text-lms-accent">{stats.percent}%</span>
          </div>

          {/* Progress bar */}
          <div className="h-2 w-full rounded-full bg-foreground/10 overflow-hidden">
            <div
              className="h-full bg-lms-cta dark:bg-lms-accent rounded-full transition-all duration-500"
              style={{ width: `${stats.percent}%` }}
            />
          </div>

          <div className="grid grid-cols-3 gap-2 pt-1 border-t border-border/50 dark:border-lms-accent-border/20 text-center">
            <div>
              <p className="text-lg font-extrabold font-['Outfit'] tabular-nums text-foreground">{stats.cleared}/{stats.totalGames}</p>
              <p className="text-[11px] text-muted-foreground font-medium">Cleared</p>
            </div>
            <div>
              <p className="text-lg font-extrabold font-['Outfit'] tabular-nums text-lms-cta dark:text-lms-accent">+{stats.totalPoints}</p>
              <p className="text-[11px] text-muted-foreground font-medium">Points</p>
            </div>
            <div>
              <p className="text-lg font-extrabold font-['Outfit'] tabular-nums text-foreground">{stats.threeDCleared}/11</p>
              <p className="text-[11px] text-muted-foreground font-medium">3D Sims</p>
            </div>
          </div>
        </div>
      </div>

      {/* ── Search & Filter Controls ── */}
      <div className="flex flex-col gap-4">
        {/* Module Category Tabs */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
          {MODULE_TABS.map((tab) => {
            const isSelected = selectedModule === tab.key;
            return (
              <button
                key={tab.key}
                onClick={() => setSelectedModule(tab.key)}
                className={`h-9 px-4 rounded-full text-xs font-semibold whitespace-nowrap transition-all cursor-pointer shrink-0 ${
                  isSelected
                    ? "bg-lms-cta text-white shadow-none"
                    : "bg-transparent text-muted-foreground border border-border/70 dark:border-lms-accent-border/30 hover:text-foreground hover:border-lms-accent"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Search Bar */}
        <div className="flex items-center justify-between gap-3">
          <div className="relative w-full max-w-md">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search missions, topics, or satellite systems..."
              className="w-full h-10 pl-9 pr-9 border border-border/80 dark:border-lms-accent-border bg-background text-foreground rounded-full text-xs sm:text-sm focus:outline-none focus:border-lms-cta dark:focus:border-lms-accent transition-colors"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
              >
                <X className="size-4" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Games Count & Result Bar ── */}
      <div className="flex items-center justify-between text-xs text-muted-foreground border-b border-border/50 dark:border-[#a880ff]/15 pb-2">
        <span>Showing {filteredGames.length} of {games.length} simulations</span>
        {searchQuery && (
          <button
            onClick={() => setSearchQuery("")}
            className="text-lms-cta dark:text-lms-accent hover:underline font-semibold cursor-pointer"
          >
            Clear search
          </button>
        )}
      </div>

      {/* ── Games Grid ── */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-64 rounded-xl lms-card animate-pulse opacity-40" />
          ))}
        </div>
      ) : filteredGames.length === 0 ? (
        <div className="lms-card p-12 text-center flex flex-col items-center justify-center gap-2">
          <Gamepad2 className="size-10 text-muted-foreground mb-1" />
          <p className="font-['Outfit'] text-base font-bold text-foreground">No simulations found</p>
          <p className="text-xs text-muted-foreground">
            Try adjusting your active track, module filter, or search keywords.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredGames.map((game) => {
            const modeData = mode === "engineer" ? game.engineer : game.explorer;
            const isPassed = modeData?.passed;
            const bestScore = modeData?.best_score ?? 0;
            const attemptsCount = modeData?.attempts_count ?? 0;
            const points = mode === "engineer" ? game.points_engineer : game.points_explorer;
            const timeLimit = mode === "engineer" ? game.time_engineer_seconds : game.time_explorer_seconds;
            const lesson = mode === "engineer" ? game.lesson_engineer : game.lesson_explorer;

            return (
              <article
                key={game.id}
                className="lms-card p-5 sm:p-6 flex flex-col justify-between gap-5 group transition-all"
              >
                <div>
                  {/* Top Badges */}
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-lms-cta-light text-lms-cta dark:text-lms-accent border border-lms-cta-border dark:border-lms-accent-border">
                        M{game.module_no} · {game.module_name}
                      </span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider bg-foreground/5 text-muted-foreground border border-border/60">
                        {game.kind}
                      </span>
                      {game.is_3d && (
                        <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold text-lms-cta dark:text-lms-accent bg-lms-cta-light border border-lms-cta-border dark:border-lms-accent-border">
                          <Box className="size-2.5" /> 3D
                        </span>
                      )}
                    </div>

                    {/* Completion Status Pill */}
                    {isPassed ? (
                      <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 shrink-0">
                        <CheckCircle2 className="size-3" /> {bestScore}/100
                      </span>
                    ) : attemptsCount > 0 ? (
                      <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold text-amber-500 dark:text-amber-400 bg-amber-500/10 border border-amber-500/30 shrink-0">
                        <Clock className="size-3" /> Retry ({bestScore})
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-medium text-muted-foreground border border-border/60 shrink-0">
                        Unplayed
                      </span>
                    )}
                  </div>

                  {/* Title & Description */}
                  <Link
                    to="/learn/arcade/$gameKey"
                    params={{ gameKey: game.game_key }}
                    search={{ mode }}
                    className="block"
                  >
                    <h3 className="font-['Outfit'] text-lg sm:text-xl font-bold text-foreground group-hover:text-lms-cta dark:group-hover:text-lms-accent transition-colors leading-snug">
                      {game.title}
                    </h3>
                  </Link>

                  <p className="text-xs sm:text-sm text-muted-foreground line-clamp-2 mt-2 leading-relaxed">
                    {game.blurb || "Interactive subsystem mission simulator."}
                  </p>

                  {/* Lesson Tag */}
                  {lesson && (
                    <p className="text-xs text-muted-foreground/80 mt-3 pt-3 border-t border-border/50 dark:border-lms-accent-border/15 truncate flex items-center gap-1.5">
                      <Layers className="size-3.5 shrink-0 text-muted-foreground/60" />
                      <span className="truncate">{lesson}</span>
                    </p>
                  )}
                </div>

                {/* Card Footer */}
                <div className="flex items-center justify-between gap-3 pt-3 mt-1 border-t border-border/50 dark:border-lms-accent-border/15">
                  <div className="flex items-center gap-2.5 text-xs">
                    <span className="tabular-nums font-medium text-muted-foreground flex items-center gap-1">
                      <Clock className="size-3 text-muted-foreground/70" /> {timeLimit}s
                    </span>
                    <span className="tabular-nums font-semibold text-lms-cta dark:text-lms-accent bg-lms-cta-light border border-lms-cta-border dark:border-lms-accent-border px-2 py-0.5 rounded text-[11px]">
                      +{points} pts
                    </span>
                  </div>

                  <Link
                    to="/learn/arcade/$gameKey"
                    params={{ gameKey: game.game_key }}
                    search={{ mode }}
                    className="lms-btn-primary inline-flex items-center gap-1.5 h-8 px-4 font-['Outfit'] text-xs font-semibold cursor-pointer"
                  >
                    <Play className="size-3" /> {isPassed ? "Replay" : "Launch"}
                  </Link>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
