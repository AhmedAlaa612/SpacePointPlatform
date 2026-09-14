/** Command center — the legacy app's command buttons (motor spin/stop, take
 * picture, ping, status, fake-data toggle), backed by the server-side
 * allowlist in `services/ground_station/commands.py`. A rejected/unknown
 * command never reaches the hardware — it 400s before it's even queued. */
import { useState } from "react";
import { sendCommand } from "@/api/groundStation";

interface AckEntry {
  commandId: string;
  name: string;
  ok?: boolean;
  detail?: string;
  at: string;
}

const COMMANDS: { name: string; label: string }[] = [
  { name: "PING", label: "Ping" },
  { name: "GET_STATUS", label: "Get status" },
  { name: "FAKE", label: "Toggle sim data" },
  { name: "SPIN_CW", label: "Spin CW" },
  { name: "SPIN_CCW", label: "Spin CCW" },
  { name: "STOP", label: "Stop motor" },
  { name: "TAKE_PICTURE", label: "Take picture" },
];

interface Props {
  deviceId: string;
  acks: AckEntry[];
}

export default function CommandConsole({ deviceId, acks }: Props) {
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function fire(name: string) {
    setPending(name);
    setError(null);
    try {
      await sendCommand(deviceId, name);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Command failed";
      setError(msg);
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="rounded-xl ring-1 ring-border p-4 bg-card">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-3">
        Command center
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
        {COMMANDS.map((c) => (
          <button
            key={c.name}
            type="button"
            disabled={pending === c.name}
            onClick={() => fire(c.name)}
            className="rounded-lg px-3 py-2 text-xs font-medium ring-1 ring-border hover:bg-muted disabled:opacity-50 transition-colors"
          >
            {pending === c.name ? "Sending…" : c.label}
          </button>
        ))}
      </div>
      {error && <div className="text-xs text-destructive mb-2">{error}</div>}
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
        Recent acks
      </div>
      <div className="space-y-1 max-h-32 overflow-y-auto font-mono text-[11px]">
        {acks.length === 0 && <div className="text-muted-foreground">No commands acknowledged yet.</div>}
        {acks.slice().reverse().map((a) => (
          <div key={`${a.commandId}-${a.at}`} className={a.ok === false ? "text-destructive" : ""}>
            {a.name} {a.ok === false ? "FAILED" : "OK"} {a.detail ? `— ${a.detail}` : ""}
          </div>
        ))}
      </div>
    </div>
  );
}
