import { useState, useEffect } from "react";
import { CheckCircle2, Check } from "lucide-react";
import { useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { EmojiRating } from "@/components/ui/EmojiRating";
import { useCourseRating } from "@/api/course_ratings";

/** The "you're done, here's the way back" popup (2026-09) — fires from
 * Madar (confirming a phase, in `MadarPhaseDrawer`) and a finished course.
 * `assignmentId` is only non-empty when the student got there from a
 * checklist tile in the first place (a `?program=` search param carries
 * that origin through the nav — see `TaskDrawer`'s `doWork`); when it's
 * empty (Madar opened straight from the Missions hub) the primary button
 * just closes the dialog instead of linking to a checklist that doesn't
 * apply. Landing on `/learn` already sends a program student straight to
 * their board and the sidebar carries a permanent quick-return card, so
 * this isn't the only way back — it's the moment-of-completion nudge,
 * shown once per thing finished (each caller owns its own "have I shown
 * this already" guard). */
export function CompletionCelebration({
  open, onOpenChange, title, subtitle, assignmentId, courseId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  subtitle: string;
  assignmentId: string;
  courseId?: string;
}) {
  const navigate = useNavigate();
  const [rating, setRating, { reviewText, saveReview, isSubmitting }] = useCourseRating(courseId);
  const [commentOpen, setCommentOpen] = useState(false);
  const [commentDraft, setCommentDraft] = useState(reviewText);
  const [savedSuccess, setSavedSuccess] = useState(false);

  useEffect(() => {
    setCommentDraft(reviewText);
  }, [reviewText]);

  const handleSave = async () => {
    await saveReview(commentDraft);
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 2500);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px]">
        <div className="flex flex-col items-center gap-4 py-3 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-500 animate-check-pop">
            <CheckCircle2 className="size-9" />
          </div>
          <div className="flex flex-col gap-1">
            <DialogTitle className="font-['Outfit'] text-2xl font-bold text-foreground">{title}</DialogTitle>
            <DialogDescription className="text-sm text-muted-foreground">{subtitle}</DialogDescription>
          </div>

          {courseId && (
            <div className="flex flex-col items-center gap-1.5 py-3.5 w-full border-y border-border/80 dark:border-lms-accent-border/30 my-1 bg-muted/10 dark:bg-[#12091f]/40 rounded-xl px-3.5">
              <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                {rating ? "Your Course Rating" : "Rate your experience"}
              </p>
              <EmojiRating value={rating} onChange={setRating} size="sm" />
              {rating && (
                <>
                  <p className="text-xs text-muted-foreground font-medium">
                    Rated {rating}/5 · Click to edit anytime
                  </p>
                  {!commentOpen && !reviewText && (
                    <button
                      type="button"
                      onClick={() => setCommentOpen(true)}
                      className="text-xs text-primary hover:underline mt-0.5 cursor-pointer"
                    >
                      + Add a written review (optional)
                    </button>
                  )}
                  {(commentOpen || reviewText) && (
                    <div className="w-full flex flex-col gap-1.5 mt-2 text-left">
                      <textarea
                        value={commentDraft}
                        onChange={(e) => {
                          setCommentDraft(e.target.value);
                          setSavedSuccess(false);
                        }}
                        placeholder="Share your feedback for the instructor (optional)..."
                        rows={2}
                        className="w-full text-xs p-2.5 rounded-lg bg-background border border-border resize-none focus:outline-none focus:ring-1 focus:ring-primary text-foreground"
                      />
                      <div className="flex items-center justify-between mt-0.5">
                        {savedSuccess ? (
                          <span className="text-xs text-emerald-500 font-medium flex items-center gap-1">
                            <Check className="size-3.5" /> Review saved!
                          </span>
                        ) : (
                          <span />
                        )}
                        {commentDraft !== reviewText && (
                          <button
                            type="button"
                            disabled={isSubmitting}
                            onClick={() => void handleSave()}
                            className="text-xs font-medium px-3 py-1 rounded bg-primary text-primary-foreground hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-50"
                          >
                            {isSubmitting ? "Saving..." : "Save review"}
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          <Button
            size="xl"
            className="w-full mt-1"
            onClick={() => {
              onOpenChange(false);
              if (assignmentId) void navigate({ to: "/learn/checklists/$assignmentId", params: { assignmentId } });
            }}
          >
            {assignmentId ? "Back to your program" : "Back to board"}
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
