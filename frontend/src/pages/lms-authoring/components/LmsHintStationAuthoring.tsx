import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronUp,
  Copy,
  Edit2,
  GitFork,
  Lightbulb,
  Plus,
  RotateCcw,
  Trash2,
  User,
  Users,
} from "lucide-react";
import {
  listProgramChallengesAdminApi,
  listCohortChallengesAdminApi,
  forkCohortChallengesAdminApi,
  createHintChallengeApi,
  updateHintChallengeApi,
  deleteHintChallengeApi,
  createHintCardApi,
  updateHintCardApi,
  deleteHintCardApi,
  getCohortHintJudgingSummaryApi,
  resetTeamHintRevealsApi,
  resetUserHintRevealsApi,
  type CohortHintCard,
  type CohortHintChallenge,
  type CohortHintJudgingSummary,
} from "@/api/hint_station";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { Spinner } from "@/components/ui/primitives";
import { ImportHintStationModal } from "./ImportHintStationModal";
import { cn } from "@/lib/utils";

type Scope = "program" | { cohortId: string; cohortName: string };

export function LmsHintStationAuthoring({
  programId,
  scope,
}: {
  programId: string;
  scope: Scope;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();

  const isProgramScope = scope === "program";
  const cohortId = !isProgramScope ? scope.cohortId : null;

  const [importOpen, setImportOpen] = useState(false);
  const [editingChallenge, setEditingChallenge] = useState<Partial<CohortHintChallenge> | null>(null);
  const [challengeModalOpen, setChallengeModalOpen] = useState(false);

  const [editingCard, setEditingCard] = useState<{ challengeId: string; card: Partial<CohortHintCard> } | null>(null);
  const [cardModalOpen, setCardModalOpen] = useState(false);
  const [expandedChallengeIds, setExpandedChallengeIds] = useState<Set<string>>(new Set());

  // ── Query Challenges ───────────────────────────────────────────────────────
  const queryKey = isProgramScope
    ? ["admin-hints-program", programId]
    : ["admin-hints-cohort", cohortId];

  const {
    data: challenges = [],
    isLoading,
    refetch,
  } = useQuery<CohortHintChallenge[]>({
    queryKey,
    queryFn: () =>
      isProgramScope
        ? listProgramChallengesAdminApi(programId)
        : listCohortChallengesAdminApi(cohortId!),
    enabled: isProgramScope ? !!programId : !!cohortId,
  });

  const isInherited =
    !isProgramScope &&
    challenges.length > 0 &&
    challenges.some((c) => c.owner_type === "program");

  // ── Fork Mutation ──────────────────────────────────────────────────────────
  const forkMutation = useMutation({
    mutationFn: () => forkCohortChallengesAdminApi(cohortId!),
    onSuccess: () => {
      toast.success("Challenges successfully forked for this cohort override!");
      void queryClient.invalidateQueries({ queryKey });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Failed to fork challenges"),
  });

  // ── Challenge Mutations ────────────────────────────────────────────────────
  const saveChallengeMutation = useMutation({
    mutationFn: async (data: Partial<CohortHintChallenge>) => {
      if (data.id) {
        return await updateHintChallengeApi(data.id, data);
      } else {
        const ownerType = isProgramScope ? "program" : "cohort";
        const ownerId = isProgramScope ? programId : cohortId!;
        return await createHintChallengeApi({
          owner_type: ownerType,
          owner_id: ownerId,
          title: data.title || "Untitled Challenge",
          challenge_code: data.challenge_code,
          topic: data.topic,
          description: data.description || "",
          mission_statement: data.mission_statement,
          max_points: data.max_points ?? 20,
          position: data.position ?? challenges.length,
          is_active: data.is_active ?? true,
        });
      }
    },
    onSuccess: () => {
      setChallengeModalOpen(false);
      setEditingChallenge(null);
      void queryClient.invalidateQueries({ queryKey });
      toast.success("Challenge saved.");
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Failed to save challenge"),
  });

  const deleteChallengeMutation = useMutation({
    mutationFn: (id: string) => deleteHintChallengeApi(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
      toast.success("Challenge deleted.");
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Failed to delete challenge"),
  });

  // ── Card Mutations ─────────────────────────────────────────────────────────
  const saveCardMutation = useMutation({
    mutationFn: async ({ challengeId, card }: { challengeId: string; card: Partial<CohortHintCard> }) => {
      if (card.id) {
        return await updateHintCardApi(card.id, card);
      } else {
        return await createHintCardApi(challengeId, {
          level: card.level ?? 1,
          level_label: card.level_label || `Level ${card.level ?? 1}`,
          badge_label: card.badge_label,
          title: card.title || `Level ${card.level ?? 1} Hint`,
          teaser: card.teaser,
          revealed_content: card.revealed_content || "",
          point_deduction: card.point_deduction ?? 2,
          unlock_order: card.unlock_order ?? card.level ?? 1,
          position: card.position ?? 0,
        });
      }
    },
    onSuccess: () => {
      setCardModalOpen(false);
      setEditingCard(null);
      void queryClient.invalidateQueries({ queryKey });
      toast.success("Hint card saved.");
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Failed to save hint card"),
  });

  const deleteCardMutation = useMutation({
    mutationFn: (id: string) => deleteHintCardApi(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
      toast.success("Hint card deleted.");
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Failed to delete hint card"),
  });

  const toggleExpand = (id: string) => {
    setExpandedChallengeIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (isLoading) return <Spinner />;

  return (
    <div className="flex flex-col gap-6">
      {/* ── Header Controls ────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 p-5 rounded-2xl border border-border bg-card">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <h2 className="font-display font-extrabold text-lg text-foreground">
              {isProgramScope
                ? "Program Baseline Challenges & Hints"
                : `Cohort Hints: ${scope.cohortName}`}
            </h2>
            <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
              {isProgramScope ? "Program Template" : isInherited ? "Inherited Baseline" : "Cohort Override"}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Author challenges, multi-level guidance hints, and scoring deductions for onsite competitions.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {isInherited && (
            <button
              onClick={() => forkMutation.mutate()}
              disabled={forkMutation.isPending}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-700 dark:text-amber-300 border border-amber-500/30 text-xs font-bold transition-colors cursor-pointer"
              title="Fork program baseline into a cohort-specific override"
            >
              <GitFork size={13} />
              <span>{forkMutation.isPending ? "Forking…" : "Fork for this Cohort"}</span>
            </button>
          )}

          <button
            onClick={() => setImportOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-border bg-muted/60 hover:bg-muted text-xs font-semibold transition-colors cursor-pointer"
          >
            <Copy size={13} />
            <span>Import Challenges</span>
          </button>

          <button
            onClick={() => {
              setEditingChallenge({
                title: "",
                topic: "",
                description: "",
                max_points: 20,
                position: challenges.length,
                is_active: true,
              });
              setChallengeModalOpen(true);
            }}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-all cursor-pointer shadow-sm"
          >
            <Plus size={14} />
            <span>New Challenge</span>
          </button>
        </div>
      </div>

      {/* ── Challenge List ─────────────────────────────────────────────────── */}
      {challenges.length === 0 ? (
        <div className="p-12 text-center rounded-2xl border border-dashed border-border bg-card/60 flex flex-col items-center gap-3">
          <div className="size-12 rounded-2xl bg-primary/10 text-primary flex items-center justify-center">
            <Lightbulb size={24} />
          </div>
          <h3 className="font-display font-bold text-base">No Challenges Configured</h3>
          <p className="text-xs text-muted-foreground max-w-sm">
            Create a challenge or import from another cohort/program template to start setting up assistance cards.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {challenges.map((ch) => {
            const isExpanded = expandedChallengeIds.has(ch.id);

            return (
              <div
                key={ch.id}
                className="flex flex-col rounded-2xl border border-border bg-card overflow-hidden transition-all shadow-sm"
              >
                {/* Challenge Row Header */}
                <div className="p-4 sm:p-5 flex items-start justify-between gap-4 bg-muted/10">
                  <div
                    onClick={() => toggleExpand(ch.id)}
                    className="flex-1 min-w-0 cursor-pointer flex items-start gap-3 select-none"
                  >
                    <div className="mt-1 p-1 rounded-md bg-muted text-muted-foreground">
                      {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </div>
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        {ch.challenge_code && (
                          <span className="font-mono text-xs font-bold text-primary px-1.5 py-0.5 rounded bg-primary/10">
                            {ch.challenge_code}
                          </span>
                        )}
                        <span className="font-display font-extrabold text-base text-foreground">
                          {ch.title}
                        </span>
                        {ch.topic && (
                          <span className="text-xs text-muted-foreground font-semibold">
                            • {ch.topic}
                          </span>
                        )}
                        {!ch.is_active && (
                          <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20">
                            Inactive
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground line-clamp-2">
                        {ch.description}
                      </p>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs font-bold text-muted-foreground bg-muted px-2.5 py-1 rounded-lg">
                      {ch.cards.length} {ch.cards.length === 1 ? "hint" : "hints"} • {ch.max_points} pts
                    </span>
                    <button
                      onClick={() => {
                        setEditingChallenge(ch);
                        setChallengeModalOpen(true);
                      }}
                      className="p-1.5 rounded-lg border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                      title="Edit Challenge"
                    >
                      <Edit2 size={13} />
                    </button>
                    <button
                      onClick={() => {
                        if (window.confirm(`Delete challenge "${ch.title}" and all its hint cards?`)) {
                          deleteChallengeMutation.mutate(ch.id);
                        }
                      }}
                      className="p-1.5 rounded-lg border border-border hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors cursor-pointer"
                      title="Delete Challenge"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>

                {/* Challenge Hint Cards Sub-List */}
                {isExpanded && (
                  <div className="p-4 sm:p-5 border-t border-border flex flex-col gap-3.5 bg-background/50">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                        Assistance Cards (Progressive Unlock)
                      </span>
                      <button
                        onClick={() => {
                          const nextLevel = ch.cards.length + 1;
                          setEditingCard({
                            challengeId: ch.id,
                            card: {
                              level: nextLevel,
                              level_label:
                                nextLevel === 1
                                  ? "Level 1 — Think about it"
                                  : nextLevel === 2
                                  ? "Level 2 — Go deeper"
                                  : `Level ${nextLevel} — Focus Guidance`,
                              badge_label:
                                nextLevel === 1
                                  ? "Guiding question"
                                  : nextLevel === 2
                                  ? "Technical guidance"
                                  : "Solution guidance",
                              title:
                                nextLevel === 1
                                  ? "Thinking Hint"
                                  : nextLevel === 2
                                  ? "Technical Hint"
                                  : "Implementation Hint",
                              teaser: "",
                              revealed_content: "",
                              point_deduction: nextLevel === 1 ? 2 : nextLevel === 2 ? 3 : 5,
                              unlock_order: nextLevel,
                              position: ch.cards.length,
                            },
                          });
                          setCardModalOpen(true);
                        }}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary text-xs font-bold transition-colors cursor-pointer"
                      >
                        <Plus size={13} />
                        <span>Add Hint Card</span>
                      </button>
                    </div>

                    {ch.cards.length === 0 ? (
                      <p className="text-xs text-muted-foreground italic p-3 text-center rounded-xl bg-card border border-dashed border-border">
                        No hint cards authored yet for this challenge. Click "Add Hint Card" to add Level 1.
                      </p>
                    ) : (
                      <div className="grid grid-cols-1 gap-2.5">
                        {ch.cards.map((card) => (
                          <div
                            key={card.id}
                            className="p-3.5 rounded-xl border border-border bg-card flex flex-col sm:flex-row sm:items-start justify-between gap-3"
                          >
                            <div className="flex flex-col gap-1 min-w-0 flex-1">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="font-display font-extrabold text-sm text-foreground">
                                  {card.level_label}
                                </span>
                                {card.badge_label && (
                                  <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                                    {card.badge_label}
                                  </span>
                                )}
                                <span className="text-xs font-bold text-rose-600 dark:text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded-md">
                                  -{card.point_deduction} pts
                                </span>
                              </div>

                              {card.teaser && (
                                <p className="text-xs text-muted-foreground line-clamp-1">
                                  <span className="font-semibold text-foreground">Teaser:</span> {card.teaser}
                                </p>
                              )}
                              <p className="text-xs text-foreground/80 line-clamp-2 bg-muted/40 p-2 rounded-lg font-mono text-[11px]">
                                {card.revealed_content}
                              </p>
                            </div>

                            <div className="flex items-center gap-1.5 shrink-0">
                              <button
                                onClick={() => {
                                  setEditingCard({ challengeId: ch.id, card });
                                  setCardModalOpen(true);
                                }}
                                className="p-1.5 rounded-lg border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                                title="Edit Card"
                              >
                                <Edit2 size={12} />
                              </button>
                              <button
                                onClick={() => {
                                  if (window.confirm(`Delete ${card.level_label}?`)) {
                                    deleteCardMutation.mutate(card.id);
                                  }
                                }}
                                className="p-1.5 rounded-lg border border-border hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors cursor-pointer"
                                title="Delete Card"
                              >
                                <Trash2 size={12} />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ── Cohort Hint Usage & Deducted Points (Teams + Individuals) ───────── */}
      {!isProgramScope && cohortId && (
        <CohortHintUsagePanel cohortId={cohortId} />
      )}

      {/* ── Challenge Edit / Create Modal ───────────────────────────────────── */}
      <Dialog open={challengeModalOpen} onOpenChange={(o) => !o && setChallengeModalOpen(false)}>
        <DialogContent className="max-w-lg p-6">
          <DialogHeader>
            <DialogTitle className="font-display text-lg font-bold">
              {editingChallenge?.id ? "Edit Challenge" : "New Challenge"}
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Define the onsite problem, topic, and max points for this challenge station.
            </DialogDescription>
          </DialogHeader>

          {editingChallenge && (
            <div className="flex flex-col gap-3.5 my-3">
              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-1">
                  <label className="text-[11px] font-bold text-muted-foreground uppercase">Code</label>
                  <input
                    type="text"
                    placeholder="e.g. CH01"
                    value={editingChallenge.challenge_code || ""}
                    onChange={(e) => setEditingChallenge({ ...editingChallenge, challenge_code: e.target.value })}
                    className="w-full h-9 px-3 border border-border bg-card rounded-xl text-xs font-semibold focus:outline-none focus:border-primary"
                  />
                </div>
                <div className="col-span-2">
                  <label className="text-[11px] font-bold text-muted-foreground uppercase">Title *</label>
                  <input
                    type="text"
                    placeholder="e.g. Sensor Data Collection"
                    value={editingChallenge.title || ""}
                    onChange={(e) => setEditingChallenge({ ...editingChallenge, title: e.target.value })}
                    className="w-full h-9 px-3 border border-border bg-card rounded-xl text-xs font-bold focus:outline-none focus:border-primary"
                  />
                </div>
              </div>

              <div>
                <label className="text-[11px] font-bold text-muted-foreground uppercase">Topic / Subtitle</label>
                <input
                  type="text"
                  placeholder="e.g. Optimize sensor sampling rate and buffering"
                  value={editingChallenge.topic || ""}
                  onChange={(e) => setEditingChallenge({ ...editingChallenge, topic: e.target.value })}
                  className="w-full h-9 px-3 border border-border bg-card rounded-xl text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="text-[11px] font-bold text-muted-foreground uppercase">Challenge Description *</label>
                <textarea
                  rows={3}
                  placeholder="What are students tasked with completing?"
                  value={editingChallenge.description || ""}
                  onChange={(e) => setEditingChallenge({ ...editingChallenge, description: e.target.value })}
                  className="w-full p-3 border border-border bg-card rounded-xl text-xs focus:outline-none focus:border-primary resize-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] font-bold text-muted-foreground uppercase">Max Points</label>
                  <input
                    type="number"
                    min={1}
                    value={editingChallenge.max_points ?? 20}
                    onChange={(e) => setEditingChallenge({ ...editingChallenge, max_points: parseInt(e.target.value) || 20 })}
                    className="w-full h-9 px-3 border border-border bg-card rounded-xl text-xs font-bold focus:outline-none focus:border-primary"
                  />
                </div>

                <div className="flex items-center gap-2 mt-5">
                  <input
                    type="checkbox"
                    id="challengeActive"
                    checked={editingChallenge.is_active ?? true}
                    onChange={(e) => setEditingChallenge({ ...editingChallenge, is_active: e.target.checked })}
                    className="rounded border-border text-primary cursor-pointer"
                  />
                  <label htmlFor="challengeActive" className="text-xs font-bold cursor-pointer">
                    Station Active for Students
                  </label>
                </div>
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2 border-t border-border pt-4">
            <button
              onClick={() => setChallengeModalOpen(false)}
              className="px-4 py-2 rounded-xl border border-border text-xs font-semibold hover:bg-muted cursor-pointer"
            >
              Cancel
            </button>
            <button
              onClick={() => editingChallenge && saveChallengeMutation.mutate(editingChallenge)}
              disabled={saveChallengeMutation.isPending || !editingChallenge?.title}
              className="px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 disabled:opacity-40 cursor-pointer"
            >
              Save Challenge
            </button>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── Hint Card Edit / Create Modal ────────────────────────────────────── */}
      <Dialog open={cardModalOpen} onOpenChange={(o) => !o && setCardModalOpen(false)}>
        <DialogContent className="max-w-lg p-6">
          <DialogHeader>
            <DialogTitle className="font-display text-lg font-bold">
              {editingCard?.card.id ? "Edit Hint Card" : "New Hint Card"}
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Configure the progressive disclosure hint, public teaser, secret content, and point penalty.
            </DialogDescription>
          </DialogHeader>

          {editingCard && (
            <div className="flex flex-col gap-3.5 my-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] font-bold text-muted-foreground uppercase">Level</label>
                  <input
                    type="number"
                    min={1}
                    value={editingCard.card.level ?? 1}
                    onChange={(e) => {
                      const lvl = parseInt(e.target.value) || 1;
                      setEditingCard({
                        ...editingCard,
                        card: { ...editingCard.card, level: lvl, unlock_order: lvl },
                      });
                    }}
                    className="w-full h-9 px-3 border border-border bg-card rounded-xl text-xs font-bold focus:outline-none focus:border-primary"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-bold text-muted-foreground uppercase">Level Label *</label>
                  <input
                    type="text"
                    placeholder="e.g. Level 1 — Think about it"
                    value={editingCard.card.level_label || ""}
                    onChange={(e) => setEditingCard({ ...editingCard, card: { ...editingCard.card, level_label: e.target.value } })}
                    className="w-full h-9 px-3 border border-border bg-card rounded-xl text-xs font-bold focus:outline-none focus:border-primary"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] font-bold text-muted-foreground uppercase">Badge Label</label>
                  <input
                    type="text"
                    placeholder="e.g. Guiding question"
                    value={editingCard.card.badge_label || ""}
                    onChange={(e) => setEditingCard({ ...editingCard, card: { ...editingCard.card, badge_label: e.target.value } })}
                    className="w-full h-9 px-3 border border-border bg-card rounded-xl text-xs focus:outline-none focus:border-primary"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-bold text-muted-foreground uppercase">Marks Deducted *</label>
                  <input
                    type="number"
                    min={0}
                    value={editingCard.card.point_deduction ?? 2}
                    onChange={(e) => setEditingCard({ ...editingCard, card: { ...editingCard.card, point_deduction: parseInt(e.target.value) || 0 } })}
                    className="w-full h-9 px-3 border border-border bg-card rounded-xl text-xs font-bold text-rose-600 focus:outline-none focus:border-primary"
                  />
                </div>
              </div>

              <div>
                <label className="text-[11px] font-bold text-muted-foreground uppercase">
                  Teaser / Public Question (Visible before unlocking)
                </label>
                <textarea
                  rows={2}
                  placeholder="e.g. A question to guide your thinking without revealing the solution."
                  value={editingCard.card.teaser || ""}
                  onChange={(e) => setEditingCard({ ...editingCard, card: { ...editingCard.card, teaser: e.target.value } })}
                  className="w-full p-3 border border-border bg-card rounded-xl text-xs focus:outline-none focus:border-primary resize-none"
                />
              </div>

              <div>
                <label className="text-[11px] font-bold text-muted-foreground uppercase">
                  Revealed Content * (Secret guidance unlocked on confirm)
                </label>
                <textarea
                  rows={4}
                  placeholder="e.g. Does your satellite need to transmit every single reading directly? Compare sampling frequency vs transmission intervals."
                  value={editingCard.card.revealed_content || ""}
                  onChange={(e) => setEditingCard({ ...editingCard, card: { ...editingCard.card, revealed_content: e.target.value } })}
                  className="w-full p-3 border border-border bg-card rounded-xl text-xs font-mono text-[11px] focus:outline-none focus:border-primary resize-none"
                />
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2 border-t border-border pt-4">
            <button
              onClick={() => setCardModalOpen(false)}
              className="px-4 py-2 rounded-xl border border-border text-xs font-semibold hover:bg-muted cursor-pointer"
            >
              Cancel
            </button>
            <button
              onClick={() => editingCard && saveCardMutation.mutate(editingCard)}
              disabled={saveCardMutation.isPending || !editingCard?.card.revealed_content}
              className="px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 disabled:opacity-40 cursor-pointer"
            >
              Save Hint Card
            </button>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── Import Challenges Modal ────────────────────────────────────────── */}
      <ImportHintStationModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        targetScope={
          isProgramScope
            ? { type: "program", programId }
            : { type: "cohort", cohortId: cohortId!, cohortName: scope.cohortName }
        }
        onSuccess={() => refetch()}
      />
    </div>
  );
}

function CohortHintUsagePanel({ cohortId }: { cohortId: string }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [viewMode, setViewMode] = useState<"teams" | "individuals">("teams");
  const [expandedRowId, setExpandedRowId] = useState<string | null>(null);
  const [resettingId, setResettingId] = useState<string | null>(null);

  const { data: summary, isLoading } = useQuery<CohortHintJudgingSummary>({
    queryKey: ["competitions-cohort-hints-summary", cohortId],
    queryFn: () => getCohortHintJudgingSummaryApi(cohortId),
    refetchInterval: 15_000,
  });

  const handleResetTeam = async (teamId: string, teamName: string) => {
    if (!window.confirm(`Reset all hint reveals and point deductions for team "${teamName}"?`)) return;
    setResettingId(teamId);
    try {
      await resetTeamHintRevealsApi(cohortId, teamId);
      await queryClient.invalidateQueries({ queryKey: ["competitions-cohort-hints-summary", cohortId] });
      toast.success(`Reset hints for ${teamName}.`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to reset team hints");
    } finally {
      setResettingId(null);
    }
  };

  const handleResetUser = async (userId: string, userName: string) => {
    if (!window.confirm(`Reset all individual hint reveals and point deductions for "${userName}"?`)) return;
    setResettingId(userId);
    try {
      await resetUserHintRevealsApi(cohortId, userId);
      await queryClient.invalidateQueries({ queryKey: ["competitions-cohort-hints-summary", cohortId] });
      toast.success(`Reset hints for ${userName}.`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to reset individual hints");
    } finally {
      setResettingId(null);
    }
  };

  if (isLoading) return <Spinner />;
  if (!summary) return null;

  const teamsWithHints = summary.teams.filter((t) => t.hints_used > 0).length;
  const individualsWithHints = summary.individuals.filter((u) => u.hints_used > 0).length;
  const activeMode =
    summary.teams.length === 0 && summary.individuals.length > 0 ? "individuals" : viewMode;

  return (
    <div className="flex flex-col gap-4 p-5 rounded-2xl border border-border bg-card">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h3 className="font-display font-extrabold text-base text-foreground">
            Hint Usage & Deducted Points
          </h3>
          <p className="text-xs text-muted-foreground">
            Live tracking of revealed hints and mark deductions for both competition teams and individual students.
          </p>
        </div>

        <div className="flex items-center p-1 rounded-xl bg-muted/60 border border-border text-xs font-semibold w-fit">
          <button
            onClick={() => setViewMode("teams")}
            className={cn(
              "px-3 py-1.5 rounded-lg transition-all cursor-pointer flex items-center gap-1.5",
              activeMode === "teams"
                ? "bg-card text-foreground shadow-sm font-bold"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Users size={13} />
            <span>Teams ({summary.teams.length})</span>
          </button>
          <button
            onClick={() => setViewMode("individuals")}
            className={cn(
              "px-3 py-1.5 rounded-lg transition-all cursor-pointer flex items-center gap-1.5",
              activeMode === "individuals"
                ? "bg-card text-foreground shadow-sm font-bold"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <User size={13} />
            <span>Individuals ({summary.individuals.length})</span>
          </button>
        </div>
      </div>

      {/* KPI Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-xl border border-border bg-muted/20 flex flex-col">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
            Total Hints Revealed
          </span>
          <span className="font-display font-extrabold text-xl text-foreground mt-0.5">
            {summary.total_hints_revealed}
          </span>
        </div>
        <div className="p-3.5 rounded-xl border border-rose-500/20 bg-rose-500/[0.04] flex flex-col">
          <span className="text-[11px] font-bold uppercase tracking-wider text-rose-600 dark:text-rose-400">
            Total Points Deducted
          </span>
          <span className="font-display font-extrabold text-xl text-rose-600 dark:text-rose-400 mt-0.5">
            -{summary.total_points_deducted} pts
          </span>
        </div>
        <div className="p-3.5 rounded-xl border border-border bg-muted/20 flex flex-col">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
            Teams Using Hints
          </span>
          <span className="font-display font-extrabold text-xl text-foreground mt-0.5">
            {teamsWithHints} / {summary.teams.length}
          </span>
        </div>
        <div className="p-3.5 rounded-xl border border-border bg-muted/20 flex flex-col">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
            Individuals Using Hints
          </span>
          <span className="font-display font-extrabold text-xl text-foreground mt-0.5">
            {individualsWithHints} / {summary.individuals.length}
          </span>
        </div>
      </div>

      {/* Teams Table */}
      {activeMode === "teams" ? (
        summary.teams.length === 0 ? (
          <div className="p-6 text-center rounded-xl border border-dashed border-border bg-muted/10 text-xs text-muted-foreground">
            No teams in this cohort yet. Switch to "Individuals" to view solo student hint deductions.
          </div>
        ) : (
          <div className="flex flex-col divide-y divide-border border border-border rounded-xl overflow-hidden">
            {summary.teams.map((t) => {
              const isOpen = expandedRowId === `team-${t.team_id}`;
              return (
                <div key={t.team_id} className="flex flex-col bg-card">
                  <div className="p-3.5 flex items-center justify-between gap-3 hover:bg-muted/20 transition-colors">
                    <button
                      type="button"
                      onClick={() => setExpandedRowId(isOpen ? null : `team-${t.team_id}`)}
                      className="flex items-center gap-2.5 text-left flex-1 min-w-0 cursor-pointer"
                    >
                      {isOpen ? <ChevronUp size={14} className="text-muted-foreground" /> : <ChevronDown size={14} className="text-muted-foreground" />}
                      <span className="font-bold text-sm text-foreground truncate">{t.team_name}</span>
                      {t.team_code && (
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                          {t.team_code}
                        </span>
                      )}
                    </button>

                    <div className="flex items-center gap-2.5 shrink-0">
                      <span className="text-xs font-semibold text-muted-foreground">
                        {t.hints_used} {t.hints_used === 1 ? "hint" : "hints"}
                      </span>
                      <span
                        className={cn(
                          "text-xs font-bold px-2.5 py-1 rounded-lg",
                          t.total_points_deducted > 0
                            ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20"
                            : "bg-muted text-muted-foreground",
                        )}
                      >
                        -{t.total_points_deducted} pts
                      </span>
                      <button
                        type="button"
                        onClick={() => void handleResetTeam(t.team_id, t.team_name)}
                        disabled={t.hints_used === 0 || resettingId === t.team_id}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-border hover:bg-muted text-xs font-semibold disabled:opacity-40 cursor-pointer"
                        title="Reset this team's hint reveals"
                      >
                        <RotateCcw size={12} />
                        <span>Reset</span>
                      </button>
                    </div>
                  </div>

                  {isOpen && (
                    <div className="px-4 pb-3.5 pt-1 bg-muted/10 border-t border-border/60">
                      {t.reveals.length === 0 ? (
                        <p className="text-xs text-muted-foreground py-2">No hints revealed by this team.</p>
                      ) : (
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-xs">
                            <thead className="text-[11px] font-bold uppercase text-muted-foreground border-b border-border/60">
                              <tr>
                                <th className="py-2 pr-3">Challenge</th>
                                <th className="py-2 px-3">Level</th>
                                <th className="py-2 px-3">Deducted</th>
                                <th className="py-2 px-3">Revealed By</th>
                                <th className="py-2 pl-3">Time</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-border/40">
                              {t.reveals.map((r) => (
                                <tr key={r.id}>
                                  <td className="py-2 pr-3 font-semibold text-foreground">{r.challenge_title}</td>
                                  <td className="py-2 px-3">{r.level_label}</td>
                                  <td className="py-2 px-3 font-bold text-rose-600 dark:text-rose-400">-{r.points_deducted} pts</td>
                                  <td className="py-2 px-3 text-muted-foreground">{r.revealed_by_name || "Teammate"}</td>
                                  <td className="py-2 pl-3 text-muted-foreground font-mono text-[11px]">
                                    {new Date(r.revealed_at).toLocaleString()}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )
      ) : summary.individuals.length === 0 ? (
        <div className="p-6 text-center rounded-xl border border-dashed border-border bg-muted/10 text-xs text-muted-foreground">
          No individual (unassigned-to-team) student reveals recorded in this cohort.
        </div>
      ) : (
        <div className="flex flex-col divide-y divide-border border border-border rounded-xl overflow-hidden">
          {summary.individuals.map((u) => {
            const isOpen = expandedRowId === `user-${u.user_id}`;
            return (
              <div key={u.user_id} className="flex flex-col bg-card">
                <div className="p-3.5 flex items-center justify-between gap-3 hover:bg-muted/20 transition-colors">
                  <button
                    type="button"
                    onClick={() => setExpandedRowId(isOpen ? null : `user-${u.user_id}`)}
                    className="flex items-center gap-2.5 text-left flex-1 min-w-0 cursor-pointer"
                  >
                    {isOpen ? <ChevronUp size={14} className="text-muted-foreground" /> : <ChevronDown size={14} className="text-muted-foreground" />}
                    <div className="flex flex-col min-w-0">
                      <span className="font-bold text-sm text-foreground truncate">{u.user_name}</span>
                      {u.user_email && (
                        <span className="text-[11px] text-muted-foreground truncate">{u.user_email}</span>
                      )}
                    </div>
                  </button>

                  <div className="flex items-center gap-2.5 shrink-0">
                    <span className="text-xs font-semibold text-muted-foreground">
                      {u.hints_used} {u.hints_used === 1 ? "hint" : "hints"}
                    </span>
                    <span
                      className={cn(
                        "text-xs font-bold px-2.5 py-1 rounded-lg",
                        u.total_points_deducted > 0
                          ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20"
                          : "bg-muted text-muted-foreground",
                      )}
                    >
                      -{u.total_points_deducted} pts
                    </span>
                    <button
                      type="button"
                      onClick={() => void handleResetUser(u.user_id, u.user_name)}
                      disabled={u.hints_used === 0 || resettingId === u.user_id}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-border hover:bg-muted text-xs font-semibold disabled:opacity-40 cursor-pointer"
                      title="Reset this student's individual hint reveals"
                    >
                      <RotateCcw size={12} />
                      <span>Reset</span>
                    </button>
                  </div>
                </div>

                {isOpen && (
                  <div className="px-4 pb-3.5 pt-1 bg-muted/10 border-t border-border/60">
                    {u.reveals.length === 0 ? (
                      <p className="text-xs text-muted-foreground py-2">No hints revealed by this student.</p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead className="text-[11px] font-bold uppercase text-muted-foreground border-b border-border/60">
                            <tr>
                              <th className="py-2 pr-3">Challenge</th>
                              <th className="py-2 px-3">Level</th>
                              <th className="py-2 px-3">Deducted</th>
                              <th className="py-2 pl-3">Time</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border/40">
                            {u.reveals.map((r) => (
                              <tr key={r.id}>
                                <td className="py-2 pr-3 font-semibold text-foreground">{r.challenge_title}</td>
                                <td className="py-2 px-3">{r.level_label}</td>
                                <td className="py-2 px-3 font-bold text-rose-600 dark:text-rose-400">-{r.points_deducted} pts</td>
                                <td className="py-2 pl-3 text-muted-foreground font-mono text-[11px]">
                                  {new Date(r.revealed_at).toLocaleString()}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
