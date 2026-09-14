/** Ground Station — live CubeSat telemetry/command console, ported from the
 * legacy Madar platform's LoRa-Dashboard-V3. No mission/attempt/scoring
 * wrapper (see backend/app/models/ground_station/__init__.py) — any logged-in
 * user connects and sees live data from whichever rig is online. */
import { useEffect, useState } from "react";
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { listDevices, listPhotos, type GroundStationDevice, type GroundStationPhoto } from "@/api/groundStation";
import { useGroundStationSocket, type GroundStationMessage } from "@/hooks/useGroundStationSocket";
import AttitudeCube from "@/components/ground-station/AttitudeCube";
import CommandConsole from "@/components/ground-station/CommandConsole";
import MissionGallery from "@/components/ground-station/MissionGallery";
import { buildGroundStationReport } from "@/lib/pdf";

const MAX_TREND_POINTS = 240;

interface TelemetryFrame {
  t: number;
  temp?: number;
  voltage?: number;
  current?: number;
  power?: number;
  rssi?: number;
  snr?: number;
  pitch?: number;
  roll?: number;
  yaw?: number;
}

interface AckEntry {
  commandId: string;
  name: string;
  ok?: boolean;
  detail?: string;
  at: string;
}

const CHARTS: { key: keyof TelemetryFrame; label: string; unit: string; color: string }[] = [
  { key: "temp", label: "Temperature", unit: "°C", color: "#F7B267" },
  { key: "voltage", label: "Battery voltage", unit: "V", color: "#6DD3FB" },
  { key: "current", label: "Current", unit: "A", color: "#A77DFF" },
  { key: "power", label: "Power", unit: "mW", color: "#70C1B3" },
  { key: "rssi", label: "Signal (RSSI)", unit: "dBm", color: "#F25F5C" },
  { key: "snr", label: "SNR", unit: "dB", color: "#50514F" },
];

export default function GroundStationPage() {
  const [devices, setDevices] = useState<GroundStationDevice[]>([]);
  const [deviceId, setDeviceId] = useState<string | null>(null);

  useEffect(() => {
    listDevices().then((d) => {
      setDevices(d);
      if (d.length > 0) setDeviceId((cur) => cur ?? d[0].id);
    });
  }, []);

  const selectedDevice = devices.find((d) => d.id === deviceId) ?? null;

  return (
    <div className="p-4 sm:p-6 max-w-6xl mx-auto space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Ground Station</h1>
          <p className="text-xs text-muted-foreground">
            Live CubeSat telemetry and command console.
          </p>
        </div>
        {devices.length > 1 && (
          <select
            value={deviceId ?? ""}
            onChange={(e) => setDeviceId(e.target.value)}
            className="text-xs rounded-lg ring-1 ring-border px-2 py-1.5 bg-background"
          >
            {devices.map((d) => (
              <option key={d.id} value={d.id}>{d.label}</option>
            ))}
          </select>
        )}
      </div>

      {devices.length === 0 && (
        <div className="rounded-xl ring-1 ring-border p-6 text-center text-xs text-muted-foreground bg-card">
          No ground station rigs registered yet.
        </div>
      )}

      {/* Keyed by deviceId so switching rigs remounts fresh state (history,
          acks, photos) instead of an effect manually resetting it. */}
      {deviceId && selectedDevice && <DeviceConsole key={deviceId} deviceId={deviceId} device={selectedDevice} />}
    </div>
  );
}

function DeviceConsole({ deviceId, device }: { deviceId: string; device: GroundStationDevice }) {
  const [history, setHistory] = useState<TelemetryFrame[]>([]);
  const [acks, setAcks] = useState<AckEntry[]>([]);
  const [photos, setPhotos] = useState<GroundStationPhoto[]>([]);

  useEffect(() => {
    listPhotos(deviceId).then(setPhotos).catch(() => setPhotos([]));
  }, [deviceId]);

  const { connected } = useGroundStationSocket(deviceId, (msg: GroundStationMessage) => {
    if (msg.type === "telemetry_frame") {
      const d = msg.payload.data as Record<string, number>;
      setHistory((h) => {
        const next: TelemetryFrame = {
          t: h.length,
          temp: d.temp, voltage: d.voltage, current: d.current, power: d.power,
          rssi: d.rssi, snr: d.snr, pitch: d.pitch, roll: d.roll, yaw: d.yaw,
        };
        const out = [...h, next];
        return out.length > MAX_TREND_POINTS ? out.slice(out.length - MAX_TREND_POINTS) : out;
      });
    } else if (msg.type === "command_ack") {
      setAcks((a) => [...a, {
        commandId: msg.payload.command_id, name: msg.payload.command_id.slice(0, 8),
        ok: msg.payload.ok as boolean | undefined, detail: msg.payload.detail as string | undefined,
        at: new Date().toISOString(),
      }]);
    } else if (msg.type === "photo_added") {
      setPhotos((p) => [...p, { path: msg.payload.path, url: msg.payload.url, captured_at: msg.payload.captured_at }]);
    }
  });

  const latest = history[history.length - 1];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end gap-3">
        <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${connected ? "text-emerald-500" : "text-muted-foreground"}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-emerald-500" : "bg-muted-foreground"}`} />
          {connected ? "Live" : "Connecting…"}
        </span>
        <button
          type="button"
          onClick={() => buildGroundStationReport(device.label, history, photos)}
          className="text-xs rounded-lg ring-1 ring-border px-3 py-1.5 hover:bg-muted"
        >
          Export PDF
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        {CHARTS.map((c) => (
          <div key={c.key} className="rounded-xl ring-1 ring-border p-3 bg-card text-center">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{c.label}</div>
            <div className="font-mono text-sm font-semibold">
              {latest?.[c.key] !== undefined ? Number(latest[c.key]).toFixed(1) : "--"}
              <span className="text-[10px] text-muted-foreground ml-0.5">{c.unit}</span>
            </div>
          </div>
        ))}
      </div>

      {history.length >= 2 ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {CHARTS.map((c) => (
            <div key={c.key} className="rounded-xl ring-1 ring-border overflow-hidden bg-card">
              <div className="px-4 pt-3 pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                {c.label}
              </div>
              <ResponsiveContainer width="100%" height={120}>
                <AreaChart data={history} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id={`gs-grad-${c.key}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={c.color} stopOpacity={0.35} />
                      <stop offset="100%" stopColor={c.color} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="2 4" stroke="currentColor" className="text-border" vertical={false} />
                  <XAxis dataKey="t" tick={{ fontSize: 9 }} stroke="currentColor" className="text-muted-foreground" minTickGap={30} />
                  <YAxis tick={{ fontSize: 9 }} stroke="currentColor" className="text-muted-foreground" width={38} />
                  <Tooltip
                    contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid var(--border)", background: "var(--card)", color: "var(--foreground)" }}
                    formatter={(v) => [`${Number(v ?? 0).toFixed(1)} ${c.unit}`, c.label] as [string, string]}
                  />
                  <Area type="monotone" dataKey={c.key as string} stroke={c.color} strokeWidth={1.8} fill={`url(#gs-grad-${c.key})`} isAnimationActive={false} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-xl ring-1 ring-border p-6 text-center text-xs text-muted-foreground bg-card">
          Collecting telemetry — trends appear once a few samples are in.
        </div>
      )}

      {latest?.pitch !== undefined && latest?.roll !== undefined && latest?.yaw !== undefined && (
        <AttitudeCube pitch={latest.pitch} roll={latest.roll} yaw={latest.yaw} />
      )}

      <CommandConsole deviceId={deviceId} acks={acks} />
      <MissionGallery photos={photos} />
    </div>
  );
}
