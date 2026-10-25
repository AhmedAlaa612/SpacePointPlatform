import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
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
  uploadPreQuizImageApi,
  type McqOption,
  type PinoutTableConfig,
  type PreSessionQuizPreset,
  type PreSessionQuizQuestion,
  type PreSessionQuizQuestionIn,
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
        title="Instructor Pre-Session Quizzes"
        subtitle="Build interactive hardware pinout connector tables and MCQ checks, assemble presets, and gate session starts."
      />

      <div className="flex gap-1 border-b border-border overflow-x-auto scrollbar-none no-scrollbar">
        <button
          type="button"
          onClick={() => setTab("presets")}
          className={cn(
            "px-4 py-2.5 text-sm font-semibold border-b-2 -mb-px transition-colors cursor-pointer shrink-0 flex items-center",
            tab === "presets"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          Quiz Presets / Templates
        </button>
        <button
          type="button"
          onClick={() => setTab("bank")}
          className={cn(
            "px-4 py-2.5 text-sm font-semibold border-b-2 -mb-px transition-colors cursor-pointer shrink-0 flex items-center",
            tab === "bank"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
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
              Preview Instructor View ({filtered.length})
            </button>
          )}
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="flex items-center justify-center h-9 px-4 bg-primary text-primary-foreground rounded-xl text-xs sm:text-sm font-semibold hover:opacity-90 transition-opacity cursor-pointer shrink-0 shadow-xs"
          >
            + New Question
          </button>
        </div>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          title="No questions in this topic yet"
          hint="Click 'New Question' to launch the visual hardware pinout table or MCQ builder."
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
                      {q.question_type === "pinout_table" ? "Connector Pinout Table" : "Multiple Choice"}
                    </span>
                    {q.is_other_correct && (
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30">
                        Tricky Question ("Other" Expected)
                      </span>
                    )}
                    {q.image_url && (
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
                        Has Question Image
                      </span>
                    )}
                    {q.explanation_image_url && (
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                        Has Explanation Image
                      </span>
                    )}
                  </div>
                  <h3 className="text-sm sm:text-base font-bold text-foreground mt-0.5">{q.title}</h3>
                  <p className="text-xs sm:text-sm text-muted-foreground">{q.prompt}</p>
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

              {(q.explanation || q.explanation_table || q.explanation_image_url) && (
                <div className="p-3 rounded-xl bg-muted/40 border border-border/80 flex flex-col gap-2">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                    Post-Submission Explanation
                  </span>
                  {q.explanation && <p className="text-xs text-foreground">{q.explanation}</p>}
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
            preset: {
              id: "preview-questions",
              name:
                previewQuestions.length === 1
                  ? `Preview: ${previewQuestions[0].title}`
                  : `Question Bank Preview (${topicFilter === "all" ? "All Topics" : topicFilter})`,
              description: "Interactive Instructor View Preview",
              question_ids: previewQuestions.map((q) => q.id),
              reference_attachments: [],
              questions: previewQuestions,
              is_active: true,
            },
            my_attempt: null,
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
  const [questionType, setQuestionType] = useState<"pinout_table" | "mcq">(
    question?.question_type ?? "pinout_table"
  )
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
            <div className="grid grid-cols-2 gap-1.5 p-1 bg-muted rounded-xl border border-border">
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
            </div>
          </Field>

          <Field label="Subsystem / Topic (e.g. CDHS, ADCS/APC)">
            <div className="flex gap-1.5">
              <input
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                list="pre-quiz-topics-list"
                placeholder="CDHS, ADCS/APC, EPS..."
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
              />
              <datalist id="pre-quiz-topics-list">
                {Array.from(new Set(["CDHS", "ADCS/APC", "EPS", ...existingTopics])).map((t) => (
                  <option key={t} value={t} />
                ))}
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

        {/* Interactive Connector Table Builder OR MCQ Options */}
        {questionType === "pinout_table" ? (
          <div className="flex flex-col gap-2 p-3.5 rounded-2xl border border-primary/25 bg-primary/5">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div>
                <p className="text-xs font-bold text-foreground">
                  Interactive Connector Pinout Table Builder
                </p>
                <p className="text-[11px] text-muted-foreground">
                  Type pin names into each cell and toggle On/Off on the cells that should be bridged by a jumper.
                </p>
              </div>
            </div>
            <ConnectorTableWidget
              config={tableConfig}
              mode="builder"
              onChangeConfig={setTableConfig}
            />
          </div>
        ) : (
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
                    setOptions(
                      options.map((o, i) => (i === idx ? { ...o, text: e.target.value } : o))
                    )
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

        {/* "Other" / Tricky Question Settings */}
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
                Allows the instructor to flag a pinout error or write a custom explanation. Submissions using &ldquo;Other&rdquo; are marked <strong>Pending Review</strong> for Operations to review.
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
                Enable this when the question table intentionally contains a wrong pinout (like CDHS Connector J6) and selecting table cells directly should be marked incorrect.
              </p>
            </div>
          </label>
        </div>

        {/* Post-Submission Explanation Section */}
        <div className="p-3.5 rounded-2xl border border-border bg-card flex flex-col gap-3">
          <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
            Post-Submission Answer Review &amp; Explanation
          </p>

          <Field label="Explanation Text (shown after instructor submits)">
            <textarea
              value={explanation}
              onChange={(e) => setExplanation(e.target.value)}
              rows={2}
              placeholder="Explain why these pins are selected or describe the actual pinout..."
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
            <span>Include a Corrected / Reference Connector Table in the Explanation (e.g. actual J6 pinout)</span>
          </label>

          {hasExplanationTable && (
            <div className="pt-1">
              <ConnectorTableWidget
                config={explanationTable}
                mode="builder"
                onChangeConfig={setExplanationTable}
              />
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
          <span>
            {uploading ? "Uploading…" : imageUrl ? "Replace image" : "Upload image"}
          </span>
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

/* ── Tab 2: Quiz Presets / Templates ───────────────────────────────────────── */

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
          Assemble questions from the bank into reusable presets that can be attached to any Program, Cohort, or Session.
        </p>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="flex items-center h-9 px-4 bg-primary text-primary-foreground rounded-xl text-xs sm:text-sm font-semibold hover:opacity-90 transition-opacity cursor-pointer shrink-0 shadow-xs"
        >
          + New Preset
        </button>
      </div>

      {presets.length === 0 ? (
        <EmptyState
          title="No quiz presets yet"
          hint="Create a preset to bundle questions for a program or cohort."
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
                      {preset.questions.length} question{preset.questions.length === 1 ? "" : "s"}
                    </span>
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
                    Preview Instructor View
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditingPreset(preset)}
                    className="flex items-center h-8 px-3 rounded-lg border border-border bg-background hover:bg-muted text-xs font-medium text-foreground transition-colors cursor-pointer"
                  >
                    Configure Preset
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

              {preset.reference_attachments.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-xs font-medium text-muted-foreground">Reference Datasheets:</span>
                  {preset.reference_attachments.map((att, idx) => (
                    <a
                      key={idx}
                      href={ensureAbsoluteUrl(att.url)}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-muted text-foreground border border-border hover:border-primary/40"
                    >
                      {att.title}
                    </a>
                  ))}
                </div>
              )}

              <div className="flex items-center gap-1.5 flex-wrap pt-1">
                {preset.questions.map((q, idx) => (
                  <span
                    key={q.id}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-muted/60 text-foreground border border-border"
                  >
                    <span className="text-[10px] font-bold text-primary">{idx + 1}.</span>
                    <span>{q.title}</span>
                  </span>
                ))}
              </div>
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
            preset: previewPreset,
            my_attempt: null,
            all_attempts: [],
          }}
        />
      )}
    </div>
  )
}

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
  const [name, setName] = useState(preset?.name ?? "")
  const [description, setDescription] = useState(preset?.description ?? "")
  const [questionIds, setQuestionIds] = useState<string[]>(preset?.question_ids ?? [])
  const [references, setReferences] = useState<ReferenceAttachment[]>(
    preset?.reference_attachments ?? []
  )
  const [refTitle, setRefTitle] = useState("")
  const [refUrl, setRefUrl] = useState("")
  const [error, setError] = useState("")

  const toggleQuestion = (qid: string) => {
    if (questionIds.includes(qid)) {
      setQuestionIds(questionIds.filter((id) => id !== qid))
    } else {
      setQuestionIds([...questionIds, qid])
    }
  }

  const moveQuestion = (idx: number, dir: -1 | 1) => {
    const target = idx + dir
    if (target < 0 || target >= questionIds.length) return
    const next = [...questionIds]
    const [moved] = next.splice(idx, 1)
    next.splice(target, 0, moved)
    setQuestionIds(next)
  }

  const addReference = () => {
    if (!refUrl.trim()) return
    setReferences([
      ...references,
      {
        id: `ref-${Date.now()}`,
        title: refTitle.trim() || refUrl.trim(),
        url: refUrl.trim(),
        is_file: refUrl.toLowerCase().endsWith(".pdf"),
      },
    ])
    setRefTitle("")
    setRefUrl("")
  }

  const saveMut = useMutation({
    mutationFn: () => {
      const payload = {
        name: name.trim(),
        description: description.trim() || null,
        question_ids: questionIds,
        reference_attachments: references,
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

  const questionsMap = useMemo(
    () => new Map(allQuestions.map((q) => [q.id, q])),
    [allQuestions]
  )

  return (
    <Modal
      title={preset ? `Configure Preset: ${preset.name}` : "New Pre-Session Quiz Preset"}
      onClose={onClose}
      maxWidth="sm:max-w-2xl max-w-2xl"
    >
      <div className="flex flex-col gap-4">
        <Field label="Preset Name">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. CDHS Board Pinout Options"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
          />
        </Field>

        <Field label="Description (optional)">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            placeholder="Brief summary of what this pre-session quiz covers..."
            className="w-full p-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
          />
        </Field>

        {/* Reference Datasheets / Links */}
        <div className="p-3 rounded-xl border border-border bg-muted/20 flex flex-col gap-2">
          <p className="text-xs font-bold text-foreground">
            Reference Datasheets / Component Links (shown to instructor at top of quiz)
          </p>
          {references.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {references.map((r, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-card border border-border"
                >
                  <span>{r.title}</span>
                  <button
                    type="button"
                    onClick={() => setReferences(references.filter((_, idx) => idx !== i))}
                    className="text-[11px] font-bold text-muted-foreground hover:text-red-500 cursor-pointer"
                  >
                    Remove
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              value={refTitle}
              onChange={(e) => setRefTitle(e.target.value)}
              placeholder="Title (e.g. MicroSD Module Datasheet)"
              className="flex-1 h-8 px-2.5 border border-border bg-card rounded-lg text-xs"
            />
            <input
              value={refUrl}
              onChange={(e) => setRefUrl(e.target.value)}
              placeholder="URL or copied material link"
              className="flex-1 h-8 px-2.5 border border-border bg-card rounded-lg text-xs"
            />
            <button
              type="button"
              onClick={addReference}
              disabled={!refUrl.trim()}
              className="h-8 px-3 bg-primary/10 text-primary border border-primary/20 rounded-lg text-xs font-semibold hover:bg-primary/15 disabled:opacity-50 cursor-pointer shrink-0"
            >
              + Add Reference
            </button>
          </div>
        </div>

        {/* Selected Questions Order */}
        <div className="flex flex-col gap-2">
          <p className="text-xs font-bold text-foreground">
            Selected Questions in Order ({questionIds.length})
          </p>
          {questionIds.length === 0 ? (
            <p className="text-xs text-muted-foreground italic py-2">
              Select questions from the bank below to add them to this preset.
            </p>
          ) : (
            <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto p-2 rounded-xl border border-border bg-muted/10">
              {questionIds.map((qid, idx) => {
                const q = questionsMap.get(qid)
                if (!q) return null
                return (
                  <div
                    key={qid}
                    className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg bg-card border border-border text-xs"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-bold text-primary">{idx + 1}.</span>
                      <span className="px-1.5 py-0.2 rounded bg-muted text-[10px] font-semibold">
                        {q.topic}
                      </span>
                      <span className="truncate font-medium">{q.title}</span>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <button
                        type="button"
                        onClick={() => moveQuestion(idx, -1)}
                        disabled={idx === 0}
                        className="px-1.5 py-0.5 rounded bg-muted/60 text-[11px] font-medium text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
                      >
                        Up
                      </button>
                      <button
                        type="button"
                        onClick={() => moveQuestion(idx, 1)}
                        disabled={idx === questionIds.length - 1}
                        className="px-1.5 py-0.5 rounded bg-muted/60 text-[11px] font-medium text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
                      >
                        Down
                      </button>
                      <button
                        type="button"
                        onClick={() => toggleQuestion(qid)}
                        className="px-1.5 py-0.5 rounded bg-muted/60 text-[11px] font-medium text-muted-foreground hover:text-red-500 cursor-pointer"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Question Bank Picker */}
        <div className="flex flex-col gap-2">
          <p className="text-xs font-bold text-foreground">Add / Toggle from Question Bank</p>
          <div className="flex flex-col gap-1.5 max-h-56 overflow-y-auto p-2 rounded-xl border border-border bg-card">
            {allQuestions.map((q) => {
              const selected = questionIds.includes(q.id)
              return (
                <label
                  key={q.id}
                  className={cn(
                    "flex items-center justify-between gap-2 p-2 rounded-lg border text-xs cursor-pointer transition-colors",
                    selected
                      ? "bg-primary/10 border-primary/30 text-foreground"
                      : "bg-background border-border/60 hover:bg-muted/50"
                  )}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => toggleQuestion(q.id)}
                      className="rounded border-border text-primary focus:ring-primary"
                    />
                    <span className="px-1.5 py-0.5 rounded bg-muted text-[10px] font-bold shrink-0">
                      {q.topic}
                    </span>
                    <span className="font-semibold truncate">{q.title}</span>
                  </div>
                  <span className="text-[10px] text-muted-foreground shrink-0">
                    {q.question_type === "pinout_table" ? "Connector Table" : "MCQ"}
                  </span>
                </label>
              )
            })}
          </div>
        </div>

        {error && <p className="text-xs text-red-500 bg-red-500/10 p-2.5 rounded-xl">{error}</p>}

        <ModalActions
          onCancel={onClose}
          onConfirm={() => saveMut.mutate()}
          loading={saveMut.isPending}
          disabled={!name.trim() || questionIds.length === 0}
          label={preset ? "Save Preset" : "Create Preset"}
        />
      </div>
    </Modal>
  )
}
