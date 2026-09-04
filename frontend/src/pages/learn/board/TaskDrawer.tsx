import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient, type UseMutationResult } from "@tanstack/react-query";
import { Check, ExternalLink, Play, X, type LucideIcon } from "lucide-react";
import {
  completeChecklistItem, getChecklistItemGuidelineVideoUrlApi, getChecklistItemPdfUrlApi, submitChecklistItem,
  type LmsProgramChecklistItem,
} from "@/api/lms";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PdfViewer } from "@/components/documents/PdfViewer";
import { VideoPlayer } from "@/components/video/VideoPlayer";
import { isKnownEmbedHost, toEmbedUrl } from "@/lib/embed";
import { ensureAbsoluteUrl } from "@/lib/utils";
import {
  iconForItem, MISSION_STEP_LABELS, navTargetFor, saveBoardScrollPosition, type MissionStepKey, type NavTarget,
} from "./roadmap";

const SELF_CHECK_TYPES = new Set<LmsProgramChecklistItem["item_type"]>(["manual", "pdf", "external_link", "session"]);

/** Per-item, per-browser "did they open the guideline yet" flag — the
 * final CTA stays disabled until this is true (design spec: "The guideline
 * must be viewed before the submission/complete step is enabled"). Not
 * server state — same posture the drawer takes toward "opened" vs.
 * "completed", and cheap to lose (worst case: re-open the guideline). A
 * `video` guideline never sets this via localStorage — see its own note
 * where `guidelineOpened`'s initial state is computed. */
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

interface DrawerBodyProps {
  item: LmsProgramChecklistItem;
  onClose: () => void;
  hasGuideline: boolean;
  effectiveGuidelineKind: string | null;
  guidelineOpened: boolean;
  openGuideline: () => void;
  target: NavTarget;
  workLabel: string;
  doWork: () => void;
  submissionReference: string | null;
  guidelineVideoUploaded: boolean;
  guidelineVideoUrl: string | undefined;
  isAutoTracked: boolean;
  isSubmission: boolean;
  isSelfCheck: boolean;
  done: boolean;
  awaiting: boolean;
  canSubmit: boolean;
  pastDeadline: boolean;
  submitUrl: string;
  setSubmitUrl: (url: string) => void;
  submitMutation: UseMutationResult<LmsProgramChecklistItem, Error, string>;
  Icon: LucideIcon;
  completeMutation: UseMutationResult<LmsProgramChecklistItem, Error, void>;
}

/** One task, three sections top to bottom: an optional **Guide** (a button
 * that opens a PDF/link, or an inline video area — never both, never a
 * numbered step), the **item** itself (what it actually is: a course/
 * mission's progress tracks automatically, a link/session shows what to
 * open or attend, a submission shows its paste-back form), and exactly one
 * **CTA** at the bottom — "Go to the course/mission" for anything
 * auto-tracked, "Submit for review" for a submission, "Mark as done" for
 * everything else. Never more than one primary action at a time (2026-09
 * redesign — the old numbered guideline→work→submit step list read as three
 * separate tasks instead of one).
 *
 * Split out to module scope (not declared inside `TaskDrawer`, which it
 * used to be) — a function declared *inside* a component's render body gets
 * a new identity every render, so React treated every re-render as "a
 * different component" and remounted this whole subtree from scratch
 * instead of diffing it. That's invisible for static content but destroys
 * DOM nodes with focus/selection state — the submission `<input>` below
 * lost focus on every keystroke because typing calls `setSubmitUrl` in
 * `TaskDrawer`, which re-rendered it, which remounted this. Everything this
 * used to reach via closure is now an explicit prop instead. */
function DrawerBody({
  item, onClose, hasGuideline, effectiveGuidelineKind, guidelineOpened, openGuideline, target, workLabel, doWork,
  submissionReference, guidelineVideoUploaded, guidelineVideoUrl, isAutoTracked, isSubmission, isSelfCheck, done,
  awaiting, canSubmit, pastDeadline, submitUrl, setSubmitUrl, submitMutation, Icon, completeMutation,
}: DrawerBodyProps) {
  return (
    <>
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-bold uppercase tracking-[0.06em] text-primary truncate">
          {item.checkpoint_label ?? "Task"} · {item.item_type === "mission_run" && item.mission_step_key ? MISSION_STEP_LABELS[item.mission_step_key as MissionStepKey] : "Step"}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
        >
          <X size={17} />
        </button>
      </div>

      <div className="flex flex-col gap-1.5">
        <h2 className="font-display text-[26px] md:text-2xl font-extrabold tracking-tight text-foreground">{item.title}</h2>
        {item.description && <p className="text-base text-muted-foreground">{item.description}</p>}
        {item.deadline_at && (
          <p className="text-sm text-muted-foreground">
            Due {new Date(item.deadline_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
          </p>
        )}
      </div>

      {done && (
        <div className="flex items-center gap-1.5 text-base font-semibold text-emerald-600 dark:text-emerald-500">
          <Check size={19} /> Cleared
        </div>
      )}
      {awaiting && <p className="text-base font-medium text-primary">Awaiting instructor review</p>}

      {/* Guide — optional, only when this item has one. A video is shown
          directly inline (nothing to "open"); a PDF/link gets a button. */}
      {hasGuideline && (
        <div className="flex flex-col gap-2.5 rounded-2xl ring-1 ring-border p-4 bg-muted/30">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Guide</span>
            {guidelineOpened && effectiveGuidelineKind !== "video" && (
              <span className="flex items-center gap-1 text-xs font-semibold text-emerald-600 dark:text-emerald-500">
                <Check size={13} /> Viewed
              </span>
            )}
          </div>
          {effectiveGuidelineKind === "video" ? (
            guidelineVideoUploaded ? (
              guidelineVideoUrl ? (
                <VideoPlayer
                  info={{ provider: "upload", mode: "direct", status: "ready", url: guidelineVideoUrl }}
                  title="Guideline video"
                  className="aspect-video rounded-lg overflow-hidden border border-border bg-black"
                />
              ) : (
                <div className="aspect-video rounded-lg border border-dashed border-border flex items-center justify-center text-sm text-muted-foreground bg-muted/20">
                  Loading video…
                </div>
              )
            ) : item.guideline_url ? (
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
                  className="flex items-center gap-1.5 text-base text-primary hover:underline"
                >
                  Watch the video <ExternalLink size={15} />
                </a>
              )
            ) : (
              <div className="flex items-center gap-2.5 rounded-lg border border-dashed border-border px-4 py-3.5 text-sm text-muted-foreground">
                <Play size={17} /> Start here · 3 min — video coming soon
              </div>
            )
          ) : (
            <Button variant="outline" onClick={openGuideline} className="h-12 text-base gap-2 justify-start">
              <Icon className="size-[18px]" />
              {effectiveGuidelineKind === "pdf" ? "View guideline (PDF)" : "Open guideline"}
              {guidelineOpened && <Check size={15} className="ml-auto text-emerald-600 dark:text-emerald-500" />}
            </Button>
          )}
        </div>
      )}

      {/* The item itself — what it actually is, distinct from its guide. */}
      {item.item_type === "external_link" && (
        <button
          type="button" onClick={doWork}
          className="flex items-center justify-between gap-3 rounded-xl ring-1 ring-border p-4 text-left hover:bg-foreground/5 transition-colors"
        >
          <span className="text-base font-semibold text-foreground">{workLabel}</span>
          <ExternalLink size={17} className="text-muted-foreground shrink-0" />
        </button>
      )}

      {item.item_type === "session" && (
        <div className="flex flex-col gap-1 rounded-xl ring-1 ring-border p-4 text-sm">
          {item.session_date && (
            <span className="font-semibold text-foreground">
              {new Date(item.session_date).toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })}
            </span>
          )}
          {item.session_starts_at && <span className="text-muted-foreground">{item.session_starts_at}</span>}
          {item.session_location && <span className="text-muted-foreground">{item.session_location}</span>}
          {item.session_meeting_url && (
            <a
              href={ensureAbsoluteUrl(item.session_meeting_url)} target="_blank" rel="noreferrer"
              className="flex items-center gap-1.5 text-primary hover:underline mt-1"
            >
              Join link <ExternalLink size={14} />
            </a>
          )}
        </div>
      )}

      {isAutoTracked && (
        <p className="rounded-xl ring-1 ring-border p-4 text-sm text-muted-foreground">
          {target.kind === "course"
            ? "Progress tracks automatically as you work through the course."
            : "Completes automatically once this phase is finished in Madar."}
        </p>
      )}

      {isSubmission && submissionReference && (
        <a
          href={ensureAbsoluteUrl(submissionReference)} target="_blank" rel="noreferrer"
          className="flex items-center gap-1.5 text-base text-primary hover:underline"
        >
          Open the reference link <ExternalLink size={15} />
        </a>
      )}

      {/* Always visible once something's been submitted — done or not —
          so "which submission actually went through" never has to be
          guessed at. Editing stays open after done too: every submission
          item is overridable at any time, individual or team-scoped, up
          until the deadline. */}
      {isSubmission && item.submitted_url && (
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-sm text-muted-foreground bg-muted/50 rounded-lg px-3 py-2">
          <Check className="size-3.5 shrink-0 text-emerald-600 dark:text-emerald-500" />
          <a
            href={ensureAbsoluteUrl(item.submitted_url)} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
            className="text-primary hover:underline truncate max-w-full min-w-0"
          >
            {item.submitted_url}
          </a>
          <span className="min-w-0">
            · Submitted
            {item.updated_at &&
              ` ${new Date(item.updated_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`}
            {item.updated_by_name && ` by ${item.updated_by_name}`}
          </span>
        </div>
      )}

      {isSubmission && (
        pastDeadline ? (
          <p className="text-sm font-medium text-amber-600 dark:text-amber-500">
            Deadline passed — no longer accepting submissions
          </p>
        ) : (
          <div className="flex flex-col gap-2.5" onClick={(e) => e.stopPropagation()}>
            {item.submission_prompt && <p className="text-sm text-muted-foreground">{item.submission_prompt}</p>}
            <input
              value={submitUrl || item.submitted_url || ""}
              onChange={(e) => setSubmitUrl(e.target.value)}
              placeholder="Paste your link…"
              disabled={!canSubmit}
              className="h-12 px-4 border border-border bg-background text-foreground rounded-lg text-base focus:outline-none focus:border-primary transition-colors disabled:opacity-50"
            />
          </div>
        )
      )}

      {/* Exactly one primary action, whatever this item's type. */}
      <div className="mt-auto pt-3 flex flex-col gap-2.5 border-t border-border">
        {!canSubmit && (isSubmission || isSelfCheck) && !done && !awaiting && (
          <p className="text-xs text-muted-foreground text-center">View the guide above first</p>
        )}
        {isAutoTracked && (
          <Button onClick={doWork} className="h-[52px] text-base gap-2">{workLabel}</Button>
        )}
        {isSubmission && !pastDeadline && (
          <Button
            disabled={!canSubmit || (!submitUrl && !item.submitted_url) || submitMutation.isPending}
            onClick={() => submitMutation.mutate(submitUrl || item.submitted_url || "")}
            className="h-[52px] text-base"
          >
            {submitMutation.isPending ? "Submitting…" : item.submitted_url ? "Replace submission" : "Submit for review"}
          </Button>
        )}
        {isSelfCheck && !done && !awaiting && (
          <Button
            disabled={!canSubmit || completeMutation.isPending}
            onClick={() => completeMutation.mutate()}
            className="h-[52px] text-base"
          >
            {completeMutation.isPending ? "Marking done…" : item.requires_confirmation ? "Mark as done (needs sign-off)" : "Mark as done"}
          </Button>
        )}
      </div>
    </>
  );
}

/** Design spec §"Task drawer" — guide → item → one CTA, without unloading
 * the board. Desktop: 360px right panel over a blurred/scrimmed board.
 * Mobile: bottom sheet. The per-type action logic (course routing, mission
 * routing, PDF dialog, submit/complete mutations, deadline handling) is
 * lifted from the old `ChecklistItemRow` (`LearnChecklist.tsx`, now
 * retired), not rewritten. */
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

  // A `pdf`-type item's own content IS its guideline even when
  // `guideline_kind` was never separately set on it — same file, same
  // `pdf_path`/upload, see the backend's own note on this reuse.
  const effectiveGuidelineKind = item?.guideline_kind ?? (item?.item_type === "pdf" ? "pdf" : null);

  // Reset per item via the parent's `key={item?.id}` remounting this whole
  // component (RoadmapBoard.tsx), not a useEffect+setState reset on
  // item/assignmentId change — React's own recommendation for "state that
  // should reset when a prop changes" (see "you might not need an effect"),
  // and it's what a set-state-in-effect lint rule now catches directly
  // (previously masked by DrawerBody being defined as a nested component,
  // which apparently kept the linter from fully analyzing this effect).
  // A `video` guideline is shown inline with nothing to click "open" — it
  // seeds as already-viewed rather than gating on a localStorage flag that
  // would never get set.
  const [guidelineOpened, setGuidelineOpened] = useState(() => {
    if (!item) return false;
    if (effectiveGuidelineKind === "video") return true;
    return readGuidelineViewed(assignmentId, item.id);
  });

  const { data: pdfUrl, isLoading: pdfLoading, isError: pdfError } = useQuery({
    queryKey: ["lms-checklist-item-pdf-url", assignmentId, item?.id],
    queryFn: () => getChecklistItemPdfUrlApi(assignmentId, item!.id),
    enabled: !!item && viewingPdf && effectiveGuidelineKind === "pdf",
  });

  const { data: guidelineVideoUrl } = useQuery({
    queryKey: ["lms-checklist-item-guideline-video-url", assignmentId, item?.id],
    queryFn: () => getChecklistItemGuidelineVideoUrlApi(assignmentId, item!.id),
    enabled: !!item && effectiveGuidelineKind === "video" && !!item.guideline_video_uploaded,
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
    // 'video' renders inline in DrawerBody — nothing to dispatch here.
  };

  const target = navTargetFor(item);
  const doWork = () => {
    saveBoardScrollPosition(assignmentId);
    // `program` rides along so the destination can offer a "back to your
    // program" nudge on completion (CompletionCelebration) — only these two
    // targets have one wired up so far.
    if (target.kind === "course") void navigate({ to: `/learn/courses/${target.courseId}`, search: { program: assignmentId } as never });
    else if (target.kind === "design") {
      void navigate({
        to: `/learn/missions/design/${target.attemptId}`,
        search: { ...(target.phase ? { phase: target.phase } : {}), program: assignmentId } as never,
      });
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
  // Once the deadline passes, the paste-link form is hidden — already
  // submitted content above stays visible/reviewable.
  const pastDeadline = !!item.deadline_at && new Date(item.deadline_at) < new Date();
  const Icon = iconForItem(item);

  const bodyProps: DrawerBodyProps = {
    item, onClose, hasGuideline, effectiveGuidelineKind, guidelineOpened, openGuideline, target, workLabel, doWork,
    submissionReference, guidelineVideoUploaded: !!item.guideline_video_uploaded, guidelineVideoUrl, isAutoTracked,
    isSubmission, isSelfCheck, done, awaiting, canSubmit, pastDeadline, submitUrl,
    setSubmitUrl, submitMutation, Icon, completeMutation,
  };

  return (
    <>
      {/* Scrim */}
      <div
        className="fixed inset-0 z-40 bg-black/55 dark:bg-black/55 transition-opacity"
        style={{ background: "var(--drawer-scrim, rgba(5,3,10,0.55))" }}
        onClick={onClose}
      />
      {/* Desktop right panel — 640px, not a viewport-relative width: wide
          enough to give an embedded video real size without turning into
          most of the screen on a large monitor. */}
      <div className="hidden md:flex fixed inset-y-0 right-0 z-50 w-[720px] flex-col bg-card p-8 gap-5 shadow-[-28px_0_60px_-30px_rgba(23,17,31,0.6)] overflow-y-auto">
        <DrawerBody {...bodyProps} />
      </div>
      {/* Mobile bottom sheet */}
      <div className="md:hidden fixed inset-x-0 bottom-0 z-50 flex flex-col rounded-t-[22px] bg-card px-5 pt-3 pb-6 gap-4 max-h-[86vh] overflow-y-auto">
        <div className="mx-auto h-1.5 w-12 rounded-full bg-border shrink-0" />
        <DrawerBody {...bodyProps} />
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
}
