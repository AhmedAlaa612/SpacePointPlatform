import { useState } from "react";
import { useNavigate, useParams } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen, CheckCircle2, ChevronRight, ClipboardCheck, ExternalLink, FileText, Link2,
  Rocket, Trophy, Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  fetchChecklist, completeChecklistItem, submitChecklistItem,
  type LmsProgramChecklistItem, type LmsProgramItemType,
} from "@/api/lms";

const ITEM_ICON: Record<LmsProgramItemType, typeof BookOpen> = {
  course: BookOpen,
  mission_run: Rocket,
  external_link: Link2,
  submission: Upload,
  article: FileText,
  manual: ClipboardCheck,
};

const ITEM_LABEL: Record<LmsProgramItemType, string> = {
  course: "Course",
  mission_run: "Mission run",
  external_link: "Meeting / link",
  submission: "Submission",
  article: "Article",
  manual: "Manual check-off",
};

/** /learn/checklists/$assignmentId — the LMS Program redesign's student
 * checklist (2026-08-21). Extends LearnPath.tsx's "ledger" pattern: a
 * numbered step list, but each step now carries a type-specific icon,
 * status, and action instead of only ever being a course link.
 */
export default function LearnChecklist() {
  const { assignmentId } = useParams({ strict: false }) as { assignmentId: string };
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: checklist, isLoading, error } = useQuery({
    queryKey: ["lms-checklist", assignmentId],
    queryFn: () => fetchChecklist(assignmentId),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["lms-checklist", assignmentId] });

  if (error) return <div className="mx-auto max-w-[900px] px-5 py-10"><p className="text-sm text-destructive">Couldn't load this program.</p></div>;
  if (isLoading || !checklist) return <div className="mx-auto max-w-[900px] px-5 py-10"><p className="text-sm text-muted-foreground">Loading...</p></div>;

  const requiredItems = checklist.items.filter((i) => !i.optional);
  const done = requiredItems.filter((i) => i.status === "done").length;
  const pct = requiredItems.length ? Math.round((100 * done) / requiredItems.length) : 100;
  const allRequiredDone = requiredItems.length > 0 && done === requiredItems.length;
  const currentItemId = checklist.items.find((i) => !i.optional && i.status !== "done")?.id;

  const openItem = (item: LmsProgramChecklistItem) => {
    if (item.item_type === "course" && item.course_id) {
      void navigate({ to: `/learn/courses/${item.course_id}` });
    } else if (item.item_type === "mission_run" && item.mission_attempt_id) {
      if (item.mission_kind === "design") {
        void navigate({ to: `/learn/missions/design/${item.mission_attempt_id}` });
      } else if (item.mission_kind === "operate") {
        void navigate({ to: `/learn/missions/operate/${item.mission_attempt_id}` });
      } else if (item.mission_id) {
        void navigate({ to: `/learn/missions/${item.mission_id}` });
      }
    }
  };

  return (
    <div className="flex flex-col">
      <div className="relative h-[220px] sm:h-[280px] bg-[repeating-linear-gradient(135deg,hsl(var(--primary)/0.09)_0px,hsl(var(--primary)/0.09)_11px,hsl(var(--foreground)/0.014)_11px,hsl(var(--foreground)/0.014)_22px)] flex items-end">
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/55 to-background/10" />
        <div className="relative px-5 sm:px-8 lg:px-14 pb-8 sm:pb-10 flex flex-col gap-2 max-w-2xl">
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-primary">
            Program{checklist.cohort_name ? ` · ${checklist.cohort_name}` : ""}
          </div>
          <h1 className="font-display text-3xl sm:text-4xl font-bold tracking-tight leading-none">{checklist.name}</h1>
          {checklist.description && <p className="text-sm leading-relaxed text-muted-foreground max-w-lg text-pretty">{checklist.description}</p>}
        </div>
      </div>

      <div className="px-5 sm:px-8 lg:px-14 py-8 sm:py-10 flex flex-col gap-8 max-w-[1180px] mx-auto w-full">
        <div className="flex flex-wrap items-center gap-6 sm:gap-10 py-5 border-b border-border">
          <div className="flex items-baseline gap-2">
            <div className="font-display text-3xl sm:text-4xl font-bold tracking-tight">
              {done}<span className="text-lg text-muted-foreground">/{requiredItems.length}</span>
            </div>
            <div className="text-xs text-muted-foreground">steps done</div>
          </div>
          <div className="flex-1 min-w-[120px] h-0.5 bg-border relative">
            <div className="absolute inset-y-0 left-0 bg-primary" style={{ width: `${pct}%` }} />
          </div>
        </div>

        <div className="flex flex-col">
          {checklist.items.map((item) => (
            <ChecklistItemRow
              key={item.id}
              item={item}
              current={item.id === currentItemId}
              onOpen={() => openItem(item)}
              onChanged={invalidate}
              assignmentId={assignmentId}
            />
          ))}
        </div>

        <div className="flex items-center gap-5 sm:gap-6">
          <div className={cn(
            "w-16 h-16 rounded-full ring-1 flex items-center justify-center shrink-0",
            checklist.certificate_earned ? "ring-primary bg-primary/10 text-primary" : "ring-primary/35 text-primary",
          )}>
            <Trophy className="size-6" />
          </div>
          <div className="min-w-0">
            <div className="font-display text-lg sm:text-xl font-semibold tracking-tight">{checklist.name} certificate</div>
            <div className="text-sm text-muted-foreground mt-1 max-w-md text-pretty">
              {!checklist.certificate_required
                ? "This program doesn't gate a certificate."
                : checklist.certificate_earned
                ? "Earned — it's on your profile."
                : allRequiredDone
                ? "All required steps are done — your certificate is issued with your cohort's completion."
                : "Awarded automatically once every required step above is complete."}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ChecklistItemRow({
  item, current, onOpen, onChanged, assignmentId,
}: {
  item: LmsProgramChecklistItem;
  current: boolean;
  onOpen: () => void;
  onChanged: () => void;
  assignmentId: string;
}) {
  const Icon = ITEM_ICON[item.item_type];
  const clickable = item.item_type === "course" || (item.item_type === "mission_run" && !!item.mission_attempt_id);
  const [submitUrl, setSubmitUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const completeMutation = useMutation({
    mutationFn: () => completeChecklistItem(assignmentId, item.id),
    onSuccess: onChanged,
  });
  const submitMutation = useMutation({
    mutationFn: (url: string) => submitChecklistItem(assignmentId, item.id, url),
    onSuccess: () => { onChanged(); setSubmitting(false); },
    onError: () => setSubmitting(false),
  });

  const statusBadge = item.status === "done"
    ? <span className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground"><CheckCircle2 className="size-4" /> Complete</span>
    : item.status === "awaiting_confirmation"
    ? <span className="text-sm font-medium text-primary">Awaiting confirmation</span>
    : current
    ? <span className="text-sm font-semibold text-primary">Up next</span>
    : null;

  return (
    <div
      onClick={clickable ? onOpen : undefined}
      className={cn(
        "grid grid-cols-[44px_1fr_auto] items-start gap-4 py-5 border-b border-border/70",
        item.status === "done" && "opacity-70",
        current && "-mx-3 px-3 rounded-xl bg-primary/5",
        clickable && "cursor-pointer hover:bg-foreground/5 transition-colors",
      )}
    >
      <div className={cn(
        "w-9 h-9 rounded-lg flex items-center justify-center shrink-0",
        item.status === "done" ? "bg-muted text-muted-foreground" : "bg-primary/10 border border-primary/25 text-primary",
      )}>
        <Icon className="size-4" />
      </div>

      <div className="min-w-0 flex flex-col gap-1.5">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-base font-semibold tracking-tight">{item.title}</span>
          <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground border border-border rounded px-1.5 py-0.5">
            {ITEM_LABEL[item.item_type]}
          </span>
          {item.optional && <span className="text-[10px] font-medium italic text-muted-foreground">optional</span>}
        </div>
        {item.description && <p className="text-sm text-muted-foreground max-w-lg">{item.description}</p>}

        {item.item_type === "external_link" && item.external_url && (
          <a href={item.external_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="text-sm text-primary hover:underline w-fit flex items-center gap-1">
            {item.external_url} <ExternalLink className="size-3" />
          </a>
        )}
        {item.item_type === "article" && item.external_url && (
          <a href={item.external_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="text-sm text-primary hover:underline w-fit flex items-center gap-1">
            Read the article <ExternalLink className="size-3" />
          </a>
        )}

        {item.item_type === "submission" && item.status !== "done" && item.status !== "awaiting_confirmation" && (
          <div className="flex flex-col gap-2 mt-1 max-w-md" onClick={(e) => e.stopPropagation()}>
            {item.submission_prompt && <p className="text-xs text-muted-foreground">{item.submission_prompt}</p>}
            <div className="flex gap-2">
              <input
                value={submitUrl || item.submitted_url || ""}
                onChange={(e) => setSubmitUrl(e.target.value)}
                placeholder="Paste your link…"
                className="flex-1 h-9 px-3 border border-border bg-card text-foreground rounded-lg text-sm focus:outline-none focus:border-primary transition-colors"
              />
              <Button
                size="sm"
                disabled={!(submitUrl || item.submitted_url) || submitMutation.isPending}
                onClick={() => { setSubmitting(true); submitMutation.mutate(submitUrl || item.submitted_url || ""); }}
              >
                {submitMutation.isPending && submitting ? "Saving…" : "Save link"}
              </Button>
            </div>
            {item.submitted_url && (
              <Button size="sm" variant="outline" disabled={completeMutation.isPending} onClick={() => completeMutation.mutate()}>
                {completeMutation.isPending ? "Marking done…" : "Mark as done"}
              </Button>
            )}
          </div>
        )}

        {(item.item_type === "external_link" || item.item_type === "article" || item.item_type === "manual")
          && item.status !== "done" && item.status !== "awaiting_confirmation" && (
          <Button
            size="sm" className="w-fit mt-1"
            disabled={completeMutation.isPending}
            onClick={(e) => { e.stopPropagation(); completeMutation.mutate(); }}
          >
            {completeMutation.isPending ? "Marking done…" : item.requires_confirmation ? "Mark as done (needs sign-off)" : "Mark as done"}
          </Button>
        )}
      </div>

      <div className="flex items-center gap-2 justify-self-end whitespace-nowrap">
        {statusBadge}
        {clickable && <ChevronRight className="size-4 text-muted-foreground" />}
      </div>
    </div>
  );
}
