/** Command center — the legacy app's command buttons (motor spin/stop, take
 * picture, ping, status, fake-data toggle), backed by the server-side
 * allowlist in `services/ground_station/commands.py`. A rejected/unknown
 * command never reaches the hardware — it 400s before it's even queued.
 *
 * Layout mirrors the legacy's actual structure, not just its colors: a
 * prominent camera button up top, status/sim commands as a row, and motor
 * control broken into its own bordered sub-panel with CCW/STOP/CW laid out
 * left-to-right the way the physical controls read (see the legacy's
 * `#command-center-card` — a hero button, then a "Quick Spin" sub-panel,
 * not one flat grid of equal-weight buttons). */
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

interface BtnProps {
  name: string;
  tone: Tone;
  className?: string;
  children: React.ReactNode;
  pending: string | null;
  onFire: (name: string) => void;
}

function Btn({ name, tone, className = "", children, pending, onFire }: BtnProps) {
  return (
    <button
      type="button"
      disabled={pending === name}
      onClick={() => onFire(name)}
      className={`rounded-lg text-xs font-semibold transition-all duration-200 disabled:opacity-40 ${TONE_CLASSES[tone]} ${className}`}
    >
      {pending === name ? "Sending…" : children}
    </button>
  );
}

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

      <Btn name="TAKE_PICTURE" tone="violet" pending={pending} onFire={(n) => void fire(n)} className="w-full py-3 text-sm mb-4">
        📷 Take a picture
      </Btn>

      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide" style={{ color: "rgba(215,210,203,0.75)" }}>
        Status &amp; sim
      </div>
      <div className="grid grid-cols-3 gap-2 mb-4">
        <Btn name="PING" tone="cyan" pending={pending} onFire={(n) => void fire(n)} className="py-2.5">Ping</Btn>
        <Btn name="GET_STATUS" tone="cyan" pending={pending} onFire={(n) => void fire(n)} className="py-2.5">Get status</Btn>
        <Btn name="FAKE" tone="violet" pending={pending} onFire={(n) => void fire(n)} className="py-2.5">Toggle sim</Btn>
      </div>

      <div
        className="rounded-xl p-3 mb-4"
        style={{ background: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.05)" }}
      >
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide" style={{ color: "rgba(215,210,203,0.75)" }}>
          Motor control
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Btn name="SPIN_CCW" tone="warn" pending={pending} onFire={(n) => void fire(n)} className="py-3 text-base">⟲</Btn>
          <Btn name="STOP" tone="warn" pending={pending} onFire={(n) => void fire(n)} className="py-3 font-bold">STOP</Btn>
          <Btn name="SPIN_CW" tone="warn" pending={pending} onFire={(n) => void fire(n)} className="py-3 text-base">⟳</Btn>
        </div>
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
