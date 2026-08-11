import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  myManagedMissionsApi, managedMissionStatsApi, managedMissionQueueApi, reviewManagedAttemptApi,
  type ManagedAttempt,
} from "@/api/missions_manager"

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

function AttemptRow({ attempt, missionId }: { attempt: ManagedAttempt; missionId: string }) {
  const queryClient = useQueryClient()
  const [score, setScore] = useState("")
  const [notes, setNotes] = useState("")
  const [error, setError] = useState("")

  const reviewMutation = useMutation({
    mutationFn: (passed: boolean) =>
      reviewManagedAttemptApi(attempt.id, { passed, score: score ? Number(score) : null, review_comment: notes || null }),
    onSuccess: () => {
      setError("")
      queryClient.invalidateQueries({ queryKey: ["missions-manager-queue", missionId] })
      queryClient.invalidateQueries({ queryKey: ["missions-manager-stats", missionId] })
    },
    onError: (e) => setError(errorDetail(e, "Couldn't submit this review")),
  })

  return (
    <Card className="p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-foreground">{attempt.student_name ?? attempt.team_name ?? "Unknown"}</p>
        <span className="text-xs text-muted-foreground">Attempt {attempt.attempt_no}</span>
      </div>
      {typeof attempt.payload.artifact_url === "string" && (
        <a href={attempt.payload.artifact_url} target="_blank" rel="noreferrer" className="text-xs text-primary hover:opacity-80">
          View submission
        </a>
      )}
      <div className="flex gap-2">
        <input
          value={score} onChange={(e) => setScore(e.target.value)} placeholder="Score (0-100)"
          className="h-8 w-28 px-2 border border-border bg-card text-foreground rounded-lg text-xs focus:outline-none focus:border-primary"
        />
        <input
          value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes (optional)"
          className="h-8 flex-1 px-2 border border-border bg-card text-foreground rounded-lg text-xs focus:outline-none focus:border-primary"
        />
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => reviewMutation.mutate(true)} disabled={reviewMutation.isPending}>Approve</Button>
        <Button size="sm" variant="destructive" onClick={() => reviewMutation.mutate(false)} disabled={reviewMutation.isPending}>Reject</Button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </Card>
  )
}

function MissionPanel({ missionId, title }: { missionId: string; title: string }) {
  const { data: stats } = useQuery({ queryKey: ["missions-manager-stats", missionId], queryFn: () => managedMissionStatsApi(missionId) })
  const { data: queue = [] } = useQuery({ queryKey: ["missions-manager-queue", missionId], queryFn: () => managedMissionQueueApi(missionId) })

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold text-foreground">{title}</h2>
      {stats && (
        <div className="grid grid-cols-4 gap-3">
          <Card className="p-3 text-center">
            <p className="text-xl font-bold text-foreground">{stats.total_attempts}</p>
            <p className="text-[11px] text-muted-foreground uppercase tracking-wide">Attempts</p>
          </Card>
          <Card className="p-3 text-center">
            <p className="text-xl font-bold text-foreground">{stats.total_students}</p>
            <p className="text-[11px] text-muted-foreground uppercase tracking-wide">Students</p>
          </Card>
          <Card className="p-3 text-center">
            <p className="text-xl font-bold text-foreground">{stats.passed_students}</p>
            <p className="text-[11px] text-muted-foreground uppercase tracking-wide">Passed</p>
          </Card>
          <Card className="p-3 text-center">
            <p className="text-xl font-bold text-foreground">{stats.pass_rate}%</p>
            <p className="text-[11px] text-muted-foreground uppercase tracking-wide">Pass rate</p>
          </Card>
        </div>
      )}

      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Awaiting review</p>
      {queue.length === 0 ? (
        <EmptyState title="Nothing to review right now" />
      ) : (
        <div className="flex flex-col gap-3">
          {queue.map((a) => <AttemptRow key={a.id} attempt={a} missionId={missionId} />)}
        </div>
      )}
    </div>
  )
}

/** 7B-7 (Missions Phase 2B, 2026-08-12) — D7's payoff for an approved
 * intern proposal: staff assigns a manager (`/missions/admin/{id}/managers`,
 * no frontend for that yet — done from the API directly, same as the rest
 * of missions authoring), and the manager sees this. Read + review only —
 * editing a published mission's own fields/thresholds stays admin-only and
 * frozen until draft (D9), so there's nothing here to edit. */
export default function ManageMissions() {
  const [selected, setSelected] = useState<string | null>(null)
  const { data: missions = [], isLoading } = useQuery({ queryKey: ["missions-manager-mine"], queryFn: myManagedMissionsApi })

  const selectedMission = missions.find((m) => m.mission_id === selected)

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Manage Missions" subtitle="Missions you've been assigned to manage — stats and submissions awaiting review." />

      {isLoading ? (
        <Spinner />
      ) : missions.length === 0 ? (
        <EmptyState title="You don't manage any missions yet" hint="Staff assign mission managers after a proposal is approved and integrated." />
      ) : (
        <div className="flex flex-wrap gap-2">
          {missions.map((m) => (
            <button
              key={m.mission_id}
              onClick={() => setSelected(m.mission_id)}
              className={`px-3 py-1.5 rounded-xl text-sm border ${
                selected === m.mission_id ? "bg-primary text-primary-foreground border-primary" : "border-border text-foreground hover:bg-muted"
              }`}
            >
              {m.title}
            </button>
          ))}
        </div>
      )}

      {selectedMission && <MissionPanel missionId={selectedMission.mission_id} title={selectedMission.title} />}
    </div>
  )
}
