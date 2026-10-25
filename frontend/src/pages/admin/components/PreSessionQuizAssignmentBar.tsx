import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import {
  getPreQuizAssignmentApi,
  listPreQuizPresetsApi,
  setPreQuizAssignmentApi,
  type PreQuizScope,
} from "@/api/sessions/pre_session_quiz"
import { SessionPreQuizModal } from "@/pages/instructors/components/SessionPreQuizModal"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

export function PreSessionQuizAssignmentBar({
  scope,
  ownerId,
  dayTitle,
}: {
  scope: PreQuizScope
  ownerId: string
  dayTitle?: string
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [previewOpen, setPreviewOpen] = useState(false)

  const { data: presets = [] } = useQuery({
    queryKey: ["pre-quiz-presets"],
    queryFn: () => listPreQuizPresetsApi(false),
  })

  const { data: assignment, isLoading } = useQuery({
    queryKey: ["pre-quiz-assignment", scope, ownerId],
    queryFn: () => getPreQuizAssignmentApi(scope, ownerId),
    enabled: Boolean(ownerId),
  })

  const saveMut = useMutation({
    mutationFn: ({ preset_id, clear_override }: { preset_id: string | null; clear_override?: boolean }) =>
      setPreQuizAssignmentApi(scope, ownerId, preset_id, Boolean(clear_override)),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["pre-quiz-assignment"] })
      qc.invalidateQueries({ queryKey: ["session-pre-quiz-status"] })
      if (res.preset_name) {
        toast.success(`Assigned pre-session quiz: ${res.preset_name}`)
      } else {
        toast.success("Pre-session quiz updated")
      }
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to update pre-session quiz")),
  })

  const scopeLabel =
    scope === "programs"
      ? "Program Default"
      : scope === "cohorts"
        ? "Cohort Default"
        : dayTitle || "This Session"

  const selectedPreset = presets.find((p) => p.id === assignment?.preset_id) ?? null

  return (
    <div className="p-3 sm:p-3.5 rounded-xl border border-primary/25 bg-primary/5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-bold text-foreground">
            Pre-Session Instructor Quiz ({scopeLabel})
          </span>
          {assignment?.inherited && assignment.level !== "none" && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30">
              Inherited from {assignment.level}
            </span>
          )}
          {assignment && !assignment.inherited && assignment.level !== "none" && scope !== "programs" && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-primary/15 text-primary border border-primary/30">
              Custom override
            </span>
          )}
        </div>
        <p className="text-[11px] text-muted-foreground mt-0.5">
          {assignment?.preset_name
            ? `Assigned preset: "${assignment.preset_name}" · Required before instructor can start the session · Unlocks Start Session immediately on submit.`
            : "Optional — assign a hardware pinout / readiness quiz preset that instructors must complete before starting the session."}
        </p>
      </div>

      <div className="flex items-center gap-2 flex-wrap sm:shrink-0">
        <select
          disabled={isLoading || saveMut.isPending}
          value={assignment?.preset_id ?? ""}
          onChange={(e) => {
            const val = e.target.value
            saveMut.mutate({ preset_id: val ? val : null, clear_override: false })
          }}
          className="h-8 px-2.5 rounded-lg border border-border bg-background text-xs font-medium text-foreground focus:outline-none focus:border-primary max-w-[260px]"
        >
          <option value="">None (No pre-session quiz)</option>
          {presets.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.questions.length} Qs)
            </option>
          ))}
        </select>

        {selectedPreset && (
          <button
            type="button"
            onClick={() => setPreviewOpen(true)}
            title="Preview exact instructor quiz experience"
            className="h-8 px-2.5 rounded-lg border border-primary/40 bg-primary/10 hover:bg-primary/20 text-[11px] font-semibold text-primary inline-flex items-center cursor-pointer shrink-0"
          >
            Preview Quiz
          </button>
        )}

        {assignment && !assignment.inherited && scope !== "programs" && (
          <button
            type="button"
            disabled={saveMut.isPending}
            onClick={() => saveMut.mutate({ preset_id: null, clear_override: true })}
            title="Reset to inherited Program / Cohort setting"
            className="h-8 px-2.5 rounded-lg border border-border bg-card hover:bg-muted text-[11px] font-medium text-muted-foreground hover:text-foreground inline-flex items-center cursor-pointer"
          >
            Reset to Inherited
          </button>
        )}

        <Link
          to="/instructors/facilitator/quizzes"
          className="h-8 px-2.5 rounded-lg border border-border bg-card hover:bg-muted text-[11px] font-semibold text-primary inline-flex items-center shrink-0"
        >
          Quiz Bank
        </Link>
      </div>

      {selectedPreset && (
        <SessionPreQuizModal
          open={previewOpen}
          onClose={() => setPreviewOpen(false)}
          isPreview
          quizStatus={{
            has_quiz: true,
            preset: selectedPreset,
            my_attempt: null,
            all_attempts: [],
          }}
        />
      )}
    </div>
  )
}
