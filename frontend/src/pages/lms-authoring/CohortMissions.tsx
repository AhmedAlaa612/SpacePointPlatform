import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import {
  myInstructorCohortsApi, instructorCohortProgressApi, instructorStepGatesApi, setInstructorStepGateApi,
  instructorReviewQueueApi, instructorReviewAttemptApi,
} from "@/api/missionsInstructor"
import { fetchMissionCatalog } from "@/api/missions"
import type { ManagedAttempt } from "@/api/missions_manager"

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

const MISSION_STATUS_STYLE: Record<string, string> = {
  passed: "bg-emerald-500/10 text-emerald-500",
  failed: "bg-red-500/10 text-red-500",
  submitted: "bg-amber-500/10 text-amber-600",
  in_progress: "bg-primary/10 text-primary",
  abandoned: "bg-muted text-muted-foreground",
}
const MISSION_STATUS_LABEL: Record<string, string> = {
  passed: "Passed", failed: "Failed", submitted: "Submitted", in_progress: "In progress", abandoned: "Abandoned",
}

const TABS = ["progress", "gates", "review"] as const
type Tab = (typeof TABS)[number]
const TAB_LABEL: Record<Tab, string> = { progress: "Progress", gates: "Gates", review: "Review" }

/** Cohort-scoped instructor Missions surface (2026-08-17) — the boss's own
 * ask: an instructor tracks/gates/reviews their own cohort's Design runs,
 * ops/admin get the identical capability across any cohort (the backend's
 * `require_cohort_access` already handles that bypass; this page doesn't
 * need to know which case it's in). Reachable by instructor/facilitator/
 * operations/admin — see the widened `/lms-authoring` layout guard in
 * `router.tsx`. */
export default function CohortMissions() {
  const [cohortId, setCohortId] = useState<string | null>(null)
  const [missionId, setMissionId] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>("progress")

  const { data: cohorts = [], isLoading: cohortsLoading } = useQuery({
    queryKey: ["instructor-cohorts"], queryFn: myInstructorCohortsApi,
  })
  const { data: missions = [] } = useQuery({
    queryKey: ["mission-catalog-design-only"],
    queryFn: async () => (await fetchMissionCatalog()).filter((m) => m.kind === "design"),
  })

  const effectiveCohortId = cohortId ?? cohorts[0]?.id ?? null
  const effectiveMissionId = missionId ?? missions[0]?.id ?? null

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Cohort Missions"
        subtitle="Track progress, gate steps, and review submissions for your cohort's Design mission runs."
      />

      {cohortsLoading ? (
        <Spinner />
      ) : cohorts.length === 0 ? (
        <EmptyState title="No cohorts yet" hint="This shows up once you're assigned to teach a session in a cohort." />
      ) : (
        <div className="flex flex-wrap gap-2">
          {cohorts.map((c) => (
            <button
              key={c.id}
              onClick={() => setCohortId(c.id)}
              className={`px-3 py-1.5 rounded-xl text-sm border transition-colors ${
                effectiveCohortId === c.id
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-foreground hover:bg-muted"}`}
            >
              {c.name}
            </button>
          ))}
        </div>
      )}

      {effectiveCohortId && (
        missions.length === 0 ? (
          <EmptyState title="No design missions published yet" />
        ) : (
          <>
            <select
              value={effectiveMissionId ?? ""}
              onChange={(e) => setMissionId(e.target.value)}
              className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm w-fit focus:outline-none focus:border-primary"
            >
              {missions.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}
            </select>

            <div className="flex gap-1 border-b border-border">
              {TABS.map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                    tab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                >
                  {TAB_LABEL[t]}
                </button>
              ))}
            </div>

            {effectiveMissionId && (
              <>
                {tab === "progress" && <ProgressTab cohortId={effectiveCohortId} />}
                {tab === "gates" && <GatesTab cohortId={effectiveCohortId} missionId={effectiveMissionId} />}
                {tab === "review" && <ReviewTab cohortId={effectiveCohortId} missionId={effectiveMissionId} />}
              </>
            )}
          </>
        )
      )}
    </div>
  )
}

// ── Progress ─────────────────────────────────────────────────────────────

function ProgressTab({ cohortId }: { cohortId: string }) {
  const { data: grid, isLoading } = useQuery({
    queryKey: ["instructor-cohort-progress", cohortId], queryFn: () => instructorCohortProgressApi(cohortId),
  })

  if (isLoading) return <Spinner />
  if (!grid || grid.rows.length === 0) {
    return <EmptyState title="No students registered in this cohort yet" />
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-border">
            <th className="text-left font-medium text-muted-foreground px-4 py-2.5 whitespace-nowrap">Student</th>
            {grid.missions.map((m) => (
              <th key={m.mission_id} className="font-medium text-muted-foreground px-3 py-2.5 text-center whitespace-nowrap">
                {m.title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.rows.map((row) => (
            <tr key={row.user_id} className="border-b border-border last:border-0">
              <td className="px-4 py-2.5 text-foreground whitespace-nowrap">{row.full_name}</td>
              {grid.missions.map((m) => {
                const cell = row.missions[m.mission_id]
                if (!cell) {
                  return <td key={m.mission_id} className="px-3 py-2.5 text-center text-muted-foreground">—</td>
                }
                return (
                  <td key={m.mission_id} className="px-3 py-2.5">
                    <div className="flex flex-col items-center gap-1">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${MISSION_STATUS_STYLE[cell.status] ?? ""}`}>
                        {MISSION_STATUS_LABEL[cell.status] ?? cell.status}
                      </span>
                      {cell.steps && (
                        <div className="flex gap-0.5">
                          {Object.entries(cell.steps).map(([key, done]) => (
                            <span
                              key={key} title={key}
                              className={`inline-block size-2 rounded-full ${done ? "bg-emerald-500" : "bg-muted-foreground/25"}`}
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Gates ────────────────────────────────────────────────────────────────

function GatesTab({ cohortId, missionId }: { cohortId: string; missionId: string }) {
  const queryClient = useQueryClient()
  const { data: gates = [], isLoading } = useQuery({
    queryKey: ["instructor-step-gates", cohortId, missionId], queryFn: () => instructorStepGatesApi(cohortId, missionId),
  })
  const toggleMutation = useMutation({
    mutationFn: ({ stepKey, isUnlocked }: { stepKey: string; isUnlocked: boolean }) =>
      setInstructorStepGateApi(cohortId, missionId, stepKey, isUnlocked),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["instructor-step-gates", cohortId, missionId] }),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">
        Unlock a step so students in this cohort can enter it. A locked step stays visible in their wizard, marked as
        not opened yet, rather than hidden — they can still look around.
      </p>
      {gates.map((g) => (
        <div key={g.step_key} className="flex items-center justify-between p-3 bg-background border border-border rounded-xl">
          <div>
            <p className="text-sm text-foreground">{g.label}</p>
            {g.updated_by_name && (
              <p className="text-xs text-muted-foreground">Last set by {g.updated_by_name}</p>
            )}
          </div>
          <button
            onClick={() => toggleMutation.mutate({ stepKey: g.step_key, isUnlocked: !g.is_unlocked })}
            disabled={toggleMutation.isPending}
            className={`h-8 px-3 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 ${
              g.is_unlocked ? "bg-emerald-500/10 text-emerald-600" : "bg-muted text-muted-foreground"}`}
          >
            {g.is_unlocked ? "Unlocked" : "Locked"}
          </button>
        </div>
      ))}
    </div>
  )
}

// ── Review ───────────────────────────────────────────────────────────────

function ReviewAttemptRow({ attempt, cohortId, missionId }: { attempt: ManagedAttempt; cohortId: string; missionId: string }) {
  const queryClient = useQueryClient()
  const [score, setScore] = useState("")
  const [notes, setNotes] = useState("")
  const [error, setError] = useState("")

  const reviewMutation = useMutation({
    mutationFn: (passed: boolean) =>
      instructorReviewAttemptApi(attempt.id, { passed, score: score ? Number(score) : null, review_comment: notes || null }),
    onSuccess: () => {
      setError("")
      void queryClient.invalidateQueries({ queryKey: ["instructor-review-queue", cohortId, missionId] })
    },
    onError: (e) => setError(errorDetail(e, "Couldn't submit this review")),
  })

  return (
    <div className="p-4 bg-background border border-border rounded-xl flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-foreground">{attempt.student_name ?? attempt.team_name ?? "Unknown"}</p>
        <span className="text-xs text-muted-foreground">Attempt {attempt.attempt_no}</span>
      </div>
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
        <Button size="sm" onClick={() => reviewMutation.mutate(true)} disabled={reviewMutation.isPending}>Pass</Button>
        <Button size="sm" variant="destructive" onClick={() => reviewMutation.mutate(false)} disabled={reviewMutation.isPending}>Fail</Button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

function ReviewTab({ cohortId, missionId }: { cohortId: string; missionId: string }) {
  const { data: queue = [], isLoading } = useQuery({
    queryKey: ["instructor-review-queue", cohortId, missionId], queryFn: () => instructorReviewQueueApi(cohortId, missionId),
  })

  if (isLoading) return <Spinner />
  if (queue.length === 0) {
    return (
      <EmptyState
        title="Nothing to review right now"
        hint="A Design mission run passes on its own once every step is valid — this fills up only if a future variant needs a manual sign-off."
      />
    )
  }
  return (
    <div className="flex flex-col gap-3">
      {queue.map((a) => <ReviewAttemptRow key={a.id} attempt={a} cohortId={cohortId} missionId={missionId} />)}
    </div>
  )
}
