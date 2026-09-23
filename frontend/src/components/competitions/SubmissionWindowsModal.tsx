import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Calendar, Plus, Trash2, Save } from "lucide-react"
import {
  getCohortSubmissionWindowsApi,
  updateCohortSubmissionWindowsApi,
  type SubmissionWindowItem,
} from "@/api/competitions"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useToast } from "@/components/ui/toast"
import { Spinner } from "@/components/ui/primitives"

interface SubmissionWindowsModalProps {
  cohortId: string
  open: boolean
  onClose: () => void
}

export function SubmissionWindowsModal({ cohortId, open, onClose }: SubmissionWindowsModalProps) {
  const toast = useToast()
  const queryClient = useQueryClient()

  const { data: initialWindows, isLoading } = useQuery<SubmissionWindowItem[]>({
    queryKey: ["competitions-submission-windows", cohortId],
    queryFn: () => getCohortSubmissionWindowsApi(cohortId),
    enabled: open,
  })

  const [windows, setWindows] = useState<SubmissionWindowItem[]>([])

  // New tier inline form state
  const [name, setName] = useState("")
  const [cutoffAt, setCutoffAt] = useState("")
  const [points, setPoints] = useState<string>("0")
  const [color, setColor] = useState("emerald")

  useEffect(() => {
    if (initialWindows) {
      setWindows(initialWindows)
    }
  }, [initialWindows])

  const mutation = useMutation({
    mutationFn: (updated: SubmissionWindowItem[]) =>
      updateCohortSubmissionWindowsApi(cohortId, updated),
    onSuccess: () => {
      toast.success("Submission windows saved successfully")
      queryClient.invalidateQueries({ queryKey: ["competitions-submission-windows", cohortId] })
      queryClient.invalidateQueries({ queryKey: ["competitions-leaderboard", cohortId] })
      onClose()
    },
    onError: () => {
      toast.error("Failed to save submission windows")
    },
  })

  if (!open) return null

  const handleAddWindow = () => {
    if (!name.trim()) {
      toast.error("Please enter a bracket name (e.g. 'Early Bird')")
      return
    }
    if (!cutoffAt) {
      toast.error("Please select a cutoff date and time")
      return
    }
    const pts = parseFloat(points) || 0
    const sign = pts > 0 ? "+" : ""
    const badgeLabel = `${name.trim()} (${sign}${pts})`

    // Convert local datetime input to ISO UTC
    const dateObj = new Date(cutoffAt)
    const isoStr = dateObj.toISOString()

    const newWindow: SubmissionWindowItem = {
      id: `tier-${Date.now()}`,
      name: name.trim(),
      cutoff_at: isoStr,
      points: pts,
      badge: badgeLabel,
      color,
    }

    // Insert and sort by cutoff
    const updated = [...windows, newWindow].sort(
      (a, b) => new Date(a.cutoff_at).getTime() - new Date(b.cutoff_at).getTime()
    )
    setWindows(updated)

    // Reset inputs
    setName("")
    setCutoffAt("")
    setPoints("0")
  }

  const handleDeleteWindow = (id: string) => {
    setWindows(windows.filter((w) => w.id !== id))
  }

  const handleSave = () => {
    mutation.mutate(windows)
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto p-6 bg-card border-border">
        <DialogHeader>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded-full">
              Automated Deadlines
            </span>
          </div>
          <DialogTitle className="text-xl font-bold font-display text-foreground">
            Submission Windows & Timing Incentives
          </DialogTitle>
          <p className="text-xs text-muted-foreground mt-0.5">
            Configure tiered deadlines (Early Bird bonuses, On-Time, and Late deductions).
            The platform dynamically evaluates each team's submission timestamp against these brackets.
          </p>
        </DialogHeader>

        {isLoading ? (
          <div className="py-12 flex justify-center">
            <Spinner />
          </div>
        ) : (
          <div className="mt-4 space-y-6">
            {/* Existing Brackets List */}
            <div>
              <div className="text-xs font-semibold text-foreground mb-2 flex items-center justify-between">
                <span>Configured Cutoff Tiers ({windows.length})</span>
                <span className="text-[11px] text-muted-foreground font-normal">
                  Evaluated in chronological order
                </span>
              </div>

              {windows.length === 0 ? (
                <div className="p-6 text-center rounded-xl border border-dashed border-border bg-muted/20 text-xs text-muted-foreground">
                  No submission brackets configured. Standard flat deadline applies with 0 timing points.
                </div>
              ) : (
                <div className="space-y-2">
                  {windows.map((w, index) => {
                    const cutoffDate = new Date(w.cutoff_at)
                    return (
                      <div
                        key={w.id}
                        className="flex items-center justify-between gap-3 p-3 rounded-xl border border-border bg-muted/20 hover:bg-muted/30 transition-colors"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-bold font-mono">
                            {index + 1}
                          </span>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-sm font-bold text-foreground">{w.name}</span>
                              <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full border ${
                                w.points > 0
                                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                                  : w.points < 0
                                  ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                                  : "bg-blue-500/10 text-blue-400 border-blue-500/30"
                              }`}>
                                {w.points > 0 ? `+${w.points}` : w.points} pts
                              </span>
                            </div>
                            <div className="text-xs text-muted-foreground flex items-center gap-1.5 mt-0.5">
                              <Calendar size={12} className="text-primary/70" />
                              Cutoff: <span className="font-mono text-foreground">{cutoffDate.toLocaleString()}</span>
                            </div>
                          </div>
                        </div>

                        <button
                          type="button"
                          onClick={() => handleDeleteWindow(w.id)}
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                          title="Remove tier"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Add New Tier Form Card */}
            <div className="p-4 rounded-xl border border-primary/20 bg-primary/5 space-y-3">
              <div className="text-xs font-bold uppercase tracking-wider text-primary flex items-center gap-1.5">
                <Plus size={13} />
                Add New Bracket Tier
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="sm:col-span-1">
                  <label className="block text-[11px] font-semibold text-muted-foreground mb-1">
                    Tier Name
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Early Bird"
                    className="w-full h-9 px-3 rounded-lg border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
                  />
                </div>

                <div className="sm:col-span-1">
                  <label className="block text-[11px] font-semibold text-muted-foreground mb-1">
                    Points Adjustment (+/-)
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    value={points}
                    onChange={(e) => setPoints(e.target.value)}
                    placeholder="e.g. 5, -2, 0"
                    className="w-full h-9 px-3 rounded-lg border border-border bg-card text-foreground text-xs font-mono focus:outline-none focus:border-primary"
                  />
                </div>

                <div className="sm:col-span-1">
                  <label className="block text-[11px] font-semibold text-muted-foreground mb-1">
                    Color Accent
                  </label>
                  <select
                    value={color}
                    onChange={(e) => setColor(e.target.value)}
                    className="w-full h-9 px-2 rounded-lg border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary cursor-pointer"
                  >
                    <option value="emerald">Emerald (Bonus)</option>
                    <option value="blue">Blue (Standard)</option>
                    <option value="amber">Amber (Grace / Warning)</option>
                    <option value="rose">Rose (Penalty / Critical)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-muted-foreground mb-1">
                  Cutoff Date & Time
                </label>
                <input
                  type="datetime-local"
                  value={cutoffAt}
                  onChange={(e) => setCutoffAt(e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <button
                type="button"
                onClick={handleAddWindow}
                className="w-full py-2 rounded-lg border border-primary/30 bg-primary/10 text-primary text-xs font-bold hover:bg-primary/20 transition-all flex items-center justify-center gap-1.5"
              >
                <Plus size={13} />
                Add to Brackets
              </button>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
              <button
                type="button"
                onClick={onClose}
                className="px-3.5 py-2 rounded-xl border border-border text-xs font-medium text-foreground hover:bg-muted transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={mutation.isPending}
                onClick={handleSave}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-all disabled:opacity-50"
              >
                <Save size={13} />
                {mutation.isPending ? "Saving…" : "Save Windows"}
              </button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
