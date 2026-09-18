import { isAxiosError } from "axios";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Flag, Lock } from "lucide-react";
import { finalSubmitChecklist } from "@/api/lms";
import { useToast } from "@/components/ui/toast";
import type { CheckpointGroup } from "./roadmap";

/** Same 2-line pattern every other student page in this app duplicates
 * locally (see TaskDrawer.tsx's own copy) — axios's `err.message` is a
 * generic "Request failed with status code 400", never the backend's
 * actual reason. */
function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail;
  return fallback;
}

/** Design spec §"Final gate bar" — pinned to the bottom of the board
 * (`margin-top:auto` on desktop). Summarizes the checklist's last
 * checkpoint group rather than hard-coding "Checkpoint 3" — a program
 * with no checkpoint labels at all still gets a generic "Final gate"
 * reading over its last few required tasks.
 *
 * Three states: decorative (not every required task is done yet — the
 * pre-existing behavior, unchanged), a real one-way "Final Submit" button
 * once `allDone && hasTeam && !locked` (locks the team's checklist against
 * further edits, see routers/lms/student.py::final_submit_program), and a
 * locked indicator once the team has already done that — no longer
 * interactive, only ops can undo it. `allDone` mirrors `pct === 100` in
 * `RoadmapBoard.tsx` (every required item, individual-scoped ones
 * included), matching this card's own "Complete every task above to
 * finish" copy — see `team_final_submit_readiness`'s docstring for why
 * that's deliberate. A program with no team (`hasTeam` false) has nothing
 * to lock, so `allDone` alone never turns this into a button. */
export function FinalGateBar({
  groups, allDone, locked, hasTeam, assignmentId, onFinalized,
}: {
  groups: CheckpointGroup[];
  allDone: boolean;
  locked: boolean;
  hasTeam: boolean;
  assignmentId: string;
  onFinalized: () => void;
}) {
  const toast = useToast();
  const finalSubmitMutation = useMutation({
    mutationFn: () => finalSubmitChecklist(assignmentId),
    onSuccess: () => {
      toast.success("Final submission locked in!");
      onFinalized();
    },
    onError: (err) => toast.error(errorDetail(err, "Couldn't finalize your team's submission.")),
  });

  if (groups.length === 0) return null;
  const last = groups[groups.length - 1];
  const previous = groups.length > 1 ? groups[groups.length - 2] : null;
  const taskCount = last.items.length;
  const eyebrow = last.label ? `FINAL GATE · ${last.label.toUpperCase()}` : "FINAL GATE";

  if (locked) {
    return (
      <div className="mt-6 md:mt-auto flex items-center gap-3 rounded-2xl bg-emerald-500/10 px-4 py-3.5 border border-emerald-500/30">
        <div className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-xl bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
          <Lock size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[9px] font-bold uppercase tracking-[0.08em] text-emerald-600 dark:text-emerald-400">{eyebrow}</div>
          <div className="font-display text-[16px] font-bold text-foreground truncate">Final submission locked</div>
        </div>
        <div className="hidden sm:block shrink-0 text-xs text-muted-foreground text-right max-w-[220px]">
          Ask an ops staff member to reopen it if you need changes.
        </div>
      </div>
    );
  }

  if (allDone && hasTeam) {
    return (
      <button
        type="button"
        disabled={finalSubmitMutation.isPending}
        onClick={() => {
          if (confirm("Final submit your team's checklist? This locks it against further edits — only ops can reopen it.")) {
            finalSubmitMutation.mutate();
          }
        }}
        className="mt-6 md:mt-auto flex items-center gap-3 rounded-2xl bg-primary/10 hover:bg-primary/15 transition-colors px-4 py-3.5 border border-primary/40 text-left disabled:opacity-60"
      >
        <div className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
          <CheckCircle2 size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[9px] font-bold uppercase tracking-[0.08em] text-primary">{eyebrow}</div>
          <div className="font-display text-[16px] font-bold text-foreground truncate">
            {finalSubmitMutation.isPending ? "Finalizing…" : `Final Submit — ${taskCount} task${taskCount === 1 ? "" : "s"}`}
          </div>
        </div>
        <div className="hidden sm:block shrink-0 text-xs text-muted-foreground text-right max-w-[220px]">
          Locks your team's checklist for good
        </div>
      </button>
    );
  }

  const condition = allDone
    ? "All clear — nice work"
    : previous?.label
    ? `Powers on when ${previous.label} is clear`
    : "Complete every task above to finish";

  return (
    <div className="mt-6 md:mt-auto flex items-center gap-3 rounded-2xl bg-card px-4 py-3.5 border border-border">
      <div className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <Flag size={18} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[9px] font-bold uppercase tracking-[0.08em] text-primary">{eyebrow}</div>
        <div className="font-display text-[16px] font-bold text-foreground truncate">
          Review &amp; submit — {taskCount} task{taskCount === 1 ? "" : "s"}
        </div>
      </div>
      <div className="hidden sm:block shrink-0 text-xs text-muted-foreground text-right max-w-[220px]">{condition}</div>
    </div>
  );
}
