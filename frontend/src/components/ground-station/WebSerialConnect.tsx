/** Web Serial direct-connect controls — ported from the legacy app's browser
 * hardware link (its `btn-detect` / `btn-disconnect` / `active-port-label`
 * trio in index.html + main.js). Lets a student plug the ESP32 straight into
 * their own machine and stream telemetry without the on-site agent. */
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
      {!connected && (
        <button
          type="button"
          onClick={() => void connect()}
          className="text-xs rounded-lg px-3 py-1.5 ring-1 ring-emerald-500/45 bg-emerald-500/15 text-emerald-500 hover:bg-emerald-500/25"
        >
          Detect Ports
        </button>
      )}
      {connected && (
        <button
          type="button"
          onClick={() => void disconnect()}
          className="text-xs rounded-lg px-3 py-1.5 ring-1 ring-destructive/45 bg-destructive/15 text-destructive hover:bg-destructive/25"
        >
          Disconnect
        </button>
      )}
      <span className={`text-[11px] ${connected ? "text-emerald-500" : "text-muted-foreground"}`}>
        {connected ? "Web Serial USB" : "No Port"}
      </span>
      {error && <span className="text-[11px] text-destructive">{error}</span>}
    </div>
  );
}
