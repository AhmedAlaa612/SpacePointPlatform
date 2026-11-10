import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Flag, Lock, LockOpen } from "lucide-react";
import {
  getTeamCheckpointsApi, lockTeamCheckpointApi, unlockTeamCheckpointApi,
} from "@/api/competitions";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { cn, getErrorMessage } from "@/lib/utils";

/** A team's checkpoint gates on the ops Teams tab: one badge per gate
 * (locked vs open) plus per-gate lock (with optional penalty) and unlock
 * buttons. Collapsed to a single row until opened; renders nothing when
 * the checklist has no gates. */
export function TeamCheckpointGates({ teamId, cohortId }: { teamId: string; cohortId: string }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [lockTarget, setLockTarget] = useState<{ itemId: string; title: string } | null>(null);
  const [penaltyPointsStr, setPenaltyPointsStr] = useState("");
  const [penaltyNotes, setPenaltyNotes] = useState("");

  const { data: gates, isLoading } = useQuery({
    queryKey: ["competitions-team-checkpoints", teamId],
    queryFn: () => getTeamCheckpointsApi(teamId),
    enabled: open,
  });

  const invalidateAll = () => {
    void queryClient.invalidateQueries({ queryKey: ["competitions-team-checkpoints", teamId] });
    void queryClient.invalidateQueries({ queryKey: ["competitions-teams", cohortId] });
    void queryClient.invalidateQueries({ queryKey: ["competitions-team-analytics", cohortId] });
    void queryClient.invalidateQueries({ queryKey: ["competitions-leaderboard", cohortId] });
    void queryClient.invalidateQueries({ queryKey: ["competitions-team-breakdown", cohortId, teamId] });
  };

  const lockMutation = useMutation({
    mutationFn: (args: { checkpointItemId: string; penalty_points?: number | null; notes?: string | null }) =>
      lockTeamCheckpointApi(teamId, args.checkpointItemId, {
        penalty_points: args.penalty_points,
        notes: args.notes,
      }),
    onSuccess: (_data, vars) => {
      const pen = vars.penalty_points ? -Math.abs(vars.penalty_points) : 0;
      toast.success(pen < 0 ? `Checkpoint locked with ${pen} pts penalty` : "Checkpoint locked");
      setLockTarget(null);
      setPenaltyPointsStr("");
      setPenaltyNotes("");
      invalidateAll();
    },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Failed to lock this checkpoint")),
  });

  const unlockMutation = useMutation({
    mutationFn: (checkpointItemId: string) => unlockTeamCheckpointApi(teamId, checkpointItemId),
    onSuccess: () => {
      toast.success("Checkpoint unlocked — team can re-lock forward");
      invalidateAll();
    },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Failed to unlock this checkpoint")),
  });

  const lockedCount = (gates ?? []).filter((g) => g.status === "done").length;
  const parsedPenalty = penaltyPointsStr.trim() !== "" ? parseFloat(penaltyPointsStr) : 0;
  const effectivePenaltyDeduction = !isNaN(parsedPenalty) && parsedPenalty !== 0 ? -Math.abs(parsedPenalty) : 0;

  return (
    <div className="border-t border-border/60 pt-2.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <Flag size={13} />
        Checkpoint gates
        {!isLoading && (gates ?? []).length > 0 && (
          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
            {lockedCount}/{gates!.length} locked
          </span>
        )}
      </button>

      {open && (
        <div className="mt-2 flex flex-col gap-1.5">
          {isLoading ? (
            <p className="text-xs text-muted-foreground">Loading gates…</p>
          ) : (gates ?? []).length === 0 ? (
            <p className="text-xs text-muted-foreground">No checkpoint gates on this checklist.</p>
          ) : (
            gates!.map((gate) => {
              const isLocked = gate.status === "done";
              return (
                <div
                  key={gate.item_id}
                  className="flex items-center justify-between gap-2 rounded-lg border border-border/60 bg-muted/30 px-2.5 py-1.5"
                >
                  <span className="flex items-center gap-1.5 min-w-0 text-xs flex-wrap">
                    <span
                      className={cn(
                        "text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded border shrink-0",
                        isLocked
                          ? "bg-primary/10 border-primary/30 text-primary"
                          : "bg-muted border-border text-muted-foreground",
                      )}
                    >
                      {isLocked ? "Locked" : "Open"}
                    </span>
                    <span className="truncate text-foreground font-medium">{gate.title}</span>
                    {isLocked && gate.penalty_points !== undefined && gate.penalty_points !== null && gate.penalty_points !== 0 && (
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-rose-500/15 border border-rose-500/30 text-rose-600 dark:text-rose-400">
                        Penalty: {gate.penalty_points} pts
                      </span>
                    )}
                    {isLocked && gate.locked_at && (
                      <span className="text-[11px] text-muted-foreground">
                        · Locked at {new Date(gate.locked_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                        {gate.locked_by_name && ` by ${gate.locked_by_name}`}
                        {gate.penalty_notes && ` (${gate.penalty_notes})`}
                      </span>
                    )}
                  </span>
                  {isLocked ? (
                    <button
                      type="button"
                      disabled={unlockMutation.isPending}
                      onClick={() => {
                        if (confirm(`Unlock "${gate.title}" for this team? Later gates and the final lock reopen too.`)) {
                          unlockMutation.mutate(gate.item_id);
                        }
                      }}
                      className="flex shrink-0 items-center gap-1 px-2 py-1 rounded-lg border border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[11px] font-bold hover:bg-amber-500/20 transition-colors disabled:opacity-50 cursor-pointer"
                      title="Unlock this gate — later gates and the final lock reopen too"
                    >
                      <LockOpen size={12} />
                      {unlockMutation.isPending ? "Unlocking…" : "Unlock"}
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={lockMutation.isPending}
                      onClick={() => {
                        setPenaltyPointsStr("");
                        setPenaltyNotes("");
                        setLockTarget({ itemId: gate.item_id, title: gate.title });
                      }}
                      className="flex shrink-0 items-center gap-1 px-2 py-1 rounded-lg border border-primary/40 bg-primary/10 text-primary text-[11px] font-bold hover:bg-primary/20 transition-colors disabled:opacity-50 cursor-pointer"
                      title="Lock this gate on behalf of the team (with optional penalty)"
                    >
                      <Lock size={12} />
                      Lock
                    </button>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}

      {lockTarget && (
        <Dialog open={!!lockTarget} onOpenChange={(v) => !v && setLockTarget(null)}>
          <DialogContent className="sm:max-w-md bg-card border-border p-6">
            <DialogHeader>
              <DialogTitle className="text-base font-bold text-foreground">
                Lock Checkpoint — &ldquo;{lockTarget.title}&rdquo;
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground">
                Lock this checkpoint gate on behalf of the team. You can optionally apply a penalty deduction.
              </DialogDescription>
            </DialogHeader>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (penaltyPointsStr.trim() !== "" && isNaN(parsedPenalty)) {
                  toast.error("Please enter a valid number for penalty points");
                  return;
                }
                lockMutation.mutate({
                  checkpointItemId: lockTarget.itemId,
                  penalty_points: effectivePenaltyDeduction !== 0 ? effectivePenaltyDeduction : null,
                  notes: penaltyNotes.trim() || null,
                });
              }}
              className="mt-3 space-y-4"
            >
              <div>
                <label className="block text-xs font-semibold text-foreground mb-1">
                  Penalty Points Deduction (Optional)
                </label>
                <input
                  type="number"
                  step="0.5"
                  min="0"
                  value={penaltyPointsStr}
                  onChange={(e) => setPenaltyPointsStr(e.target.value)}
                  placeholder="0 (no penalty) — e.g. 2, 5"
                  className="w-full h-9 px-3 rounded-xl border border-border bg-background text-foreground text-xs font-mono focus:outline-none focus:border-primary"
                />
                {effectivePenaltyDeduction < 0 && (
                  <p className="text-[11px] font-medium text-rose-600 dark:text-rose-400 mt-1">
                    Will deduct <strong>{effectivePenaltyDeduction} pts</strong> from the team&apos;s competition score.
                  </p>
                )}
              </div>

              <div>
                <label className="block text-xs font-semibold text-foreground mb-1">
                  Reason / Audit Note (Optional)
                </label>
                <input
                  type="text"
                  value={penaltyNotes}
                  onChange={(e) => setPenaltyNotes(e.target.value)}
                  placeholder="e.g. Late lock requested after deadline"
                  className="w-full h-9 px-3 rounded-xl border border-border bg-background text-foreground text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
                <button
                  type="button"
                  onClick={() => setLockTarget(null)}
                  className="px-3 py-1.5 rounded-xl border border-border text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={lockMutation.isPending}
                  className={cn(
                    "flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all disabled:opacity-50 cursor-pointer",
                    effectivePenaltyDeduction < 0
                      ? "bg-rose-600 text-white hover:bg-rose-700"
                      : "bg-primary text-primary-foreground hover:opacity-90",
                  )}
                >
                  <Lock size={12} />
                  {lockMutation.isPending
                    ? "Locking…"
                    : effectivePenaltyDeduction < 0
                    ? `Lock & Apply ${effectivePenaltyDeduction} pts`
                    : "Lock without Penalty"}
                </button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
