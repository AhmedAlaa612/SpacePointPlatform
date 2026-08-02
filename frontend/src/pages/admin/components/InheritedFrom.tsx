import { RotateCcw } from "lucide-react"
import { cn } from "@/lib/utils"

/**
 * One way to say "this is inherited unless you override it" (2026-08-02).
 *
 * Program → cohort → session inheritance used to be presented four different
 * ways on the same screen: prose for materials, a grey info box for kits, a
 * purple pill for openings, and a badge + "currently using" sentence + revert
 * button for location/warehouse. The last one was the clearest, so it's the
 * one generalised here and used by all four.
 *
 * `overridden` is the only thing that decides the badge — the underlying
 * model is unchanged everywhere ("" / empty / no rows still means inherit).
 */
export function InheritedFrom({
  label, icon, level = "cohort", overridden, using, autoResolved = false, onRevert, hint, className,
}: {
  /** Section label, e.g. "Location". Omit for a bare pill. */
  label?: string
  icon?: React.ReactNode
  /** Where the inherited value comes from when not overridden. */
  level?: "program" | "cohort"
  overridden: boolean
  /** What actually applies right now, override or not. */
  using?: React.ReactNode
  /** True when "not overridden" means resolved automatically rather than
   *  inherited from the level above (the warehouse case). */
  autoResolved?: boolean
  onRevert?: () => void
  hint?: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        {label && (
          <span className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            {icon} {label}
          </span>
        )}
        <InheritedBadge level={level} overridden={overridden} autoResolved={autoResolved} />
      </div>

      {using !== undefined && (
        <p className="text-xs text-muted-foreground">
          Currently using: <span className="text-foreground font-medium">{using}</span>
          {!overridden && !autoResolved ? ` (from ${level})` : ""}
        </p>
      )}

      {overridden && onRevert && (
        <button
          type="button"
          onClick={onRevert}
          className="w-fit h-8 px-3 border border-border rounded-xl text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors whitespace-nowrap inline-flex items-center gap-1.5"
        >
          <RotateCcw size={12} /> {autoResolved ? "Revert to automatic" : `Revert to ${level} default`}
        </button>
      )}

      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

/** The pill on its own, for rows inside a list (a single kit, say) where the
 *  full label/using/revert treatment would be far too much furniture. */
export function InheritedBadge({
  level = "cohort", overridden, autoResolved = false, className,
}: {
  level?: "program" | "cohort"
  overridden: boolean
  autoResolved?: boolean
  className?: string
}) {
  return (
    <span
      className={cn(
        "text-[10px] font-semibold px-1.5 py-0.5 rounded-full border shrink-0",
        overridden
          ? "bg-primary/10 text-primary border-primary/20"
          : "bg-muted text-muted-foreground border-border",
        className,
      )}
    >
      {overridden
        ? "Overridden for this session"
        : autoResolved ? "Resolved automatically" : `Inherited from ${level}`}
    </span>
  )
}
