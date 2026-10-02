import { useEffect, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  putTeamOperationsScoreApi,
  type CompetitionLeaderboardRow,
  type CompetitionRubric,
} from "@/api/competitions"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

interface TeamOperationsScoreModalProps {
  cohortId: string
  team: CompetitionLeaderboardRow | null
  rubric: CompetitionRubric | null
  open: boolean
  onClose: () => void
}

const leafKey = (parent: string, sub: string) => `${parent}.${sub}`

/** Operations grades its own rubric criteria and leaves feedback/comments for one team.
 * Even if the rubric has no operations-specific criteria, operations can leave
 * team-specific feedback here prior to publishing. Judge averages are untouched. */
export function TeamOperationsScoreModal({ cohortId, team, rubric, open, onClose }: TeamOperationsScoreModalProps) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [scores, setScores] = useState<Record<string, number>>({})
  const [notes, setNotes] = useState("")

  const operationsCriteria =
    rubric?.criteria.filter((c) => (c.scored_by ?? "judge") === "operations") ?? []

  useEffect(() => {
    if (!open || !team) return
    const saved = team.ops_criterion_scores ?? {}
    const next: Record<string, number> = {}
    for (const c of operationsCriteria) {
      const subs = c.sub_criteria ?? []
      if (subs.length > 0) {
        for (const s of subs) next[leafKey(c.key, s.key)] = Number(saved[leafKey(c.key, s.key)] ?? 0)
      } else {
        next[c.key] = Number(saved[c.key] ?? 0)
      }
    }
    setScores(next)
    setNotes(team.ops_criterion_notes ?? "")
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, team?.team_id])

  const saveMutation = useMutation({
    mutationFn: () =>
      putTeamOperationsScoreApi(cohortId, team!.team_id, {
        criterion_scores: scores,
        notes: notes.trim() || null,
      }),
    onSuccess: () => {
      toast.success(`Operations evaluation saved for ${team?.team_name}`)
      queryClient.invalidateQueries({ queryKey: ["competitions-leaderboard", cohortId] })
      queryClient.invalidateQueries({ queryKey: ["competitions-top20", cohortId] })
      queryClient.invalidateQueries({ queryKey: ["competitions-team-breakdown", cohortId, team?.team_id] })
      queryClient.invalidateQueries({ queryKey: ["competitions-student-result", cohortId] })
      onClose()
    },
    onError: (e: unknown) => toast.error(getErrorMessage(e, "Failed to save operations evaluation")),
  })

  if (!open || !team) return null

  const parentTotal = (criterionKey: string, subs: { key: string }[]) =>
    subs.reduce((s, sub) => s + (Number(scores[leafKey(criterionKey, sub.key)]) || 0), 0)

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg p-6 bg-card border-border">
        <DialogHeader>
          <DialogTitle className="text-lg font-bold text-foreground">
            Operations & Feedback — {team.team_name}
          </DialogTitle>
          <p className="text-xs text-muted-foreground mt-0.5">
            Operations rubric scores and qualitative comments for this team. Judges' scores are unaffected.
          </p>
        </DialogHeader>

        <div className="mt-4 flex flex-col gap-4">
          {operationsCriteria.length === 0 ? (
            <div className="p-3 bg-muted/40 border border-border/70 rounded-xl text-xs text-muted-foreground">
              This rubric does not include operations criteria. You can still add comments and feedback for this team below.
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Operations Criteria
              </span>
              {operationsCriteria.map((c) => {
                const subs = c.sub_criteria ?? []
                if (subs.length === 0) {
                  return (
                    <div key={c.key} className="flex items-center gap-3">
                      <label className="flex-1 text-sm text-foreground">{c.label}</label>
                      <input
                        type="number" min={0} max={c.max_points}
                        value={scores[c.key] ?? 0}
                        onChange={(e) => setScores((s) => ({ ...s, [c.key]: Number(e.target.value) }))}
                        className="w-20 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
                      />
                      <span className="w-16 text-xs text-muted-foreground">/ {c.max_points}</span>
                    </div>
                  )
                }
                const computed = parentTotal(c.key, subs)
                return (
                  <div key={c.key} className="flex flex-col gap-1.5 border border-border rounded-xl p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium text-foreground">{c.label}</span>
                      <span className="text-xs text-muted-foreground tabular-nums">
                        <span className="font-semibold text-foreground">{computed}</span> / {c.max_points} · auto
                      </span>
                    </div>
                    {subs.map((sub) => (
                      <div key={sub.key} className="flex items-center gap-3 pl-4">
                        <label className="flex-1 text-sm text-muted-foreground">{sub.label}</label>
                        <input
                          type="number" min={0} max={sub.max_points}
                          value={scores[leafKey(c.key, sub.key)] ?? 0}
                          onChange={(e) =>
                            setScores((s) => ({ ...s, [leafKey(c.key, sub.key)]: Number(e.target.value) }))
                          }
                          className="w-20 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
                        />
                        <span className="w-16 text-xs text-muted-foreground">/ {sub.max_points}</span>
                      </div>
                    ))}
                  </div>
                )
              })}
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Operations Feedback & Comments
              </span>
              <span className="text-[11px] text-muted-foreground">Visible to team if enabled</span>
            </div>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add feedback, notes, or instructions for this team..."
              rows={4}
              className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary resize-y"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-border/60">
            <button
              type="button"
              onClick={onClose}
              className="h-10 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="h-10 px-5 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
            >
              {saveMutation.isPending
                ? "Saving…"
                : operationsCriteria.length > 0
                ? "Save score & comments"
                : "Save comments"}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
