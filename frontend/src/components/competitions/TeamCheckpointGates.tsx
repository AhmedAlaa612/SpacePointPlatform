import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Flag, LockOpen } from "lucide-react";
import {
  getTeamCheckpointsApi, unlockTeamCheckpointApi,
} from "@/api/competitions";
import { useToast } from "@/components/ui/toast";
import { cn, getErrorMessage } from "@/lib/utils";

/** A team's checkpoint gates on the ops Teams tab: one badge per gate
 * (locked vs open) plus a per-gate unlock button that cascades down
 * through later gates and the final lock. Collapsed to a single row
 * until opened; renders nothing when the checklist has no gates. */
export function TeamCheckpointGates({ teamId, cohortId }: { teamId: string; cohortId: string }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data: gates, isLoading } = useQuery({
    queryKey: ["competitions-team-checkpoints", teamId],
    queryFn: () => getTeamCheckpointsApi(teamId),
    enabled: open,
  });

  const unlockMutation = useMutation({
    mutationFn: (checkpointItemId: string) => unlockTeamCheckpointApi(teamId, checkpointItemId),
    onSuccess: () => {
      toast.success("Checkpoint unlocked — team can re-lock forward");
      void queryClient.invalidateQueries({ queryKey: ["competitions-team-checkpoints", teamId] });
      void queryClient.invalidateQueries({ queryKey: ["competitions-teams", cohortId] });
      void queryClient.invalidateQueries({ queryKey: ["competitions-team-analytics", cohortId] });
    },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Failed to unlock this checkpoint")),
  });

  const lockedCount = (gates ?? []).filter((g) => g.status === "done").length;

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
                  <span className="flex items-center gap-1.5 min-w-0 text-xs">
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
                  </span>
                  {isLocked && (
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
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
