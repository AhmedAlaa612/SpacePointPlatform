import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, Link } from "@tanstack/react-router";
import { isAxiosError } from "axios";
import { CheckCircle2, ChevronRight, Lock, Rocket, Sparkles, Users, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  createTeam, fetchMission, startMissionAttempt, submitQuizAttempt, submitSubmissionAttempt,
  type MissionAttempt, type MissionDetail, type MissionQuizReview, type MissionTeam,
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
  const navigate = useNavigate();
  const [mission, setMission] = useState<MissionDetail | null>(null);
  const [error, setError] = useState("");
  const [selectedVariantId, setSelectedVariantId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");
  const [quizReview, setQuizReview] = useState<MissionQuizReview | null>(null);
  // "either" missions let the student pick; "team" forces it; "solo" never shows this.
  const [asTeam, setAsTeam] = useState(false);
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [newTeamName, setNewTeamName] = useState("");
  const [creatingTeam, setCreatingTeam] = useState(false);
  const [teamError, setTeamError] = useState("");

  const load = useCallback(() => {
    fetchMission(missionId)
      .then((m) => {
        setMission(m);
        setSelectedVariantId((prev) => prev ?? m.variants[0]?.id ?? null);
        setSelectedTeamId((prev) => prev ?? m.my_teams[0]?.id ?? null);
        setAsTeam((prev) => prev || m.team_policy === "team");
      })
      .catch(() => setError("Couldn't load this mission."));
  }, [missionId]);

  // Client-side navigation between two mission pages (e.g. a prerequisite
  // chip) reuses this component without remounting — reset per-mission
  // state before the new fetch lands, or a stale selectedVariantId from
  // the previous mission survives and 404s the new one's start call.
  useEffect(() => {
    setMission(null);
    setSelectedVariantId(null);
    setQuizReview(null);
    setError("");
    setAsTeam(false);
    setSelectedTeamId(null);
    setTeamError("");
  }, [missionId]);

  useEffect(() => {
    load();
  }, [load]);

  // Most recent attempt, if any — drives which panel shows.
  const activeAttempt: MissionAttempt | null = useMemo(() => {
    if (!mission || mission.attempts.length === 0) return null;
    return mission.attempts[mission.attempts.length - 1];
  }, [mission]);

  // A design mission is a whole nine-step wizard and an operate mission is
  // a live console — neither is a single attempt form, each lives at its
  // own route, keyed on the attempt (P7-5 / Stage 7B-4). Any existing
  // attempt sends the student straight there: design attempts never
  // become "failed" (stay in_progress until ready), operate attempts can,
  // but a decided operate attempt is still best viewed on its own console
  // (it shows the final telemetry/score), not back on this generic page.
  useEffect(() => {
    if (!mission || !activeAttempt) return;
    if (mission.kind === "design") {
      navigate({ to: "/learn/missions/design/$attemptId", params: { attemptId: activeAttempt.id }, replace: true });
    } else if (mission.kind === "operate") {
      navigate({ to: "/learn/missions/operate/$attemptId", params: { attemptId: activeAttempt.id }, replace: true });
    }
  }, [mission, activeAttempt, navigate]);

  const handleStart = async () => {
    if (!mission || !selectedVariantId) return;
    if (asTeam && !selectedTeamId) return;
    setStarting(true);
    setStartError("");
    setQuizReview(null);
    try {
      const attempt = await startMissionAttempt(mission.id, selectedVariantId, asTeam ? selectedTeamId! : undefined);
      if (mission.kind === "design") {
        navigate({ to: "/learn/missions/design/$attemptId", params: { attemptId: attempt.id } });
        return;
      }
      if (mission.kind === "operate") {
        navigate({ to: "/learn/missions/operate/$attemptId", params: { attemptId: attempt.id } });
        return;
      }
      load();
    } catch (err) {
      setStartError(errorDetail(err, "Couldn't start this mission right now."));
    } finally {
      setStarting(false);
    }
  };

  const handleCreateTeam = async () => {
    if (!newTeamName.trim()) return;
    setCreatingTeam(true);
    setTeamError("");
    try {
      const team = await createTeam(newTeamName.trim());
      setNewTeamName("");
      setSelectedTeamId(team.id);
      load();
    } catch (err) {
      setTeamError(errorDetail(err, "Couldn't create this team right now."));
    } finally {
      setCreatingTeam(false);
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

      {activeAttempt?.team_name && (inProgress || activeAttempt.status === "submitted" || decided) && (
        <div className="w-fit flex items-center gap-1.5 text-xs text-muted-foreground px-2.5 py-1 rounded-lg ring-1 ring-border">
          <Users className="size-3.5" /> Team: {activeAttempt.team_name}
        </div>
      )}

      {activeAttempt?.status === "submitted" && (
        <Card className="p-5 flex flex-col gap-1.5">
          <p className="text-sm font-medium">Awaiting review</p>
          <p className="text-xs text-muted-foreground">
            {activeAttempt.team_name ? "Your team submitted" : "You submitted"} this attempt — a reviewer will score it soon. Check back on this page later.
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

      {mission.locked && (
        <Card className="p-5 flex flex-col gap-2">
          <p className="text-sm font-semibold flex items-center gap-1.5"><Lock className="size-4" /> Locked</p>
          <p className="text-xs text-muted-foreground">Complete these missions first:</p>
          <div className="flex flex-wrap gap-2 mt-1">
            {mission.prerequisites.map((p) => (
              <Link
                key={p.mission_id}
                to="/learn/missions/$missionId"
                params={{ missionId: p.mission_id }}
                className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg ring-1 ${
                  p.satisfied ? "ring-emerald-500/30 text-emerald-500" : "ring-border text-muted-foreground"
                }`}
              >
                {p.satisfied ? <CheckCircle2 className="size-3" /> : <Lock className="size-3" />}
                {p.title}
              </Link>
            ))}
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

          {mission.team_policy !== "solo" && (
            <TeamPicker
              teamPolicy={mission.team_policy}
              myTeams={mission.my_teams}
              asTeam={asTeam}
              onModeChange={setAsTeam}
              selectedTeamId={selectedTeamId}
              onSelectTeam={setSelectedTeamId}
              newTeamName={newTeamName}
              onNewTeamNameChange={setNewTeamName}
              onCreateTeam={() => void handleCreateTeam()}
              creatingTeam={creatingTeam}
              teamError={teamError}
            />
          )}

          <Button
            size="xl" className="w-fit" onClick={() => void handleStart()}
            disabled={starting || !selectedVariantId || mission.locked || (asTeam && !selectedTeamId)}
          >
            {mission.locked ? "Locked" : starting ? "Starting..." : decided ? "Try again" : "Start mission"}
          </Button>
          {startError && <p className="text-xs text-destructive">{startError}</p>}
        </Card>
      )}
    </div>
  );
}

function TeamPicker({
  teamPolicy, myTeams, asTeam, onModeChange, selectedTeamId, onSelectTeam,
  newTeamName, onNewTeamNameChange, onCreateTeam, creatingTeam, teamError,
}: {
  teamPolicy: MissionDetail["team_policy"];
  myTeams: MissionTeam[];
  asTeam: boolean;
  onModeChange: (asTeam: boolean) => void;
  selectedTeamId: string | null;
  onSelectTeam: (teamId: string) => void;
  newTeamName: string;
  onNewTeamNameChange: (name: string) => void;
  onCreateTeam: () => void;
  creatingTeam: boolean;
  teamError: string;
}) {
  return (
    <div className="flex flex-col gap-2 pt-1 border-t border-border">
      {teamPolicy === "either" && (
        <div className="flex items-center gap-2 pt-3">
          <button
            onClick={() => onModeChange(false)}
            className={`px-3 py-1.5 rounded-xl text-sm ring-1 transition-colors ${!asTeam ? "ring-primary/40 bg-primary/10 text-primary font-medium" : "ring-border hover:bg-muted/50"}`}
          >
            Solo
          </button>
          <button
            onClick={() => onModeChange(true)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-sm ring-1 transition-colors ${asTeam ? "ring-primary/40 bg-primary/10 text-primary font-medium" : "ring-border hover:bg-muted/50"}`}
          >
            <Users className="size-3.5" /> Team
          </button>
        </div>
      )}
      {asTeam && (
        <div className={teamPolicy === "either" ? "flex flex-col gap-2" : "flex flex-col gap-2 pt-3"}>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Your team</p>
          {myTeams.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {myTeams.map((t) => (
                <button
                  key={t.id}
                  onClick={() => onSelectTeam(t.id)}
                  className={`px-3 py-1.5 rounded-xl text-sm ring-1 transition-colors ${
                    t.id === selectedTeamId ? "ring-primary/40 bg-primary/10 text-primary font-medium" : "ring-border hover:bg-muted/50"
                  }`}
                >
                  {t.name} <span className="text-xs text-muted-foreground">({t.member_names.length})</span>
                </button>
              ))}
            </div>
          )}
          <div className="flex items-center gap-2">
            <input
              value={newTeamName}
              onChange={(e) => onNewTeamNameChange(e.target.value)}
              placeholder="New team name..."
              className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors flex-1 min-w-0"
            />
            <Button size="sm" onClick={onCreateTeam} disabled={!newTeamName.trim() || creatingTeam}>
              {creatingTeam ? "Creating..." : "Create"}
            </Button>
          </div>
          {teamError && <p className="text-xs text-destructive">{teamError}</p>}
        </div>
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
