/** The debrief (Operate v2, Stage 7C-8) — where the learning lands.
 *
 * A score teaches nothing. What teaches is seeing the moment the battery
 * started falling, noticing it was four minutes before you did anything,
 * and reading what the correct response would have been.
 *
 * Everything here comes from the trace frozen at finish time, so a debrief
 * opened next week shows the flight that was actually graded — not a
 * re-simulation against a variant someone has since retuned. That is the
 * same "never retroactively change graded work" discipline the design
 * mission had to learn from Madar (F2/F4).
 *
 * Disclosure is always full here, whatever the variant's in-flight setting.
 * Once the flight is over, withholding the explanation from someone who
 * just lost a pass to a fault serves nobody.
 */
import { useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  AlertTriangle, CheckCircle2, ChevronRight, Clock, FileText, MinusCircle, RotateCcw, XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import OrbitTimeline from "@/components/missions/OrbitTimeline";
import TelemetryTrends, { type TrendPoint } from "@/components/missions/TelemetryTrends";
import { countdown, fetchDebrief, flightClock, type Debrief } from "@/api/missionsOperate";

const OUTCOME_META: Record<string, { icon: typeof CheckCircle2; tone: string; label: string }> = {
  resolved: { icon: CheckCircle2, tone: "text-emerald-500", label: "Caught in time" },
  late: { icon: Clock, tone: "text-amber-500", label: "Fixed, but late" },
  unresolved: { icon: XCircle, tone: "text-destructive", label: "Never resolved" },
};

const NOTE_TONE: Record<string, string> = {
  good: "ring-emerald-500/30 bg-emerald-500/5",
  warn: "ring-amber-500/30 bg-amber-500/5",
  bad: "ring-destructive/30 bg-destructive/5",
};

const NOTE_ICON: Record<string, typeof CheckCircle2> = {
  good: CheckCircle2,
  warn: AlertTriangle,
  bad: XCircle,
};

function SummaryStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex flex-col gap-0.5 px-3 py-2.5 rounded-xl ring-1 ring-border">
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="font-mono text-sm font-semibold">{value}</span>
    </div>
  );
}

export default function OperateDebrief({ attemptId, missionId }: { attemptId: string; missionId: string }) {
  const [debrief, setDebrief] = useState<Debrief | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchDebrief(attemptId).then(setDebrief).catch(() => setError("Couldn't load the debrief."));
  }, [attemptId]);

  if (error) {
    return <div className="mx-auto max-w-[1000px] px-5 py-10"><p className="text-sm text-destructive">{error}</p></div>;
  }
  if (!debrief) {
    return <div className="mx-auto max-w-[1000px] px-5 py-10"><p className="text-sm text-muted-foreground">Reconstructing the flight...</p></div>;
  }

  const s = debrief.report.summary ?? {};
  const trend: TrendPoint[] = debrief.trace.map((p) => ({
    t: p.t, soc: p.soc, wheel_rpm: p.wheel_rpm, payload_temp: p.payload_temp,
    signal: p.signal, storage: p.storage, downlinked: p.downlinked,
  }));

  return (
    <div className="mx-auto max-w-[1000px] px-5 sm:px-8 py-6 sm:py-8 flex flex-col gap-6">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Link to="/learn/missions" className="text-primary hover:opacity-80">Missions</Link>
        <ChevronRight className="size-3" />
        <Link to="/learn/missions/$missionId" params={{ missionId }} className="text-primary hover:opacity-80">
          Flight Operations
        </Link>
        <ChevronRight className="size-3" />
        <span className="text-foreground">Debrief</span>
      </div>

      {/* --- verdict ------------------------------------------------------ */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            {debrief.variant_label} · post-flight debrief
          </span>
          <h1 className={`font-display text-3xl font-extrabold tracking-tight flex items-center gap-2 ${
            debrief.passed ? "text-emerald-500" : "text-destructive"
          }`}>
            {debrief.passed ? <CheckCircle2 className="size-7" /> : <XCircle className="size-7" />}
            {debrief.passed ? "Mission accomplished" : "Mission failed"}
          </h1>
          <p className="text-sm text-muted-foreground">
            Scored <span className="font-mono font-semibold text-foreground">{debrief.score.toFixed(1)}%</span>
            {" "}against a {debrief.pass_threshold}% threshold.
          </p>
        </div>
        <Link to="/learn/missions/$missionId" params={{ missionId }}>
          <Button variant="outline" className="gap-1.5">
            <RotateCcw className="size-3.5" /> Fly it again
          </Button>
        </Link>
      </div>

      {/* --- score breakdown ---------------------------------------------- */}
      <Card className="p-5 flex flex-col gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">How the score was built</p>
        <div className="grid sm:grid-cols-3 gap-3">
          <div className="flex flex-col gap-1">
            <span className="text-[11px] text-muted-foreground">Objectives (60%)</span>
            <span className="font-mono text-lg font-semibold">{debrief.objectives_score.toFixed(1)}%</span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[11px] text-muted-foreground">Fault response (40%)</span>
            <span className="font-mono text-lg font-semibold">{debrief.performance_score.toFixed(1)}%</span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[11px] text-muted-foreground">Penalties</span>
            <span className={`font-mono text-lg font-semibold ${debrief.penalty_points > 0 ? "text-destructive" : ""}`}>
              −{debrief.penalty_points.toFixed(1)}
            </span>
          </div>
        </div>
        <div className="flex flex-col gap-2 border-t border-border/60 pt-3">
          {debrief.objectives.map((o) => (
            <div key={o.key} className="flex items-center gap-3 text-xs">
              {o.met
                ? <CheckCircle2 className="size-3.5 text-emerald-500 shrink-0" />
                : <MinusCircle className="size-3.5 text-muted-foreground shrink-0" />}
              <span className="flex-1">{o.label}</span>
              <span className="font-mono text-muted-foreground">{o.detail}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* --- the flight, replayed ----------------------------------------- */}
      <div className="flex flex-col gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Your flight</p>
          <p className="text-[11px] text-muted-foreground mt-1">
            Fault windows are shaded above the orbit strip — green where you caught it, amber where you were late,
            red where it was never fixed.
          </p>
        </div>
        <Card className="p-4">
          <OrbitTimeline
            sessionSeconds={debrief.timeline.session_seconds}
            periodSeconds={debrief.timeline.period_seconds}
            orbits={debrief.timeline.orbits}
            passes={debrief.timeline.passes}
            eclipses={debrief.timeline.eclipses}
            saa={debrief.timeline.saa}
            anomalies={debrief.anomaly_windows.map((a) => ({
              start_t: a.start_t, end_t: a.end_t, outcome: a.outcome, title: a.title,
            }))}
          />
        </Card>
        <TelemetryTrends
          data={trend}
          passes={debrief.timeline.passes}
          eclipses={debrief.timeline.eclipses}
        />
      </div>

      {/* --- what happened ------------------------------------------------ */}
      <Tabs defaultValue="notes" className="gap-3">
        <TabsList>
          <TabsTrigger value="notes">What to take away</TabsTrigger>
          <TabsTrigger value="anomalies">Faults ({debrief.anomaly_windows.length})</TabsTrigger>
          <TabsTrigger value="report">Flight report</TabsTrigger>
          <TabsTrigger value="log">Full log</TabsTrigger>
        </TabsList>

        <TabsContent value="notes" className="flex flex-col gap-2">
          {debrief.report.notes?.map((note, i) => {
            const Icon = NOTE_ICON[note.tone] ?? AlertTriangle;
            return (
              <div key={i} className={`flex items-start gap-2.5 rounded-xl ring-1 px-4 py-3 ${NOTE_TONE[note.tone]}`}>
                <Icon className={`size-4 shrink-0 mt-0.5 ${
                  note.tone === "good" ? "text-emerald-500" : note.tone === "warn" ? "text-amber-500" : "text-destructive"
                }`} />
                <p className="text-xs leading-relaxed">{note.text}</p>
              </div>
            );
          })}
          {debrief.penalties.length > 0 && (
            <div className="mt-2 flex flex-col gap-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Penalties</p>
              {debrief.penalties.map((p) => (
                <div key={p.key} className="rounded-xl ring-1 ring-border px-4 py-3 flex flex-col gap-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-xs font-semibold">{p.label}{p.count > 1 ? ` ×${p.count}` : ""}</span>
                    <span className="font-mono text-xs text-destructive">−{p.points}</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-relaxed">{p.note}</p>
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="anomalies" className="flex flex-col gap-3">
          {debrief.anomaly_windows.length === 0 && (
            <p className="text-xs text-muted-foreground">No faults were raised during this flight.</p>
          )}
          {debrief.anomaly_windows.map((a, i) => {
            const meta = OUTCOME_META[a.outcome];
            const Icon = meta.icon;
            return (
              <Card key={`${a.key}-${i}`} className="p-4 flex flex-col gap-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex items-start gap-2.5">
                    <Icon className={`size-4 shrink-0 mt-0.5 ${meta.tone}`} />
                    <div>
                      <p className="text-sm font-semibold">{a.title}</p>
                      <p className="text-[11px] text-muted-foreground">
                        {a.subsystem} · {a.origin === "injected" ? "external event" : "caused by your configuration"}
                      </p>
                    </div>
                  </div>
                  <span className={`text-[11px] font-semibold ${meta.tone}`}>{meta.label}</span>
                </div>

                <div className="grid sm:grid-cols-3 gap-2 text-[11px] font-mono">
                  <span className="text-muted-foreground">
                    appeared <span className="text-foreground">{flightClock(a.start_t)}</span>
                  </span>
                  <span className="text-muted-foreground">
                    {a.response_seconds !== null
                      ? <>you responded after <span className="text-foreground">{countdown(a.response_seconds)}</span></>
                      : <span className="text-destructive">never responded</span>}
                  </span>
                  <span className="text-muted-foreground">
                    window was {countdown(a.response_window_s)}
                  </span>
                </div>

                {a.teaching.meaning && (
                  <div className="flex flex-col gap-2 border-t border-border/60 pt-3 text-xs">
                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                        What you were seeing
                      </p>
                      <p className="leading-relaxed">{a.teaching.symptom}</p>
                    </div>
                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                        What it meant
                      </p>
                      <p className="leading-relaxed">{a.teaching.meaning}</p>
                    </div>
                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-wide text-emerald-600 dark:text-emerald-400 mb-1">
                        The right response
                      </p>
                      <p className="leading-relaxed">{a.teaching.action}</p>
                    </div>
                    {a.outcome !== "resolved" && (
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-destructive mb-1">
                          What it cost you
                        </p>
                        <p className="leading-relaxed">{a.teaching.if_ignored}</p>
                      </div>
                    )}
                    {a.cleared_by && (
                      <p className="text-[11px] text-muted-foreground">
                        Cleared by <code className="font-mono text-primary">{a.cleared_by}</code>.
                      </p>
                    )}
                  </div>
                )}
              </Card>
            );
          })}
        </TabsContent>

        <TabsContent value="report" className="flex flex-col gap-3">
          <p className="text-[11px] text-muted-foreground flex items-center gap-1.5">
            <FileText className="size-3.5" /> Auto-generated post-flight record.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <SummaryStat label="Orbits flown" value={String(s.orbits_flown ?? "—")} />
            <SummaryStat label="Commands issued" value={String(s.commands_issued ?? 0)} />
            <SummaryStat label="Science takes" value={String(s.science_takes ?? 0)} />
            <SummaryStat label="Downlinked" value={`${s.downlinked_mb ?? 0} MB`} />
            <SummaryStat label="Time transmitting" value={`${s.downlink_minutes ?? 0} min`} />
            <SummaryStat label="Lowest battery" value={`${s.min_soc_pct ?? 0}%`} />
            <SummaryStat label="Peak instrument temp" value={`${s.max_payload_temp_c ?? 0} °C`} />
            <SummaryStat label="Safe mode entries" value={String(s.safe_mode_entries ?? 0)} />
            <SummaryStat label="Radiation upsets" value={String(s.obc_upsets ?? 0)} />
            <SummaryStat label="Science lost" value={String(s.science_dropped ?? 0)} />
            <SummaryStat label="Final mode" value={String(s.final_mode ?? "—")} />
            <SummaryStat
              label="Faults handled"
              value={`${debrief.report.anomaly_tally?.resolved ?? 0} / ${debrief.report.anomaly_tally?.total ?? 0}`}
            />
          </div>
        </TabsContent>

        <TabsContent value="log">
          <div className="rounded-xl overflow-hidden ring-1 ring-border">
            <div className="bg-[#0a0d14] p-4 flex flex-col gap-1 max-h-[420px] overflow-y-auto font-mono text-[11px]">
              {[
                ...debrief.spacecraft_log.map((l) => ({ t: l.t, kind: "log" as const, level: l.level, text: l.message })),
                ...debrief.events.map((e) => ({
                  t: e.sim_t, kind: "cmd" as const, level: e.success ? "OK" : "ERR",
                  text: `$ ${e.command}${e.arg ? ` ${e.arg}` : ""} — ${e.message}`,
                })),
              ]
                .sort((a, b) => a.t - b.t)
                .map((row, i) => (
                  <div key={i} className="flex gap-2 leading-relaxed">
                    <span className="text-[#4a5568] shrink-0">{flightClock(row.t).slice(2)}</span>
                    <span className={
                      row.kind === "cmd"
                        ? (row.level === "OK" ? "text-emerald-400" : "text-red-400")
                        : row.level === "ERROR" ? "text-red-400"
                        : row.level === "WARNING" ? "text-amber-400" : "text-[#8892b0]"
                    }>
                      {row.text}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
