import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ExternalLink, Play, X } from "lucide-react";
import {
  completeChecklistItem, getChecklistItemPdfUrlApi, submitChecklistItem, type LmsProgramChecklistItem,
} from "@/api/lms";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PdfViewer } from "@/components/documents/PdfViewer";
import { isKnownEmbedHost, toEmbedUrl } from "@/lib/embed";
import { cn, ensureAbsoluteUrl } from "@/lib/utils";
import { iconForItem, MISSION_STEP_LABELS, navTargetFor, saveBoardScrollPosition, type MissionStepKey } from "./roadmap";

const SELF_CHECK_TYPES = new Set<LmsProgramChecklistItem["item_type"]>(["manual", "pdf", "external_link", "session"]);

/** Per-item, per-browser "did they open the guideline yet" flag — the
 * submit step is disabled until this is true (design spec: "The guideline
 * step must be completed before the submission step is enabled."). Not
 * server state — same posture the drawer takes toward "opened" vs.
 * "completed", and cheap to lose (worst case: re-open the guideline). */
function guidelineViewedKey(assignmentId: string, itemId: string) {
  return `roadmap-guideline-viewed:${assignmentId}:${itemId}`;
}

function readGuidelineViewed(assignmentId: string, itemId: string): boolean {
  try {
    return localStorage.getItem(guidelineViewedKey(assignmentId, itemId)) === "1";
  } catch {
    return false;
  }
}

function markGuidelineViewed(assignmentId: string, itemId: string) {
  try {
    localStorage.setItem(guidelineViewedKey(assignmentId, itemId), "1");
  } catch {
    /* no-op */
  }
}

function StepRow({
  index, status, title, hint, onClick, disabled,
}: {
  index: number;
  status: "done" | "now" | "next" | "upcoming";
  title: string;
  hint?: string;
  onClick?: () => void;
  disabled?: boolean;
}) {
  const pillLabel = status === "done" ? "DONE" : status === "now" ? "NOW" : status === "next" ? "NEXT" : "";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || !onClick}
      className={cn(
        "flex items-start gap-3 rounded-xl p-2.5 text-left transition-colors",
        onClick && !disabled ? "hover:bg-foreground/5 cursor-pointer" : "cursor-default",
      )}
    >
      <span
        className={cn(
          "flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full text-[11px] font-bold mt-0.5",
          status === "done" ? "bg-primary text-primary-foreground" : status === "now" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
        )}
      >
        {status === "done" ? <Check size={12} /> : index}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2 flex-wrap">
          <span className="text-[12.5px] font-semibold text-foreground">{title}</span>
          {pillLabel && (
            <span
              className={cn(
                "text-[9px] font-bold uppercase tracking-wide rounded px-1.5 py-0.5",
                status === "done" ? "text-emerald-600 dark:text-emerald-500" : "text-primary bg-primary/10",
              )}
            >
              {pillLabel}
            </span>
          )}
        </span>
        {hint && <span className="block text-[10.5px] text-muted-foreground mt-0.5">{hint}</span>}
      </span>
    </button>
  );
}

/** Design spec §"Task drawer" — guideline → work → submit, without
 * unloading the board. Desktop: 360px right panel over a blurred/scrimmed
 * board. Mobile: bottom sheet. The per-type action logic (course routing,
 * mission routing, PDF dialog, submit/complete mutations, deadline
 * handling) is lifted from the old `ChecklistItemRow`
 * (`LearnChecklist.tsx`, now retired), not rewritten. */
export function TaskDrawer({
  item, assignmentId, onClose, onChanged,
}: {
  item: LmsProgramChecklistItem | null;
  assignmentId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [submitUrl, setSubmitUrl] = useState("");
  const [viewingPdf, setViewingPdf] = useState(false);
  const [guidelineOpened, setGuidelineOpened] = useState(false);

  useEffect(() => {
    if (item) setGuidelineOpened(readGuidelineViewed(assignmentId, item.id));
    setSubmitUrl("");
  }, [item, assignmentId]);

  // A `pdf`-type item's own content IS its guideline even when
  // `guideline_kind` was never separately set on it — same file, same
  // `pdf_path`/upload, see the backend's own note on this reuse.
  const effectiveGuidelineKind = item?.guideline_kind ?? (item?.item_type === "pdf" ? "pdf" : null);

  const { data: pdfUrl, isLoading: pdfLoading, isError: pdfError } = useQuery({
    queryKey: ["lms-checklist-item-pdf-url", assignmentId, item?.id],
    queryFn: () => getChecklistItemPdfUrlApi(assignmentId, item!.id),
    enabled: !!item && viewingPdf && effectiveGuidelineKind === "pdf",
  });

  const completeMutation = useMutation({
    mutationFn: () => completeChecklistItem(assignmentId, item!.id),
    onSuccess: () => { onChanged(); queryClient.invalidateQueries({ queryKey: ["lms-checklist", assignmentId] }); },
  });
  const submitMutation = useMutation({
    mutationFn: (url: string) => submitChecklistItem(assignmentId, item!.id, url),
    onSuccess: () => { onChanged(); queryClient.invalidateQueries({ queryKey: ["lms-checklist", assignmentId] }); },
  });

  if (!item) return null;

  const openGuideline = () => {
    markGuidelineViewed(assignmentId, item.id);
    setGuidelineOpened(true);
    if (effectiveGuidelineKind === "pdf") {
      setViewingPdf(true);
    } else if (item.guideline_kind === "link" && item.guideline_url) {
      window.open(ensureAbsoluteUrl(item.guideline_url), "_blank", "noreferrer");
    }
    // 'video' opens inline below — nothing to dispatch here.
  };

  const target = navTargetFor(item);
  const doWork = () => {
    saveBoardScrollPosition(assignmentId);
    if (target.kind === "course") void navigate({ to: `/learn/courses/${target.courseId}` });
    else if (target.kind === "design") {
      void navigate({ to: `/learn/missions/design/${target.attemptId}`, search: target.phase ? ({ phase: target.phase } as never) : undefined });
    } else if (target.kind === "operate") void navigate({ to: `/learn/missions/operate/${target.attemptId}` });
    else if (target.kind === "mission") void navigate({ to: `/learn/missions/${target.missionId}` });
    else if (target.kind === "external") window.open(ensureAbsoluteUrl(target.url), "_blank", "noreferrer");
  };
  // A submission item's own `external_url` is an optional reference link
  // (e.g. a Tinkercad template) — a genuine "do the work" destination
  // distinct from its guideline. Only shown when set.
  const submissionReference = item.item_type === "submission" && item.external_url ? item.external_url : null;

  const hasGuideline = !!effectiveGuidelineKind;
  const isAutoTracked = item.item_type === "course" || item.item_type === "mission_run";
  const isSubmission = item.item_type === "submission";
  const isSelfCheck = SELF_CHECK_TYPES.has(item.item_type);
  const done = item.status === "done";
  const awaiting = item.status === "awaiting_confirmation";

  const workLabel =
    target.kind === "course" ? "Open the course" :
    target.kind === "design" ? `Open Madar${item.mission_step_key ? ` · ${MISSION_STEP_LABELS[item.mission_step_key as MissionStepKey]}` : ""}` :
    target.kind === "operate" ? "Open the mission" :
    target.kind === "mission" ? "Open the mission" :
    target.kind === "external" ? "Open the link" : "Open";

  const canSubmit = !hasGuideline || guidelineOpened;
  const Icon = iconForItem(item);

  // Step numbering — computed once, in render order, so it stays correct
  // regardless of which combination of rows actually renders (a plain
  // manual/pdf/session item has no "do the work" row at all; a submission
  // with a reference link gets one in addition to its submit row).
  const showWorkStep = (target.kind !== "none" && target.kind !== "drawer" && !isAutoTracked) || !!submissionReference;
  const showAutoTrackedStep = isAutoTracked;
  const showSubmitStep = !isAutoTracked && (isSubmission || isSelfCheck);
  let stepCounter = 0;
  const guidelineStepIndex = hasGuideline ? ++stepCounter : 0;
  const workStepIndex = showWorkStep ? ++stepCounter : 0;
  const autoTrackedStepIndex = showAutoTrackedStep ? ++stepCounter : 0;
  const submitStepIndex = showSubmitStep ? ++stepCounter : 0;

  return (
    <>
      {/* Scrim */}
      <div
        className="fixed inset-0 z-40 bg-black/55 dark:bg-black/55 transition-opacity"
        style={{ background: "var(--drawer-scrim, rgba(5,3,10,0.55))" }}
        onClick={onClose}
      />
      {/* Desktop right panel */}
      <div className="hidden md:flex fixed inset-y-0 right-0 z-50 w-[360px] flex-col bg-card p-[22px] gap-3.5 shadow-[-28px_0_60px_-30px_rgba(23,17,31,0.6)] overflow-y-auto">
        <DrawerBody item={item} />
      </div>
      {/* Mobile bottom sheet */}
      <div className="md:hidden fixed inset-x-0 bottom-0 z-50 flex flex-col rounded-t-[22px] bg-card px-4 pt-2.5 pb-5 gap-3 max-h-[86vh] overflow-y-auto">
        <div className="mx-auto h-1 w-10 rounded-full bg-border shrink-0" />
        <DrawerBody item={item} />
      </div>

      {effectiveGuidelineKind === "pdf" ? (
        <Dialog open={viewingPdf} onOpenChange={setViewingPdf}>
          <DialogContent className="sm:max-w-[95vw] max-w-[95vw] w-[95vw]">
            <DialogHeader><DialogTitle>{item.title} — Guideline</DialogTitle></DialogHeader>
            {pdfLoading && <p className="text-sm text-muted-foreground py-6">Loading document...</p>}
            {pdfError && <p className="text-sm text-destructive py-6">Couldn't load this document.</p>}
            {pdfUrl && <PdfViewer url={pdfUrl} />}
          </DialogContent>
        </Dialog>
      ) : null}
    </>
  );

  function DrawerBody({ item }: { item: LmsProgramChecklistItem }) {
    return (
      <>
        <div className="flex items-center justify-between gap-2">
          <div className="text-[10px] font-bold uppercase tracking-[0.06em] text-primary truncate">
            {item.checkpoint_label ?? "Task"} · {item.item_type === "mission_run" && item.mission_step_key ? MISSION_STEP_LABELS[item.mission_step_key as MissionStepKey] : "Step"}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            <X size={14} />
          </button>
        </div>

        <div className="flex flex-col gap-1">
          <h2 className="font-display text-[22px] md:text-[18px] font-extrabold tracking-tight text-foreground">{item.title}</h2>
          {item.description && <p className="text-sm text-muted-foreground">{item.description}</p>}
          {item.deadline_at && (
            <p className="text-xs text-muted-foreground">
              Due {new Date(item.deadline_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
            </p>
          )}
        </div>

        {done && (
          <div className="flex items-center gap-1.5 text-sm font-semibold text-emerald-600 dark:text-emerald-500">
            <Check size={16} /> Cleared
          </div>
        )}
        {awaiting && <p className="text-sm font-medium text-primary">Awaiting instructor review</p>}

        <div className="flex flex-col gap-1">
          {hasGuideline && (
            <StepRow
              index={guidelineStepIndex}
              status={guidelineOpened ? "done" : "now"}
              title="View the guideline"
              hint={effectiveGuidelineKind === "video" ? "Short video" : effectiveGuidelineKind === "pdf" ? "PDF guide" : "Opens in a new tab"}
              onClick={openGuideline}
            />
          )}

          {item.guideline_kind === "video" && (
            <div className="ml-9 -mt-1 mb-1">
              {item.guideline_url ? (
                isKnownEmbedHost(item.guideline_url) ? (
                  <div className="aspect-video rounded-lg overflow-hidden border border-border">
                    <iframe
                      src={toEmbedUrl(item.guideline_url)} title="Guideline video" allowFullScreen
                      className="w-full h-full"
                    />
                  </div>
                ) : (
                  <a
                    href={ensureAbsoluteUrl(item.guideline_url)} target="_blank" rel="noreferrer"
                    className="flex items-center gap-1.5 text-sm text-primary hover:underline"
                  >
                    Watch the video <ExternalLink size={12} />
                  </a>
                )
              ) : (
                <div className="flex items-center gap-2 rounded-lg border border-dashed border-border px-3 py-2.5 text-xs text-muted-foreground">
                  <Play size={14} /> Start here · 3 min — video coming soon
                </div>
              )}
            </div>
          )}

          {/* A real external/in-app destination to open — never rendered
              for a "drawer"-kind target (manual/pdf/session/plain
              submission with no reference link), which has nothing to
              navigate to outside the drawer itself. */}
          {showWorkStep && (
            <StepRow
              index={workStepIndex}
              status={done ? "done" : "next"}
              title={submissionReference ? "Open the reference link" : workLabel}
              hint="Opens in a new tab"
              onClick={() => {
                if (submissionReference) window.open(ensureAbsoluteUrl(submissionReference), "_blank", "noreferrer");
                else doWork();
              }}
            />
          )}

          {showAutoTrackedStep ? (
            <StepRow
              index={autoTrackedStepIndex}
              status={done ? "done" : "now"}
              title={workLabel}
              hint={target.kind === "course" ? "Completes automatically once you finish the course" : "Completes automatically once this phase is complete in Madar"}
              onClick={doWork}
            />
          ) : showSubmitStep ? (
            <StepRow
              index={submitStepIndex}
              status={done ? "done" : awaiting ? "done" : canSubmit ? "now" : "upcoming"}
              title={isSubmission ? "Submit for review" : "Mark as done"}
              hint={!canSubmit ? "Opens after you view the guideline" : undefined}
              onClick={undefined}
            />
          ) : null}
        </div>

        {isSubmission && !done && !awaiting && (
          <div className="flex flex-col gap-2" onClick={(e) => e.stopPropagation()}>
            {item.submission_prompt && <p className="text-xs text-muted-foreground">{item.submission_prompt}</p>}
            <input
              value={submitUrl || item.submitted_url || ""}
              onChange={(e) => setSubmitUrl(e.target.value)}
              placeholder="Paste your link…"
              disabled={!canSubmit}
              className="h-10 px-3 border border-border bg-background text-foreground rounded-lg text-sm focus:outline-none focus:border-primary transition-colors disabled:opacity-50"
            />
          </div>
        )}
        {isSubmission && item.submitted_url && (
          <a
            href={ensureAbsoluteUrl(item.submitted_url)} target="_blank" rel="noreferrer"
            className="text-xs text-primary hover:underline truncate"
          >
            Current submission: {item.submitted_url}
          </a>
        )}

        <div className="mt-auto pt-2 flex flex-col gap-2.5 border-t border-border">
          {!done && !awaiting && (
            <p className="text-xs text-muted-foreground">
              Finishing this powers the next step and keeps you on the roadmap — no back-tracking.
            </p>
          )}
          {hasGuideline && (
            <Button onClick={openGuideline} className="h-11">
              <Icon size={14} /> Open guideline
            </Button>
          )}
          {isSubmission && !done && (
            <Button
              variant="outline"
              disabled={!canSubmit || (!submitUrl && !item.submitted_url) || submitMutation.isPending}
              onClick={() => submitMutation.mutate(submitUrl || item.submitted_url || "")}
              className="h-[42px]"
            >
              {submitMutation.isPending ? "Submitting…" : "Go to submission"}
            </Button>
          )}
          {isSelfCheck && !done && !awaiting && (
            <Button
              variant="outline"
              disabled={!canSubmit || completeMutation.isPending}
              onClick={() => completeMutation.mutate()}
              className="h-[42px]"
            >
              {completeMutation.isPending ? "Marking done…" : item.requires_confirmation ? "Mark as done (needs sign-off)" : "Mark as done"}
            </Button>
          )}
        </div>
      </>
    );
  }
}
