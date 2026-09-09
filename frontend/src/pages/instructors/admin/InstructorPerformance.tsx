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
          <div className="flex flex-col gap-3">
            {perf.rating_history.map((r) => (
              <div key={r.rating_id} className="rounded-xl border border-border p-3 flex flex-col gap-1.5">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div>
                    <p className="text-sm font-semibold text-foreground">{r.program_name}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {r.rater_name ? `Rated by ${r.rater_name}` : "Rated"}
                      {r.submitted_at && ` · ${new Date(r.submitted_at).toLocaleDateString()}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0 flex-wrap">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                      {r.overall_rating} / 5
                    </span>
                    {r.recommended != null && (
                      <span
                        className={`text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full ${
                          r.recommended
                            ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                            : "bg-red-500/10 text-red-600 dark:text-red-400"
                        }`}
                      >
                        {r.recommended ? "Recommended" : "Not recommended"}
                      </span>
                    )}
                    {r.flag !== "none" && (
                      <span
                        className={`text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full ${
                          r.flag === "exceptional"
                            ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                            : "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                        }`}
                      >
                        {r.flag === "exceptional" ? "Exceptional" : "Concern"}
                      </span>
                    )}
                  </div>
                </div>
                {r.strengths && (
                  <p className="text-xs text-foreground/90">
                    <span className="font-medium text-muted-foreground">Strengths: </span>{r.strengths}
                  </p>
                )}
                {r.areas_for_improvement && (
                  <p className="text-xs text-foreground/90">
                    <span className="font-medium text-muted-foreground">Areas for improvement: </span>{r.areas_for_improvement}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
