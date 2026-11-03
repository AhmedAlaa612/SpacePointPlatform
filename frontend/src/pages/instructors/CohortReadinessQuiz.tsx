import { useEffect, useMemo, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "@tanstack/react-router"
import {
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  Clock,
  Eye,
  FileText,
  GripVertical,
  HelpCircle,
  Lock,
  RotateCcw,
  Search,
  X,
  XCircle,
} from "lucide-react"

import {
  getCohortPreQuizStatusApi,
  startCohortPhaseApi,
  submitCohortPhaseApi,
  type CohortPreQuizStatus,
  type PhaseTrial,
  type PhaseTrialSubmitIn,
  type PreSessionQuizAnswerIn,
  type PreSessionQuizPreset,
  type QuizPipelinePhase,
  type ReferenceAttachment,
} from "@/api/sessions/pre_session_quiz"
import { PdfViewer } from "@/components/documents/PdfViewer"
import { ConnectorTableWidget } from "@/components/quiz/ConnectorTableWidget"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/primitives"
import { useToast } from "@/components/ui/toast"
import { cn, ensureAbsoluteUrl, getErrorMessage } from "@/lib/utils"

export interface CohortReadinessQuizProps {
  presetOverride?: PreSessionQuizPreset
  isObserverMode?: boolean
  onExitObserver?: () => void
}

export default function CohortReadinessQuiz({
  presetOverride,
  isObserverMode = false,
  onExitObserver,
}: CohortReadinessQuizProps = {}) {
  const { cohortId } = (useParams({ strict: false }) || {}) as { cohortId?: string }
  const searchParams = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null
  const sessionId = searchParams?.get("sessionId") || undefined
  const navigate = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()

  const isSimulated = isObserverMode || Boolean(presetOverride)

  // Simulated state for LMS Observer / Preview Mode
  const [observerAttempt, setObserverAttempt] = useState<CohortPreQuizStatus["my_attempt"]>(() => {
    if (!isSimulated) return null
    return {
      id: "observer-simulated-attempt",
      cohort_id: "observer-cohort",
      preset_id: presetOverride?.id || "preview-preset",
      user_id: "observer-user",
      status: "in_progress",
      current_phase_index: 0,
      phase_started_at: new Date().toISOString(),
      total_duration_seconds: 0,
      final_score: 0,
      total_questions: presetOverride?.questions?.length || 0,
      answers: [],
      phase_states: {},
      locked_until: null,
      started_at: new Date().toISOString(),
      submitted_at: null,
    } as any
  })
  const [observerTrials, setObserverTrials] = useState<PhaseTrial[]>([])

  const { data: status, isLoading: queryLoading } = useQuery({
    queryKey: ["cohort-pre-quiz-status", cohortId],
    queryFn: () => getCohortPreQuizStatusApi(cohortId!),
    enabled: !isSimulated && Boolean(cohortId),
    refetchInterval: (query) => {
      const att = query.state.data?.my_attempt
      return att?.status === "cooldown_locked" ? 2000 : false
    },
  })

  const preset = isSimulated ? presetOverride : status?.preset
  const attempt = isSimulated ? observerAttempt : status?.my_attempt
  const trials = isSimulated ? observerTrials : (status?.trials ?? [])
  const phases = preset?.phases ?? []
  const isLoading = !isSimulated ? queryLoading : false

  // Active viewing phase index (allows clicking back to review completed phases)
  const [viewingPhaseIndex, setViewingPhaseIndex] = useState<number>(0)
  const [pdfModalDoc, setPdfModalDoc] = useState<ReferenceAttachment | null>(null)
  const [datasheetDrawerOpen, setDatasheetDrawerOpen] = useState(false)

  // Sync viewing phase index with attempt progress
  useEffect(() => {
    if (attempt) {
      setViewingPhaseIndex((prev) => {
        const curr = attempt.current_phase_index ?? 0
        if (prev > curr) {
          return curr
        }
        return prev === 0 ? curr : prev
      })
    }
  }, [attempt?.current_phase_index])

  // Automatically start phase attempt on backend if not started yet
  useEffect(() => {
    if (isSimulated || !cohortId || !preset?.phases) return
    const activePhase = preset.phases[viewingPhaseIndex]
    if (!activePhase) return
    if (!attempt || (attempt.current_phase_index === viewingPhaseIndex && attempt.status !== "completed" && attempt.status !== "cooldown_locked")) {
      startCohortPhaseApi(cohortId, activePhase.id).catch(() => {})
    }
  }, [cohortId, preset?.phases, viewingPhaseIndex, attempt, isSimulated])

  // Current phase active timer (tracks active duration on phase)
  const [phaseSeconds, setPhaseSeconds] = useState(0)
  useEffect(() => {
    setPhaseSeconds(0)
    const interval = setInterval(() => {
      setPhaseSeconds((s) => s + 1)
    }, 1000)
    return () => clearInterval(interval)
  }, [viewingPhaseIndex])

  // Calculate cooldown countdown seconds
  const [cooldownRemaining, setCooldownRemaining] = useState<number | null>(null)
  useEffect(() => {
    if (!attempt?.locked_until) {
      setCooldownRemaining(null)
      return
    }
    const updateCountdown = () => {
      const remaining = Math.max(
        0,
        Math.floor((new Date(attempt.locked_until!).getTime() - Date.now()) / 1000)
      )
      setCooldownRemaining(remaining)
      if (remaining === 0) {
        if (!isSimulated && cohortId) {
          qc.invalidateQueries({ queryKey: ["cohort-pre-quiz-status", cohortId] })
        } else if (isSimulated) {
          setObserverAttempt((prev) =>
            prev ? { ...prev, status: "in_progress", locked_until: null } : null
          )
        }
      }
    }
    updateCountdown()
    const timer = setInterval(updateCountdown, 1000)
    return () => clearInterval(timer)
  }, [attempt?.locked_until, cohortId, qc, isSimulated])

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3">
        <Spinner className="size-8 text-primary" />
        <p className="text-sm text-muted-foreground">Loading Instructor Readiness Pipeline…</p>
      </div>
    )
  }

  if (!preset) {
    return (
      <div className="max-w-xl mx-auto py-16 px-4 text-center space-y-4">
        <p className="text-base font-semibold">
          {isSimulated ? "Observer Mode: Pipeline Preset Missing" : "No Readiness Pipeline Assigned"}
        </p>
        <p className="text-sm text-muted-foreground mt-1 max-w-xs mx-auto">
          {isSimulated
            ? "No pipeline preset was passed to preview."
            : "There is no active pre-session quiz or readiness pipeline assigned to this cohort."}
        </p>
        {isSimulated && onExitObserver ? (
          <Button onClick={onExitObserver}>Exit Observer Mode</Button>
        ) : sessionId ? (
          <Button onClick={() => navigate({ to: `/instructors/sessions/${sessionId}` })}>
            Return to Session
          </Button>
        ) : null}
      </div>
    )
  }

  const isCompleted = attempt?.status === "completed"
  const currentPhase = phases[viewingPhaseIndex]
  const isViewingCompleteStep = viewingPhaseIndex >= phases.length

  const handleObserverSubmit = (body: PhaseTrialSubmitIn) => {
    if (!currentPhase) return
    const now = new Date()
    const nowIso = now.toISOString()
    const trialNumber = observerTrials.filter((t) => t.phase_id === currentPhase.id).length + 1
    let passed = false
    let score = 0
    let total = 1
    let scorePct = 100
    let trialPayload: Record<string, any> = {}

    if (currentPhase.phase_type === "explore_datasheets") {
      passed = true
      score = 1
      total = 1
      scorePct = 100
    } else if (currentPhase.phase_type === "subsystem_matching") {
      const items = currentPhase.matching_config?.items || []
      total = items.length || 1
      score = 0
      const placements = body.matching_placements || {}
      const results: Record<string, any> = {}
      items.forEach((it) => {
        const userBucket = placements[it.datasheet_id]
        const isOk = userBucket === it.correct_bucket_id
        if (isOk) score++
        results[it.datasheet_id] = { is_correct: isOk }
      })
      scorePct = total > 0 ? Math.round((score / total) * 100) : 100
      passed = scorePct >= (currentPhase.pass_percentage ?? 100)
      trialPayload = { results, placements }
    } else if (currentPhase.phase_type === "quiz") {
      const phaseQIds = new Set(currentPhase.question_ids || [])
      const questions = (preset?.questions || []).filter((q) => phaseQIds.has(q.id))
      total = questions.length || 1
      score = 0
      const gradedAnswers: any[] = []
      questions.forEach((q) => {
        const ans = body.answers?.find((a) => a.question_id === q.id)
        let isCorrect = false
        if (ans) {
          if (q.is_other_correct && ans.chose_other) {
            isCorrect = true
          } else if (q.question_type === "mcq" && ans.selected_option_index != null) {
            const opt = q.options?.[ans.selected_option_index]
            isCorrect = Boolean(opt?.is_correct)
          } else if (q.question_type === "pinout_table" && q.table_config?.rows?.length) {
            const selectedCells = ans.selected_cells || []
            const hasAnySelection = selectedCells.some((r) => Array.isArray(r) && r.length > 0)
            if (!hasAnySelection) {
              isCorrect = false
            } else {
              isCorrect = true
              for (let rIdx = 0; rIdx < q.table_config.rows.length; rIdx++) {
                const row = q.table_config.rows[rIdx]
                const expectedIndices = new Set(
                  (row.cells || [])
                    .map((c: any, cIdx: number) => (c.is_correct ? cIdx : -1))
                    .filter((idx: number) => idx >= 0)
                )
                const userRow = new Set(selectedCells[rIdx] || [])
                if (
                  expectedIndices.size !== userRow.size ||
                  ![...expectedIndices].every((idx) => userRow.has(idx))
                ) {
                  isCorrect = false
                  break
                }
              }
            }
          } else if (q.question_type === "written") {
            isCorrect = Boolean(ans.written_text && ans.written_text.trim().length > 0)
          } else {
            isCorrect = false
          }
        }
        if (isCorrect) score++
        gradedAnswers.push({
          question_id: q.id,
          status: isCorrect ? "correct" : "incorrect",
          score: isCorrect ? 1 : 0,
        })
      })
      scorePct = total > 0 ? Math.round((score / total) * 100) : 100
      passed = scorePct >= (currentPhase.pass_percentage ?? 100)
      trialPayload = { answers: gradedAnswers }
    }

    const newTrial: PhaseTrial = {
      id: `sim-trial-${Date.now()}`,
      attempt_id: "observer-simulated-attempt",
      phase_id: currentPhase.id,
      phase_index: viewingPhaseIndex,
      phase_type: currentPhase.phase_type,
      trial_number: trialNumber,
      started_at: nowIso,
      submitted_at: nowIso,
      duration_seconds: body.client_duration_seconds || 15,
      score,
      total,
      score_pct: scorePct,
      pass_percentage_required: currentPhase.pass_percentage ?? 100,
      passed,
      cooldown_until: null,
      payload: trialPayload,
    }
    setObserverTrials((prev) => [...prev, newTrial])

    if (passed) {
      toast.success(`Passed ${currentPhase.title}! Score: ${scorePct}%`)
      const nextIdx = viewingPhaseIndex + 1
      const isAllDone = nextIdx >= phases.length
      setObserverAttempt((prev) => ({
        ...prev!,
        current_phase_index: Math.max(prev?.current_phase_index ?? 0, nextIdx),
        status: isAllDone ? "completed" : "in_progress",
        final_score: (prev!.final_score || 0) + score,
        total_questions: (prev!.total_questions || 0) + total,
        submitted_at: isAllDone ? nowIso : prev!.submitted_at,
        locked_until: null,
      }))
      if (nextIdx < phases.length) {
        setViewingPhaseIndex(nextIdx)
      } else {
        setViewingPhaseIndex(phases.length)
      }
    } else {
      toast.error(
        `Did not meet ${currentPhase.pass_percentage}% passing score. Review delay applied.`
      )
      if (currentPhase.cooldown_seconds > 0) {
        const lockUntil = new Date(Date.now() + currentPhase.cooldown_seconds * 1000).toISOString()
        setObserverAttempt((prev) => ({
          ...prev!,
          status: "cooldown_locked",
          locked_until: lockUntil,
        }))
      }
    }
  }

  const handleObserverForcePass = () => {
    if (!currentPhase || viewingPhaseIndex >= phases.length) return
    const nowIso = new Date().toISOString()
    const trialNumber = observerTrials.filter((t) => t.phase_id === currentPhase.id).length + 1
    const newTrial: PhaseTrial = {
      id: `sim-trial-pass-${Date.now()}`,
      attempt_id: "observer-simulated-attempt",
      phase_id: currentPhase.id,
      phase_index: viewingPhaseIndex,
      phase_type: currentPhase.phase_type,
      trial_number: trialNumber,
      started_at: nowIso,
      submitted_at: nowIso,
      duration_seconds: 5,
      score: 1,
      total: 1,
      score_pct: 100,
      pass_percentage_required: currentPhase.pass_percentage ?? 100,
      passed: true,
      cooldown_until: null,
      payload: { forced_observer_pass: true },
    }
    setObserverTrials((prev) => [...prev, newTrial])
    const nextIdx = viewingPhaseIndex + 1
    const isAllDone = nextIdx >= phases.length
    setObserverAttempt((prev) => ({
      ...prev!,
      current_phase_index: Math.max(prev?.current_phase_index ?? 0, nextIdx),
      status: isAllDone ? "completed" : "in_progress",
      final_score: (prev?.final_score || 0) + 1,
      total_questions: (prev?.total_questions || 0) + 1,
      submitted_at: isAllDone ? nowIso : prev?.submitted_at ?? null,
      locked_until: null,
    }))
    setCooldownRemaining(null)
    setViewingPhaseIndex(nextIdx < phases.length ? nextIdx : phases.length)
    toast.success(`Observer: Phase ${viewingPhaseIndex + 1} (${currentPhase.title}) passed with 100%!`)
  }

  const handleObserverForceFail = () => {
    if (!currentPhase || viewingPhaseIndex >= phases.length) return
    const nowIso = new Date().toISOString()
    const trialNumber = observerTrials.filter((t) => t.phase_id === currentPhase.id).length + 1
    const cooldownSec = currentPhase.cooldown_seconds || 0
    const lockUntil = cooldownSec > 0 ? new Date(Date.now() + cooldownSec * 1000).toISOString() : null
    const newTrial: PhaseTrial = {
      id: `sim-trial-fail-${Date.now()}`,
      attempt_id: "observer-simulated-attempt",
      phase_id: currentPhase.id,
      phase_index: viewingPhaseIndex,
      phase_type: currentPhase.phase_type,
      trial_number: trialNumber,
      started_at: nowIso,
      submitted_at: nowIso,
      duration_seconds: 5,
      score: 0,
      total: 1,
      score_pct: 0,
      pass_percentage_required: currentPhase.pass_percentage ?? 100,
      passed: false,
      cooldown_until: lockUntil,
      payload: { forced_observer_fail: true },
    }
    setObserverTrials((prev) => [...prev, newTrial])
    if (lockUntil) {
      setObserverAttempt((prev) => ({
        ...prev!,
        status: "cooldown_locked",
        locked_until: lockUntil,
      }))
      setCooldownRemaining(cooldownSec)
    }
    toast.error(`Observer: Phase ${viewingPhaseIndex + 1} (${currentPhase.title}) failed with 0%. ${cooldownSec > 0 ? `Cooldown applied: ${cooldownSec}s.` : ""}`)
  }

  const formatTimer = (totalSec: number) => {
    const mins = Math.floor(totalSec / 60)
    const secs = totalSec % 60
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* ── LMS Observer Mode Header Bar (Flat, No Gradients) ───────────────────── */}
      {isSimulated && (
        <div className="bg-card text-foreground px-4 py-2.5 sticky top-0 z-40 border-b border-border shadow-xs flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold tracking-wider uppercase bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30 flex items-center gap-1.5 shrink-0">
              <Eye className="size-3" />
              Observer Mode
            </span>
            <span className="text-xs sm:text-sm text-muted-foreground">
              Instructor View Simulation &bull; <strong className="text-foreground">{preset.name}</strong>
            </span>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Quick jump to phase */}
            <select
              value={viewingPhaseIndex}
              onChange={(e) => {
                const idx = Number(e.target.value)
                setViewingPhaseIndex(idx)
                setObserverAttempt((prev) => ({
                  ...prev!,
                  current_phase_index: Math.max(prev?.current_phase_index ?? 0, idx),
                }))
              }}
              className="h-8 px-2.5 rounded-lg bg-background border border-border text-xs font-semibold text-foreground focus:outline-none focus:border-primary cursor-pointer"
            >
              {phases.map((ph, idx) => (
                <option key={ph.id || idx} value={idx}>
                  Phase {idx + 1}: {ph.title}
                </option>
              ))}
              <option value={phases.length}>
                Completion Summary
              </option>
            </select>

            {/* Quick Simulation Shortcuts: Force Pass (100%) & Force Fail (0%) */}
            {!isViewingCompleteStep && (
              <div className="flex items-center gap-1.5 flex-wrap">
                <button
                  type="button"
                  onClick={handleObserverForcePass}
                  className="h-8 px-2.5 rounded-lg bg-emerald-500/15 border border-emerald-500/30 hover:bg-emerald-500/25 text-xs font-bold text-emerald-600 dark:text-emerald-400 transition-colors cursor-pointer flex items-center gap-1.5"
                  title="Simulate passing this step with 100%"
                >
                  <CheckCircle2 className="size-3.5 shrink-0" />
                  <span className="sm:hidden">Pass (100%)</span>
                  <span className="hidden sm:inline">Pass Step (100%)</span>
                </button>
                <button
                  type="button"
                  onClick={handleObserverForceFail}
                  className="h-8 px-2.5 rounded-lg bg-destructive/15 border border-destructive/30 hover:bg-destructive/25 text-xs font-bold text-destructive transition-colors cursor-pointer flex items-center gap-1.5"
                  title="Simulate failing this step with 0% (triggers cooldown)"
                >
                  <XCircle className="size-3.5 shrink-0" />
                  <span className="sm:hidden">Fail (0%)</span>
                  <span className="hidden sm:inline">Fail Step (0%)</span>
                </button>
              </div>
            )}

            {/* Reset Simulation */}
            <button
              type="button"
              onClick={() => {
                setObserverAttempt({
                  id: "observer-simulated-attempt",
                  cohort_id: "observer-cohort",
                  preset_id: preset.id,
                  user_id: "observer-user",
                  status: "in_progress",
                  current_phase_index: 0,
                  phase_started_at: new Date().toISOString(),
                  total_duration_seconds: 0,
                  final_score: 0,
                  total_questions: preset.questions?.length || 0,
                  answers: [],
                  phase_states: {},
                  locked_until: null,
                  started_at: new Date().toISOString(),
                  submitted_at: null,
                } as any)
                setObserverTrials([])
                setViewingPhaseIndex(0)
                setCooldownRemaining(null)
                toast.success("Observer simulation reset to Phase 1")
              }}
              className="h-8 px-2.5 rounded-lg bg-muted hover:bg-muted/80 text-xs font-semibold text-foreground transition-colors cursor-pointer border border-border flex items-center gap-1.5"
            >
              <RotateCcw className="size-3.5" />
              Reset Simulation
            </button>

            {/* Bypass Cooldown if locked */}
            {observerAttempt?.locked_until && (
              <button
                type="button"
                onClick={() => {
                  setObserverAttempt((prev) => ({
                    ...prev!,
                    status: "in_progress",
                    locked_until: null,
                  }))
                  setCooldownRemaining(null)
                  toast.success("Observer: Cooldown bypassed")
                }}
                className="h-8 px-2.5 rounded-lg bg-amber-500/15 border border-amber-500/30 hover:bg-amber-500/25 text-xs font-bold text-amber-600 dark:text-amber-400 transition-colors cursor-pointer flex items-center gap-1.5"
              >
                <Clock className="size-3.5" />
                Bypass Cooldown
              </button>
            )}

            {/* Exit Observer View */}
            {onExitObserver && (
              <button
                type="button"
                onClick={onExitObserver}
                className="h-8 px-3 rounded-lg border border-border bg-background hover:bg-muted text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors cursor-pointer flex items-center gap-1.5"
              >
                <X className="size-3.5" />
                Exit Observer
              </button>
            )}
          </div>
        </div>
      )}

      {/* ── Top Header Navigation Bar ────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-border bg-card/95 backdrop-blur px-4 sm:px-6 py-3">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            {isSimulated && onExitObserver ? (
              <button
                type="button"
                onClick={onExitObserver}
                className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground font-medium shrink-0 cursor-pointer"
              >
                <ArrowLeft className="size-3.5" /> Exit Observer
              </button>
            ) : sessionId ? (
              <Link
                to="/instructors/sessions/$sessionId"
                params={{ sessionId }}
                className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground font-medium shrink-0"
              >
                <ArrowLeft className="size-3.5" /> Back to Session
              </Link>
            ) : (
              <Link
                to="/instructors/dashboard"
                className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground font-medium shrink-0"
              >
                <ArrowLeft className="size-3.5" /> Dashboard
              </Link>
            )}
            <div className="h-4 w-px bg-border hidden sm:block" />
            <div className="min-w-0">
              <h1 className="text-sm font-bold text-foreground truncate">{preset.name}</h1>
              <p className="text-[11px] text-muted-foreground truncate hidden sm:block">
                Instructor Pre-Cohort Readiness Gate
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-4 shrink-0">
            {/* Live Active Phase Timer */}
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-muted border border-border text-xs font-mono font-medium text-foreground">
              <Clock className="size-3.5 text-muted-foreground" />
              <span>Phase: {formatTimer(phaseSeconds)}</span>
              {attempt?.total_duration_seconds ? (
                <span className="text-muted-foreground hidden md:inline">
                  (Total: {formatTimer(attempt.total_duration_seconds + phaseSeconds)})
                </span>
              ) : null}
            </div>

            {/* Reference Datasheet Drawer Toggle */}
            {preset.reference_attachments?.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDatasheetDrawerOpen(true)}
                className="gap-1.5 text-xs h-8"
              >
                <FileText className="size-3.5" />
                <span className="hidden sm:inline">Reference Guides</span>
                <span className="px-1.5 py-0.2 rounded-full bg-primary/10 text-primary text-[10px] font-bold">
                  {preset.reference_attachments.length}
                </span>
              </Button>
            )}
          </div>
        </div>

        {/* ── Top Horizontal Phase Stepper ───────────────────────────────────── */}
        <div className="max-w-7xl mx-auto pt-3 pb-1 overflow-x-auto scrollbar-none no-scrollbar">
          <div className="flex items-center gap-2 min-w-max">
            {phases.map((ph, idx) => {
              const isPast = (attempt?.current_phase_index ?? 0) > idx || isCompleted
              const isViewing = viewingPhaseIndex === idx
              const isLocked = (attempt?.current_phase_index ?? 0) < idx && !isCompleted

              return (
                <div key={ph.id} className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={isLocked}
                    onClick={() => setViewingPhaseIndex(idx)}
                    className={cn(
                      "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed",
                      isViewing
                        ? "bg-primary text-primary-foreground shadow-sm ring-2 ring-primary/20"
                        : isPast
                        ? "bg-purple-500/10 text-purple-700 dark:text-purple-300 hover:bg-purple-500/15"
                        : "bg-muted text-muted-foreground hover:text-foreground"
                    )}
                  >
                    <span
                      className={cn(
                        "size-5 rounded-full inline-flex items-center justify-center text-[10px] font-bold shrink-0",
                        isViewing
                          ? "bg-primary-foreground text-primary"
                          : isPast
                          ? "bg-purple-500 text-white"
                          : "bg-muted-foreground/20 text-muted-foreground"
                      )}
                    >
                      {isPast ? <CheckCircle2 className="size-3" /> : idx + 1}
                    </span>
                    <span className="truncate max-w-[130px] sm:max-w-[160px]">{ph.title}</span>
                  </button>

                  {idx < phases.length - 1 && (
                    <div
                      className={cn(
                        "w-4 h-0.5 shrink-0 rounded-full",
                        (attempt?.current_phase_index ?? 0) > idx || isCompleted
                          ? "bg-primary"
                          : "bg-border"
                      )}
                    />
                  )}
                </div>
              )
            })}

            {/* Complete Step Pill */}
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "w-4 h-0.5 shrink-0 rounded-full",
                  isCompleted ? "bg-primary" : "bg-border"
                )}
              />
              <button
                type="button"
                disabled={!isCompleted}
                onClick={() => setViewingPhaseIndex(phases.length)}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
                  viewingPhaseIndex >= phases.length
                    ? "bg-emerald-600 text-white"
                    : isCompleted
                    ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                    : "bg-muted text-muted-foreground opacity-40 cursor-not-allowed"
                )}
              >
                <CheckCircle2 className="size-3.5" />
                <span>Complete</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* ── Main Layout Body ─────────────────────────────────────────────────── */}
      <div className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 flex flex-col lg:flex-row gap-6">
        {/* Left Phase Navigation Sidebar */}
        <aside className="lg:w-64 shrink-0 hidden lg:flex flex-col gap-2">
          <div className="p-3 rounded-xl border border-border bg-card">
            <h2 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
              Pipeline Steps
            </h2>
            <nav className="flex flex-col gap-1">
              {phases.map((ph, idx) => {
                const isPast = (attempt?.current_phase_index ?? 0) > idx || isCompleted
                const isViewing = viewingPhaseIndex === idx
                const isLocked = (attempt?.current_phase_index ?? 0) < idx && !isCompleted

                return (
                  <button
                    key={ph.id}
                    type="button"
                    disabled={isLocked}
                    onClick={() => setViewingPhaseIndex(idx)}
                    className={cn(
                      "w-full text-left p-2.5 rounded-lg text-xs transition-colors flex items-start gap-2.5 border",
                      isViewing
                        ? "bg-primary/10 border-primary/40 text-foreground font-bold"
                        : "border-transparent hover:bg-muted/50 text-muted-foreground hover:text-foreground",
                      isLocked && "opacity-40 cursor-not-allowed"
                    )}
                  >
                    <div className="mt-0.5 shrink-0">
                      {isPast ? (
                        <CheckCircle2 className="size-4 text-purple-600 dark:text-purple-400" />
                      ) : isLocked ? (
                        <Lock className="size-3.5 text-muted-foreground" />
                      ) : (
                        <span className="size-4 rounded-full bg-primary/20 text-primary text-[10px] font-bold inline-flex items-center justify-center">
                          {idx + 1}
                        </span>
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-medium">{ph.title}</p>
                      {ph.subtitle && (
                        <p className="text-[10px] text-muted-foreground truncate">{ph.subtitle}</p>
                      )}
                    </div>
                  </button>
                )
              })}

              <button
                type="button"
                disabled={!isCompleted}
                onClick={() => setViewingPhaseIndex(phases.length)}
                className={cn(
                  "w-full text-left p-2.5 rounded-lg text-xs transition-colors flex items-center gap-2.5 border",
                  viewingPhaseIndex >= phases.length
                    ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-700 dark:text-emerald-300 font-bold"
                    : isCompleted
                    ? "border-transparent text-emerald-600 hover:bg-emerald-500/10"
                    : "border-transparent opacity-40 cursor-not-allowed text-muted-foreground"
                )}
              >
                <CheckCircle2 className="size-4 text-emerald-600" />
                <span className="font-medium">Completion Summary</span>
              </button>
            </nav>
          </div>

          {/* Quick Help Card */}
          <div className="p-3.5 rounded-xl border border-border bg-muted/30 text-xs space-y-1.5">
            <div className="flex items-center gap-1.5 font-bold text-foreground">
              <HelpCircle className="size-3.5 text-primary" />
              <span>Readiness Rules</span>
            </div>
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              Complete each phase sequentially. All phase trials and duration are logged for review.
              Passing unlocks session delivery for this entire cohort.
            </p>
          </div>
        </aside>

        {/* Center / Right Phase Player Content Area */}
        <main className="flex-1 min-w-0 flex flex-col gap-6">
          {/* Active Cooldown Banner */}
          {cooldownRemaining !== null && cooldownRemaining > 0 && (
            <div className="p-4 rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-900 dark:text-amber-200 flex items-start gap-3">
              <Clock className="size-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-bold">Review Delay in Progress</p>
                <p className="text-xs text-amber-800 dark:text-amber-300 mt-0.5">
                  The phase trial did not meet the required threshold. Please review the technical
                  datasheets. You can retry this phase in:
                </p>
                <div className="mt-2 text-xl font-mono font-extrabold tabular-nums text-amber-700 dark:text-amber-300">
                  {formatTimer(cooldownRemaining)}
                </div>
              </div>
            </div>
          )}

          {/* Render Active Phase */}
          {isViewingCompleteStep ? (
            <CompleteStep
              preset={preset}
              attempt={attempt}
              cohortId={cohortId || "observer-cohort"}
              sessionId={sessionId}
              isObserverMode={isSimulated}
              onExitObserver={onExitObserver}
            />
          ) : currentPhase ? (
            <PhasePlayer
              cohortId={cohortId}
              preset={preset}
              phase={currentPhase}
              phaseIndex={viewingPhaseIndex}
              attempt={attempt}
              trials={trials.filter((t) => t.phase_id === currentPhase.id)}
              cooldownRemaining={cooldownRemaining}
              onOpenPdf={(doc) => setPdfModalDoc(doc)}
              onAdvancingNext={() => {
                if (viewingPhaseIndex + 1 < phases.length) {
                  setViewingPhaseIndex(viewingPhaseIndex + 1)
                } else {
                  setViewingPhaseIndex(phases.length)
                }
              }}
              isObserverMode={isSimulated}
              onObserverSubmit={handleObserverSubmit}
            />
          ) : null}
        </main>
      </div>

      {/* ── Slide-Over Datasheet & User Guide Drawer ─────────────────────────── */}
      {datasheetDrawerOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm animate-in fade-in-0 duration-200">
          <div className="w-full max-w-xl h-full bg-card border-l border-border shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-right duration-200">
            <div className="px-5 py-4 border-b border-border flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-foreground">Reference Datasheets &amp; Guides</h3>
                <p className="text-xs text-muted-foreground">
                  Browse module pinouts and hardware specifications anytime.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setDatasheetDrawerOpen(false)}
                className="p-1 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {preset.reference_attachments.map((doc) => (
                <div
                  key={doc.id || doc.url}
                  className="p-3.5 rounded-xl border border-border bg-card hover:border-primary/40 transition-colors flex items-center justify-between gap-3"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className="text-xs font-bold text-foreground truncate">{doc.title}</span>
                      {doc.subsystem_tag && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-primary/10 text-primary">
                          {doc.subsystem_tag}
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-muted-foreground capitalize">
                      {doc.doc_type?.replace("_", " ") || "Datasheet"}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setPdfModalDoc(doc)
                    }}
                    className="gap-1 text-xs shrink-0"
                  >
                    <Eye className="size-3.5" /> View PDF
                  </Button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Full-Page PDF Modal ──────────────────────────────────────────────── */}
      {pdfModalDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/75 backdrop-blur-sm animate-in fade-in-0 duration-200">
          <div className="w-full max-w-5xl h-[92vh] bg-card border border-border rounded-2xl shadow-2xl flex flex-col overflow-hidden">
            <div className="px-5 py-3 border-b border-border flex items-center justify-between bg-muted/40 shrink-0">
              <div className="min-w-0">
                <h3 className="text-sm font-bold text-foreground truncate">{pdfModalDoc.title}</h3>
                <p className="text-xs text-muted-foreground truncate">{pdfModalDoc.url}</p>
              </div>
              <button
                type="button"
                onClick={() => setPdfModalDoc(null)}
                className="p-1 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground shrink-0"
              >
                <X className="size-5" />
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4 bg-muted/20">
              <PdfViewer url={ensureAbsoluteUrl(pdfModalDoc.url)} className="h-full" />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Phase Dispatcher / Player ─────────────────────────────────────────────── */

function PhasePlayer({
  cohortId,
  preset,
  phase,
  phaseIndex,
  attempt: _attempt,
  trials,
  cooldownRemaining,
  onOpenPdf,
  onAdvancingNext,
  isObserverMode = false,
  onObserverSubmit,
}: {
  cohortId?: string
  preset: PreSessionQuizPreset
  phase: QuizPipelinePhase
  phaseIndex: number
  attempt: CohortPreQuizStatus["my_attempt"]
  trials: PhaseTrial[]
  cooldownRemaining: number | null
  onOpenPdf: (doc: ReferenceAttachment) => void
  onAdvancingNext: () => void
  isObserverMode?: boolean
  onObserverSubmit?: (body: PhaseTrialSubmitIn) => void
}) {
  const qc = useQueryClient()
  const toast = useToast()

  const submitMut = useMutation({
    mutationFn: (body: PhaseTrialSubmitIn) => {
      if (!cohortId) throw new Error("No cohort id")
      return submitCohortPhaseApi(cohortId, phase.id, body)
    },
    onSuccess: (data) => {
      if (cohortId) qc.invalidateQueries({ queryKey: ["cohort-pre-quiz-status", cohortId] })
      if (data.trial.passed) {
        toast.success(`Passed ${phase.title}! Score: ${data.trial.score_pct}%`)
        onAdvancingNext()
      } else {
        toast.error(`Did not meet ${phase.pass_percentage}% passing score. Review delay applied.`)
      }
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to submit phase trial")),
  })

  const handleSubmit = (body: PhaseTrialSubmitIn) => {
    if (isObserverMode && onObserverSubmit) {
      onObserverSubmit(body)
    } else {
      submitMut.mutate(body)
    }
  }

  const isSubmitting = isObserverMode ? false : submitMut.isPending
  const isPassed = trials.some((t) => t.passed)
  const isCooldownLocked = cooldownRemaining !== null && cooldownRemaining > 0

  return (
    <div className="flex flex-col gap-6">
      {/* Phase Header & Instructions Box */}
      <div className="p-5 rounded-2xl border border-border bg-card flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-primary/10 text-primary">
              Phase {phaseIndex + 1} of {preset.phases?.length ?? 0}
            </span>
            {isPassed && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
                <CheckCircle2 className="size-3" /> Passed
              </span>
            )}
            <h2 className="text-lg font-bold text-foreground">{phase.title}</h2>
          </div>
          {phase.subtitle && <p className="text-xs text-muted-foreground">{phase.subtitle}</p>}
        </div>

        {/* Phase Requirements Pill */}
        <div className="flex items-center gap-3 shrink-0 flex-wrap text-left md:text-right">
          <div className="text-left md:text-right">
            <p className="text-[11px] text-muted-foreground">Required Pass Score</p>
            <p className="text-sm font-bold text-foreground">{phase.pass_percentage}%</p>
          </div>
          {phase.cooldown_seconds > 0 && (
            <div className="text-left md:text-right pl-3 border-l border-border">
              <p className="text-[11px] text-muted-foreground">Review Delay on Fail</p>
              <p className="text-sm font-bold text-amber-600 dark:text-amber-400">
                {Math.round(phase.cooldown_seconds / 60)} min
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Instructions list if present */}
      {phase.instructions && phase.instructions.length > 0 && (
        <div className="p-4 rounded-xl border border-border bg-muted/20 space-y-2">
          <p className="text-xs font-bold text-foreground">
            What to do in this phase:
          </p>
          <ul className="text-xs text-muted-foreground space-y-1 list-disc list-inside">
            {phase.instructions.map((inst, i) => (
              <li key={i}>{inst}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Render Specific Phase Body */}
      {phase.phase_type === "explore_datasheets" && (
        <ExploreDatasheetsPhase
          preset={preset}
          onOpenPdf={onOpenPdf}
          isPassed={isPassed}
          isSubmitting={isSubmitting}
          onContinue={() => handleSubmit({ client_duration_seconds: 10 })}
        />
      )}

      {phase.phase_type === "subsystem_matching" && (
        <SubsystemMatchingPhase
          phase={phase}
          preset={preset}
          isPassed={isPassed}
          isCooldownLocked={isCooldownLocked}
          isSubmitting={isSubmitting}
          lastTrial={trials[trials.length - 1]}
          onOpenPdf={onOpenPdf}
          onSubmit={(placements, clientDuration) =>
            handleSubmit({
              matching_placements: placements,
              client_duration_seconds: clientDuration,
            })
          }
        />
      )}

      {phase.phase_type === "quiz" && (
        <QuizQuestionsPhase
          phase={phase}
          preset={preset}
          isPassed={isPassed}
          isCooldownLocked={isCooldownLocked}
          isSubmitting={isSubmitting}
          lastTrial={trials[trials.length - 1]}
          onOpenPdf={onOpenPdf}
          onSubmit={(answers, clientDuration) =>
            handleSubmit({
              answers,
              client_duration_seconds: clientDuration,
            })
          }
        />
      )}
    </div>
  )
}

/* ── Phase 1: Explore Datasheets ───────────────────────────────────────────── */

function ExploreDatasheetsPhase({
  preset,
  onOpenPdf,
  isPassed: _isPassed,
  isSubmitting,
  onContinue,
}: {
  preset: PreSessionQuizPreset
  onOpenPdf: (doc: ReferenceAttachment) => void
  isPassed: boolean
  isSubmitting: boolean
  onContinue: () => void
}) {
  const [search, setSearch] = useState("")
  const [filterType, setFilterType] = useState<"all" | "datasheet" | "user_guide">("all")

  const filteredDocs = useMemo(() => {
    return (preset.reference_attachments || []).filter((doc) => {
      const matchesSearch =
        !search.trim() ||
        doc.title.toLowerCase().includes(search.toLowerCase()) ||
        doc.subsystem_tag?.toLowerCase().includes(search.toLowerCase())
      const matchesType = filterType === "all" || (doc.doc_type || "datasheet") === filterType
      return matchesSearch && matchesType
    })
  }, [preset.reference_attachments, search, filterType])

  return (
    <div className="flex flex-col gap-5">
      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="relative w-full sm:w-80">
          <Search className="size-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search module datasheets..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-xl border border-border bg-card text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
        </div>

        <div className="flex items-center gap-1 bg-muted p-1 rounded-xl self-start sm:self-auto">
          {(["all", "datasheet", "user_guide"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setFilterType(t)}
              className={cn(
                "px-3 py-1 rounded-lg text-xs font-semibold capitalize transition-colors",
                filterType === t
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {t === "all" ? "All Documents" : t.replace("_", " ") + "s"}
            </button>
          ))}
        </div>
      </div>

      {/* Grid of First-Page PDF Preview Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {filteredDocs.map((doc) => (
          <div
            key={doc.id || doc.url}
            className="rounded-2xl border border-border bg-card overflow-hidden hover:border-primary/40 transition-all flex flex-col group shadow-sm"
          >
            {/* Top 1st-Page Thumbnail Preview Frame */}
            <div className="h-48 w-full bg-muted/40 relative overflow-hidden border-b border-border flex items-center justify-center">
              <PdfViewer
                url={ensureAbsoluteUrl(doc.url)}
                maxPages={1}
                hideControls
                className="w-full h-full pointer-events-none"
              />
              <div className="absolute inset-0 bg-background/80 backdrop-blur-xs opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center p-3">
                <Button
                  size="sm"
                  onClick={() => onOpenPdf(doc)}
                  className="w-full gap-1.5 text-xs shadow-md"
                >
                  <Eye className="size-3.5" /> Open Full PDF
                </Button>
              </div>
            </div>

            {/* Card Meta & Details */}
            <div className="p-4 flex-1 flex flex-col justify-between gap-3">
              <div>
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                    {doc.doc_type?.replace("_", " ") || "Datasheet"}
                  </span>
                  {doc.subsystem_tag && (
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-primary/10 text-primary">
                      {doc.subsystem_tag}
                    </span>
                  )}
                </div>
                <h3 className="text-xs font-bold text-foreground line-clamp-2">{doc.title}</h3>
              </div>

              <Button
                variant="outline"
                size="sm"
                onClick={() => onOpenPdf(doc)}
                className="w-full gap-1 text-xs"
              >
                View PDF <ChevronRight className="size-3.5" />
              </Button>
            </div>
          </div>
        ))}
      </div>

      {/* Bottom Action Footer */}
      <div className="pt-4 border-t border-border flex justify-end">
        <Button onClick={onContinue} disabled={isSubmitting} className="gap-2 px-6">
          {isSubmitting ? (
            <Spinner className="size-4" />
          ) : (
            <>
              <span>Continue to Next Phase</span>
              <ChevronRight className="size-4" />
            </>
          )}
        </Button>
      </div>
    </div>
  )
}

/* ── Phase 2: Subsystem Matching ───────────────────────────────────────────── */

function SubsystemMatchingPhase({
  phase,
  preset,
  isPassed: _isPassed,
  isCooldownLocked,
  isSubmitting,
  lastTrial,
  onOpenPdf,
  onSubmit,
}: {
  phase: QuizPipelinePhase
  preset: PreSessionQuizPreset
  isPassed: boolean
  isCooldownLocked: boolean
  isSubmitting: boolean
  lastTrial?: PhaseTrial
  onOpenPdf: (doc: ReferenceAttachment) => void
  onSubmit: (placements: Record<string, string>, duration: number) => void
}) {
  const matchingConfig = phase.matching_config
  const buckets = matchingConfig?.buckets || []
  const items = matchingConfig?.items || []

  // Map datasheet ID to bucket ID
  const [placements, setPlacements] = useState<Record<string, string>>({})
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const startTimeRef = useRef<number>(Date.now())

  // Reset timer on phase switch
  useEffect(() => {
    startTimeRef.current = Date.now()
  }, [phase.id])

  // Hydrate datasheet records
  const datasheetsMap = useMemo(() => {
    const map = new Map<string, ReferenceAttachment>()
    for (const doc of preset.reference_attachments || []) {
      if (doc.id) map.set(doc.id, doc)
    }
    return map
  }, [preset.reference_attachments])

  // Unplaced pool of module datasheets
  const unplacedItems = useMemo(() => {
    return items.filter((it) => !placements[it.datasheet_id])
  }, [items, placements])

  const handleDrop = (bucketId: string, datasheetId: string) => {
    if (isCooldownLocked) return
    setPlacements((prev) => ({
      ...prev,
      [datasheetId]: bucketId,
    }))
  }

  const handleRemove = (datasheetId: string) => {
    if (isCooldownLocked) return
    setPlacements((prev) => {
      const next = { ...prev }
      delete next[datasheetId]
      return next
    })
  }

  const handleSubmit = () => {
    const elapsed = Math.max(1, Math.round((Date.now() - startTimeRef.current) / 1000))
    onSubmit(placements, elapsed)
  }

  const allAssigned = items.length > 0 && Object.keys(placements).length === items.length

  const getBucketColorStyles = (color: string) => {
    switch (color) {
      case "emerald":
        return "border-emerald-500/40 bg-emerald-500/5 text-emerald-800 dark:text-emerald-300"
      case "blue":
        return "border-blue-500/40 bg-blue-500/5 text-blue-800 dark:text-blue-300"
      case "amber":
        return "border-amber-500/40 bg-amber-500/5 text-amber-800 dark:text-amber-300"
      case "cyan":
        return "border-cyan-500/40 bg-cyan-500/5 text-cyan-800 dark:text-cyan-300"
      case "purple":
      default:
        return "border-purple-500/40 bg-purple-500/5 text-purple-800 dark:text-purple-300"
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {/* ── Top Pool of Draggable Module Datasheets ─────────────────────────── */}
      <div className="p-5 rounded-2xl border border-border bg-card space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              Module Datasheets to Classify ({unplacedItems.length} Remaining)
            </h3>
            <p className="text-xs text-muted-foreground">
              Drag each card or choose a subsystem from the dropdown to assign.
            </p>
          </div>
          {unplacedItems.length > 0 && (
            <span className="text-xs text-amber-600 dark:text-amber-400 font-semibold">
              All modules must be assigned before submitting
            </span>
          )}
        </div>

        {unplacedItems.length === 0 ? (
          <div className="py-6 text-center text-xs text-muted-foreground border border-dashed border-border rounded-xl bg-muted/20">
            <CheckCircle2 className="size-5 text-emerald-500 mx-auto mb-1.5" />
            All module datasheets have been assigned to subsystem buckets! Review below and submit.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {unplacedItems.map((it) => {
              const doc = datasheetsMap.get(it.datasheet_id)
              const title = doc?.title || it.datasheet_id

              return (
                <div
                  key={it.datasheet_id}
                  draggable={!isCooldownLocked}
                  onDragStart={() => setDraggingId(it.datasheet_id)}
                  onDragEnd={() => setDraggingId(null)}
                  className={cn(
                    "p-3 rounded-xl border border-border bg-card shadow-sm cursor-grab active:cursor-grabbing hover:border-primary/50 transition-all flex flex-col justify-between gap-2.5",
                    draggingId === it.datasheet_id && "opacity-50 ring-2 ring-primary"
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <span className="text-[10px] font-bold text-muted-foreground uppercase">
                        Module Card
                      </span>
                      <h4 className="text-xs font-bold text-foreground line-clamp-2">{title}</h4>
                    </div>
                    <GripVertical className="size-4 text-muted-foreground shrink-0 mt-0.5" />
                  </div>

                  <div className="flex items-center justify-between gap-2 pt-1 border-t border-border">
                    {doc && (
                      <button
                        type="button"
                        onClick={() => onOpenPdf(doc)}
                        className="text-[11px] text-primary hover:underline font-medium inline-flex items-center gap-1"
                      >
                        <Eye className="size-3" /> View PDF
                      </button>
                    )}

                    {/* Touch / Click-to-assign fallback select */}
                    <select
                      value=""
                      onChange={(e) => {
                        if (e.target.value) handleDrop(e.target.value, it.datasheet_id)
                      }}
                      className="text-[11px] py-1 px-2 rounded-lg border border-border bg-background text-foreground"
                    >
                      <option value="">Move to...</option>
                      {buckets.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* ── Subsystem Drop Zones ────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {buckets.map((b) => {
          const droppedIds = Object.keys(placements).filter((dsId) => placements[dsId] === b.id)
          const targetCount = items.filter((it) => it.correct_bucket_id === b.id).length
          const colorStyles = getBucketColorStyles(b.color)

          return (
            <div
              key={b.id}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault()
                if (draggingId) handleDrop(b.id, draggingId)
              }}
              className={cn(
                "rounded-2xl border-2 p-4 flex flex-col justify-between gap-3 min-h-[220px] transition-colors",
                colorStyles
              )}
            >
              <div>
                <div className="flex items-center justify-between gap-2 mb-1">
                  <h4 className="text-sm font-extrabold tracking-wide uppercase">{b.label}</h4>
                  {phase.show_bucket_target_counts ? (
                    <span className="text-xs font-mono font-bold">
                      {droppedIds.length} / {targetCount} modules
                    </span>
                  ) : (
                    <span className="text-xs font-mono font-bold">
                      {droppedIds.length} assigned
                    </span>
                  )}
                </div>
                {b.subtitle && <p className="text-[11px] opacity-80 mb-3">{b.subtitle}</p>}

                {/* Dropped Module Cards */}
                <div className="space-y-2">
                  {droppedIds.map((dsId) => {
                    const doc = datasheetsMap.get(dsId)
                    const title = doc?.title || dsId
                    const trialResult = lastTrial?.payload?.results?.[dsId]

                    return (
                      <div
                        key={dsId}
                        className={cn(
                          "p-2.5 rounded-xl border bg-card text-foreground shadow-sm flex items-center justify-between gap-2 text-xs",
                          trialResult?.is_correct === true && "border-emerald-500 bg-emerald-500/10",
                          trialResult?.is_correct === false && "border-red-500 bg-red-500/10"
                        )}
                      >
                        <span className="truncate font-medium">{title}</span>
                        <div className="flex items-center gap-1 shrink-0">
                          {doc && (
                            <button
                              type="button"
                              onClick={() => onOpenPdf(doc)}
                              className="p-1.5 sm:p-1 text-muted-foreground hover:text-foreground rounded-lg hover:bg-muted"
                              title="View PDF"
                            >
                              <Eye className="size-4 sm:size-3.5" />
                            </button>
                          )}
                          {!isCooldownLocked && (
                            <button
                              type="button"
                              onClick={() => handleRemove(dsId)}
                              className="p-1.5 sm:p-1 text-muted-foreground hover:text-destructive rounded-lg hover:bg-destructive/10"
                              title="Remove from bucket"
                            >
                              <X className="size-4 sm:size-3.5" />
                            </button>
                          )}
                        </div>
                      </div>
                    )
                  })}

                  {droppedIds.length === 0 && (
                    <div className="py-8 text-center text-xs opacity-60 border border-dashed border-current/30 rounded-xl">
                      Drag modules here
                    </div>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Bottom Submit Footer */}
      <div className="pt-4 border-t border-border flex items-center justify-between gap-4">
        <p className="text-xs text-muted-foreground">
          {Object.keys(placements).length} of {items.length} modules placed
        </p>

        <Button
          onClick={handleSubmit}
          disabled={!allAssigned || isCooldownLocked || isSubmitting}
          className="gap-2 px-6"
        >
          {isSubmitting ? (
            <Spinner className="size-4" />
          ) : (
            <>
              <span>Submit Answer</span>
              <ChevronRight className="size-4" />
            </>
          )}
        </Button>
      </div>
    </div>
  )
}

/* ── Phases 3, 4, 5: Question Bank Quiz (Pinout, Addressing, Scenarios) ───── */

function QuizQuestionsPhase({
  phase,
  preset,
  isPassed: _isPassed,
  isCooldownLocked,
  isSubmitting,
  lastTrial,
  onOpenPdf: _onOpenPdf,
  onSubmit,
}: {
  phase: QuizPipelinePhase
  preset: PreSessionQuizPreset
  isPassed: boolean
  isCooldownLocked: boolean
  isSubmitting: boolean
  lastTrial?: PhaseTrial
  onOpenPdf: (doc: ReferenceAttachment) => void
  onSubmit: (answers: PreSessionQuizAnswerIn[], duration: number) => void
}) {
  const phaseQuestionIds = useMemo(() => new Set(phase.question_ids || []), [phase.question_ids])
  const questions = useMemo(() => {
    return (preset.questions || []).filter((q) => phaseQuestionIds.has(q.id))
  }, [preset.questions, phaseQuestionIds])

  const [answersByQid, setAnswersByQid] = useState<Record<string, PreSessionQuizAnswerIn>>({})
  const startTimeRef = useRef<number>(Date.now())

  useEffect(() => {
    startTimeRef.current = Date.now()
  }, [phase.id])

  // Hydrate answers from last trial if available
  useEffect(() => {
    if (lastTrial?.payload?.answers) {
      const map: Record<string, PreSessionQuizAnswerIn> = {}
      for (const a of lastTrial.payload.answers) {
        map[a.question_id] = {
          question_id: a.question_id,
          selected_option_index: a.selected_option_index,
          selected_cells: a.selected_cells,
          chose_other: a.chose_other,
          other_text: a.other_text,
          written_text: a.written_text,
        }
      }
      setAnswersByQid(map)
    }
  }, [lastTrial])

  const handleCellToggle = (qid: string, rowIndex: number, cellIndex: number) => {
    if (isCooldownLocked) return
    setAnswersByQid((prev) => {
      const current = prev[qid] || { question_id: qid }
      const currentCells = current.selected_cells ? [...current.selected_cells] : []
      while (currentCells.length <= rowIndex) {
        currentCells.push([])
      }
      const row = currentCells[rowIndex] ? [...currentCells[rowIndex]] : []
      const existingIdx = row.indexOf(cellIndex)
      if (existingIdx >= 0) {
        row.splice(existingIdx, 1)
      } else {
        row.push(cellIndex)
      }
      currentCells[rowIndex] = row
      return {
        ...prev,
        [qid]: {
          ...current,
          selected_cells: currentCells,
        },
      }
    })
  }

  const handleSubmit = () => {
    const elapsed = Math.max(1, Math.round((Date.now() - startTimeRef.current) / 1000))
    const answersList = questions.map((q) => answersByQid[q.id] || { question_id: q.id })
    onSubmit(answersList, elapsed)
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Question Cards List */}
      <div className="space-y-6">
        {questions.map((q, qIndex) => {
          const ans = answersByQid[q.id] || { question_id: q.id }
          const trialAnswer = lastTrial?.payload?.answers?.find((a: any) => a.question_id === q.id)

          return (
            <div
              key={q.id}
              className={cn(
                "p-5 rounded-2xl border border-border bg-card space-y-4 shadow-sm",
                trialAnswer?.status === "correct" && "border-emerald-500/40 bg-emerald-500/5",
                trialAnswer?.status === "incorrect" && "border-red-500/40 bg-red-500/5"
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                    Question {qIndex + 1} of {questions.length} · {q.topic}
                  </span>
                  <h3 className="text-sm font-bold text-foreground mt-0.5">{q.title}</h3>
                </div>
                {trialAnswer && (
                  <span
                    className={cn(
                      "px-2 py-0.5 rounded-full text-[10px] font-bold uppercase",
                      trialAnswer.status === "correct" && "bg-emerald-500/15 text-emerald-600",
                      trialAnswer.status === "incorrect" && "bg-red-500/15 text-red-600",
                      trialAnswer.status === "pending_review" && "bg-amber-500/15 text-amber-600"
                    )}
                  >
                    {trialAnswer.status.replace("_", " ")}
                  </span>
                )}
              </div>

              <p className="text-xs text-foreground whitespace-pre-line leading-relaxed">
                {q.prompt}
              </p>

              {/* Pinout Table Widget */}
              {q.question_type === "pinout_table" && q.table_config && (
                <div className="overflow-x-auto pt-2">
                  <ConnectorTableWidget
                    config={q.table_config}
                    selectedCells={ans.selected_cells || []}
                    onToggleCell={(r: number, c: number) => handleCellToggle(q.id, r, c)}
                    disabled={isCooldownLocked}
                    mode={trialAnswer && phase.show_correct_on_fail ? "review" : "interactive"}
                  />
                </div>
              )}

              {/* MCQ Options */}
              {q.question_type === "mcq" && (
                <div className="space-y-2 pt-2">
                  {(q.options || []).map((opt, optIdx) => (
                    <button
                      key={optIdx}
                      type="button"
                      disabled={isCooldownLocked}
                      onClick={() =>
                        setAnswersByQid((prev) => ({
                          ...prev,
                          [q.id]: {
                            ...prev[q.id],
                            question_id: q.id,
                            selected_option_index: optIdx,
                            chose_other: false,
                          },
                        }))
                      }
                      className={cn(
                        "w-full text-left p-3 rounded-xl border text-xs transition-colors flex items-center justify-between gap-3 cursor-pointer disabled:cursor-not-allowed",
                        ans.selected_option_index === optIdx && !ans.chose_other
                          ? "border-primary bg-primary/10 text-foreground font-semibold ring-1 ring-primary/20"
                          : "border-border bg-card hover:bg-muted/50 text-muted-foreground"
                      )}
                    >
                      <span>{opt.text}</span>
                      <div
                        className={cn(
                          "size-4 rounded-full border flex items-center justify-center shrink-0",
                          ans.selected_option_index === optIdx && !ans.chose_other
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-muted-foreground/40"
                        )}
                      >
                        {ans.selected_option_index === optIdx && !ans.chose_other && (
                          <div className="size-1.5 rounded-full bg-white" />
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              )}

              {/* Written Answer Input */}
              {q.question_type === "written" && (
                <div className="pt-2">
                  <textarea
                    rows={4}
                    disabled={isCooldownLocked}
                    placeholder="Enter your detailed technical explanation here..."
                    value={ans.written_text || ""}
                    onChange={(e) =>
                      setAnswersByQid((prev) => ({
                        ...prev,
                        [q.id]: {
                          ...prev[q.id],
                          question_id: q.id,
                          written_text: e.target.value,
                        },
                      }))
                    }
                    className="w-full p-3 rounded-xl border border-border bg-background text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                </div>
              )}

              {/* "Other (Write Explanation)" Option */}
              {q.allow_other && (
                <div className="pt-3 border-t border-border space-y-2">
                  <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-foreground">
                    <input
                      type="checkbox"
                      disabled={isCooldownLocked}
                      checked={Boolean(ans.chose_other)}
                      onChange={(e) =>
                        setAnswersByQid((prev) => ({
                          ...prev,
                          [q.id]: {
                            ...prev[q.id],
                            question_id: q.id,
                            chose_other: e.target.checked,
                          },
                        }))
                      }
                      className="rounded border-border text-primary focus:ring-primary size-4"
                    />
                    <span>Other — Flag Datasheet Discrepancy or Alternate Route</span>
                  </label>

                  {ans.chose_other && (
                    <input
                      type="text"
                      disabled={isCooldownLocked}
                      placeholder="Specify the reason or datasheet discrepancy..."
                      value={ans.other_text || ""}
                      onChange={(e) =>
                        setAnswersByQid((prev) => ({
                          ...prev,
                          [q.id]: {
                            ...prev[q.id],
                            question_id: q.id,
                            other_text: e.target.value,
                          },
                        }))
                      }
                      className="w-full px-3 py-2 rounded-xl border border-border bg-background text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
                    />
                  )}
                </div>
              )}
            </div>
          )
        })}
        </div>

        {/* Submit Button Footer */}
        <div className="pt-4 border-t border-border flex justify-end">
          <Button
            onClick={handleSubmit}
            disabled={isCooldownLocked || isSubmitting}
            className="gap-2 px-6"
          >
            {isSubmitting ? (
              <Spinner className="size-4" />
            ) : (
              <>
                <span>Submit Answers</span>
                <ChevronRight className="size-4" />
              </>
            )}
          </Button>
        </div>
      </div>
  )
}

/* ── Completion Step ───────────────────────────────────────────────────────── */

function CompleteStep({
  preset,
  attempt,
  cohortId: _cohortId,
  sessionId,
  isObserverMode = false,
  onExitObserver,
}: {
  preset: PreSessionQuizPreset
  attempt: CohortPreQuizStatus["my_attempt"]
  cohortId: string
  sessionId?: string
  isObserverMode?: boolean
  onExitObserver?: () => void
}) {
  const navigate = useNavigate()

  return (
    <div className="max-w-2xl mx-auto py-12 px-4 text-center space-y-6">
      <div className="size-16 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 mx-auto flex items-center justify-center">
        <CheckCircle2 className="size-8" />
      </div>

      <div className="space-y-2">
        <h2 className="text-2xl font-extrabold text-foreground">
          {isObserverMode ? "Observer Preview: Pipeline Completed!" : "Cohort Readiness Pipeline Passed!"}
        </h2>
        <p className="text-sm text-muted-foreground max-w-lg mx-auto">
          {isObserverMode
            ? `You have successfully tested and completed all phases of ${preset.name}. In live delivery, completing this unlocks session start for the entire cohort.`
            : `Congratulations! You have satisfied all prerequisite phases of ${preset.name}. Delivery access has been unlocked for all sessions in this cohort.`}
        </p>
      </div>

      {/* Summary Metrics Grid */}
      <div className="grid grid-cols-3 gap-3 p-4 rounded-2xl border border-border bg-card text-center">
        <div>
          <p className="text-[11px] text-muted-foreground">Phases Completed</p>
          <p className="text-lg font-bold text-foreground">{preset.phases?.length ?? 0}</p>
        </div>
        <div className="border-x border-border">
          <p className="text-[11px] text-muted-foreground">Score</p>
          <p className="text-lg font-bold text-emerald-600 dark:text-emerald-400">
            {attempt?.final_score ?? 0} / {attempt?.total_questions ?? 0}
          </p>
        </div>
        <div>
          <p className="text-[11px] text-muted-foreground">Total Active Time</p>
          <p className="text-lg font-bold text-foreground">
            {Math.round((attempt?.total_duration_seconds ?? 0) / 60)} min
          </p>
        </div>
      </div>

      <div className="pt-4 flex justify-center gap-3">
        {isObserverMode && onExitObserver ? (
          <Button
            size="lg"
            onClick={onExitObserver}
            className="gap-2 px-8 font-bold bg-primary text-primary-foreground"
          >
            <span>Exit Observer Mode</span>
            <ChevronRight className="size-4" />
          </Button>
        ) : sessionId ? (
          <Button
            size="lg"
            onClick={() => navigate({ to: `/instructors/sessions/${sessionId}` })}
            className="gap-2 px-8 font-bold"
          >
            <span>Return to Session &amp; Start Delivery</span>
            <ChevronRight className="size-4" />
          </Button>
        ) : (
          <Button
            size="lg"
            onClick={() => navigate({ to: "/instructors/dashboard" })}
            className="gap-2 px-8 font-bold"
          >
            <span>Go to Instructor Dashboard</span>
            <ChevronRight className="size-4" />
          </Button>
        )}
      </div>
    </div>
  )
}
