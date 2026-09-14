/** Web Serial direct-connect button — ported from the legacy app's browser
 * hardware link. Lets a student plug the ESP32 straight into their own
 * machine and stream telemetry without the on-site agent. */
import { useState } from "react";
import {
  connectWebSerial, disconnectWebSerial, isWebSerialSupported,
} from "@/lib/groundStationWebSerial";
import { sendBrowserTelemetry } from "@/api/groundStation";

interface Props {
  deviceId: string;
}

export default function WebSerialConnect({ deviceId }: Props) {
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const supported = isWebSerialSupported();

  async function connect() {
    setError(null);
    try {
      await connectWebSerial({
        onConnect: () => setConnected(true),
        onDisconnect: () => setConnected(false),
        onTelemetry: (entry) => { void sendBrowserTelemetry(deviceId, entry.data); },
        onAdcsTelemetry: (entry) => { void sendBrowserTelemetry(deviceId, entry); },
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to connect");
    }
  }

  async function disconnect() {
    await disconnectWebSerial({ onDisconnect: () => setConnected(false) });
  }

  if (!supported) {
    return (
      <span className="text-[11px] text-muted-foreground">
        Web Serial direct-connect needs Chrome or Edge.
      </span>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={() => void (connected ? disconnect() : connect())}
        className={`text-xs rounded-lg px-3 py-1.5 ring-1 ring-border hover:bg-muted ${connected ? "bg-emerald-500/15 text-emerald-500" : ""}`}
      >
        {connected ? "Disconnect USB" : "Connect via USB (Web Serial)"}
      </button>
      {error && <span className="text-[11px] text-destructive">{error}</span>}
    </div>
  );
}
