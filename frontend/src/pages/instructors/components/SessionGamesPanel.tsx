import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Trophy, Play } from "lucide-react"
import { listSessionAssignmentsApi, type GameSessionAssignment } from "@/api/games_sessions"
import { openRunApi } from "@/api/games_live"
import { Card, CardContent } from "@/components/ui/card"
import { useToast } from "@/components/ui/toast"

/** Live Quiz entry point on the instructor's own session screen (Live
 * Games Phase 2C, 8-7, D11) — "instructor opens their sessions, same way
 * they see the material and attendance, they see a game that they can
 * start anytime with the questions ready in it." "Run" opens a fresh
 * lobby every click — there's no "resume the run I already opened"
 * lookup yet, so navigating away and clicking Run again starts a second
 * lobby rather than rejoining the first. Acceptable for now: nothing
 * about an unstarted lobby is lost (no points, no participants beyond
 * whoever already joined it), and Restart already covers the "I opened
 * the wrong one" case once live. */
export function SessionGamesPanel({ sessionId }: { sessionId: string }) {
  const navigate = useNavigate()
  const toast = useToast()
  const [openingId, setOpeningId] = useState<string | null>(null)

  const { data: assignments = [] } = useQuery<GameSessionAssignment[]>({
    queryKey: ["game-session-assignments", sessionId],
    queryFn: () => listSessionAssignmentsApi(sessionId),
  })

  const openRun = useMutation({
    mutationFn: (assignmentId: string) => openRunApi(assignmentId),
    onMutate: (assignmentId) => setOpeningId(assignmentId),
    onSuccess: (run) => { void navigate({ to: "/instructors/game-runs/$runId", params: { runId: run.id } }) },
    onError: () => { toast.error("Couldn't open this game"); setOpeningId(null) },
  })

  if (assignments.length === 0) return null

  return (
    <Card>
      <CardContent className="p-4 flex flex-col gap-3">
        <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Trophy size={15} /> Live Quiz
        </p>
        <div className="flex flex-col gap-1.5">
          {assignments.map((a) => (
            <div
              key={a.id}
              className="flex items-center justify-between gap-3 rounded-xl border border-border bg-background/50 px-3 py-2"
            >
              <div className="min-w-0">
                <p className="text-sm text-foreground truncate">{a.game_title}</p>
                <p className="text-xs text-muted-foreground">
                  {a.question_count} question{a.question_count === 1 ? "" : "s"}
                  {a.instructor_note ? ` · ${a.instructor_note}` : ""}
                </p>
              </div>
              <button
                onClick={() => openRun.mutate(a.id)}
                disabled={openRun.isPending && openingId === a.id}
                className="h-8 px-3 bg-primary text-primary-foreground rounded-lg text-xs font-semibold hover:opacity-90 transition-colors disabled:opacity-50 flex items-center gap-1.5 shrink-0"
              >
                <Play size={12} /> {openRun.isPending && openingId === a.id ? "Opening…" : "Run"}
              </button>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
