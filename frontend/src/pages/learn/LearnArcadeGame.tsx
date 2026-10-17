import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Compass, Wrench, Box } from "lucide-react";
import { fetchArcadeGamesApi, submitArcadeAttemptApi, type ArcadeDebriefNote } from "@/api/arcade";
import { useToast } from "@/components/ui/toast";

export default function LearnArcadeGame() {
  const navigate = useNavigate();
  const { gameKey } = useParams({ strict: false }) as { gameKey: string };
  const search = useSearch({ strict: false }) as {
    mode?: "explorer" | "engineer";
    program?: string;
    itemId?: string;
  };
  const mode = search.mode === "engineer" ? "engineer" : "explorer";
  const assignmentId = search.program;
  const itemId = search.itemId;

  const queryClient = useQueryClient();
  const toast = useToast();
  const [justPassed, setJustPassed] = useState(false);

  const { data: games = [] } = useQuery({
    queryKey: ["arcade-games"],
    queryFn: fetchArcadeGamesApi,
  });

  const currentGame = useMemo(() => {
    return games.find((g) => g.game_key === gameKey) ?? null;
  }, [games, gameKey]);

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.origin !== window.location.origin || !e.data || e.data.type !== "SPMA_GAME_FINISHED") return;
      const payload = e.data as {
        gameKey: string;
        mode: "explorer" | "engineer";
        score: number;
        passed: boolean;
        accuracy: number;
        elapsedSeconds: number;
        notes: ArcadeDebriefNote[];
      };
      void submitArcadeAttemptApi(payload.gameKey, {
        mode: payload.mode,
        score: payload.score,
        accuracy: payload.accuracy,
        passed: payload.passed,
        elapsed_seconds: payload.elapsedSeconds,
        notes: payload.notes ?? [],
        assignment_id: assignmentId ?? null,
        program_item_id: itemId ?? null,
      }).then((res) => {
        if (res.passed) {
          setJustPassed(true);
          toast.success(
            res.points_awarded > 0
              ? `Mission passed! +${res.points_awarded} pts`
              : "Mission passed! Program step cleared.",
          );
        }
        void queryClient.invalidateQueries({ queryKey: ["arcade-games"] });
        if (assignmentId) {
          void queryClient.invalidateQueries({ queryKey: ["lms-checklist", assignmentId] });
        }
      });
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [assignmentId, itemId, queryClient, toast]);

  const modeData = mode === "engineer" ? currentGame?.engineer : currentGame?.explorer;
  const iframeSrc = `/arcade/index.html?game=${encodeURIComponent(gameKey)}&mode=${mode}&locked=1`;

  return (
    <div className="w-full h-[calc(100vh-4rem)] md:h-screen flex flex-col bg-background">
      {/* ── SpacePoint LMS Header Bar ── */}
      <div className="flex items-center justify-between px-4 sm:px-6 py-2.5 bg-card/90 border-b border-border text-sm shrink-0 backdrop-blur-sm">
        <div className="flex items-center gap-3 min-w-0">
          {assignmentId ? (
            <Link
              to="/learn/checklists/$assignmentId"
              params={{ assignmentId }}
              className="inline-flex items-center gap-1.5 font-semibold text-primary hover:underline shrink-0"
            >
              <ArrowLeft className="size-4" /> Back to Program
            </Link>
          ) : (
            <Link
              to="/learn/arcade"
              className="inline-flex items-center gap-1.5 font-semibold text-primary hover:underline shrink-0"
            >
              <ArrowLeft className="size-4" /> Mission Arcade
            </Link>
          )}

          <div className="hidden sm:flex items-center gap-2 text-muted-foreground min-w-0">
            <span>/</span>
            {currentGame && (
              <span className="text-xs font-semibold uppercase tracking-wider text-primary/80 bg-primary/10 px-2 py-0.5 rounded border border-primary/20 shrink-0">
                M{currentGame.module_no} · {currentGame.module_name}
              </span>
            )}
            <span className="font-display font-bold text-foreground truncate">
              {currentGame?.title || gameKey}
            </span>
            {currentGame?.is_3d && (
              <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold text-primary bg-primary/15 border border-primary/30 shrink-0">
                <Box className="size-2.5" /> 3D
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {/* Track selector */}
          <div className="inline-flex rounded-lg bg-card/80 border border-border p-0.5 text-xs">
            <button
              onClick={() => {
                void navigate({
                  to: "/learn/arcade/$gameKey",
                  params: { gameKey },
                  search: { mode: "explorer", program: assignmentId, itemId } as never,
                });
              }}
              className={`px-2.5 py-1 rounded-md font-medium transition-all flex items-center gap-1 ${
                mode === "explorer"
                  ? "bg-primary text-primary-foreground font-semibold"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Compass className="size-3" /> Explorer
            </button>
            <button
              onClick={() => {
                void navigate({
                  to: "/learn/arcade/$gameKey",
                  params: { gameKey },
                  search: { mode: "engineer", program: assignmentId, itemId } as never,
                });
              }}
              className={`px-2.5 py-1 rounded-md font-medium transition-all flex items-center gap-1 ${
                mode === "engineer"
                  ? "bg-primary text-primary-foreground font-semibold"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Wrench className="size-3" /> Engineer
            </button>
          </div>

          {/* Cleared badge */}
          {(justPassed || modeData?.passed) && (
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-400 bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-1 rounded-full">
              <CheckCircle2 className="size-3.5" /> Cleared ({modeData?.best_score ?? 100}/100)
            </span>
          )}
        </div>
      </div>

      <iframe src={iframeSrc} title={currentGame?.title || gameKey} className="w-full flex-1 min-h-0 border-0" />
    </div>
  );
}
