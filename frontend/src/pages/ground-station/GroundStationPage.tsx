/** Ground Station console — ported from the legacy Madar platform's
 * LoRa-Dashboard-V3. `DeviceConsole` is the reusable live-console body;
 * it's mounted by `pages/learn/GroundStationAttemptPage.tsx`, keyed to one
 * mission attempt's rig (2026-09-14 rework — see that file and
 * backend/app/services/ground_station/access.py for the ownership model). */
import { useEffect, useRef, useState } from "react";
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { ackCommand, getHistory, listPhotos, type GroundStationDevice, type GroundStationPhoto } from "@/api/groundStation";
import { useGroundStationSocket, type GroundStationMessage } from "@/hooks/useGroundStationSocket";
import AttitudeCube from "@/components/ground-station/AttitudeCube";
import CommandConsole from "@/components/ground-station/CommandConsole";
import MissionGallery from "@/components/ground-station/MissionGallery";
import HistoryPanel from "@/components/ground-station/HistoryPanel";
import AlertsPanel from "@/components/ground-station/AlertsPanel";
import EarthGlobe from "@/components/ground-station/EarthGlobe";
import SimToggle from "@/components/ground-station/SimToggle";
import WebSerialConnect from "@/components/ground-station/WebSerialConnect";
import { isWebSerialConnected, writeSerialCommand } from "@/lib/groundStationWebSerial";
import { buildGroundStationReport } from "@/lib/pdf";

const MAX_TREND_POINTS = 240;

interface TelemetryFrame {
  t: number;
  recorded_at: string;
  temp?: number;
  voltage?: number;
  current?: number;
  power?: number;
  rssi?: number;
  snr?: number;
  pitch?: number;
  roll?: number;
  yaw?: number;
  lat?: number;
  lon?: number;
  alt?: number;
}

interface AckEntry {
  commandId: string;
  name: string;
  ok?: boolean;
  detail?: string;
  at: string;
}

// Same per-metric colors as the legacy dashboard's charts.js `metrics`
// array, kept for visual parity.
const CHARTS: { key: keyof TelemetryFrame; label: string; unit: string; color: string }[] = [
  { key: "temp", label: "Temperature", unit: "°C", color: "#ff6b6b" },
  { key: "voltage", label: "Voltage", unit: "V", color: "#00c6ff" },
  { key: "current", label: "Current", unit: "A", color: "#f9d423" },
  { key: "power", label: "Power", unit: "mW", color: "#a855f7" },
  { key: "rssi", label: "Signal RSSI", unit: "dBm", color: "#00ff7f" },
  { key: "snr", label: "SNR", unit: "dB", color: "#39ff14" },
];

export function DeviceConsole({ deviceId, device }: { deviceId: string; device: GroundStationDevice }) {
  const [history, setHistory] = useState<TelemetryFrame[]>([]);
  const [acks, setAcks] = useState<AckEntry[]>([]);
  const [photos, setPhotos] = useState<GroundStationPhoto[]>([]);
  const [alertRefreshToken, setAlertRefreshToken] = useState(0);
  const [exporting, setExporting] = useState(false);
  const liveChartsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listPhotos(deviceId).then(setPhotos).catch(() => setPhotos([]));
  }, [deviceId]);

  useEffect(() => {
    // Seed the live cards from what's already recorded — otherwise a rig
    // that posted data five minutes ago (and hasn't since) shows
    // "Collecting telemetry" forever just because no *new* frame has
    // arrived over the socket since this tab opened.
    getHistory(deviceId, 60)
      .then((res) => {
        setHistory(res.data.slice(-MAX_TREND_POINTS).map((p, i) => ({
          t: i, recorded_at: p.recorded_at,
          temp: p.temp ?? undefined, voltage: p.voltage ?? undefined, current: p.current ?? undefined,
          power: p.power ?? undefined, rssi: p.rssi ?? undefined, snr: p.snr ?? undefined,
          pitch: p.pitch ?? undefined, roll: p.roll ?? undefined, yaw: p.yaw ?? undefined,
          lat: p.lat ?? undefined, lon: p.lon ?? undefined, alt: p.alt ?? undefined,
        })));
      })
      .catch(() => undefined);
  }, [deviceId]);

  const { connected } = useGroundStationSocket(deviceId, (msg: GroundStationMessage) => {
    if (msg.type === "telemetry_frame") {
      const d = msg.payload.data as Record<string, number>;
      setHistory((h) => {
        const next: TelemetryFrame = {
          t: h.length, recorded_at: msg.payload.recorded_at,
          temp: d.temp, voltage: d.voltage, current: d.current, power: d.power,
          rssi: d.rssi, snr: d.snr, pitch: d.pitch, roll: d.roll, yaw: d.yaw,
          lat: d.lat, lon: (d.lon ?? d.lng), alt: d.alt,
        };
        const out = [...h, next];
        return out.length > MAX_TREND_POINTS ? out.slice(out.length - MAX_TREND_POINTS) : out;
      });
    } else if (msg.type === "command_queued") {
      // Best-effort forwarding: whichever open tab actually has Web Serial
      // connected to the rig relays the command down the wire and acks it
      // — same fire-and-forget model as the on-site agent's ack_command.
      // A no-op for every other viewer (isWebSerialConnected() is false).
      if (isWebSerialConnected()) {
        const line = msg.payload.arg ? `${msg.payload.name} ${msg.payload.arg}` : msg.payload.name;
        void writeSerialCommand(line).then((ok) => void ackCommand(deviceId, msg.payload.id, ok));
      }
    } else if (msg.type === "command_ack") {
      setAcks((a) => [...a, {
        commandId: msg.payload.command_id, name: msg.payload.command_id.slice(0, 8),
        ok: msg.payload.ok as boolean | undefined, detail: msg.payload.detail as string | undefined,
        at: new Date().toISOString(),
      }]);
    } else if (msg.type === "photo_added") {
      setPhotos((p) => [...p, {
        path: msg.payload.path, url: msg.payload.url, captured_at: msg.payload.captured_at,
        lat: msg.payload.lat ?? null, lon: msg.payload.lon ?? null, alt: msg.payload.alt ?? null,
      }]);
    } else if (msg.type === "alert") {
      setAlertRefreshToken((n) => n + 1);
    }
  });

  const latest = history[history.length - 1];

  async function exportPdf() {
    setExporting(true);
    try {
      await buildGroundStationReport(device.label, history, photos.length, liveChartsRef.current);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <WebSerialConnect deviceId={deviceId} />
          <SimToggle deviceId={deviceId} onToggle={() => setHistory([])} />
        </div>
        <div className="flex items-center gap-3">
          <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${connected ? "text-emerald-500" : "text-muted-foreground"}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-emerald-500" : "bg-muted-foreground"}`} />
            {connected ? "Live" : "Connecting…"}
          </span>
          <button
            type="button"
            onClick={() => void exportPdf()}
            disabled={exporting}
            className="text-xs rounded-lg ring-1 ring-border px-3 py-1.5 hover:bg-muted disabled:opacity-50"
          >
            {exporting ? "Generating…" : "Export PDF"}
          </button>
        </div>
      </div>

      {history.length >= 2 ? (
        <div ref={liveChartsRef} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {CHARTS.map((c) => (
            <div
              key={c.key}
              className="gs-holo-card rounded-2xl p-5 flex flex-col gap-4 shadow-[0_8px_32px_0_rgba(0,0,0,0.3)] backdrop-blur-md transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_15px_35px_rgba(0,0,0,0.4),0_0_18px_rgba(101,63,132,0.35)]"
              style={{ background: "rgba(101,63,132,0.08)", border: "1px solid rgba(101,63,132,0.25)" }}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="text-xs uppercase tracking-widest" style={{ color: "rgba(215,210,203,0.75)" }}>
                  {c.label}
                </div>
                <div className="text-right leading-none">
                  <span className="text-2xl font-semibold text-white">
                    {latest?.[c.key] !== undefined ? Number(latest[c.key]).toFixed(2) : "--"}
                  </span>
                  <span className="ml-1 text-xs tracking-wide" style={{ color: "rgba(215,210,203,0.75)" }}>{c.unit}</span>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={90}>
                <AreaChart data={history} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                  <defs>
                    <linearGradient id={`gs-grad-${c.key}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={c.color} stopOpacity={0.4} />
                      <stop offset="100%" stopColor={c.color} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="2 4" stroke="rgba(255,255,255,0.08)" vertical={false} />
                  <XAxis dataKey="t" tick={{ fontSize: 9, fill: "rgba(255,255,255,0.5)" }} stroke="rgba(255,255,255,0.1)" minTickGap={30} />
                  <YAxis tick={{ fontSize: 9, fill: "rgba(255,255,255,0.5)" }} stroke="rgba(255,255,255,0.1)" width={32} />
                  <Tooltip
                    contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid rgba(101,63,132,0.4)", background: "rgba(20,10,30,0.95)", color: "#fff" }}
                    formatter={(v) => [`${Number(v ?? 0).toFixed(2)} ${c.unit}`, c.label] as [string, string]}
                  />
                  <Area type="monotone" dataKey={c.key as string} stroke={c.color} strokeWidth={2} fill={`url(#gs-grad-${c.key})`} isAnimationActive={false} dot={false} />
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

      <EarthGlobe lat={latest?.lat ?? null} lon={latest?.lon ?? null} alt={latest?.alt ?? null} />

      <HistoryPanel deviceId={deviceId} />
      <AlertsPanel deviceId={deviceId} refreshToken={alertRefreshToken} />
      <CommandConsole deviceId={deviceId} acks={acks} />
      <MissionGallery photos={photos} />
    </div>
  );
}
