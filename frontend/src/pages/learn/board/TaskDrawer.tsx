import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient, type UseMutationResult } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { Check, Copy, ExternalLink, Loader2, Lock, LogOut, Pencil, Plus, Play, Trash2, Users, X, type LucideIcon } from "lucide-react";
import {
  completeChecklistItem, createFormationTeam, getChecklistItemGuidelineVideoUrlApi, getChecklistItemPdfUrlApi,
  joinFormationTeam, leaveFormationTeam, previewFormationJoin, setTeamNameChecklistItem,
  submitChecklistItem, submitChecklistItemText, submitChecklistItemLinks,
  type LmsProgramChecklistItem, type LmsTeamMember, type SubmissionLink, type SubmissionLinkLabel,
  type TeamFormationPreview,
} from "@/api/lms";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PdfViewer } from "@/components/documents/PdfViewer";
import { VideoPlayer, type VideoPlaybackInfo } from "@/components/video/VideoPlayer";
import { isKnownEmbedHost, toEmbedUrl } from "@/lib/embed";
import { ensureAbsoluteUrl } from "@/lib/utils";
import { useToast } from "@/components/ui/toast";
import {
  iconForItem, isSectionFrozen, MISSION_STEP_LABELS, navTargetFor, saveBoardScrollPosition, type MissionStepKey,
} from "./roadmap";

const SELF_CHECK_TYPES = new Set<LmsProgramChecklistItem["item_type"]>(["manual", "pdf", "external_link", "session"]);

/** Same 2-line pattern every other student page in this app already
 * duplicates locally (LearnProfile.tsx, MissionPage.tsx, etc.) rather than
 * a shared import — axios's own `err.message` is a generic "Request
 * failed with status code 400", never the backend's actual reason, so a
 * mutation that skips this shows the student an unhelpful, effectively
 * unhandled-looking error instead of what's really wrong. */
function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail;
  return fallback;
}

/** Does this multi-field submission row have an answer? Reads .text for a
 * text-type field, .url for everything else — including the free-text
 * legacy path (no spec at all), which predates field_type and is always
 * link-only. Mirrors routers/lms/student.py::submit_program_item's own
 * per-field-type check. */
function hasRowValue(link: SubmissionLink | undefined, spec: SubmissionLinkLabel | undefined): boolean {
  if (!link) return false;
  return spec?.field_type === "text" ? !!(link.text ?? "").trim() : !!(link.url ?? "").trim();
}

function hasTableRowValue(link: SubmissionLink | undefined): boolean {
  if (!link) return false;
  if ((link.url ?? "").trim()) return true;
  if ((link.text ?? "").trim()) return true;
  if (link.values) {
    return Object.values(link.values).some((v) => v !== null && v !== undefined && String(v).trim() !== "");
  }
  return false;
}

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
  workLabel: string;
  doWork: () => void;
  submissionReference: string | null;
  guidelineVideoUploaded: boolean;
  guidelineVideoInfo: VideoPlaybackInfo | null | undefined;
  isAutoTracked: boolean;
  isSubmission: boolean;
  isMultiLink: boolean;
  isTeamSetup: boolean;
  teamName: string | null;
  teamCode: string | null;
  teamMembers: LmsTeamMember[];
  assignmentId: string;
  isPoster: boolean;
  onOpenMadar?: () => void;
  isSelfCheck: boolean;
  done: boolean;
  awaiting: boolean;
  canSubmit: boolean;
  pastDeadline: boolean;
  submitUrl: string;
  setSubmitUrl: (url: string) => void;
  submitMutation: UseMutationResult<LmsProgramChecklistItem, Error, string>;
  submitText: string;
  setSubmitText: (text: string) => void;
  submitTextMutation: UseMutationResult<LmsProgramChecklistItem, Error, string>;
  linksInput: SubmissionLink[];
  setLinksInput: (links: SubmissionLink[] | ((prev: SubmissionLink[]) => SubmissionLink[])) => void;
  submitLinksMutation: UseMutationResult<LmsProgramChecklistItem, Error, SubmissionLink[]>;
  Icon: LucideIcon;
  completeMutation: UseMutationResult<LmsProgramChecklistItem, Error, void>;
  teamFinalLocked?: boolean;
  sectionFrozen?: boolean;
  onChanged: () => void;
}

/** Team formation panel — create with code, join with code, switch with
 * confirm, leave, rename. One item: when in a team it shows filled state
 * (name editable, code shareable, members); when solo it shows the
 * flowchart branches (create → get code / enter code to join). */
function TeamFormationPanel({
  assignmentId, item, teamName, teamCode, teamMembers, pastDeadline, onChanged,
}: {
  assignmentId: string;
  item: LmsProgramChecklistItem;
  teamName: string | null;
  teamCode: string | null;
  teamMembers: LmsTeamMember[];
  pastDeadline: boolean;
  onChanged: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [createName, setCreateName] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [preview, setPreview] = useState<TeamFormationPreview | null>(null);
  const [confirmLeave, setConfirmLeave] = useState(false);
  const [copied, setCopied] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [editValue, setEditValue] = useState("");
  // Server-confirmed deadline (stale local clock safe) — same posture the
  // drawer takes for every other deadline-gated form.
  const [deadlinePassed, setDeadlinePassed] = useState(false);
  const isLocked = pastDeadline || deadlinePassed;
  const invalidate = () => {
    onChanged();
    void queryClient.invalidateQueries({ queryKey: ["lms-checklist", assignmentId] });
  };
  const renameMutation = useMutation({
    mutationFn: (name: string) => setTeamNameChecklistItem(assignmentId, item.id, name),
    onSuccess: () => {
      toast.success("Team name saved!");
      setEditingName(false);
      invalidate();
    },
    onError: (err) => {
      const detail = errorDetail(err, "That name might already be taken — try another.");
      toast.error(detail);
      if (detail.toLowerCase().includes("deadline")) setDeadlinePassed(true);
    },
  });
  const createMutation = useMutation({
    mutationFn: (name: string) => createFormationTeam(assignmentId, item.id, name),
    onSuccess: () => { toast.success("Team created — share your code!"); setCreateName(""); setPreview(null); invalidate(); },
    onError: (err) => toast.error(errorDetail(err, "Couldn't create the team.")),
  });
  const joinMutation = useMutation({
    mutationFn: ({ code, confirm }: { code: string; confirm: boolean }) => joinFormationTeam(assignmentId, item.id, code, confirm),
    onSuccess: () => { toast.success("Joined the team!"); setJoinCode(""); setPreview(null); invalidate(); },
    onError: (err) => {
      // Switch needs confirm — surface the preview so the UI can ask.
      if (isAxiosError(err) && err.response?.status === 409) {
        const detail = typeof err.response?.data?.detail === "string" ? err.response.data.detail : "";
        if (detail.includes("Confirm to leave")) {
          void previewMutation.mutateAsync(joinCode.trim()).then(setPreview).catch(() => toast.error(detail));
          return;
        }
        toast.error(detail || "Couldn't join the team.");
        return;
      }
      toast.error(errorDetail(err, "Couldn't join the team."));
    },
  });
  const previewMutation = useMutation({
    mutationFn: (code: string) => previewFormationJoin(assignmentId, item.id, code),
    onError: (err) => toast.error(errorDetail(err, "No team found with this code.")),
  });
  const leaveMutation = useMutation({
    mutationFn: () => leaveFormationTeam(assignmentId, item.id),
    onSuccess: () => { toast.success("Left the team."); setConfirmLeave(false); invalidate(); },
    onError: (err) => toast.error(errorDetail(err, "Couldn't leave the team.")),
  });

  if (isLocked) {
    return (
      <div className="flex flex-col gap-2.5 rounded-xl ring-1 ring-border p-4 text-sm" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Users size={16} /> {teamName ? `Team ${teamName}` : "Team formation"}
        </div>
        {teamName && (
          <>
            {teamCode && (
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">Team code:</span>
                <code className="font-mono font-bold tracking-widest text-foreground">{teamCode}</code>
              </div>
            )}
            {teamMembers.length > 0 && (
              <p className="text-sm text-muted-foreground">{teamMembers.length} member{teamMembers.length === 1 ? "" : "s"} · {teamMembers.map((m) => m.name ?? "—").join(", ")}</p>
            )}
          </>
        )}
        <p className="text-sm font-medium text-amber-600 dark:text-amber-500">Deadline passed — teams are locked in</p>
      </div>
    );
  }

  if (!teamName) {
    return (
      <div className="flex flex-col gap-3 rounded-xl ring-1 ring-border p-4 text-sm" onClick={(e) => e.stopPropagation()}>
        <div className="flex flex-col gap-2">
          <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Have a team code?</span>
          <div className="flex gap-2">
            <input
              value={joinCode}
              onChange={(e) => { setJoinCode(e.target.value.toUpperCase()); setPreview(null); }}
              placeholder="Enter code (e.g. K7P2QX)"
              maxLength={16}
              className="h-12 flex-1 min-w-0 px-4 border border-border bg-background text-foreground rounded-lg text-base font-mono uppercase tracking-widest focus:outline-none focus:border-primary transition-colors"
            />
            <Button
              disabled={!joinCode.trim() || previewMutation.isPending || joinMutation.isPending}
              onClick={() => previewMutation.mutate(joinCode.trim(), { onSuccess: (p) => { setPreview(p); if (!p.requires_switch) joinMutation.mutate({ code: joinCode.trim(), confirm: false }); } })}
              className="h-12 px-4 shrink-0"
            >
              {previewMutation.isPending || joinMutation.isPending ? "Joining…" : "Join"}
            </Button>
          </div>
          {preview && (
            <div className="rounded-lg bg-muted/50 px-3 py-2.5 flex flex-col gap-2">
              <p className="text-sm text-foreground">
                Join <span className="font-semibold">{preview.team_name}</span> ({preview.member_count} member{preview.member_count === 1 ? "" : "s"})?
              </p>
              {preview.requires_switch && (
                <p className="text-sm text-amber-600 dark:text-amber-500">
                  You're on {preview.current_team_name} — joining will move you. Your old team is deleted if it goes empty.
                </p>
              )}
              <div className="flex gap-2">
                <Button size="sm" disabled={joinMutation.isPending} onClick={() => joinMutation.mutate({ code: joinCode.trim(), confirm: true })}>
                  {joinMutation.isPending ? "Moving…" : preview.requires_switch ? `Leave ${preview.current_team_name} & join` : "Confirm join"}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setPreview(null)}>Cancel</Button>
              </div>
            </div>
          )}
          {previewMutation.isError && !preview && (
            <p className="text-sm text-destructive">No team found with this code — check it and try again.</p>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="h-px flex-1 bg-border" /> or <span className="h-px flex-1 bg-border" />
        </div>
        <div className="flex flex-col gap-2">
          <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">No code? Create a team</span>
          <div className="flex gap-2">
            <input
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              placeholder="Your team's name"
              maxLength={100}
              className="h-12 flex-1 min-w-0 px-4 border border-border bg-background text-foreground rounded-lg text-base focus:outline-none focus:border-primary transition-colors"
            />
            <Button
              disabled={!createName.trim() || createMutation.isPending}
              onClick={() => createMutation.mutate(createName.trim())}
              className="h-12 px-4 shrink-0"
            >
              {createMutation.isPending ? "Creating…" : "Create"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">You'll get a code to share with teammates.</p>
        </div>
        {item.max_team_size != null && (
          <p className="text-xs text-muted-foreground">Max {item.max_team_size} members per team.</p>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl ring-1 ring-border p-4 text-sm" onClick={(e) => e.stopPropagation()}>
      {/* Team name — big and bold, edit-in-place via the pencil */}
      <div className="flex flex-col gap-1.5">
        {!editingName ? (
          <>
            <div className="flex items-center gap-2">
              <span className="text-xl font-extrabold tracking-tight text-foreground">{teamName}</span>
              <button
                type="button"
                aria-label="Rename team"
                onClick={() => { setEditValue(teamName ?? ""); setEditingName(true); }}
                className="flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"
              >
                <Pencil size={15} />
              </button>
            </div>
            {item.updated_by_name && (
              <span className="text-xs text-muted-foreground">
                Set by {item.updated_by_name}
                {item.updated_at && ` · ${new Date(item.updated_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`}
              </span>
            )}
          </>
        ) : (
          <>
            <input
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              // eslint-disable-next-line jsx-a11y/no-autofocus
              autoFocus
              placeholder="Your team's name"
              maxLength={100}
              className="h-12 px-4 border border-border bg-background text-foreground rounded-lg text-base font-semibold focus:outline-none focus:border-primary transition-colors"
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={!editValue.trim() || renameMutation.isPending}
                onClick={() => renameMutation.mutate(editValue.trim())}
              >
                {renameMutation.isPending ? "Saving…" : "Save"}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setEditingName(false)}>Cancel</Button>
            </div>
          </>
        )}
      </div>
      {/* Members — vertical, bold, one card each */}
      <div className="flex flex-col gap-1.5">
        <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
          Members · {teamMembers.length}
        </span>
        {teamMembers.map((m) => (
          <div key={m.id} className="flex items-center gap-2.5 rounded-lg ring-1 ring-border bg-muted/30 px-3 py-2">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-bold text-primary">
              {(m.name ?? "?").charAt(0).toUpperCase()}
            </span>
            <span className="text-sm font-bold text-foreground">{m.name ?? "—"}</span>
          </div>
        ))}
      </div>
      {teamCode && (
        <div className="flex items-center gap-2 rounded-lg bg-primary/10 border border-primary/25 px-3 py-2.5">
          <div className="flex flex-col">
            <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Team code — share to add members</span>
            <code className="font-mono text-lg font-bold tracking-[0.2em] text-foreground">{teamCode}</code>
          </div>
          <button
            type="button"
            aria-label="Copy team code"
            onClick={() => {
              const done = () => { setCopied(true); window.setTimeout(() => setCopied(false), 1500); };
              if (navigator.clipboard?.writeText) void navigator.clipboard.writeText(teamCode).then(done).catch(done);
              else done();
            }}
            className="ml-auto flex h-9 w-9 items-center justify-center rounded-full bg-background text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            {copied ? <Check size={16} className="text-emerald-600" /> : <Copy size={16} />}
          </button>
        </div>
      )}
      {/* Leave — to join another team, leave first then enter its code */}
      {!confirmLeave ? (
        <button
          type="button"
          onClick={() => setConfirmLeave(true)}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-destructive transition-colors cursor-pointer"
        >
          <LogOut size={14} /> Leave team
        </button>
      ) : (
        <div className="rounded-lg bg-muted/50 px-3 py-2.5 flex flex-col gap-2">
          <p className="text-sm text-foreground">Leave {teamName}? {teamMembers.length <= 1 ? "The team will be deleted." : ""}</p>
          <div className="flex gap-2">
            <Button size="sm" variant="destructive" disabled={leaveMutation.isPending} onClick={() => leaveMutation.mutate()}>
              {leaveMutation.isPending ? "Leaving…" : "Yes, leave"}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setConfirmLeave(false)}>Stay</Button>
          </div>
        </div>
      )}
      {item.max_team_size != null && (
        <p className="text-xs text-muted-foreground">Max {item.max_team_size} members per team.</p>
      )}
    </div>
  );
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
  item, onClose, hasGuideline, effectiveGuidelineKind, guidelineOpened, openGuideline, workLabel, doWork,
  submissionReference, guidelineVideoUploaded, guidelineVideoInfo, isAutoTracked, isSubmission, isMultiLink, isTeamSetup, teamName,
  teamCode, teamMembers, assignmentId,
  isPoster, onOpenMadar, isSelfCheck, done, awaiting, canSubmit, pastDeadline, submitUrl, setSubmitUrl, submitMutation,
  submitText, setSubmitText, submitTextMutation,
  linksInput, setLinksInput, submitLinksMutation,
  Icon, completeMutation,
  teamFinalLocked, sectionFrozen, onChanged,
}: DrawerBodyProps) {
  // A plain (non-multi) submission item can itself be a text field
  // (2026-09-16) — isPoster is excluded on purpose, it's always
  // item_type=="mission_run" and always link-only regardless of this flag.
  const isTextSubmission = item.item_type === "submission" && !isMultiLink && item.submission_field_type === "text";
  // Checkpoint freeze — this team item sits above a locked checkpoint, so
  // every write 409s. Hide all inputs/actions and show the neutral locked
  // notice instead (never the submit button + an error toast).
  const frozen = !!sectionFrozen;
  const inputsHidden = (teamFinalLocked && item.scope === "team") || frozen;
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
          <p className={`text-sm ${pastDeadline ? "text-amber-600 dark:text-amber-500 font-medium" : "text-muted-foreground"}`}>
            {pastDeadline ? "Deadline passed · " : ""}Due {new Date(item.deadline_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
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
              guidelineVideoInfo ? (
                <VideoPlayer
                  info={guidelineVideoInfo}
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

      {/* Poster Template & Madar shortcuts */}
      {isPoster && item.poster_template_url && (
        <button
          type="button"
          onClick={() => window.open(ensureAbsoluteUrl(item.poster_template_url!), "_blank", "noreferrer")}
          className="flex items-center justify-between gap-3 rounded-xl ring-1 ring-border p-4 text-left hover:bg-foreground/5 transition-colors cursor-pointer"
        >
          <span className="text-base font-semibold text-foreground">Open poster template</span>
          <ExternalLink size={17} className="text-muted-foreground shrink-0" />
        </button>
      )}

      {isPoster && onOpenMadar && (
        <button
          type="button"
          onClick={onOpenMadar}
          className="flex items-center justify-between gap-3 rounded-xl ring-1 ring-border p-4 text-left hover:bg-foreground/5 transition-colors cursor-pointer"
        >
          <span className="text-base font-semibold text-foreground">Go to Mission</span>
          <ExternalLink size={17} className="text-muted-foreground shrink-0" />
        </button>
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

      {/* Team setup — formation + rename. One item: create/join/leave with
          codes plus rename, always shared (any teammate, last write wins).
          Frozen by a locked checkpoint → neutral lock notice, no forms. */}
      {isTeamSetup && (
        frozen ? (
          <div className="flex items-center justify-center gap-2 p-3.5 rounded-xl bg-primary/10 border border-primary/25 text-primary text-sm font-semibold">
            <Lock size={16} className="shrink-0 text-muted-foreground" />
            This checkpoint is now locked for your team
          </div>
        ) : (
          <TeamFormationPanel
            assignmentId={assignmentId} item={item}
            teamName={teamName} teamCode={teamCode} teamMembers={teamMembers}
            pastDeadline={pastDeadline}
            onChanged={onChanged}
          />
        )
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
      {isSubmission && item.submission_table_config && item.submitted_links && item.submitted_links.length > 0 && (
        <div className="flex flex-col gap-2 p-3.5 rounded-xl bg-muted/40 border border-border">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
            <Check className="size-3.5 shrink-0 text-emerald-600 dark:text-emerald-500" /> Current Submission
            {item.updated_at && ` · ${new Date(item.updated_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`}
            {item.updated_by_name && ` by ${item.updated_by_name}`}
          </div>
          <div className="overflow-x-auto rounded-lg border border-border/40">
            <table className="w-full text-left text-xs border-collapse min-w-[480px]">
              <thead>
                <tr className="border-b border-border/60 text-muted-foreground bg-muted/20">
                  <th className="py-2 px-2.5 font-semibold w-8 text-center shrink-0">#</th>
                  <th className="py-2 px-2.5 font-semibold min-w-[110px]">{item.submission_table_config.tag_label || "Tag"}</th>
                  {item.submission_table_config.columns?.map((c) => (
                    <th key={c.key} className="py-2 px-2.5 font-semibold min-w-[110px]">{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border/30">
                {item.submitted_links.map((link, idx) => (
                  <tr key={idx} className="hover:bg-muted/30">
                    <td className="py-2 px-2 font-mono text-center text-muted-foreground">{idx + 1}</td>
                    <td className="py-2 px-2 font-semibold text-foreground">{link.tag || link.label || "—"}</td>
                    {item.submission_table_config?.columns?.map((col) => {
                      if (col.type === "link") {
                        const url = link.url || link.values?.[col.key];
                        return (
                          <td key={col.key} className="py-2 px-2">
                            {url ? (
                              <a href={ensureAbsoluteUrl(String(url))} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="text-primary hover:underline flex items-center gap-1">
                                <span className="truncate max-w-[180px]">{String(url)}</span>
                                <ExternalLink size={10} className="shrink-0" />
                              </a>
                            ) : <span className="text-muted-foreground">—</span>}
                          </td>
                        );
                      }
                      const val = link.values?.[col.key];
                      return (
                        <td key={col.key} className="py-2 px-2 text-foreground">
                          {val !== undefined && val !== null && String(val).trim() !== "" ? String(val) : <span className="text-muted-foreground">—</span>}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {isSubmission && !item.submission_table_config && isMultiLink && item.submitted_links && item.submitted_links.length > 0 && (
        <div className="flex flex-col gap-1 text-sm text-muted-foreground bg-muted/50 rounded-lg px-3 py-2">
          <div className="flex items-center gap-1.5 font-medium text-foreground">
            <Check className="size-3.5 shrink-0 text-emerald-600 dark:text-emerald-500" /> Submitted
            {item.updated_at &&
              ` ${new Date(item.updated_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`}
            {item.updated_by_name && ` by ${item.updated_by_name}`}
          </div>
          {item.submitted_links.map((link, i) => (
            <div key={i} className={link.text ? "flex flex-col gap-0.5 pl-5" : "flex items-center gap-1.5 pl-5"}>
              {link.label && <span className="shrink-0 font-medium text-foreground">{link.label}:</span>}
              {link.text ? (
                <p className="whitespace-pre-wrap text-foreground">{link.text}</p>
              ) : (
                <a
                  href={ensureAbsoluteUrl(link.url ?? "")} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
                  className="text-primary hover:underline truncate max-w-full min-w-0"
                >
                  {link.url}
                </a>
              )}
            </div>
          ))}
        </div>
      )}

      {isSubmission && !isMultiLink && !isTextSubmission && item.submitted_url && (
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-sm text-muted-foreground bg-muted/50 rounded-lg px-3 py-2">
          <Check className="size-3.5 shrink-0 text-emerald-600 dark:text-emerald-500" />
          <a
            href={ensureAbsoluteUrl(item.submitted_url)} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
            className="text-primary hover:underline truncate max-w-full min-w-0 font-medium"
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

      {isTextSubmission && item.submitted_text && (
        <div className="flex flex-col gap-1 text-sm text-muted-foreground bg-muted/50 rounded-lg px-3 py-2">
          <div className="flex items-center gap-1.5 font-medium text-foreground">
            <Check className="size-3.5 shrink-0 text-emerald-600 dark:text-emerald-500" /> Submitted
            {item.updated_at &&
              ` ${new Date(item.updated_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`}
            {item.updated_by_name && ` by ${item.updated_by_name}`}
          </div>
          <p className="whitespace-pre-wrap text-foreground pl-5">{item.submitted_text}</p>
        </div>
      )}

      {isSubmission && !isMultiLink && !inputsHidden && (
        pastDeadline ? (
          <p className="text-sm font-medium text-amber-600 dark:text-amber-500">
            Deadline passed — no longer accepting submissions
          </p>
        ) : isTextSubmission ? (
          <div className="flex flex-col gap-2.5" onClick={(e) => e.stopPropagation()}>
            {item.submission_prompt && <p className="text-sm text-muted-foreground">{item.submission_prompt}</p>}
            <textarea
              value={submitText || item.submitted_text || ""}
              onChange={(e) => setSubmitText(e.target.value)}
              placeholder="Type your answer…"
              rows={5}
              disabled={!canSubmit}
              className="px-4 py-3 border border-border bg-background text-foreground rounded-lg text-base focus:outline-none focus:border-primary transition-colors disabled:opacity-50 resize-y"
            />
          </div>
        ) : (
          <div className="flex flex-col gap-2.5" onClick={(e) => e.stopPropagation()}>
            {item.submission_prompt ? (
              <p className="text-sm text-muted-foreground">{item.submission_prompt}</p>
            ) : isPoster ? (
              <p className="text-sm text-muted-foreground">Paste your poster link (Canva, Google Slides, Figma, etc.):</p>
            ) : null}
            <input
              value={submitUrl || item.submitted_url || ""}
              onChange={(e) => setSubmitUrl(e.target.value)}
              placeholder={isPoster ? "https://..." : "Paste your link…"}
              disabled={!canSubmit}
              className="h-12 px-4 border border-border bg-background text-foreground rounded-lg text-base focus:outline-none focus:border-primary transition-colors disabled:opacity-50"
            />
          </div>
        )
      )}

      {isSubmission && isMultiLink && !inputsHidden && (
        pastDeadline ? (
          <p className="text-sm font-medium text-amber-600 dark:text-amber-500">
            Deadline passed — no longer accepting submissions
          </p>
        ) : item.submission_table_config ? (
          <div className="flex flex-col gap-3" onClick={(e) => e.stopPropagation()}>
            {item.submission_prompt && <p className="text-sm text-muted-foreground">{item.submission_prompt}</p>}
            
            <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-sm">
              <table className="w-full text-left text-xs border-collapse min-w-[500px]">
                <thead>
                  <tr className="border-b border-border bg-muted/40 text-muted-foreground">
                    <th className="py-2.5 px-3 font-bold w-10 text-center">#</th>
                    <th className="py-2.5 px-3 font-bold min-w-[140px]">{item.submission_table_config.tag_label || "Tag"}</th>
                    {item.submission_table_config.columns?.map((col) => (
                      <th key={col.key} className="py-2.5 px-3 font-bold min-w-[130px]">
                        {col.label}
                        {col.required && <span className="text-destructive"> *</span>}
                      </th>
                    ))}
                    <th className="py-2.5 px-2 w-10 text-center" aria-label="Actions" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {linksInput.map((row, i) => {
                    const presetTags = item.submission_table_config?.tags ?? [];
                    const isCustomTag = Boolean(row.tag && !presetTags.includes(row.tag));
                    return (
                      <tr key={i} className="hover:bg-muted/15 transition-colors">
                        <td className="py-2.5 px-3 font-mono text-center text-muted-foreground font-semibold">
                          {i + 1}
                        </td>
                        <td className="py-2 px-3">
                          {presetTags.length > 0 ? (
                            isCustomTag ? (
                              <div className="flex items-center gap-1">
                                <input
                                  value={row.tag ?? ""}
                                  onChange={(e) =>
                                    setLinksInput((prev) =>
                                      prev.map((l, j) => (j === i ? { ...l, tag: e.target.value, label: e.target.value } : l))
                                    )
                                  }
                                  placeholder="Tag name"
                                  disabled={!canSubmit}
                                  className="h-10 w-full px-2.5 border border-border bg-background text-foreground rounded-lg text-xs focus:outline-none focus:border-primary"
                                />
                                <button
                                  type="button"
                                  onClick={() =>
                                    setLinksInput((prev) =>
                                      prev.map((l, j) => (j === i ? { ...l, tag: presetTags[0], label: presetTags[0] } : l))
                                    )
                                  }
                                  className="text-muted-foreground hover:text-foreground text-[10px] px-1"
                                  title="Reset to preset tag"
                                >
                                  ✕
                                </button>
                              </div>
                            ) : (
                              <select
                                value={row.tag ?? ""}
                                onChange={(e) => {
                                  const val = e.target.value;
                                  setLinksInput((prev) =>
                                    prev.map((l, j) =>
                                      j === i
                                        ? { ...l, tag: val === "__custom__" ? "Other" : val, label: val === "__custom__" ? "Other" : val }
                                        : l
                                    )
                                  );
                                }}
                                disabled={!canSubmit}
                                className="h-10 w-full px-2.5 border border-border bg-background text-foreground rounded-lg text-xs focus:outline-none focus:border-primary cursor-pointer font-medium"
                              >
                                {presetTags.map((t) => (
                                  <option key={t} value={t}>{t}</option>
                                ))}
                                {item.submission_table_config?.allow_custom_tags && (
                                  <option value="__custom__">+ Custom Tag...</option>
                                )}
                              </select>
                            )
                          ) : (
                            <input
                              value={row.tag ?? row.label ?? ""}
                              onChange={(e) =>
                                setLinksInput((prev) =>
                                  prev.map((l, j) => (j === i ? { ...l, tag: e.target.value, label: e.target.value } : l))
                                )
                              }
                              placeholder="Tag name"
                              disabled={!canSubmit}
                              className="h-10 w-full px-2.5 border border-border bg-background text-foreground rounded-lg text-xs focus:outline-none focus:border-primary"
                            />
                          )}
                        </td>
                        {item.submission_table_config?.columns?.map((col) => {
                          const val = (col.type === "link" && row.url !== undefined && row.url !== null && row.url !== "")
                            ? row.url
                            : (row.values?.[col.key] as string) ?? "";
                          
                          if (col.type === "link") {
                            return (
                              <td key={col.key} className="py-2 px-3">
                                <input
                                  type="url"
                                  value={val}
                                  onChange={(e) => {
                                    const next = e.target.value;
                                    setLinksInput((prev) =>
                                      prev.map((l, j) =>
                                        j === i
                                          ? {
                                              ...l,
                                              url: next,
                                              values: { ...(l.values || {}), [col.key]: next },
                                            }
                                          : l
                                      )
                                    );
                                  }}
                                  placeholder="https://…"
                                  disabled={!canSubmit}
                                  className="h-10 w-full px-2.5 border border-border bg-background text-foreground rounded-lg text-xs focus:outline-none focus:border-primary"
                                />
                              </td>
                            );
                          }
                          if (col.type === "select") {
                            return (
                              <td key={col.key} className="py-2 px-3">
                                <select
                                  value={val}
                                  onChange={(e) => {
                                    const next = e.target.value;
                                    setLinksInput((prev) =>
                                      prev.map((l, j) =>
                                        j === i
                                          ? {
                                              ...l,
                                              values: { ...(l.values || {}), [col.key]: next },
                                            }
                                          : l
                                      )
                                    );
                                  }}
                                  disabled={!canSubmit}
                                  className="h-10 w-full px-2.5 border border-border bg-background text-foreground rounded-lg text-xs focus:outline-none focus:border-primary cursor-pointer"
                                >
                                  <option value="">Select...</option>
                                  {col.options?.map((opt) => (
                                    <option key={opt} value={opt}>{opt}</option>
                                  ))}
                                </select>
                              </td>
                            );
                          }
                          return (
                            <td key={col.key} className="py-2 px-3">
                              <input
                                type="text"
                                value={val}
                                onChange={(e) => {
                                  const next = e.target.value;
                                  setLinksInput((prev) =>
                                    prev.map((l, j) =>
                                      j === i
                                        ? {
                                            ...l,
                                            values: { ...(l.values || {}), [col.key]: next },
                                          }
                                        : l
                                    )
                                  );
                                }}
                                placeholder={col.label}
                                disabled={!canSubmit}
                                className="h-10 w-full px-2.5 border border-border bg-background text-foreground rounded-lg text-xs focus:outline-none focus:border-primary"
                              />
                            </td>
                          );
                        })}
                        <td className="py-2 px-2 text-center">
                          <button
                            type="button"
                            disabled={!canSubmit || linksInput.length <= 1}
                            onClick={() => setLinksInput((prev) => prev.filter((_, j) => j !== i))}
                            className="p-2 text-muted-foreground hover:text-destructive transition-colors disabled:opacity-20"
                            title="Delete row"
                          >
                            <Trash2 size={15} />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <button
              type="button"
              disabled={!canSubmit}
              onClick={() => {
                const presetTags = item.submission_table_config?.tags ?? [];
                const usedTags = new Set(linksInput.map((l) => l.tag || l.label));
                const nextTag = presetTags.find((t) => !usedTags.has(t)) ?? presetTags[0] ?? "";
                setLinksInput((prev) => [...prev, { tag: nextTag, label: nextTag, url: "", text: "", values: {} }]);
              }}
              className="self-start flex items-center gap-1.5 px-3 py-2 rounded-lg border border-primary/25 bg-primary/10 text-primary hover:bg-primary/20 text-xs font-semibold transition-colors disabled:opacity-50"
            >
              <Plus size={14} /> Add {item.submission_table_config.tag_label ? `Another ${item.submission_table_config.tag_label}` : "Row"}
            </button>
          </div>
        ) : item.submission_link_labels?.length ? (
          // Ops's own fixed label set (2026-09-14) — a fixed row per
          // label, in ops's order; no adding/removing/renaming, only
          // filling each one in. "required" ones block submission (see
          // the CTA's disabled condition below).
          <div className="flex flex-col gap-2.5" onClick={(e) => e.stopPropagation()}>
            {item.submission_prompt && <p className="text-sm text-muted-foreground">{item.submission_prompt}</p>}
            {item.submission_link_labels.map((spec, i) => (
              <div key={spec.label} className="flex flex-col gap-1">
                <label className="text-xs font-medium text-foreground">
                  {spec.label}{spec.required && <span className="text-destructive"> *</span>}
                </label>
                {spec.field_type === "text" ? (
                  <textarea
                    value={linksInput[i]?.text ?? ""}
                    onChange={(e) => setLinksInput((prev) => prev.map((l, j) => j === i ? { ...l, text: e.target.value } : l))}
                    placeholder="Type your answer…"
                    rows={4}
                    disabled={!canSubmit}
                    className="px-3 py-2.5 border border-border bg-background text-foreground rounded-lg text-base focus:outline-none focus:border-primary transition-colors disabled:opacity-50 resize-y"
                  />
                ) : (
                  <input
                    value={linksInput[i]?.url ?? ""}
                    onChange={(e) => setLinksInput((prev) => prev.map((l, j) => j === i ? { ...l, url: e.target.value } : l))}
                    placeholder="https://…"
                    disabled={!canSubmit}
                    className="h-12 px-3 border border-border bg-background text-foreground rounded-lg text-base focus:outline-none focus:border-primary transition-colors disabled:opacity-50"
                  />
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col gap-2.5" onClick={(e) => e.stopPropagation()}>
            {item.submission_prompt && <p className="text-sm text-muted-foreground">{item.submission_prompt}</p>}
            {linksInput.map((link, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  value={link.label ?? ""}
                  onChange={(e) => setLinksInput((prev) => prev.map((l, j) => j === i ? { ...l, label: e.target.value } : l))}
                  placeholder="Label (optional) — e.g. Member 1"
                  disabled={!canSubmit}
                  className="h-12 w-2/5 px-3 border border-border bg-background text-foreground rounded-lg text-sm focus:outline-none focus:border-primary transition-colors disabled:opacity-50"
                />
                <input
                  value={link.url ?? ""}
                  onChange={(e) => setLinksInput((prev) => prev.map((l, j) => j === i ? { ...l, url: e.target.value } : l))}
                  placeholder="https://…"
                  disabled={!canSubmit}
                  className="h-12 flex-1 px-3 border border-border bg-background text-foreground rounded-lg text-base focus:outline-none focus:border-primary transition-colors disabled:opacity-50"
                />
                <button
                  type="button"
                  disabled={!canSubmit || linksInput.length <= 1}
                  onClick={() => setLinksInput((prev) => prev.filter((_, j) => j !== i))}
                  aria-label="Remove link"
                  className="flex h-12 w-10 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:text-destructive transition-colors disabled:opacity-30"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
            <button
              type="button"
              disabled={!canSubmit}
              onClick={() => setLinksInput((prev) => [...prev, { label: "", url: "", text: "" }])}
              className="self-start flex items-center gap-1.5 text-sm font-medium text-primary hover:underline disabled:opacity-50"
            >
              <Plus size={14} /> Add another link
            </button>
          </div>
        )
      )}

      {item.item_type === "quiz" && pastDeadline && !done && !frozen && (
        <p className="text-sm font-medium text-amber-600 dark:text-amber-500">
          Deadline passed — no longer accepting quiz attempts
        </p>
      )}

      {isSelfCheck && pastDeadline && !done && !awaiting && !frozen && (
        <p className="text-sm font-medium text-amber-600 dark:text-amber-500">
          Deadline passed — this step can no longer be completed
        </p>
      )}

      {/* Exactly one primary action, whatever this item's type. A section
          frozen by a locked checkpoint never shows a submit/complete button —
          just the neutral lock notice, so the write can never 409. */}
      <div className="mt-auto pt-3 flex flex-col gap-2.5 border-t border-border">
        {frozen ? (
          <div className="flex items-center justify-center gap-2 p-3.5 rounded-xl bg-primary/10 border border-primary/25 text-primary text-sm font-semibold">
            <Lock size={16} className="shrink-0 text-muted-foreground" /> This checkpoint is now locked for your team
          </div>
        ) : teamFinalLocked && item.scope === "team" ? (
          <div className="flex items-center justify-center gap-2 p-3.5 rounded-xl bg-primary/10 border border-primary/25 text-primary text-sm font-semibold">
            <Lock size={16} /> Final submission locked · Sealed for review
          </div>
        ) : (
          <>
            {!canSubmit && (isSubmission || isSelfCheck || isTeamSetup) && !done && !awaiting && (
              <p className="text-xs text-muted-foreground text-center">View the guide above first</p>
            )}
            {item.item_type === "mission_run" && item.scope === "team" && !teamName && (
              <p className="text-xs text-amber-600 dark:text-amber-500 text-center font-medium">
                This is a team mission. Join or form a team to unlock it.
              </p>
            )}
            {isAutoTracked && (
              <Button
                disabled={
                  (item.item_type === "quiz" && pastDeadline && !done) ||
                  (item.item_type === "mission_run" && item.scope === "team" && !teamName)
                }
                onClick={() => {
                  if (item.item_type === "mission_run" && !item.mission_attempt_id) {
                    onChanged();
                    return;
                  }
                  doWork();
                }}
                className="h-[52px] text-base gap-2"
              >
                {item.item_type === "quiz" && pastDeadline && !done ? (
                  "Deadline passed"
                ) : item.item_type === "mission_run" && !item.mission_attempt_id ? (
                  item.scope === "team" && !teamName ? (
                    "Join a team to unlock this mission"
                  ) : (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      Syncing mission… Click to refresh
                    </>
                  )
                ) : (
                  workLabel
                )}
              </Button>
            )}
            {isSubmission && !isMultiLink && !isTextSubmission && !pastDeadline && (
              <Button
                disabled={!canSubmit || (!submitUrl && !item.submitted_url) || submitMutation.isPending}
                onClick={() => submitMutation.mutate(submitUrl || item.submitted_url || "")}
                className="h-[52px] text-base"
              >
                {submitMutation.isPending
                  ? "Submitting…"
                  : item.submitted_url
                  ? isPoster
                    ? "Update poster link"
                    : "Replace submission"
                  : isPoster
                  ? "Submit poster"
                  : "Submit for review"}
              </Button>
            )}
            {isTextSubmission && !pastDeadline && (
              <Button
                disabled={!canSubmit || (!submitText.trim() && !item.submitted_text) || submitTextMutation.isPending}
                onClick={() => submitTextMutation.mutate((submitText || item.submitted_text || "").trim())}
                className="h-[52px] text-base"
              >
                {submitTextMutation.isPending
                  ? "Submitting…"
                  : item.submitted_text
                  ? "Replace submission"
                  : "Submit for review"}
              </Button>
            )}
            {isSubmission && isMultiLink && !pastDeadline && (
              <Button
                disabled={
                  !canSubmit || submitLinksMutation.isPending
                  || (item.submission_table_config
                    ? !linksInput.some((l) => hasTableRowValue(l))
                    : (!linksInput.some((l, i) => hasRowValue(l, item.submission_link_labels?.[i]))
                       || (item.submission_link_labels?.some((spec, i) => spec.required && !hasRowValue(linksInput[i], spec)) ?? false)))
                }
                onClick={() => submitLinksMutation.mutate(
                  item.submission_table_config
                    ? linksInput
                        .filter((l) => hasTableRowValue(l))
                        .map((l) => {
                          const tag = (l.tag || l.label || "").trim();
                          const url = (l.url || (l.values?.url as string) || "").trim();
                          return {
                            tag,
                            label: tag,
                            url: url || null,
                            text: l.text || null,
                            values: l.values || {},
                          };
                        })
                    : linksInput
                        .map((l, i) => ({ link: l, spec: item.submission_link_labels?.[i] }))
                        .filter(({ link, spec }) => hasRowValue(link, spec))
                        .map(({ link, spec }) => (
                          spec?.field_type === "text"
                            ? { label: link.label?.trim() || null, url: null, text: (link.text ?? "").trim() }
                            : { label: link.label?.trim() || null, url: (link.url ?? "").trim(), text: null }
                        )),
                )}
                className="h-[52px] text-base"
              >
                {submitLinksMutation.isPending
                  ? "Submitting…"
                  : item.submitted_links?.length
                  ? "Replace submission"
                  : "Submit for review"}
              </Button>
            )}
            {isSelfCheck && !done && !awaiting && (
              <Button
                disabled={!canSubmit || completeMutation.isPending || pastDeadline}
                onClick={() => completeMutation.mutate()}
                className="h-[52px] text-base"
              >
                {pastDeadline
                  ? "Deadline passed"
                  : completeMutation.isPending
                  ? "Marking done…"
                  : item.requires_confirmation
                  ? "Mark as done (needs sign-off)"
                  : "Mark as done"}
              </Button>
            )}
          </>
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
  item, items, assignmentId, teamName, teamCode, teamMembers, teamFinalLocked, onClose, onChanged,
}: {
  item: LmsProgramChecklistItem | null;
  items?: LmsProgramChecklistItem[];
  assignmentId: string;
  teamName: string | null;
  teamCode?: string | null;
  teamMembers?: LmsTeamMember[];
  teamFinalLocked?: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [submitUrl, setSubmitUrl] = useState("");
  // The plain single-text-field submission's own input (2026-09-16) —
  // separate from submitUrl since a text answer and a link answer are
  // mutually exclusive per item.submission_field_type, never both at once.
  const [submitText, setSubmitText] = useState("");
  // Multi-link submission rows (2026-09-14, ops's per-item toggle) —
  // seeded from whatever's already submitted, one blank row for a fresh
  // item, resets per-item the same way every other drawer state does (via
  // the parent's `key={item?.id}` remount, not an effect).
  const [linksInput, setLinksInput] = useState<SubmissionLink[]>(() => {
    if (item?.submission_table_config) {
      if (item.submitted_links?.length) {
        return item.submitted_links.map((l) => ({
          tag: l.tag ?? l.label ?? "",
          label: l.label ?? l.tag ?? "",
          url: l.url ?? "",
          text: l.text ?? "",
          values: l.values ?? {},
        }));
      }
      if (item.submission_table_config.tags?.length) {
        return item.submission_table_config.tags.map((tag) => ({
          tag,
          label: tag,
          url: "",
          text: "",
          values: {},
        }));
      }
      return [{ tag: "", label: "", url: "", text: "", values: {} }];
    }
    // Ops's own fixed label set (2026-09-14): one row per label, in ops's
    // order, seeded from whatever's already submitted under that exact
    // label — not just positionally, since ops can reorder/add labels
    // after students have already submitted under the old set.
    if (item?.submission_link_labels?.length) {
      return item.submission_link_labels.map((spec) => {
        const existing = item.submitted_links?.find((l) => l.label === spec.label);
        return { label: spec.label, url: existing?.url ?? "", text: existing?.text ?? "" };
      });
    }
    return item?.submitted_links?.length
      ? item.submitted_links.map((l) => ({ label: l.label, url: l.url ?? "", text: l.text ?? "" }))
      : [{ label: "", url: "", text: "" }];
  });
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

  const { data: guidelineVideoResult } = useQuery({
    queryKey: ["lms-checklist-item-guideline-video-url", assignmentId, item?.id],
    queryFn: () => getChecklistItemGuidelineVideoUrlApi(assignmentId, item!.id),
    enabled: !!item && effectiveGuidelineKind === "video" && !!item.guideline_video_uploaded,
    // Poll while an hls_encrypted upload is still transcoding — this used
    // to be a non-issue when uploads flipped straight to "ready", but now
    // there is a real async gap to bridge without a manual refresh.
    refetchInterval: (q) => {
      const status = q.state.data?.video_info?.status;
      return status && status !== "ready" && status !== "failed" ? 4000 : false;
    },
  });
  const guidelineVideoInfo = guidelineVideoResult?.video_info;

  const toast = useToast();
  const isPoster = item?.mission_step_key === "poster";
  const completeMutation = useMutation({
    mutationFn: () => completeChecklistItem(assignmentId, item!.id),
    onSuccess: () => {
      toast.success("Task completed!");
      onChanged();
      queryClient.invalidateQueries({ queryKey: ["lms-checklist", assignmentId] });
    },
    onError: (err) => {
      toast.error(errorDetail(err, "Failed to complete item."));
    },
  });
  const submitMutation = useMutation({
    mutationFn: (url: string) => submitChecklistItem(assignmentId, item!.id, url),
    onSuccess: () => {
      toast.success(isPoster ? "Poster link saved successfully!" : "Submission received!");
      onChanged();
      queryClient.invalidateQueries({ queryKey: ["lms-checklist", assignmentId] });
    },
    onError: (err) => {
      toast.error(errorDetail(err, "Failed to submit. Please check your link."));
    },
  });
  const submitTextMutation = useMutation({
    mutationFn: (text: string) => submitChecklistItemText(assignmentId, item!.id, text),
    onSuccess: () => {
      toast.success("Submission received!");
      onChanged();
      queryClient.invalidateQueries({ queryKey: ["lms-checklist", assignmentId] });
    },
    onError: (err) => {
      toast.error(errorDetail(err, "Failed to submit. Please try again."));
    },
  });
  const submitLinksMutation = useMutation({
    mutationFn: (links: SubmissionLink[]) => submitChecklistItemLinks(assignmentId, item!.id, links),
    onSuccess: () => {
      toast.success("Submission received!");
      onChanged();
      queryClient.invalidateQueries({ queryKey: ["lms-checklist", assignmentId] });
    },
    onError: (err) => {
      toast.error(errorDetail(err, "Failed to submit. Please check your links."));
    },
  });
  // (Rename now lives inside the team-formation panel, which owns its own
  // mutation + server-confirmed deadline flip.)

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
    else if (target.kind === "quiz") void navigate({ to: `/learn/checklists/${assignmentId}/quiz/${target.itemId}` });
    else if (target.kind === "arcade_game") {
      void navigate({
        to: `/learn/arcade/${target.gameKey}`,
        search: { mode: target.mode, program: assignmentId, itemId: target.itemId } as never,
      });
    } else if (target.kind === "external") window.open(ensureAbsoluteUrl(target.url), "_blank", "noreferrer");
    else if (item.item_type === "mission_run") {
      if (item.mission_id) {
        void navigate({ to: `/learn/missions/${item.mission_id}` });
      } else {
        onChanged();
      }
    }
  };
  // A submission item's own `external_url` is an optional reference link
  // (e.g. a Tinkercad template) — a genuine "do the work" destination
  // distinct from its guideline. Only shown when set.
  const submissionReference = item.item_type === "submission" && item.external_url ? item.external_url : null;

  const hasGuideline = !!effectiveGuidelineKind;
  const isAutoTracked = (item.item_type === "course" || item.item_type === "mission_run" || item.item_type === "quiz" || item.item_type === "arcade_game") && !isPoster;
  const isSubmission = item.item_type === "submission" || isPoster;
  const isMultiLink = item.item_type === "submission" && item.submission_multi_link;
  const isTeamSetup = item.item_type === "team_setup";
  const isSelfCheck = SELF_CHECK_TYPES.has(item.item_type);
  const done = item.status === "done";
  const awaiting = item.status === "awaiting_confirmation";

  const onOpenMadar = isPoster && (item.mission_attempt_id || item.mission_id) ? () => {
    saveBoardScrollPosition(assignmentId);
    if (item.mission_attempt_id) {
      void navigate({
        to: `/learn/missions/design/${item.mission_attempt_id}`,
        search: { phase: "poster", program: assignmentId } as never,
      });
    } else if (item.mission_id) {
      void navigate({ to: `/learn/missions/${item.mission_id}` });
    }
  } : undefined;

  const workLabel =
    target.kind === "course" ? "Open the course" :
    target.kind === "design" ? `Open Madar${item.mission_step_key ? ` · ${MISSION_STEP_LABELS[item.mission_step_key as MissionStepKey]}` : ""}` :
    target.kind === "operate" ? "Open the mission" :
    target.kind === "mission" ? "Open the mission" :
    target.kind === "quiz" ? (done ? "View results" : "Start the quiz") :
    target.kind === "arcade_game" ? (done ? "Replay game" : "Play game") :
    target.kind === "external" ? "Open the link" : "Open";

  const canSubmit = !hasGuideline || guidelineOpened;
  // Once the deadline passes, the paste-link form is hidden — already
  // submitted content above stays visible/reviewable. Posters remain editable anytime.
  // (Team formation handles its own server-confirmed deadline inside its panel.)
  const pastDeadline = !isPoster && !!item.deadline_at && new Date(item.deadline_at) < new Date();
  const Icon = iconForItem(item);
  const sectionFrozen = !!items?.length && isSectionFrozen(items, item, !!teamName);

  const bodyProps: DrawerBodyProps = {
    item, onClose, hasGuideline, effectiveGuidelineKind, guidelineOpened, openGuideline, workLabel, doWork,
    submissionReference, guidelineVideoUploaded: !!item.guideline_video_uploaded, guidelineVideoInfo, isAutoTracked,
    isSubmission, isMultiLink, isTeamSetup, teamName,
    teamCode: teamCode ?? null, teamMembers: teamMembers ?? [], assignmentId,
    isPoster, onOpenMadar, isSelfCheck, done, awaiting, canSubmit, pastDeadline,
    submitUrl, setSubmitUrl, submitMutation, submitText, setSubmitText, submitTextMutation,
    linksInput, setLinksInput, submitLinksMutation,
    Icon, completeMutation,
    teamFinalLocked, sectionFrozen, onChanged,
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
