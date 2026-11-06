import { useMemo, useState } from "react";
import { useNavigate, useParams } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDown,
  ArrowLeft,
  CheckCircle2,
  Cpu,
  HelpCircle,
  Lightbulb,
  Radio,
  ShieldAlert,
  Sparkles,
  Users,
} from "lucide-react";
import {
  getProgramHintsApi,
  revealHintCardApi,
  type CohortHintCard,
} from "@/api/hint_station";
import { Spinner } from "@/components/ui/primitives";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

const CHALLENGE_ICONS = [Cpu, Radio, Sparkles, HelpCircle];

/** Student-only Hint Station (2026-11): progressive assistance cards for a
 * checklist's challenges. Works for both competition teams and individual
 * workshop users — the backend resolves team scope (or falls back to the
 * individual user) automatically. The judging/audit surfaces live with ops
 * (LMS Programs > Hints tab on the program/cohort, plus the judge's team
 * detail page), never inside this page. */
export default function HintStationPage() {
  const { assignmentId } = useParams({ strict: false }) as { assignmentId: string };
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();

  const [selectedChallengeId, setSelectedChallengeId] = useState<string | null>(null);
  const [cardToReveal, setCardToReveal] = useState<CohortHintCard | null>(null);

  // ── Student hint station data ────────────────────────────────────────────
  const {
    data: stationData,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["lms-hint-station", assignmentId],
    queryFn: () => getProgramHintsApi(assignmentId),
    refetchInterval: 15_000,
  });

  // Default active challenge to first available
  const effectiveChallenge = useMemo(() => {
    if (!stationData?.challenges || stationData.challenges.length === 0) return null;
    if (selectedChallengeId) {
      const match = stationData.challenges.find((c) => c.id === selectedChallengeId);
      if (match) return match;
    }
    return stationData.challenges[0];
  }, [stationData?.challenges, selectedChallengeId]);

  // ── Reveal Mutation ─────────────────────────────────────────────────────
  const revealMutation = useMutation({
    mutationFn: (cardId: string) => revealHintCardApi(assignmentId, cardId),
    onSuccess: (updatedCard) => {
      setCardToReveal(null);
      void queryClient.invalidateQueries({ queryKey: ["lms-hint-station", assignmentId] });
      toast.success(`${updatedCard.level_label} unlocked! -${updatedCard.point_deduction} points applied.`);
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail || "Failed to reveal hint";
      toast.error(detail);
    },
  });

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3">
        <Spinner />
        <p className="text-sm font-medium text-muted-foreground">Connecting to Hint Station…</p>
      </div>
    );
  }

  if (error || !stationData) {
    return (
      <div className="max-w-md mx-auto my-12 p-6 rounded-2xl border border-destructive/30 bg-destructive/5 text-center flex flex-col items-center gap-3">
        <AlertTriangle className="size-10 text-destructive" />
        <h2 className="text-lg font-bold">Hint Station Unavailable</h2>
        <p className="text-sm text-muted-foreground">
          Could not load the hint station for this checklist. Ensure the program has active challenges.
        </p>
        <button
          onClick={() => void navigate({ to: `/learn/checklists/${assignmentId}` as never })}
          className="mt-2 px-4 py-2 rounded-xl bg-card border border-border text-sm font-semibold hover:bg-muted transition-colors cursor-pointer"
        >
          Back to Roadmap
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen bg-background text-foreground">
      {/* ── Top App Bar ────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80 px-4 sm:px-6 py-3">
        <div className="max-w-5xl mx-auto flex items-center gap-2.5">
          <button
            onClick={() => void navigate({ to: `/learn/checklists/${assignmentId}` as never })}
            className="p-1.5 rounded-lg border border-border hover:bg-muted/80 text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            title="Return to Checklist"
          >
            <ArrowLeft size={16} />
          </button>
          <div className="flex flex-col">
            <span className="font-display font-extrabold text-base sm:text-lg tracking-tight leading-none uppercase">
              {stationData.cohort_name || stationData.program_name || "SpacePoint"}
            </span>
          </div>
        </div>
      </header>

      {/* ── Main Content Area ──────────────────────────────────────────────── */}
      <main className="flex-1 max-w-5xl mx-auto w-full px-4 sm:px-8 py-8 flex flex-col gap-8">
        {/* Guidance — floating text, no card */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-1.5 text-sm font-bold uppercase tracking-wider text-primary">
            <Lightbulb size={15} className="text-amber-500" />
            <span>Mission Support</span>
          </div>
          <h2 className="font-display text-2xl sm:text-3xl font-extrabold tracking-tight">
            Need a little guidance?
          </h2>
          <p className="text-sm sm:text-base text-muted-foreground leading-relaxed max-w-2xl">
            Choose a challenge and unlock progressive hints. Try solving it independently first — each revealed hint deducts points from your score.
          </p>
        </div>

        {/* Challenge Selector */}
        {stationData.challenges.length === 0 ? (
          <div className="p-10 text-center rounded-2xl border border-dashed border-border bg-card">
            <p className="text-base text-muted-foreground">No active challenges have been configured for this station yet.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
                Select a challenge
              </h3>
              {stationData.team_name && (
                <span className="text-sm font-semibold text-primary inline-flex items-center gap-1.5">
                  <Users size={14} /> Team {stationData.team_name}
                </span>
              )}
              {!stationData.team_name && (
                <span className="text-sm font-semibold text-muted-foreground">
                  Individual participant
                </span>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {stationData.challenges.map((ch, idx) => {
                const isSelected = effectiveChallenge?.id === ch.id;
                const IconComp = CHALLENGE_ICONS[idx % CHALLENGE_ICONS.length];
                const hintsUnlocked = ch.cards.filter((c) => c.is_revealed).length;

                return (
                  <button
                    key={ch.id}
                    onClick={() => setSelectedChallengeId(ch.id)}
                    className={cn(
                      "flex items-start gap-4 p-5 rounded-2xl border text-left transition-all cursor-pointer relative",
                      isSelected
                        ? "bg-card border-primary/50 shadow-md ring-2 ring-primary/20"
                        : "bg-card/60 hover:bg-card border-border hover:border-border/80",
                    )}
                  >
                    <div
                      className={cn(
                        "p-2.5 rounded-xl shrink-0 transition-colors",
                        isSelected
                          ? "bg-primary/10 text-primary"
                          : "bg-muted text-muted-foreground",
                      )}
                    >
                      <IconComp size={20} />
                    </div>
                    <div className="flex flex-col min-w-0 flex-1">
                      <span className="font-display font-bold text-base sm:text-lg text-foreground leading-snug truncate">
                        {ch.title}
                      </span>
                      <span className="text-sm text-muted-foreground line-clamp-1 mt-0.5">
                        {ch.topic || ch.description}
                      </span>

                      <div className="flex items-center gap-2 mt-2.5">
                        <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-muted text-muted-foreground">
                          {ch.cards.length} {ch.cards.length === 1 ? "hint" : "hints"}
                        </span>
                        {hintsUnlocked > 0 && (
                          <span className="text-xs font-bold px-2 py-0.5 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                            {hintsUnlocked} unlocked (-{ch.points_deducted} pts)
                          </span>
                        )}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Assistance Cards for Active Challenge */}
        {effectiveChallenge && (
          <div className="flex flex-col gap-4 mt-2">
            <div className="flex items-center justify-between border-b border-border/60 pb-2">
              <div className="flex flex-col">
                <h3 className="font-display font-extrabold text-lg sm:text-xl">
                  {effectiveChallenge.title}
                </h3>
                <p className="text-sm text-muted-foreground">
                  Max score: {effectiveChallenge.max_points} pts • Remaining:{" "}
                  <span className="font-bold text-foreground">
                    {effectiveChallenge.max_remaining_points} pts
                  </span>
                </p>
              </div>
              {effectiveChallenge.points_deducted > 0 && (
                <span className="text-sm font-bold text-rose-600 dark:text-rose-400 bg-rose-500/10 border border-rose-500/20 px-2.5 py-1 rounded-full">
                  -{effectiveChallenge.points_deducted} pts deducted
                </span>
              )}
            </div>

            <div className="flex flex-col gap-4">
              {effectiveChallenge.cards.length === 0 ? (
                <p className="text-sm text-muted-foreground p-4 text-center">
                  No hints authored for this challenge yet.
                </p>
              ) : (
                effectiveChallenge.cards.map((card) => {
                  return (
                    <div
                      key={card.id}
                      className={cn(
                        "flex flex-col gap-3 p-5 sm:p-6 rounded-2xl border transition-all",
                        card.is_revealed
                          ? "bg-emerald-500/[0.04] border-emerald-500/30 shadow-sm"
                          : card.is_locked
                          ? "bg-card/40 border-border/60 opacity-80"
                          : "bg-card border-border shadow-sm hover:border-primary/30",
                      )}
                    >
                      {/* Card Header */}
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex flex-col gap-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-display font-extrabold text-base sm:text-lg text-foreground">
                              {card.level_label}
                            </span>
                            {card.badge_label && (
                              <span className="px-2 py-0.5 rounded-full text-[11px] font-bold uppercase tracking-wider bg-primary/10 text-primary border border-primary/20">
                                {card.badge_label}
                              </span>
                            )}
                          </div>
                          {card.title && card.title !== card.level_label && (
                            <span className="text-sm font-semibold text-muted-foreground">
                              {card.title}
                            </span>
                          )}
                        </div>

                        <span
                          className={cn(
                            "text-sm font-bold px-2 py-1 rounded-lg shrink-0",
                            card.is_revealed
                              ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20"
                              : "bg-muted text-muted-foreground border border-border",
                          )}
                        >
                          -{card.point_deduction} pts
                        </span>
                      </div>

                      {/* Card Body */}
                      {card.is_revealed ? (
                        <div className="flex flex-col gap-2.5 pt-1">
                          <div className="p-4 rounded-xl bg-card border border-emerald-500/20 text-sm sm:text-base text-foreground whitespace-pre-wrap leading-relaxed">
                            {card.revealed_content}
                          </div>
                          <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                            <CheckCircle2 size={14} />
                            <span>
                              Unlocked {card.revealed_by_name ? `by ${card.revealed_by_name}` : ""}
                            </span>
                          </div>
                        </div>
                      ) : (
                        <div className="flex flex-col gap-3">
                          {card.teaser && (
                            <p className="text-sm sm:text-base text-muted-foreground leading-relaxed">
                              {card.teaser}
                            </p>
                          )}

                          {card.is_locked ? (
                            <button
                              disabled
                              className="w-full py-3 px-4 rounded-xl border border-border/80 bg-muted/40 text-muted-foreground text-sm font-semibold flex items-center justify-center gap-2 cursor-not-allowed"
                            >
                              <ArrowDown size={15} className="text-muted-foreground" />
                              <span>Unlock Level {card.unlock_order - 1} first</span>
                            </button>
                          ) : (
                            <button
                              onClick={() => setCardToReveal(card)}
                              className="w-full py-3 px-4 rounded-xl bg-foreground text-background dark:bg-primary dark:text-primary-foreground text-sm font-bold flex items-center justify-center gap-2 hover:opacity-90 active:scale-[0.99] transition-all cursor-pointer shadow-sm"
                            >
                              <Lightbulb size={15} />
                              <span>Reveal {card.level_label} (-{card.point_deduction} pts)</span>
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}
      </main>

      {/* ── Sticky Live Score Meter Bar ────────────────────────────────────── */}
      {effectiveChallenge && (
        <footer className="sticky bottom-0 z-20 mt-auto border-t border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80 px-4 sm:px-8 py-3 shadow-lg">
          <div className="max-w-5xl mx-auto flex items-center justify-between gap-4">
            <div className="flex flex-col">
              <span className="text-xs font-semibold text-muted-foreground">
                Challenge Score
              </span>
              <span className="font-display font-black text-base sm:text-lg text-foreground">
                {effectiveChallenge.max_remaining_points} / {effectiveChallenge.max_points} pts
              </span>
            </div>

            <div className="flex items-center gap-3">
              {stationData.total_points_deducted > 0 && (
                <div className="flex flex-col items-end">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-rose-600 dark:text-rose-400">
                    Total Deduction
                  </span>
                  <span className="font-display font-extrabold text-base text-rose-600 dark:text-rose-400">
                    -{stationData.total_points_deducted} pts
                  </span>
                </div>
              )}

              <div className="px-3 py-1.5 rounded-xl bg-primary/10 border border-primary/20 text-sm font-bold text-primary flex items-center gap-1.5">
                <Lightbulb size={14} className="text-amber-500" />
                <span>{stationData.total_hints_revealed} hints used</span>
              </div>
            </div>
          </div>
        </footer>
      )}

      {/* ── Confirmation Modal ─────────────────────────────────────────────── */}
      <Dialog open={!!cardToReveal} onOpenChange={(open) => !open && setCardToReveal(null)}>
        <DialogContent className="max-w-sm rounded-2xl p-6">
          <DialogHeader className="gap-2 text-left">
            <div className="size-10 rounded-full bg-rose-500/10 text-rose-600 dark:text-rose-400 flex items-center justify-center border border-rose-500/20 mb-1">
              <ShieldAlert size={20} />
            </div>
            <DialogTitle className="font-display text-lg font-bold">
              Unlock {cardToReveal?.level_label}?
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground leading-relaxed">
              Revealing this assistance card will deduct{" "}
              <span className="font-extrabold text-foreground underline decoration-rose-500">
                {cardToReveal?.point_deduction} marks
              </span>{" "}
              from your score{stationData.team_name ? " for your entire team" : ""} and log it for judging.
            </DialogDescription>
          </DialogHeader>

          <div className="flex items-center justify-end gap-2.5 mt-5">
            <button
              onClick={() => setCardToReveal(null)}
              className="px-4 py-2 rounded-xl border border-border text-xs font-semibold hover:bg-muted transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              onClick={() => cardToReveal && revealMutation.mutate(cardToReveal.id)}
              disabled={revealMutation.isPending}
              className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold transition-colors cursor-pointer shadow-sm flex items-center gap-1.5 disabled:opacity-50"
            >
              {revealMutation.isPending ? "Unlocking…" : `Confirm & Deduct ${cardToReveal?.point_deduction} pts`}
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
