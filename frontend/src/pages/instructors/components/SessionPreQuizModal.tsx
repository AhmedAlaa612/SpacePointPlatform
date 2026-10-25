import { useEffect, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { resolveQuizImageUrl } from "@/api/lms"
import {
  submitSessionPreQuizApi,
  type PreSessionQuizAnswerIn,
  type PreSessionQuizAnswerRecord,
  type PreSessionQuizAttempt,
  type PreSessionQuizQuestion,
  type SessionPreQuizStatus,
} from "@/api/sessions/pre_session_quiz"
import { ConnectorTableWidget } from "@/components/quiz/ConnectorTableWidget"
import { Button } from "@/components/ui/button"
import { useToast } from "@/components/ui/toast"
import { cn, ensureAbsoluteUrl, getErrorMessage } from "@/lib/utils"

interface DraftAnswerState {
  selected_cells: number[][]
  selected_option_index: number | null
  chose_other: boolean
  other_text: string
}

function gradePreviewAttempt(
  questions: PreSessionQuizQuestion[],
  answers: PreSessionQuizAnswerIn[],
): PreSessionQuizAttempt {
  let autoScore = 0
  let pendingReviewCount = 0

  const records: PreSessionQuizAnswerRecord[] = questions.map((q) => {
    const sub = answers.find((a) => a.question_id === q.id)
    if (!sub) {
      return {
        question_id: q.id,
        selected_option_index: null,
        selected_cells: [],
        chose_other: false,
        other_text: null,
        status: "incorrect",
      }
    }

    if (sub.chose_other) {
      pendingReviewCount += 1
      return {
        question_id: q.id,
        selected_option_index: null,
        selected_cells: [],
        chose_other: true,
        other_text: sub.other_text ?? "",
        status: "pending_review",
      }
    }

    if (q.is_other_correct) {
      return {
        question_id: q.id,
        selected_option_index: sub.selected_option_index ?? null,
        selected_cells: sub.selected_cells ?? [],
        chose_other: false,
        other_text: null,
        status: "incorrect",
      }
    }

    if (q.question_type === "pinout_table" && q.table_config) {
      const rows = q.table_config.rows ?? []
      const submittedCells = sub.selected_cells ?? []
      let allMatch = rows.length > 0
      for (let rIdx = 0; rIdx < rows.length; rIdx++) {
        const expectedCols = (rows[rIdx].cells ?? [])
          .map((c, cIdx) => (c.is_correct ? cIdx : -1))
          .filter((idx) => idx >= 0)
          .sort((a, b) => a - b)
        const actualCols = [...(submittedCells[rIdx] ?? [])].sort((a, b) => a - b)
        if (
          expectedCols.length !== actualCols.length ||
          expectedCols.some((val, i) => val !== actualCols[i])
        ) {
          allMatch = false
          break
        }
      }
      if (allMatch) autoScore += 1
      return {
        question_id: q.id,
        selected_option_index: null,
        selected_cells: submittedCells,
        chose_other: false,
        other_text: null,
        status: allMatch ? "correct" : "incorrect",
      }
    }

    const expectedIdx = q.options.findIndex((o) => o.is_correct)
    const isCorrect = expectedIdx >= 0 && sub.selected_option_index === expectedIdx
    if (isCorrect) autoScore += 1
    return {
      question_id: q.id,
      selected_option_index: sub.selected_option_index ?? null,
      selected_cells: [],
      chose_other: false,
      other_text: null,
      status: isCorrect ? "correct" : "incorrect",
    }
  })

  return {
    id: "preview-attempt",
    session_id: "preview",
    preset_id: null,
    user_id: "preview",
    user_name: "Instructor Preview",
    answers: records,
    auto_score: autoScore,
    final_score: autoScore,
    total_questions: questions.length,
    pending_review_count: pendingReviewCount,
    submitted_at: new Date().toISOString(),
  }
}

export function SessionPreQuizModal({
  open,
  onClose,
  sessionId,
  quizStatus,
  canStartSession,
  onStartSession,
  isStartingSession,
  isPreview = false,
}: {
  open: boolean
  onClose: () => void
  sessionId?: string
  quizStatus: SessionPreQuizStatus
  canStartSession?: boolean
  onStartSession?: () => void
  isStartingSession?: boolean
  isPreview?: boolean
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const preset = quizStatus.preset
  const [previewAttempt, setPreviewAttempt] = useState<PreSessionQuizAttempt | null>(null)
  const attempt = isPreview ? previewAttempt : quizStatus.my_attempt

  // Show the Connection Selection Guide before starting the quiz when no attempt exists yet
  const [showGuide, setShowGuide] = useState<boolean>(!attempt)
  const [drafts, setDrafts] = useState<Record<string, DraftAnswerState>>({})
  const [validationError, setValidationError] = useState("")
  const [zoomImageUrl, setZoomImageUrl] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setShowGuide(!attempt)
      setValidationError("")
    }
  }, [open, Boolean(attempt)])

  const getDraft = (questionId: string, rowCount = 0): DraftAnswerState => {
    const existing = drafts[questionId]
    if (existing) return existing
    return {
      selected_cells: Array.from({ length: rowCount }, () => []),
      selected_option_index: null,
      chose_other: false,
      other_text: "",
    }
  }

  const updateDraft = (questionId: string, rowCount: number, patch: Partial<DraftAnswerState>) => {
    setValidationError("")
    setDrafts((prev) => ({
      ...prev,
      [questionId]: { ...getDraft(questionId, rowCount), ...patch },
    }))
  }

  const submitMut = useMutation({
    mutationFn: (answers: PreSessionQuizAnswerIn[]) =>
      submitSessionPreQuizApi(sessionId!, answers),
    onSuccess: () => {
      if (sessionId) {
        qc.invalidateQueries({ queryKey: ["session-pre-quiz-status", sessionId] })
      }
      setShowGuide(false)
      toast.success("Pre-session quiz submitted! Start session is now unlocked.")
    },
    onError: (err) => setValidationError(getErrorMessage(err, "Failed to submit quiz")),
  })

  if (!open || !preset) return null

  const questions = preset.questions

  const handleResetPreview = () => {
    setPreviewAttempt(null)
    setDrafts({})
    setValidationError("")
    setShowGuide(false)
  }

  const handleSubmit = () => {
    setValidationError("")
    const payload: PreSessionQuizAnswerIn[] = []

    for (let i = 0; i < questions.length; i++) {
      const q = questions[i]
      const rowCount = q.table_config?.rows.length ?? 0
      const d = getDraft(q.id, rowCount)

      if (d.chose_other) {
        if (!d.other_text.trim()) {
          setValidationError(`Question ${i + 1} (${q.title}): Please write an explanation for "Other".`)
          return
        }
        payload.push({
          question_id: q.id,
          selected_cells: null,
          selected_option_index: null,
          chose_other: true,
          other_text: d.other_text.trim(),
        })
      } else if (q.question_type === "pinout_table") {
        const totalSelected = d.selected_cells.reduce((acc, row) => acc + row.length, 0)
        if (totalSelected === 0) {
          setValidationError(
            `Question ${i + 1} (${q.title}): Please select the pinout cells in the connector table (or choose "Other" if applicable).`,
          )
          return
        }
        payload.push({
          question_id: q.id,
          selected_cells: d.selected_cells,
          selected_option_index: null,
          chose_other: false,
          other_text: null,
        })
      } else {
        if (d.selected_option_index === null || d.selected_option_index === undefined) {
          setValidationError(`Question ${i + 1} (${q.title}): Please select an answer option.`)
          return
        }
        payload.push({
          question_id: q.id,
          selected_cells: null,
          selected_option_index: d.selected_option_index,
          chose_other: false,
          other_text: null,
        })
      }
    }

    if (isPreview) {
      const graded = gradePreviewAttempt(questions, payload)
      setPreviewAttempt(graded)
      setShowGuide(false)
      toast.success("Preview submitted! Showing instructor Answer Review & Explanations.")
      return
    }

    submitMut.mutate(payload)
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-3 sm:p-6">
      <div className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-4xl max-h-[92vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b border-border flex items-start justify-between gap-3 bg-muted/30 shrink-0">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base sm:text-lg font-bold text-foreground">{preset.name}</h2>
              <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-primary/15 text-primary">
                {questions.length} Question{questions.length === 1 ? "" : "s"}
              </span>
              {isPreview && (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/20 text-amber-600 dark:text-amber-300 border border-amber-500/40">
                  Instructor View Preview
                </span>
              )}
            </div>
            {preset.description && (
              <p className="text-xs text-muted-foreground mt-0.5">{preset.description}</p>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => setShowGuide((v) => !v)}
              className={cn(
                "h-8 px-3 rounded-lg border text-xs font-semibold inline-flex items-center transition-colors cursor-pointer",
                showGuide
                  ? "border-primary bg-primary/15 text-primary"
                  : "border-border bg-card hover:bg-muted text-muted-foreground hover:text-foreground",
              )}
            >
              {showGuide ? "Back to Questions" : "How It Works Guide"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="h-8 px-2.5 rounded-lg border border-border text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer shrink-0"
            >
              Close
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5">
          {/* Reference Attachments Banner */}
          {preset.reference_attachments && preset.reference_attachments.length > 0 && (
            <div className="p-3.5 rounded-xl border border-primary/25 bg-primary/5 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
              <span className="text-xs font-medium text-foreground">
                Reference Datasheets &amp; Pinout Guides:
              </span>
              <div className="flex items-center gap-2 flex-wrap">
                {preset.reference_attachments.map((att, idx) => (
                  <a
                    key={idx}
                    href={ensureAbsoluteUrl(att.url)}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center px-2.5 py-1 rounded-lg bg-card border border-border hover:border-primary/50 text-xs font-semibold text-primary transition-colors"
                  >
                    {att.title || "Reference Document"}
                  </a>
                ))}
              </div>
            </div>
          )}

          {showGuide ? (
            <PreQuizInstructionsGuide onStartQuiz={() => setShowGuide(false)} />
          ) : (
            <>
              {/* Score & Status Banner when Attempt Exists */}
              {attempt && (
                <div className="p-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-bold text-emerald-600 dark:text-emerald-400">
                        Pre-Session Quiz Submitted
                      </span>
                      <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-card border border-border text-foreground">
                        Score: {attempt.final_score} / {attempt.total_questions}
                      </span>
                      {attempt.pending_review_count > 0 && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30">
                          {attempt.pending_review_count} Pending Review
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Review the explanations and reference pinout tables below.{" "}
                      {attempt.pending_review_count > 0 &&
                        "Questions where you selected 'Other' are marked Pending Review and will update once reviewed."}
                    </p>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {isPreview && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={handleResetPreview}
                        className="h-9 px-3.5 text-xs font-bold rounded-xl cursor-pointer"
                      >
                        Reset &amp; Try Again
                      </Button>
                    )}
                    {canStartSession && onStartSession && !isPreview && (
                      <Button
                        size="default"
                        disabled={isStartingSession}
                        onClick={() => {
                          onStartSession()
                          onClose()
                        }}
                        className="h-10 px-5 text-xs font-bold rounded-xl shadow-md bg-primary text-black hover:opacity-90 shrink-0 cursor-pointer"
                      >
                        {isStartingSession ? "Starting…" : "Start Session Now"}
                      </Button>
                    )}
                  </div>
                </div>
              )}

              {/* Questions List */}
              <div className="space-y-5">
                {questions.map((q, index) => {
                  const ansResult = attempt?.answers.find((a) => a.question_id === q.id)
                  const rowCount = q.table_config?.rows.length ?? 0
                  const draft = getDraft(q.id, rowCount)

                  return (
                    <QuestionItemCard
                      key={q.id}
                      index={index}
                      question={q}
                      isReview={Boolean(attempt)}
                      draft={draft}
                      onUpdateDraft={(patch) => updateDraft(q.id, rowCount, patch)}
                      ansResult={ansResult}
                      onZoomImage={(url) => setZoomImageUrl(url)}
                    />
                  )
                })}
              </div>

              {validationError && (
                <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-xs font-medium text-red-500">
                  {validationError}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3.5 border-t border-border bg-muted/20 flex items-center justify-between gap-3 shrink-0">
          <span className="text-xs text-muted-foreground">
            {showGuide
              ? "Read the Connection Selection Guide above, then click Start Pre-Session Quiz."
              : attempt?.submitted_at
                ? `${isPreview ? "Preview submitted" : "Submitted"} ${new Date(attempt.submitted_at).toLocaleString()}`
                : "Submitting immediately unlocks Start Session and shows explanations."}
          </span>
          <div className="flex items-center gap-2.5">
            <Button variant="outline" size="sm" onClick={onClose} className="cursor-pointer">
              {attempt ? "Close" : "Cancel"}
            </Button>
            {showGuide ? (
              <Button
                size="sm"
                onClick={() => setShowGuide(false)}
                className="px-5 font-bold bg-primary text-black hover:opacity-90 cursor-pointer"
              >
                {attempt ? "View Quiz Results" : "Start Pre-Session Quiz"}
              </Button>
            ) : (
              !attempt && (
                <Button
                  size="sm"
                  disabled={submitMut.isPending}
                  onClick={handleSubmit}
                  className="px-5 font-bold bg-primary text-black hover:opacity-90 cursor-pointer"
                >
                  {submitMut.isPending
                    ? "Submitting…"
                    : isPreview
                      ? "Submit Quiz (Preview)"
                      : "Submit Pre-Session Quiz"}
                </Button>
              )
            )}
          </div>
        </div>
      </div>

      {/* Image Lightbox */}
      {zoomImageUrl && (
        <div
          className="fixed inset-0 z-[60] bg-black/85 flex items-center justify-center p-4 cursor-zoom-out"
          onClick={() => setZoomImageUrl(null)}
        >
          <img
            src={zoomImageUrl}
            alt="Zoomed diagram"
            className="max-w-full max-h-[90vh] rounded-xl border border-border object-contain shadow-2xl"
          />
        </div>
      )}
    </div>
  )
}

/** Pre-Quiz Connection Selection Guide & How It Works (from Page 1 & 6 of SpacePoint Board Datasheet Pinout Options) */
function PreQuizInstructionsGuide({ onStartQuiz }: { onStartQuiz: () => void }) {
  return (
    <div className="space-y-5">
      <div className="p-5 rounded-2xl border border-primary/30 bg-primary/5 space-y-3">
        <div className="text-primary font-bold text-sm sm:text-base">
          Board Datasheet Pinout Options — Connection Selection Guide
        </div>
        <p className="text-xs sm:text-sm text-foreground/90 leading-relaxed">
          In this section, you will use the <strong>subsystem datasheets</strong> and the{" "}
          <strong>module datasheets</strong> to decide how each board connector should be configured.
          Each connector includes several possible pin header options. Your task is to study the
          available options, compare them with the required subsystem connections, and select the
          correct configuration for your satellite system.
        </p>
        <p className="text-xs sm:text-sm text-foreground/90 leading-relaxed">
          You should not choose the connections randomly. Each selection must be based on the
          function of the subsystem, the module requirements, and the electrical interface described
          in the datasheets. Before placing any jumper header or making any connection, make sure you
          understand whether the selected pins are used for{" "}
          <strong>
            power, ground, communication, sensor input, control signals, or optional expansion
          </strong>
          .
        </p>
      </div>

      {/* How to Use the Tables */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="p-4 rounded-2xl border border-border bg-card space-y-3">
          <h4 className="text-xs sm:text-sm font-bold text-foreground uppercase tracking-wider">
            How to Use the Connector Tables
          </h4>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Each table shows the available pin header options for a specific board connector. The{" "}
            <strong className="text-foreground">columns (1, 2, 3)</strong> represent the possible
            jumper/header positions, while the{" "}
            <strong className="text-foreground">rows (Pin 1..N)</strong> represent the pins on the
            connector.
          </p>
          <div className="space-y-1.5 pt-1">
            <p className="text-xs font-semibold text-foreground">
              For each connector, review the table and identify:
            </p>
            <ol className="text-xs text-foreground/90 space-y-1.5 list-decimal list-inside">
              <li>Which pins are required for the subsystem or module you are connecting.</li>
              <li>
                Which voltage level is required, such as <strong>3.3V (3V3)</strong> or{" "}
                <strong>5V</strong>.
              </li>
              <li>
                Which communication protocol is being used, such as{" "}
                <strong>UART, I2C, or SPI</strong>.
              </li>
              <li>Which pins should remain open or unconnected.</li>
              <li>Which jumper headers should be installed to enable the required connection.</li>
            </ol>
          </div>
        </div>

        {/* Visual Example of Clicking Cells + "Other" Discrepancy Note */}
        <div className="p-4 rounded-2xl border border-border bg-card space-y-3 flex flex-col justify-between">
          <div className="space-y-2.5">
            <h4 className="text-xs sm:text-sm font-bold text-foreground uppercase tracking-wider">
              How to Mark Your Answer
            </h4>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Click directly on the cells in each row to highlight the jumper configuration (for
              example, selecting <strong className="text-foreground">3V3 + Main</strong> on Pin 1 and{" "}
              <strong className="text-foreground">Main + GND</strong> on Pin 2):
            </p>

            {/* Mini visual example table */}
            <div className="overflow-hidden rounded-xl border-2 border-purple-900/40 text-xs">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-[#5b2d82] text-white font-bold">
                    <th className="p-1.5 border border-purple-900/40">J3</th>
                    <th className="p-1.5 border border-purple-900/40">1</th>
                    <th className="p-1.5 border border-purple-900/40">2</th>
                    <th className="p-1.5 border border-purple-900/40">3</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="bg-[#5b2d82] text-white font-bold text-center p-1.5 border border-purple-900/40">
                      Pin 1
                    </td>
                    <td className="bg-[#8e7cc3] dark:bg-[#7042a6] text-slate-950 dark:text-white font-bold text-center p-1.5 border border-purple-900/35">
                      3V3
                    </td>
                    <td className="bg-[#8e7cc3] dark:bg-[#7042a6] text-slate-950 dark:text-white font-bold text-center p-1.5 border border-purple-900/35">
                      Main
                    </td>
                    <td className="bg-card text-foreground font-bold text-center p-1.5 border border-purple-900/35">
                      GND
                    </td>
                  </tr>
                  <tr>
                    <td className="bg-[#5b2d82] text-white font-bold text-center p-1.5 border border-purple-900/40">
                      Pin 2
                    </td>
                    <td className="bg-card text-foreground font-bold text-center p-1.5 border border-purple-900/35">
                      3V3
                    </td>
                    <td className="bg-[#8e7cc3] dark:bg-[#7042a6] text-slate-950 dark:text-white font-bold text-center p-1.5 border border-purple-900/35">
                      Main
                    </td>
                    <td className="bg-[#8e7cc3] dark:bg-[#7042a6] text-slate-950 dark:text-white font-bold text-center p-1.5 border border-purple-900/35">
                      GND
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div className="p-3 rounded-xl border border-amber-500/40 bg-amber-500/10">
            <p className="text-[11px] text-foreground/90 leading-relaxed">
              <strong>Pay Attention to Datasheet Pinouts:</strong> Always compare the connector
              pinout options in the table against the actual pinout of the module/component. If you
              spot a discrepancy where the table options cannot match the component pinout, select{" "}
              <strong>&ldquo;Other&rdquo;</strong> and write your explanation!
            </p>
          </div>
        </div>
      </div>

      <div className="flex justify-center pt-1">
        <Button
          size="default"
          onClick={onStartQuiz}
          className="h-11 px-8 text-sm font-bold rounded-xl shadow-lg bg-primary text-black hover:opacity-90 cursor-pointer"
        >
          I Understand — Start Pre-Session Quiz
        </Button>
      </div>
    </div>
  )
}

function QuestionItemCard({
  index,
  question: q,
  isReview,
  draft,
  onUpdateDraft,
  ansResult,
  onZoomImage,
}: {
  index: number
  question: PreSessionQuizQuestion
  isReview: boolean
  draft: DraftAnswerState
  onUpdateDraft: (patch: Partial<DraftAnswerState>) => void
  ansResult?: PreSessionQuizAnswerRecord
  onZoomImage: (url: string) => void
}) {
  const resolvedQuestionImage = resolveQuizImageUrl(q.image_url)
  const resolvedExplanationImage = resolveQuizImageUrl(q.explanation_image_url)

  const handleToggleCell = (rowIdx: number, colIdx: number) => {
    const rowCount = q.table_config?.rows.length ?? 0
    const nextCells = Array.from({ length: rowCount }, (_, r) => [...(draft.selected_cells[r] ?? [])])
    const rowArr = nextCells[rowIdx] ?? []
    if (rowArr.includes(colIdx)) {
      nextCells[rowIdx] = rowArr.filter((c) => c !== colIdx)
    } else {
      nextCells[rowIdx] = [...rowArr, colIdx].sort((a, b) => a - b)
    }
    onUpdateDraft({ selected_cells: nextCells, chose_other: false })
  }

  const statusBadge = () => {
    if (!isReview || !ansResult) return null
    if (ansResult.status === "correct") {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
          Correct
        </span>
      )
    }
    if (ansResult.status === "pending_review") {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30">
          Pending Review
        </span>
      )
    }
    return (
      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-red-500/15 text-red-500 border border-red-500/30">
        Incorrect
      </span>
    )
  }

  return (
    <div className="p-4 sm:p-5 rounded-2xl border border-border bg-card shadow-sm space-y-4">
      {/* Question Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="px-2 py-0.5 rounded-md bg-primary/15 text-primary text-xs font-bold">
              Q{index + 1}
            </span>
            {q.topic && (
              <span className="px-2 py-0.5 rounded-md bg-muted text-muted-foreground text-[11px] font-semibold uppercase">
                {q.topic}
              </span>
            )}
            <h3 className="text-sm sm:text-base font-bold text-foreground">{q.title}</h3>
          </div>
          <p className="text-xs sm:text-sm text-foreground/90 whitespace-pre-wrap leading-relaxed">
            {q.prompt}
          </p>
        </div>
        {statusBadge()}
      </div>

      {/* Optional Question Image / Diagram */}
      {resolvedQuestionImage && (
        <div className="rounded-xl overflow-hidden border border-border bg-muted/20 p-2 flex flex-col items-center">
          <img
            src={resolvedQuestionImage}
            alt={q.title}
            onClick={() => onZoomImage(resolvedQuestionImage)}
            className="max-h-64 object-contain rounded-lg cursor-zoom-in hover:opacity-95 transition-opacity"
          />
          <span className="text-[10px] text-muted-foreground mt-1">Click diagram to enlarge</span>
        </div>
      )}

      {/* Interactive or Review Body */}
      {q.question_type === "pinout_table" && q.table_config && (
        <div
          className={cn(
            "transition-opacity",
            !isReview && draft.chose_other && "opacity-45 pointer-events-none",
          )}
        >
          <ConnectorTableWidget
            config={q.table_config}
            mode={isReview ? "review" : "interactive"}
            selectedCells={isReview ? ansResult?.selected_cells ?? [] : draft.selected_cells}
            onToggleCell={handleToggleCell}
            disabled={!isReview && draft.chose_other}
          />
        </div>
      )}

      {q.question_type === "mcq" && (
        <div
          className={cn(
            "grid grid-cols-1 gap-2",
            !isReview && draft.chose_other && "opacity-45 pointer-events-none",
          )}
        >
          {q.options.map((opt, optIdx) => {
            const isSelected = isReview
              ? ansResult?.selected_option_index === optIdx
              : draft.selected_option_index === optIdx
            const isCorrectOpt = isReview && opt.is_correct

            return (
              <button
                key={optIdx}
                type="button"
                disabled={isReview}
                onClick={() =>
                  onUpdateDraft({ selected_option_index: optIdx, chose_other: false })
                }
                className={cn(
                  "p-3 rounded-xl border text-left text-xs sm:text-sm font-medium transition-all flex items-center justify-between gap-3",
                  !isReview && "cursor-pointer",
                  isReview
                    ? isCorrectOpt
                      ? "border-emerald-500 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                      : isSelected
                        ? "border-red-500 bg-red-500/10 text-red-600"
                        : "border-border bg-muted/20 text-muted-foreground"
                    : isSelected
                      ? "border-primary bg-primary/15 text-foreground ring-1 ring-primary/40"
                      : "border-border bg-card hover:bg-muted/50 text-foreground",
                )}
              >
                <span>{opt.text}</span>
                {isReview && isCorrectOpt && (
                  <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400 shrink-0">
                    Correct
                  </span>
                )}
                {isReview && isSelected && !isCorrectOpt && (
                  <span className="text-xs font-bold text-red-500 shrink-0">Selected</span>
                )}
              </button>
            )
          })}
        </div>
      )}

      {/* "Other (Write Explanation)" Option */}
      {q.allow_other && !isReview && (
        <div
          className={cn(
            "p-3.5 rounded-xl border transition-all space-y-2.5",
            draft.chose_other
              ? "border-amber-500/60 bg-amber-500/10"
              : "border-dashed border-border bg-muted/20 hover:border-border/90",
          )}
        >
          <label className="flex items-center gap-2.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={draft.chose_other}
              onChange={(e) =>
                onUpdateDraft({
                  chose_other: e.target.checked,
                  ...(e.target.checked
                    ? {
                        selected_cells: Array.from(
                          { length: q.table_config?.rows.length ?? 0 },
                          () => [],
                        ),
                        selected_option_index: null,
                      }
                    : {}),
                })
              }
              className="rounded border-border text-primary focus:ring-primary"
            />
            <span className="text-xs font-bold text-foreground">
              Other — None of the above / Explain datasheet discrepancy
            </span>
          </label>

          {draft.chose_other && (
            <textarea
              rows={3}
              value={draft.other_text}
              onChange={(e) => onUpdateDraft({ other_text: e.target.value })}
              placeholder="Write your explanation (e.g., identify the pinout discrepancy between the connector options and the actual component pinout)..."
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-xs text-foreground focus:outline-none focus:border-primary resize-y"
            />
          )}
        </div>
      )}

      {/* Instructor's "Other" Written Answer in Review Mode */}
      {isReview && ansResult?.chose_other && (
        <div className="p-3.5 rounded-xl border border-amber-500/30 bg-amber-500/10 space-y-2">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <span className="text-xs font-bold text-amber-600 dark:text-amber-400">
              You selected &ldquo;Other&rdquo; — Written Explanation:
            </span>
            {ansResult.status === "pending_review" && (
              <span className="text-[11px] font-semibold text-amber-600 dark:text-amber-400">
                Awaiting Review
              </span>
            )}
          </div>
          <p className="text-xs text-foreground bg-card/80 p-2.5 rounded-lg border border-border/60 whitespace-pre-wrap">
            {ansResult.other_text || "No explanation provided."}
          </p>
          {ansResult.review_comment && (
            <div className="pt-1 text-xs text-muted-foreground">
              <strong className="text-foreground">Reviewer Feedback:</strong> {ansResult.review_comment}
            </div>
          )}
        </div>
      )}

      {/* Explanation Section (Shown in Review Mode after Submission) */}
      {isReview && (q.explanation || resolvedExplanationImage || q.explanation_table) && (
        <div className="p-4 rounded-xl border border-primary/25 bg-primary/5 space-y-3">
          <div className="text-xs font-bold text-primary uppercase tracking-wider">
            Answer Explanation &amp; Reference Pinout
          </div>

          {q.explanation && (
            <p className="text-xs sm:text-sm text-foreground/90 whitespace-pre-wrap leading-relaxed">
              {q.explanation}
            </p>
          )}

          {resolvedExplanationImage && (
            <div className="rounded-xl overflow-hidden border border-border bg-card p-2 flex flex-col items-center">
              <img
                src={resolvedExplanationImage}
                alt="Explanation diagram"
                onClick={() => onZoomImage(resolvedExplanationImage)}
                className="max-h-64 object-contain rounded-lg cursor-zoom-in"
              />
              <span className="text-[10px] text-muted-foreground mt-1">Click diagram to enlarge</span>
            </div>
          )}

          {q.explanation_table && (
            <div className="pt-1 space-y-1.5">
              <span className="text-[11px] font-semibold text-muted-foreground">
                Reference Pinout Table:
              </span>
              <ConnectorTableWidget
                config={q.explanation_table}
                mode="reference"
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
