import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Clock, RotateCcw, Save } from "lucide-react"
import {
  updateTeamTimingAdjustmentApi,
  getTeamScoreBreakdownApi,
  type CompetitionLeaderboardRow,
} from "@/api/competitions"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useToast } from "@/components/ui/toast"

interface TimingOverrideModalProps {
  cohortId: string
  team: CompetitionLeaderboardRow | null
  open: boolean
  onClose: () => void
}

export function TimingOverrideModal({ cohortId, team, open, onClose }: TimingOverrideModalProps) {
  const toast = useToast()
  const queryClient = useQueryClient()

  const [pointsStr, setPointsStr] = useState<string>("")
  const [notes, setNotes] = useState<string>("")

  const { data: breakdown } = useQuery({
    queryKey: ["competitions-team-breakdown", cohortId, team?.team_id],
    queryFn: () => getTeamScoreBreakdownApi(cohortId, team!.team_id),
    enabled: open && !!team,
  })

  useEffect(() => {
    if (team) {
      setPointsStr(
        team.is_timing_override && team.timing_adjustment !== undefined && team.timing_adjustment !== null
          ? String(team.timing_adjustment)
          : ""
      )
      setNotes(team.timing_override_notes || "")
    }
  }, [team])

  const mutation = useMutation({
    mutationFn: (overrideData: { override_points: number | null; notes: string | null }) =>
      updateTeamTimingAdjustmentApi(cohortId, team!.team_id, overrideData),
    onSuccess: () => {
      toast.success("Timing adjustment updated")
      queryClient.invalidateQueries({ queryKey: ["competitions-leaderboard", cohortId] })
      queryClient.invalidateQueries({ queryKey: ["competitions-team-breakdown", cohortId, team?.team_id] })
      onClose()
    },
    onError: () => {
      toast.error("Failed to update timing adjustment")
    },
  })

  if (!open || !team) return null

  const handleSaveOverride = (e: React.FormEvent) => {
    e.preventDefault()
    const val = parseFloat(pointsStr)
    if (isNaN(val)) {
      toast.error("Please enter a valid numeric points value (e.g. 5, -2, 0)")
      return
    }
    mutation.mutate({
      override_points: val,
      notes: notes.trim() || null,
    })
  }

  const handleResetToAuto = () => {
    mutation.mutate({
      override_points: null,
      notes: null,
    })
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md p-6 bg-card border-border">
        <DialogHeader>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded-full">
              Operations Control
            </span>
            {team.is_timing_override && (
              <span className="text-[10px] font-bold uppercase tracking-wider text-purple-400 bg-purple-500/10 border border-purple-500/30 px-2 py-0.5 rounded-full">
                Currently Overridden
              </span>
            )}
          </div>
          <DialogTitle className="text-lg font-bold font-display text-foreground">
            Timing Adjustment — {team.team_name}
          </DialogTitle>
          <p className="text-xs text-muted-foreground mt-0.5">
            Manually override or waive submission bonus/deduction points for this team.
          </p>
        </DialogHeader>

        <div className="mt-4 space-y-4">
          {/* Audit Timestamp Card */}
          <div className="p-3 rounded-xl bg-muted/30 border border-border text-xs space-y-1.5">
            <div className="flex justify-between items-center text-muted-foreground">
              <span className="flex items-center gap-1">
                <Clock size={12} className="text-primary" />
                Final Lock Time:
              </span>
              <span className="font-mono text-foreground font-semibold">
                {team.final_locked_at ? new Date(team.final_locked_at).toLocaleString() : "Not Locked"}
              </span>
            </div>
            {team.first_locked_at && team.first_locked_at !== team.final_locked_at && (
              <div className="flex justify-between items-center text-muted-foreground border-t border-border/40 pt-1">
                <span>First Locked Time:</span>
                <span className="font-mono text-foreground">{new Date(team.first_locked_at).toLocaleString()}</span>
              </div>
            )}
            <div className="flex justify-between items-center text-muted-foreground border-t border-border/40 pt-1">
              <span>Auto-Resolved Tier:</span>
              <span className="font-medium text-foreground">
                {team.timing_tier_name || team.timing_badge || "Standard (0 pts)"}
              </span>
            </div>

            {breakdown?.timing_breakdown && breakdown.timing_breakdown.length > 1 && (
              <div className="border-t border-border/40 pt-2 space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground">Breakdown:</span>
                {breakdown.timing_breakdown.map((gate) => (
                  <div key={gate.gate_id} className="flex justify-between items-center text-xs">
                    <span className="text-muted-foreground truncate">{gate.title}</span>
                    <span className={`font-mono text-[11px] font-semibold ${
                      gate.points > 0 ? "text-emerald-400" : gate.points < 0 ? "text-rose-400" : "text-muted-foreground"
                    }`}>
                      {gate.points > 0 ? `+${gate.points}` : gate.points} pts
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <form onSubmit={handleSaveOverride} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-foreground mb-1">
                Manual Timing Points (+ or -)
              </label>
              <div className="relative">
                <input
                  type="number"
                  step="0.5"
                  value={pointsStr}
                  onChange={(e) => setPointsStr(e.target.value)}
                  placeholder="e.g. 5.0, 3.0, 0, -2.0"
                  className="w-full h-10 px-3 rounded-xl border border-border bg-card text-foreground text-sm font-mono focus:outline-none focus:border-primary"
                />
              </div>
              <p className="text-[11px] text-muted-foreground mt-1">
                Positive numbers award a bonus (e.g. 5). Negative numbers apply a penalty (e.g. -2).
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-foreground mb-1">
                Reason / Ops Audit Note (Optional)
              </label>
              <input
                type="text"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. Approved medical/technical extension"
                className="w-full h-9 px-3 rounded-xl border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
              />
            </div>

            <div className="flex items-center justify-between gap-3 pt-2 border-t border-border">
              {team.is_timing_override ? (
                <button
                  type="button"
                  disabled={mutation.isPending}
                  onClick={handleResetToAuto}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                >
                  <RotateCcw size={13} />
                  Restore Auto
                </button>
              ) : (
                <div />
              )}

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-3 py-2 rounded-xl border border-border text-xs font-medium text-foreground hover:bg-muted transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={mutation.isPending || !pointsStr}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-all disabled:opacity-50"
                >
                  <Save size={13} />
                  {mutation.isPending ? "Saving…" : "Save Override"}
                </button>
              </div>
            </div>
          </form>
        </div>
      </DialogContent>
    </Dialog>
  )
}
