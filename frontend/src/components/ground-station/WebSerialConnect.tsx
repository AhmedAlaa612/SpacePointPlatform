/** Web Serial direct-connect controls — ported from the legacy app's browser
 * hardware link (its `btn-detect` / `btn-disconnect` / `active-port-label`
 * trio in index.html + main.js). Lets a student plug the ESP32 straight into
 * their own machine and stream telemetry without the on-site agent. */
import { useEffect, useRef, useState } from "react";
import {
  connectWebSerial, disconnectWebSerial, isWebSerialSupported, normalizeTelemetryPayload,
} from "@/lib/groundStationWebSerial";
import { sendBrowserTelemetry } from "@/api/groundStation";

interface Props {
  deviceId: string;
  /** Called immediately on the client whenever a telemetry frame arrives
   * from USB Web Serial or SatKit Wi-Fi (`192.168.4.1`), so the Ground Station
   * charts and 3D Attitude Cube update live even if the laptop is offline on
   * the SatKit's Wi-Fi access point (`ALFALAJ-SAT1`). */
  onLocalFrame?: (data: Record<string, unknown>) => void;
  /** Exposes the active SatKit Wi-Fi host when connected over Wi-Fi so
   * CommandConsole can forward commands directly to `http://<host>/api/cmd`. */
  onWifiHostChange?: (host: string | null) => void;
}

const OFFLINE_QUEUE_KEY = "gs_offline_telemetry_queue_v1";

function queueOfflineFrame(deviceId: string, data: Record<string, unknown>) {
  try {
    const raw = localStorage.getItem(OFFLINE_QUEUE_KEY);
    const list: { deviceId: string; data: Record<string, unknown>; ts: string }[] = raw ? JSON.parse(raw) : [];
    list.push({ deviceId, data, ts: new Date().toISOString() });
    if (list.length > 300) list.splice(0, list.length - 300);
    localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(list));
  } catch {
    // ignore storage quota errors
  }
}

async function flushOfflineQueue() {
  try {
    const raw = localStorage.getItem(OFFLINE_QUEUE_KEY);
    if (!raw) return;
    const list: { deviceId: string; data: Record<string, unknown>; ts: string }[] = JSON.parse(raw);
    if (!list.length) return;
    localStorage.removeItem(OFFLINE_QUEUE_KEY);
    for (const item of list.slice(-60)) {
      try {
        await sendBrowserTelemetry(item.deviceId, item.data);
      } catch {
        // Still offline — put remaining back
        queueOfflineFrame(item.deviceId, item.data);
        break;
      }
    }
  } catch {
    // ignore
  }
}

export default function WebSerialConnect({ deviceId, onLocalFrame, onWifiHostChange }: Props) {
  const [connected, setConnected] = useState(false);
  const [wifiConnected, setWifiConnected] = useState(false);
  const [wifiHost, setWifiHost] = useState("192.168.4.1");
  const [showWifiInput, setShowWifiInput] = useState(false);
  const [queuedCount, setQueuedCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const wifiTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const supported = isWebSerialSupported();

  function forwardFrame(data: Record<string, unknown>) {
    onLocalFrame?.(data);
    sendBrowserTelemetry(deviceId, data)
      .then(() => {
        void flushOfflineQueue();
        try {
          const q = localStorage.getItem(OFFLINE_QUEUE_KEY);
          setQueuedCount(q ? JSON.parse(q).length : 0);
        } catch {
          setQueuedCount(0);
        }
      })
      .catch(() => {
        queueOfflineFrame(deviceId, data);
        try {
          const q = localStorage.getItem(OFFLINE_QUEUE_KEY);
          setQueuedCount(q ? JSON.parse(q).length : 0);
        } catch {
          // ignore
        }
      });
  }

  async function connect() {
    setError(null);
    try {
      await connectWebSerial({
        onConnect: () => setConnected(true),
        onDisconnect: () => setConnected(false),
        onTelemetry: (entry) => {
          // Single unified frame (includes temp/voltage AND roll/pitch/yaw)
          forwardFrame(entry.data);
        },
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to connect");
    }
  }

  async function disconnect() {
    await disconnectWebSerial({ onDisconnect: () => setConnected(false) });
  }

  async function pollWifiOnce(host: string): Promise<boolean> {
    const base = /^https?:\/\//i.test(host) ? host.replace(/\/+$/, "") : `http://${host.replace(/\/+$/, "")}`;
    const endpoints = [`${base}/api/telemetry`, `${base}/data`, `${base}/telemetry`];
    for (const url of endpoints) {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 1800);
      try {
        const res = await fetch(url, { signal: ctrl.signal, cache: "no-store" });
        clearTimeout(timer);
        if (!res.ok) continue;
        const text = await res.text();
        const sanitized = text.replace(/:\s*-?(?:nan|inf|infinity)\b/gi, ":null");
        const raw = JSON.parse(sanitized) as Record<string, unknown>;
        const norm = normalizeTelemetryPayload(raw);
        if (norm) {
          forwardFrame(norm);
          return true;
        }
      } catch {
        clearTimeout(timer);
      }
    }
    return false;
  }

  async function connectWifi() {
    setError(null);
    const cleanHost = wifiHost.trim() || "192.168.4.1";
    const ok = await pollWifiOnce(cleanHost);
    if (!ok) {
      const isHttps = window.location.protocol === "https:";
      setError(
        isHttps
          ? `Couldn't reach http://${cleanHost} (join ALFALAJ-SAT1 Wi-Fi & allow Insecure Content in browser site settings, or use USB)`
          : `Couldn't reach http://${cleanHost}/api/telemetry — make sure you joined ALFALAJ-SAT1 Wi-Fi`,
      );
      return;
    }
    setWifiConnected(true);
    setShowWifiInput(false);
    onWifiHostChange?.(cleanHost);
    if (wifiTimerRef.current) clearInterval(wifiTimerRef.current);
    wifiTimerRef.current = setInterval(() => {
      void pollWifiOnce(cleanHost);
    }, 1000);
  }

  function disconnectWifi() {
    if (wifiTimerRef.current) clearInterval(wifiTimerRef.current);
    wifiTimerRef.current = null;
    setWifiConnected(false);
    onWifiHostChange?.(null);
  }

  useEffect(() => {
    const onOnline = () => { void flushOfflineQueue(); };
    window.addEventListener("online", onOnline);
    return () => {
      window.removeEventListener("online", onOnline);
      if (wifiTimerRef.current) clearInterval(wifiTimerRef.current);
      void disconnectWebSerial();
    };
  }, []);

  return (
    <div className="flex flex-wrap items-center gap-2">
      {supported ? (
        <>
          {!connected ? (
            <button
              type="button"
              onClick={() => void connect()}
              className="text-xs rounded-lg px-3 py-1.5 ring-1 ring-emerald-500/45 bg-emerald-500/15 text-emerald-500 hover:bg-emerald-500/25"
            >
              Detect USB Port
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void disconnect()}
              className="text-xs rounded-lg px-3 py-1.5 ring-1 ring-destructive/45 bg-destructive/15 text-destructive hover:bg-destructive/25"
            >
              Disconnect USB
            </button>
          )}
        </>
      ) : (
        <span className="text-[11px] text-muted-foreground">
          USB Web Serial needs Chrome/Edge
        </span>
      )}

      {!wifiConnected ? (
        showWifiInput ? (
          <div className="flex items-center gap-1">
            <input
              type="text"
              value={wifiHost}
              onChange={(e) => setWifiHost(e.target.value)}
              placeholder="192.168.4.1"
              className="text-xs rounded-lg ring-1 ring-border px-2 py-1 bg-background font-mono w-28"
            />
            <button
              type="button"
              onClick={() => void connectWifi()}
              className="text-xs rounded-lg px-2.5 py-1.5 ring-1 ring-sky-500/45 bg-sky-500/15 text-sky-400 hover:bg-sky-500/25"
            >
              Link
            </button>
            <button
              type="button"
              onClick={() => setShowWifiInput(false)}
              className="text-xs rounded-lg px-2 py-1.5 text-muted-foreground hover:bg-muted"
            >
              ✕
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => void connectWifi()}
            onContextMenu={(e) => { e.preventDefault(); setShowWifiInput(true); }}
            title="Connect to SatKit Wi-Fi AP (default 192.168.4.1). Right-click to change IP."
            className="text-xs rounded-lg px-3 py-1.5 ring-1 ring-sky-500/45 bg-sky-500/15 text-sky-400 hover:bg-sky-500/25"
          >
            SatKit Wi-Fi (192.168.4.1)
          </button>
        )
      ) : (
        <button
          type="button"
          onClick={disconnectWifi}
          className="text-xs rounded-lg px-3 py-1.5 ring-1 ring-destructive/45 bg-destructive/15 text-destructive hover:bg-destructive/25"
        >
          Disconnect Wi-Fi ({wifiHost})
        </button>
      )}

      {!wifiConnected && !showWifiInput && (
        <button
          type="button"
          onClick={() => setShowWifiInput(true)}
          className="text-[11px] text-muted-foreground hover:text-foreground underline"
        >
          IP
        </button>
      )}

      <span className={`text-[11px] ${connected || wifiConnected ? "text-emerald-500" : "text-muted-foreground"}`}>
        {connected && wifiConnected
          ? "USB + Wi-Fi Live"
          : connected
            ? "Web Serial USB"
            : wifiConnected
              ? `SatKit Wi-Fi (${wifiHost})`
              : "No Hardware Link"}
      </span>
      {queuedCount > 0 && (
        <span className="text-[11px] text-amber-400" title="Telemetry frames buffered while on SatKit Wi-Fi; will sync when internet reconnects.">
          ({queuedCount} buffered offline)
        </span>
      )}
      {error && <span className="text-[11px] text-destructive">{error}</span>}
    </div>
  );
}
