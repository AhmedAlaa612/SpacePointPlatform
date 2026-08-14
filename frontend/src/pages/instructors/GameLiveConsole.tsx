import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useParams } from "@tanstack/react-router"
import { CheckCircle2, ChevronLeft, Download, Eye, EyeOff, RotateCcw, Square, Timer, Trophy, Users } from "lucide-react"
import {
  endRunApi, getCurrentQuestionApi, getLeaderboardApi, getRosterApi, getRunApi, nextQuestionApi,
  revealAllNamesApi, revealParticipantNameApi, revealRunApi, restartRunApi, startRunApi,
  type LeaderboardEntry, type QuestionResult, type RosterEntry,
} from "@/api/games_live"
import { useGameRunSocket } from "@/hooks/useGameRunSocket"
import { PageHeader, Spinner } from "@/pages/instructors/components/common"
import { ConfirmDialog } from "@/pages/admin/components/common"
import { Card, CardContent } from "@/components/ui/card"
import { useToast } from "@/components/ui/toast"
import { PodiumBoard } from "@/components/games/PodiumBoard"
import { AvatarBadge } from "@/components/games/AvatarBadge"
import { CountdownLeadIn } from "@/components/games/CountdownLeadIn"

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

/** Large projector-scale countdown ring (~240px) — this console is meant
 * to be read from across a physical classroom, per the Claude Design
 * spec's own framing ("1600×900 projector"). Timing logic here is
 * unchanged from the original small-badge version, verified live
 * (20s → 15s over 5 real seconds, no premature fire) — only the visual
 * changed, from a 64px bordered circle to an SVG progress ring. */
function Countdown({ seconds, keyProp, onExpire }: { seconds: number; keyProp: string; onExpire?: () => void }) {
  const [remaining, setRemaining] = useState(seconds)
  const firedRef = useRef(false)
  useEffect(() => {
    setRemaining(seconds)
    firedRef.current = false
    const start = Date.now()
    const id = setInterval(() => {
      const left = Math.max(0, seconds - Math.floor((Date.now() - start) / 1000))
      setRemaining(left)
      if (left === 0) {
        clearInterval(id)
        if (!firedRef.current) { firedRef.current = true; onExpire?.() }
      }
    }, 250)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keyProp, seconds])

  const pct = seconds > 0 ? remaining / seconds : 0
  const radius = 104
  const circumference = 2 * Math.PI * radius
  const urgent = remaining <= 5

  return (
    <div className="relative w-60 h-60 flex-none">
      <svg viewBox="0 0 240 240" className="w-full h-full -rotate-90">
        <circle cx="120" cy="120" r={radius} fill="none" strokeWidth="14" className="stroke-muted" />
        <circle
          cx="120" cy="120" r={radius} fill="none" strokeWidth="14" strokeLinecap="round"
          strokeDasharray={circumference} strokeDashoffset={circumference * (1 - pct)}
          className={`transition-[stroke-dashoffset] duration-200 ${urgent ? "stroke-destructive" : "stroke-primary"}`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-1">
        <span className={`font-display text-6xl font-extrabold leading-none ${urgent ? "text-destructive" : "text-foreground"}`}>
          {remaining}
        </span>
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">seconds left</span>
      </div>
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

function csvEscape(value: string): string {
  return /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value
}

function downloadCsv(filename: string, rows: string[][]) {
  const csv = rows.map((row) => row.map(csvEscape).join(",")).join("\n")
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url; a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/** The instructor's projected final screen (Live Games Phase 2C, 8-8b,
 * Frame 06) — built from the real final leaderboard, not mock data. The
 * global "Reveal names" toggle is distinct from the live per-row popover
 * (8-7): one flips every row at once for the class to see on the
 * projector. */
function FinalPodium({ runId }: { runId: string }) {
  const [namesRevealed, setNamesRevealed] = useState(false)
  const [names, setNames] = useState<Record<string, string>>({})

  const { data: board = [] } = useQuery<LeaderboardEntry[]>({
    queryKey: ["game-run-final-leaderboard", runId], queryFn: () => getLeaderboardApi(runId),
  })

  const revealAll = useMutation({
    mutationFn: () => revealAllNamesApi(runId),
    onSuccess: (rows) => {
      setNames(Object.fromEntries(rows.map((r) => [r.participant_id, r.real_name])))
      setNamesRevealed(true)
    },
  })

  /** The exported file is a staff record, not the projector.
   *
   * This used to write the real-name column only if "Reveal names" happened
   * to be toggled on, and blank it again the moment it was toggled off — so
   * whether the export was usable depended on the state of an unrelated
   * display control. The reveal toggle exists to protect nicknames *on the
   * screen the class is looking at*; the file an instructor downloads to
   * their own machine has no audience to protect it from, and a results
   * export that can't tell you who scored what is not a results export.
   */
  const exportResults = async () => {
    let resolved = names
    if (Object.keys(resolved).length === 0) {
      const rows = await revealAllNamesApi(runId)
      resolved = Object.fromEntries(rows.map((r) => [r.participant_id, r.real_name]))
      setNames(resolved)
    }
    downloadCsv(`live-quiz-results-${runId}.csv`, [
      ["Rank", "Nickname", "Real name", "Score"],
      ...board.map((row, i) => [
        String(i + 1), row.nickname, resolved[row.participant_id] ?? "", String(row.score),
      ]),
    ])
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-foreground">Final standings</p>
        <div className="flex items-center gap-2">
          <button
            onClick={() => namesRevealed ? setNamesRevealed(false) : revealAll.mutate()}
            disabled={revealAll.isPending}
            className="h-8 px-3 border border-border rounded-lg text-xs font-medium text-foreground hover:bg-muted transition-colors flex items-center gap-1.5 disabled:opacity-50"
          >
            {namesRevealed ? <EyeOff size={12} /> : <Eye size={12} />} {namesRevealed ? "Hide names" : "Reveal names"}
          </button>
          <button
            onClick={() => void exportResults()}
            className="h-8 px-3 border border-border rounded-lg text-xs font-medium text-foreground hover:bg-muted transition-colors flex items-center gap-1.5"
          >
            <Download size={12} /> Export results
          </button>
        </div>
      </div>
      <PodiumBoard entries={board} revealedNames={namesRevealed ? names : undefined} />
    </div>
  )
}

export default function GameLiveConsole() {
  const { runId } = useParams({ strict: false }) as { runId: string }
  const qc = useQueryClient()
  const toast = useToast()
  const [revealed, setRevealed] = useState(false)
  const [results, setResults] = useState<QuestionResult[] | null>(null)
  const [restartConfirm, setRestartConfirm] = useState(false)
  const [endConfirm, setEndConfirm] = useState(false)
  // Client-local 3-2-1 overlay — set the instant Start/Next is clicked
  // (own action, no need to wait on the WS round trip) and again from the
  // question_started broadcast (covers reconnects / any other path onto
  // this run), cleared by CountdownLeadIn's own onDone.
  const [leadIn, setLeadIn] = useState(false)

  const runKey = ["game-run", runId]
  const { data: run, isLoading } = useQuery({ queryKey: runKey, queryFn: () => getRunApi(runId) })

  const { data: question } = useQuery({
    queryKey: ["game-run-question", runId, run?.current_question_position],
    queryFn: () => getCurrentQuestionApi(runId),
    enabled: !!run && run.status === "live",
  })

  const rosterKey = ["game-run-roster", runId, run?.current_question_position]
  const { data: roster = [] } = useQuery({
    queryKey: rosterKey,
    queryFn: () => getRosterApi(runId),
    enabled: !!run && (run.status === "lobby" || run.status === "live"),
    // WS (participant_joined/updated/answered, below) is the primary path
    // now — this poll is just a cheap redundant safety net during "live".
    refetchInterval: run?.status === "live" && !revealed ? 3000 : false,
  })

  const { data: leaderboard = [] } = useQuery<LeaderboardEntry[]>({
    queryKey: ["game-run-leaderboard", runId],
    queryFn: () => getLeaderboardApi(runId),
    enabled: revealed,
  })

  const { connected } = useGameRunSocket(runId, (msg) => {
    if (msg.type === "question_started") {
      setRevealed(false)
      setResults(null)
      setLeadIn(true)
      qc.invalidateQueries({ queryKey: runKey })
    } else if (msg.type === "leaderboard_update") {
      setRevealed(true)
      qc.invalidateQueries({ queryKey: ["game-run-leaderboard", runId] })
    } else if (msg.type === "game_restarted") {
      toast.success("Game restarted")
      setRevealed(false)
      setResults(null)
      setLeadIn(true)
      qc.invalidateQueries({ queryKey: runKey })
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
    qc.invalidateQueries({ queryKey: ["game-run-leaderboard", runId] })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected])

  const start = useMutation({
    mutationFn: () => startRunApi(runId),
    onSuccess: () => { setRevealed(false); setLeadIn(true); qc.invalidateQueries({ queryKey: runKey }) },
  })
  const reveal = useMutation({
    mutationFn: () => revealRunApi(runId),
    onSuccess: (r) => { setResults(r); setRevealed(true) },
  })
  const next = useMutation({
    mutationFn: () => nextQuestionApi(runId),
    onSuccess: () => { setRevealed(false); setResults(null); setLeadIn(true); qc.invalidateQueries({ queryKey: runKey }) },
  })
  const restart = useMutation({
    mutationFn: () => restartRunApi(runId),
    // A restart resets this same run — same id, same code, same players —
    // so there is nowhere to navigate to. Clearing the reveal/results state
    // is what actually puts the console back in the lobby.
    onSuccess: () => {
      setRestartConfirm(false)
      setRevealed(false)
      setResults(null)
      setLeadIn(true)
      toast.success("Restarted — points from this run are reversed, everyone is back in the lobby")
      qc.invalidateQueries({ queryKey: runKey })
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
              <div className="flex flex-wrap justify-center gap-2 max-w-md">
                {roster.map((p) => (
                  <div key={p.participant_id} className="flex items-center gap-1.5 pl-1 pr-2.5 py-1 rounded-full bg-muted text-foreground">
                    <AvatarBadge avatar={p.avatar} nickname={p.nickname} size={32} />
                    <span className="text-xs">{p.nickname}</span>
                  </div>
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

      {phase === "question" && question && leadIn && (
        <Card>
          <CardContent>
            <CountdownLeadIn onDone={() => setLeadIn(false)} />
          </CardContent>
        </Card>
      )}

      {phase === "question" && question && !leadIn && (
        <div className="flex flex-col lg:flex-row gap-4 items-start">
          <Card className="flex-1 min-w-0 w-full">
            <CardContent className="p-6 sm:p-8 flex flex-col gap-6">
              <p className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Question {question.position} of {run.total_questions}
              </p>
              <p className="font-display text-2xl sm:text-3xl font-bold text-foreground leading-snug">{question.prompt}</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {question.options.map((o, i) => (
                  <div
                    key={i}
                    className={`flex items-center gap-3 min-h-14 px-4 py-3 rounded-xl border text-base ${
                      o.is_correct ? "border-emerald-500/40 bg-emerald-500/5 text-foreground" : "border-border text-foreground"
                    }`}
                  >
                    <span className="w-8 h-8 flex-none flex items-center justify-center rounded-lg border border-current text-sm font-bold">
                      {String.fromCharCode(65 + i)}
                    </span>
                    <span className="flex-1">{o.text}</span>
                    {o.is_correct && <CheckCircle2 size={16} className="text-emerald-500 shrink-0" />}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="w-full lg:w-[340px] flex-none">
            <CardContent className="p-6 flex flex-col items-center gap-6">
              <Countdown
                seconds={question.time_limit_seconds} keyProp={question.id}
                onExpire={() => { if (!reveal.isPending && !revealed) reveal.mutate() }}
              />
              <div className="w-full text-center">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Answered</p>
                <p className="font-display text-4xl font-extrabold text-foreground mt-0.5 leading-none">
                  {answeredCount}<span className="text-lg text-muted-foreground font-semibold"> / {roster.length}</span>
                </p>
              </div>
              <RosterGrid roster={roster} />
              <button
                onClick={() => reveal.mutate()}
                disabled={reveal.isPending}
                className="w-full h-11 bg-primary text-primary-foreground rounded-xl text-sm font-semibold hover:opacity-90 transition-colors disabled:opacity-50"
              >
                {reveal.isPending ? "Revealing…" : "Reveal answers"}
              </button>
            </CardContent>
          </Card>
        </div>
      )}

      {phase === "results" && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col lg:flex-row gap-4 items-start">
            {results && (
              <Card className="flex-1 min-w-0 w-full">
                <CardContent className="p-6 sm:p-8 flex flex-col gap-4">
                  <p className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-1">Results</p>
                  {results.map((r) => (
                    <div key={r.index} className="flex items-center gap-4">
                      <span className={`w-8 h-8 flex-none flex items-center justify-center rounded-lg border text-sm font-bold ${
                        r.is_correct ? "border-emerald-500 text-emerald-500" : "border-border text-muted-foreground"
                      }`}>
                        {String.fromCharCode(65 + r.index)}
                      </span>
                      <span className="text-base text-foreground w-48 truncate">{r.text}</span>
                      <div className="flex-1 h-3 rounded-full bg-muted overflow-hidden">
                        <div
                          className={`h-full ${r.is_correct ? "bg-emerald-500" : "bg-muted-foreground/40"}`}
                          style={{ width: `${r.pct}%` }}
                        />
                      </div>
                      <span className="text-sm text-muted-foreground w-20 text-right">{r.count} · {r.pct}%</span>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            <Card className="w-full lg:w-[380px] flex-none">
              <CardContent className="p-5 flex flex-col gap-2">
                <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <Trophy size={13} /> Leaderboard
                </p>
                {leaderboard.map((row, i) => (
                  <div key={row.participant_id} className="flex items-center gap-3 py-1.5">
                    <span className="w-5 text-xs font-bold text-muted-foreground">{i + 1}</span>
                    <AvatarBadge avatar={row.avatar} nickname={row.nickname} size={32} />
                    <RevealNamePopover runId={runId} participantId={row.participant_id} nickname={row.nickname} />
                    <span className="ml-auto text-sm font-semibold text-foreground">{row.score}</span>
                  </div>
                ))}
                {leaderboard.length === 0 && <p className="text-sm text-muted-foreground">No scores yet.</p>}
              </CardContent>
            </Card>
          </div>

          <button
            onClick={() => next.mutate()}
            disabled={next.isPending}
            className="h-11 px-6 bg-primary text-primary-foreground rounded-xl text-sm font-semibold hover:opacity-90 transition-colors disabled:opacity-50 w-fit"
          >
            {next.isPending ? "…" : run.current_question_position === run.total_questions ? "End game" : "Next question"}
          </button>
        </div>
      )}

      {phase === "ended" && <FinalPodium runId={runId} />}

      {restartConfirm && (
        <ConfirmDialog
          title="Restart this game"
          description="Everyone stays in the game with the same code — they go back to the lobby and play the same questions again from the start. Points already awarded in this run are reversed, so nobody keeps a score from the attempt you're replacing."
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

/** Embedded directly in the console's right-hand panel now (was its own
 * full-width card) — a fixed 4-column grid fits the panel's ~300px
 * content width without depending on page-wide breakpoints. */
function RosterGrid({ roster }: { roster: RosterEntry[] }) {
  if (roster.length === 0) return null
  return (
    <div className="w-full">
      <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">
        <Timer size={13} /> Roster · answered lights up
      </p>
      <div className="grid grid-cols-4 gap-2">
        {roster.map((p) => (
          <div
            key={p.participant_id}
            className={`flex flex-col items-center gap-1 p-2 rounded-lg border text-center transition-colors ${
              p.has_answered_current ? "border-emerald-500/40 bg-emerald-500/10" : "border-border"
            }`}
          >
            <AvatarBadge avatar={p.avatar} nickname={p.nickname} size={32} />
            <span className={`w-2 h-2 rounded-full ${p.has_answered_current ? "bg-emerald-500" : "bg-muted-foreground/30"}`} />
            <span className="text-[10px] text-foreground truncate w-full">{p.nickname}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
