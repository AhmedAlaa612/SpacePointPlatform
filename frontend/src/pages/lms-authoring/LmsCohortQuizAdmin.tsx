import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { ArrowDown, ArrowUp, Download, Pencil, Plus, RefreshCw, Trash2, Upload, X } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/pages/admin/components/common"
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
  onSaved: () => void
}) {
  const [topic, setTopic] = useState(initial?.topic ?? "")
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
      } else {
        await createCohortQuizQuestionApi(body)
      }
      onSaved()
    } catch (e) {
      setError(errorDetail(e, "Failed to save"))
    } finally {
      setSaving(false)
    }
  }

  const inputCls = "w-full h-9 px-3 border border-border bg-background text-foreground rounded-lg text-sm focus:outline-none focus:border-primary transition-colors"

  return (
    <div className="flex flex-col gap-2.5 p-4 border border-primary/30 bg-primary/5 rounded-xl">
      <div className="flex gap-2.5">
        <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Topic (e.g. EPS)" className={inputCls} />
        <input value={subtopic} onChange={(e) => setSubtopic(e.target.value)} placeholder="Subtopic (optional)" className={inputCls} />
      </div>
      <div className="flex gap-2.5">
        <select value={difficulty} onChange={(e) => setDifficulty(e.target.value as CohortQuizDifficulty)} className={`${inputCls} cursor-pointer`}>
          {DIFFICULTIES.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
        <input
          type="number" min={1} value={timeLimitSeconds} onChange={(e) => setTimeLimitSeconds(Number(e.target.value) || 15)}
          placeholder="Time limit (sec)" className={inputCls}
        />
      </div>
      <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Question prompt" rows={2} className={`${inputCls} h-auto py-2 resize-none`} />
      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] font-medium text-muted-foreground">Options — pick the correct one</label>
        {options.map((o, i) => (
          <div key={i} className="flex items-center gap-2">
            <input type="radio" checked={o.is_correct} onChange={() => setCorrect(i)} />
            <input value={o.text} onChange={(e) => setOptionText(i, e.target.value)} placeholder={`Option ${String.fromCharCode(65 + i)}`} className={inputCls} />
            {options.length > 2 && (
              <button onClick={() => setOptions((prev) => prev.filter((_, idx) => idx !== i))} className="p-1 text-muted-foreground hover:text-red-600">
                <X size={14} />
              </button>
            )}
          </div>
        ))}
        {options.length < 4 && (
          <button
            onClick={() => setOptions((prev) => [...prev, { text: "", is_correct: false }])}
            className="text-xs text-primary hover:underline w-fit"
          >
            + Add option
          </button>
        )}
      </div>
      <textarea
        value={explanation} onChange={(e) => setExplanation(e.target.value)} placeholder="Explanation (optional, shown after submit)"
        rows={2} className={`${inputCls} h-auto py-2 resize-none`}
      />
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex gap-2">
        <Button onClick={() => void save()} disabled={saving}>
          {saving ? "Saving…" : initial ? "Save changes" : "Save question"}
        </Button>
        <Button variant="outline" onClick={onCancel}>Cancel</Button>
      </div>
    </div>
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

  const { data: template, isLoading } = useQuery({
    queryKey: ["cohort-quiz-template", templateId], queryFn: () => getCohortQuizTemplateApi(templateId),
  })
  // "active" (vs. QuestionBankTab's "all" above) — see that query's own
  // comment on why these must not share a cache key. Fetched unfiltered —
  // both the "add one question" picker (topic-filtered client-side below)
  // and the generate panel's topic checkboxes (which need every active
  // topic regardless of that filter) read from this one query.
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

  // Stats over the template's active questions — everything they need
  // (topic, difficulty, time_limit_seconds) already comes back on
  // `template.questions`, so this is a pure client-side derivation, no
  // extra endpoint. Retired questions are excluded, matching the
  // active-only `question_count` the badges elsewhere already show.
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
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-foreground">{template.name}</h3>
      {template.description && <p className="text-xs text-muted-foreground">{template.description}</p>}

      {activeQuestions.length > 0 && (
        <div className="flex flex-col gap-2 p-3 bg-muted/30 border border-border rounded-xl text-xs">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="font-semibold text-foreground">
              {activeQuestions.length} question{activeQuestions.length === 1 ? "" : "s"}
            </span>
            <span className="text-muted-foreground">~{formatDurationMinSec(totalSeconds)} total</span>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            {Array.from(topicCounts.entries()).map(([topic, count]) => (
              <span key={topic} className="px-2 py-0.5 rounded-full border border-border text-muted-foreground">
                {topic} <span className="text-foreground font-medium">{count}</span>
              </span>
            ))}
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            {DIFFICULTIES.filter((d) => difficultyCounts.has(d)).map((d) => (
              <span key={d} className="px-2 py-0.5 rounded-full border border-border text-muted-foreground">
                {d} <span className="text-foreground font-medium">{difficultyCounts.get(d)}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center gap-2">
        <select value={topicFilter} onChange={(e) => setTopicFilter(e.target.value)} className="h-9 px-3 border border-border bg-card text-foreground rounded-lg text-sm cursor-pointer">
          <option value="">All topics</option>
          {allTopics.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={pickerQuestionId} onChange={(e) => setPickerQuestionId(e.target.value)} className="flex-1 h-9 px-3 border border-border bg-card text-foreground rounded-lg text-sm cursor-pointer">
          <option value="">Add a question…</option>
          {pickable.map((q) => <option key={q.id} value={q.id}>[{q.topic}] {q.prompt.slice(0, 60)}</option>)}
        </select>
        <Button
          onClick={() => pickerQuestionId && addMutation.mutate(pickerQuestionId)}
          disabled={!pickerQuestionId || addMutation.isPending}
        >
          <Plus size={14} />
        </Button>
      </div>

      <div className="flex flex-col gap-2 p-3 bg-muted/30 border border-border rounded-xl">
        <p className="text-xs font-semibold text-foreground">
          {template.questions.length > 0 ? "Regenerate the whole set" : "Or auto-generate a starting set"}
        </p>
        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="number" min={1} max={200} value={generateCount}
            onChange={(e) => setGenerateCount(Math.min(200, Math.max(1, Number(e.target.value) || 1)))}
            className="w-20 h-9 px-3 border border-border bg-background text-foreground rounded-lg text-sm"
          />
          <span className="text-xs text-muted-foreground">questions, spread across:</span>
          <div className="flex items-center gap-1.5 flex-wrap">
            {allTopics.length === 0 ? (
              <span className="text-xs text-muted-foreground italic">no active questions in the bank yet</span>
            ) : allTopics.map((topic) => (
              <button
                key={topic}
                onClick={() => toggleGenerateTopic(topic)}
                className={`text-[11px] font-medium px-2.5 py-1 rounded-full border transition-colors cursor-pointer ${
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
        <span className="text-[11px] text-muted-foreground">
          {generateTopics.length === 0 ? "No topics selected — draws from all of them." : null}
          {template.questions.length > 0 && " This replaces the template's current question list entirely."}
        </span>
        <Button
          variant="outline"
          onClick={() => (template.questions.length > 0 ? setConfirmGenerate(true) : generateMutation.mutate())}
          disabled={allTopics.length === 0 || generateMutation.isPending}
          className="w-fit"
        >
          <RefreshCw size={14} className="mr-1.5" />
          {generateMutation.isPending ? "Generating…" : template.questions.length > 0 ? "Regenerate" : "Generate"}
        </Button>
        {generateMutation.isError && (
          <p className="text-xs text-destructive">{errorDetail(generateMutation.error, "Couldn't generate questions.")}</p>
        )}
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

      {template.questions.length === 0 ? (
        <EmptyState title="No questions yet" hint="Pick some from the bank above." />
      ) : (
        <div className="flex flex-col gap-2">
          {template.questions.map((tq, i) => (
            <div key={tq.id} className={`flex items-center gap-2 p-3 bg-card border rounded-xl ${tq.question.is_active ? "border-border" : "border-amber-500/40"}`}>
              <div className="flex flex-col">
                <button onClick={() => move(i, -1)} disabled={i === 0} className="text-muted-foreground hover:text-foreground disabled:opacity-30"><ArrowUp size={12} /></button>
                <button onClick={() => move(i, 1)} disabled={i === template.questions.length - 1} className="text-muted-foreground hover:text-foreground disabled:opacity-30"><ArrowDown size={12} /></button>
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 flex-wrap mb-0.5">
                  <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border border-border text-muted-foreground">{tq.question.topic}</span>
                  <span className="text-[10px] text-muted-foreground">{tq.question.time_limit_seconds}s</span>
                  {!tq.question.is_active && (
                    <span className="text-[10px] font-semibold uppercase text-amber-600 dark:text-amber-500 border border-amber-500/30 rounded px-1.5 py-0.5">
                      retired — won't be served
                    </span>
                  )}
                </div>
                <p className="text-sm text-foreground truncate">{tq.question.prompt}</p>
              </div>
              <button onClick={() => removeMutation.mutate(tq.id)} className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors shrink-0">
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
