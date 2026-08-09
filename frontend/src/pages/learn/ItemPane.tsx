import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ChevronLeft, ChevronRight, FileWarning, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  checkQuizAnswer, getAttachmentUrl, recordProgress, submitQuiz,
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
  if (item.kind === "video" && "transcode_status" in item.content) {
    return (
      <VideoPlayer
        itemId={item.id}
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

  return null;
}

function readingMinutes(body: string): number {
  const words = body.trim().split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(words / 200));
}

function TextBlock({ body, onContinue }: { body: string; onContinue: () => void }) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-primary mb-2.5">
        Reading · {readingMinutes(body)} min
      </p>
      <div className="p-5 rounded-2xl ring-1 ring-border bg-card/60 whitespace-pre-wrap text-sm leading-relaxed">
        {body}
      </div>
      <Button size="xl" onClick={onContinue} className="mt-5">
        Continue <ChevronRight className="size-4" />
      </Button>
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

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading document...</p>;
  }
  if (isError || !data) {
    return (
      <div className="flex items-center gap-2 p-4 rounded-2xl ring-1 ring-destructive/30 bg-destructive/5 text-destructive text-sm">
        <FileWarning className="size-4 shrink-0" /> Couldn't load this document.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {data.filename && (
        <p className="text-[11px] font-semibold uppercase tracking-wide text-primary">{data.filename}</p>
      )}
      <iframe
        src={data.url}
        title={data.filename ?? "Attachment"}
        className="w-full h-[70vh] rounded-2xl ring-1 ring-border bg-card"
      />
      <Button size="xl" onClick={onDone} className="w-fit">
        Mark as read <ChevronRight className="size-4" />
      </Button>
    </div>
  );
}

function FlashcardsBlock({
  title, cards, onDone,
}: { title: string | null; cards: { term: string; definition: string }[]; onDone: () => void }) {
  const [queue, setQueue] = useState(cards);
  const [doneCount, setDoneCount] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const total = cards.length;

  // A card that's "still learning" gets requeued rather than skipped, so the
  // deck only finishes once every card has been marked "got it" at least once.
  useEffect(() => {
    if (queue.length === 0) onDone();
  }, [queue, onDone]);

  const card = queue[0];
  if (!card) return null;

  const stillLearning = () => {
    setRevealed(false);
    setQueue((prev) => [...prev.slice(1), prev[0]]);
  };

  const gotIt = () => {
    setRevealed(false);
    setDoneCount((n) => n + 1);
    setQueue((prev) => prev.slice(1));
  };

  return (
    <div>
      {title && <p className="text-sm text-muted-foreground mb-2">{title}</p>}
      <button
        onClick={() => setRevealed((r) => !r)}
        className="w-full min-h-48 p-6 rounded-2xl ring-1 ring-border bg-card/60 flex items-center justify-center text-center cursor-pointer hover:ring-primary/30 transition-shadow"
      >
        <span className="font-display text-lg font-medium">{revealed ? card.definition : card.term}</span>
      </button>
      <p className="mt-2.5 text-center text-xs text-muted-foreground">
        {revealed ? "Tap to see the term" : "Tap to reveal"} · {doneCount}/{total} · {total - doneCount} to go
      </p>
      <div className="mt-5 flex gap-2">
        <Button size="xl" variant="outline" className="flex-1" onClick={stillLearning}>
          Still learning
        </Button>
        <Button size="xl" className="flex-1" onClick={gotIt}>
          <CheckCircle2 className="size-4" /> Got it
        </Button>
      </div>
      <button
        onClick={onDone}
        className="mt-3 mx-auto block text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
      >
        Skip deck
      </button>
    </div>
  );
}

function ScoreRing({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div
      className="relative w-[74px] h-[74px] shrink-0 rounded-full flex items-center justify-center"
      style={{ background: `conic-gradient(hsl(var(--primary)) 0% ${pct}%, hsl(var(--muted)) ${pct}% 100%)` }}
    >
      <div className="w-[58px] h-[58px] rounded-full bg-background flex flex-col items-center justify-center">
        <span className="font-display text-lg font-bold leading-none">{Math.round(pct)}%</span>
      </div>
    </div>
  );
}

function QuizBlock({ item, onPassed }: { item: ModuleItem; onPassed: () => void }) {
  const content = "questions" in item.content ? item.content : null;
  const questions = content?.questions ?? [];
  const passThreshold = content?.pass_threshold ?? 0;
  const [answers, setAnswers] = useState<number[]>(() => questions.map(() => -1));
  // One entry per question once its answer has been live-checked — drives
  // both "has this question been revealed yet" and what to show for it.
  // Keyed by question index so Back/Next never re-fetches an already-seen one.
  const [checks, setChecks] = useState<Record<number, QuizAnswerCheck>>({});
  const [checking, setChecking] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [review, setReview] = useState<QuizReview | null>(null);
  const [submitting, setSubmitting] = useState(false);

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

  const retry = () => {
    setReview(null);
    setAnswers(questions.map(() => -1));
    setChecks({});
    setCurrentIndex(0);
  };

  // Reviewing a submitted attempt: the whole point is scanning every
  // result at a glance (right/wrong, explanations), so this stays one
  // list — only the *answering* phase below is paginated.
  if (review) {
    return (
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-4 p-4 rounded-2xl ring-1 ring-border bg-card/60">
          <ScoreRing score={review.score} />
          <div className="min-w-0">
            <p className={`text-[11px] font-semibold uppercase tracking-wide flex items-center gap-1.5 ${review.passed ? "text-emerald-500" : "text-destructive"}`}>
              {review.passed ? <CheckCircle2 className="size-3" /> : <XCircle className="size-3" />}
              {review.passed ? "Passed" : "Not yet"}
              {passThreshold > 0 && ` · ${passThreshold}% needed`}
            </p>
            <p className="font-display text-lg font-bold mt-1">
              {review.passed ? "Check complete" : `Score ${review.score}%`}
            </p>
          </div>
        </div>

        {questions.map((q, qi) => {
          const reviewQ = review.questions[qi];
          return (
            <div key={qi} className="p-4 rounded-2xl ring-1 ring-border bg-card/60">
              <p className="font-medium text-sm mb-3">{q.prompt}</p>
              <div className="flex flex-col gap-2">
                {q.options.map((opt, oi) => {
                  const isSelected = answers[qi] === oi;
                  return (
                    <button
                      key={oi}
                      disabled
                      className={`text-left px-3.5 py-2.5 rounded-xl ring-1 text-sm cursor-default disabled:cursor-default flex items-center justify-between gap-2 transition-colors ${
                        isSelected ? "ring-primary/40 bg-primary/10" : "ring-border"
                      }`}
                    >
                      <span>{opt.text}</span>
                      {isSelected && (reviewQ?.correct ? (
                        <CheckCircle2 className="size-4 text-emerald-500 shrink-0" />
                      ) : (
                        <XCircle className="size-4 text-destructive shrink-0" />
                      ))}
                    </button>
                  );
                })}
              </div>
              <p className={`mt-2 text-xs ${reviewQ.correct ? "text-emerald-500" : "text-destructive"}`}>
                {reviewQ.correct
                  ? `Your answer: ${q.options[reviewQ.selected]?.text ?? ""} ✓`
                  : `You said: ${q.options[reviewQ.selected]?.text ?? ""}${reviewQ.correct_text ? ` · Correct: ${reviewQ.correct_text}` : ""}`}
              </p>
              {!reviewQ.correct && reviewQ.explanation && (
                <p className="mt-1 text-xs text-muted-foreground">{reviewQ.explanation}</p>
              )}
            </div>
          );
        })}

        {!review.passed && (
          <Button size="xl" onClick={retry} className="w-fit">Retry</Button>
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
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          Question {currentIndex + 1} of {questions.length}
        </p>
        {passThreshold > 0 && (
          <p className="text-xs text-muted-foreground">Passing score: {passThreshold}%</p>
        )}
      </div>

      <div className="p-4 rounded-2xl ring-1 ring-border bg-card/60">
        <p className="font-medium text-sm mb-3">{q.prompt}</p>
        <div className="flex flex-col gap-2">
          {q.options.map((opt, oi) => {
            const isSelected = answers[currentIndex] === oi;
            const isRevealedCorrectOption = currentCheck && !currentCheck.correct
              && currentCheck.correct_text != null && opt.text === currentCheck.correct_text;
            return (
              <button
                key={oi}
                disabled={!!currentCheck}
                onClick={() => selectAnswer(oi)}
                className={`text-left px-3.5 py-2.5 rounded-xl ring-1 text-sm flex items-center justify-between gap-2 transition-colors ${
                  currentCheck ? "cursor-default" : "cursor-pointer"
                } ${
                  isSelected ? "ring-primary/40 bg-primary/10" : isRevealedCorrectOption ? "ring-emerald-500/40 bg-emerald-500/5" : "ring-border hover:bg-muted/50"
                }`}
              >
                <span>{opt.text}</span>
                {isSelected && currentCheck && (currentCheck.correct ? (
                  <CheckCircle2 className="size-4 text-emerald-500 shrink-0" />
                ) : (
                  <XCircle className="size-4 text-destructive shrink-0" />
                ))}
                {!isSelected && isRevealedCorrectOption && (
                  <CheckCircle2 className="size-4 text-emerald-500 shrink-0" />
                )}
              </button>
            );
          })}
        </div>
        {checking && <p className="mt-3 text-xs text-muted-foreground">Checking...</p>}
        {currentCheck && (
          <p className={`mt-3 text-xs ${currentCheck.correct ? "text-emerald-500" : "text-destructive"}`}>
            {currentCheck.correct ? "Correct!" : `Not quite — the answer was "${currentCheck.correct_text ?? ""}"`}
          </p>
        )}
        {currentCheck?.explanation && (
          <p className="mt-1 text-xs text-muted-foreground">{currentCheck.explanation}</p>
        )}
      </div>

      <div className="flex gap-2">
        <Button
          size="xl" variant="outline" className="w-fit"
          disabled={currentIndex === 0}
          onClick={() => setCurrentIndex((i) => i - 1)}
        >
          <ChevronLeft className="size-4" /> Previous
        </Button>
        {!currentCheck ? (
          <Button
            size="xl" className="w-fit"
            disabled={answers[currentIndex] < 0 || checking}
            onClick={() => void checkCurrent()}
          >
            {checking ? "Submitting..." : "Submit"}
          </Button>
        ) : isLastQuestion ? (
          <Button
            size="xl" className="w-fit"
            onClick={() => void handleSubmit()}
            disabled={!allAnswered || submitting}
          >
            {submitting ? "Submitting..." : "Finish"}
          </Button>
        ) : (
          <Button
            size="xl" className="w-fit"
            onClick={() => setCurrentIndex((i) => i + 1)}
          >
            Next <ChevronRight className="size-4" />
          </Button>
        )}
      </div>
    </div>
  );
}
