import { useNavigate, useParams } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { ArrowLeft, Award, Clock, Star, Trophy } from "lucide-react"
import { PageHeader, Spinner, StatCard } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { getUserProfileApi } from "@/api/auth"
import { getInstructorPerformanceApi } from "@/api/instructor_assessment"

/** Instructor Performance Profile — the "view full performance history"
 *  detail page linked from the admin instructors roster (2026-09). Every
 *  number here is fetched live from the backend's own derived aggregation
 *  (services/instructor_assessment/performance.py) — nothing is duplicated
 *  or cached client-side. */
export default function InstructorPerformance() {
  const { userId } = useParams({ strict: false }) as { userId: string }
  const navigate = useNavigate()

  const { data: user, isLoading: userLoading } = useQuery({
    queryKey: ["user-profile", userId],
    queryFn: () => getUserProfileApi(userId),
  })
  const { data: perf, isLoading: perfLoading } = useQuery({
    queryKey: ["instructor-performance", userId],
    queryFn: () => getInstructorPerformanceApi(userId),
  })

  if (userLoading || perfLoading || !user || !perf) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <Button variant="outline" size="sm" onClick={() => void navigate({ to: "/instructors/admin/instructors" })} className="self-start gap-1.5">
        <ArrowLeft size={14} /> Back to instructors
      </Button>

      <PageHeader
        title={user.full_name || user.email}
        subtitle={
          perf.certifications.length > 0
            ? perf.certifications.map((c) => c.label).join(" · ")
            : "No certifications on file"
        }
      />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard icon={<Trophy size={18} />} label="Sessions delivered" value={perf.total_sessions_delivered} />
        <StatCard icon={<Clock size={18} />} label="Hours delivered" value={`${perf.total_hours_delivered}h`} />
        <StatCard icon={<Award size={18} />} label="Programs" value={perf.programs_participated_in} />
        <StatCard
          icon={<Star size={18} />}
          label="Average rating"
          value={perf.average_rating != null ? `${perf.average_rating} / 5` : "—"}
        />
      </div>

      {perf.recent_rating_trend.length > 0 && (
        <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-5">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">Recent performance trend</h3>
          <div className="flex items-end gap-2 h-16">
            {perf.recent_rating_trend.map((v, i) => (
              <div key={i} className="flex flex-col items-center gap-1 flex-1">
                <div
                  className="w-full bg-primary/70 rounded-t"
                  style={{ height: `${Math.max((v / 5) * 100, 6)}%` }}
                  title={`${v} / 5`}
                />
                <span className="text-[10px] text-muted-foreground">{v}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid sm:grid-cols-2 gap-4">
        <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-5">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">Quiz / assessment history</h3>
          {perf.quiz_history.length === 0 ? (
            <p className="text-sm text-muted-foreground">No assessments taken yet.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="text-muted-foreground uppercase tracking-wide">
                <tr><th className="text-left font-medium py-1">Program</th><th className="text-left font-medium py-1">Score</th><th className="text-left font-medium py-1">Critical</th></tr>
              </thead>
              <tbody>
                {perf.quiz_history.map((q) => (
                  <tr key={q.attempt_id} className="border-t border-border">
                    <td className="py-1.5">{q.program_name}</td>
                    <td className="py-1.5">{q.score}/{q.total} ({q.total ? Math.round(((q.score ?? 0) / q.total) * 100) : 0}%)</td>
                    <td className="py-1.5">{q.critical_correct}/{q.critical_total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-5">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">Rating history</h3>
          {perf.rating_history.length === 0 ? (
            <p className="text-sm text-muted-foreground">No post-program ratings yet.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="text-muted-foreground uppercase tracking-wide">
                <tr><th className="text-left font-medium py-1">Program</th><th className="text-left font-medium py-1">Rater</th><th className="text-left font-medium py-1">Overall</th><th className="text-left font-medium py-1">Recommended</th></tr>
              </thead>
              <tbody>
                {perf.rating_history.map((r) => (
                  <tr key={r.rating_id} className="border-t border-border">
                    <td className="py-1.5">{r.program_name}</td>
                    <td className="py-1.5">{r.rater_name ?? "—"}</td>
                    <td className="py-1.5">{r.overall_rating}</td>
                    <td className="py-1.5">{r.recommended === null ? "—" : r.recommended ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
