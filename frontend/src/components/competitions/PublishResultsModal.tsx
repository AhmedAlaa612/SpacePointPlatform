import { useEffect, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  publishCohortResultsApi,
  updateCohortPublicationSettingsApi,
  type CompetitionVisibilitySettings,
} from "@/api/competitions"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"
import { Award, Eye, FileText, Layers, MessageSquare, ShieldCheck, Trophy } from "lucide-react"

interface PublishResultsModalProps {
  cohortId: string
  open: boolean
  onClose: () => void
  isPublished?: boolean
  currentSettings?: CompetitionVisibilitySettings | null
}

const DEFAULT_SETTINGS: CompetitionVisibilitySettings = {
  show_score: true,
  show_rank: true,
  show_breakdown: true,
  show_ops_criteria: true,
  show_ops_comments: true,
  show_judge_comments: true,
}

export function PublishResultsModal({
  cohortId,
  open,
  onClose,
  isPublished = false,
  currentSettings,
}: PublishResultsModalProps) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [settings, setSettings] = useState<CompetitionVisibilitySettings>(DEFAULT_SETTINGS)

  useEffect(() => {
    if (open) {
      if (currentSettings) {
        setSettings({
          show_score: currentSettings.show_score ?? true,
          show_rank: currentSettings.show_rank ?? true,
          show_breakdown: currentSettings.show_breakdown ?? true,
          show_ops_criteria: currentSettings.show_ops_criteria ?? true,
          show_ops_comments: currentSettings.show_ops_comments ?? true,
          show_judge_comments: currentSettings.show_judge_comments ?? true,
        })
      } else {
        setSettings(DEFAULT_SETTINGS)
      }
    }
  }, [open, currentSettings])

  const toggle = (key: keyof CompetitionVisibilitySettings) => {
    setSettings((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const setAll = (val: boolean) => {
    setSettings({
      show_score: val,
      show_rank: val,
      show_breakdown: val,
      show_ops_criteria: val,
      show_ops_comments: val,
      show_judge_comments: val,
    })
  }

  const invalidateQueries = () => {
    queryClient.invalidateQueries({ queryKey: ["competitions-publication", cohortId] })
    queryClient.invalidateQueries({ queryKey: ["competitions-leaderboard", cohortId] })
    queryClient.invalidateQueries({ queryKey: ["competitions-student-result", cohortId] })
  }

  const publishMutation = useMutation({
    mutationFn: () => publishCohortResultsApi(cohortId, settings),
    onSuccess: () => {
      toast.success("Results published with chosen visibility settings")
      invalidateQueries()
      onClose()
    },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Failed to publish results")),
  })

  const updateSettingsMutation = useMutation({
    mutationFn: () => updateCohortPublicationSettingsApi(cohortId, settings),
    onSuccess: () => {
      toast.success("Visibility settings updated")
      invalidateQueries()
      onClose()
    },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Failed to update visibility settings")),
  })

  const isPending = publishMutation.isPending || updateSettingsMutation.isPending

  const handleSave = () => {
    if (isPublished) {
      updateSettingsMutation.mutate()
    } else {
      publishMutation.mutate()
    }
  }

  const options: Array<{
    key: keyof CompetitionVisibilitySettings
    title: string
    description: string
    icon: typeof Trophy
  }> = [
    {
      key: "show_score",
      title: "Total Score & Percentage",
      description: "Show final evaluation score and percentage calculation on the student's result card.",
      icon: Award,
    },
    {
      key: "show_rank",
      title: "Team Rank & Cohort Standings",
      description: "Display the team's placement (e.g. Rank #3 of 24) among all cohort teams.",
      icon: Trophy,
    },
    {
      key: "show_breakdown",
      title: "Rubric Criteria Breakdown",
      description: "Show the average score points awarded across all judges for each rubric criterion.",
      icon: Layers,
    },
    {
      key: "show_ops_criteria",
      title: "Operations Criteria Scores",
      description: "Display scores evaluated by the operations team for operations-specific criteria.",
      icon: ShieldCheck,
    },
    {
      key: "show_ops_comments",
      title: "Operations Feedback & Comments",
      description: "Include notes and feedback written by the operations team for each team.",
      icon: MessageSquare,
    },
    {
      key: "show_judge_comments",
      title: "Judges' Qualitative Comments",
      description: "Show anonymized comments and qualitative feedback submitted by judges.",
      icon: FileText,
    },
  ]

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-xl p-6 bg-card border-border">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-xl bg-primary/10 text-primary">
              <Eye size={20} />
            </div>
            <div>
              <DialogTitle className="text-lg font-bold text-foreground">
                {isPublished ? "Result Visibility Settings" : "Publish Competition Results"}
              </DialogTitle>
              <p className="text-xs text-muted-foreground mt-0.5">
                {isPublished
                  ? "Configure which score components and feedback students can see on their result page."
                  : "Choose what information is visible to students upon publishing. You can edit this anytime."}
              </p>
            </div>
          </div>
        </DialogHeader>

        <div className="mt-4 flex flex-col gap-3">
          <div className="flex items-center justify-between pb-1 border-b border-border/60">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Student Visibility Options
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setAll(true)}
                className="text-xs text-primary hover:underline font-medium"
              >
                Select all
              </button>
              <span className="text-muted-foreground text-xs">·</span>
              <button
                type="button"
                onClick={() => setAll(false)}
                className="text-xs text-muted-foreground hover:text-foreground font-medium"
              >
                Deselect all
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-2.5 max-h-[60vh] overflow-y-auto pr-1">
            {options.map((opt) => {
              const Icon = opt.icon
              const checked = !!settings[opt.key]
              return (
                <label
                  key={opt.key}
                  className={`flex items-start gap-3 p-3 rounded-xl border transition-all cursor-pointer select-none ${
                    checked
                      ? "bg-primary/5 border-primary/30"
                      : "bg-card border-border hover:bg-muted/30 opacity-75"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(opt.key)}
                    className="mt-1 h-4 w-4 rounded border-border text-primary focus:ring-primary accent-primary"
                  />
                  <div className="flex items-start gap-2.5 flex-1 min-w-0">
                    <div
                      className={`p-1.5 rounded-lg shrink-0 mt-0.5 ${
                        checked ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
                      }`}
                    >
                      <Icon size={16} />
                    </div>
                    <div className="flex flex-col gap-0.5">
                      <span className="text-sm font-semibold text-foreground leading-tight">
                        {opt.title}
                      </span>
                      <span className="text-xs text-muted-foreground leading-normal">
                        {opt.description}
                      </span>
                    </div>
                  </div>
                </label>
              )
            })}
          </div>

          <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-border mt-1">
            <button
              type="button"
              onClick={onClose}
              disabled={isPending}
              className="h-10 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={isPending}
              className="h-10 px-5 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
            >
              {isPending
                ? "Saving…"
                : isPublished
                ? "Save visibility settings"
                : "Publish results"}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
