import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Trophy, Users, BookOpen, Rocket, CheckCircle2, HelpCircle, Gamepad2, Award } from "lucide-react";
import { getLeaderboardApi, fetchMyChecklists } from "@/api/lms";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";

function getInitials(name?: string | null): string {
  if (!name) return "EX";
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

export default function LearnLeaderboard() {
  const { currentUser, user } = useAuth();
  const isAuthed = !!user;

  // Cohort context if student belongs to cohorts
  const { data: myChecklists = [] } = useQuery({
    queryKey: ["lms-my-checklists"],
    queryFn: fetchMyChecklists,
    enabled: isAuthed,
  });

  const availableCohorts = useMemo(() => {
    const list: { id: string; name: string }[] = [];
    const seen = new Set<string>();
    for (const c of myChecklists) {
      if (c.cohort_id && !seen.has(c.cohort_id)) {
        seen.add(c.cohort_id);
        list.push({ id: c.cohort_id, name: c.cohort_name || c.name });
      }
    }
    return list;
  }, [myChecklists]);

  const [scope, setScope] = useState<"global" | "cohort">("global");
  const [selectedCohortId, setSelectedCohortId] = useState<string | undefined>(undefined);

  const activeCohortId = selectedCohortId || availableCohorts[0]?.id;

  const { data: rows = [], isLoading } = useQuery({
    queryKey: ["lms-leaderboard", scope, scope === "cohort" ? activeCohortId : "all"],
    queryFn: () => getLeaderboardApi(scope, scope === "cohort" ? activeCohortId : undefined),
  });

  // Current user's row in this leaderboard
  const myEntry = useMemo(() => {
    if (!currentUser?.id) return null;
    return rows.find((r) => r.user_id === currentUser.id) || null;
  }, [rows, currentUser]);

  // Top 3 for podium
  const topThree = useMemo(() => {
    const first = rows[0] || null;
    const second = rows[1] || null;
    const third = rows[2] || null;
    return { first, second, third };
  }, [rows]);

  // Remaining ranks (4+)
  const restRows = useMemo(() => rows.slice(3), [rows]);

  return (
    <div className="mx-auto max-w-[1240px] px-6 sm:px-10 lg:px-12 py-10 sm:py-16 flex flex-col gap-10 sm:gap-12">
      {/* Page Header */}
      <div>
        <h1 className="font-display text-[38px] sm:text-[46px] lg:text-[48px] font-extrabold leading-[48px] tracking-[-1.2px] text-foreground">
          Leaderboard
        </h1>
      </div>

      {/* Your Standing Banner */}
      {isAuthed && (
        <section className="lms-card p-6 sm:p-8 grid grid-cols-1 sm:grid-cols-3 gap-6 sm:gap-8 items-center">
          <div className="flex flex-col gap-1.5 border-b sm:border-b-0 sm:border-r border-border/40 pb-5 sm:pb-0 sm:pr-6">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              Your Rank
            </span>
            <div className="flex items-baseline gap-2">
              <strong className="font-display text-3xl sm:text-4xl font-extrabold text-foreground tracking-tight">
                {myEntry ? `#${myEntry.rank}` : "—"}
              </strong>
              <span className="text-xs text-muted-foreground">
                {myEntry ? `of ${rows.length} ranked` : "Not ranked yet"}
              </span>
            </div>
            <span className="text-[11px] text-muted-foreground">
              {myEntry ? "Ranked explorer" : "Complete quizzes and modules to enter the board"}
            </span>
          </div>

          <div className="flex items-center gap-4 border-b sm:border-b-0 sm:border-r border-border/40 pb-5 sm:pb-0 sm:pr-6">
            <div className="size-14 rounded-full border-2 border-lms-accent/50 bg-lms-cta-light flex items-center justify-center font-display font-extrabold text-lms-cta dark:text-lms-accent text-lg shrink-0">
              {getInitials(currentUser?.nickname || currentUser?.full_name)}
            </div>
            <div className="flex flex-col min-w-0">
              <strong className="font-display text-lg font-bold text-foreground truncate">
                {currentUser?.nickname || currentUser?.full_name || "Explorer"}
              </strong>
              {currentUser?.nickname && currentUser?.full_name && (
                <span className="text-xs text-muted-foreground truncate">
                  {currentUser.full_name}
                </span>
              )}
              <span className="text-[11px] text-lms-cta dark:text-lms-accent font-semibold mt-0.5">
                {scope === "global" ? "Global standings" : "Program standings"}
              </span>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              Total Points
            </span>
            <strong className="font-display text-3xl sm:text-4xl font-extrabold text-foreground tracking-tight">
              {(myEntry?.points ?? 0).toLocaleString()} <span className="text-xs font-bold text-lms-cta dark:text-lms-accent">PTS</span>
            </strong>
            <span className="text-[11px] text-muted-foreground">
              Earn points for lessons, checks, and milestones
            </span>
          </div>
        </section>
      )}

      {/* Scope Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2.5 sm:gap-3 flex-wrap">
          <button
            onClick={() => setScope("global")}
            className={cn(
              "h-10 px-5 rounded-full text-xs sm:text-sm font-bold transition-all cursor-pointer inline-flex items-center gap-2 select-none",
              scope === "global"
                ? "bg-lms-cta text-white shadow-none"
                : "bg-transparent text-muted-foreground border border-border/60 dark:border-lms-accent-border hover:text-foreground hover:border-lms-accent"
            )}
          >
            <Users className="size-4" />
            All learners
            {scope === "global" && (
              <span className="font-mono text-[11px] px-1.5 py-0.5 rounded-full bg-white/20 text-white">
                {rows.length}
              </span>
            )}
          </button>

          {availableCohorts.length > 0 && (
            <button
              onClick={() => setScope("cohort")}
              className={cn(
                "h-10 px-5 rounded-full text-xs sm:text-sm font-bold transition-all cursor-pointer inline-flex items-center gap-2 select-none",
                scope === "cohort"
                  ? "bg-lms-cta text-white shadow-none"
                  : "bg-transparent text-muted-foreground border border-border/60 dark:border-lms-accent-border hover:text-foreground hover:border-lms-accent"
              )}
            >
              <Rocket className="size-4" />
              My program
              {scope === "cohort" && (
                <span className="font-mono text-[11px] px-1.5 py-0.5 rounded-full bg-white/20 text-white">
                  {rows.length}
                </span>
              )}
            </button>
          )}
        </div>

        {scope === "cohort" && availableCohorts.length > 1 && (
          <select
            value={activeCohortId}
            onChange={(e) => setSelectedCohortId(e.target.value)}
            className="h-10 px-3 rounded-lg border border-border/60 dark:border-[#a880ff]/30 bg-background text-xs font-semibold text-foreground focus:outline-none focus:border-[#A880FF]"
          >
            {availableCohorts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Main Content Layout */}
      {isLoading ? (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          <div className="lg:col-span-8 flex flex-col gap-6">
            <div className="h-48 rounded-xl bg-muted/40 animate-pulse" />
            <div className="h-64 rounded-xl bg-muted/40 animate-pulse" />
          </div>
          <div className="lg:col-span-4">
            <div className="h-64 rounded-xl bg-muted/40 animate-pulse" />
          </div>
        </div>
      ) : rows.length === 0 ? (
        <div className="lms-card p-12 text-center flex flex-col items-center gap-3">
          <Trophy className="size-10 text-muted-foreground/40" />
          <h3 className="font-display text-lg font-bold text-foreground">No rankings yet</h3>
          <p className="text-xs sm:text-sm text-muted-foreground max-w-sm">
            Be the first to score points by completing course lessons and quizzes.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Standings Area */}
          <div className="lg:col-span-8 flex flex-col gap-8">
            {/* Top 3 Podium */}
            <div className="grid grid-cols-3 gap-3 sm:gap-4 items-end pt-6">
              {/* 2nd Place */}
              {topThree.second ? (
                <div className="lms-card p-4 sm:p-6 flex flex-col items-center text-center gap-2.5 pb-6">
                  <div className="size-12 sm:size-14 rounded-full border-2 border-zinc-400 bg-zinc-400/10 flex items-center justify-center font-display font-bold text-zinc-300 text-sm sm:text-base">
                    {getInitials(topThree.second.display_name)}
                  </div>
                  <span className="font-display font-extrabold text-sm sm:text-base text-zinc-400">
                    #2
                  </span>
                  <h3 className="font-display font-bold text-sm sm:text-base text-foreground truncate w-full">
                    {topThree.second.display_name}
                  </h3>
                  <strong className="font-display text-xs sm:text-sm font-bold text-foreground/90">
                    {topThree.second.points.toLocaleString()} pts
                  </strong>
                </div>
              ) : (
                <div className="lms-card p-4 sm:p-6 opacity-30 flex flex-col items-center justify-center min-h-[140px] text-xs text-muted-foreground">
                  —
                </div>
              )}

              {/* 1st Place */}
              {topThree.first ? (
                <div className="lms-card p-4 sm:p-6 flex flex-col items-center text-center gap-2.5 pb-8 relative -translate-y-2 border-lms-accent">
                  <div className="absolute -top-3.5 px-3 py-0.5 rounded-full bg-lms-cta border border-lms-accent text-[11px] font-bold text-white flex items-center gap-1 shadow-sm">
                    <Trophy className="size-3 text-lms-accent" />
                    Leader
                  </div>
                  <div className="size-14 sm:size-16 rounded-full border-2 border-lms-accent bg-lms-cta-light flex items-center justify-center font-display font-extrabold text-lms-cta dark:text-lms-accent text-base sm:text-lg mt-1">
                    {getInitials(topThree.first.display_name)}
                  </div>
                  <span className="font-display font-extrabold text-base sm:text-lg text-lms-cta dark:text-lms-accent">
                    #1
                  </span>
                  <h3 className="font-display font-bold text-sm sm:text-base text-foreground truncate w-full">
                    {topThree.first.display_name}
                  </h3>
                  <strong className="font-display text-sm sm:text-base font-extrabold text-foreground">
                    {topThree.first.points.toLocaleString()} pts
                  </strong>
                </div>
              ) : null}

              {/* 3rd Place */}
              {topThree.third ? (
                <div className="lms-card p-4 sm:p-6 flex flex-col items-center text-center gap-2.5 pb-5">
                  <div className="size-12 sm:size-14 rounded-full border-2 border-amber-600/70 bg-amber-600/10 flex items-center justify-center font-display font-bold text-amber-500 text-sm sm:text-base">
                    {getInitials(topThree.third.display_name)}
                  </div>
                  <span className="font-display font-extrabold text-sm sm:text-base text-amber-600">
                    #3
                  </span>
                  <h3 className="font-display font-bold text-sm sm:text-base text-foreground truncate w-full">
                    {topThree.third.display_name}
                  </h3>
                  <strong className="font-display text-xs sm:text-sm font-bold text-foreground/90">
                    {topThree.third.points.toLocaleString()} pts
                  </strong>
                </div>
              ) : (
                <div className="lms-card p-4 sm:p-6 opacity-30 flex flex-col items-center justify-center min-h-[140px] text-xs text-muted-foreground">
                  —
                </div>
              )}
            </div>

            {/* Ranking Table (Ranks 4+) */}
            {restRows.length > 0 && (
              <div className="lms-card overflow-hidden">
                <div className="px-6 py-4 border-b border-border/40 grid grid-cols-12 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                  <span className="col-span-2">Rank</span>
                  <span className="col-span-7">Learner</span>
                  <span className="col-span-3 text-right">Points</span>
                </div>
                <div className="divide-y divide-border/20">
                  {restRows.map((person) => {
                    const isMe = person.user_id === currentUser?.id;
                    return (
                      <div
                        key={person.user_id}
                        className={cn(
                          "px-6 py-4 grid grid-cols-12 items-center transition-colors",
                          isMe
                            ? "bg-lms-cta-light border-l-4 border-l-lms-accent"
                            : "hover:bg-white/[0.02]"
                        )}
                      >
                        <span className="col-span-2 font-display text-sm font-extrabold text-muted-foreground">
                          #{person.rank}
                        </span>
                        <div className="col-span-7 flex items-center gap-3 min-w-0 pr-2">
                          <div className="size-8 rounded-full border border-border/60 bg-white/5 flex items-center justify-center text-xs font-bold text-foreground shrink-0">
                            {getInitials(person.display_name)}
                          </div>
                          <span className="font-semibold text-xs sm:text-sm text-foreground truncate">
                            {person.display_name}
                            {isMe && (
                              <span className="ml-2 text-[10px] uppercase font-bold text-lms-cta dark:text-lms-accent px-1.5 py-0.5 rounded border border-lms-accent-border bg-lms-cta-light">
                                You
                              </span>
                            )}
                          </span>
                        </div>
                        <span className="col-span-3 text-right font-display text-xs sm:text-sm font-bold text-foreground">
                          {person.points.toLocaleString()} pts
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Right Sidebar: How points work */}
          <aside className="lg:col-span-4 flex flex-col gap-6">
            <div className="lms-card p-6 sm:p-7 flex flex-col gap-5">
              <div className="flex items-center gap-2.5">
                <Award className="size-5 text-[#A880FF]" />
                <h2 className="font-display text-lg font-bold text-foreground">
                  How points work
                </h2>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Points reward progress and understanding across your enrolled space missions and courses.
              </p>

              <div className="flex flex-col gap-3 pt-2">
                <div className="flex items-center justify-between p-3 rounded-lg border border-border/40 bg-white/[0.02]">
                  <div className="flex items-center gap-2.5">
                    <Rocket className="size-4 text-[#A880FF]" />
                    <span className="text-xs font-semibold text-foreground">
                      Space missions
                    </span>
                  </div>
                  <strong className="font-display text-xs font-extrabold text-[#A880FF]">
                    +100–300
                  </strong>
                </div>

                <div className="flex items-center justify-between p-3 rounded-lg border border-border/40 bg-white/[0.02]">
                  <div className="flex items-center gap-2.5">
                    <BookOpen className="size-4 text-[#A880FF]" />
                    <span className="text-xs font-semibold text-foreground">
                      Course modules
                    </span>
                  </div>
                  <strong className="font-display text-xs font-extrabold text-[#A880FF]">
                    +100
                  </strong>
                </div>

                <div className="flex items-center justify-between p-3 rounded-lg border border-border/40 bg-white/[0.02]">
                  <div className="flex items-center gap-2.5">
                    <Gamepad2 className="size-4 text-[#A880FF]" />
                    <span className="text-xs font-semibold text-foreground">
                      Mission Arcade
                    </span>
                  </div>
                  <strong className="font-display text-xs font-extrabold text-[#A880FF]">
                    +50–100
                  </strong>
                </div>

                <div className="flex items-center justify-between p-3 rounded-lg border border-border/40 bg-white/[0.02]">
                  <div className="flex items-center gap-2.5">
                    <CheckCircle2 className="size-4 text-[#A880FF]" />
                    <span className="text-xs font-semibold text-foreground">
                      Program task
                    </span>
                  </div>
                  <strong className="font-display text-xs font-extrabold text-[#A880FF]">
                    +50
                  </strong>
                </div>
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
