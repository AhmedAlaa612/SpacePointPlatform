import { useMemo, useState } from "react";
import { CheckCircle2, ChevronRight, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogTitle,
} from "@/components/ui/dialog";
import {
  recordProgress, submitQuiz, type ModuleItem, type QuizReview,
} from "@/api/lms";
import { VideoPlayer } from "./VideoPlayer";

/** One switch on item.kind → the five content panes (design 1i). Net-new,
 * replacing the inline switch that used to live directly in the module
 * route — this version has no route of its own, PlayerLayout swaps it in.
 */
export function ItemPane({
  item, moduleItems, onProgressed,
}: { item: ModuleItem; moduleItems: ModuleItem[]; onProgressed: () => void }) {
  const [checkpointOpen, setCheckpointOpen] = useState(false);
  const [resumeSignal, setResumeSignal] = useState(0);

  // A quiz with mid_video_at_seconds references the *other* video item in
  // this same module (service-level rule: exactly one video item when set).
  const checkpointQuiz = useMemo(() => {
    if (item.kind !== "video") return null;
    return moduleItems.find(
      (i) => i.kind === "quiz" && "mid_video_at_seconds" in i.content && i.content.mid_video_at_seconds != null,
    ) ?? null;
  }, [item, moduleItems]);

  if (item.kind === "video" && "transcode_status" in item.content) {
    return (
      <div>
        <VideoPlayer
          itemId={item.id}
          transcodeStatus={item.content.transcode_status}
          checkpointSeconds={checkpointQuiz && "mid_video_at_seconds" in checkpointQuiz.content ? checkpointQuiz.content.mid_video_at_seconds : null}
          onCheckpoint={() => setCheckpointOpen(true)}
          resumeSignal={resumeSignal}
          onEnded={() => { recordProgress(item.id, "video-watched").finally(onProgressed); }}
        />
        <Dialog open={checkpointOpen} onOpenChange={setCheckpointOpen}>
          <DialogContent showCloseButton={false} className="max-w-lg">
            <DialogTitle>Quick check before you continue</DialogTitle>
            {checkpointQuiz && (
              <QuizBlock
                item={checkpointQuiz}
                onPassed={() => {
                  setCheckpointOpen(false);
                  setResumeSignal((n) => n + 1);
                }}
              />
            )}
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  if (item.kind === "text" && "body" in item.content) {
    return <TextBlock body={item.content.body} onContinue={() => recordProgress(item.id, "text-viewed").finally(onProgressed)} />;
  }

  if (item.kind === "flashcards" && "cards" in item.content) {
    return (
      <FlashcardsBlock
        title={item.content.title}
        cards={item.content.cards}
        onDone={() => recordProgress(item.id, "flashcards-skipped").finally(onProgressed)}
      />
    );
  }

  if (item.kind === "quiz") {
    return <QuizBlock item={item} onPassed={onProgressed} />;
  }

  return null;
}

function TextBlock({ body, onContinue }: { body: string; onContinue: () => void }) {
  return (
    <div>
      <div className="p-5 rounded-2xl ring-1 ring-border bg-card/60 whitespace-pre-wrap text-sm leading-relaxed">
        {body}
      </div>
      <Button size="xl" onClick={onContinue} className="mt-5">
        Continue <ChevronRight className="size-4" />
      </Button>
    </div>
  );
}

function FlashcardsBlock({
  title, cards, onDone,
}: { title: string | null; cards: { term: string; definition: string }[]; onDone: () => void }) {
  const [i, setI] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const card = cards[i];
  const isLast = i === cards.length - 1;

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
        {revealed ? "Tap to see the term" : "Tap to reveal"} · {i + 1}/{cards.length}
      </p>
      <div className="mt-5 flex gap-2">
        <Button size="xl" variant="outline" onClick={onDone}>Skip</Button>
        <Button
          size="xl"
          className="flex-1"
          onClick={() => {
            setRevealed(false);
            if (isLast) onDone();
            else setI((n) => n + 1);
          }}
        >
          {isLast ? "Finish" : "Next"}
        </Button>
      </div>
    </div>
  );
}

function QuizBlock({ item, onPassed }: { item: ModuleItem; onPassed: () => void }) {
  const content = "questions" in item.content ? item.content : null;
  const questions = content?.questions ?? [];
  const passThreshold = content?.pass_threshold ?? 0;
  const [answers, setAnswers] = useState<number[]>(() => questions.map(() => -1));
  const [review, setReview] = useState<QuizReview | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!content) return null;

  const allAnswered = answers.every((a) => a >= 0);

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
  };

  return (
    <div className="flex flex-col gap-4">
      {passThreshold > 0 && (
        <p className="text-xs text-muted-foreground">Passing score: {passThreshold}%</p>
      )}
      {questions.map((q, qi) => (
        <div key={qi} className="p-4 rounded-2xl ring-1 ring-border bg-card/60">
          <p className="font-medium text-sm mb-3">{q.prompt}</p>
          <div className="flex flex-col gap-2">
            {q.options.map((opt, oi) => {
              const reviewQ = review?.questions[qi];
              const isSelected = answers[qi] === oi;
              const showResult = review != null && isSelected;
              return (
                <button
                  key={oi}
                  disabled={review != null}
                  onClick={() => setAnswers((prev) => prev.map((a, idx) => (idx === qi ? oi : a)))}
                  className={`text-left px-3.5 py-2.5 rounded-xl ring-1 text-sm cursor-pointer disabled:cursor-default flex items-center justify-between gap-2 transition-colors ${
                    isSelected ? "ring-primary/40 bg-primary/10" : "ring-border hover:bg-muted/50"
                  }`}
                >
                  <span>{opt.text}</span>
                  {showResult && (reviewQ?.correct ? (
                    <CheckCircle2 className="size-4 text-emerald-500 shrink-0" />
                  ) : (
                    <XCircle className="size-4 text-destructive shrink-0" />
                  ))}
                </button>
              );
            })}
          </div>
          {review && !review.questions[qi].correct && review.questions[qi].explanation && (
            <p className="mt-2 text-xs text-muted-foreground">{review.questions[qi].explanation}</p>
          )}
        </div>
      ))}

      {review ? (
        <div>
          <p className={`text-sm font-medium mb-3 ${review.passed ? "text-emerald-500" : "text-destructive"}`}>
            {review.passed ? `Passed — ${review.score}%` : `Score ${review.score}% — try again`}
          </p>
          {!review.passed && <Button size="xl" onClick={retry}>Retry</Button>}
        </div>
      ) : (
        <Button size="xl" onClick={() => void handleSubmit()} disabled={!allAnswered || submitting} className="w-fit">
          {submitting ? "Submitting..." : "Submit"}
        </Button>
      )}
    </div>
  );
}
