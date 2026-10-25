import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ChevronLeft, ChevronRight, FileText, FileWarning, Rocket, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PdfViewer } from "@/components/documents/PdfViewer";
import {
  checkQuizAnswer, fetchQuizQuestions, getAttachmentUrl, recordProgress, submitQuiz,
  resolveQuizImageUrl,
  type ModuleItem, type QuizAnswerCheck, type QuizReview,
} from "@/api/lms";
import { VideoPlayer } from "./VideoPlayer";

/** One switch on item.kind → the five content panes (design 1i). Net-new,
 * replacing the inline switch that used to live directly in the module
 * route — this version has no route of its own, PlayerLayout swaps it in.
 */
export function ItemPane({
  item, onProgressed,
}: { item: ModuleItem; onProgressed: () => void }) {
  // The Got it! button for a video lives in LearnPlayer.tsx instead of
  // here, in the same row as the title (both sit *under* the player,
  // player-first) — every other content type keeps its action inside its
  // own block since there's no title to share a row with.
  if (item.kind === "video" && "transcode_status" in item.content) {
    return (
      <VideoPlayer
        key={item.id}
        itemId={item.id}
        videoId={item.content.video_id}
        transcodeStatus={item.content.transcode_status}
        onEnded={() => { recordProgress(item.id, "video-watched").finally(onProgressed); }}
      />
    );
  }

  if (item.kind === "text" && "body" in item.content) {
    return <TextBlock body={item.content.body} onContinue={() => recordProgress(item.id, "text-viewed").finally(onProgressed)} />;
  }

  if (item.kind === "flashcards" && "cards" in item.content) {
    return (
      <FlashcardsBlock
        key={item.id}
        title={item.content.title}
        cards={item.content.cards}
        onDone={() => recordProgress(item.id, "flashcards-skipped").finally(onProgressed)}
      />
    );
  }

  if (item.kind === "quiz") {
    return <QuizBlock item={item} onPassed={onProgressed} />;
  }

  if (item.kind === "attachment") {
    return (
      <AttachmentBlock
        key={item.id}
        itemId={item.id}
        onDone={() => recordProgress(item.id, "attachment-viewed").finally(onProgressed)}
      />
    );
  }

  if (item.kind === "mission" && "mission_id" in item.content) {
    return <MissionEmbedBlock content={item.content} />;
  }

  return null;
}

// P5-5 — the attempt flow itself lives on the standalone mission page
// (/learn/missions/$missionId), reused as-is rather than rebuilt inline:
// completion is server-driven (rule ①, decide_attempt writes ItemProgress
// directly), so this block only orients and links out, it never calls
// recordProgress — there is no client-assertable action for a mission item.
function MissionEmbedBlock({ content }: { content: Extract<ModuleItem["content"], { mission_id: string }> }) {
  const passed = content.attempt_status === "passed";
  const statusLabel =
    content.attempt_status === "passed" ? "Passed"
    : content.attempt_status === "failed" ? "Not yet passed"
    : content.attempt_status === "submitted" ? "Awaiting review"
    : content.attempt_status === "in_progress" ? "In progress"
    : "Not started";

  return (
    <div className="lms-card p-6 sm:p-8 flex flex-col gap-5 items-start">
      <div className="flex items-center gap-2 text-xs text-[#A880FF] font-bold uppercase tracking-wider">
        <Rocket className="size-4" /> Mission
      </div>
      <div>
        <p className="font-['Outfit'] text-2xl font-bold text-foreground">{content.mission_title ?? "Mission"}</p>
        <p className="text-sm sm:text-base text-muted-foreground mt-1 flex items-center gap-2">
          {passed ? <CheckCircle2 className="size-4 text-emerald-400" /> : null}
          <span>{statusLabel}</span>
          {content.points != null && <span>· {content.points} pts</span>}
        </p>
      </div>
      <Link to="/learn/missions/$missionId" params={{ missionId: content.mission_id }}>
        <button type="button" className="lms-btn-primary px-6 py-3 font-['Outfit'] text-sm cursor-pointer">
          {passed ? "Review mission" : "Go to mission"}
        </button>
      </Link>
    </div>
  );
}

function readingMinutes(body: string): number {
  const words = body.trim().split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(words / 200));
}

function TextBlock({ body, onContinue }: { body: string; onContinue: () => void }) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs font-semibold uppercase tracking-wider text-[#A880FF]">
        Reading · {readingMinutes(body)} min
      </p>
      <div className="lms-card p-6 sm:p-8 whitespace-pre-wrap text-base sm:text-lg leading-relaxed text-foreground/90 font-normal">
        {body}
      </div>
      <div className="flex justify-end pt-2">
        <button
          type="button"
          onClick={onContinue}
          className="lms-btn-primary px-6 py-3 font-['Outfit'] text-sm flex items-center gap-2 cursor-pointer"
        >
          <CheckCircle2 className="size-4" /> Got it!
        </button>
      </div>
    </div>
  );
}

function AttachmentBlock({ itemId, onDone }: { itemId: string; onDone: () => void }) {
  // Signed URL is fetched fresh per view (short-lived, same posture as the
  // video token) — never baked into the module-read payload.
  const { data, isLoading, isError } = useQuery({
    queryKey: ["attachment-url", itemId],
    queryFn: () => getAttachmentUrl(itemId),
  });
  const [open, setOpen] = useState(false);

  if (isLoading) {
    return <p className="text-sm sm:text-base text-muted-foreground font-['Outfit']">Loading document...</p>;
  }
  if (isError || !data) {
    return (
      <div className="flex items-center gap-3 p-5 rounded-xl border border-destructive/30 bg-destructive/5 text-destructive text-sm sm:text-base">
        <FileWarning className="size-5 shrink-0" /> Couldn't load this document.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Opens in a near-fullscreen viewer instead of rendering inline in
          this narrow reading column — "fit width" scales to whatever
          container it's in, and this one is much narrower than a modal,
          so text came out visibly smaller/softer than everywhere else the
          same PdfViewer renders. */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="lms-card p-6 flex items-center gap-4 hover:border-[#A880FF] transition-all text-left cursor-pointer group w-full"
      >
        <FileText className="text-[#A880FF] shrink-0 group-hover:scale-105 transition-transform" size={28} />
        <div className="min-w-0 flex-1">
          <p className="font-['Outfit'] text-base sm:text-lg font-bold text-foreground truncate">{data.filename ?? "Document"}</p>
          <p className="text-xs sm:text-sm text-muted-foreground mt-0.5">Click to view document</p>
        </div>
      </button>
      <div className="flex justify-end pt-1">
        <button
          type="button"
          onClick={onDone}
          className="lms-btn-primary px-6 py-3 font-['Outfit'] text-sm flex items-center gap-2 cursor-pointer"
        >
          <CheckCircle2 className="size-4" /> Got it!
        </button>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-[95vw] max-w-[95vw] w-[95vw] h-[92vh] max-h-[92vh] flex flex-col border border-border dark:border-[#a880ff]/30 bg-background dark:bg-[#05030A]">
          <DialogHeader><DialogTitle className="font-['Outfit'] text-lg font-bold text-foreground">{data.filename ?? "Document"}</DialogTitle></DialogHeader>
          <PdfViewer url={data.url} className="flex flex-col gap-3 flex-1 min-h-0" />
        </DialogContent>
      </Dialog>
    </div>
  );
}

function FlashcardsBlock({
  title, cards, onDone,
}: { title: string | null; cards: { term: string; definition: string }[]; onDone: () => void }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const total = cards.length;
  const card = cards[currentIndex];
  if (!card) return null;

  const goTo = (i: number) => {
    setRevealed(false);
    setCurrentIndex(i);
  };

  return (
    <div className="flex flex-col gap-4">
      {title && <p className="text-xs font-semibold uppercase tracking-wider text-lms-cta dark:text-lms-accent">{title}</p>}
      <button
        type="button"
        onClick={() => setRevealed((r) => !r)}
        className="lms-card w-full min-h-64 p-8 sm:p-12 flex items-center justify-center text-center cursor-pointer hover:border-lms-accent transition-all select-none"
      >
        <span className="font-['Outfit'] text-xl sm:text-2xl font-bold leading-relaxed text-foreground">{revealed ? card.definition : card.term}</span>
      </button>

      {/* Free navigation, not a queue — every card is a dot, click any dot
          to jump straight to it. No per-card "still learning" requeue. */}
      <div className="mt-2 flex items-center justify-center gap-2">
        {cards.map((_, i) => (
          <button
            key={i}
            type="button"
            onClick={() => goTo(i)}
            aria-label={`Go to card ${i + 1}`}
            className={`h-2.5 rounded-full transition-all cursor-pointer ${
              i === currentIndex ? "w-8 bg-lms-cta dark:bg-lms-accent" : "w-2.5 bg-foreground/20 dark:bg-white/20 hover:bg-foreground/40 dark:hover:bg-white/40"
            }`}
          />
        ))}
      </div>

      <p className="text-center text-xs text-muted-foreground">
        {revealed ? "Click to see term" : "Click to reveal definition"} · Card {currentIndex + 1} of {total}
      </p>

      <div className="mt-4 flex items-center justify-between">
        <button
          type="button"
          onClick={onDone}
          className="text-xs sm:text-sm text-muted-foreground hover:text-foreground dark:hover:text-white transition-colors cursor-pointer"
        >
          Skip
        </button>
        <button
          type="button"
          onClick={onDone}
          className="lms-btn-primary px-6 py-3 font-['Outfit'] text-sm flex items-center gap-2 cursor-pointer"
        >
          <CheckCircle2 className="size-4" /> Got it!
        </button>
      </div>
    </div>
  );
}

function ScoreRing({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div
      className="relative w-[84px] h-[84px] shrink-0 rounded-full flex items-center justify-center"
      style={{ background: `conic-gradient(#A880FF 0% ${pct}%, rgba(168, 128, 255, 0.15) ${pct}% 100%)` }}
    >
      <div className="w-[68px] h-[68px] rounded-full bg-card dark:bg-[#05030A] flex flex-col items-center justify-center">
        <span className="font-['Outfit'] text-xl font-extrabold leading-none text-foreground">{Math.round(pct)}%</span>
      </div>
    </div>
  );
}

function QuizBlock({ item, onPassed }: { item: ModuleItem; onPassed: () => void }) {
  const content = "questions" in item.content ? item.content : null;
  // Random-N quizzes (2026-09-01): the server samples a fresh subset each
  // time it's fetched fresh (module load, or after a submit clears the
  // sample), so this needs to be state — not just derived from `item` —
  // for retry() to be able to swap in a newly-fetched sample.
  const [liveContent, setLiveContent] = useState(content);
  const questions = liveContent?.questions ?? [];
  const passThreshold = liveContent?.pass_threshold ?? 0;
  const [answers, setAnswers] = useState<number[]>(() => questions.map(() => -1));
  // One entry per question once its answer has been live-checked — drives
  // both "has this question been revealed yet" and what to show for it.
  // Keyed by question index so Back/Next never re-fetches an already-seen one.
  const [checks, setChecks] = useState<Record<number, QuizAnswerCheck>>({});
  const [checking, setChecking] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [review, setReview] = useState<QuizReview | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [retrying, setRetrying] = useState(false);

  if (!content) return null;

  const allAnswered = answers.every((a) => a >= 0);
  const isLastQuestion = currentIndex === questions.length - 1;
  const currentCheck = checks[currentIndex];

  const selectAnswer = (oi: number) => {
    if (currentCheck) return; // locked once checked
    setAnswers((prev) => prev.map((a, idx) => (idx === currentIndex ? oi : a)));
  };

  const checkCurrent = async () => {
    if (checking || currentCheck || answers[currentIndex] < 0) return;
    setChecking(true);
    try {
      const result = await checkQuizAnswer(item.id, currentIndex, answers[currentIndex]);
      setChecks((prev) => ({ ...prev, [currentIndex]: result }));
    } finally {
      setChecking(false);
    }
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const result = await submitQuiz(item.id, answers);
      setReview(result);
      if (result.passed) onPassed();
    } finally {
      setSubmitting(false);
    }
  };

  const retry = async () => {
    setRetrying(true);
    try {
      // submitQuiz always clears the server-side sample for a randomized
      // quiz, so this naturally draws a fresh random N when applicable.
      const fresh = await fetchQuizQuestions(item.id);
      setLiveContent(fresh);
      setReview(null);
      setAnswers(fresh.questions.map(() => -1));
      setChecks({});
      setCurrentIndex(0);
    } finally {
      setRetrying(false);
    }
  };

  // Reviewing a submitted attempt: the whole point is scanning every
  // result at a glance (right/wrong, explanations), so this stays one
  // list — only the *answering* phase below is paginated.
  if (review) {
    return (
      <div className="flex flex-col gap-6">
        <div className="lms-card p-6 flex items-center gap-5">
          <ScoreRing score={review.score} />
          <div className="min-w-0">
            <p className={`text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5 ${review.passed ? "text-emerald-400" : "text-rose-400"}`}>
              {review.passed ? <CheckCircle2 className="size-3.5" /> : <XCircle className="size-3.5" />}
              {review.passed ? "Passed" : "Not yet passed"}
              {passThreshold > 0 && ` · ${passThreshold}% needed`}
            </p>
            <p className="font-['Outfit'] text-2xl font-bold mt-1 text-foreground">
              {review.passed ? "Quiz passed!" : `Score: ${review.score}%`}
            </p>
          </div>
        </div>

        {questions.map((q, qi) => {
          const reviewQ = review.questions[qi];
          return (
            <div key={qi} className="lms-card p-6 flex flex-col gap-4">
              {q.image_url && (
                <div className="mb-2 overflow-hidden rounded-xl border border-[#a880ff]/20 bg-black/40 flex justify-center p-3">
                  <img
                    src={resolveQuizImageUrl(q.image_url)}
                    alt="Question diagram"
                    className="max-h-64 w-auto object-contain rounded-lg"
                    loading="lazy"
                  />
                </div>
              )}
              <p className="font-['Outfit'] font-bold text-base sm:text-lg text-foreground">{q.prompt}</p>
              <div className="flex flex-col gap-2.5">
                {q.options.map((opt, oi) => {
                  const isSelected = answers[qi] === oi;
                  return (
                    <div
                      key={oi}
                      className={`text-left px-4 py-3 rounded-xl border text-sm sm:text-base flex items-center justify-between gap-3 transition-colors ${
                        isSelected
                          ? reviewQ?.correct
                            ? "border-emerald-500/70 bg-emerald-500/10 text-emerald-300 font-semibold"
                            : "border-rose-500/70 bg-rose-500/10 text-rose-300 font-semibold"
                          : "border-[#a880ff]/20 bg-foreground/[0.02] text-muted-foreground"
                      }`}
                    >
                      <span>{opt.text}</span>
                      {isSelected && (reviewQ?.correct ? (
                        <CheckCircle2 className="size-4 text-emerald-400 shrink-0" />
                      ) : (
                        <XCircle className="size-4 text-rose-400 shrink-0" />
                      ))}
                    </div>
                  );
                })}
              </div>
              <p className={`text-xs sm:text-sm font-semibold flex items-center gap-1.5 ${reviewQ?.correct ? "text-emerald-400" : "text-rose-400"}`}>
                {reviewQ?.correct
                  ? `Your answer: ${q.options[reviewQ.selected]?.text ?? ""} ✓`
                  : `You said: ${q.options[reviewQ?.selected ?? -1]?.text ?? ""}${reviewQ?.correct_text ? ` · Correct: ${reviewQ.correct_text}` : ""}`}
              </p>
              {!reviewQ?.correct && reviewQ?.explanation && (
                <p className="text-xs sm:text-sm text-muted-foreground bg-white/[0.02] p-3 rounded-lg border border-[#a880ff]/15">{reviewQ.explanation}</p>
              )}
            </div>
          );
        })}

        {!review.passed && (
          <button
            type="button"
            onClick={() => void retry()}
            disabled={retrying}
            className="lms-btn-primary px-7 py-3 font-['Outfit'] text-sm w-fit cursor-pointer disabled:opacity-40"
          >
            {retrying ? "Loading..." : "Retry quiz"}
          </button>
        )}
      </div>
    );
  }

  // Answering phase: one question on screen at a time, Previous/Submit
  // between them. Picking an option just selects it; clicking Submit is
  // what checks it live (right/wrong + explanation shown right there,
  // options lock) — the operator's ask, so feedback appears on an explicit
  // action rather than the instant an option is clicked. The final Submit
  // (the real, once-per-attempt grade via quiz/submit) only appears once
  // the last question has been checked.
  const q = questions[currentIndex];
  if (!q) return null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between text-xs sm:text-sm text-muted-foreground">
        <span className="font-['Outfit'] font-semibold text-[#A880FF]">
          Question {currentIndex + 1} of {questions.length}
        </span>
        {passThreshold > 0 && (
          <span>Passing score: {passThreshold}%</span>
        )}
      </div>

      <div className="lms-card p-6 sm:p-8 flex flex-col gap-5">
        {q.image_url && (
          <div className="overflow-hidden rounded-xl border border-[#a880ff]/20 bg-black/40 flex justify-center p-3">
            <img
              src={resolveQuizImageUrl(q.image_url)}
              alt="Question diagram"
              className="max-h-80 w-auto object-contain rounded-lg"
              loading="eager"
            />
          </div>
        )}
        <h3 className="font-['Outfit'] font-bold text-lg sm:text-xl text-foreground leading-snug">{q.prompt}</h3>
        <div className="flex flex-col gap-2.5">
          {q.options.map((opt, oi) => {
            const isSelected = answers[currentIndex] === oi;
            const isRevealedCorrectOption = currentCheck && !currentCheck.correct
              && currentCheck.correct_text != null && opt.text === currentCheck.correct_text;
            return (
              <button
                key={oi}
                type="button"
                disabled={!!currentCheck}
                onClick={() => selectAnswer(oi)}
                className={`text-left px-4 py-3.5 rounded-xl border text-sm sm:text-base flex items-center justify-between gap-3 transition-all ${
                  currentCheck ? "cursor-default" : "cursor-pointer"
                } ${
                  isSelected && currentCheck
                    ? currentCheck.correct
                      ? "border-emerald-500/70 bg-emerald-500/10 text-emerald-300 font-semibold"
                      : "border-rose-500/70 bg-rose-500/10 text-rose-300 font-semibold"
                    : isSelected
                    ? "border-2 border-lms-accent bg-lms-cta-light text-foreground dark:text-white font-semibold"
                    : isRevealedCorrectOption
                    ? "border-2 border-emerald-500/70 bg-emerald-500/10 text-emerald-300 font-semibold"
                    : "border-[#a880ff]/25 bg-foreground/[0.02] hover:border-[#a880ff]/50 hover:bg-[#a880ff]/5 text-foreground"
                }`}
              >
                <span>{opt.text}</span>
                {isSelected && currentCheck && (currentCheck.correct ? (
                  <CheckCircle2 className="size-4 text-emerald-400 shrink-0" />
                ) : (
                  <XCircle className="size-4 text-rose-400 shrink-0" />
                ))}
                {!isSelected && isRevealedCorrectOption && (
                  <CheckCircle2 className="size-4 text-emerald-400 shrink-0" />
                )}
              </button>
            );
          })}
        </div>
        {checking && <p className="text-xs sm:text-sm text-muted-foreground">Checking answer...</p>}
        {currentCheck && (
          <div className={`p-4 rounded-xl border text-sm ${currentCheck.correct ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" : "border-rose-500/40 bg-rose-500/10 text-rose-300"}`}>
            <p className="font-semibold">
              {currentCheck.correct ? "Correct!" : `Not quite — the answer was "${currentCheck.correct_text ?? ""}"`}
            </p>
            {currentCheck.explanation && (
              <p className="mt-1.5 text-xs sm:text-sm opacity-90">{currentCheck.explanation}</p>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          disabled={currentIndex === 0}
          onClick={() => setCurrentIndex((i) => i - 1)}
          className="lms-btn-secondary px-5 py-2.5 font-['Outfit'] text-sm flex items-center gap-1.5 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
        >
          <ChevronLeft className="size-4" /> Previous
        </button>
        {!currentCheck ? (
          <button
            type="button"
            disabled={answers[currentIndex] < 0 || checking}
            onClick={() => void checkCurrent()}
            className="lms-btn-primary px-6 py-2.5 font-['Outfit'] text-sm flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            {checking ? "Submitting..." : "Submit"}
          </button>
        ) : isLastQuestion ? (
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={!allAnswered || submitting}
            className="lms-btn-primary px-6 py-2.5 font-['Outfit'] text-sm flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            {submitting ? "Submitting..." : "Finish"}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setCurrentIndex((i) => i + 1)}
            className="lms-btn-primary px-6 py-2.5 font-['Outfit'] text-sm flex items-center gap-1.5 cursor-pointer"
          >
            Next <ChevronRight className="size-4" />
          </button>
        )}
      </div>
    </div>
  );
}
