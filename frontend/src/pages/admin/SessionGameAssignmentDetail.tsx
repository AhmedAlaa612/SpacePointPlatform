import { useEffect, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useParams, useNavigate } from "@tanstack/react-router"
import {
  ArrowLeft, ArrowUp, ArrowDown, ArrowRight, Plus, Pencil, Copy, Trash2, Sparkle, Timer, CheckCircle2,
  SlidersHorizontal, Eye,
} from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Modal, Field, ModalActions, ConfirmDialog } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import type { GameQuestion, GameQuestionOption, PointsMode } from "@/api/games_admin"
import {
  getSessionAssignmentApi, updateSessionAssignmentApi, deleteSessionAssignmentApi,
  createAssignmentQuestionApi, updateAssignmentQuestionApi, duplicateAssignmentQuestionApi,
  deleteAssignmentQuestionApi, reorderAssignmentQuestionsApi,
  type GameSessionAssignmentDetail,
} from "@/api/games_sessions"

/** Editor for one session's independent snapshot copy of a game's questions
 * (Live Games Phase 2C, 8-4, D12) — same shape as LmsGameDetail.tsx (the
 * template editor, 8-3), pointed at `/games/sessions/*` instead of
 * `/games/admin/*`. Editing here never touches the shared template. */

function QuestionEditor({
  assignmentId, question, onClose,
}: { assignmentId: string; question: GameQuestion | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [prompt, setPrompt] = useState(question?.prompt ?? "")
  const [options, setOptions] = useState<GameQuestionOption[]>(
    question?.options ?? [{ text: "", is_correct: true }, { text: "", is_correct: false }],
  )
  const [timeLimit, setTimeLimit] = useState(question?.time_limit_seconds?.toString() ?? "")
  const [pointsMode, setPointsMode] = useState<PointsMode>(question?.points_mode ?? "normal")
  const [error, setError] = useState("")

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["game-session-assignment", assignmentId] })

  const saveMutation = useMutation({
    mutationFn: () => {
      const body = {
        prompt: prompt.trim(),
        options,
        time_limit_seconds: timeLimit.trim() ? Number(timeLimit) : null,
        points_mode: pointsMode,
      }
      return question ? updateAssignmentQuestionApi(question.id, body) : createAssignmentQuestionApi(assignmentId, body)
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

        <Field label="Options (mark the one correct answer)">
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
          <Field label="Time limit (blank = assignment default)">
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

function PreviewModal({ assignment, onClose }: { assignment: GameSessionAssignmentDetail; onClose: () => void }) {
  const [index, setIndex] = useState(0)
  const q = assignment.questions[index]

  return (
    <Modal title={`Preview · ${index + 1} of ${assignment.questions.length}`} onClose={onClose} maxWidth="sm:max-w-lg max-w-lg">
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1"><Timer size={12} />{q.time_limit_seconds ?? assignment.time_limit_seconds}s</span>
          <span className={`inline-flex items-center gap-1 ${q.points_mode === "double" ? "text-primary font-semibold" : ""}`}>
            <Sparkle size={12} />{q.max_points} pts{q.points_mode === "double" ? " · X2" : ""}
          </span>
        </div>
        <p className="text-base font-semibold text-foreground">{q.prompt}</p>
        <div className="grid grid-cols-1 gap-2">
          {q.options.map((opt, i) => (
            <div
              key={i}
              className={`flex items-center gap-2 h-11 px-3 rounded-xl border text-sm ${
                opt.is_correct ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-600" : "border-border text-foreground"
              }`}
            >
              <span className="w-5 h-5 flex-none flex items-center justify-center rounded-md border border-current text-[10px] font-bold">
                {String.fromCharCode(65 + i)}
              </span>
              <span className="flex-1 truncate">{opt.text}</span>
              {opt.is_correct && <CheckCircle2 size={14} />}
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between pt-2">
          <button
            onClick={() => setIndex((i) => Math.max(0, i - 1))} disabled={index === 0}
            className="h-9 px-3 border border-border rounded-xl text-xs font-medium text-foreground hover:bg-muted disabled:opacity-30 transition-colors"
          >
            Previous
          </button>
          <button
            onClick={() => index === assignment.questions.length - 1 ? onClose() : setIndex((i) => i + 1)}
            className="h-9 px-4 bg-primary text-primary-foreground rounded-xl text-xs font-semibold hover:opacity-90 transition-colors flex items-center gap-1.5"
          >
            {index === assignment.questions.length - 1 ? "Done" : "Next"} <ArrowRight size={12} />
          </button>
        </div>
      </div>
    </Modal>
  )
}

function AssignmentConfigPanel({ assignment, assignmentId }: { assignment: GameSessionAssignmentDetail; assignmentId: string }) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [note, setNote] = useState(assignment.instructor_note ?? "")
  const [timeLimit, setTimeLimit] = useState(assignment.time_limit_seconds.toString())
  const [floorPct, setFloorPct] = useState(assignment.floor_pct.toString())
  const [blackoutCount, setBlackoutCount] = useState(assignment.blackout_count.toString())

  useEffect(() => {
    setNote(assignment.instructor_note ?? "")
    setTimeLimit(assignment.time_limit_seconds.toString())
    setFloorPct(assignment.floor_pct.toString())
    setBlackoutCount(assignment.blackout_count.toString())
  }, [assignment.instructor_note, assignment.time_limit_seconds, assignment.floor_pct, assignment.blackout_count])

  const saveMutation = useMutation({
    mutationFn: () => updateSessionAssignmentApi(assignmentId, {
      instructor_note: note.trim() || null,
      time_limit_seconds: Number(timeLimit),
      floor_pct: Number(floorPct),
      blackout_count: Number(blackoutCount),
    }),
    onSuccess: () => { toast.success("Saved"); queryClient.invalidateQueries({ queryKey: ["game-session-assignment", assignmentId] }) },
  })

  const dirty = (
    note !== (assignment.instructor_note ?? "") ||
    Number(timeLimit) !== assignment.time_limit_seconds ||
    Number(floorPct) !== assignment.floor_pct ||
    Number(blackoutCount) !== assignment.blackout_count
  )

  return (
    <div className="rounded-2xl bg-card ring-1 ring-border p-5 flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <SlidersHorizontal size={14} className="text-primary" />
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Session config</p>
      </div>
      <Field label="Instructor note (not shown to students)">
        <textarea
          value={note} onChange={(e) => setNote(e.target.value)} rows={2}
          className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary resize-none"
        />
      </Field>
      <div className="grid grid-cols-3 gap-4">
        <Field label="Time limit (s)">
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
        Copied from the game's defaults when it was assigned — editing these only affects this session, not the
        shared game or any other session it's assigned to.
      </p>
      {dirty && (
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="h-9 px-4 w-fit bg-primary text-primary-foreground text-xs font-semibold rounded-xl hover:opacity-90 transition-colors disabled:opacity-50"
        >
          {saveMutation.isPending ? "Saving…" : "Save"}
        </button>
      )}
    </div>
  )
}

export default function SessionGameAssignmentDetail() {
  const { assignmentId } = useParams({ strict: false }) as { assignmentId: string }
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const toast = useToast()
  const [editing, setEditing] = useState<GameQuestion | "new" | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<GameQuestion | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [removeAssignmentConfirm, setRemoveAssignmentConfirm] = useState(false)

  const { data: assignment, isLoading } = useQuery<GameSessionAssignmentDetail>({
    queryKey: ["game-session-assignment", assignmentId],
    queryFn: () => getSessionAssignmentApi(assignmentId),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["game-session-assignment", assignmentId] })

  const duplicateMutation = useMutation({
    mutationFn: (id: string) => duplicateAssignmentQuestionApi(id),
    onSuccess: invalidate,
  })
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteAssignmentQuestionApi(id),
    onSuccess: () => { setDeleteTarget(null); invalidate() },
  })
  const reorderMutation = useMutation({
    mutationFn: (ids: string[]) => reorderAssignmentQuestionsApi(assignmentId, ids),
    onSuccess: (rows) => queryClient.setQueryData(["game-session-assignment", assignmentId], (old: GameSessionAssignmentDetail | undefined) =>
      old ? { ...old, questions: rows } : old),
  })
  const removeAssignmentMutation = useMutation({
    mutationFn: () => deleteSessionAssignmentApi(assignmentId),
    onSuccess: () => {
      toast.success("Assignment removed")
      queryClient.invalidateQueries({ queryKey: ["game-session-assignments"] })
      navigate({ to: "/operations/cohorts" })
    },
  })

  const move = (index: number, direction: -1 | 1) => {
    if (!assignment) return
    const target = index + direction
    if (target < 0 || target >= assignment.questions.length || reorderMutation.isPending) return
    const ids = assignment.questions.map((q) => q.id)
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    reorderMutation.mutate(ids)
  }

  if (isLoading || !assignment) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <button
        onClick={() => window.history.back()}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors w-fit"
      >
        <ArrowLeft size={14} /> Back
      </button>

      <PageHeader
        title={assignment.game_title}
        subtitle={`${assignment.question_count} question${assignment.question_count === 1 ? "" : "s"} · this session's own copy`}
        action={
          <button
            onClick={() => setRemoveAssignmentConfirm(true)}
            className="h-9 px-3 border border-border rounded-lg text-xs font-medium text-destructive hover:bg-destructive/10 transition-colors flex items-center gap-1.5"
          >
            <Trash2 size={12} /> Remove from session
          </button>
        }
      />

      <AssignmentConfigPanel assignment={assignment} assignmentId={assignmentId} />

      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Questions · {assignment.question_count}</p>
        {assignment.questions.length > 0 && (
          <button
            onClick={() => setPreviewing(true)}
            className="h-8 px-3 border border-border rounded-lg text-xs font-medium text-foreground hover:bg-muted transition-colors flex items-center gap-1.5"
          >
            <Eye size={12} /> Preview
          </button>
        )}
      </div>

      {assignment.questions.length === 0 ? (
        <EmptyState title="No questions yet" hint="Add one to start building this session's copy." />
      ) : (
        <div className="flex flex-col gap-2">
          {assignment.questions.map((q, index) => {
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
                    onClick={() => move(index, 1)} disabled={index === assignment.questions.length - 1 || reorderMutation.isPending}
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
                    <span className="inline-flex items-center gap-1"><Timer size={12} />{q.time_limit_seconds ?? assignment.time_limit_seconds}s</span>
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

      {previewing && assignment.questions.length > 0 && (
        <PreviewModal assignment={assignment} onClose={() => setPreviewing(false)} />
      )}

      {editing && (
        <QuestionEditor
          assignmentId={assignmentId}
          question={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          title="Delete question"
          description={`"${deleteTarget.prompt}" will be removed from this session's copy — the shared game is unaffected.`}
          confirmLabel="Delete"
          destructive
          pending={deleteMutation.isPending}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
        />
      )}

      {removeAssignmentConfirm && (
        <ConfirmDialog
          title="Remove this game from the session"
          description="The instructor will no longer see it as an option to start. The shared game template is unaffected."
          confirmLabel="Remove"
          destructive
          pending={removeAssignmentMutation.isPending}
          onCancel={() => setRemoveAssignmentConfirm(false)}
          onConfirm={() => removeAssignmentMutation.mutate()}
        />
      )}
    </div>
  )
}
