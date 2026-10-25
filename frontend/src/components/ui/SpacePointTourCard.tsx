import { useEffect, useRef, useState } from "react";
import type { TooltipRenderProps } from "react-joyride";
import { X, ChevronLeft, ChevronRight, Check, HelpCircle } from "lucide-react";
import { useTour } from "@/context/TourContext";
import type { TourActionGuide } from "@/lib/tours";
import { cn } from "@/lib/utils";

/**
 * Custom tooltip card for React Joyride v3 that matches SpacePoint's
 * dark/light theme tokens (bg-popover, border-primary/30, text-foreground).
 */
export function SpacePointTourCard({
  index,
  size,
  step,
  isLastStep,
  backProps,
  closeProps,
  primaryProps,
  skipProps,
  tooltipProps,
}: TooltipRenderProps) {
  return (
    <div
      {...tooltipProps}
      className="w-[min(360px,calc(100vw-2rem))] rounded-2xl border border-primary/30 bg-popover/95 p-5 text-popover-foreground shadow-2xl backdrop-blur-xl"
    >
      {/* Header row: badge + close button */}
      <div className="flex items-center justify-between gap-2 pb-2.5">
        <div className="inline-flex items-center rounded-full border border-primary/25 bg-primary/10 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-primary">
          <span>
            Step {index + 1} of {size}
          </span>
        </div>
        <button
          {...closeProps}
          type="button"
          className="rounded-lg p-1 text-muted-foreground transition-colors hover:bg-foreground/10 hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </div>

      {/* Step title & body */}
      {step.title && (
        <h3 className="font-display text-base font-bold tracking-tight text-foreground">
          {step.title}
        </h3>
      )}
      <div className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
        {step.content}
      </div>

      {/* Progress dots */}
      {size > 1 && (
        <div className="mt-4 flex items-center gap-1">
          {Array.from({ length: size }).map((_, idx) => (
            <span
              key={idx}
              className={
                idx === index
                  ? "h-1.5 w-5 rounded-full bg-primary transition-all"
                  : idx < index
                  ? "h-1.5 w-1.5 rounded-full bg-primary/40 transition-all"
                  : "h-1.5 w-1.5 rounded-full bg-muted-foreground/25 transition-all"
              }
            />
          ))}
        </div>
      )}

      {/* Footer buttons */}
      <div className="mt-4 flex items-center justify-between gap-2 border-t border-border/60 pt-3.5">
        {!isLastStep ? (
          <button
            {...skipProps}
            type="button"
            className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground"
          >
            Skip tour
          </button>
        ) : (
          <span />
        )}

        <div className="flex items-center gap-2">
          {index > 0 && (
            <button
              {...backProps}
              type="button"
              className="inline-flex items-center gap-1 rounded-xl border border-border bg-background/60 px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-foreground/5"
            >
              <ChevronLeft className="size-3.5" />
              Back
            </button>
          )}
          <button
            {...primaryProps}
            type="button"
            className="inline-flex items-center gap-1 rounded-xl bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground shadow-sm transition-opacity hover:opacity-90"
          >
            {isLastStep ? (
              <>
                Done
                <Check className="size-3.5" />
              </>
            ) : (
              <>
                Next
                <ChevronRight className="size-3.5" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Interactive Tutorial & Action Guide Launcher Menu ("What do you want to do?").
 * Lets the user either run the Full Workspace Tour or select a specific live
 * action walkthrough for their role.
 */
export function TutorialLauncherMenu({
  tourAttr = "portal-tutorial-btn",
  compact = false,
  align = "right",
  side = "bottom",
}: {
  tourAttr?: string;
  compact?: boolean;
  align?: "left" | "right";
  side?: "top" | "bottom";
}) {
  const { startTour, startCustomTour, getAvailableActions } = useTour();
  const [open, setOpen] = useState(false);
  const [actions, setActions] = useState<TourActionGuide[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleToggle = () => {
    if (!open) {
      setActions(getAvailableActions());
    }
    setOpen((v) => !v);
  };

  return (
    <div ref={ref} className="relative" data-tour={tourAttr}>
      <button
        type="button"
        onClick={handleToggle}
        aria-label="Tutorials and live guides"
        title="Tutorials & live action guides"
        className={cn(
          "inline-flex items-center gap-1.5 rounded-xl text-xs font-medium text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground cursor-pointer",
          compact ? "p-2.5" : "border border-border/60 bg-background/40 px-3 py-2",
        )}
      >
        <HelpCircle size={compact ? 19 : 15} className="text-primary" />
        {!compact && <span>Tutorial</span>}
      </button>

      {open && (
        <div
          className={cn(
            "absolute z-50 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-2xl border border-border bg-popover text-popover-foreground shadow-2xl",
            align === "left" ? "left-0" : "right-0",
            side === "top" ? "bottom-full mb-2" : "top-full mt-2",
          )}
        >
          <div className="border-b border-border px-4 py-3">
            <p className="text-xs font-bold uppercase tracking-wider text-primary">
              Interactive Guides
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Pick an action to see how it is done live on screen.
            </p>
          </div>

          <div className="max-h-80 overflow-y-auto p-2 space-y-1">
            {/* Option 1: Full Workspace Tour */}
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                startTour();
              }}
              className="flex w-full items-start justify-between gap-2 rounded-xl border border-primary/20 bg-primary/5 px-3 py-2.5 text-left transition-colors hover:bg-primary/10 cursor-pointer"
            >
              <div>
                <p className="text-xs font-semibold text-foreground">
                  Full Workspace Tour
                </p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  Walk through all visible tabs and controls for your role.
                </p>
              </div>
              <ChevronRight className="mt-0.5 size-4 shrink-0 text-primary" />
            </button>

            {/* Role-specific Live Action Guides */}
            {actions.length > 0 && (
              <div className="pt-1.5">
                <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  How do I...
                </p>
                {actions.map((action) => (
                  <button
                    key={action.id}
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      startCustomTour(action.steps);
                    }}
                    className="flex w-full items-start justify-between gap-2 rounded-xl px-3 py-2 text-left transition-colors hover:bg-muted/70 cursor-pointer"
                  >
                    <div>
                      <p className="text-xs font-medium text-foreground">
                        {action.title}
                      </p>
                      <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
                        {action.description}
                      </p>
                    </div>
                    <ChevronRight className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
