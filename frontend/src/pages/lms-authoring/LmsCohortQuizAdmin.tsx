import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { ArrowDown, ArrowUp, Download, Plus, Trash2, Upload, X } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/pages/admin/components/common"
import {
  addCohortQuizTemplateQuestionApi, createCohortQuizQuestionApi, createCohortQuizTemplateApi,
  downloadCohortQuizQuestionTemplateApi, getCohortQuizTemplateApi, importCohortQuizQuestionsApi,
  listCohortQuizQuestionsApi, listCohortQuizTemplatesApi, removeCohortQuizTemplateQuestionApi,
  reorderCohortQuizTemplateQuestionsApi, retireCohortQuizQuestionApi, type CohortQuizQuestionInput,
} from "@/api/cohort_quiz"
import type { CohortQuizDifficulty } from "@/types/cohort_quiz"

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
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
              {q.is_active && (
                <button
                  onClick={() => setConfirmRetireId(q.id)}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors shrink-0"
                  title="Retire"
                >
                  <Trash2 size={14} />
                </button>
              )}
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

function QuestionForm({ onCancel, onSaved }: { onCancel: () => void; onSaved: () => void }) {
  const [topic, setTopic] = useState("")
  const [subtopic, setSubtopic] = useState("")
  const [difficulty, setDifficulty] = useState<CohortQuizDifficulty>("Easy")
  const [timeLimitSeconds, setTimeLimitSeconds] = useState(15)
  const [prompt, setPrompt] = useState("")
  const [options, setOptions] = useState([{ text: "", is_correct: true }, { text: "", is_correct: false }])
  const [explanation, setExplanation] = useState("")
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
      await createCohortQuizQuestionApi(body)
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
        <Button onClick={() => void save()} disabled={saving}>{saving ? "Saving…" : "Save question"}</Button>
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

  const { data: templates = [], isLoading } = useQuery({ queryKey: ["cohort-quiz-templates"], queryFn: listCohortQuizTemplatesApi })

  const createMutation = useMutation({
    mutationFn: () => createCohortQuizTemplateApi({ name: name.trim(), description: description.trim() || null }),
    onSuccess: (t) => {
      setCreating(false); setName(""); setDescription("")
      queryClient.invalidateQueries({ queryKey: ["cohort-quiz-templates"] })
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
            <div className="flex gap-2">
              <Button onClick={() => void createMutation.mutate()} disabled={!name.trim() || createMutation.isPending}>Create</Button>
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

  const { data: template, isLoading } = useQuery({
    queryKey: ["cohort-quiz-template", templateId], queryFn: () => getCohortQuizTemplateApi(templateId),
  })
  const { data: bank = [] } = useQuery({
    // "active" (vs. QuestionBankTab's "all" above) — see that query's own
    // comment on why these must not share a cache key.
    queryKey: ["cohort-quiz-questions", "active", topicFilter],
    queryFn: () => listCohortQuizQuestionsApi(topicFilter ? { topic: topicFilter, is_active: true } : { is_active: true }),
  })
  const topics = Array.from(new Set(bank.map((q) => q.topic))).sort()
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

  const move = (index: number, direction: -1 | 1) => {
    if (!template) return
    const ids = template.questions.map((tq) => tq.id)
    const target = index + direction
    if (target < 0 || target >= ids.length) return
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    reorderMutation.mutate(ids)
  }

  if (isLoading || !template) return <Spinner />

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-foreground">{template.name}</h3>
      {template.description && <p className="text-xs text-muted-foreground">{template.description}</p>}

      <div className="flex items-center gap-2">
        <select value={topicFilter} onChange={(e) => setTopicFilter(e.target.value)} className="h-9 px-3 border border-border bg-card text-foreground rounded-lg text-sm cursor-pointer">
          <option value="">All topics</option>
          {topics.map((t) => <option key={t} value={t}>{t}</option>)}
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
