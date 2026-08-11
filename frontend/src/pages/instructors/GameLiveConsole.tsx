import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "@tanstack/react-router"
import { CheckCircle2, ChevronLeft, EyeOff, RotateCcw, Square, Timer, Trophy, Users } from "lucide-react"
import {
  endRunApi, getCurrentQuestionApi, getLeaderboardApi, getRosterApi, getRunApi, nextQuestionApi,
  revealParticipantNameApi, revealRunApi, restartRunApi, startRunApi,
  type LeaderboardEntry, type QuestionResult,
} from "@/api/games_live"
import { useGameRunSocket } from "@/hooks/useGameRunSocket"
import { PageHeader, Spinner } from "@/pages/instructors/components/common"
import { ConfirmDialog } from "@/pages/admin/components/common"
import { Card, CardContent } from "@/components/ui/card"
import { useToast } from "@/components/ui/toast"

/** Instructor live console (Live Games Phase 2C, 8-7) — Claude Design
 * spec Frame 02: 2a "question" (prompt, countdown, roster grid ticking
 * off who's answered) and 2b "results" (per-option bars, staff
 * leaderboard, blackout banner) — driven by the run's own status plus a
 * local `revealed` flag (Reveal closes the question without moving
 * position; Next is the separate action that actually advances). WS
 * (8-5) keeps this in sync with itself and, once 8-8 exists, with
 * students; `game_restarted` swaps the console onto the new run's
 * channel automatically since `runId` state is what the socket keys on. */

type Phase = "lobby" | "question" | "results" | "ended"

function Countdown({ seconds, keyProp }: { seconds: number; keyProp: string }) {
  const [remaining, setRemaining] = useState(seconds)
  useEffect(() => {
    setRemaining(seconds)
    const start = Date.now()
    const id = setInterval(() => {
      const left = Math.max(0, seconds - Math.floor((Date.now() - start) / 1000))
      setRemaining(left)
      if (left === 0) clearInterval(id)
    }, 250)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keyProp, seconds])

  return (
    <div className={`w-16 h-16 rounded-full border-4 flex items-center justify-center text-lg font-bold ${
      remaining <= 5 ? "border-destructive text-destructive" : "border-primary text-primary"
    }`}>
      {remaining}
    </div>
  )
}

function RevealNamePopover({ runId, participantId, nickname }: { runId: string; participantId: string; nickname: string }) {
  const [name, setName] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const reveal = async () => {
    if (name) { setName(null); return }
    setLoading(true)
    try {
      const res = await revealParticipantNameApi(runId, participantId)
      setName(res.real_name)
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      onClick={reveal}
      className="text-sm text-foreground hover:underline text-left"
      title="Click to reveal real name (staff only)"
    >
      {name ?? nickname}
      {loading && "…"}
    </button>
  )
}

export default function GameLiveConsole() {
  const { runId } = useParams({ strict: false }) as { runId: string }
  const navigate = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()
  const [revealed, setRevealed] = useState(false)
  const [results, setResults] = useState<QuestionResult[] | null>(null)
  const [restartConfirm, setRestartConfirm] = useState(false)
  const [endConfirm, setEndConfirm] = useState(false)

  const runKey = ["game-run", runId]
  const { data: run, isLoading } = useQuery({ queryKey: runKey, queryFn: () => getRunApi(runId) })

  const { data: question } = useQuery({
    queryKey: ["game-run-question", runId, run?.current_question_position],
    queryFn: () => getCurrentQuestionApi(runId),
    enabled: !!run && run.status === "live",
  })

  const { data: roster = [] } = useQuery({
    queryKey: ["game-run-roster", runId, run?.current_question_position],
    queryFn: () => getRosterApi(runId),
    enabled: !!run && (run.status === "lobby" || run.status === "live"),
    refetchInterval: run?.status === "live" && !revealed ? 3000 : false,
  })

  const { data: leaderboard = [] } = useQuery<LeaderboardEntry[]>({
    queryKey: ["game-run-leaderboard", runId],
    queryFn: () => getLeaderboardApi(runId),
    enabled: revealed,
  })

  useGameRunSocket(runId, (msg) => {
    if (msg.type === "question_started") {
      setRevealed(false)
      setResults(null)
      qc.invalidateQueries({ queryKey: runKey })
    } else if (msg.type === "leaderboard_update") {
      setRevealed(true)
      qc.invalidateQueries({ queryKey: ["game-run-leaderboard", runId] })
    } else if (msg.type === "game_restarted") {
      toast.success("Game restarted")
      void navigate({ to: "/instructors/game-runs/$runId", params: { runId: msg.payload.new_run_id } })
    } else if (msg.type === "game_ended") {
      qc.invalidateQueries({ queryKey: runKey })
    }
  })

  const start = useMutation({
    mutationFn: () => startRunApi(runId),
    onSuccess: () => { setRevealed(false); qc.invalidateQueries({ queryKey: runKey }) },
  })
  const reveal = useMutation({
    mutationFn: () => revealRunApi(runId),
    onSuccess: (r) => { setResults(r); setRevealed(true) },
  })
  const next = useMutation({
    mutationFn: () => nextQuestionApi(runId),
    onSuccess: () => { setRevealed(false); setResults(null); qc.invalidateQueries({ queryKey: runKey }) },
  })
  const restart = useMutation({
    mutationFn: () => restartRunApi(runId),
    onSuccess: (newRun) => {
      setRestartConfirm(false)
      toast.success("Restarted — past points from this run are reversed")
      void navigate({ to: "/instructors/game-runs/$runId", params: { runId: newRun.id } })
    },
  })
  const end = useMutation({
    mutationFn: () => endRunApi(runId),
    onSuccess: () => { setEndConfirm(false); qc.invalidateQueries({ queryKey: runKey }) },
  })

  if (isLoading || !run) return <Spinner />

  const phase: Phase = run.status === "ended" ? "ended" : run.status === "lobby" ? "lobby" : revealed ? "results" : "question"
  const answeredCount = roster.filter((r) => r.has_answered_current).length

  return (
    <div className="flex flex-col gap-4">
      <button
        onClick={() => window.history.back()}
        className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ChevronLeft size={14} /> Back
      </button>

      <PageHeader
        title={`Live Quiz — run ${run.run_no}`}
        subtitle={`${run.total_questions} question${run.total_questions === 1 ? "" : "s"}${run.blackout_active ? " · blackout round" : ""}`}
        action={
          <div className="flex items-center gap-2">
            {run.status !== "ended" && (
              <button
                onClick={() => setRestartConfirm(true)}
                className="h-9 px-3 border border-border rounded-lg text-xs font-medium text-foreground hover:bg-muted transition-colors flex items-center gap-1.5"
              >
                <RotateCcw size={12} /> Restart
              </button>
            )}
            {run.status !== "ended" && (
              <button
                onClick={() => setEndConfirm(true)}
                className="h-9 px-3 border border-border rounded-lg text-xs font-medium text-destructive hover:bg-destructive/10 transition-colors flex items-center gap-1.5"
              >
                <Square size={12} /> End
              </button>
            )}
          </div>
        }
      />

      {run.blackout_active && phase !== "lobby" && (
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-400 text-sm">
          <EyeOff size={14} /> Blackout round — students only see their own score now. You still see everything.
        </div>
      )}

      {phase === "lobby" && (
        <Card>
          <CardContent className="p-6 flex flex-col items-center gap-4 text-center">
            <Users size={28} className="text-muted-foreground" />
            <div>
              <p className="text-sm font-semibold text-foreground">{roster.length} joined</p>
              <p className="text-xs text-muted-foreground mt-1">Waiting for students. Start whenever you're ready.</p>
            </div>
            {roster.length > 0 && (
              <div className="flex flex-wrap justify-center gap-1.5 max-w-md">
                {roster.map((p) => (
                  <span key={p.participant_id} className="text-xs px-2.5 py-1 rounded-full bg-muted text-foreground">{p.nickname}</span>
                ))}
              </div>
            )}
            <button
              onClick={() => start.mutate()}
              disabled={start.isPending}
              className="h-10 px-6 bg-primary text-primary-foreground rounded-xl text-sm font-semibold hover:opacity-90 transition-colors disabled:opacity-50"
            >
              {start.isPending ? "Starting…" : "Start"}
            </button>
          </CardContent>
        </Card>
      )}

      {phase === "question" && question && (
        <div className="flex flex-col gap-4">
          <Card>
            <CardContent className="p-6 flex flex-col gap-4">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">Question {question.position} of {run.total_questions}</p>
                  <p className="text-lg font-semibold text-foreground mt-1">{question.prompt}</p>
                </div>
                <Countdown seconds={question.time_limit_seconds} keyProp={question.id} />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {question.options.map((o, i) => (
                  <div
                    key={i}
                    className={`flex items-center gap-2 h-11 px-3 rounded-xl border text-sm ${
                      o.is_correct ? "border-emerald-500/40 bg-emerald-500/5 text-foreground" : "border-border text-foreground"
                    }`}
                  >
                    <span className="w-5 h-5 flex-none flex items-center justify-center rounded-md border border-current text-[10px] font-bold">
                      {String.fromCharCode(65 + i)}
                    </span>
                    <span className="flex-1 truncate">{o.text}</span>
                    {o.is_correct && <CheckCircle2 size={14} className="text-emerald-500" />}
                  </div>
                ))}
              </div>
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">{answeredCount} / {roster.length} answered</p>
                <button
                  onClick={() => reveal.mutate()}
                  disabled={reveal.isPending}
                  className="h-9 px-4 bg-primary text-primary-foreground rounded-xl text-xs font-semibold hover:opacity-90 transition-colors disabled:opacity-50"
                >
                  {reveal.isPending ? "Revealing…" : "Reveal answers"}
                </button>
              </div>
            </CardContent>
          </Card>

          <RosterGrid roster={roster} />
        </div>
      )}

      {phase === "results" && (
        <div className="flex flex-col gap-4">
          {results && (
            <Card>
              <CardContent className="p-6 flex flex-col gap-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Results</p>
                {results.map((r) => (
                  <div key={r.index} className="flex items-center gap-3">
                    <span className={`w-5 h-5 flex-none flex items-center justify-center rounded-md border text-[10px] font-bold ${
                      r.is_correct ? "border-emerald-500 text-emerald-500" : "border-border text-muted-foreground"
                    }`}>
                      {String.fromCharCode(65 + r.index)}
                    </span>
                    <span className="text-sm text-foreground w-40 truncate">{r.text}</span>
                    <div className="flex-1 h-2.5 rounded-full bg-muted overflow-hidden">
                      <div
                        className={`h-full ${r.is_correct ? "bg-emerald-500" : "bg-muted-foreground/40"}`}
                        style={{ width: `${r.pct}%` }}
                      />
                    </div>
                    <span className="text-xs text-muted-foreground w-16 text-right">{r.count} · {r.pct}%</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardContent className="p-4 flex flex-col gap-2">
              <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <Trophy size={13} /> Leaderboard
              </p>
              {leaderboard.map((row, i) => (
                <div key={row.participant_id} className="flex items-center gap-3 py-1">
                  <span className="w-5 text-xs font-bold text-muted-foreground">{i + 1}</span>
                  <RevealNamePopover runId={runId} participantId={row.participant_id} nickname={row.nickname} />
                  <span className="ml-auto text-sm font-semibold text-foreground">{row.score}</span>
                </div>
              ))}
              {leaderboard.length === 0 && <p className="text-sm text-muted-foreground">No scores yet.</p>}
            </CardContent>
          </Card>

          <button
            onClick={() => next.mutate()}
            disabled={next.isPending}
            className="h-10 px-6 bg-primary text-primary-foreground rounded-xl text-sm font-semibold hover:opacity-90 transition-colors disabled:opacity-50 w-fit"
          >
            {next.isPending ? "…" : run.current_question_position === run.total_questions ? "End game" : "Next question"}
          </button>
        </div>
      )}

      {phase === "ended" && (
        <Card>
          <CardContent className="p-6 text-center flex flex-col gap-2">
            <Trophy size={28} className="text-primary mx-auto" />
            <p className="text-sm font-semibold text-foreground">Game ended</p>
            <p className="text-xs text-muted-foreground">Final standings land on the podium screen (coming soon).</p>
          </CardContent>
        </Card>
      )}

      {restartConfirm && (
        <ConfirmDialog
          title="Restart this game"
          description="Every point awarded so far in this run is reversed for every student — the game starts fresh with the same question set. This can't be undone."
          confirmLabel="Restart"
          destructive
          pending={restart.isPending}
          onCancel={() => setRestartConfirm(false)}
          onConfirm={() => restart.mutate()}
        />
      )}
      {endConfirm && (
        <ConfirmDialog
          title="End this game"
          description="Students will see the game has ended. Points already awarded stay as they are."
          confirmLabel="End"
          destructive
          pending={end.isPending}
          onCancel={() => setEndConfirm(false)}
          onConfirm={() => end.mutate()}
        />
      )}
    </div>
  )
}

function RosterGrid({ roster }: { roster: { participant_id: string; nickname: string; has_answered_current: boolean }[] }) {
  if (roster.length === 0) return null
  return (
    <Card>
      <CardContent className="p-4">
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">
          <Timer size={13} /> Roster
        </p>
        <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 gap-2">
          {roster.map((p) => (
            <div
              key={p.participant_id}
              className={`flex flex-col items-center gap-1 p-2 rounded-lg border text-center transition-colors ${
                p.has_answered_current ? "border-emerald-500/40 bg-emerald-500/10" : "border-border"
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${p.has_answered_current ? "bg-emerald-500" : "bg-muted-foreground/30"}`} />
              <span className="text-[11px] text-foreground truncate w-full">{p.nickname}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
