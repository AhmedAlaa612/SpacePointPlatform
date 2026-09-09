import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { ArrowDown, ArrowUp, CheckCircle2, ChevronDown, ChevronUp, Clock, Download, Pencil, Plus, RefreshCw, Trash2, Upload, X } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { ConfirmDialog, Modal } from "@/pages/admin/components/common"
import {
  addCohortQuizTemplateQuestionApi, createCohortQuizQuestionApi, createCohortQuizTemplateApi,
  downloadCohortQuizQuestionTemplateApi, generateCohortQuizTemplateQuestionsApi, getCohortQuizTemplateApi,
  importCohortQuizQuestionsApi, listCohortQuizQuestionsApi, listCohortQuizTemplatesApi,
  removeCohortQuizTemplateQuestionApi, reorderCohortQuizTemplateQuestionsApi, retireCohortQuizQuestionApi,
  updateCohortQuizQuestionApi, type CohortQuizQuestionInput,
} from "@/api/cohort_quiz"
import type { CohortQuizDifficulty, CohortQuizQuestion } from "@/types/cohort_quiz"

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

function formatDurationMinSec(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes === 0) return `${seconds}s`
  if (seconds === 0) return `${minutes}m`
  return `${minutes}m ${seconds}s`
}

const DIFFICULTIES: CohortQuizDifficulty[] = ["Easy", "Medium", "Hard"]

/** Facilitator authoring for the cohort knowledge quiz (2026-09) — the
 * question bank (topic/difficulty/per-question timer) and the fixed
 * templates a `quiz` checklist item points at
 * (`LmsProgramAdmin.tsx`'s `ItemForm`). Every student on a checklist gets
 * the exact same template, hand-picked here — not a random draw, unlike
 * the sibling instructor-assessment authoring screen this page's shape
 * otherwise borrows from. */
export default function LmsCohortQuizAdmin() {
  const [tab, setTab] = useState<"bank" | "templates">("bank")
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Quiz Bank"
        subtitle="Author knowledge-check questions by topic and difficulty, then assemble them into fixed templates for a program checklist's quiz step."
      />
      <div className="flex gap-1 border-b border-border">
        {(["bank", "templates"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors cursor-pointer ${
              tab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t === "bank" ? "Question Bank" : "Templates"}
          </button>
        ))}
      </div>
      {tab === "bank" ? <QuestionBankTab /> : <TemplatesTab />}
    </div>
  )
}

function QuestionBankTab() {
  const queryClient = useQueryClient()
  const [topicFilter, setTopicFilter] = useState("")
  const [adding, setAdding] = useState(false)
  const [editingQuestion, setEditingQuestion] = useState<CohortQuizQuestion | null>(null)
  const [confirmRetireId, setConfirmRetireId] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [importMessage, setImportMessage] = useState("")

  const { data: questions = [], isLoading } = useQuery({
    // "all" here (vs. TemplateDetail's "active" below) — two different
    // filters must not share a cache entry, or whichever view loads first
    // within the staleTime window silently serves the other its data.
    queryKey: ["cohort-quiz-questions", "all", topicFilter],
    queryFn: () => listCohortQuizQuestionsApi(topicFilter ? { topic: topicFilter } : undefined),
  })
  const topics = Array.from(new Set(questions.map((q) => q.topic))).sort()

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["cohort-quiz-questions"] })

  const retireMutation = useMutation({
    mutationFn: (id: string) => retireCohortQuizQuestionApi(id),
    onSuccess: () => { invalidate(); setConfirmRetireId(null) },
  })

  const [importFailed, setImportFailed] = useState(false)
  const importMutation = useMutation({
    mutationFn: (file: File) => importCohortQuizQuestionsApi(file),
    onSuccess: (result) => {
      invalidate()
      const parts = [`Imported ${result.created}`]
      if (result.skipped_duplicates > 0) parts.push(`skipped ${result.skipped_duplicates} already in the bank`)
      if (result.errors.length > 0) parts.push(`skipped ${result.errors.length} row(s) with errors: ${result.errors.slice(0, 3).join("; ")}`)
      setImportFailed(false)
      setImportMessage(parts.join(", "))
    },
    onError: (err) => { setImportFailed(true); setImportMessage(errorDetail(err, "Import failed")) },
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <select
          value={topicFilter} onChange={(e) => setTopicFilter(e.target.value)}
          className="h-9 px-3 border border-border bg-card text-foreground rounded-lg text-sm cursor-pointer"
        >
          <option value="">All topics</option>
          {topics.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => void downloadCohortQuizQuestionTemplateApi()}>
            <Download size={14} className="mr-1.5" /> Template
          </Button>
          <input
            ref={fileInputRef} type="file" accept=".xlsx" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) importMutation.mutate(f); e.target.value = "" }}
          />
          <Button variant="outline" onClick={() => fileInputRef.current?.click()} disabled={importMutation.isPending}>
            <Upload size={14} className="mr-1.5" /> {importMutation.isPending ? "Importing…" : "Import xlsx"}
          </Button>
          <Button onClick={() => setAdding(true)}><Plus size={14} className="mr-1.5" /> New question</Button>
        </div>
      </div>
      {importMessage && (
        <p className={`text-xs ${importFailed ? "text-destructive" : "text-muted-foreground"}`}>{importMessage}</p>
      )}

      {adding && <QuestionForm onCancel={() => setAdding(false)} onSaved={() => { setAdding(false); invalidate() }} />}
      {editingQuestion && (
        <QuestionForm
          initial={editingQuestion}
          onCancel={() => setEditingQuestion(null)}
          onSaved={() => { setEditingQuestion(null); invalidate() }}
        />
      )}

      {isLoading ? <Spinner /> : questions.length === 0 ? (
        <EmptyState title="No questions yet" hint="Add one, or import the boss's xlsx bank." />
      ) : (
        <div className="flex flex-col gap-2">
          {questions.map((q) => (
            <div key={q.id} className={`flex items-start justify-between gap-3 p-3 bg-card border border-border rounded-xl ${!q.is_active ? "opacity-50" : ""}`}>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 flex-wrap mb-1">
                  <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border border-border text-muted-foreground">{q.topic}</span>
                  <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border border-border text-muted-foreground">{q.difficulty}</span>
                  <span className="text-[10px] text-muted-foreground">{q.time_limit_seconds}s</span>
                  {!q.is_active && <span className="text-[10px] font-semibold uppercase text-amber-600">retired</span>}
                </div>
                <p className="text-sm text-foreground">{q.prompt}</p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => setEditingQuestion(q)}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  title="Edit"
                >
                  <Pencil size={14} />
                </button>
                {q.is_active && (
                  <button
                    onClick={() => setConfirmRetireId(q.id)}
                    className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
                    title="Retire"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {confirmRetireId && (
        <ConfirmDialog
          title="Retire this question?"
          description="It stays visible in any past attempt's review, but won't be pickable for new templates."
          confirmLabel="Retire"
          destructive
          pending={retireMutation.isPending}
          onCancel={() => setConfirmRetireId(null)}
          onConfirm={() => retireMutation.mutate(confirmRetireId)}
        />
      )}
    </div>
  )
}

function QuestionForm({
  initial, onCancel, onSaved,
}: {
  initial?: CohortQuizQuestion
  onCancel: () => void
  onSaved: (createdQuestion?: CohortQuizQuestion) => void
}) {
  const { data: bankQuestions = [] } = useQuery({
    queryKey: ["cohort-quiz-questions", "all", ""],
    queryFn: () => listCohortQuizQuestionsApi(),
  })
  const existingTopics = Array.from(
    new Set(bankQuestions.map((q) => q.topic).filter((t): t is string => Boolean(t && t.trim()))),
  ).sort()

  const [topic, setTopic] = useState(initial?.topic ?? "")
  const [isCustomTopic, setIsCustomTopic] = useState(() => {
    if (!initial?.topic) return false
    return existingTopics.length > 0 && !existingTopics.includes(initial.topic)
  })
  const [subtopic, setSubtopic] = useState(initial?.subtopic ?? "")
  const [difficulty, setDifficulty] = useState<CohortQuizDifficulty>(initial?.difficulty ?? "Easy")
  const [timeLimitSeconds, setTimeLimitSeconds] = useState(initial?.time_limit_seconds ?? 15)
  const [prompt, setPrompt] = useState(initial?.prompt ?? "")
  const [options, setOptions] = useState(
    initial?.options.map((o) => ({ text: o.text, is_correct: o.is_correct }))
    ?? [{ text: "", is_correct: true }, { text: "", is_correct: false }],
  )
  const [explanation, setExplanation] = useState(initial?.explanation ?? "")
  const [error, setError] = useState("")
  const [saving, setSaving] = useState(false)

  const setOptionText = (i: number, text: string) =>
    setOptions((prev) => prev.map((o, idx) => (idx === i ? { ...o, text } : o)))
  const setCorrect = (i: number) =>
    setOptions((prev) => prev.map((o, idx) => ({ ...o, is_correct: idx === i })))

  const save = async () => {
    setError("")
    if (!topic.trim()) { setError("Topic is required"); return }
    if (!prompt.trim()) { setError("Prompt is required"); return }
    if (options.some((o) => !o.text.trim())) { setError("Every option needs text"); return }
    setSaving(true)
    try {
      const body: CohortQuizQuestionInput = {
        topic: topic.trim(), subtopic: subtopic.trim() || null, difficulty, time_limit_seconds: timeLimitSeconds,
        prompt: prompt.trim(), options: options.map((o) => ({ text: o.text.trim(), is_correct: o.is_correct })),
        explanation: explanation.trim() || null,
      }
      if (initial) {
        await updateCohortQuizQuestionApi(initial.id, body)
        onSaved()
      } else {
        const created = await createCohortQuizQuestionApi(body)
        onSaved(created)
      }
    } catch (e) {
      setError(errorDetail(e, "Failed to save"))
    } finally {
      setSaving(false)
    }
  }

  const inputCls = "w-full h-10 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"

  return (
    <Modal
      title={initial ? "Edit Question" : "New Question"}
      onClose={onCancel}
      maxWidth="sm:max-w-xl max-w-xl"
    >
      <div className="flex flex-col gap-3.5 pt-1">
        <div className="flex gap-2.5">
          <div className="flex-1 flex flex-col gap-1">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-foreground">Topic</label>
              {isCustomTopic && (
                <button
                  type="button"
                  onClick={() => {
                    setIsCustomTopic(false)
                    setTopic(existingTopics[0] ?? "")
                  }}
                  className="text-[11px] text-primary hover:underline cursor-pointer"
                >
                  ← Select existing
                </button>
              )}
            </div>
            {isCustomTopic ? (
              <input
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="Type new topic (e.g. EPS)"
                className={inputCls}
                autoFocus
              />
            ) : (
              <select
                value={topic}
                onChange={(e) => {
                  if (e.target.value === "__NEW__") {
                    setIsCustomTopic(true)
                    setTopic("")
                  } else {
                    setTopic(e.target.value)
                  }
                }}
                className={`${inputCls} cursor-pointer`}
              >
                <option value="">Select a topic…</option>
                {topic && !existingTopics.includes(topic) && (
                  <option value={topic}>{topic}</option>
                )}
                {existingTopics.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
                <option value="__NEW__">+ Add new topic…</option>
              </select>
            )}
          </div>
          <div className="flex-1 flex flex-col gap-1">
            <label className="text-xs font-semibold text-foreground">Subtopic (optional)</label>
            <input value={subtopic} onChange={(e) => setSubtopic(e.target.value)} placeholder="e.g. Solar panels" className={inputCls} />
          </div>
        </div>

        <div className="flex gap-2.5">
          <div className="flex-1 flex flex-col gap-1">
            <label className="text-xs font-semibold text-foreground">Difficulty</label>
            <select value={difficulty} onChange={(e) => setDifficulty(e.target.value as CohortQuizDifficulty)} className={`${inputCls} cursor-pointer`}>
              {DIFFICULTIES.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <div className="flex-1 flex flex-col gap-1">
            <label className="text-xs font-semibold text-foreground">Time limit (seconds)</label>
            <input
              type="number" min={1} value={timeLimitSeconds} onChange={(e) => setTimeLimitSeconds(Number(e.target.value) || 15)}
              placeholder="15" className={inputCls}
            />
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-foreground">Question Prompt</label>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Type the question prompt here…" rows={3} className={`${inputCls} h-auto py-2.5 resize-none`} />
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-xs font-semibold text-foreground">Options (select radio for correct answer)</label>
          {options.map((o, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                type="radio" name="correct-option" checked={o.is_correct} onChange={() => setCorrect(i)}
                className="w-4 h-4 text-primary cursor-pointer shrink-0" title="Mark as correct answer"
              />
              <span className="text-xs font-bold text-muted-foreground w-4 shrink-0">{String.fromCharCode(65 + i)}</span>
              <input value={o.text} onChange={(e) => setOptionText(i, e.target.value)} placeholder={`Option ${String.fromCharCode(65 + i)} text`} className={inputCls} />
              {options.length > 2 && (
                <button onClick={() => setOptions((prev) => prev.filter((_, idx) => idx !== i))} className="p-2 text-muted-foreground hover:text-red-600 rounded-lg hover:bg-muted transition-colors shrink-0">
                  <X size={15} />
                </button>
              )}
            </div>
          ))}
          {options.length < 4 && (
            <button
              onClick={() => setOptions((prev) => [...prev, { text: "", is_correct: false }])}
              className="text-xs font-semibold text-primary hover:underline w-fit mt-0.5"
            >
              + Add option
            </button>
          )}
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-foreground">Explanation (optional)</label>
          <textarea
            value={explanation} onChange={(e) => setExplanation(e.target.value)} placeholder="Explanation shown to students after submitting their answer…"
            rows={2} className={`${inputCls} h-auto py-2 resize-none`}
          />
        </div>

        {error && <p className="text-xs font-medium text-destructive">{error}</p>}

        <div className="flex justify-end gap-2 pt-3 border-t border-border mt-1">
          <Button variant="outline" onClick={onCancel}>Cancel</Button>
          <Button onClick={() => void save()} disabled={saving}>
            {saving ? "Saving…" : initial ? "Save changes" : "Create question"}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function TemplatesTab() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [createCount, setCreateCount] = useState(10)
  const [createTopics, setCreateTopics] = useState<string[]>([])

  const { data: templates = [], isLoading } = useQuery({ queryKey: ["cohort-quiz-templates"], queryFn: listCohortQuizTemplatesApi })
  // Same cache key `TemplateDetail` uses for its own topic list — sharing
  // it here means picking a topic during creation doesn't cost a second
  // fetch once the freshly-made template opens into that view.
  const { data: allActiveBank = [] } = useQuery({
    queryKey: ["cohort-quiz-questions", "active", ""],
    queryFn: () => listCohortQuizQuestionsApi({ is_active: true }),
  })
  const allTopics = Array.from(new Set(allActiveBank.map((q) => q.topic))).sort()
  const toggleCreateTopic = (topic: string) =>
    setCreateTopics((prev) => (prev.includes(topic) ? prev.filter((t) => t !== topic) : [...prev, topic]))

  const createMutation = useMutation({
    mutationFn: async () => {
      const template = await createCohortQuizTemplateApi({ name: name.trim(), description: description.trim() || null })
      if (allActiveBank.length > 0) {
        await generateCohortQuizTemplateQuestionsApi(template.id, {
          count: createCount, topics: createTopics.length > 0 ? createTopics : null,
        })
      }
      return template
    },
    onSuccess: (t) => {
      setCreating(false); setName(""); setDescription(""); setCreateTopics([])
      queryClient.invalidateQueries({ queryKey: ["cohort-quiz-templates"] })
      queryClient.invalidateQueries({ queryKey: ["cohort-quiz-template", t.id] })
      setSelectedId(t.id)
    },
  })

  return (
    <div className="flex flex-col gap-4 md:flex-row">
      <div className="flex flex-col gap-2 md:w-72 shrink-0">
        {creating ? (
          <div className="flex flex-col gap-2 p-3 bg-card border border-border rounded-xl">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Template name" className="h-9 px-3 border border-border bg-background rounded-lg text-sm" />
            <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description (optional)" className="h-9 px-3 border border-border bg-background rounded-lg text-sm" />
            {allTopics.length > 0 && (
              <>
                <div className="flex items-center gap-2">
                  <input
                    type="number" min={1} max={200} value={createCount}
                    onChange={(e) => setCreateCount(Math.min(200, Math.max(1, Number(e.target.value) || 1)))}
                    className="w-16 h-9 px-3 border border-border bg-background text-foreground rounded-lg text-sm"
                  />
                  <span className="text-xs text-muted-foreground">questions, spread across:</span>
                </div>
                <div className="flex items-center gap-1.5 flex-wrap">
                  {allTopics.map((topic) => (
                    <button
                      key={topic}
                      onClick={() => toggleCreateTopic(topic)}
                      className={`text-[11px] font-medium px-2.5 py-1 rounded-full border transition-colors cursor-pointer ${
                        createTopics.includes(topic)
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-border text-muted-foreground hover:border-primary/40"
                      }`}
                    >
                      {topic}
                    </button>
                  ))}
                </div>
                <span className="text-[11px] text-muted-foreground">
                  {createTopics.length === 0 ? "No topics selected — draws from all of them." : "You can still edit or regenerate the picks after."}
                </span>
              </>
            )}
            {createMutation.isError && (
              <p className="text-xs text-destructive">{errorDetail(createMutation.error, "Failed to create template.")}</p>
            )}
            <div className="flex gap-2">
              <Button onClick={() => void createMutation.mutate()} disabled={!name.trim() || createMutation.isPending}>
                {createMutation.isPending ? "Creating…" : "Create"}
              </Button>
              <Button variant="outline" onClick={() => setCreating(false)}>Cancel</Button>
            </div>
          </div>
        ) : (
          <Button onClick={() => setCreating(true)}><Plus size={14} className="mr-1.5" /> New template</Button>
        )}
        {isLoading ? <Spinner /> : templates.length === 0 ? (
          <EmptyState title="No templates yet" />
        ) : (
          templates.map((t) => (
            <button
              key={t.id}
              onClick={() => setSelectedId(t.id)}
              className={`text-left p-3 rounded-xl border transition-colors ${selectedId === t.id ? "border-primary bg-primary/5" : "border-border bg-card hover:border-primary/40"}`}
            >
              <p className="text-sm font-medium text-foreground">{t.name}</p>
              <p className="text-xs text-muted-foreground">{t.question_count} question{t.question_count === 1 ? "" : "s"}</p>
            </button>
          ))
        )}
      </div>
      <div className="flex-1 min-w-0">
        {selectedId ? <TemplateDetail templateId={selectedId} /> : <EmptyState title="Pick a template" hint="Or create a new one to start adding questions." />}
      </div>
    </div>
  )
}

function TemplateDetail({ templateId }: { templateId: string }) {
  const queryClient = useQueryClient()
  const [topicFilter, setTopicFilter] = useState("")
  const [pickerQuestionId, setPickerQuestionId] = useState("")
  const [generateCount, setGenerateCount] = useState(10)
  const [generateTopics, setGenerateTopics] = useState<string[]>([])
  const [confirmGenerate, setConfirmGenerate] = useState(false)
  const [editingQuestion, setEditingQuestion] = useState<CohortQuizQuestion | null>(null)
  const [creatingNewQuestion, setCreatingNewQuestion] = useState(false)
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set())

  const toggleCollapse = (id: string) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const { data: template, isLoading } = useQuery({
    queryKey: ["cohort-quiz-template", templateId], queryFn: () => getCohortQuizTemplateApi(templateId),
  })
  const { data: allActiveBank = [] } = useQuery({
    queryKey: ["cohort-quiz-questions", "active", ""],
    queryFn: () => listCohortQuizQuestionsApi({ is_active: true }),
  })
  const bank = topicFilter ? allActiveBank.filter((q) => q.topic === topicFilter) : allActiveBank
  const allTopics = Array.from(new Set(allActiveBank.map((q) => q.topic))).sort()
  const alreadyOnTemplate = new Set((template?.questions ?? []).map((tq) => tq.question.id))
  const pickable = bank.filter((q) => !alreadyOnTemplate.has(q.id))

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["cohort-quiz-template", templateId] })

  const addMutation = useMutation({
    mutationFn: (questionId: string) => addCohortQuizTemplateQuestionApi(templateId, questionId),
    onSuccess: () => { invalidate(); setPickerQuestionId("") },
  })
  const removeMutation = useMutation({
    mutationFn: (templateQuestionId: string) => removeCohortQuizTemplateQuestionApi(templateId, templateQuestionId),
    onSuccess: invalidate,
  })
  const reorderMutation = useMutation({
    mutationFn: (ids: string[]) => reorderCohortQuizTemplateQuestionsApi(templateId, ids),
    onSuccess: invalidate,
  })
  const generateMutation = useMutation({
    mutationFn: () => generateCohortQuizTemplateQuestionsApi(templateId, {
      count: generateCount, topics: generateTopics.length > 0 ? generateTopics : null,
    }),
    onSuccess: () => { invalidate(); setConfirmGenerate(false) },
  })

  const move = (index: number, direction: -1 | 1) => {
    if (!template) return
    const ids = template.questions.map((tq) => tq.id)
    const target = index + direction
    if (target < 0 || target >= ids.length) return
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    reorderMutation.mutate(ids)
  }
  const toggleGenerateTopic = (topic: string) =>
    setGenerateTopics((prev) => (prev.includes(topic) ? prev.filter((t) => t !== topic) : [...prev, topic]))

  if (isLoading || !template) return <Spinner />

  const activeQuestions = template.questions.filter((tq) => tq.question.is_active)
  const totalSeconds = activeQuestions.reduce((sum, tq) => sum + tq.question.time_limit_seconds, 0)
  const countBy = <K extends string>(pick: (tq: (typeof activeQuestions)[number]) => K) => {
    const counts = new Map<K, number>()
    for (const tq of activeQuestions) counts.set(pick(tq), (counts.get(pick(tq)) ?? 0) + 1)
    return counts
  }
  const topicCounts = countBy((tq) => tq.question.topic)
  const difficultyCounts = countBy((tq) => tq.question.difficulty as CohortQuizDifficulty)

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-base font-bold text-foreground">{template.name}</h3>
        {template.description && <p className="text-xs text-muted-foreground mt-0.5">{template.description}</p>}
      </div>

      {editingQuestion && (
        <QuestionForm
          initial={editingQuestion}
          onCancel={() => setEditingQuestion(null)}
          onSaved={() => {
            setEditingQuestion(null)
            invalidate()
            queryClient.invalidateQueries({ queryKey: ["cohort-quiz-questions"] })
          }}
        />
      )}

      {creatingNewQuestion && (
        <QuestionForm
          onCancel={() => setCreatingNewQuestion(false)}
          onSaved={async (createdQuestion) => {
            if (createdQuestion) {
              try {
                await addCohortQuizTemplateQuestionApi(templateId, createdQuestion.id)
              } catch (e) {
                // handle if already on template
              }
            }
            setCreatingNewQuestion(false)
            invalidate()
            queryClient.invalidateQueries({ queryKey: ["cohort-quiz-questions"] })
          }}
        />
      )}

      {/* 1. Stats Overview Card */}
      {activeQuestions.length > 0 && (
        <div className="rounded-2xl border border-border bg-card p-4 sm:p-5 flex flex-col gap-4 shadow-sm">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pb-4 border-b border-border">
            <div className="flex flex-col gap-0.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Total Questions</span>
              <div className="flex items-baseline gap-1.5">
                <span className="text-3xl font-extrabold font-display text-foreground">{activeQuestions.length}</span>
                <span className="text-xs text-muted-foreground font-medium">questions</span>
              </div>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Est. Duration</span>
              <div className="flex items-baseline gap-1.5">
                <span className="text-3xl font-extrabold font-display text-primary">~{formatDurationMinSec(totalSeconds)}</span>
              </div>
            </div>
            <div className="flex flex-col gap-1.5 col-span-2 sm:col-span-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Difficulty Balance</span>
              <div className="flex items-center gap-2 flex-wrap">
                {DIFFICULTIES.map((d) => {
                  const count = difficultyCounts.get(d) ?? 0
                  const badgeColor =
                    d === "Easy"
                      ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                      : d === "Medium"
                      ? "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30"
                      : "bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30"
                  return (
                    <span key={d} className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-xl border text-xs font-semibold ${badgeColor}`}>
                      {d}: <span className="font-bold text-sm">{count}</span>
                    </span>
                  )
                })}
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Topic Coverage</span>
            <div className="flex items-center gap-2 flex-wrap">
              {Array.from(topicCounts.entries()).map(([topic, count]) => (
                <span key={topic} className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border bg-background/80 text-foreground text-xs font-medium shadow-xs">
                  <span>{topic}</span>
                  <span className="px-2 py-0.5 rounded-md bg-primary/10 text-primary font-bold text-xs">{count}</span>
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 2. Regenerate Whole Set Card (Placed directly under Stats) */}
      <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl shadow-xs">
        <div>
          <p className="text-sm font-semibold text-foreground">
            {template.questions.length > 0 ? "Regenerate whole set" : "Auto-generate starting question set"}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {template.questions.length > 0
              ? "Replaces the template's current question list entirely with a new random selection."
              : "Automatically draws a balanced mix of active questions from the selected topics."}
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground font-medium">Draw</span>
            <input
              type="number" min={1} max={200} value={generateCount}
              onChange={(e) => setGenerateCount(Math.min(200, Math.max(1, Number(e.target.value) || 1)))}
              className="w-20 h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm font-semibold tabular-nums text-center"
            />
            <span className="text-xs text-muted-foreground font-medium">questions across:</span>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            {allTopics.length === 0 ? (
              <span className="text-xs text-muted-foreground italic">no active questions in the bank yet</span>
            ) : allTopics.map((topic) => (
              <button
                key={topic}
                onClick={() => toggleGenerateTopic(topic)}
                className={`text-xs font-semibold px-3 py-1.5 rounded-xl border transition-colors cursor-pointer ${
                  generateTopics.includes(topic)
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:border-primary/40"
                }`}
              >
                {topic}
              </button>
            ))}
          </div>
        </div>
        <span className="text-xs text-muted-foreground">
          {generateTopics.length === 0 ? "No topics selected — draws from all available topics." : null}
        </span>
        <Button
          variant="outline"
          onClick={() => (template.questions.length > 0 ? setConfirmGenerate(true) : generateMutation.mutate())}
          disabled={allTopics.length === 0 || generateMutation.isPending}
          className="w-fit h-10 px-4 rounded-xl text-sm font-medium gap-2"
        >
          <RefreshCw size={15} />
          {generateMutation.isPending ? "Generating…" : template.questions.length > 0 ? "Regenerate" : "Generate"}
        </Button>
        {generateMutation.isError && (
          <p className="text-xs text-destructive">{errorDetail(generateMutation.error, "Couldn't generate questions.")}</p>
        )}
      </div>

      {/* 3. Filter Topic, Add Question from Bank & Create New Question */}
      <div className="rounded-2xl border border-border bg-card p-4 flex flex-col sm:flex-row items-stretch sm:items-end gap-3 shadow-xs">
        <div className="w-full sm:w-44 shrink-0 flex flex-col gap-1.5">
          <label className="text-xs font-semibold text-foreground">Filter topic</label>
          <select
            value={topicFilter}
            onChange={(e) => setTopicFilter(e.target.value)}
            className="h-11 px-3 border border-border bg-background text-foreground rounded-xl text-sm font-medium focus:outline-none focus:border-primary transition-colors cursor-pointer"
          >
            <option value="">All topics ({allTopics.length})</option>
            {allTopics.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>

        <div className="flex-1 flex flex-col gap-1.5 min-w-0">
          <label className="text-xs font-semibold text-foreground">Select question from bank</label>
          <select
            value={pickerQuestionId}
            onChange={(e) => setPickerQuestionId(e.target.value)}
            className="h-11 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm font-medium focus:outline-none focus:border-primary transition-colors cursor-pointer truncate"
          >
            <option value="">Add from bank ({pickable.length} available)…</option>
            {pickable.map((q) => (
              <option key={q.id} value={q.id}>
                [{q.topic} - {q.difficulty}] {q.prompt.length > 60 ? q.prompt.slice(0, 60) + "…" : q.prompt}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2 shrink-0 flex-wrap sm:flex-nowrap">
          <Button
            onClick={() => pickerQuestionId && addMutation.mutate(pickerQuestionId)}
            disabled={!pickerQuestionId || addMutation.isPending}
            className="h-11 px-4 rounded-xl font-semibold text-sm gap-1.5"
          >
            <Plus size={16} /> Add From Bank
          </Button>
          <Button
            variant="outline"
            onClick={() => setCreatingNewQuestion(true)}
            className="h-11 px-4 rounded-xl font-semibold text-sm gap-1.5 border-primary/40 text-primary hover:bg-primary/10"
          >
            <Plus size={16} /> Create New Question
          </Button>
        </div>
      </div>

      {confirmGenerate && (
        <ConfirmDialog
          title="Replace this template's question set?"
          description={`This deletes all ${template.questions.length} current question(s) on this template and picks ${generateCount} new one(s) at random. Any student who already started this quiz keeps their own frozen set — this only affects new attempts.`}
          confirmLabel="Regenerate"
          destructive
          pending={generateMutation.isPending}
          onCancel={() => setConfirmGenerate(false)}
          onConfirm={() => generateMutation.mutate()}
        />
      )}

      {/* 4. Detailed & Expandable Question Cards List */}
      {template.questions.length === 0 ? (
        <EmptyState title="No questions yet" hint="Pick some from the bank above or auto-generate a set." />
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Questions on this template ({template.questions.length})
            </span>
            <button
              onClick={() => {
                if (collapsedIds.size === template.questions.length) setCollapsedIds(new Set())
                else setCollapsedIds(new Set(template.questions.map((tq) => tq.id)))
              }}
              className="text-xs font-medium text-primary hover:underline"
            >
              {collapsedIds.size === template.questions.length ? "Expand all" : "Collapse all"}
            </button>
          </div>

          {template.questions.map((tq, i) => {
            const q = tq.question
            const isCollapsed = collapsedIds.has(tq.id)
            const difficultyColor =
              q.difficulty === "Easy"
                ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                : q.difficulty === "Medium"
                ? "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30"
                : "bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30"

            return (
              <div
                key={tq.id}
                className={`flex flex-col gap-3 p-4 bg-card border rounded-2xl transition-all shadow-xs ${
                  !q.is_active ? "border-amber-500/40 opacity-70" : "border-border hover:border-primary/40"
                }`}
              >
                {/* Header Bar */}
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 flex-wrap min-w-0">
                    <div className="flex flex-col shrink-0">
                      <button onClick={() => move(i, -1)} disabled={i === 0} className="text-muted-foreground hover:text-foreground disabled:opacity-20 p-0.5" title="Move up">
                        <ArrowUp size={13} />
                      </button>
                      <button onClick={() => move(i, 1)} disabled={i === template.questions.length - 1} className="text-muted-foreground hover:text-foreground disabled:opacity-20 p-0.5" title="Move down">
                        <ArrowDown size={13} />
                      </button>
                    </div>

                    <span className="text-xs font-mono font-bold text-muted-foreground shrink-0">
                      #{String(i + 1).padStart(2, "0")}
                    </span>

                    <span className="text-[11px] font-semibold uppercase tracking-wide px-2.5 py-0.5 rounded-full border border-border bg-muted/40 text-foreground">
                      {q.topic}
                    </span>

                    {q.subtopic && (
                      <span className="text-[11px] font-medium px-2 py-0.5 rounded-full border border-border text-muted-foreground">
                        {q.subtopic}
                      </span>
                    )}

                    <span className={`text-[11px] font-semibold uppercase tracking-wide px-2.5 py-0.5 rounded-full border ${difficultyColor}`}>
                      {q.difficulty}
                    </span>

                    <span className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground px-2 py-0.5 rounded-md bg-muted/30">
                      <Clock size={12} /> {q.time_limit_seconds}s
                    </span>

                    {!q.is_active && (
                      <span className="text-[10px] font-semibold uppercase text-amber-600 dark:text-amber-500 border border-amber-500/30 rounded px-1.5 py-0.5">
                        retired
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => setEditingQuestion(q)}
                      className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                      title="Edit question & timing"
                    >
                      <Pencil size={13} /> Edit
                    </button>
                    <button
                      onClick={() => toggleCollapse(tq.id)}
                      className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                      title={isCollapsed ? "Show options & details" : "Hide options"}
                    >
                      {isCollapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
                    </button>
                    <button
                      onClick={() => removeMutation.mutate(tq.id)}
                      className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
                      title="Remove from template"
                    >
                      <X size={15} />
                    </button>
                  </div>
                </div>

                {/* Prompt */}
                <p className="text-sm font-semibold text-foreground leading-relaxed">
                  {q.prompt}
                </p>

                {/* Options & Answer key */}
                {!isCollapsed && (
                  <div className="flex flex-col gap-2 pt-1 border-t border-border/50 mt-1">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Options & Answer Key</span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {q.options.map((opt, optIdx) => (
                        <div
                          key={optIdx}
                          className={`flex items-start gap-2.5 p-2.5 rounded-xl border text-xs leading-relaxed transition-all ${
                            opt.is_correct
                              ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-950 dark:text-emerald-200 font-medium"
                              : "border-border bg-background/60 text-foreground/80"
                          }`}
                        >
                          <span
                            className={`w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5 ${
                              opt.is_correct
                                ? "bg-emerald-500 text-white"
                                : "bg-muted text-muted-foreground"
                            }`}
                          >
                            {String.fromCharCode(65 + optIdx)}
                          </span>
                          <span className="flex-1 min-w-0">{opt.text}</span>
                          {opt.is_correct && (
                            <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-600 dark:text-emerald-400 shrink-0">
                              <CheckCircle2 size={12} /> Correct
                            </span>
                          )}
                        </div>
                      ))}
                    </div>

                    {q.explanation && (
                      <div className="p-2.5 rounded-xl bg-muted/40 border border-border text-xs text-muted-foreground mt-1">
                        <span className="font-semibold text-foreground">Explanation: </span>
                        {q.explanation}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
