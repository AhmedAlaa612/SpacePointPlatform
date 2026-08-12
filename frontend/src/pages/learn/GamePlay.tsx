import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "@tanstack/react-router"
import { CheckCircle2, Clock, EyeOff, Flame, Trophy, XCircle } from "lucide-react"
import {
  getMyScoreApi, getPlayQuestionApi, getPlayRunApi, getStudentLeaderboardApi,
  joinRunApi, submitAnswerApi, type AnswerAck, type StudentLeaderboardEntry,
} from "@/api/games_play"
import { useGameRunSocket } from "@/hooks/useGameRunSocket"
import { useAuth } from "@/context/AuthContext"

/** Student play screen (Live Games Phase 2C, 8-8) — Claude Design spec
 * Frames 03-05: lobby (waiting for start), answering (big mobile tap
 * targets + countdown), feedback (own correct/incorrect + score
 * breakdown + streak, shown the instant the student answers — this is
 * client-driven, not waiting on the instructor's Reveal), between-
 * questions (the leaderboard once the instructor does Reveal, own-score-
 * only once blackout starts, D10). `game_restarted` swaps the page onto
 * the new run's channel by updating `runId` state, same pattern as the
 * instructor console. */

type LocalPhase = "join" | "lobby" | "answering" | "feedback" | "between" | "ended"

function Countdown({ seconds, questionKey, onExpire }: { seconds: number; questionKey: string; onExpire: () => void }) {
  const [remaining, setRemaining] = useState(seconds)
  const firedRef = useRef(false)

  useEffect(() => {
    setRemaining(seconds)
    firedRef.current = false
    const start = Date.now()
    const id = setInterval(() => {
      const left = Math.max(0, seconds - Math.floor((Date.now() - start) / 1000))
      setRemaining(left)
      if (left === 0 && !firedRef.current) {
        firedRef.current = true
        onExpire()
        clearInterval(id)
      }
    }, 250)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [questionKey, seconds])

  return (
    <div className={`text-2xl font-display font-extrabold ${remaining <= 5 ? "text-destructive" : "text-foreground"}`}>
      {remaining}s
    </div>
  )
}

export default function GamePlay() {
  const { runId } = useParams({ strict: false }) as { runId: string }
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { currentUser } = useAuth()

  const [avatar] = useState<string | null>(null)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const [ack, setAck] = useState<AnswerAck | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [answeredPosition, setAnsweredPosition] = useState<number | null>(null)
  const questionStartedAtRef = useRef<number>(Date.now())

  const runKey = ["play-run", runId]
  const { data: run } = useQuery({ queryKey: runKey, queryFn: () => getPlayRunApi(runId), refetchInterval: 4000 })

  const myScore = useQuery({
    queryKey: ["play-my-score", runId], queryFn: () => getMyScoreApi(runId),
    retry: false, enabled: !!runId,
  })
  const hasJoined = myScore.isSuccess

  const { data: question } = useQuery({
    queryKey: ["play-question", runId, run?.current_question_position],
    queryFn: () => getPlayQuestionApi(runId),
    enabled: hasJoined && run?.status === "live",
  })

  const { data: leaderboard = [] } = useQuery<StudentLeaderboardEntry[]>({
    queryKey: ["play-leaderboard", runId, run?.current_question_position],
    queryFn: () => getStudentLeaderboardApi(runId),
    enabled: hasJoined && revealed,
  })

  useGameRunSocket(hasJoined ? runId : null, (msg) => {
    if (msg.type === "question_started") {
      setSelectedIndex(null); setAck(null); setRevealed(false); setAnsweredPosition(null)
      questionStartedAtRef.current = Date.now()
      qc.invalidateQueries({ queryKey: runKey })
    } else if (msg.type === "leaderboard_update") {
      setRevealed(true)
      qc.invalidateQueries({ queryKey: ["play-leaderboard", runId] })
      qc.invalidateQueries({ queryKey: ["play-my-score", runId] })
    } else if (msg.type === "game_restarted") {
      void navigate({ to: "/learn/games/$runId", params: { runId: msg.payload.new_run_id } })
    } else if (msg.type === "game_ended") {
      qc.invalidateQueries({ queryKey: runKey })
    }
  })

  const join = useMutation({
    mutationFn: () => joinRunApi(runId, avatar),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["play-my-score", runId] }) },
  })

  const answer = useMutation({
    mutationFn: (index: number | null) => {
      const elapsed = (Date.now() - questionStartedAtRef.current) / 1000
      return submitAnswerApi(runId, index, elapsed)
    },
    onSuccess: (result, index) => {
      setAck(result); setSelectedIndex(index); setAnsweredPosition(run?.current_question_position ?? null)
      qc.invalidateQueries({ queryKey: ["play-my-score", runId] })
    },
  })

  if (!run) return <div className="p-8 text-center text-sm text-muted-foreground">Loading…</div>

  const phase: LocalPhase =
    run.status === "ended" ? "ended"
    : !hasJoined ? "join"
    : run.status === "lobby" ? "lobby"
    : answeredPosition === run.current_question_position ? (revealed ? "between" : "feedback")
    : "answering"

  return (
    <div className="mx-auto max-w-[520px] px-5 py-6 sm:py-10 flex flex-col gap-6 min-h-[70vh]">
      {phase === "join" && (
        <div className="flex flex-col items-center gap-5 text-center pt-10">
          <Trophy className="size-10 text-primary" />
          <div>
            <h1 className="font-display text-2xl font-extrabold">Ready to play?</h1>
            <p className="text-sm text-muted-foreground mt-1">
              You'll play as <span className="font-semibold text-foreground">{currentUser?.nickname ?? currentUser?.full_name}</span>
            </p>
          </div>
          <button
            onClick={() => join.mutate()}
            disabled={join.isPending}
            className="h-12 px-8 bg-primary text-primary-foreground rounded-2xl text-base font-bold hover:opacity-90 transition-colors disabled:opacity-50"
          >
            {join.isPending ? "Joining…" : "Join game"}
          </button>
        </div>
      )}

      {phase === "lobby" && (
        <div className="flex flex-col items-center gap-4 text-center pt-16">
          <div className="size-4 rounded-full bg-primary animate-pulse" />
          <h1 className="font-display text-xl font-extrabold">You're in!</h1>
          <p className="text-sm text-muted-foreground">Waiting for your instructor to start…</p>
        </div>
      )}

      {phase === "answering" && question && (
        <div className="flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Question {question.position} of {run.total_questions}
            </span>
            <Countdown
              seconds={question.time_limit_seconds} questionKey={question.id}
              onExpire={() => { if (!answer.isPending && selectedIndex === null) answer.mutate(null) }}
            />
          </div>
          <h1 className="font-display text-xl font-bold leading-snug">{question.prompt}</h1>
          <div className="grid grid-cols-1 gap-3">
            {question.options.map((o, i) => (
              <button
                key={i}
                onClick={() => !answer.isPending && answer.mutate(i)}
                disabled={answer.isPending}
                className="h-16 px-5 rounded-2xl border-2 border-border bg-card text-left text-base font-semibold text-foreground hover:border-primary/50 active:scale-[0.98] transition-all disabled:opacity-60 flex items-center gap-3"
              >
                <span className="w-7 h-7 flex-none flex items-center justify-center rounded-lg border-2 border-current text-xs">
                  {String.fromCharCode(65 + i)}
                </span>
                {o.text}
              </button>
            ))}
          </div>
        </div>
      )}

      {phase === "feedback" && ack && (
        <div className="flex flex-col items-center gap-5 text-center pt-8">
          {ack.is_correct ? (
            <CheckCircle2 className="size-14 text-emerald-500" />
          ) : (
            <XCircle className="size-14 text-destructive" />
          )}
          <h1 className="font-display text-2xl font-extrabold">{ack.is_correct ? "Correct!" : "Not quite"}</h1>
          {ack.is_correct && (
            <div className="flex flex-col gap-1.5 w-full max-w-xs">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Base (correct)</span>
                <span className="font-semibold text-foreground">+{ack.base_points}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Speed bonus</span>
                <span className="font-semibold text-foreground">+{ack.speed_bonus}</span>
              </div>
              <div className="flex justify-between text-base border-t border-border pt-1.5 mt-1">
                <span className="font-semibold">Total</span>
                <span className="font-display font-extrabold text-primary">+{ack.points_awarded}</span>
              </div>
            </div>
          )}
          {ack.streak >= 2 && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 text-sm font-semibold">
              <Flame size={14} /> {ack.streak} in a row
            </span>
          )}
          <p className="text-xs text-muted-foreground flex items-center gap-1.5"><Clock size={12} /> Waiting for the rest of the class…</p>
        </div>
      )}

      {phase === "between" && (
        <div className="flex flex-col gap-4">
          {run.blackout_active ? (
            <div className="flex flex-col items-center gap-3 text-center pt-8">
              <EyeOff className="size-10 text-amber-500" />
              <h1 className="font-display text-xl font-extrabold">Blackout round</h1>
              <p className="text-sm text-muted-foreground">Leaderboard's hidden till the end — here's your score.</p>
              <p className="font-display text-4xl font-extrabold text-primary mt-2">{myScore.data?.score ?? 0}</p>
            </div>
          ) : (
            <>
              <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <Trophy size={13} /> Leaderboard
              </p>
              <div className="flex flex-col gap-2">
                {leaderboard.map((row, i) => (
                  <div
                    key={row.participant_id}
                    className={`flex items-center gap-3 rounded-xl border p-3 ${row.is_me ? "border-primary/40 bg-primary/5" : "border-border bg-card"}`}
                  >
                    <span className="w-6 text-center text-sm font-bold text-muted-foreground">{i + 1}</span>
                    <span className="flex-1 text-sm font-medium truncate">
                      {row.nickname}{row.is_me && <span className="ml-1.5 font-normal text-muted-foreground">(you)</span>}
                    </span>
                    <span className="font-display font-bold text-sm">{row.score}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {phase === "ended" && (
        <div className="flex flex-col items-center gap-4 text-center pt-16">
          <Trophy className="size-12 text-primary" />
          <h1 className="font-display text-2xl font-extrabold">Game over!</h1>
          <p className="text-sm text-muted-foreground">Final score: <span className="font-semibold text-foreground">{myScore.data?.score ?? 0}</span></p>
          <p className="text-xs text-muted-foreground">Podium screen coming soon.</p>
        </div>
      )}
    </div>
  )
}
