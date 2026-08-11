import { useEffect, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useParams, useNavigate } from "@tanstack/react-router"
import {
  ArrowLeft, ArrowUp, ArrowDown, Plus, Pencil, Copy, Trash2, Sparkle, Timer, CheckCircle2, SlidersHorizontal,
} from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Modal, Field, ModalActions, ConfirmDialog } from "@/pages/admin/components/common"
import {
  getGameApi, updateGameApi, createGameQuestionApi, updateGameQuestionApi, duplicateGameQuestionApi,
  deleteGameQuestionApi, reorderGameQuestionsApi,
  type GameDetail, type GameQuestion, type GameQuestionOption, type PointsMode,
} from "@/api/games_admin"

function QuestionEditor({
  gameId, question, onClose,
}: { gameId: string; question: GameQuestion | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [prompt, setPrompt] = useState(question?.prompt ?? "")
  const [options, setOptions] = useState<GameQuestionOption[]>(
    question?.options ?? [{ text: "", is_correct: true }, { text: "", is_correct: false }],
  )
  const [timeLimit, setTimeLimit] = useState(question?.time_limit_seconds?.toString() ?? "")
  const [pointsMode, setPointsMode] = useState<PointsMode>(question?.points_mode ?? "normal")
  const [error, setError] = useState("")

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["games-admin", gameId] })

  const saveMutation = useMutation({
    mutationFn: () => {
      const body = {
        prompt: prompt.trim(),
        options,
        time_limit_seconds: timeLimit.trim() ? Number(timeLimit) : null,
        points_mode: pointsMode,
      }
      return question ? updateGameQuestionApi(question.id, body) : createGameQuestionApi(gameId, body)
    },
    onSuccess: () => { setError(""); invalidate(); onClose() },
    onError: (e: any) => setError(e?.response?.data?.detail?.[0]?.msg ?? e?.response?.data?.detail ?? "Couldn't save this question"),
  })

  const correctCount = options.filter((o) => o.is_correct).length
  const canSave = prompt.trim().length > 0 && options.length >= 2 && options.every((o) => o.text.trim()) && correctCount === 1

  return (
    <Modal title={question ? "Edit question" : "Add question"} onClose={onClose} maxWidth="sm:max-w-xl max-w-xl">
      <div className="flex flex-col gap-4">
        <Field label="Prompt">
          <textarea
            value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={2} autoFocus
            className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary resize-none"
          />
        </Field>

        <Field label={`Options (mark the one correct answer)`}>
          <div className="flex flex-col gap-2">
            {options.map((opt, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className="w-6 h-6 flex-none flex items-center justify-center rounded-md border border-border text-[11px] font-bold text-muted-foreground">
                  {String.fromCharCode(65 + i)}
                </span>
                <input
                  value={opt.text}
                  onChange={(e) => setOptions(options.map((o, j) => j === i ? { ...o, text: e.target.value } : o))}
                  className="flex-1 h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
                  placeholder={`Option ${String.fromCharCode(65 + i)}`}
                />
                <button
                  type="button"
                  title={opt.is_correct ? "Correct answer" : "Mark correct"}
                  onClick={() => setOptions(options.map((o, j) => ({ ...o, is_correct: j === i })))}
                  className={`w-9 h-9 flex-none flex items-center justify-center rounded-xl border transition-colors ${
                    opt.is_correct ? "border-0 bg-emerald-500 text-white" : "border-border text-muted-foreground hover:bg-muted"
                  }`}
                >
                  <CheckCircle2 size={15} />
                </button>
                {options.length > 2 && (
                  <button
                    type="button"
                    onClick={() => setOptions(options.filter((_, j) => j !== i))}
                    className="w-9 h-9 flex-none flex items-center justify-center rounded-xl border border-border text-muted-foreground hover:bg-muted transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            ))}
            {options.length < 4 && (
              <button
                type="button"
                onClick={() => setOptions([...options, { text: "", is_correct: false }])}
                className="h-9 px-3 border border-dashed border-border rounded-xl text-xs font-medium text-muted-foreground hover:bg-muted transition-colors w-fit flex items-center gap-1.5"
              >
                <Plus size={12} /> Add option
              </button>
            )}
          </div>
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Time limit (blank = game default)">
            <input
              type="number" min={1} value={timeLimit} onChange={(e) => setTimeLimit(e.target.value)}
              placeholder="seconds"
              className="w-full h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
            />
          </Field>
          <Field label="Points">
            <div className="flex gap-2">
              {(["normal", "double"] as PointsMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setPointsMode(mode)}
                  className={`flex-1 h-9 rounded-xl text-xs font-semibold border transition-colors ${
                    pointsMode === mode
                      ? "border-primary/40 bg-primary/10 text-primary"
                      : "border-border text-muted-foreground hover:bg-muted"
                  }`}
                >
                  {mode === "normal" ? "Normal · 100" : "Double · 200 · X2"}
                </button>
              ))}
            </div>
          </Field>
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}
        <ModalActions
          onCancel={onClose}
          onConfirm={() => saveMutation.mutate()}
          loading={saveMutation.isPending}
          disabled={!canSave}
          label={question ? "Save question" : "Add question"}
        />
      </div>
    </Modal>
  )
}

function GameDefaultsPanel({ game, gameId }: { game: GameDetail; gameId: string }) {
  const queryClient = useQueryClient()
  const [timeLimit, setTimeLimit] = useState(game.default_time_limit_seconds.toString())
  const [floorPct, setFloorPct] = useState(game.default_floor_pct.toString())
  const [blackoutCount, setBlackoutCount] = useState(game.default_blackout_count.toString())

  useEffect(() => {
    setTimeLimit(game.default_time_limit_seconds.toString())
    setFloorPct(game.default_floor_pct.toString())
    setBlackoutCount(game.default_blackout_count.toString())
  }, [game.default_time_limit_seconds, game.default_floor_pct, game.default_blackout_count])

  const saveMutation = useMutation({
    mutationFn: () => updateGameApi(gameId, {
      default_time_limit_seconds: Number(timeLimit),
      default_floor_pct: Number(floorPct),
      default_blackout_count: Number(blackoutCount),
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["games-admin", gameId] }),
  })

  const dirty = (
    Number(timeLimit) !== game.default_time_limit_seconds ||
    Number(floorPct) !== game.default_floor_pct ||
    Number(blackoutCount) !== game.default_blackout_count
  )

  return (
    <div className="rounded-2xl bg-card ring-1 ring-border p-5 flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <SlidersHorizontal size={14} className="text-primary" />
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Game defaults</p>
      </div>
      <div className="grid grid-cols-3 gap-4">
        <Field label="Default time limit (s)">
          <input
            type="number" min={1} value={timeLimit} onChange={(e) => setTimeLimit(e.target.value)}
            className="w-full h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
          />
        </Field>
        <Field label="Slow-answer floor (%)">
          <input
            type="number" min={0} max={100} value={floorPct} onChange={(e) => setFloorPct(e.target.value)}
            className="w-full h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
          />
        </Field>
        <Field label="Blackout round (last N)">
          <input
            type="number" min={0} value={blackoutCount} onChange={(e) => setBlackoutCount(e.target.value)}
            className="w-full h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
          />
        </Field>
      </div>
      <p className="text-xs text-muted-foreground">
        A correct answer at the buzzer still earns the floor share of that question's points. The last N questions
        hide the leaderboard from students — you still see it.
      </p>
      {dirty && (
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="h-9 px-4 w-fit bg-primary text-primary-foreground text-xs font-semibold rounded-xl hover:opacity-90 transition-colors disabled:opacity-50"
        >
          {saveMutation.isPending ? "Saving…" : "Save defaults"}
        </button>
      )}
    </div>
  )
}

/** Live Quiz question editor — Claude Design spec Frame 01, rebuilt inside
 * this app's real /lms-authoring shell and component conventions (Modal
 * for add/edit, up/down arrows for reorder — same pattern
 * LmsModuleDetail.tsx already uses — rather than the mockup's inline-expand
 * row, for consistency with the rest of this authoring surface). */
export default function LmsGameDetail() {
  const { gameId } = useParams({ strict: false }) as { gameId: string }
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [editing, setEditing] = useState<GameQuestion | "new" | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<GameQuestion | null>(null)

  const { data: game, isLoading } = useQuery<GameDetail>({
    queryKey: ["games-admin", gameId],
    queryFn: () => getGameApi(gameId),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["games-admin", gameId] })

  const duplicateMutation = useMutation({
    mutationFn: (id: string) => duplicateGameQuestionApi(id),
    onSuccess: invalidate,
  })
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteGameQuestionApi(id),
    onSuccess: () => { setDeleteTarget(null); invalidate() },
  })
  const reorderMutation = useMutation({
    mutationFn: (ids: string[]) => reorderGameQuestionsApi(gameId, ids),
    onSuccess: (rows) => queryClient.setQueryData(["games-admin", gameId], (old: GameDetail | undefined) =>
      old ? { ...old, questions: rows } : old),
  })

  const move = (index: number, direction: -1 | 1) => {
    if (!game) return
    const target = index + direction
    if (target < 0 || target >= game.questions.length || reorderMutation.isPending) return
    const ids = game.questions.map((q) => q.id)
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    reorderMutation.mutate(ids)
  }

  if (isLoading || !game) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <button
        onClick={() => void navigate({ to: "/lms-authoring/games" })}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors w-fit"
      >
        <ArrowLeft size={14} /> Back
      </button>

      <PageHeader
        title={game.title}
        subtitle={`${game.question_count} question${game.question_count === 1 ? "" : "s"}${game.description ? ` · ${game.description}` : ""}`}
      />

      <GameDefaultsPanel game={game} gameId={gameId} />

      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Questions · {game.question_count}</p>
      </div>

      {game.questions.length === 0 ? (
        <EmptyState title="No questions yet" hint="Add one to start building this game." />
      ) : (
        <div className="flex flex-col gap-2">
          {game.questions.map((q, index) => {
            const correct = q.options.find((o) => o.is_correct)
            return (
              <div
                key={q.id}
                className="flex items-center gap-3 p-4 bg-card border border-border rounded-2xl"
              >
                <div className="flex flex-col shrink-0">
                  <button
                    onClick={() => move(index, -1)} disabled={index === 0 || reorderMutation.isPending}
                    className="text-muted-foreground hover:text-foreground disabled:opacity-25 transition-colors" title="Move up"
                  >
                    <ArrowUp size={14} />
                  </button>
                  <button
                    onClick={() => move(index, 1)} disabled={index === game.questions.length - 1 || reorderMutation.isPending}
                    className="text-muted-foreground hover:text-foreground disabled:opacity-25 transition-colors" title="Move down"
                  >
                    <ArrowDown size={14} />
                  </button>
                </div>
                <div className="w-7 h-7 flex-none flex items-center justify-center rounded-lg bg-primary/10 text-primary text-xs font-bold">
                  {index + 1}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-foreground truncate">{q.prompt}</p>
                  <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground flex-wrap">
                    {correct && (
                      <span className="inline-flex items-center gap-1"><CheckCircle2 size={12} className="text-emerald-500" />{correct.text}</span>
                    )}
                    <span>{q.options.length} options</span>
                    <span className="inline-flex items-center gap-1"><Timer size={12} />{q.time_limit_seconds ?? game.default_time_limit_seconds}s</span>
                    <span className={`inline-flex items-center gap-1 ${q.points_mode === "double" ? "text-primary font-semibold" : ""}`}>
                      <Sparkle size={12} />{q.max_points} pts{q.points_mode === "double" ? " · X2" : ""}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1 flex-none">
                  <button onClick={() => setEditing(q)} className="h-8 px-3 border border-border rounded-lg text-xs font-medium text-foreground hover:bg-muted transition-colors flex items-center gap-1">
                    <Pencil size={12} /> Edit
                  </button>
                  <button onClick={() => duplicateMutation.mutate(q.id)} className="h-8 px-3 border border-border rounded-lg text-xs font-medium text-foreground hover:bg-muted transition-colors flex items-center gap-1">
                    <Copy size={12} /> Duplicate
                  </button>
                  <button onClick={() => setDeleteTarget(q)} className="h-8 px-3 rounded-lg text-xs font-medium text-destructive hover:bg-destructive/10 transition-colors flex items-center gap-1">
                    <Trash2 size={12} /> Delete
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      <button
        onClick={() => setEditing("new")}
        className="h-10 px-4 border border-dashed border-border rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors w-fit flex items-center gap-1.5"
      >
        <Plus size={14} /> Add question
      </button>

      {editing && (
        <QuestionEditor
          gameId={gameId}
          question={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          title="Delete question"
          description={`"${deleteTarget.prompt}" will be removed from this game.`}
          confirmLabel="Delete"
          destructive
          pending={deleteMutation.isPending}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
        />
      )}
    </div>
  )
}
