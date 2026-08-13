/** Telemetry trend charts (Operate v2, Stage 7C-5).
 *
 * SatKit kept a rolling ten-sample history in `App.js` and drew four
 * Chart.js line charts from it. The v1 port dropped them and showed
 * instantaneous numbers in a text grid instead.
 *
 * Getting them back is not cosmetic. **A battery voltage of 3.5 V is fine;
 * a battery voltage that has been falling for six minutes is an anomaly.**
 * You cannot see that in a number, which is why the v1 console could not
 * support diagnosis even in principle and had to put the answer on the
 * health light instead.
 *
 * Built on recharts — already a dependency here (`instructors/admin/Overview`
 * uses it), so no bundle cost. The live console accumulates its own history
 * from the poll loop; the debrief passes the server's frozen trace to the
 * same component, so both views are literally the same chart.
 */
import {
  Area, AreaChart, CartesianGrid, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

export interface TrendPoint {
  t: number;
  soc: number;
  wheel_rpm: number;
  payload_temp: number;
  signal: number;
  storage?: number;
  downlinked?: number;
}

export interface TrendSpec {
  key: keyof TrendPoint;
  label: string;
  unit: string;
  color: string;
  /** Flight-rule limit; drawn as a dashed reference line so the chart shows
   * the same threshold the console colours against and the briefing taught. */
  limit?: number;
  limitSide?: "above" | "below";
  domain?: [number | "auto", number | "auto"];
}

/** The four channels worth trending. Not exported — both callers want the
 * same set, and a chart list that varies per page would defeat the point of
 * the console and the debrief being literally the same chart. */
const TREND_SPECS: TrendSpec[] = [
  { key: "soc", label: "Battery charge", unit: "%", color: "#6DD3FB", limit: 40, limitSide: "below", domain: [0, 100] },
  { key: "wheel_rpm", label: "Reaction wheel", unit: "RPM", color: "#A77DFF", limit: 4500, limitSide: "above", domain: [0, 6200] },
  { key: "payload_temp", label: "Instrument temp", unit: "°C", color: "#F7B267", limit: 55, limitSide: "above", domain: ["auto", "auto"] },
  { key: "signal", label: "Signal strength", unit: "dBm", color: "#70C1B3", domain: [-125, -60] },
];

interface Props {
  data: TrendPoint[];
  specs?: TrendSpec[];
  /** Pass windows, shaded so the signal chart's peaks line up with a reason. */
  passes?: { start_t: number; end_t: number }[];
  eclipses?: { start_t: number; end_t: number }[];
  height?: number;
  columns?: string;
}

function clock(t: number): string {
  const m = Math.floor(t / 60);
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;
}

export default function TelemetryTrends({
  data, specs = TREND_SPECS, passes = [], eclipses = [], height = 132,
  columns = "grid-cols-1 lg:grid-cols-2",
}: Props) {
  if (data.length < 2) {
    return (
      <div className="rounded-xl ring-1 ring-border p-6 text-center text-xs text-muted-foreground">
        Collecting telemetry — trends appear once a few samples are in.
      </div>
    );
  }

  return (
    <div className={`grid ${columns} gap-3`}>
      {specs.map((spec) => {
        const last = data[data.length - 1][spec.key] as number;
        const first = data[0][spec.key] as number;
        const delta = last - first;
        const breached =
          spec.limit !== undefined &&
          (spec.limitSide === "above" ? last >= spec.limit : last <= spec.limit);

        return (
          <div key={String(spec.key)} className="rounded-xl ring-1 ring-border overflow-hidden bg-card">
            <div className="flex items-baseline justify-between px-4 pt-3 pb-1">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                {spec.label}
              </span>
              <span className="flex items-baseline gap-2">
                <span className={`font-mono text-sm font-semibold ${breached ? "text-destructive" : ""}`}>
                  {typeof last === "number" ? last.toFixed(spec.key === "wheel_rpm" ? 0 : 1) : "--"}
                  <span className="text-[10px] text-muted-foreground ml-0.5">{spec.unit}</span>
                </span>
                <span
                  className={`font-mono text-[10px] ${
                    Math.abs(delta) < 0.05 ? "text-muted-foreground" : delta > 0 ? "text-emerald-500" : "text-amber-500"
                  }`}
                >
                  {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}
                </span>
              </span>
            </div>
            <ResponsiveContainer width="100%" height={height}>
              <AreaChart data={data} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id={`grad-${String(spec.key)}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={spec.color} stopOpacity={0.35} />
                    <stop offset="100%" stopColor={spec.color} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="2 4" stroke="currentColor" className="text-border" vertical={false} />

                {eclipses.map((e, i) => (
                  <ReferenceArea
                    key={`e${i}`} x1={e.start_t} x2={e.end_t}
                    fill="currentColor" className="text-foreground" fillOpacity={0.06} strokeOpacity={0}
                  />
                ))}
                {passes.map((p, i) => (
                  <ReferenceArea
                    key={`p${i}`} x1={p.start_t} x2={p.end_t}
                    fill="#10b981" fillOpacity={0.1} strokeOpacity={0}
                  />
                ))}

                <XAxis
                  dataKey="t" type="number" domain={["dataMin", "dataMax"]}
                  tickFormatter={clock} tick={{ fontSize: 9 }} stroke="currentColor"
                  className="text-muted-foreground" minTickGap={30}
                />
                <YAxis
                  domain={spec.domain ?? ["auto", "auto"]} tick={{ fontSize: 9 }}
                  stroke="currentColor" className="text-muted-foreground" width={38}
                />
                {spec.limit !== undefined && (
                  <ReferenceLine
                    y={spec.limit} stroke="#f87171" strokeDasharray="4 3" strokeWidth={1}
                    label={{ value: "limit", fontSize: 9, fill: "#f87171", position: "insideTopRight" }}
                  />
                )}
                <Tooltip
                  contentStyle={{
                    fontSize: 11, borderRadius: 8, border: "1px solid var(--border)",
                    background: "var(--card)", color: "var(--foreground)",
                  }}
                  labelFormatter={(v) => `T+${clock(Number(v))}`}
                  formatter={(v) => [`${Number(v ?? 0).toFixed(1)} ${spec.unit}`, spec.label] as [string, string]}
                />
                <Area
                  type="monotone" dataKey={spec.key as string} stroke={spec.color} strokeWidth={1.8}
                  fill={`url(#grad-${String(spec.key)})`} isAnimationActive={false} dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        );
      })}
    </div>
  );
}
