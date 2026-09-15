/** Command center — the legacy app's command buttons (motor spin/stop, take
 * picture, ping, status, fake-data toggle), backed by the server-side
 * allowlist in `services/ground_station/commands.py`. A rejected/unknown
 * command never reaches the hardware — it 400s before it's even queued.
 * Styled after the legacy `.admin-card`/`.btn-cmd` glass-and-glow look —
 * cyan for status/info, violet for the camera/sim commands, red for
 * anything that spins a motor. */
import { useState } from "react";
import { sendCommand } from "@/api/groundStation";

interface AckEntry {
  commandId: string;
  name: string;
  ok?: boolean;
  detail?: string;
  at: string;
}

type Tone = "cyan" | "violet" | "warn";

const TONE_CLASSES: Record<Tone, string> = {
  cyan: "text-[#00d2ff] bg-[rgba(0,210,255,0.1)] ring-1 ring-[rgba(0,210,255,0.3)] hover:bg-[rgba(0,210,255,0.25)] hover:shadow-[0_0_10px_rgba(0,210,255,0.4)]",
  violet: "text-[#c586ff] bg-[rgba(168,85,247,0.12)] ring-1 ring-[rgba(168,85,247,0.35)] hover:bg-[rgba(168,85,247,0.28)] hover:shadow-[0_0_10px_rgba(168,85,247,0.4)]",
  warn: "text-[#ff6188] bg-[rgba(255,65,108,0.1)] ring-1 ring-[rgba(255,65,108,0.3)] hover:bg-[rgba(255,65,108,0.25)] hover:shadow-[0_0_10px_rgba(255,65,108,0.4)]",
};

const COMMANDS: { name: string; label: string; tone: Tone }[] = [
  { name: "PING", label: "Ping", tone: "cyan" },
  { name: "GET_STATUS", label: "Get status", tone: "cyan" },
  { name: "FAKE", label: "Toggle sim data", tone: "violet" },
  { name: "TAKE_PICTURE", label: "Take picture", tone: "violet" },
  { name: "SPIN_CW", label: "⟳ Spin CW", tone: "warn" },
  { name: "SPIN_CCW", label: "⟲ Spin CCW", tone: "warn" },
  { name: "STOP", label: "Stop motor", tone: "warn" },
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
    <div
      className="rounded-2xl p-5 backdrop-blur-md shadow-[0_8px_32px_rgba(0,0,0,0.3)]"
      style={{ background: "rgba(16,20,30,0.7)", border: "1px solid rgba(255,255,255,0.1)" }}
    >
      <div
        className="text-sm font-semibold mb-4 pb-2"
        style={{ color: "#00d2ff", borderBottom: "1px solid rgba(255,255,255,0.1)" }}
      >
        Command center
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
        {COMMANDS.map((c) => (
          <button
            key={c.name}
            type="button"
            disabled={pending === c.name}
            onClick={() => void fire(c.name)}
            className={`rounded-lg px-3 py-2.5 text-xs font-semibold transition-all duration-200 disabled:opacity-40 ${TONE_CLASSES[c.tone]}`}
          >
            {pending === c.name ? "Sending…" : c.label}
          </button>
        ))}
      </div>
      {error && <div className="text-xs text-destructive mb-3">{error}</div>}
      <div className="text-[11px] font-semibold uppercase tracking-wide mb-1" style={{ color: "rgba(215,210,203,0.75)" }}>
        Recent acks
      </div>
      <div className="space-y-1 max-h-32 overflow-y-auto font-mono text-[11px]">
        {acks.length === 0 && <div className="text-muted-foreground">No commands acknowledged yet.</div>}
        {acks.slice().reverse().map((a) => (
          <div key={`${a.commandId}-${a.at}`} className={a.ok === false ? "text-[#ff6188]" : "text-[#39ff14]"}>
            {a.name} {a.ok === false ? "FAILED" : "OK"} {a.detail ? `— ${a.detail}` : ""}
          </div>
        ))}
      </div>
    </div>
  );
}
