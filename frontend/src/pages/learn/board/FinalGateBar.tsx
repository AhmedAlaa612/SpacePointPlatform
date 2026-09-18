import { isAxiosError } from "axios";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Flag, Lock } from "lucide-react";
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
 * Three states: decorative (not every required *team* task is done yet —
 * the pre-existing behavior, unchanged), a real one-way "Final Submit"
 * button once `teamReady && hasTeam && !locked` (locks the team's
 * checklist against further edits, see
 * routers/lms/student.py::final_submit_program), and a locked indicator
 * once the team has already done that — no longer interactive, only ops
 * can undo it. `teamReady` (computed in `RoadmapBoard.tsx`) only counts
 * the team-scoped required items — a teammate's own unrelated personal
 * task never blocks it (2026-09-19, found live: it did, and shouldn't
 * have — see `team_final_submit_readiness`'s docstring on the backend
 * side, which was fixed the same way). A program with no team (`hasTeam`
 * false) has nothing to lock, so `teamReady` alone never turns this into
 * a button. The ready state is styled as a solid, filled CTA (not just a
 * tinted card like the other two states) specifically so it reads as
 * clickable at a glance — found live, 2026-09-19: the original tinted-card
 * treatment looked identical to the purely-decorative states and nobody
 * could tell it was a button. */
export function FinalGateBar({
  groups, teamReady, locked, hasTeam, assignmentId, onFinalized,
}: {
  groups: CheckpointGroup[];
  teamReady: boolean;
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
      </div>
    );
  }

  if (teamReady && hasTeam) {
    return (
      <button
        type="button"
        disabled={finalSubmitMutation.isPending}
        onClick={() => {
          if (confirm("Submit your team's work? You won't be able to make further edits — only ops can reopen it.")) {
            finalSubmitMutation.mutate();
          }
        }}
        className="group mt-6 md:mt-auto flex items-center gap-3 rounded-2xl bg-primary px-4 py-3.5 shadow-[0_4px_20px_-4px_hsl(var(--primary)/0.55)] transition-all hover:-translate-y-0.5 hover:shadow-[0_8px_28px_-4px_hsl(var(--primary)/0.7)] active:translate-y-0 disabled:opacity-60 disabled:pointer-events-none disabled:hover:translate-y-0"
      >
        <div className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-xl bg-primary-foreground/15 text-primary-foreground">
          <CheckCircle2 size={18} />
        </div>
        <div className="min-w-0 flex-1 text-left">
          <div className="text-[9px] font-bold uppercase tracking-[0.08em] text-primary-foreground/75">{eyebrow}</div>
          <div className="font-display text-[16px] font-bold text-primary-foreground truncate">
            {finalSubmitMutation.isPending ? "Finalizing…" : `Final Submit — ${taskCount} task${taskCount === 1 ? "" : "s"}`}
          </div>
        </div>
        <div className="hidden sm:flex shrink-0 items-center gap-1 text-xs font-semibold text-primary-foreground/90">
          Tap to submit
          <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
        </div>
      </button>
    );
  }

  const condition = teamReady
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
