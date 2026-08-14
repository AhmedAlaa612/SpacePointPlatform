import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useParams } from "@tanstack/react-router"
import { CheckCircle2, Clock, EyeOff, Flame, Trophy, Users, XCircle } from "lucide-react"
import {
  getMyScoreApi, getPlayQuestionApi, getPlayRosterApi, getPlayRunApi, getStudentLeaderboardApi,
  joinRunApi, submitAnswerApi, type AnswerAck, type StudentLeaderboardEntry,
} from "@/api/games_play"
import type { QuestionResult, RosterEntry } from "@/api/games_live"
import { useGameRunSocket } from "@/hooks/useGameRunSocket"
import { useAuth } from "@/context/AuthContext"
import { PodiumBoard } from "@/components/games/PodiumBoard"
import { AvatarBadge } from "@/components/games/AvatarBadge"
import { AvatarNicknamePicker } from "@/components/games/AvatarNicknamePicker"
import { CountdownLeadIn } from "@/components/games/CountdownLeadIn"

/** Student play screen (Live Games Phase 2C, 8-8; world-class rework).
 * Phases: join → lobby (named roster + avatar/nickname picker, D18) →
 * countdown (shared 3-2-1 lead-in, synced off `question_started`) →
 * question (one persistent question+options view — unanswered,
 * locked-in-waiting, then revealed — replacing the old separate
 * answering/feedback/between screens) → ended. Correctness only renders
 * once `revealed` flips true (the instructor's Reveal broadcast, or their
 * own timeout auto-triggering it), never the instant a student personally
 * submits — the whole room finds out together. `game_restarted` swaps the
 * page onto the new run's channel by updating `runId` state. */

type LocalPhase = "join" | "lobby" | "countdown" | "question" | "ended"

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

/** The student's own final screen (8-8b, D19) — same podium, scaled to
 * fit a phone, own placement highlighted. Blackout auto-clears once a
 * run ends (`is_blackout_active` requires a live current question), so
 * the same student leaderboard endpoint that was redacted mid-blackout
 * now returns everyone — the podium moment doubles as the reveal. */
function FinalStandings({ runId }: { runId: string }) {
  const { data: board = [] } = useQuery<StudentLeaderboardEntry[]>({
    queryKey: ["play-final-leaderboard", runId], queryFn: () => getStudentLeaderboardApi(runId),
  })
  const own = board.find((e) => e.is_me)

  return (
    <div className="flex flex-col items-center gap-6 pt-4">
      <div className="text-center">
        <Trophy className="size-10 text-primary mx-auto" />
        <h1 className="font-display text-2xl font-extrabold mt-2">Game over!</h1>
      </div>
      <div className="w-full">
        <PodiumBoard entries={board} ownParticipantId={own?.participant_id} />
      </div>
    </div>
  )
}

export default function GamePlay() {
  const { runId } = useParams({ strict: false }) as { runId: string }
  const qc = useQueryClient()
  const { currentUser } = useAuth()

  const [avatar] = useState<string | null>(null)
  // My own in-game identity (nickname/avatar) — distinct from the profile
  // nickname once the picker's been used, D18. Seeded by the join
  // response and re-synced by an idempotent join call on page load (see
  // the effect below), since a mid-lobby refresh never re-fires the
  // "Join game" button's own click handler.
  const [me, setMe] = useState<{ nickname: string; avatar: string | null } | null>(null)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const [ack, setAck] = useState<AnswerAck | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [revealResults, setRevealResults] = useState<QuestionResult[] | null>(null)
  const [answeredPosition, setAnsweredPosition] = useState<number | null>(null)
  const [leadIn, setLeadIn] = useState(false)
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

  const rosterKey = ["play-roster", runId]
  const { data: roster = [] } = useQuery({
    queryKey: rosterKey,
    queryFn: () => getPlayRosterApi(runId),
    enabled: hasJoined && (run?.status === "lobby" || run?.status === "live"),
  })

  const { data: leaderboard = [] } = useQuery<StudentLeaderboardEntry[]>({
    queryKey: ["play-leaderboard", runId, run?.current_question_position],
    queryFn: () => getStudentLeaderboardApi(runId),
    enabled: hasJoined && revealed,
  })

  const { connected } = useGameRunSocket(hasJoined ? runId : null, (msg) => {
    if (msg.type === "question_started") {
      setSelectedIndex(null); setAck(null); setRevealed(false); setRevealResults(null); setAnsweredPosition(null)
      setLeadIn(true)
      qc.invalidateQueries({ queryKey: runKey })
    } else if (msg.type === "leaderboard_update") {
      setRevealed(true)
      setRevealResults(msg.payload.results ?? null)
      qc.invalidateQueries({ queryKey: ["play-leaderboard", runId] })
      qc.invalidateQueries({ queryKey: ["play-my-score", runId] })
    } else if (msg.type === "game_restarted") {
      // Same run, reset to its lobby — the student stays put rather than
      // being bounced back to the join-code screen, which is what made the
      // old new-run restart feel like being kicked out.
      setRevealed(false)
      setRevealResults(null)
      qc.invalidateQueries({ queryKey: runKey })
      qc.invalidateQueries({ queryKey: ["play-my-score", runId] })
      qc.invalidateQueries({ queryKey: ["play-leaderboard", runId] })
    } else if (msg.type === "game_ended") {
      qc.invalidateQueries({ queryKey: runKey })
    } else if (msg.type === "participant_joined") {
      qc.setQueryData<RosterEntry[]>(rosterKey, (old = []) =>
        old.some((p) => p.participant_id === msg.payload.participant_id)
          ? old
          : [...old, {
              participant_id: msg.payload.participant_id, nickname: msg.payload.nickname,
              avatar: msg.payload.avatar, has_answered_current: false,
            }],
      )
    } else if (msg.type === "participant_updated") {
      qc.setQueryData<RosterEntry[]>(rosterKey, (old = []) =>
        old.map((p) => p.participant_id === msg.payload.participant_id
          ? { ...p, nickname: msg.payload.nickname, avatar: msg.payload.avatar } : p),
      )
    } else if (msg.type === "participant_answered") {
      qc.setQueryData<RosterEntry[]>(rosterKey, (old = []) =>
        old.map((p) => p.participant_id === msg.payload.participant_id ? { ...p, has_answered_current: true } : p),
      )
    }
  })

  // Redis pub/sub has no replay — a reconnect after a drop needs an
  // explicit re-sync, not just a green "connected" dot.
  useEffect(() => {
    if (!connected) return
    qc.invalidateQueries({ queryKey: runKey })
    qc.invalidateQueries({ queryKey: rosterKey })
    qc.invalidateQueries({ queryKey: ["play-leaderboard", runId] })
    qc.invalidateQueries({ queryKey: ["play-my-score", runId] })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected])

  const join = useMutation({
    mutationFn: () => joinRunApi(runId, avatar),
    onSuccess: (p) => {
      setMe({ nickname: p.nickname, avatar: p.avatar })
      qc.invalidateQueries({ queryKey: ["play-my-score", runId] })
    },
  })

  // join_run is idempotent — safe to call again on a mid-lobby page
  // refresh, purely to re-populate `me` (the join button's own onSuccess
  // only fires once, the first time).
  useEffect(() => {
    if (hasJoined && !me && !join.isPending) join.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasJoined, me])

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
    : leadIn ? "countdown"
    : "question"

  const locked = !!question && answeredPosition === question.position
  const answeredCount = roster.filter((r) => r.has_answered_current).length
  const myNickname = me?.nickname ?? currentUser?.nickname ?? currentUser?.full_name ?? "You"

  return (
    <div className="mx-auto max-w-[520px] px-5 py-6 sm:py-10 flex flex-col gap-6 min-h-[70vh]">
      {phase === "join" && (
        <div className="flex flex-col items-center gap-5 text-center pt-10">
          <Trophy className="size-10 text-primary" />
          <div>
            <h1 className="font-display text-2xl font-extrabold">Ready to play?</h1>
            <p className="text-sm text-muted-foreground mt-1">
              You'll play as <span className="font-semibold text-foreground">{myNickname}</span>
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
        <div className="flex flex-col items-center gap-6 pt-4">
          <div className="text-center">
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">You're in · waiting room</p>
            <h1 className="font-display text-xl font-extrabold mt-1">
              {run.total_questions} question{run.total_questions === 1 ? "" : "s"}
            </h1>
          </div>

          <AvatarNicknamePicker
            runId={runId}
            nickname={myNickname}
            avatar={me?.avatar ?? null}
            onUpdated={setMe}
          />

          <div className="w-full flex flex-col gap-2">
            <p className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              <Users size={13} /> {roster.length} {roster.length === 1 ? "explorer" : "explorers"} in the room
            </p>
            <div className="flex flex-wrap gap-2">
              {roster.map((p) => (
                <div key={p.participant_id} className="flex items-center gap-1.5 pl-1 pr-2.5 py-1 rounded-full bg-muted">
                  <AvatarBadge avatar={p.avatar} nickname={p.nickname} size={32} />
                  <span className="text-xs text-foreground">{p.nickname}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="w-full mt-auto flex items-center gap-2 px-4 py-3 rounded-2xl bg-card border border-border">
            <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
            <span className="text-xs text-muted-foreground">Starts when the instructor says go</span>
          </div>
        </div>
      )}

      {phase === "countdown" && (
        <CountdownLeadIn onDone={() => { questionStartedAtRef.current = Date.now(); setLeadIn(false) }} />
      )}

      {phase === "question" && question && (
        <div className="flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Question {question.position} of {run.total_questions}
            </span>
            {!locked && (
              <Countdown
                seconds={question.time_limit_seconds} questionKey={question.id}
                onExpire={() => { if (!answer.isPending && selectedIndex === null) answer.mutate(null) }}
              />
            )}
          </div>
          <h1 className="font-display text-xl font-bold leading-snug">{question.prompt}</h1>
          <div className="grid grid-cols-1 gap-3">
            {question.options.map((o, i) => {
              const result = revealResults?.[i]
              const isMine = selectedIndex === i
              let colorClass = "border-border bg-card"
              if (revealed && result) {
                if (result.is_correct) colorClass = "border-emerald-500 bg-emerald-500/10"
                else if (isMine) colorClass = "border-destructive bg-destructive/10"
              } else if (isMine) {
                colorClass = "border-primary bg-primary/10"
              }
              return (
                <button
                  key={i}
                  onClick={() => !locked && !answer.isPending && answer.mutate(i)}
                  disabled={locked || answer.isPending}
                  className={`h-16 px-5 rounded-2xl border-2 text-left text-base font-semibold text-foreground transition-all flex items-center gap-3 ${colorClass} ${
                    !locked ? "hover:border-primary/50 active:scale-[0.98] disabled:opacity-60" : ""
                  }`}
                >
                  <span className="w-7 h-7 flex-none flex items-center justify-center rounded-lg border-2 border-current text-xs">
                    {String.fromCharCode(65 + i)}
                  </span>
                  <span className="flex-1">{o.text}</span>
                  {revealed && result?.is_correct && <CheckCircle2 size={18} className="text-emerald-500 shrink-0" />}
                  {revealed && isMine && result && !result.is_correct && <XCircle size={18} className="text-destructive shrink-0" />}
                </button>
              )
            })}
          </div>

          {locked && !revealed && (
            <p className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Clock size={12} /> {selectedIndex === null ? "Time's up" : "Locked in"} — waiting for the rest of the class
              {roster.length > 0 && ` · ${answeredCount} of ${roster.length} answered`}
            </p>
          )}

          {revealed && (
            <>
              {ack && (
                <div className={`flex flex-col gap-2 p-4 rounded-2xl border ${ack.is_correct ? "border-emerald-500/30 bg-emerald-500/5" : "border-border bg-card"}`}>
                  <div className="flex items-center justify-between">
                    <span className={`text-sm font-bold ${ack.is_correct ? "text-emerald-500" : "text-muted-foreground"}`}>
                      {ack.is_correct ? "Correct!" : selectedIndex === null ? "No answer submitted" : "Not quite"}
                    </span>
                    <span className="font-display text-xl font-extrabold text-primary">+{ack.points_awarded}</span>
                  </div>
                  {ack.is_correct && (
                    <div className="flex flex-col gap-1 text-xs text-muted-foreground">
                      <div className="flex justify-between"><span>Base (correct)</span><span className="text-foreground font-medium">+{ack.base_points}</span></div>
                      <div className="flex justify-between"><span>Speed bonus</span><span className="text-foreground font-medium">+{ack.speed_bonus}</span></div>
                    </div>
                  )}
                  {ack.streak >= 2 && (
                    <span className="inline-flex items-center gap-1.5 w-fit px-3 py-1 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 text-xs font-semibold">
                      <Flame size={12} /> {ack.streak} in a row
                    </span>
                  )}
                </div>
              )}

              {run.blackout_active ? (
                <div className="flex flex-col items-center gap-2 text-center py-6">
                  <EyeOff className="size-8 text-amber-500" />
                  <p className="text-sm font-semibold">Blackout round</p>
                  <p className="text-xs text-muted-foreground">Leaderboard's hidden till the end — here's your score.</p>
                  <p className="font-display text-3xl font-extrabold text-primary mt-1">{myScore.data?.score ?? 0}</p>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <Trophy size={13} /> Leaderboard
                  </p>
                  {leaderboard.map((row, i) => (
                    <div
                      key={row.participant_id}
                      className={`flex items-center gap-3 rounded-xl border p-3 ${row.is_me ? "border-primary/40 bg-primary/5" : "border-border bg-card"}`}
                    >
                      <span className="w-6 text-center text-sm font-bold text-muted-foreground">{i + 1}</span>
                      <AvatarBadge avatar={row.avatar} nickname={row.nickname} size={32} />
                      <span className="flex-1 text-sm font-medium truncate">
                        {row.nickname}{row.is_me && <span className="ml-1.5 font-normal text-muted-foreground">(you)</span>}
                      </span>
                      <span className="font-display font-bold text-sm">{row.score}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {phase === "ended" && <FinalStandings runId={runId} />}
    </div>
  )
}
