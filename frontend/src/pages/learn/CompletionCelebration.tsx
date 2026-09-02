import { CheckCircle2 } from "lucide-react";
import { useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";

/** The "you're done, here's the way back" popup (2026-09) — fires from
 * Madar (a phase, or the whole mission) and a finished course, but only
 * when the student got there from a checklist tile in the first place
 * (a `?program=` search param carries that origin through the nav —
 * see TaskDrawer's `doWork`). Landing on `/learn` already sends a
 * program student straight to their board and the sidebar carries a
 * permanent quick-return card, so this isn't the only way back — it's
 * the moment-of-completion nudge, shown once per thing finished (each
 * caller owns its own "have I shown this already" guard). */
export function CompletionCelebration({
  open, onOpenChange, title, subtitle, assignmentId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  subtitle: string;
  assignmentId: string;
}) {
  const navigate = useNavigate();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[380px]">
        <div className="flex flex-col items-center gap-4 py-3 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-500 animate-check-pop">
            <CheckCircle2 className="size-9" />
          </div>
          <div className="flex flex-col gap-1">
            <DialogTitle className="font-display text-xl font-bold text-foreground">{title}</DialogTitle>
            <DialogDescription className="text-sm text-muted-foreground">{subtitle}</DialogDescription>
          </div>
          <Button
            size="xl"
            className="w-full mt-1"
            onClick={() => {
              onOpenChange(false);
              void navigate({ to: "/learn/checklists/$assignmentId", params: { assignmentId } });
            }}
          >
            Back to your program
          </Button>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            Stay here
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
