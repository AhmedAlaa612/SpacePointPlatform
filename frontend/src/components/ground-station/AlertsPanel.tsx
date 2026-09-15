/** Alert thresholds + the alert feed — ported from the legacy app's
 * `/api/thresholds` + `/api/alerts` panel. Any logged-in user can edit
 * thresholds and acknowledge alerts, same access model the legacy app had
 * (see console.py's module docstring). */
import { useEffect, useState } from "react";
import {
  acknowledgeAlert, getThresholds, listAlerts, putThresholds,
  type GroundStationAlert, type Thresholds,
} from "@/api/groundStation";

interface Props {
  deviceId: string;
  /** Bumped whenever a live "alert" WS event arrives, to refresh the list. */
  refreshToken: number;
}

const FIELDS: { key: keyof Omit<Thresholds, "device_id">; label: string }[] = [
  { key: "temp_max", label: "Temp max (°C)" },
  { key: "temp_min", label: "Temp min (°C)" },
  { key: "voltage_max", label: "Voltage max (V)" },
  { key: "voltage_min", label: "Voltage min (V)" },
  { key: "current_max", label: "Current max (mA)" },
  { key: "power_max", label: "Power max (mW)" },
];

export default function AlertsPanel({ deviceId, refreshToken }: Props) {
  const [thresholds, setThresholds] = useState<Thresholds | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [alerts, setAlerts] = useState<GroundStationAlert[]>([]);
  const [saving, setSaving] = useState(false);

  function applyThresholds(t: Thresholds) {
    setThresholds(t);
    setDraft(Object.fromEntries(FIELDS.map((f) => [f.key, String(t[f.key])])));
  }

  useEffect(() => {
    getThresholds(deviceId).then(applyThresholds).catch(() => undefined);
    listAlerts(deviceId).then(setAlerts).catch(() => undefined);
  }, [deviceId]);

  useEffect(() => {
    if (refreshToken > 0) listAlerts(deviceId).then(setAlerts).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshToken]);

  async function save() {
    setSaving(true);
    try {
      const values = Object.fromEntries(FIELDS.map((f) => [f.key, Number(draft[f.key])]));
      const updated = await putThresholds(deviceId, values);
      setThresholds(updated);
    } finally {
      setSaving(false);
    }
  }

  async function ack(alertId: string) {
    await acknowledgeAlert(deviceId, alertId);
    setAlerts((a) => a.map((x) => (x.id === alertId ? { ...x, acknowledged: true } : x)));
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
      <div className="rounded-xl ring-1 ring-border p-4 bg-card">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-3">
          Alert thresholds
        </div>
        <div className="grid grid-cols-2 gap-2">
          {FIELDS.map((f) => (
            <label key={f.key} className="text-xs">
              <span className="text-muted-foreground block mb-0.5">{f.label}</span>
              <input
                type="number"
                value={draft[f.key] ?? ""}
                onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                className="w-full rounded-md ring-1 ring-border px-2 py-1 bg-background font-mono text-xs"
              />
            </label>
          ))}
        </div>
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving || !thresholds}
          className="mt-3 text-xs rounded-lg px-3 py-1.5 ring-1 ring-border hover:bg-muted disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save thresholds"}
        </button>
      </div>

      <div className="rounded-xl ring-1 ring-border p-4 bg-card">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-3">
          Alerts
        </div>
        {alerts.length === 0 ? (
          <div className="text-xs text-muted-foreground">No alerts.</div>
        ) : (
          <div className="space-y-1.5 max-h-56 overflow-y-auto">
            {alerts.map((a) => (
              <div
                key={a.id}
                className={`flex items-center justify-between gap-2 text-xs rounded-md px-2 py-1.5 ${a.acknowledged ? "opacity-50" : "bg-destructive/10 text-destructive"}`}
              >
                <span className="font-mono">
                  {a.alert_type.toUpperCase()} {a.severity.toUpperCase()}: {a.current_value} (limit {a.threshold})
                </span>
                {!a.acknowledged && (
                  <button type="button" onClick={() => void ack(a.id)} className="shrink-0 rounded px-2 py-0.5 ring-1 ring-border hover:bg-muted">
                    Ack
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
