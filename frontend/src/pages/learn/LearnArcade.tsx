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
          <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-foreground">
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
            <div className="inline-flex rounded-xl bg-card border border-border p-1">
              <button
                type="button"
                onClick={() => setMode("explorer")}
                className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  mode === "explorer"
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Compass className="size-3.5" /> Explorer
              </button>
              <button
                type="button"
                onClick={() => setMode("engineer")}
                className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  mode === "engineer"
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Wrench className="size-3.5" /> Engineer
              </button>
            </div>
          </div>
        </div>

        {/* Overall Progress Stats Box */}
        <div className="flex flex-col gap-4 p-5 sm:p-6 rounded-2xl bg-card border border-border min-w-[280px] lg:w-80 shrink-0">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Track Mastery
            </span>
            <span className="text-sm font-bold font-display tabular-nums text-primary">{stats.percent}%</span>
          </div>

          {/* Progress bar */}
          <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-500"
              style={{ width: `${stats.percent}%` }}
            />
          </div>

          <div className="grid grid-cols-3 gap-2 pt-1 border-t border-border/50 text-center">
            <div>
              <p className="text-lg font-bold font-display tabular-nums text-foreground">{stats.cleared}/{stats.totalGames}</p>
              <p className="text-[11px] text-muted-foreground font-medium">Cleared</p>
            </div>
            <div>
              <p className="text-lg font-bold font-display tabular-nums text-amber-400">+{stats.totalPoints}</p>
              <p className="text-[11px] text-muted-foreground font-medium">Points</p>
            </div>
            <div>
              <p className="text-lg font-bold font-display tabular-nums text-foreground">{stats.threeDCleared}/11</p>
              <p className="text-[11px] text-muted-foreground font-medium">3D Sims</p>
            </div>
          </div>
        </div>
      </div>

      {/* ── Search & Filter Controls ── */}
      <div className="flex flex-col gap-4">
        {/* Module Category Tabs */}
        <div className="flex items-center gap-2.5 overflow-x-auto pb-2 scrollbar-none">
          {MODULE_TABS.map((tab) => {
            const isSelected = selectedModule === tab.key;
            return (
              <button
                key={tab.key}
                onClick={() => setSelectedModule(tab.key)}
                className={`px-5 py-2.5 rounded-2xl text-sm font-semibold whitespace-nowrap transition-all border shrink-0 ${
                  isSelected
                    ? "bg-foreground text-background border-foreground shadow-md font-bold"
                    : "bg-card text-muted-foreground border-border hover:border-foreground/30 hover:text-foreground"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Search Bar */}
        <div className="flex items-center justify-between gap-3">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search missions, topics, or satellite systems..."
              className="w-full h-11 pl-10 pr-9 bg-card border border-border text-foreground rounded-xl text-sm placeholder:text-muted-foreground/70 focus:outline-none focus:border-primary transition-colors"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Games Count & Result Bar ── */}
      <div className="flex items-center justify-between text-xs text-muted-foreground border-b border-border/50 pb-2">
        <span>Showing {filteredGames.length} of {games.length} simulations</span>
        {searchQuery && (
          <button
            onClick={() => setSearchQuery("")}
            className="text-primary hover:underline font-medium"
          >
            Clear search
          </button>
        )}
      </div>

      {/* ── Games Grid ── */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-64 rounded-2xl bg-card border border-border animate-pulse" />
          ))}
        </div>
      ) : filteredGames.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-12 text-center rounded-2xl border border-dashed border-border bg-card/40">
          <Gamepad2 className="size-10 text-muted-foreground mb-3" />
          <h3 className="font-display text-base font-semibold text-foreground">No simulations found</h3>
          <p className="text-xs text-muted-foreground mt-1 max-w-sm">
            Try adjusting your track, module filter, or search keywords.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredGames.map((game) => {
            const modeData = mode === "engineer" ? game.engineer : game.explorer;
            const isPassed = modeData?.passed;
            const bestScore = modeData?.best_score ?? 0;
            const attemptsCount = modeData?.attempts_count ?? 0;
            const points = mode === "engineer" ? game.points_engineer : game.points_explorer;
            const timeLimit = mode === "engineer" ? game.time_engineer_seconds : game.time_explorer_seconds;
            const lesson = mode === "engineer" ? game.lesson_engineer : game.lesson_explorer;

            return (
              <div
                key={game.id}
                className="group relative flex flex-col justify-between rounded-2xl border border-border bg-card p-5 hover:border-primary/50 transition-all hover:shadow-lg flex flex-col justify-between"
              >
                <div>
                  {/* Top Badges */}
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-primary/10 text-primary border border-primary/20">
                        M{game.module_no} · {game.module_name}
                      </span>
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-muted text-muted-foreground border border-border">
                        {game.kind}
                      </span>
                      {game.is_3d && (
                        <span className="flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-bold text-primary bg-primary/10 border border-primary/25">
                          <Box className="size-2.5" /> 3D
                        </span>
                      )}
                    </div>

                    {/* Completion Status Pill */}
                    {isPassed ? (
                      <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/25 shrink-0">
                        <CheckCircle2 className="size-3" /> {bestScore}/100
                      </span>
                    ) : attemptsCount > 0 ? (
                      <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold text-amber-400 bg-amber-500/10 border border-amber-500/25 shrink-0">
                        <Clock className="size-3" /> Retry ({bestScore})
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-medium text-muted-foreground/70 border border-border/50 shrink-0">
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
                    <h3 className="font-display text-lg font-bold text-foreground group-hover:text-primary transition-colors flex items-center gap-2">
                      {game.title}
                    </h3>
                  </Link>

                  <p className="text-xs text-muted-foreground line-clamp-2 mt-1.5 leading-relaxed">
                    {game.blurb || "Interactive subsystem mission simulator."}
                  </p>

                  {/* Lesson Tag */}
                  {lesson && (
                    <p className="text-[11px] text-muted-foreground/75 mt-3 pt-2.5 border-t border-border/40 truncate flex items-center gap-1">
                      <Layers className="size-3 shrink-0 text-muted-foreground/60" />
                      <span className="truncate">{lesson}</span>
                    </p>
                  )}
                </div>

                {/* Card Footer */}
                <div className="flex items-center justify-between gap-3 pt-4 mt-4 border-t border-border/60">
                  <div className="flex items-center gap-3 text-xs">
                    <span className="tabular-nums font-medium text-muted-foreground flex items-center gap-1">
                      <Clock className="size-3" /> {timeLimit}s
                    </span>
                    <span className="tabular-nums font-semibold text-amber-400 bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded text-[11px]">
                      +{points} pts
                    </span>
                  </div>

                  <Link
                    to="/learn/arcade/$gameKey"
                    params={{ gameKey: game.game_key }}
                    search={{ mode }}
                    className="inline-flex items-center gap-1.5 h-8 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition-opacity"
                  >
                    <Play className="size-3" /> {isPassed ? "Replay" : "Launch"}
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
