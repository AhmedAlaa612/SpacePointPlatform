import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { getProgramsApi } from "@/api/sessions/programs"
import { getCohortsApi } from "@/api/sessions/cohorts"
import { getProgressGridApi, type MissionStatus } from "@/api/lms_progress_grid"
import type { Program } from "@/types/sessions"
import type { Cohort } from "@/types/sessions"

const MISSION_STATUS_STYLE: Record<MissionStatus, string> = {
  passed: "bg-emerald-500/10 text-emerald-500",
  failed: "bg-red-500/10 text-red-500",
  submitted: "bg-amber-500/10 text-amber-600",
  in_progress: "bg-primary/10 text-primary",
  abandoned: "bg-muted text-muted-foreground",
}

const MISSION_STATUS_LABEL: Record<MissionStatus, string> = {
  passed: "Passed", failed: "Failed", submitted: "Submitted",
  in_progress: "In progress", abandoned: "Abandoned",
}

function CoursePctCell({ enrolled, pct }: { enrolled: boolean; pct: number }) {
  if (!enrolled) return <span className="text-xs text-muted-foreground">Not enrolled</span>
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 rounded-full bg-muted overflow-hidden">
        <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums text-foreground">{pct}%</span>
    </div>
  )
}

/** 7B-1 (Missions Phase 2B, 2026-08-12) — every active student in one cohort
 * x every course in its curriculum x every mission the roster has
 * attempted, completion at a glance. Own page under /lms-authoring,
 * matching LM1-13's "own pages" convention; scoped to one cohort at a time
 * like every other progress view in the app (my-programs, session roster) —
 * there is no platform-wide matrix here. */
export default function LmsProgressGrid() {
  const [programId, setProgramId] = useState("")
  const [cohortId, setCohortId] = useState("")

  const { data: programs = [], isLoading: programsLoading } = useQuery<Program[]>({
    queryKey: ["sessions-programs"],
    queryFn: getProgramsApi,
  })
  const { data: cohorts = [] } = useQuery<Cohort[]>({
    queryKey: ["sessions-cohorts", programId],
    queryFn: () => getCohortsApi(programId),
    enabled: !!programId,
  })
  const { data: grid, isLoading: gridLoading } = useQuery({
    queryKey: ["lms-admin-progress-grid", cohortId],
    queryFn: () => getProgressGridApi(cohortId),
    enabled: !!cohortId,
  })

  if (programsLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Progress Grid"
        subtitle="Every student in a cohort against every course and mission they touch — who's stuck, and where."
      />

      <div className="flex flex-wrap gap-3 max-w-2xl">
        <select
          value={programId}
          onChange={(e) => { setProgramId(e.target.value); setCohortId("") }}
          className="h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="">Select a program…</option>
          {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select
          value={cohortId}
          onChange={(e) => setCohortId(e.target.value)}
          disabled={!programId}
          className="h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer disabled:opacity-50"
        >
          <option value="">Select a cohort…</option>
          {cohorts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>

      {!cohortId ? (
        <EmptyState title="Pick a cohort" hint="Choose a program and cohort above to see its progress grid." />
      ) : gridLoading || !grid ? (
        <Spinner />
      ) : grid.rows.length === 0 ? (
        <EmptyState title="No active students in this cohort" />
      ) : grid.courses.length === 0 && grid.missions.length === 0 ? (
        <EmptyState
          title="Nothing to show yet"
          hint="This cohort has no curriculum courses and no mission attempts on record."
        />
      ) : (
        <div className="overflow-x-auto rounded-xl ring-1 ring-border">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="text-left font-medium text-muted-foreground px-4 py-2.5 sticky left-0 bg-muted/40">
                  Student
                </th>
                {grid.courses.map((c) => (
                  <th key={c.course_id} className="text-left font-medium text-muted-foreground px-4 py-2.5 whitespace-nowrap">
                    {c.title}
                  </th>
                ))}
                {grid.missions.map((m) => (
                  <th key={m.mission_id} className="text-left font-medium text-muted-foreground px-4 py-2.5 whitespace-nowrap">
                    {m.title}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grid.rows.map((row) => (
                <tr key={row.user_id} className="border-b border-border last:border-0">
                  <td className="px-4 py-2.5 font-medium text-foreground whitespace-nowrap sticky left-0 bg-card">
                    {row.full_name}
                  </td>
                  {grid.courses.map((c) => {
                    const cell = row.courses[c.course_id]
                    return (
                      <td key={c.course_id} className="px-4 py-2.5">
                        {cell ? <CoursePctCell enrolled={cell.enrolled} pct={cell.pct} /> : <span className="text-xs text-muted-foreground">—</span>}
                      </td>
                    )
                  })}
                  {grid.missions.map((m) => {
                    const cell = row.missions[m.mission_id]
                    return (
                      <td key={m.mission_id} className="px-4 py-2.5">
                        {cell ? (
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium ${MISSION_STATUS_STYLE[cell.status]}`}>
                            {MISSION_STATUS_LABEL[cell.status]}
                            {cell.score !== null && <span className="opacity-70">· {cell.score}%</span>}
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">Not attempted</span>
                        )}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
