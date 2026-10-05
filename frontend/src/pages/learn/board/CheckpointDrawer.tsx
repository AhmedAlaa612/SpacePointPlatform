import { isAxiosError } from "axios";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Circle, Flag, Lock, X } from "lucide-react";
import { lockCheckpointChecklist, type LmsProgramChecklistItem } from "@/api/lms";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { checkpointSectionItems } from "./roadmap";

/** Same 2-line pattern FinalGateBar/TaskDrawer duplicate locally. */
function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail;
  return fallback;
}

/** A checkpoint gate's modal — deliberately simple, same shape as the
 * Final Submit confirmation dialog: title + section X/Y + one glowing
 * lock action when ready, or the locked-by line when already locked. */
export function CheckpointDrawer({
  item, items, assignmentId, hasTeam, onClose, onChanged,
}: {
  item: LmsProgramChecklistItem;
  items: LmsProgramChecklistItem[];
  assignmentId: string;
  hasTeam: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const toast = useToast();
  const section = checkpointSectionItems(items, item.id);
  const doneCount = section.filter((i) => i.status === "done").length;
  const ready = section.length > 0 ? doneCount === section.length : true;
  const locked = item.status === "done";

  const lockMutation = useMutation({
    mutationFn: () => lockCheckpointChecklist(assignmentId, item.id),
    onSuccess: () => {
      toast.success("Checkpoint locked — onward!");
      onChanged();
      onClose();
    },
    onError: (err) => toast.error(errorDetail(err, "Couldn't lock this checkpoint.")),
  });

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md p-6 bg-card border-border">
        <DialogHeader>
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded-full">
              Team Checkpoint
            </span>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            >
              <X size={17} />
            </button>
          </div>
          <DialogTitle className="text-xl font-bold font-display text-foreground flex items-center gap-2">
            <Flag size={18} className="text-primary shrink-0" />
            {item.title}
          </DialogTitle>
        </DialogHeader>

        <div className="mt-3 space-y-4">
          {item.description && <p className="text-xs text-muted-foreground leading-relaxed">{item.description}</p>}

          <div className="p-4 rounded-xl border border-border bg-muted/30 space-y-2">
            <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-muted-foreground">
              <span>Section progress</span>
              <span className="font-display text-sm text-foreground">{doneCount}/{section.length}</span>
            </div>
            {section.length === 0 ? (
              <p className="text-xs text-muted-foreground">No team tasks in this section — ready to lock.</p>
            ) : (
              <ul className="space-y-1.5">
                {section.map((s) => (
                  <li key={s.id} className="flex items-center gap-2 text-xs">
                    {s.status === "done" ? (
                      <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
                    ) : (
                      <Circle size={14} className="text-muted-foreground shrink-0" />
                    )}
                    <span className={cn("truncate", s.status === "done" ? "text-foreground" : "text-muted-foreground")}>
                      {s.title}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {locked ? (
            <div className="flex items-center justify-center gap-2 p-3.5 rounded-xl bg-primary/10 border border-primary/25 text-primary text-sm font-semibold">
              <Lock size={16} />
              {item.updated_by_name
                ? `Locked by ${item.updated_by_name}${item.updated_at ? ` on ${new Date(item.updated_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}` : ""}`
                : "Locked"}
            </div>
          ) : !hasTeam ? (
            <p className="text-xs text-muted-foreground text-center">Join a team to lock this gate.</p>
          ) : (
            <button
              type="button"
              disabled={!ready || lockMutation.isPending}
              onClick={() => lockMutation.mutate()}
              title={ready ? undefined : "Finish every team task above first"}
              className="gate-beacon-border w-full flex items-center justify-center gap-2 px-5 py-3 rounded-xl border-[2.5px] bg-primary text-primary-foreground font-extrabold text-sm tracking-wide shadow-md shadow-primary/25 hover:shadow-lg hover:shadow-primary/35 transition-all duration-150 disabled:opacity-50 cursor-pointer disabled:pointer-events-none"
            >
              <Lock size={15} />
              {lockMutation.isPending ? "Locking…" : ready ? "Lock Checkpoint" : `Finish section first (${doneCount}/${section.length})`}
            </button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
