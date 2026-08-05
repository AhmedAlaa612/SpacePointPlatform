import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "@tanstack/react-router";
import { CheckCircle2, ChevronRight, XCircle } from "lucide-react";
import {
  fetchModule,
  recordProgress,
  submitQuiz,
  type ModuleDetail,
  type ModuleItem,
  type QuizReview,
} from "@/api/lms";
import { VideoPlayer } from "./VideoPlayer";

/** The module player (LM1-8) — walks items in order: video (with an optional
 * mid-video checkpoint quiz) → text → flashcards → end quiz. D7: quizzes have
 * unlimited retries and a wrong-answer review with explanations after every
 * submission. One write path per kind, mirroring the backend's own discipline
 * (services/lms/progress.py) — this component never guesses completion, it
 * only calls recordProgress/submitQuiz and reacts to what comes back.
 */
export default function LearnModule() {
  // strict from-string lookup can fail to resolve on a fresh/hard page load
  // (see LearnCourse.tsx) — strict: false reads whatever route matched.
  const { moduleId } = useParams({ strict: false }) as { moduleId: string };
  const navigate = useNavigate();
  const [module, setModule] = useState<ModuleDetail | null>(null);
  const [error, setError] = useState("");
  const [index, setIndex] = useState(0);
  const [resumeSignal, setResumeSignal] = useState(0);
  const [checkpointOpen, setCheckpointOpen] = useState(false);

  useEffect(() => {
    fetchModule(moduleId)
      .then((data) => {
        setModule(data);
        const firstIncomplete = data.items.findIndex((i) => i.status !== "completed" && i.status !== "skipped");
        setIndex(firstIncomplete === -1 ? Math.max(data.items.length - 1, 0) : firstIncomplete);
      })
      .catch(() => setError("Couldn't load this module."));
  }, [moduleId]);

  const item = module?.items[index];

  // A quiz item with mid_video_at_seconds references the *previous* video
  // item in the same module (service-level rule: exactly one video per
  // module when this is set) — find it once we know the module's items.
  const checkpointQuiz = useMemo(() => {
    if (!module || item?.kind !== "video") return null;
    return module.items.find(
      (i) => i.kind === "quiz" && "mid_video_at_seconds" in i.content && i.content.mid_video_at_seconds != null,
    ) ?? null;
  }, [module, item]);

  const advance = useCallback(() => {
    setModule((prev) => {
      if (!prev) return prev;
      const next = index + 1;
      if (next >= prev.items.length) {
        void navigate({ to: `/learn/courses/${prev.course_id}` });
        return prev;
      }
      setIndex(next);
      return prev;
    });
  }, [index, navigate]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!module || !item) return <p className="text-sm text-muted-foreground">Loading...</p>;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold truncate">{module.title}</h1>
        <span className="text-xs text-muted-foreground shrink-0">
          {index + 1}/{module.items.length}
        </span>
      </div>

      {item.kind === "video" && "transcode_status" in item.content && (
        <>
          <VideoPlayer
            itemId={item.id}
            transcodeStatus={item.content.transcode_status}
            checkpointSeconds={checkpointQuiz && "mid_video_at_seconds" in checkpointQuiz.content
              ? checkpointQuiz.content.mid_video_at_seconds : null}
            onCheckpoint={() => setCheckpointOpen(true)}
            resumeSignal={resumeSignal}
            onEnded={() => {
              recordProgress(item.id, "video-watched").finally(advance);
            }}
          />
          {checkpointOpen && checkpointQuiz && (
            <div className="mt-4 p-4 rounded-xl border border-border bg-card">
              <p className="text-xs text-muted-foreground mb-2">Quick check before you continue</p>
              <QuizBlock
                item={checkpointQuiz}
                onPassed={() => {
                  setCheckpointOpen(false);
                  setResumeSignal((n) => n + 1);
                }}
              />
            </div>
          )}
        </>
      )}

      {item.kind === "text" && "body" in item.content && (
        <TextBlock body={item.content.body} onContinue={() => recordProgress(item.id, "text-viewed").finally(advance)} />
      )}

      {item.kind === "flashcards" && "cards" in item.content && (
        <FlashcardsBlock
          title={item.content.title}
          cards={item.content.cards}
          onDone={() => recordProgress(item.id, "flashcards-skipped").finally(advance)}
        />
      )}

      {item.kind === "quiz" && checkpointQuiz?.id !== item.id && (
        <QuizBlock item={item} onPassed={advance} />
      )}
    </div>
  );
}

function TextBlock({ body, onContinue }: { body: string; onContinue: () => void }) {
  return (
    <div>
      <div className="p-4 rounded-xl border border-border bg-card whitespace-pre-wrap text-sm leading-relaxed">
        {body}
      </div>
      <button
        onClick={onContinue}
        className="mt-4 h-11 px-6 bg-primary text-primary-foreground rounded-xl font-medium text-sm cursor-pointer flex items-center gap-1"
      >
        Continue <ChevronRight size={16} />
      </button>
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
        className="w-full min-h-40 p-6 rounded-xl border border-border bg-card flex items-center justify-center text-center cursor-pointer"
      >
        <span className="text-base font-medium">{revealed ? card.definition : card.term}</span>
      </button>
      <p className="mt-2 text-center text-xs text-muted-foreground">
        {revealed ? "Tap to see the term" : "Tap to reveal"} · {i + 1}/{cards.length}
      </p>
      <div className="mt-4 flex gap-2">
        <button
          onClick={onDone}
          className="h-11 px-4 border border-border rounded-xl text-sm text-muted-foreground cursor-pointer"
        >
          Skip
        </button>
        <button
          onClick={() => {
            setRevealed(false);
            if (isLast) onDone();
            else setI((n) => n + 1);
          }}
          className="flex-1 h-11 bg-primary text-primary-foreground rounded-xl font-medium text-sm cursor-pointer"
        >
          {isLast ? "Finish" : "Next"}
        </button>
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
        <div key={qi} className="p-4 rounded-xl border border-border bg-card">
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
                  className={`text-left px-3 py-2 rounded-lg border text-sm cursor-pointer disabled:cursor-default flex items-center justify-between gap-2 ${
                    isSelected ? "border-primary bg-primary/5" : "border-border"
                  }`}
                >
                  <span>{opt.text}</span>
                  {showResult && (reviewQ?.correct ? (
                    <CheckCircle2 size={16} className="text-primary shrink-0" />
                  ) : (
                    <XCircle size={16} className="text-destructive shrink-0" />
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
          <p className={`text-sm font-medium mb-3 ${review.passed ? "text-primary" : "text-destructive"}`}>
            {review.passed ? `Passed — ${review.score}%` : `Score ${review.score}% — try again`}
          </p>
          {!review.passed && (
            <button
              onClick={retry}
              className="h-11 px-6 bg-primary text-primary-foreground rounded-xl font-medium text-sm cursor-pointer"
            >
              Retry
            </button>
          )}
        </div>
      ) : (
        <button
          onClick={() => void handleSubmit()}
          disabled={!allAnswered || submitting}
          className="h-11 px-6 bg-primary text-primary-foreground rounded-xl font-medium text-sm disabled:opacity-50 cursor-pointer"
        >
          {submitting ? "Submitting..." : "Submit"}
        </button>
      )}
    </div>
  );
}
