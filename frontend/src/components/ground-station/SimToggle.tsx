/** "Sat Control / Sim" switch — the legacy app's own simulation toggle,
 * ported. Flip it on and synthetic telemetry starts flowing immediately,
 * through the same no-auth ingest path real hardware uses (persisted,
 * broadcast to every viewer) — no board, agent, or Web Serial required.
 * Good for demos and for proving the console itself works before any
 * hardware is on hand. */
import { useEffect, useRef, useState } from "react";
import { sendBrowserTelemetry } from "@/api/groundStation";

const INTERVAL_MS = 1000;

interface Props {
  deviceId: string;
}

function fakeFrame() {
  const t = Date.now() / 1000;
  return {
    temp: 25.0 + 5.0 * Math.sin(t * 0.1),
    voltage: 3.7 + 0.3 * Math.sin(t * 0.05),
    current: 0.4 + 0.1 * Math.sin(t * 0.2),
    power: (3.7 + 0.3 * Math.sin(t * 0.05)) * (0.4 + 0.1 * Math.sin(t * 0.2)),
    rssi: -70 + 8 * Math.sin(t * 0.15),
    snr: 8 + 3 * Math.sin(t * 0.25),
    roll: 10.0 * Math.sin(t * 0.3),
    pitch: 8.0 * Math.cos(t * 0.25),
    yaw: (t * 5.0) % 360,
  };
}

export default function SimToggle({ deviceId }: Props) {
  const [simOn, setSimOn] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!simOn) return;
    void sendBrowserTelemetry(deviceId, fakeFrame());
    timerRef.current = setInterval(() => {
      void sendBrowserTelemetry(deviceId, fakeFrame());
    }, INTERVAL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [simOn, deviceId]);

  return (
    <div className="flex items-center gap-2 rounded-full ring-1 ring-border bg-card px-1 py-1">
      <span className="pl-2 text-xs text-muted-foreground">Sat control</span>
      <button
        type="button"
        onClick={() => setSimOn((v) => !v)}
        className={`rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
          simOn ? "bg-violet-500/20 text-violet-500 ring-1 ring-violet-500/40" : "text-muted-foreground hover:bg-muted"
        }`}
      >
        Sim
      </button>
      {simOn && (
        <span className="mr-1 flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-semibold text-emerald-500 ring-1 ring-emerald-500/40 bg-emerald-500/10">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
          SIM: ON
        </span>
      )}
    </div>
  );
}
