import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  BookOpen,
  ChevronDown,
  ChevronUp,
  FileText,
  Layers,
  Plus,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react"
import { resolveQuizImageUrl } from "@/api/lms"
import {
  createPreQuizPresetApi,
  createPreQuizQuestionApi,
  deletePreQuizPresetApi,
  deletePreQuizQuestionApi,
  listPreQuizPresetsApi,
  listPreQuizQuestionsApi,
  updatePreQuizPresetApi,
  updatePreQuizQuestionApi,
  uploadPreQuizDatasheetApi,
  uploadPreQuizImageApi,
  type MatchingItemRule,
  type MatchingPhaseConfig,
  type McqOption,
  type PinoutTableConfig,
  type PreSessionQuizPreset,
  type PreSessionQuizPresetIn,
  type PreSessionQuizQuestion,
  type PreSessionQuizQuestionIn,
  type QuizPipelinePhase,
  type ReferenceAttachment,
} from "@/api/sessions/pre_session_quiz"
import { ConnectorTableWidget } from "@/components/quiz/ConnectorTableWidget"
import { SessionPreQuizModal } from "@/pages/instructors/components/SessionPreQuizModal"
import { EmptyState, PageHeader, Spinner } from "@/components/ui/primitives"
import { useToast } from "@/components/ui/toast"
import { cn, ensureAbsoluteUrl, getErrorMessage } from "@/lib/utils"
import { ConfirmDialog, Field, Modal, ModalActions } from "@/pages/admin/components/common"

const DEFAULT_TABLE_CONFIG: PinoutTableConfig = {
  connector_name: "J3",
  header_subtitle: "J31, J32, J33, J34",
  columns: ["1", "2", "3"],
  rows: [
    {
      label: "Pin 1",
      cells: [
        { text: "3V3", is_correct: true },
        { text: "Main", is_correct: true },
        { text: "GND", is_correct: false },
      ],
    },
    {
      label: "Pin 2",
      cells: [
        { text: "3V3", is_correct: false },
        { text: "Main", is_correct: true },
        { text: "GND", is_correct: true },
      ],
    },
  ],
}

const DEFAULT_MCQ_OPTIONS: McqOption[] = [
  { text: "Leave Open", is_correct: false },
  { text: "Short (Connect the Jumper Header Between Both Pins)", is_correct: true },
]

export default function PreSessionQuizzes() {
  const [tab, setTab] = useState<"bank" | "presets">("presets")

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Instructor Pre-Session Quizzes &amp; Readiness Pipeline"
        subtitle="Build multi-phase cohort readiness pipelines, configure interactive connector pinouts, MCQ checks, and written scenarios."
      />

      <div className="flex gap-1 border-b border-border overflow-x-auto scrollbar-none no-scrollbar">
        <button
          type="button"
          onClick={() => setTab("presets")}
          className={cn(
            "px-4 py-2.5 text-sm font-semibold border-b-2 -mb-px transition-colors cursor-pointer shrink-0 flex items-center gap-2",
            tab === "presets"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <Layers size={15} />
          Quiz Presets &amp; Pipelines
        </button>
        <button
          type="button"
          onClick={() => setTab("bank")}
          className={cn(
            "px-4 py-2.5 text-sm font-semibold border-b-2 -mb-px transition-colors cursor-pointer shrink-0 flex items-center gap-2",
            tab === "bank"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <BookOpen size={15} />
          Question Bank (Visual Builder)
        </button>
      </div>

      {tab === "presets" ? <PresetsTab /> : <QuestionBankTab />}
    </div>
  )
}

/* ── Tab 1: Question Bank with Visual Pinout Builder ───────────────────────── */

function QuestionBankTab() {
  const qc = useQueryClient()
  const toast = useToast()
  const [topicFilter, setTopicFilter] = useState<string>("all")
  const [editingQuestion, setEditingQuestion] = useState<PreSessionQuizQuestion | null>(null)
  const [creating, setCreating] = useState(false)
  const [deletingQuestion, setDeletingQuestion] = useState<PreSessionQuizQuestion | null>(null)
  const [previewQuestions, setPreviewQuestions] = useState<PreSessionQuizQuestion[] | null>(null)

  const { data: questions = [], isLoading } = useQuery({
    queryKey: ["pre-quiz-questions"],
    queryFn: () => listPreQuizQuestionsApi({ active_only: false }),
  })

  const topics = useMemo(() => {
    const set = new Set<string>()
    questions.forEach((q) => {
      if (q.topic) set.add(q.topic)
    })
    return Array.from(set).sort()
  }, [questions])

  const filtered = useMemo(() => {
    if (topicFilter === "all") return questions
    return questions.filter((q) => q.topic === topicFilter)
  }, [questions, topicFilter])

  const deleteMut = useMutation({
    mutationFn: (id: string) => deletePreQuizQuestionApi(id),
    onSuccess: () => {
      toast.success("Question deleted")
      setDeletingQuestion(null)
      qc.invalidateQueries({ queryKey: ["pre-quiz-questions"] })
      qc.invalidateQueries({ queryKey: ["pre-quiz-presets"] })
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not delete question")),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            type="button"
            onClick={() => setTopicFilter("all")}
            className={cn(
              "h-8 px-3 rounded-full text-xs font-semibold transition-colors cursor-pointer",
              topicFilter === "all"
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:text-foreground"
            )}
          >
            All Topics ({questions.length})
          </button>
          {topics.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTopicFilter(t)}
              className={cn(
                "h-8 px-3 rounded-full text-xs font-semibold transition-colors cursor-pointer",
                topicFilter === t
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:text-foreground"
              )}
            >
              {t} ({questions.filter((q) => q.topic === t).length})
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {filtered.length > 0 && (
            <button
              type="button"
              onClick={() => setPreviewQuestions(filtered)}
              className="flex items-center justify-center h-9 px-3.5 border border-primary/40 bg-primary/10 text-primary rounded-xl text-xs sm:text-sm font-semibold hover:bg-primary/20 transition-colors cursor-pointer shrink-0"
            >
              Preview ({filtered.length})
            </button>
          )}
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="flex items-center justify-center h-9 px-4 bg-primary text-primary-foreground rounded-xl text-xs sm:text-sm font-semibold hover:opacity-90 transition-opacity cursor-pointer shrink-0 shadow-xs gap-1.5"
          >
            <Plus size={15} /> New Question
          </button>
        </div>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          title="No questions in this topic yet"
          hint="Click 'New Question' to launch the visual hardware pinout table, MCQ, or written scenario builder."
        />
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {filtered.map((q) => (
            <div
              key={q.id}
              className="p-4 rounded-2xl border border-border bg-card/80 flex flex-col gap-3 shadow-xs"
            >
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="flex flex-col gap-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-primary/10 text-primary border border-primary/20">
                      {q.topic}
                    </span>
                    <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-muted text-foreground border border-border">
                      {q.question_type === "pinout_table"
                        ? "Connector Pinout Table"
                        : q.question_type === "written"
                        ? "Written Scenario"
                        : q.question_type === "subsystem_matching"
                        ? "Subsystem Matching"
                        : "Multiple Choice"}
                    </span>
                    {q.is_other_correct && (
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30">
                        Tricky Question (&ldquo;Other&rdquo; Expected)
                      </span>
                    )}
                    {q.image_url && (
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
                        Has Image
                      </span>
                    )}
                    {q.explanation_image_url && (
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                        Has Explanation Image
                      </span>
                    )}
                  </div>
                  <h3 className="text-sm sm:text-base font-bold text-foreground mt-0.5">{q.title}</h3>
                  <p className="text-xs sm:text-sm text-muted-foreground whitespace-pre-wrap">{q.prompt}</p>
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  <button
                    type="button"
                    onClick={() => setPreviewQuestions([q])}
                    className="flex items-center h-8 px-3 rounded-lg border border-primary/35 bg-primary/10 hover:bg-primary/20 text-xs font-semibold text-primary transition-colors cursor-pointer"
                  >
                    Preview
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditingQuestion(q)}
                    className="flex items-center h-8 px-3 rounded-lg border border-border bg-background hover:bg-muted text-xs font-medium text-foreground transition-colors cursor-pointer"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeletingQuestion(q)}
                    className="h-8 px-2.5 rounded-lg border border-border bg-background hover:bg-red-500/10 text-xs font-medium text-muted-foreground hover:text-red-500 transition-colors cursor-pointer"
                    title="Delete question"
                  >
                    Delete
                  </button>
                </div>
              </div>

              {q.image_url && (
                <div className="max-h-48 overflow-hidden rounded-xl border border-border bg-muted/20 p-2 flex justify-center">
                  <img
                    src={resolveQuizImageUrl(q.image_url)}
                    alt={q.title}
                    className="max-h-44 object-contain rounded"
                  />
                </div>
              )}

              {q.question_type === "pinout_table" && q.table_config && (
                <div className="max-w-xl">
                  <ConnectorTableWidget config={q.table_config} mode="reference" />
                </div>
              )}

              {q.question_type === "mcq" && q.options.length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-xl">
                  {q.options.map((opt, idx) => (
                    <div
                      key={idx}
                      className={cn(
                        "px-3 py-2 rounded-xl border text-xs font-semibold flex items-center justify-between gap-2",
                        opt.is_correct
                          ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-700 dark:text-emerald-300"
                          : "bg-muted/40 border-border text-muted-foreground"
                      )}
                    >
                      <span>{opt.text}</span>
                      {opt.is_correct && (
                        <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 shrink-0">
                          Correct
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {q.question_type === "written" && (
                <div className="p-3 rounded-xl border border-border bg-muted/30 max-w-xl text-xs text-muted-foreground italic">
                  Instructor writes an open-ended technical diagnostic answer.
                </div>
              )}

              {(q.explanation || q.explanation_table || q.explanation_image_url) && (
                <div className="p-3 rounded-xl bg-muted/40 border border-border/80 flex flex-col gap-2">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                    Post-Submission Explanation / Ops Grading Reference
                  </span>
                  {q.explanation && <p className="text-xs text-foreground whitespace-pre-wrap">{q.explanation}</p>}
                  {q.explanation_image_url && (
                    <div className="max-h-44 overflow-hidden rounded-lg border border-border bg-card p-2 flex justify-center">
                      <img
                        src={resolveQuizImageUrl(q.explanation_image_url)}
                        alt="Explanation diagram"
                        className="max-h-40 object-contain rounded"
                      />
                    </div>
                  )}
                  {q.explanation_table && (
                    <div className="max-w-xl pt-1">
                      <ConnectorTableWidget config={q.explanation_table} mode="reference" />
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {(creating || editingQuestion) && (
        <QuestionBuilderModal
          question={editingQuestion}
          existingTopics={topics}
          onClose={() => {
            setCreating(false)
            setEditingQuestion(null)
          }}
          onSaved={() => {
            setCreating(false)
            setEditingQuestion(null)
            qc.invalidateQueries({ queryKey: ["pre-quiz-questions"] })
            qc.invalidateQueries({ queryKey: ["pre-quiz-presets"] })
          }}
        />
      )}

      {deletingQuestion && (
        <ConfirmDialog
          title="Delete Question"
          description={`Are you sure you want to delete "${deletingQuestion.title}"?`}
          confirmLabel="Delete"
          destructive
          pending={deleteMut.isPending}
          onConfirm={() => deleteMut.mutate(deletingQuestion.id)}
          onCancel={() => setDeletingQuestion(null)}
        />
      )}

      {previewQuestions && (
        <SessionPreQuizModal
          open={Boolean(previewQuestions)}
          onClose={() => setPreviewQuestions(null)}
          isPreview
          quizStatus={{
            has_quiz: true,
            assignment_level: "preview",
            preset: {
              id: "preview-questions",
              name:
                previewQuestions.length === 1
                  ? `Preview: ${previewQuestions[0].title}`
                  : `Question Bank Preview (${topicFilter === "all" ? "All Topics" : topicFilter})`,
              description: "Interactive Instructor View Preview",
              question_ids: previewQuestions.map((q) => q.id),
              reference_attachments: [],
              phases: [],
              questions: previewQuestions,
              is_active: true,
            },
            my_attempt: null,
            trials: [],
            all_attempts: [],
          }}
        />
      )}
    </div>
  )
}

/* ── Visual Question Builder Modal ─────────────────────────────────────────── */

function QuestionBuilderModal({
  question,
  existingTopics,
  onClose,
  onSaved,
}: {
  question: PreSessionQuizQuestion | null
  existingTopics: string[]
  onClose: () => void
  onSaved: () => void
}) {
  const toast = useToast()
  const [topic, setTopic] = useState(question?.topic ?? "CDHS")
  const [questionType, setQuestionType] = useState<"pinout_table" | "mcq" | "written">(() => {
    if (question?.question_type === "written") return "written"
    if (question?.question_type === "mcq") return "mcq"
    return "pinout_table"
  })
  const [title, setTitle] = useState(question?.title ?? "")
  const [prompt, setPrompt] = useState(
    question?.prompt ??
      "Select the required jumper header pinout positions on the connector below based on the subsystem and module datasheets."
  )
  const [imageUrl, setImageUrl] = useState(question?.image_url ?? "")
  const [tableConfig, setTableConfig] = useState<PinoutTableConfig>(
    question?.table_config ?? DEFAULT_TABLE_CONFIG
  )
  const [options, setOptions] = useState<McqOption[]>(
    question?.options?.length ? question.options : DEFAULT_MCQ_OPTIONS
  )
  const [allowOther, setAllowOther] = useState(question?.allow_other ?? false)
  const [isOtherCorrect, setIsOtherCorrect] = useState(question?.is_other_correct ?? false)
  const [explanation, setExplanation] = useState(question?.explanation ?? "")
  const [explanationImageUrl, setExplanationImageUrl] = useState(
    question?.explanation_image_url ?? ""
  )
  const [hasExplanationTable, setHasExplanationTable] = useState(
    Boolean(question?.explanation_table)
  )
  const [explanationTable, setExplanationTable] = useState<PinoutTableConfig>(
    question?.explanation_table ?? DEFAULT_TABLE_CONFIG
  )
  const [uploadingQuestionImg, setUploadingQuestionImg] = useState(false)
  const [uploadingExplanationImg, setUploadingExplanationImg] = useState(false)
  const [error, setError] = useState("")

  const handleUploadImage = async (file: File, target: "question" | "explanation") => {
    try {
      if (target === "question") setUploadingQuestionImg(true)
      else setUploadingExplanationImg(true)
      const res = await uploadPreQuizImageApi(file)
      if (target === "question") setImageUrl(res.url)
      else setExplanationImageUrl(res.url)
      toast.success("Image uploaded")
    } catch (e) {
      toast.error(getErrorMessage(e, "Image upload failed"))
    } finally {
      if (target === "question") setUploadingQuestionImg(false)
      else setUploadingExplanationImg(false)
    }
  }

  const saveMut = useMutation({
    mutationFn: () => {
      const payload: PreSessionQuizQuestionIn = {
        topic: topic.trim() || "General",
        question_type: questionType,
        title: title.trim(),
        prompt: prompt.trim(),
        image_url: imageUrl.trim() || null,
        options: questionType === "mcq" ? options : [],
        table_config: questionType === "pinout_table" ? tableConfig : null,
        allow_other: allowOther || isOtherCorrect,
        is_other_correct: isOtherCorrect,
        explanation: explanation.trim() || null,
        explanation_image_url: explanationImageUrl.trim() || null,
        explanation_table: hasExplanationTable ? explanationTable : null,
        is_active: true,
      }
      return question
        ? updatePreQuizQuestionApi(question.id, payload)
        : createPreQuizQuestionApi(payload)
    },
    onSuccess: () => {
      toast.success(question ? "Question updated" : "Question created")
      onSaved()
    },
    onError: (e) => setError(getErrorMessage(e, "Failed to save question")),
  })

  return (
    <Modal
      title={question ? `Edit: ${question.title}` : "Create Pre-Session Quiz Question"}
      onClose={onClose}
      maxWidth="sm:max-w-3xl max-w-3xl"
    >
      <div className="flex flex-col gap-4">
        {/* Question Type & Topic */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Question Format">
            <div className="grid grid-cols-3 gap-1 p-1 bg-muted rounded-xl border border-border">
              <button
                type="button"
                onClick={() => setQuestionType("pinout_table")}
                className={cn(
                  "h-8 rounded-lg text-xs font-semibold flex items-center justify-center transition-colors cursor-pointer",
                  questionType === "pinout_table"
                    ? "bg-card text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                Connector Table
              </button>
              <button
                type="button"
                onClick={() => setQuestionType("mcq")}
                className={cn(
                  "h-8 rounded-lg text-xs font-semibold flex items-center justify-center transition-colors cursor-pointer",
                  questionType === "mcq"
                    ? "bg-card text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                Multiple Choice
              </button>
              <button
                type="button"
                onClick={() => setQuestionType("written")}
                className={cn(
                  "h-8 rounded-lg text-xs font-semibold flex items-center justify-center transition-colors cursor-pointer",
                  questionType === "written"
                    ? "bg-card text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                Written Scenario
              </button>
            </div>
          </Field>

          <Field label="Subsystem / Topic (e.g. CDHS, ADCS/APC, Addressing, Scenarios)">
            <div className="flex gap-1.5">
              <input
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                list="pre-quiz-topics-list"
                placeholder="CDHS, ADCS/APC, EPS, Addressing, Scenarios..."
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
              />
              <datalist id="pre-quiz-topics-list">
                {Array.from(new Set(["CDHS", "ADCS/APC", "EPS", "Addressing", "Scenarios", ...existingTopics])).map(
                  (t) => (
                    <option key={t} value={t} />
                  )
                )}
              </datalist>
            </div>
          </Field>
        </div>

        <Field label="Question Title">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. CDHS — Connector J6 (MicroSD SPI Interface)"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
          />
        </Field>

        <Field label="Instructions / Prompt">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={2}
            placeholder="Instructions shown to the instructor..."
            className="w-full p-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
          />
        </Field>

        {/* Question Image / Diagram Uploader */}
        <ImageUploaderBox
          label="Question Image / Component Reference Diagram (optional)"
          imageUrl={imageUrl}
          uploading={uploadingQuestionImg}
          onChangeUrl={setImageUrl}
          onUploadFile={(f) => void handleUploadImage(f, "question")}
        />

        {/* Format Specific Config */}
        {questionType === "pinout_table" && (
          <div className="flex flex-col gap-2 p-3.5 rounded-2xl border border-primary/25 bg-primary/5">
            <div>
              <p className="text-xs font-bold text-foreground">Interactive Connector Pinout Table Builder</p>
              <p className="text-[11px] text-muted-foreground">
                Type pin names into each cell and toggle On/Off on the cells that should be bridged by a jumper.
              </p>
            </div>
            <ConnectorTableWidget config={tableConfig} mode="builder" onChangeConfig={setTableConfig} />
          </div>
        )}

        {questionType === "mcq" && (
          <div className="flex flex-col gap-2 p-3.5 rounded-2xl border border-border bg-muted/20">
            <p className="text-xs font-bold text-foreground">Multiple Choice Options</p>
            {options.map((opt, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={opt.is_correct}
                  onChange={(e) =>
                    setOptions(
                      options.map((o, i) => (i === idx ? { ...o, is_correct: e.target.checked } : o))
                    )
                  }
                  className="rounded border-border text-primary focus:ring-primary size-4 cursor-pointer"
                  title="Mark as correct option"
                />
                <input
                  value={opt.text}
                  onChange={(e) =>
                    setOptions(options.map((o, i) => (i === idx ? { ...o, text: e.target.value } : o)))
                  }
                  placeholder={`Option ${idx + 1}`}
                  className="flex-1 h-9 px-3 border border-border bg-card text-foreground rounded-xl text-xs sm:text-sm focus:outline-none focus:border-primary"
                />
                {options.length > 2 && (
                  <button
                    type="button"
                    onClick={() => setOptions(options.filter((_, i) => i !== idx))}
                    className="px-2 py-1 text-xs text-muted-foreground hover:text-red-500 cursor-pointer"
                  >
                    Remove
                  </button>
                )}
              </div>
            ))}
            <button
              type="button"
              onClick={() => setOptions([...options, { text: "", is_correct: false }])}
              className="self-start inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-semibold text-primary bg-primary/10 hover:bg-primary/15 cursor-pointer"
            >
              + Add Option
            </button>
          </div>
        )}

        {questionType === "written" && (
          <div className="p-3.5 rounded-2xl border border-border bg-muted/20 flex flex-col gap-2">
            <p className="text-xs font-bold text-foreground">Written Scenario Format</p>
            <p className="text-xs text-muted-foreground">
              Instructors will see a multi-line text input to write their technical troubleshooting or architectural diagnosis.
              Their response is recorded for Operations review and will be auto-credited to allow pipeline progression.
            </p>
            <div className="h-20 rounded-xl border border-dashed border-border bg-card/60 p-3 text-xs text-muted-foreground italic select-none">
              [Instructor Textarea Response Box]
            </div>
          </div>
        )}

        {/* "Other" / Tricky Question Settings */}
        {questionType !== "written" && (
          <div className="p-3.5 rounded-2xl border border-amber-500/30 bg-amber-500/5 flex flex-col gap-2.5">
            <label className="flex items-start gap-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={allowOther || isOtherCorrect}
                onChange={(e) => setAllowOther(e.target.checked)}
                className="mt-0.5 rounded border-border text-primary focus:ring-primary"
              />
              <div>
                <p className="text-xs font-bold text-foreground">
                  Include &ldquo;Other (Write Explanation)&rdquo; Option
                </p>
                <p className="text-[11px] text-muted-foreground">
                  Allows the instructor to flag a pinout error or write a custom explanation.
                </p>
              </div>
            </label>

            <label className="flex items-start gap-2.5 cursor-pointer select-none pl-6 border-t border-amber-500/20 pt-2">
              <input
                type="checkbox"
                checked={isOtherCorrect}
                onChange={(e) => {
                  setIsOtherCorrect(e.target.checked)
                  if (e.target.checked) setAllowOther(true)
                }}
                className="mt-0.5 rounded border-border text-amber-600 focus:ring-amber-500"
              />
              <div>
                <p className="text-xs font-bold text-amber-700 dark:text-amber-300">
                  Tricky Datasheet Error Question (&ldquo;Other&rdquo; is the expected choice)
                </p>
                <p className="text-[11px] text-muted-foreground">
                  Enable this when the question table intentionally contains a wrong pinout (like CDHS Connector J6).
                  Selecting &ldquo;Other&rdquo; and writing a non-empty explanation will auto-credit as 100% Correct while flagging for Ops review.
                </p>
              </div>
            </label>
          </div>
        )}

        {/* Post-Submission Explanation Section */}
        <div className="p-3.5 rounded-2xl border border-border bg-card flex flex-col gap-3">
          <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
            Post-Submission Answer Review &amp; Ops Rubric
          </p>

          <Field label="Explanation &amp; Grading Guidelines">
            <textarea
              value={explanation}
              onChange={(e) => setExplanation(e.target.value)}
              rows={2}
              placeholder="Explain why these pins are selected or key points for Operations to verify..."
              className="w-full p-3 border border-border bg-background text-foreground rounded-xl text-xs sm:text-sm focus:outline-none focus:border-primary"
            />
          </Field>

          <ImageUploaderBox
            label="Explanation Image / Diagram (optional)"
            imageUrl={explanationImageUrl}
            uploading={uploadingExplanationImg}
            onChangeUrl={setExplanationImageUrl}
            onUploadFile={(f) => void handleUploadImage(f, "explanation")}
          />

          <label className="flex items-center gap-2 text-xs font-semibold text-foreground cursor-pointer select-none pt-1">
            <input
              type="checkbox"
              checked={hasExplanationTable}
              onChange={(e) => setHasExplanationTable(e.target.checked)}
              className="rounded border-border text-primary focus:ring-primary"
            />
            <span>Include a Corrected / Reference Connector Table in the Explanation</span>
          </label>

          {hasExplanationTable && (
            <div className="pt-1">
              <ConnectorTableWidget config={explanationTable} mode="builder" onChangeConfig={setExplanationTable} />
            </div>
          )}
        </div>

        {error && <p className="text-xs text-red-500 bg-red-500/10 p-2.5 rounded-xl">{error}</p>}

        <ModalActions
          onCancel={onClose}
          onConfirm={() => saveMut.mutate()}
          loading={saveMut.isPending}
          disabled={!title.trim() || !prompt.trim()}
          label={question ? "Save Changes" : "Create Question"}
        />
      </div>
    </Modal>
  )
}

function ImageUploaderBox({
  label,
  imageUrl,
  uploading,
  onChangeUrl,
  onUploadFile,
}: {
  label: string
  imageUrl: string
  uploading: boolean
  onChangeUrl: (url: string) => void
  onUploadFile: (file: File) => void
}) {
  return (
    <div className="flex flex-col gap-2 p-3 rounded-xl bg-muted/20 border border-border/70">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-foreground">{label}</span>
        {imageUrl && (
          <button
            type="button"
            onClick={() => onChangeUrl("")}
            className="text-[11px] text-red-500 hover:underline cursor-pointer"
          >
            Remove image
          </button>
        )}
      </div>

      {imageUrl && (
        <div className="max-h-44 overflow-hidden rounded-lg border border-border bg-card/70 flex items-center justify-center p-2">
          <img
            src={resolveQuizImageUrl(imageUrl)}
            alt="Preview"
            className="max-h-40 max-w-full object-contain rounded"
          />
        </div>
      )}

      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
        <label className="inline-flex items-center justify-center h-8 px-3 rounded-lg border border-primary/40 bg-primary/5 hover:bg-primary/10 text-xs font-semibold text-primary cursor-pointer transition-colors shrink-0">
          <span>{uploading ? "Uploading…" : imageUrl ? "Replace image" : "Upload image"}</span>
          <input
            type="file"
            accept="image/*"
            disabled={uploading}
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) {
                onUploadFile(f)
                e.target.value = ""
              }
            }}
          />
        </label>
        <input
          value={imageUrl}
          onChange={(e) => onChangeUrl(e.target.value)}
          placeholder="Or paste image URL / /files/... path"
          className="flex-1 h-8 px-2.5 border border-border bg-card text-foreground rounded-lg text-xs focus:outline-none focus:border-primary"
        />
      </div>
    </div>
  )
}

/* ── Tab 2: Quiz Presets & Pipeline Templates ──────────────────────────────── */

function PresetsTab() {
  const qc = useQueryClient()
  const toast = useToast()
  const [editingPreset, setEditingPreset] = useState<PreSessionQuizPreset | null>(null)
  const [creating, setCreating] = useState(false)
  const [deletingPreset, setDeletingPreset] = useState<PreSessionQuizPreset | null>(null)
  const [previewPreset, setPreviewPreset] = useState<PreSessionQuizPreset | null>(null)

  const { data: presets = [], isLoading } = useQuery({
    queryKey: ["pre-quiz-presets"],
    queryFn: () => listPreQuizPresetsApi(false),
  })

  const { data: allQuestions = [] } = useQuery({
    queryKey: ["pre-quiz-questions"],
    queryFn: () => listPreQuizQuestionsApi({ active_only: false }),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deletePreQuizPresetApi(id),
    onSuccess: () => {
      toast.success("Preset deleted")
      setDeletingPreset(null)
      qc.invalidateQueries({ queryKey: ["pre-quiz-presets"] })
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not delete preset")),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <p className="text-xs sm:text-sm text-muted-foreground">
          Assemble multi-phase readiness pipelines with datasheets, matching buckets, and question phases that gate cohort delivery.
        </p>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="flex items-center h-9 px-4 bg-primary text-primary-foreground rounded-xl text-xs sm:text-sm font-semibold hover:opacity-90 transition-opacity cursor-pointer shrink-0 shadow-xs gap-1.5"
        >
          <Plus size={15} /> New Pipeline Preset
        </button>
      </div>

      {presets.length === 0 ? (
        <EmptyState
          title="No quiz presets yet"
          hint="Create a preset to configure the 5-phase hardware readiness pipeline."
        />
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {presets.map((preset) => (
            <div
              key={preset.id}
              className="p-4 rounded-2xl border border-border bg-card flex flex-col gap-3 shadow-xs"
            >
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-base font-bold text-foreground">{preset.name}</h3>
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-primary/10 text-primary border border-primary/20">
                      {preset.phases?.length || 0} Phase{preset.phases?.length === 1 ? "" : "s"}
                    </span>
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-muted text-foreground border border-border">
                      {preset.questions?.length || 0} Questions
                    </span>
                    {preset.reference_attachments?.length > 0 && (
                      <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-muted text-foreground border border-border">
                        {preset.reference_attachments.length} Datasheets
                      </span>
                    )}
                  </div>
                  {preset.description && (
                    <p className="text-xs sm:text-sm text-muted-foreground">{preset.description}</p>
                  )}
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  <button
                    type="button"
                    onClick={() => setPreviewPreset(preset)}
                    className="flex items-center h-8 px-3 rounded-lg border border-primary/40 bg-primary/10 hover:bg-primary/20 text-xs font-semibold text-primary transition-colors cursor-pointer"
                  >
                    Preview
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditingPreset(preset)}
                    className="flex items-center h-8 px-3 rounded-lg border border-border bg-background hover:bg-muted text-xs font-medium text-foreground transition-colors cursor-pointer"
                  >
                    Configure Pipeline
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeletingPreset(preset)}
                    className="h-8 px-2.5 rounded-lg border border-border bg-background hover:bg-red-500/10 text-xs font-medium text-muted-foreground hover:text-red-500 transition-colors cursor-pointer"
                    title="Delete preset"
                  >
                    Delete
                  </button>
                </div>
              </div>

              {/* Pipeline Phases Badges */}
              {preset.phases && preset.phases.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 pt-1">
                  <span className="text-xs font-semibold text-muted-foreground mr-1">Pipeline Phases:</span>
                  {preset.phases.map((ph, idx) => (
                    <span
                      key={ph.id || idx}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-muted/60 text-foreground border border-border"
                    >
                      <span className="text-[10px] font-bold text-primary">{idx + 1}.</span>
                      <span>{ph.title}</span>
                      {ph.cooldown_seconds > 0 && (
                        <span className="text-[10px] text-amber-600 dark:text-amber-400 font-semibold">
                          ({Math.round(ph.cooldown_seconds / 60)}m cd)
                        </span>
                      )}
                    </span>
                  ))}
                </div>
              )}

              {/* Datasheets list */}
              {preset.reference_attachments?.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
                  <span className="text-xs font-medium text-muted-foreground">Datasheets:</span>
                  {preset.reference_attachments.map((att, idx) => (
                    <a
                      key={idx}
                      href={ensureAbsoluteUrl(att.url)}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium bg-muted text-foreground border border-border hover:border-primary/40"
                    >
                      <FileText size={11} className="text-primary" />
                      <span>{att.title}</span>
                      {att.subsystem_tag && (
                        <span className="text-[9px] px-1 py-0.2 rounded bg-background font-bold text-muted-foreground">
                          {att.subsystem_tag}
                        </span>
                      )}
                    </a>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {(creating || editingPreset) && (
        <PresetBuilderModal
          preset={editingPreset}
          allQuestions={allQuestions}
          onClose={() => {
            setCreating(false)
            setEditingPreset(null)
          }}
          onSaved={() => {
            setCreating(false)
            setEditingPreset(null)
            qc.invalidateQueries({ queryKey: ["pre-quiz-presets"] })
          }}
        />
      )}

      {deletingPreset && (
        <ConfirmDialog
          title="Delete Quiz Preset"
          description={`Are you sure you want to delete "${deletingPreset.name}"?`}
          confirmLabel="Delete"
          destructive
          pending={deleteMut.isPending}
          onConfirm={() => deleteMut.mutate(deletingPreset.id)}
          onCancel={() => setDeletingPreset(null)}
        />
      )}

      {previewPreset && (
        <SessionPreQuizModal
          open={Boolean(previewPreset)}
          onClose={() => setPreviewPreset(null)}
          isPreview
          quizStatus={{
            has_quiz: true,
            assignment_level: "preview",
            preset: previewPreset,
            my_attempt: null,
            trials: [],
            all_attempts: [],
          }}
        />
      )}
    </div>
  )
}

/* ── Upgraded Multi-Phase Pipeline & Datasheet Preset Builder Modal ─────────── */

function PresetBuilderModal({
  preset,
  allQuestions,
  onClose,
  onSaved,
}: {
  preset: PreSessionQuizPreset | null
  allQuestions: PreSessionQuizQuestion[]
  onClose: () => void
  onSaved: () => void
}) {
  const toast = useToast()
  const [modalTab, setModalTab] = useState<"phases" | "datasheets" | "settings">("phases")
  const [name, setName] = useState(preset?.name ?? "")
  const [description, setDescription] = useState(preset?.description ?? "")
  const [references, setReferences] = useState<ReferenceAttachment[]>(
    preset?.reference_attachments ?? []
  )
  const [phases, setPhases] = useState<QuizPipelinePhase[]>(preset?.phases ?? [])
  const [expandedPhaseIndex, setExpandedPhaseIndex] = useState<number | null>(0)

  // Datasheet upload state
  const [newDocTitle, setNewDocTitle] = useState("")
  const [newDocUrl, setNewDocUrl] = useState("")
  const [newDocType, setNewDocType] = useState<"datasheet" | "user_guide">("datasheet")
  const [newDocSubsystem, setNewDocSubsystem] = useState("CDHS")
  const [uploadingPdf, setUploadingPdf] = useState(false)
  const [error, setError] = useState("")

  // Quick seed standard 5-phase pipeline
  const quickSeedStandardPipeline = () => {
    const standardDatasheets: ReferenceAttachment[] = [
      {
        id: "ds-esp32",
        title: "ESP32 Microcontroller Data Sheet",
        url: "/files/datasheets/esp32_datasheet.pdf",
        doc_type: "datasheet",
        subsystem_tag: "CDHS",
        is_file: true,
      },
      {
        id: "ds-microsd",
        title: "MicroSD Card Interface User Guide",
        url: "/files/datasheets/microsd_user_guide.pdf",
        doc_type: "user_guide",
        subsystem_tag: "CDHS",
        is_file: true,
      },
      {
        id: "ds-tmp102",
        title: "TMP102 Temperature Sensor Data Sheet",
        url: "/files/datasheets/tmp102_datasheet.pdf",
        doc_type: "datasheet",
        subsystem_tag: "CDHS",
        is_file: true,
      },
      {
        id: "ds-bmp280",
        title: "BMP280 Barometric Pressure & Temp Sensor Data Sheet",
        url: "/files/datasheets/bmp280_datasheet.pdf",
        doc_type: "datasheet",
        subsystem_tag: "CDHS",
        is_file: true,
      },
      {
        id: "ds-mpu6050",
        title: "MPU6050 6-Axis IMU Sensor Data Sheet",
        url: "/files/datasheets/mpu6050_datasheet.pdf",
        doc_type: "datasheet",
        subsystem_tag: "ADCS/APC",
        is_file: true,
      },
      {
        id: "ds-hmc5883l",
        title: "HMC5883L 3-Axis Magnetometer Data Sheet",
        url: "/files/datasheets/hmc5883l_datasheet.pdf",
        doc_type: "datasheet",
        subsystem_tag: "ADCS/APC",
        is_file: true,
      },
      {
        id: "ds-ina219",
        title: "INA219 DC Current / Power Sensor Data Sheet",
        url: "/files/datasheets/ina219_datasheet.pdf",
        doc_type: "datasheet",
        subsystem_tag: "EPS",
        is_file: true,
      },
      {
        id: "ds-tp4056",
        title: "TP4056 Lithium Battery Charging Module Guide",
        url: "/files/datasheets/tp4056_guide.pdf",
        doc_type: "user_guide",
        subsystem_tag: "EPS",
        is_file: true,
      },
      {
        id: "ds-solar",
        title: "Solar Panel Regulator & Boost Converter Module Guide",
        url: "/files/datasheets/solar_regulator_guide.pdf",
        doc_type: "user_guide",
        subsystem_tag: "EPS",
        is_file: true,
      },
      {
        id: "ds-cdhs-bus",
        title: "CDHS Main Bus Connector Pinout Guide",
        url: "/files/datasheets/cdhs_connector_pinout_guide.pdf",
        doc_type: "user_guide",
        subsystem_tag: "CDHS",
        is_file: true,
      },
      {
        id: "ds-i2c-bus",
        title: "I2C & UART Bus Wiring Reference Guide",
        url: "/files/datasheets/i2c_uart_bus_wiring.pdf",
        doc_type: "user_guide",
        subsystem_tag: "CDHS",
        is_file: true,
      },
      {
        id: "ds-payload",
        title: "Payload Subsystem Integration Guide",
        url: "/files/datasheets/payload_integration_guide.pdf",
        doc_type: "user_guide",
        subsystem_tag: "ADCS/APC",
        is_file: true,
      },
    ]

    const nextDatasheets = references.length > 0 ? references : standardDatasheets
    setReferences(nextDatasheets)

    const pinoutQIds = allQuestions
      .filter((q) => q.question_type === "pinout_table" || q.topic.toLowerCase().includes("cdhs"))
      .map((q) => q.id)
    const addressQIds = allQuestions
      .filter(
        (q) =>
          q.topic.toLowerCase().includes("address") ||
          q.title.toLowerCase().includes("address") ||
          q.prompt.toLowerCase().includes("address")
      )
      .map((q) => q.id)
    const scenarioQIds = allQuestions
      .filter(
        (q) =>
          q.topic.toLowerCase().includes("scenario") ||
          q.question_type === "written" ||
          q.title.toLowerCase().includes("scenario") ||
          q.prompt.toLowerCase().includes("scenario")
      )
      .map((q) => q.id)

    const standardPhases: QuizPipelinePhase[] = [
      {
        id: `phase-${Date.now()}-1`,
        phase_type: "explore_datasheets",
        title: "Explore Data Sheets",
        subtitle: "Review module datasheets and user guides",
        instructions: [
          "View the first page of each data sheet.",
          "Explore all module datasheets and user guides before moving to matching.",
        ],
        pass_percentage: 100,
        cooldown_seconds: 0,
        show_correct_on_fail: false,
        show_explanation_on_fail: false,
        show_bucket_target_counts: true,
        allow_datasheet_lookup: true,
        question_ids: [],
      },
      {
        id: `phase-${Date.now()}-2`,
        phase_type: "subsystem_matching",
        title: "Match Modules to Subsystems",
        subtitle: "Drag and drop modules into their subsystem",
        instructions: [
          "Assign every module datasheet to its correct subsystem.",
          "Refer back to the Phase 1 datasheets if you are unsure.",
        ],
        pass_percentage: 100,
        cooldown_seconds: 900, // 15 mins
        show_correct_on_fail: false,
        show_explanation_on_fail: false,
        show_bucket_target_counts: true,
        allow_datasheet_lookup: true,
        question_ids: [],
        matching_config: {
          buckets: [
            { id: "CDHS", label: "CDHS", subtitle: "Command & Data Handling System", color: "purple" },
            { id: "EPS", label: "EPS", subtitle: "Electrical Power System", color: "emerald" },
            { id: "ADCS/APC", label: "ADCS/APC", subtitle: "Attitude Determination & Control System", color: "blue" },
          ],
          items: nextDatasheets.map((ds) => ({
            datasheet_id: ds.id || ds.title,
            correct_bucket_id: ds.subsystem_tag || "CDHS",
            explanation: `${ds.title} belongs to ${ds.subsystem_tag || "CDHS"}.`,
          })),
        },
      },
      {
        id: `phase-${Date.now()}-3`,
        phase_type: "quiz",
        title: "CDHS & Module Pinout Quiz",
        subtitle: "Connector jumper pinouts and header tables",
        instructions: [
          "Select the required jumper header connections for each hardware connector.",
          "If a datasheet contains an error, use the Other option to explain.",
        ],
        pass_percentage: 100,
        cooldown_seconds: 60, // 1 min
        show_correct_on_fail: false,
        show_explanation_on_fail: false,
        show_bucket_target_counts: false,
        allow_datasheet_lookup: true,
        question_ids: pinoutQIds.length > 0 ? pinoutQIds : allQuestions.slice(0, 3).map((q) => q.id),
      },
      {
        id: `phase-${Date.now()}-4`,
        phase_type: "quiz",
        title: "Addressing & Bus Protocol Quiz",
        subtitle: "I2C/UART device addressing and address pins",
        instructions: [
          "Answer hardware bus addressing questions.",
          "Calculate resulting slave addresses from hardware pin state changes.",
        ],
        pass_percentage: 100,
        cooldown_seconds: 60, // 1 min
        show_correct_on_fail: false,
        show_explanation_on_fail: false,
        show_bucket_target_counts: false,
        allow_datasheet_lookup: true,
        question_ids: addressQIds.length > 0 ? addressQIds : allQuestions.slice(3, 7).map((q) => q.id),
      },
      {
        id: `phase-${Date.now()}-5`,
        phase_type: "quiz",
        title: "Scenario & Troubleshooting Quiz",
        subtitle: "Hardware scenarios and open-ended diagnosis",
        instructions: [
          "Analyze the troubleshooting scenarios.",
          "Provide thorough diagnostic steps for hardware delivery readiness.",
        ],
        pass_percentage: 100,
        cooldown_seconds: 60, // 1 min
        show_correct_on_fail: false,
        show_explanation_on_fail: false,
        show_bucket_target_counts: false,
        allow_datasheet_lookup: true,
        question_ids: scenarioQIds.length > 0 ? scenarioQIds : allQuestions.slice(7).map((q) => q.id),
      },
    ]

    setPhases(standardPhases)
    if (!name.trim()) setName("Standard SpacePoint Hardware Delivery Pipeline")
    if (!description.trim()) {
      setDescription(
        "Standard 5-phase cohort readiness pipeline: Datasheet exploration, Subsystem matching (15m cooldown), Pinout tables, I2C/UART Addressing, and Troubleshooting Scenarios."
      )
    }
    toast.success("Standard 5-Phase Pipeline loaded!")
  }

  const handleUploadPdf = async (file: File) => {
    try {
      setUploadingPdf(true)
      const res = await uploadPreQuizDatasheetApi(file)
      const title = newDocTitle.trim() || file.name.replace(/\.pdf$/i, "")
      const newItem: ReferenceAttachment = {
        id: `ds-${Date.now()}`,
        title,
        url: res.url,
        doc_type: newDocType,
        subsystem_tag: newDocSubsystem,
        is_file: true,
      }
      setReferences([...references, newItem])
      setNewDocTitle("")
      setNewDocUrl("")
      toast.success(`Uploaded ${newItem.title}`)
    } catch (e) {
      toast.error(getErrorMessage(e, "PDF upload failed"))
    } finally {
      setUploadingPdf(false)
    }
  }

  const addManualDatasheet = () => {
    if (!newDocUrl.trim() && !newDocTitle.trim()) return
    const newItem: ReferenceAttachment = {
      id: `ds-${Date.now()}`,
      title: newDocTitle.trim() || newDocUrl.trim(),
      url: newDocUrl.trim(),
      doc_type: newDocType,
      subsystem_tag: newDocSubsystem,
      is_file: newDocUrl.toLowerCase().endsWith(".pdf"),
    }
    setReferences([...references, newItem])
    setNewDocTitle("")
    setNewDocUrl("")
  }

  const addPhase = (type: "explore_datasheets" | "subsystem_matching" | "quiz") => {
    const newPhase: QuizPipelinePhase = {
      id: `phase-${Date.now()}`,
      phase_type: type,
      title:
        type === "explore_datasheets"
          ? "Explore Data Sheets"
          : type === "subsystem_matching"
          ? "Match Modules to Subsystems"
          : "Question Bank Quiz",
      subtitle: "",
      instructions: [],
      pass_percentage: 100,
      cooldown_seconds: type === "subsystem_matching" ? 900 : type === "quiz" ? 60 : 0,
      show_correct_on_fail: false,
      show_explanation_on_fail: false,
      show_bucket_target_counts: true,
      allow_datasheet_lookup: true,
      question_ids: [],
      matching_config:
        type === "subsystem_matching"
          ? {
              buckets: [
                { id: "CDHS", label: "CDHS", subtitle: "Command & Data Handling System", color: "purple" },
                { id: "EPS", label: "EPS", subtitle: "Electrical Power System", color: "emerald" },
                { id: "ADCS/APC", label: "ADCS/APC", subtitle: "Attitude Determination & Control System", color: "blue" },
              ],
              items: references.map((r) => ({
                datasheet_id: r.id || r.title,
                correct_bucket_id: r.subsystem_tag || "CDHS",
              })),
            }
          : undefined,
    }
    setPhases([...phases, newPhase])
    setExpandedPhaseIndex(phases.length)
  }

  const movePhase = (idx: number, dir: -1 | 1) => {
    const target = idx + dir
    if (target < 0 || target >= phases.length) return
    const next = [...phases]
    const [moved] = next.splice(idx, 1)
    next.splice(target, 0, moved)
    setPhases(next)
    setExpandedPhaseIndex(target)
  }

  const removePhase = (idx: number) => {
    setPhases(phases.filter((_, i) => i !== idx))
    setExpandedPhaseIndex(null)
  }

  const saveMut = useMutation({
    mutationFn: () => {
      // Collect question IDs across all quiz phases
      const allQuizQIds = Array.from(
        new Set(
          phases
            .filter((p) => p.phase_type === "quiz")
            .flatMap((p) => p.question_ids || [])
        )
      )

      const payload: PreSessionQuizPresetIn = {
        name: name.trim(),
        description: description.trim() || null,
        question_ids: allQuizQIds.length > 0 ? allQuizQIds : preset?.question_ids || [],
        reference_attachments: references,
        phases: phases,
        is_active: true,
      }
      return preset ? updatePreQuizPresetApi(preset.id, payload) : createPreQuizPresetApi(payload)
    },
    onSuccess: () => {
      toast.success(preset ? "Preset updated" : "Preset created")
      onSaved()
    },
    onError: (e) => setError(getErrorMessage(e, "Failed to save preset")),
  })

  return (
    <Modal
      title={preset ? `Configure Pipeline Preset: ${preset.name}` : "New Readiness Pipeline Preset"}
      onClose={onClose}
      maxWidth="sm:max-w-4xl max-w-4xl"
    >
      <div className="flex flex-col gap-4">
        {/* Name & Description Bar */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Pipeline Preset Name">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Standard SpacePoint Hardware Delivery Pipeline"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
            />
          </Field>
          <Field label="Description (optional)">
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Summary of this readiness pipeline..."
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
            />
          </Field>
        </div>

        {/* Modal Tabs */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-2">
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setModalTab("phases")}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer flex items-center gap-1.5",
                modalTab === "phases"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:text-foreground"
              )}
            >
              <Layers size={13} />
              Pipeline Phases ({phases.length})
            </button>
            <button
              type="button"
              onClick={() => setModalTab("datasheets")}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer flex items-center gap-1.5",
                modalTab === "datasheets"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:text-foreground"
              )}
            >
              <FileText size={13} />
              Datasheet Catalog ({references.length})
            </button>
          </div>

          <button
            type="button"
            onClick={quickSeedStandardPipeline}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-primary/40 bg-primary/10 hover:bg-primary/20 text-xs font-bold text-primary transition-colors cursor-pointer"
          >
            <Sparkles size={13} />
            Quick-Seed Standard 5-Phase Pipeline
          </button>
        </div>

        {/* ── TAB 1: PHASES EDITOR ─────────────────────────────────────────── */}
        {modalTab === "phases" && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <span className="text-xs text-muted-foreground">
                Define the ordered sequence of phases instructors must complete before session delivery.
              </span>
              <div className="flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => addPhase("explore_datasheets")}
                  className="px-2.5 py-1 rounded-lg border border-border bg-card text-[11px] font-semibold text-foreground hover:bg-muted cursor-pointer"
                >
                  + Explore Datasheets
                </button>
                <button
                  type="button"
                  onClick={() => addPhase("subsystem_matching")}
                  className="px-2.5 py-1 rounded-lg border border-border bg-card text-[11px] font-semibold text-foreground hover:bg-muted cursor-pointer"
                >
                  + Subsystem Matching
                </button>
                <button
                  type="button"
                  onClick={() => addPhase("quiz")}
                  className="px-2.5 py-1 rounded-lg border border-border bg-card text-[11px] font-semibold text-foreground hover:bg-muted cursor-pointer"
                >
                  + Question Quiz
                </button>
              </div>
            </div>

            {phases.length === 0 ? (
              <div className="p-8 text-center border border-dashed border-border rounded-2xl bg-muted/20 flex flex-col items-center gap-2">
                <p className="text-sm font-semibold text-foreground">No pipeline phases defined</p>
                <p className="text-xs text-muted-foreground max-w-md">
                  Click &ldquo;Quick-Seed Standard 5-Phase Pipeline&rdquo; above to pre-populate the full 5-step hardware pipeline, or add phases manually.
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {phases.map((ph, idx) => {
                  const isExpanded = expandedPhaseIndex === idx
                  return (
                    <div
                      key={ph.id || idx}
                      className="rounded-2xl border border-border bg-card overflow-hidden shadow-2xs"
                    >
                      {/* Phase Item Header */}
                      <div className="p-3 bg-muted/30 flex items-center justify-between gap-2">
                        <div
                          className="flex items-center gap-2 min-w-0 cursor-pointer flex-1"
                          onClick={() => setExpandedPhaseIndex(isExpanded ? null : idx)}
                        >
                          <span className="flex items-center justify-center size-6 rounded-full bg-primary/10 text-primary text-xs font-bold shrink-0">
                            {idx + 1}
                          </span>
                          <span className="font-bold text-xs sm:text-sm text-foreground truncate">
                            {ph.title || `Phase ${idx + 1}`}
                          </span>
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-muted text-foreground border border-border shrink-0">
                            {ph.phase_type === "explore_datasheets"
                              ? "Explore Datasheets"
                              : ph.phase_type === "subsystem_matching"
                              ? "Subsystem Matching"
                              : "Question Bank Quiz"}
                          </span>
                          {ph.cooldown_seconds > 0 && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 shrink-0">
                              {Math.round(ph.cooldown_seconds / 60)}m Cooldown
                            </span>
                          )}
                          {ph.phase_type === "quiz" && (
                            <span className="text-[11px] text-muted-foreground font-medium shrink-0">
                              ({ph.question_ids?.length || 0} Qs)
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            type="button"
                            onClick={() => movePhase(idx, -1)}
                            disabled={idx === 0}
                            className="p-1 rounded bg-muted/60 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
                            title="Move Up"
                          >
                            <ChevronUp size={14} />
                          </button>
                          <button
                            type="button"
                            onClick={() => movePhase(idx, 1)}
                            disabled={idx === phases.length - 1}
                            className="p-1 rounded bg-muted/60 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
                            title="Move Down"
                          >
                            <ChevronDown size={14} />
                          </button>
                          <button
                            type="button"
                            onClick={() => removePhase(idx)}
                            className="p-1 rounded bg-muted/60 text-muted-foreground hover:text-red-500 cursor-pointer"
                            title="Remove Phase"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>

                      {/* Phase Settings Expanded */}
                      {isExpanded && (
                        <div className="p-4 border-t border-border flex flex-col gap-4 bg-card">
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <Field label="Phase Title">
                              <input
                                value={ph.title}
                                onChange={(e) => {
                                  const next = [...phases]
                                  next[idx].title = e.target.value
                                  setPhases(next)
                                }}
                                className="w-full h-9 px-3 border border-border bg-background rounded-xl text-xs sm:text-sm"
                              />
                            </Field>
                            <Field label="Subtitle / Short Description">
                              <input
                                value={ph.subtitle || ""}
                                onChange={(e) => {
                                  const next = [...phases]
                                  next[idx].subtitle = e.target.value
                                  setPhases(next)
                                }}
                                className="w-full h-9 px-3 border border-border bg-background rounded-xl text-xs sm:text-sm"
                              />
                            </Field>
                          </div>

                          {/* Pass Percentage & Cooldown Inputs */}
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3 rounded-xl bg-muted/20 border border-border">
                            <Field label="Required Pass Threshold (%)">
                              <div className="flex items-center gap-2">
                                <input
                                  type="number"
                                  min={0}
                                  max={100}
                                  value={ph.pass_percentage}
                                  onChange={(e) => {
                                    const next = [...phases]
                                    next[idx].pass_percentage = Number(e.target.value) || 0
                                    setPhases(next)
                                  }}
                                  className="w-24 h-8 px-2.5 border border-border bg-background rounded-lg text-xs"
                                />
                                <span className="text-xs text-muted-foreground">
                                  % required to unlock next phase (e.g. 100)
                                </span>
                              </div>
                            </Field>

                            <Field label="Retry Cooldown Duration">
                              <div className="flex items-center gap-2">
                                <input
                                  type="number"
                                  min={0}
                                  value={Math.round(ph.cooldown_seconds / 60)}
                                  onChange={(e) => {
                                    const mins = Math.max(0, Number(e.target.value) || 0)
                                    const next = [...phases]
                                    next[idx].cooldown_seconds = mins * 60
                                    setPhases(next)
                                  }}
                                  className="w-20 h-8 px-2.5 border border-border bg-background rounded-lg text-xs"
                                />
                                <span className="text-xs text-muted-foreground">
                                  minutes lock on failed trial (e.g. 15 for Matching, 1 for Pinouts)
                                </span>
                              </div>
                            </Field>
                          </div>

                          {/* Disclosure Toggles */}
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                            <label className="flex items-center gap-2 cursor-pointer select-none">
                              <input
                                type="checkbox"
                                checked={ph.show_correct_on_fail}
                                onChange={(e) => {
                                  const next = [...phases]
                                  next[idx].show_correct_on_fail = e.target.checked
                                  setPhases(next)
                                }}
                                className="rounded border-border text-primary"
                              />
                              <span>Reveal correct/incorrect answers after failed trial</span>
                            </label>

                            <label className="flex items-center gap-2 cursor-pointer select-none">
                              <input
                                type="checkbox"
                                checked={ph.show_explanation_on_fail}
                                onChange={(e) => {
                                  const next = [...phases]
                                  next[idx].show_explanation_on_fail = e.target.checked
                                  setPhases(next)
                                }}
                                className="rounded border-border text-primary"
                              />
                              <span>Reveal explanations &amp; reference tables on failure</span>
                            </label>

                            <label className="flex items-center gap-2 cursor-pointer select-none">
                              <input
                                type="checkbox"
                                checked={ph.allow_datasheet_lookup}
                                onChange={(e) => {
                                  const next = [...phases]
                                  next[idx].allow_datasheet_lookup = e.target.checked
                                  setPhases(next)
                                }}
                                className="rounded border-border text-primary"
                              />
                              <span>Allow opening Datasheets Drawer during this phase</span>
                            </label>

                            {ph.phase_type === "subsystem_matching" && (
                              <label className="flex items-center gap-2 cursor-pointer select-none">
                                <input
                                  type="checkbox"
                                  checked={ph.show_bucket_target_counts}
                                  onChange={(e) => {
                                    const next = [...phases]
                                    next[idx].show_bucket_target_counts = e.target.checked
                                    setPhases(next)
                                  }}
                                  className="rounded border-border text-primary"
                                />
                                <span>Show target module count hint (e.g. &ldquo;0 / 5 modules&rdquo;)</span>
                              </label>
                            )}
                          </div>

                          {/* Phase Type Specific Content Editor */}
                          {ph.phase_type === "quiz" && (
                            <PhaseQuestionSelector
                              selectedQuestionIds={ph.question_ids || []}
                              allQuestions={allQuestions}
                              onChangeQuestionIds={(nextIds) => {
                                const next = [...phases]
                                next[idx].question_ids = nextIds
                                setPhases(next)
                              }}
                            />
                          )}

                          {ph.phase_type === "subsystem_matching" && (
                            <PhaseMatchingEditor
                              matchingConfig={
                                ph.matching_config ?? {
                                  buckets: [
                                    { id: "CDHS", label: "CDHS", color: "purple" },
                                    { id: "EPS", label: "EPS", color: "emerald" },
                                    { id: "ADCS/APC", label: "ADCS/APC", color: "blue" },
                                  ],
                                  items: [],
                                }
                              }
                              datasheets={references}
                              onChangeMatchingConfig={(nextCfg) => {
                                const next = [...phases]
                                next[idx].matching_config = nextCfg
                                setPhases(next)
                              }}
                            />
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {/* ── TAB 2: DATASHEET CATALOG ─────────────────────────────────────── */}
        {modalTab === "datasheets" && (
          <div className="flex flex-col gap-4">
            <div className="p-3.5 rounded-2xl border border-primary/25 bg-primary/5 flex flex-col gap-3">
              <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                <Upload size={14} className="text-primary" />
                Upload New Module Datasheet or User Guide (PDF)
              </span>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <input
                  value={newDocTitle}
                  onChange={(e) => setNewDocTitle(e.target.value)}
                  placeholder="Doc Title (e.g. TMP102 Temp Sensor Data Sheet)"
                  className="h-8 px-2.5 border border-border bg-card rounded-lg text-xs"
                />
                <select
                  value={newDocType}
                  onChange={(e) => setNewDocType(e.target.value as any)}
                  className="h-8 px-2.5 border border-border bg-card rounded-lg text-xs"
                >
                  <option value="datasheet">Data Sheet</option>
                  <option value="user_guide">User Guide</option>
                </select>
                <input
                  value={newDocSubsystem}
                  onChange={(e) => setNewDocSubsystem(e.target.value)}
                  placeholder="Subsystem Tag (CDHS, EPS, ADCS/APC...)"
                  className="h-8 px-2.5 border border-border bg-card rounded-lg text-xs"
                />
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                <label className="inline-flex items-center justify-center h-8 px-3 rounded-lg border border-primary/40 bg-primary/10 hover:bg-primary/20 text-xs font-semibold text-primary cursor-pointer transition-colors">
                  <span>{uploadingPdf ? "Uploading PDF…" : "Choose PDF File & Upload"}</span>
                  <input
                    type="file"
                    accept="application/pdf"
                    disabled={uploadingPdf}
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0]
                      if (f) {
                        void handleUploadPdf(f)
                        e.target.value = ""
                      }
                    }}
                  />
                </label>
                <span className="text-[11px] text-muted-foreground">or</span>
                <input
                  value={newDocUrl}
                  onChange={(e) => setNewDocUrl(e.target.value)}
                  placeholder="Paste URL (/files/... or https://...)"
                  className="flex-1 h-8 px-2.5 border border-border bg-card rounded-lg text-xs min-w-[200px]"
                />
                <button
                  type="button"
                  onClick={addManualDatasheet}
                  disabled={!newDocUrl.trim() && !newDocTitle.trim()}
                  className="h-8 px-3 bg-primary text-primary-foreground rounded-lg text-xs font-semibold hover:opacity-90 disabled:opacity-40 cursor-pointer"
                >
                  Add
                </button>
              </div>
            </div>

            {/* List of Datasheets */}
            <div className="flex flex-col gap-2">
              <span className="text-xs font-bold text-foreground">
                Configured Catalog ({references.length} documents)
              </span>

              {references.length === 0 ? (
                <p className="text-xs text-muted-foreground italic py-2">
                  No reference datasheets configured yet. Upload PDFs or click Quick-Seed Standard Pipeline above.
                </p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-72 overflow-y-auto p-1">
                  {references.map((r, i) => (
                    <div
                      key={i}
                      className="p-2.5 rounded-xl border border-border bg-card flex items-center justify-between gap-2 text-xs"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <FileText size={16} className="text-primary shrink-0" />
                        <div className="min-w-0">
                          <p className="font-semibold text-foreground truncate">{r.title}</p>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <span className="px-1.5 py-0.2 rounded bg-muted text-[10px] font-bold text-muted-foreground">
                              {r.doc_type === "user_guide" ? "User Guide" : "Data Sheet"}
                            </span>
                            {r.subsystem_tag && (
                              <span className="px-1.5 py-0.2 rounded bg-primary/10 text-[10px] font-bold text-primary">
                                {r.subsystem_tag}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-1 shrink-0">
                        <a
                          href={ensureAbsoluteUrl(r.url)}
                          target="_blank"
                          rel="noreferrer"
                          className="px-2 py-1 rounded bg-muted text-[11px] font-medium text-foreground hover:bg-muted/80"
                        >
                          View
                        </a>
                        <button
                          type="button"
                          onClick={() => setReferences(references.filter((_, idx) => idx !== i))}
                          className="p-1 text-muted-foreground hover:text-red-500 cursor-pointer"
                          title="Remove"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {error && <p className="text-xs text-red-500 bg-red-500/10 p-2.5 rounded-xl">{error}</p>}

        <ModalActions
          onCancel={onClose}
          onConfirm={() => saveMut.mutate()}
          loading={saveMut.isPending}
          disabled={!name.trim() || phases.length === 0}
          label={preset ? "Save Changes" : "Create Pipeline Preset"}
        />
      </div>
    </Modal>
  )
}

/* ── Phase Question Selector Helper ────────────────────────────────────────── */

function PhaseQuestionSelector({
  selectedQuestionIds,
  allQuestions,
  onChangeQuestionIds,
}: {
  selectedQuestionIds: string[]
  allQuestions: PreSessionQuizQuestion[]
  onChangeQuestionIds: (ids: string[]) => void
}) {
  const [topicFilter, setTopicFilter] = useState("all")

  const questionsMap = useMemo(() => new Map(allQuestions.map((q) => [q.id, q])), [allQuestions])

  const topics = useMemo(() => {
    const set = new Set<string>()
    allQuestions.forEach((q) => {
      if (q.topic) set.add(q.topic)
    })
    return Array.from(set).sort()
  }, [allQuestions])

  const filteredQuestions = useMemo(() => {
    if (topicFilter === "all") return allQuestions
    return allQuestions.filter((q) => q.topic === topicFilter)
  }, [allQuestions, topicFilter])

  const toggleQ = (qid: string) => {
    if (selectedQuestionIds.includes(qid)) {
      onChangeQuestionIds(selectedQuestionIds.filter((id) => id !== qid))
    } else {
      onChangeQuestionIds([...selectedQuestionIds, qid])
    }
  }

  const moveQ = (idx: number, dir: -1 | 1) => {
    const target = idx + dir
    if (target < 0 || target >= selectedQuestionIds.length) return
    const next = [...selectedQuestionIds]
    const [moved] = next.splice(idx, 1)
    next.splice(target, 0, moved)
    onChangeQuestionIds(next)
  }

  return (
    <div className="flex flex-col gap-3 p-3 rounded-xl border border-border bg-muted/10">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="text-xs font-bold text-foreground">
          Selected Questions in this Quiz Phase ({selectedQuestionIds.length})
        </span>
      </div>

      {selectedQuestionIds.length === 0 ? (
        <p className="text-xs text-muted-foreground italic">No questions selected for this phase.</p>
      ) : (
        <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto p-1.5 rounded-lg border border-border bg-card">
          {selectedQuestionIds.map((qid, idx) => {
            const q = questionsMap.get(qid)
            if (!q) return null
            return (
              <div
                key={qid}
                className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-md bg-muted/40 border border-border text-xs"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-bold text-primary">{idx + 1}.</span>
                  <span className="px-1.5 py-0.2 rounded bg-background text-[10px] font-semibold">{q.topic}</span>
                  <span className="truncate font-medium">{q.title}</span>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    type="button"
                    onClick={() => moveQ(idx, -1)}
                    disabled={idx === 0}
                    className="p-1 rounded hover:bg-muted text-muted-foreground disabled:opacity-30 cursor-pointer"
                  >
                    <ChevronUp size={12} />
                  </button>
                  <button
                    type="button"
                    onClick={() => moveQ(idx, 1)}
                    disabled={idx === selectedQuestionIds.length - 1}
                    className="p-1 rounded hover:bg-muted text-muted-foreground disabled:opacity-30 cursor-pointer"
                  >
                    <ChevronDown size={12} />
                  </button>
                  <button
                    type="button"
                    onClick={() => toggleQ(qid)}
                    className="p-1 text-muted-foreground hover:text-red-500 cursor-pointer"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Question Bank Picker Filter */}
      <div className="flex flex-col gap-1.5 pt-1">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[11px] font-semibold text-muted-foreground">Pick from Bank:</span>
          <button
            type="button"
            onClick={() => setTopicFilter("all")}
            className={cn(
              "px-2 py-0.5 rounded text-[10px] font-semibold cursor-pointer",
              topicFilter === "all" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
            )}
          >
            All
          </button>
          {topics.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTopicFilter(t)}
              className={cn(
                "px-2 py-0.5 rounded text-[10px] font-semibold cursor-pointer",
                topicFilter === t ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
              )}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-44 overflow-y-auto p-1 rounded-lg border border-border bg-card">
          {filteredQuestions.map((q) => {
            const isSelected = selectedQuestionIds.includes(q.id)
            return (
              <label
                key={q.id}
                className={cn(
                  "flex items-center gap-2 p-1.5 rounded-md border text-xs cursor-pointer transition-colors",
                  isSelected ? "bg-primary/10 border-primary/30" : "bg-background border-border hover:bg-muted/40"
                )}
              >
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => toggleQ(q.id)}
                  className="rounded border-border text-primary"
                />
                <span className="truncate flex-1 font-medium">{q.title}</span>
                <span className="text-[10px] text-muted-foreground">{q.topic}</span>
              </label>
            )
          })}
        </div>
      </div>
    </div>
  )
}

/* ── Phase Matching Editor Helper ─────────────────────────────────────────── */

function PhaseMatchingEditor({
  matchingConfig,
  datasheets,
  onChangeMatchingConfig,
}: {
  matchingConfig: MatchingPhaseConfig
  datasheets: ReferenceAttachment[]
  onChangeMatchingConfig: (cfg: MatchingPhaseConfig) => void
}) {
  const buckets = matchingConfig.buckets || []
  const items = matchingConfig.items || []

  const updateItemTarget = (datasheetId: string, bucketId: string) => {
    const existing = items.find((it) => it.datasheet_id === datasheetId)
    let nextItems: MatchingItemRule[]
    if (existing) {
      nextItems = items.map((it) =>
        it.datasheet_id === datasheetId ? { ...it, correct_bucket_id: bucketId } : it
      )
    } else {
      nextItems = [...items, { datasheet_id: datasheetId, correct_bucket_id: bucketId }]
    }
    onChangeMatchingConfig({ ...matchingConfig, items: nextItems })
  }

  return (
    <div className="flex flex-col gap-3 p-3 rounded-xl border border-border bg-muted/10">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-bold text-foreground">
          Subsystem Buckets &amp; Module Matching Rules
        </span>
      </div>

      {/* Subsystem Buckets Summary */}
      <div className="flex flex-wrap gap-2">
        {buckets.map((b) => (
          <div
            key={b.id}
            className="px-2.5 py-1.5 rounded-lg border bg-card text-xs flex items-center gap-2"
          >
            <span
              className={cn(
                "size-2 rounded-full",
                b.color === "purple" && "bg-purple-500",
                b.color === "emerald" && "bg-emerald-500",
                b.color === "blue" && "bg-blue-500",
                b.color === "amber" && "bg-amber-500",
                b.color === "rose" && "bg-rose-500"
              )}
            />
            <span className="font-bold text-foreground">{b.label}</span>
            {b.subtitle && <span className="text-[10px] text-muted-foreground">({b.subtitle})</span>}
          </div>
        ))}
      </div>

      {/* Datasheets Mapping */}
      <div className="flex flex-col gap-1.5 pt-1">
        <span className="text-[11px] font-semibold text-muted-foreground">
          Assign each datasheet to its correct subsystem bucket:
        </span>
        {datasheets.length === 0 ? (
          <p className="text-xs text-muted-foreground italic">
            Add datasheets in the Datasheet Catalog tab to configure matching rules.
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-56 overflow-y-auto p-1">
            {datasheets.map((ds) => {
              const rule = items.find((it) => it.datasheet_id === (ds.id || ds.title))
              const currentBucket = rule?.correct_bucket_id || ds.subsystem_tag || buckets[0]?.id || ""
              return (
                <div
                  key={ds.id || ds.title}
                  className="p-2 rounded-lg border border-border bg-card flex items-center justify-between gap-2 text-xs"
                >
                  <span className="font-medium truncate flex-1">{ds.title}</span>
                  <select
                    value={currentBucket}
                    onChange={(e) => updateItemTarget(ds.id || ds.title, e.target.value)}
                    className="h-7 px-2 border border-border bg-background rounded text-[11px] font-bold"
                  >
                    {buckets.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.label}
                      </option>
                    ))}
                  </select>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
