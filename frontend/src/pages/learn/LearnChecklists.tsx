import { useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, ClipboardCheck, Trophy } from "lucide-react";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/primitives";
import { fetchMyChecklists } from "@/api/lms";
import { cn } from "@/lib/utils";

/** /learn/checklists — the LMS Program redesign (2026-08-21): every
 * checklist a student has been assigned, auto-populated at registration
 * time. Distinct from /learn/programs/$cohortId (LearnProgram.tsx, the
 * public catalog's program detail/registration page) and from
 * /learn/my-programs (the older, still-live courses-only cohort view) —
 * this is the new mixed-item-type checklist entity.
 */
export default function LearnChecklists() {
  const navigate = useNavigate();
  const { data: checklists, isLoading } = useQuery({ queryKey: ["lms-my-checklists"], queryFn: fetchMyChecklists });

  return (
    <div className="mx-auto max-w-[1320px] px-5 sm:px-8 lg:px-14 py-8 sm:py-10 flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight">Programs</h1>
        <p className="text-sm text-muted-foreground mt-1.5">
          Every checklist your instructors and ops have assigned you — courses, mission runs, submissions, and manual steps, all in one place.
        </p>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
      {checklists && checklists.length === 0 && (
        <EmptyState title="No programs assigned yet" hint="Once you're assigned a program checklist, it'll show up here." />
      )}

      <div className="grid sm:grid-cols-2 gap-4">
        {checklists?.map((c) => (
          <Card
            key={c.assignment_id}
            className="cursor-pointer hover:ring-primary/30 transition-shadow p-5 flex flex-col gap-4"
            onClick={() => void navigate({ to: `/learn/checklists/${c.assignment_id}` })}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                {c.cohort_name && (
                  <div className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground mb-1">{c.cohort_name}</div>
                )}
                <div className="font-display text-lg font-semibold leading-snug">{c.name}</div>
              </div>
              <span
                className={cn(
                  "shrink-0 text-[10px] font-bold uppercase tracking-wide rounded-md px-2 py-1",
                  c.pct === 100 ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                    : c.items_done > 0 ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground",
                )}
              >
                {c.pct === 100 ? "Complete" : c.items_done > 0 ? "In progress" : "Not started"}
              </span>
            </div>

            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>{c.items_done} of {c.items_total} steps</span>
                <span>{c.pct}%</span>
              </div>
              <div className="h-1.5 rounded-full bg-muted relative overflow-hidden">
                <div
                  className={cn("absolute inset-y-0 left-0 rounded-full", c.pct === 100 ? "bg-emerald-500" : "bg-primary")}
                  style={{ width: `${c.pct}%` }}
                />
              </div>
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-border">
              {c.pct === 100 ? (
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Trophy className="size-3.5" />
                  {c.certificate_earned ? "Certificate earned" : c.certificate_required ? "Awaiting certificate" : "All done"}
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground min-w-0">
                  <ClipboardCheck className="size-3.5 shrink-0" />
                  <span className="truncate">Next: <span className="text-foreground font-medium">{c.next_item_title}</span></span>
                </div>
              )}
              <span className="shrink-0 text-sm font-semibold text-primary flex items-center gap-1">
                {c.items_done > 0 ? "Continue" : "Start"}
                <ChevronRight className="size-4" />
              </span>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
