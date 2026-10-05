import { Lock, X, Flag, AlertCircle, ArrowRight } from "lucide-react";
import type { LmsProgramChecklistItem } from "@/api/lms";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { unlockRequirementDetails, iconForItem } from "./roadmap";

/** A dialog opened when a student clicks on a locked task tile, explaining
 * precisely what needs to be done to unlock it. */
export function LockedTaskModal({
  item,
  items,
  onClose,
  onGoToBlocker,
}: {
  item: LmsProgramChecklistItem;
  items: LmsProgramChecklistItem[];
  onClose: () => void;
  onGoToBlocker?: (blockerId: string) => void;
}) {
  const req = unlockRequirementDetails(items, item);
  const Icon = iconForItem(item);

  // Find blocker item to enable direct navigation if possible
  const blockerItem = items.find((i) => i.title === req.blockerTitle);

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md p-6 bg-card border-border">
        <DialogHeader>
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground bg-muted border border-border px-2 py-0.5 rounded-full flex items-center gap-1">
              <Lock size={10} /> Locked Step
            </span>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            >
              <X size={15} />
            </button>
          </div>
          <DialogTitle className="text-lg font-bold font-display text-foreground flex items-center gap-2">
            <Icon size={18} className="text-muted-foreground shrink-0" />
            {item.title}
          </DialogTitle>
        </DialogHeader>

        <div className="mt-4 space-y-4">
          <div className="p-4 rounded-xl border border-border/80 bg-muted/40 space-y-2">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
              {req.type === "checkpoint" ? (
                <Flag size={14} className="text-primary shrink-0" />
              ) : (
                <AlertCircle size={14} className="text-amber-500 shrink-0" />
              )}
              <span>How to unlock</span>
            </div>
            <p className="text-sm text-foreground font-medium leading-relaxed">
              {req.message}
            </p>
          </div>

          <div className="flex items-center justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={onClose}>
              Got it
            </Button>
            {blockerItem && onGoToBlocker && (
              <Button
                size="sm"
                onClick={() => {
                  onClose();
                  onGoToBlocker(blockerItem.id);
                }}
                className="gap-1.5"
              >
                Go to task <ArrowRight size={13} />
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
