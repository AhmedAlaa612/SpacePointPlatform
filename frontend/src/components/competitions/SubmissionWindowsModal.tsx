import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Calendar, Plus, Trash2, Save } from "lucide-react"
import {
  getCohortSubmissionWindowsApi,
  updateCohortSubmissionWindowsApi,
  getCohortCheckpointsApi,
  type SubmissionWindowItem,
  type CohortCheckpoint,
} from "@/api/competitions"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useToast } from "@/components/ui/toast"
import { Spinner } from "@/components/ui/primitives"
import { cn } from "@/lib/utils"

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

  const { data: checkpoints = [] } = useQuery<CohortCheckpoint[]>({
    queryKey: ["competitions-cohort-checkpoints", cohortId],
    queryFn: () => getCohortCheckpointsApi(cohortId),
    enabled: open,
  })

  const [windows, setWindows] = useState<SubmissionWindowItem[]>([])
  const [selectedGateId, setSelectedGateId] = useState<string>("final")

  // New tier inline form state
  const [name, setName] = useState("")
  const [cutoffAt, setCutoffAt] = useState("")
  const [points, setPoints] = useState<string>("0")
  const [color, setColor] = useState("green")
  const [isDeadline, setIsDeadline] = useState(false)

  useEffect(() => {
    if (open && initialWindows) {
      setWindows(initialWindows)
    }
  }, [open, initialWindows])

  const mutation = useMutation({
    mutationFn: (updated: SubmissionWindowItem[]) =>
      updateCohortSubmissionWindowsApi(cohortId, updated),
    onSuccess: () => {
      toast.success("Submission windows saved successfully")
      queryClient.invalidateQueries({ queryKey: ["competitions-submission-windows", cohortId] })
      queryClient.invalidateQueries({ queryKey: ["competitions-timing-student", cohortId] })
      queryClient.invalidateQueries({ queryKey: ["competitions-leaderboard", cohortId] })
      onClose()
    },
    onError: () => {
      toast.error("Failed to save submission windows")
    },
  })

  if (!open) return null

  const activeWindows = windows.filter((w) =>
    selectedGateId === "final"
      ? !w.checkpoint_id || w.checkpoint_id === "final"
      : String(w.checkpoint_id || "") === String(selectedGateId)
  )

  const handleAddWindow = () => {
    if (!name.trim()) {
      toast.error("Please enter a bracket name (e.g. 'Early Bird' or 'Final Deadline')")
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
      is_deadline: isDeadline,
      checkpoint_id: selectedGateId === "final" ? null : selectedGateId,
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
    setIsDeadline(false)
  }

  const handleDeleteWindow = (id: string) => {
    setWindows(windows.filter((w) => w.id !== id))
  }

  const handleSave = () => {
    mutation.mutate(windows)
  }

  const selectedCheckpoint = checkpoints.find((c) => c.id === selectedGateId)
  const currentGateLabel = selectedGateId === "final" ? "Final Submission" : (selectedCheckpoint?.title || "Checkpoint")

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto p-4 sm:p-6 bg-card border-border">
        <DialogHeader>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded-full">
              Automated Deadlines
            </span>
          </div>
          <DialogTitle className="text-xl font-bold font-display text-foreground">
            Submission Windows & Timing Incentives
          </DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <div className="py-12 flex justify-center">
            <Spinner />
          </div>
        ) : (
          <div className="mt-2 space-y-5">
            {/* Gate Selector */}
            <div className="flex items-center gap-1.5 p-1 bg-muted/40 rounded-xl overflow-x-auto border border-border">
              <button
                type="button"
                onClick={() => setSelectedGateId("final")}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors cursor-pointer",
                  selectedGateId === "final"
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                )}
              >
                Final Submission
              </button>
              {checkpoints.map((cp, idx) => (
                <button
                  key={cp.id}
                  type="button"
                  onClick={() => setSelectedGateId(cp.id)}
                  className={cn(
                    "px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors cursor-pointer",
                    selectedGateId === cp.id
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                  )}
                >
                  {cp.title || `Checkpoint ${idx + 1}`}
                </button>
              ))}
            </div>

            {/* Existing Brackets List for current gate */}
            <div>
              <div className="text-xs font-semibold text-foreground mb-2 flex items-center justify-between">
                <span>{currentGateLabel} Tiers ({activeWindows.length})</span>
                <span className="text-[11px] text-muted-foreground font-normal">
                  Evaluated in chronological order
                </span>
              </div>

              {activeWindows.length === 0 ? (
                <div className="p-5 text-center rounded-xl border border-dashed border-border bg-muted/20 text-xs text-muted-foreground">
                  No submission brackets configured for {currentGateLabel.toLowerCase()}.
                </div>
              ) : (
                <div className="space-y-2">
                  {activeWindows.map((w, index) => {
                    const cutoffDate = new Date(w.cutoff_at)
                    const colorStyle =
                      w.color === "rose"
                        ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                        : w.color === "white"
                        ? "bg-white/10 text-zinc-100 border-white/20"
                        : "bg-green-500/10 text-green-400 border-green-500/30"

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
                              {w.is_deadline && (
                                <span className="text-[10px] font-extrabold uppercase px-1.5 py-0.5 rounded bg-rose-500/15 border border-rose-500/30 text-rose-400 tracking-wider">
                                  Hard Deadline
                                </span>
                              )}
                              <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full border ${colorStyle}`}>
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
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-rose-400 hover:bg-rose-500/10 transition-colors cursor-pointer"
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
                Add Tier for {currentGateLabel}
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
                    Points (+/-)
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
                    <option value="green">Green</option>
                    <option value="rose">Rose</option>
                    <option value="white">White</option>
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

              <div className="flex items-center gap-2 pt-1 pb-1">
                <input
                  type="checkbox"
                  id="isDeadlineCheckbox"
                  checked={isDeadline}
                  onChange={(e) => setIsDeadline(e.target.checked)}
                  className="h-4 w-4 rounded border-border text-primary focus:ring-primary cursor-pointer"
                />
                <label htmlFor="isDeadlineCheckbox" className="text-xs font-semibold text-foreground cursor-pointer select-none">
                  Hard Submission Deadline
                </label>
              </div>

              <button
                type="button"
                onClick={handleAddWindow}
                className="w-full py-2 rounded-lg border border-primary/30 bg-primary/10 text-primary text-xs font-bold hover:bg-primary/20 transition-all flex items-center justify-center gap-1.5 cursor-pointer"
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
                className="px-3.5 py-2 rounded-xl border border-border text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={mutation.isPending}
                onClick={handleSave}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-all disabled:opacity-50 cursor-pointer"
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
