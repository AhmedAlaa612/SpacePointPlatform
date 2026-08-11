import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { Plus, Trash2, Trophy, SlidersHorizontal } from "lucide-react"
import { Modal, Field, ModalActions } from "@/pages/admin/components/common"
import { listGamesApi, type Game } from "@/api/games_admin"
import {
  listSessionAssignmentsApi, createSessionAssignmentApi, deleteSessionAssignmentApi,
  type GameSessionAssignment,
} from "@/api/games_sessions"
import { useToast } from "@/components/ui/toast"

/** Live Quiz assignment (Live Games Phase 2C, 8-4, D11) — same "next to
 * materials" placement as MaterialsPanel, same single-query/mutations-
 * invalidate-that-key shape. Attaching a game snapshots its question set
 * (D12) — the picked-from list is templates (`/games/admin`); what shows
 * here afterward is each session's own independent copy. */
export function GameAssignmentPanel({ sessionId }: { sessionId: string }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [pickerOpen, setPickerOpen] = useState(false)
  const [selectedGameId, setSelectedGameId] = useState("")
  const [note, setNote] = useState("")

  const key = ["game-session-assignments", sessionId]
  const { data: assignments = [] } = useQuery<GameSessionAssignment[]>({
    queryKey: key, queryFn: () => listSessionAssignmentsApi(sessionId),
  })
  const { data: games = [] } = useQuery<Game[]>({ queryKey: ["games-admin"], queryFn: listGamesApi })

  const invalidate = () => qc.invalidateQueries({ queryKey: key })

  const assignMutation = useMutation({
    mutationFn: () => createSessionAssignmentApi(sessionId, { game_id: selectedGameId, instructor_note: note || null }),
    onSuccess: () => {
      toast.success("Game assigned")
      setPickerOpen(false); setSelectedGameId(""); setNote("")
      invalidate()
    },
  })
  const removeMutation = useMutation({
    mutationFn: (assignmentId: string) => deleteSessionAssignmentApi(assignmentId),
    onSuccess: () => { toast.success("Assignment removed"); invalidate() },
  })

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-foreground">Live Quiz</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Games ready for the instructor to start during this session. Each one gets its own editable copy of the
            questions — changes here never touch the shared game.
          </p>
        </div>
        <button
          onClick={() => setPickerOpen(true)}
          className="h-8 px-3 border border-border rounded-lg text-xs font-medium text-foreground hover:bg-muted transition-colors flex items-center gap-1.5 shrink-0"
        >
          <Plus size={12} /> Assign game
        </button>
      </div>

      <div className="flex flex-col gap-1.5">
        {assignments.map((a) => (
          <div
            key={a.id}
            className="flex items-center gap-3 rounded-xl border border-border bg-background/50 px-3 py-2"
          >
            <div className="w-8 h-8 flex-none flex items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Trophy size={14} />
            </div>
            <div className="min-w-0 flex-1">
              <Link
                to="/operations/game-assignments/$assignmentId" params={{ assignmentId: a.id }}
                className="text-sm font-medium text-foreground hover:underline truncate block"
              >
                {a.game_title}
              </Link>
              <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground flex-wrap">
                <span>{a.question_count} question{a.question_count === 1 ? "" : "s"}</span>
                <span className="inline-flex items-center gap-1"><SlidersHorizontal size={11} />{a.time_limit_seconds}s · floor {a.floor_pct}% · blackout last {a.blackout_count}</span>
                {a.instructor_note && <span className="italic truncate">"{a.instructor_note}"</span>}
              </div>
            </div>
            <button
              onClick={() => removeMutation.mutate(a.id)}
              className="p-1 text-muted-foreground hover:text-red-600 shrink-0"
              aria-label={`Remove ${a.game_title}`}
            ><Trash2 size={14} /></button>
          </div>
        ))}
        {assignments.length === 0 && (
          <p className="text-sm text-muted-foreground">No games assigned to this session yet.</p>
        )}
      </div>

      {pickerOpen && (
        <Modal title="Assign a game" onClose={() => setPickerOpen(false)}>
          <div className="flex flex-col gap-4">
            <Field label="Game">
              <select
                value={selectedGameId} onChange={(e) => setSelectedGameId(e.target.value)}
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
              >
                <option value="">Select a game…</option>
                {games.map((g) => (
                  <option key={g.id} value={g.id}>{g.title} ({g.question_count} question{g.question_count === 1 ? "" : "s"})</option>
                ))}
              </select>
            </Field>
            <Field label="Instructor note (optional, not shown to students)">
              <textarea
                value={note} onChange={(e) => setNote(e.target.value)} rows={2}
                placeholder="Run after the orbits module"
                className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary resize-none"
              />
            </Field>
            <ModalActions
              onCancel={() => setPickerOpen(false)}
              onConfirm={() => assignMutation.mutate()}
              loading={assignMutation.isPending}
              disabled={!selectedGameId}
              label="Assign"
            />
          </div>
        </Modal>
      )}
    </div>
  )
}
