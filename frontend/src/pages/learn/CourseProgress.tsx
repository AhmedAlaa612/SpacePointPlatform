import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

/** Shared progress expression (design 1k, option A — bar + percent, the
 * design's own default "everywhere"). One component so every screen stays
 * consistent instead of five hand-rolled bars drifting apart. */
export function CourseProgress({
  value, label, className,
}: { value: number; label?: string; className?: string }) {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <Progress value={value} className="flex-1" />
      <span className="text-xs text-muted-foreground whitespace-nowrap shrink-0">
        {label ?? `${value}%`}
      </span>
    </div>
  );
}
