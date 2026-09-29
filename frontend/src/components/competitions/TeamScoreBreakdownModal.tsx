import { Fragment, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Clock, MessageSquare, User } from "lucide-react"
import { getTeamScoreBreakdownApi, type TeamScoreBreakdown } from "@/api/competitions"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Spinner } from "@/components/ui/primitives"

interface TeamScoreBreakdownModalProps {
  cohortId: string
  teamId: string | null
  open: boolean
  onClose: () => void
}

export function TeamScoreBreakdownModal({ cohortId, teamId, open, onClose }: TeamScoreBreakdownModalProps) {
  const [selectedJudgeIdx, setSelectedJudgeIdx] = useState<number>(0)

  const { data: breakdown, isLoading } = useQuery<TeamScoreBreakdown>({
    queryKey: ["competitions-team-breakdown", cohortId, teamId],
    queryFn: () => getTeamScoreBreakdownApi(cohortId, teamId!),
    enabled: open && !!teamId,
  })

  if (!open || !teamId) return null

  const activeJudge = breakdown?.judges[selectedJudgeIdx]

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto p-6 bg-card border-border">
        <DialogHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 flex-wrap mb-1">
                {breakdown?.qualification && (
                  <span className="text-[10px] font-bold uppercase tracking-wider text-amber-500 bg-amber-500/10 border border-amber-500/30 px-2 py-0.5 rounded-full">
                    {breakdown.qualification}
                  </span>
                )}
              </div>
              <DialogTitle className="text-xl font-bold font-display text-foreground">
                {breakdown?.team_name ?? "Team Evaluation Breakdown"}
              </DialogTitle>
            </div>

            {/* Score summary cards */}
            {breakdown && (
              <div className="flex items-center gap-3 shrink-0 text-right">
                <div className="p-2.5 rounded-xl bg-muted/40 border border-border text-center min-w-[70px]">
                  <div className="text-[10px] uppercase font-bold text-muted-foreground">Rubric</div>
                  <div className="text-base font-bold text-foreground tabular-nums">
                    {breakdown.raw_judge_score ?? "—"}
                  </div>
                </div>
                {breakdown.ops_max_points !== null && breakdown.ops_max_points !== undefined && (
                  <div className="p-2.5 rounded-xl bg-foreground/[0.06] border border-foreground/20 text-center min-w-[70px]">
                    <div className="text-[10px] uppercase font-bold text-foreground">Operations</div>
                    <div className="text-base font-bold text-foreground tabular-nums">
                      {breakdown.ops_score ?? "—"}
                    </div>
                  </div>
                )}
                <div className="p-2.5 rounded-xl bg-muted/40 border border-border text-center min-w-[70px]">
                  <div className="text-[10px] uppercase font-bold text-muted-foreground">Timing</div>
                  <div className={`text-base font-bold tabular-nums ${
                    (breakdown.timing_adjustment ?? 0) > 0 ? "text-emerald-500" : (breakdown.timing_adjustment ?? 0) < 0 ? "text-rose-500" : "text-muted-foreground"
                  }`}>
                    {(breakdown.timing_adjustment ?? 0) > 0 ? `+${breakdown.timing_adjustment}` : (breakdown.timing_adjustment ?? 0)}
                  </div>
                </div>
                <div className="p-2.5 rounded-xl bg-primary/10 border border-primary/25 text-center min-w-[80px]">
                  <div className="text-[10px] uppercase font-bold text-primary">Final</div>
                  <div className="text-lg font-black text-foreground tabular-nums">
                    {breakdown.final_score ?? "—"}
                    {breakdown.score_percent !== null && (
                      <span className="text-xs text-muted-foreground ml-1 font-normal font-sans">
                        ({breakdown.score_percent}%)
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </DialogHeader>

        {isLoading ? (
          <div className="py-12 flex justify-center">
            <Spinner />
          </div>
        ) : !breakdown ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            No score data found for this team.
          </div>
        ) : (
          <div className="mt-4 space-y-6">
            {/* Timing & Submission Lock Audit Card */}
            <div className="p-4 rounded-xl bg-muted/20 border border-border/70 space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold text-foreground">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <Clock size={14} className="text-primary" />
                  Submission Lock Timestamp
                </span>
                <span className="font-mono">
                  {breakdown.final_locked_at ? new Date(breakdown.final_locked_at).toLocaleString() : "Not finalized"}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Resolved Timing Adjustment:</span>
                <div className="flex items-center gap-2">
                  <span className={`font-semibold px-2 py-0.5 rounded-full text-[11px] border ${
                    (breakdown.timing_adjustment ?? 0) > 0
                      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                      : (breakdown.timing_adjustment ?? 0) < 0
                      ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                      : "bg-muted text-muted-foreground border-border"
                  }`}>
                    {breakdown.timing_badge || `${breakdown.timing_adjustment ?? 0} pts`}
                  </span>
                  {breakdown.is_timing_override && (
                    <span className="bg-purple-500/10 text-purple-400 border border-purple-500/30 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase">
                      Ops Override
                    </span>
                  )}
                </div>
              </div>
              {breakdown.timing_override_notes && (
                <div className="text-[11px] text-muted-foreground italic border-t border-border/40 pt-1 mt-1">
                  Ops Note: {breakdown.timing_override_notes}
                </div>
              )}
            </div>

            {/* Operations Criteria — graded by the SpacePoint team, not the judges */}
            {(breakdown.ops_breakdown ?? []).length > 0 && (
              <div className="p-4 rounded-xl bg-foreground/[0.03] border border-foreground/20 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-foreground">
                    Operations Criteria
                  </span>
                  <span className="font-bold tabular-nums text-foreground">
                    {breakdown.ops_score ?? "—"}
                    {breakdown.ops_max_points !== null && breakdown.ops_max_points !== undefined && (
                      <span className="font-normal text-muted-foreground"> / {breakdown.ops_max_points}</span>
                    )}
                  </span>
                </div>
                <div className="border border-border/60 rounded-xl overflow-hidden bg-card">
                  <table className="w-full text-xs">
                    <tbody className="divide-y divide-border/60">
                      {(breakdown.ops_breakdown ?? []).map((c) => (
                        <Fragment key={c.key}>
                          <tr className="hover:bg-muted/20">
                            <td className="py-2 px-3 font-medium text-foreground">{c.label}</td>
                            <td className="py-2 px-3 text-right text-muted-foreground font-mono w-20">{c.max_points}</td>
                            <td className="py-2 px-3 text-right font-bold text-foreground tabular-nums w-24">
                              {c.awarded_points !== null && c.awarded_points !== undefined ? c.awarded_points : "—"}
                            </td>
                          </tr>
                          {(c.subs ?? []).map((s) => (
                            <tr key={`${c.key}.${s.key}`} className="hover:bg-muted/20 bg-muted/20">
                              <td className="py-1.5 pl-7 pr-3 text-muted-foreground">↳ {s.label}</td>
                              <td className="py-1.5 px-3 text-right text-muted-foreground font-mono">{s.max_points}</td>
                              <td className="py-1.5 px-3 text-right tabular-nums text-foreground">
                                {s.awarded_points !== null && s.awarded_points !== undefined ? s.awarded_points : "—"}
                              </td>
                            </tr>
                          ))}
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
                {breakdown.ops_criterion_notes && (
                  <div className="text-[11px] text-muted-foreground italic">
                    Operations note: {breakdown.ops_criterion_notes}
                  </div>
                )}
              </div>
            )}

            {/* Judges Selector Tabs */}
            {breakdown.judges.length > 0 ? (
              <div>
                <div className="flex items-center gap-2 border-b border-border pb-2">
                  {breakdown.judges.map((j, idx) => (
                    <button
                      key={j.judge_user_id}
                      onClick={() => setSelectedJudgeIdx(idx)}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                        selectedJudgeIdx === idx
                          ? "bg-primary text-primary-foreground shadow-sm"
                          : "bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                    >
                      <User size={13} />
                      <span>{j.judge_name}</span>
                      <span className="font-bold tabular-nums ml-1 bg-black/20 px-1.5 py-0.2 rounded">
                        {j.total_points} pts
                      </span>
                    </button>
                  ))}
                </div>

                {activeJudge && (
                  <div className="mt-4 space-y-5">
                    {/* Judge Info Subtitle */}
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <div>
                        Evaluated by <strong className="text-foreground">{activeJudge.judge_name}</strong> ({activeJudge.judge_email})
                      </div>
                      {activeJudge.submitted_at && (
                        <div>Submitted: {new Date(activeJudge.submitted_at).toLocaleString()}</div>
                      )}
                    </div>

                    {/* Criteria Breakdown Table */}
                    <div className="border border-border rounded-xl overflow-hidden">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-muted/40 text-muted-foreground border-b border-border text-left uppercase tracking-wider font-semibold">
                            <th className="py-2.5 px-3">Rubric Criterion</th>
                            <th className="py-2.5 px-3 w-24 text-right">Max Pts</th>
                            <th className="py-2.5 px-3 w-28 text-right">Awarded</th>
                            <th className="py-2.5 px-3">Criterion Feedback</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/60">
                          {activeJudge.criteria.map((c) => (
                            <Fragment key={c.key}>
                              <tr className="hover:bg-muted/20">
                                <td className="py-2.5 px-3 font-medium text-foreground">
                                  {c.label}
                                </td>
                                <td className="py-2.5 px-3 text-right text-muted-foreground font-mono">
                                  {c.max_points}
                                </td>
                                <td className="py-2.5 px-3 text-right font-bold text-foreground tabular-nums">
                                  {c.awarded_points !== null && c.awarded_points !== undefined ? c.awarded_points : "—"}
                                </td>
                                <td className="py-2.5 px-3 text-muted-foreground">
                                  {c.comment ? (
                                    <span className="text-foreground italic font-normal">"{c.comment}"</span>
                                  ) : (
                                    <span className="text-muted-foreground/60">—</span>
                                  )}
                                </td>
                              </tr>
                              {(c.subs ?? []).map((s) => (
                                <tr key={`${c.key}.${s.key}`} className="hover:bg-muted/20 bg-muted/20">
                                  <td className="py-1.5 pl-7 pr-3 text-muted-foreground">↳ {s.label}</td>
                                  <td className="py-1.5 px-3 text-right text-muted-foreground font-mono">{s.max_points}</td>
                                  <td className="py-1.5 px-3 text-right tabular-nums text-foreground">
                                    {s.awarded_points !== null && s.awarded_points !== undefined ? s.awarded_points : "—"}
                                  </td>
                                  <td />
                                </tr>
                              ))}
                            </Fragment>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* Overall Judge Feedback / Notes Card */}
                    {activeJudge.notes ? (
                      <div className="p-4 rounded-xl bg-card border border-border/80 space-y-1.5">
                        <div className="flex items-center gap-1.5 text-xs font-semibold text-primary">
                          <MessageSquare size={13} />
                          Overall Judge Notes & Feedback:
                        </div>
                        <p className="text-xs text-foreground whitespace-pre-wrap leading-relaxed pl-5 italic">
                          "{activeJudge.notes}"
                        </p>
                      </div>
                    ) : (
                      <div className="text-xs text-muted-foreground italic">
                        No general qualitative notes provided by this judge.
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="py-6 text-center text-sm text-muted-foreground">
                This team has not been scored by any judges yet.
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
