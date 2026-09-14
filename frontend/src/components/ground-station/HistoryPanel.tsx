/** Historical telemetry — ported from the legacy app's `history.js`: a
 * time-range picker, a live/paused toggle, and a chart+table over
 * `/ground-station/devices/{id}/history`. Refresh cadence mirrors the
 * legacy's `refreshRate()` (10s under an hour, 30s beyond it). */
import { useEffect, useRef, useState } from "react";
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getHistory, type TelemetryPoint } from "@/api/groundStation";

const RANGE_OPTIONS = [
  { minutes: 15, label: "Last 15 min" },
  { minutes: 60, label: "Last 1 hour" },
  { minutes: 360, label: "Last 6 hours" },
  { minutes: 1440, label: "Last 24 hours" },
  { minutes: 10080, label: "Last 7 days" },
  { minutes: 43200, label: "Last 1 month" },
];

function refreshRateMs(minutes: number): number {
  if (minutes <= 60) return 10_000;
  if (minutes <= 1440) return 30_000;
  return 60_000;
}

const METRICS: { key: keyof TelemetryPoint; label: string; unit: string; color: string }[] = [
  { key: "temp", label: "Temperature", unit: "°C", color: "#ff6b6b" },
  { key: "voltage", label: "Voltage", unit: "V", color: "#00d2ff" },
  { key: "current", label: "Current", unit: "mA", color: "#ffd93d" },
  { key: "power", label: "Power", unit: "mW", color: "#6bcb77" },
  { key: "rssi", label: "RSSI", unit: "dBm", color: "#c77dff" },
];

interface Props {
  deviceId: string;
  chartRef?: React.RefObject<HTMLDivElement | null>;
}

export default function HistoryPanel({ deviceId, chartRef }: Props) {
  const [minutes, setMinutes] = useState(60);
  const [live, setLive] = useState(false);
  const [rows, setRows] = useState<TelemetryPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function load() {
    setLoading(true);
    try {
      const res = await getHistory(deviceId, minutes);
      setRows(res.data);
    } finally {
      setLoading(false);
    }
  }

  // Background refresh (mount + live-poll interval) never toggles the
  // "loading" spinner — only the manual Refresh button does, since that's
  // a plain event handler and not subject to the effect-body setState rule.
  function backgroundRefresh() {
    getHistory(deviceId, minutes).then((res) => setRows(res.data)).catch(() => undefined);
  }

  useEffect(() => {
    backgroundRefresh();
    if (timerRef.current) clearInterval(timerRef.current);
    if (live) {
      timerRef.current = setInterval(backgroundRefresh, refreshRateMs(minutes));
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deviceId, minutes, live]);

  const chartData = rows.map((r) => ({ ...r, t: new Date(r.recorded_at).getTime() }));

  return (
    <div className="rounded-xl ring-1 ring-border p-4 bg-card space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">History</div>
        <div className="flex items-center gap-2">
          <select
            value={minutes}
            onChange={(e) => setMinutes(Number(e.target.value))}
            className="text-xs rounded-lg ring-1 ring-border px-2 py-1 bg-background"
          >
            {RANGE_OPTIONS.map((r) => (
              <option key={r.minutes} value={r.minutes}>{r.label}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => setLive((v) => !v)}
            className={`text-xs rounded-lg px-3 py-1 ring-1 ring-border ${live ? "bg-emerald-500/15 text-emerald-500" : "hover:bg-muted"}`}
          >
            {live ? "Live" : "Paused"}
          </button>
          <button type="button" onClick={() => void load()} className="text-xs rounded-lg px-3 py-1 ring-1 ring-border hover:bg-muted">
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="text-center text-xs text-muted-foreground py-8">No historical data for this range yet.</div>
      ) : (
        <div ref={chartRef} className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {METRICS.map((m) => (
            <div key={m.key} className="rounded-lg ring-1 ring-border overflow-hidden">
              <div className="px-3 pt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{m.label}</div>
              <ResponsiveContainer width="100%" height={110}>
                <AreaChart data={chartData} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id={`hist-grad-${m.key}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={m.color} stopOpacity={0.35} />
                      <stop offset="100%" stopColor={m.color} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="2 4" stroke="currentColor" className="text-border" vertical={false} />
                  <XAxis dataKey="t" tickFormatter={(t) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} tick={{ fontSize: 9 }} stroke="currentColor" className="text-muted-foreground" minTickGap={40} />
                  <YAxis tick={{ fontSize: 9 }} stroke="currentColor" className="text-muted-foreground" width={36} />
                  <Tooltip
                    contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid var(--border)", background: "var(--card)", color: "var(--foreground)" }}
                    labelFormatter={(t) => new Date(Number(t)).toLocaleString()}
                    formatter={(v) => [`${Number(v ?? 0).toFixed(1)} ${m.unit}`, m.label] as [string, string]}
                  />
                  <Area type="monotone" dataKey={m.key as string} stroke={m.color} strokeWidth={1.6} fill={`url(#hist-grad-${m.key})`} isAnimationActive={false} dot={false} connectNulls />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
