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
    <div className={`flex items-center gap-2 font-['Outfit'] text-3xl sm:text-4xl font-black tracking-tight ${remaining <= 5 ? "text-destructive animate-pulse" : "text-foreground"}`}>
      <Clock className={`size-6 sm:size-7 ${remaining <= 5 ? "text-destructive" : "text-lms-cta dark:text-lms-accent"}`} />
      <span>{remaining}s</span>
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
      <div className="text-center flex flex-col items-center gap-2">
        {/* Floating trophy icon with no container wrapper */}
        <Trophy className="size-16 text-lms-cta dark:text-lms-accent stroke-[1.75]" />
        <h1 className="font-['Outfit'] text-3xl sm:text-4xl font-extrabold tracking-tight text-foreground">
          Game over!
        </h1>
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
    <div className="mx-auto max-w-3xl lg:max-w-4xl px-5 py-6 sm:py-10 flex flex-col gap-6 min-h-[70vh]">
      {phase === "join" && (
        <div className="flex flex-col items-center gap-5 text-center pt-10">
          {/* Floating trophy icon with no container wrapper */}
          <Trophy className="size-16 text-lms-cta dark:text-lms-accent stroke-[1.75]" />
          <div>
            <h1 className="font-['Outfit'] text-3xl sm:text-4xl font-extrabold tracking-tight text-foreground">
              Ready to play?
            </h1>
            <p className="text-base text-muted-foreground mt-1.5">
              You'll play as <span className="font-bold text-foreground">{myNickname}</span>
            </p>
          </div>
          <button
            type="button"
            onClick={() => join.mutate()}
            disabled={join.isPending}
            className="lms-btn-primary h-12 px-8 rounded-2xl text-base font-bold cursor-pointer disabled:opacity-50"
          >
            {join.isPending ? "Joining…" : "Join game"}
          </button>
        </div>
      )}

      {phase === "lobby" && (
        <div className="flex flex-col items-center gap-6 pt-4">
          <div className="text-center">
            <p className="text-xs font-bold text-lms-cta dark:text-lms-accent uppercase tracking-wider">
              You're in · waiting room
            </p>
            <h1 className="font-['Outfit'] text-2xl font-extrabold mt-1 text-foreground">
              {run.total_questions} question{run.total_questions === 1 ? "" : "s"}
            </h1>
          </div>

          <AvatarNicknamePicker
            runId={runId}
            nickname={myNickname}
            avatar={me?.avatar ?? null}
            onUpdated={setMe}
          />

          <div className="w-full flex flex-col gap-2.5">
            <p className="flex items-center gap-1.5 text-xs font-bold text-muted-foreground uppercase tracking-wider">
              <Users size={14} /> {roster.length} {roster.length === 1 ? "explorer" : "explorers"} in the room
            </p>
            <div className="flex flex-wrap gap-2">
              {roster.map((p) => (
                <div key={p.participant_id} className="flex items-center gap-2 pl-1.5 pr-3 py-1 rounded-full bg-muted/50 dark:bg-[#1a0f26] border border-border/80 dark:border-lms-accent-border/30">
                  <AvatarBadge avatar={p.avatar} nickname={p.nickname} size={32} />
                  <span className="text-xs font-semibold text-foreground">{p.nickname}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="w-full mt-auto flex items-center gap-2.5 px-4 py-3 rounded-2xl lms-card border border-border/80 dark:border-lms-accent-border/30 bg-muted/20 dark:bg-[#0d0915]">
            <span className="w-2.5 h-2.5 rounded-full bg-lms-cta dark:bg-lms-accent animate-pulse" />
            <span className="text-xs font-medium text-muted-foreground">Starts when the instructor says go</span>
          </div>
        </div>
      )}

      {phase === "countdown" && (
        <CountdownLeadIn onDone={() => { questionStartedAtRef.current = Date.now(); setLeadIn(false) }} />
      )}

      {phase === "question" && question && (
        <div className="flex flex-col gap-6">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                Question {question.position} of {run.total_questions}
              </span>
              <div className="flex items-center gap-1.5">
                {Array.from({ length: run.total_questions }).map((_, i) => {
                  const qPos = i + 1
                  const isCurrent = qPos === question.position
                  const isPast = qPos < question.position
                  return (
                    <div
                      key={i}
                      className={`h-2.5 rounded-full transition-all duration-300 ${
                        isCurrent
                          ? "w-7 bg-lms-cta dark:bg-lms-accent ring-2 ring-lms-accent-glow"
                          : isPast
                          ? "w-2.5 bg-lms-cta/60 dark:bg-lms-accent/60"
                          : "w-2.5 bg-muted-foreground/25 dark:bg-muted-foreground/20"
                      }`}
                    />
                  )
                })}
              </div>
            </div>
            {!locked && (
              <Countdown
                seconds={question.time_limit_seconds} questionKey={question.id}
                onExpire={() => { if (!answer.isPending && selectedIndex === null) answer.mutate(null) }}
              />
            )}
          </div>
          <h1 className="font-['Outfit'] text-2xl sm:text-3xl lg:text-4xl font-extrabold leading-tight tracking-normal text-foreground">
            {question.prompt}
          </h1>
          <div className="grid grid-cols-1 gap-3">
            {question.options.map((o, i) => {
              const result = revealResults?.[i]
              const isMine = selectedIndex === i
              let colorClass = "border-border/80 dark:border-lms-accent-border/30 bg-muted/10 dark:bg-[#0d0915]/60 hover:border-lms-cta dark:hover:border-lms-accent"
              let badgeClass = "border-border/80 dark:border-lms-accent-border/30 bg-muted/30 dark:bg-[#1a0f26] text-muted-foreground"

              if (revealed && result) {
                if (result.is_correct) {
                  colorClass = "border-emerald-500/60 bg-emerald-500/15"
                  badgeClass = "border-emerald-500/50 bg-emerald-500 text-white dark:text-black font-bold"
                } else if (isMine) {
                  colorClass = "border-destructive/60 bg-destructive/15"
                  badgeClass = "border-destructive/50 bg-destructive text-white font-bold"
                }
              } else if (isMine) {
                colorClass = "border-lms-cta dark:border-lms-accent bg-lms-cta-light"
                badgeClass = "border-lms-cta dark:border-lms-accent bg-lms-cta dark:bg-lms-accent text-white dark:text-black font-bold"
              }

              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => !locked && !answer.isPending && answer.mutate(i)}
                  disabled={locked || answer.isPending}
                  className={`min-h-[64px] py-3.5 px-5 rounded-2xl border-2 text-left text-base font-semibold text-foreground transition-all flex items-center gap-4 cursor-pointer ${colorClass} ${
                    !locked ? "active:scale-[0.98] disabled:opacity-60" : ""
                  }`}
                >
                  <span className={`w-8 h-8 flex-none flex items-center justify-center rounded-xl border-2 text-sm font-extrabold transition-colors ${badgeClass}`}>
                    {String.fromCharCode(65 + i)}
                  </span>
                  <span className="flex-1 text-base leading-snug">{o.text}</span>
                  {revealed && result?.is_correct && <CheckCircle2 size={18} className="text-emerald-500 shrink-0" />}
                  {revealed && isMine && result && !result.is_correct && <XCircle size={18} className="text-destructive shrink-0" />}
                </button>
              )
            })}
          </div>

          {locked && !revealed && (
            <p className="text-xs text-muted-foreground flex items-center gap-1.5 font-medium">
              <Clock size={12} /> {selectedIndex === null ? "Time's up" : "Locked in"} — waiting for the rest of the class
              {roster.length > 0 && ` · ${answeredCount} of ${roster.length} answered`}
            </p>
          )}

          {revealed && (
            <>
              {ack && (
                <div className={`flex flex-col gap-2 p-5 rounded-2xl border-2 shadow-lg shadow-black/10 ${ack.is_correct ? "border-emerald-500/40 bg-emerald-500/10" : "border-border/80 dark:border-lms-accent-border/30 bg-muted/20 dark:bg-[#0d0915]"}`}>
                  <div className="flex items-center justify-between">
                    <span className={`text-base font-bold ${ack.is_correct ? "text-emerald-500 dark:text-emerald-400" : "text-muted-foreground"}`}>
                      {ack.is_correct ? "Correct!" : selectedIndex === null ? "No answer submitted" : "Not quite"}
                    </span>
                    <span className="font-['Outfit'] text-2xl font-black text-lms-cta dark:text-lms-accent">+{ack.points_awarded}</span>
                  </div>
                  {ack.is_correct && (
                    <div className="flex flex-col gap-1 text-xs text-muted-foreground">
                      <div className="flex justify-between"><span>Base (correct)</span><span className="text-foreground font-medium">+{ack.base_points}</span></div>
                      <div className="flex justify-between"><span>Speed bonus</span><span className="text-foreground font-medium">+{ack.speed_bonus}</span></div>
                    </div>
                  )}
                  {ack.streak >= 2 && (
                    <span className="inline-flex items-center gap-1.5 w-fit px-3 py-1 rounded-full bg-amber-500/15 text-amber-500 border border-amber-500/30 text-xs font-bold">
                      <Flame size={12} /> {ack.streak} in a row
                    </span>
                  )}
                </div>
              )}

              {run.blackout_active ? (
                <div className="flex flex-col items-center gap-2 text-center py-6">
                  <EyeOff className="size-10 text-amber-500 stroke-[1.75]" />
                  <p className="text-base font-bold text-foreground">Blackout round</p>
                  <p className="text-xs text-muted-foreground">Leaderboard's hidden till the end — here's your score.</p>
                  <p className="font-['Outfit'] text-4xl font-black text-lms-cta dark:text-lms-accent mt-1">{myScore.data?.score ?? 0}</p>
                </div>
              ) : (
                <div className="flex flex-col gap-2.5">
                  <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    <Trophy size={14} className="text-lms-cta dark:text-lms-accent" /> Leaderboard
                  </p>
                  {leaderboard.map((row, i) => (
                    <div
                      key={row.participant_id}
                      className={`flex items-center gap-3.5 rounded-2xl border p-3.5 transition-all ${
                        row.is_me
                          ? "border-lms-cta dark:border-lms-accent bg-lms-cta-light"
                          : "border-border/80 dark:border-lms-accent-border/30 bg-muted/10 dark:bg-[#0d0915]"
                      }`}
                    >
                      <span className="w-6 text-center text-sm font-mono font-bold text-muted-foreground">{i + 1}</span>
                      <AvatarBadge avatar={row.avatar} nickname={row.nickname} size={34} />
                      <span className="flex-1 text-sm font-semibold truncate text-foreground">
                        {row.nickname}{row.is_me && <span className="ml-1.5 font-bold text-lms-cta dark:text-lms-accent">(you)</span>}
                      </span>
                      <span className="font-['Outfit'] font-black text-base text-foreground">{row.score}</span>
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
