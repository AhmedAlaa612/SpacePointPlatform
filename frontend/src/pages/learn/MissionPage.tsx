import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, Link } from "@tanstack/react-router";
import { isAxiosError } from "axios";
import { CheckCircle2, ChevronRight, Rocket, Sparkles, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  fetchMission, startMissionAttempt, submitQuizAttempt, submitSubmissionAttempt,
  type MissionAttempt, type MissionDetail, type MissionQuizReview,
} from "@/api/missions";

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail;
  return fallback;
}

/** Mission landing + attempt flow (P5-4) — orient, pick a variant, attempt,
 * see the result, all on one page (unlike a course, a mission has no
 * multi-module player to route into). `quiz` self-grades immediately;
 * `submission` hands off to a human reviewer and the page polls nothing —
 * the student comes back later and the attempt just reads `passed` once
 * reviewed. */
export default function MissionPage() {
  const { missionId } = useParams({ strict: false }) as { missionId: string };
  const [mission, setMission] = useState<MissionDetail | null>(null);
  const [error, setError] = useState("");
  const [selectedVariantId, setSelectedVariantId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");
  const [quizReview, setQuizReview] = useState<MissionQuizReview | null>(null);

  const load = useCallback(() => {
    fetchMission(missionId)
      .then((m) => {
        setMission(m);
        setSelectedVariantId((prev) => prev ?? m.variants[0]?.id ?? null);
      })
      .catch(() => setError("Couldn't load this mission."));
  }, [missionId]);

  useEffect(() => {
    load();
  }, [load]);

  // Most recent attempt, if any — drives which panel shows.
  const activeAttempt: MissionAttempt | null = useMemo(() => {
    if (!mission || mission.attempts.length === 0) return null;
    return mission.attempts[mission.attempts.length - 1];
  }, [mission]);

  const handleStart = async () => {
    if (!mission || !selectedVariantId) return;
    setStarting(true);
    setStartError("");
    setQuizReview(null);
    try {
      await startMissionAttempt(mission.id, selectedVariantId);
      load();
    } catch (err) {
      setStartError(errorDetail(err, "Couldn't start this mission right now."));
    } finally {
      setStarting(false);
    }
  };

  if (error) return <div className="mx-auto max-w-[900px] px-5 py-10"><p className="text-sm text-destructive">{error}</p></div>;
  if (!mission) return <div className="mx-auto max-w-[900px] px-5 py-10"><p className="text-sm text-muted-foreground">Loading...</p></div>;

  const selectedVariant = mission.variants.find((v) => v.id === selectedVariantId) ?? mission.variants[0];
  const inProgress = activeAttempt?.status === "in_progress";
  const decided = activeAttempt?.status === "passed" || activeAttempt?.status === "failed";

  return (
    <div className="mx-auto max-w-[900px] px-5 sm:px-8 py-6 sm:py-8 flex flex-col gap-6">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Link to="/learn/missions" className="text-primary hover:opacity-80">Missions</Link>
        {mission.track && (
          <>
            <ChevronRight className="size-3" />
            <span>{mission.track}</span>
          </>
        )}
        <ChevronRight className="size-3" />
        <span className="text-foreground">{mission.title}</span>
      </div>

      <div className="flex flex-col gap-3">
        <div className="w-fit flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded-md bg-primary/10 text-primary">
          <Rocket className="size-3" /> Mission
        </div>
        <h1 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight leading-tight">{mission.title}</h1>
        {mission.description && <p className="text-base leading-relaxed text-muted-foreground max-w-xl">{mission.description}</p>}
      </div>

      {inProgress && mission.kind === "quiz" && selectedVariant && (
        <MissionQuizForm
          attemptId={activeAttempt.id}
          variant={selectedVariant}
          review={quizReview}
          onSubmitted={(result) => {
            setQuizReview(result.review);
            load();
          }}
        />
      )}

      {inProgress && mission.kind === "submission" && (
        <MissionSubmissionForm attemptId={activeAttempt.id} onSubmitted={load} />
      )}

      {activeAttempt?.status === "submitted" && (
        <Card className="p-5 flex flex-col gap-1.5">
          <p className="text-sm font-medium">Awaiting review</p>
          <p className="text-xs text-muted-foreground">
            You submitted this attempt — a reviewer will score it soon. Check back on this page later.
          </p>
        </Card>
      )}

      {decided && (
        <Card className="p-5 flex items-center gap-4">
          {activeAttempt.status === "passed" ? (
            <CheckCircle2 className="size-8 text-emerald-500 shrink-0" />
          ) : (
            <XCircle className="size-8 text-destructive shrink-0" />
          )}
          <div className="min-w-0">
            <p className={`text-sm font-semibold ${activeAttempt.status === "passed" ? "text-emerald-500" : "text-destructive"}`}>
              {activeAttempt.status === "passed" ? "Passed" : "Not this time"}
            </p>
            {activeAttempt.score != null && <p className="text-xs text-muted-foreground mt-0.5">Score: {activeAttempt.score}</p>}
          </div>
        </Card>
      )}

      {(!activeAttempt || decided) && (
        <Card className="p-5 flex flex-col gap-4">
          {mission.variants.length > 1 && (
            <div className="flex flex-col gap-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Difficulty</p>
              <div className="flex flex-wrap gap-2">
                {mission.variants.map((v) => (
                  <button
                    key={v.id}
                    onClick={() => setSelectedVariantId(v.id)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-sm ring-1 transition-colors ${
                      v.id === selectedVariantId ? "ring-primary/40 bg-primary/10 text-primary font-medium" : "ring-border hover:bg-muted/50"
                    }`}
                  >
                    {v.label}
                    <span className="text-xs text-muted-foreground flex items-center gap-0.5"><Sparkles className="size-3" /> {v.points}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          <Button size="xl" className="w-fit" onClick={() => void handleStart()} disabled={starting || !selectedVariantId}>
            {starting ? "Starting..." : decided ? "Try again" : "Start mission"}
          </Button>
          {startError && <p className="text-xs text-destructive">{startError}</p>}
        </Card>
      )}
    </div>
  );
}

function MissionQuizForm({
  attemptId, variant, review, onSubmitted,
}: {
  attemptId: string;
  variant: MissionDetail["variants"][number];
  review: MissionQuizReview | null;
  onSubmitted: (result: { review: MissionQuizReview | null }) => void;
}) {
  const questions = "questions" in variant.config ? variant.config.questions : [];
  const passThreshold = "pass_threshold" in variant.config ? variant.config.pass_threshold : 0;
  const [answers, setAnswers] = useState<number[]>(() => questions.map(() => -1));
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  const allAnswered = answers.length > 0 && answers.every((a) => a >= 0);

  const handleSubmit = async () => {
    setSubmitting(true);
    setSubmitError("");
    try {
      const result = await submitQuizAttempt(attemptId, answers);
      onSubmitted(result);
    } catch (err) {
      setSubmitError(errorDetail(err, "Couldn't submit this attempt right now."));
    } finally {
      setSubmitting(false);
    }
  };

  if (review) {
    return (
      <div className="flex flex-col gap-4">
        <Card className="p-4 flex items-center gap-4">
          {review.passed ? <CheckCircle2 className="size-6 text-emerald-500 shrink-0" /> : <XCircle className="size-6 text-destructive shrink-0" />}
          <div>
            <p className={`text-sm font-semibold ${review.passed ? "text-emerald-500" : "text-destructive"}`}>
              {review.passed ? "Passed" : "Not yet"} · {review.score}%{passThreshold > 0 && ` (${passThreshold}% needed)`}
            </p>
          </div>
        </Card>
        {questions.map((q, qi) => {
          const reviewQ = review.questions[qi];
          return (
            <Card key={qi} className="p-4">
              <p className="font-medium text-sm mb-3">{q.prompt}</p>
              <div className="flex flex-col gap-2">
                {q.options.map((opt, oi) => {
                  const isSelected = reviewQ?.selected === oi;
                  return (
                    <div
                      key={oi}
                      className={`px-3.5 py-2.5 rounded-xl ring-1 text-sm flex items-center justify-between gap-2 ${
                        isSelected ? "ring-primary/40 bg-primary/10" : "ring-border"
                      }`}
                    >
                      <span>{opt.text}</span>
                      {isSelected && (reviewQ?.correct ? (
                        <CheckCircle2 className="size-4 text-emerald-500 shrink-0" />
                      ) : (
                        <XCircle className="size-4 text-destructive shrink-0" />
                      ))}
                    </div>
                  );
                })}
              </div>
              {!reviewQ?.correct && reviewQ?.correct_text && (
                <p className="mt-2 text-xs text-destructive">Correct answer: {reviewQ.correct_text}</p>
              )}
            </Card>
          );
        })}
      </div>
    );
  }

  return (
    <Card className="p-5 flex flex-col gap-5">
      {questions.map((q, qi) => (
        <div key={qi} className="flex flex-col gap-2">
          <p className="font-medium text-sm">{qi + 1}. {q.prompt}</p>
          <div className="flex flex-col gap-2">
            {q.options.map((opt, oi) => (
              <button
                key={oi}
                onClick={() => setAnswers((prev) => prev.map((a, idx) => (idx === qi ? oi : a)))}
                className={`text-left px-3.5 py-2.5 rounded-xl ring-1 text-sm transition-colors ${
                  answers[qi] === oi ? "ring-primary/40 bg-primary/10" : "ring-border hover:bg-muted/50"
                }`}
              >
                {opt.text}
              </button>
            ))}
          </div>
        </div>
      ))}
      <Button size="xl" className="w-fit" onClick={() => void handleSubmit()} disabled={!allAnswered || submitting}>
        {submitting ? "Submitting..." : "Submit"}
      </Button>
      {submitError && <p className="text-xs text-destructive">{submitError}</p>}
    </Card>
  );
}

function MissionSubmissionForm({ attemptId, onSubmitted }: { attemptId: string; onSubmitted: () => void }) {
  const [artifactUrl, setArtifactUrl] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  const handleSubmit = async () => {
    if (!artifactUrl.trim()) return;
    setSubmitting(true);
    setSubmitError("");
    try {
      await submitSubmissionAttempt(attemptId, artifactUrl.trim(), notes.trim() || undefined);
      onSubmitted();
    } catch (err) {
      setSubmitError(errorDetail(err, "Couldn't submit this attempt right now."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="p-5 flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Link to your work</label>
        <input
          value={artifactUrl}
          onChange={(e) => setArtifactUrl(e.target.value)}
          placeholder="https://..."
          className="h-10 px-3.5 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Notes (optional)</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          className="px-3.5 py-2.5 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors resize-none"
        />
      </div>
      <Button size="xl" className="w-fit" onClick={() => void handleSubmit()} disabled={!artifactUrl.trim() || submitting}>
        {submitting ? "Submitting..." : "Submit for review"}
      </Button>
      {submitError && <p className="text-xs text-destructive">{submitError}</p>}
    </Card>
  );
}
