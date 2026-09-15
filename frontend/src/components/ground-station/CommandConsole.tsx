/** Command center — the legacy app's command buttons (motor spin/stop,
 * ping, status, fake-data toggle), backed by the server-side allowlist in
 * `services/ground_station/commands.py`. A rejected/unknown command never
 * reaches the hardware — it 400s before it's even queued.
 *
 * Layout has real hierarchy — a status/sim row, then motor control broken
 * out into its own bordered sub-panel with CCW/STOP/CW laid out
 * left-to-right the way the physical controls read — but styled in the
 * platform's own purple (`--primary`), not a legacy-style multi-color
 * scheme. */
import { useState } from "react";
import { sendCommand } from "@/api/groundStation";

interface AckEntry {
  commandId: string;
  name: string;
  ok?: boolean;
  detail?: string;
  at: string;
}

interface BtnProps {
  name: string;
  className?: string;
  children: React.ReactNode;
  pending: string | null;
  onFire: (name: string) => void;
}

function Btn({ name, className = "", children, pending, onFire }: BtnProps) {
  return (
    <button
      type="button"
      disabled={pending === name}
      onClick={() => onFire(name)}
      className={`rounded-lg text-xs font-semibold text-primary bg-primary/10 ring-1 ring-primary/30 transition-all duration-200 hover:bg-primary/25 hover:shadow-[0_0_10px_rgba(167,125,255,0.4)] disabled:opacity-40 ${className}`}
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
      <div className="text-sm font-semibold mb-4 pb-2 text-primary" style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}>
        Command center
      </div>

      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide" style={{ color: "rgba(215,210,203,0.75)" }}>
        Status &amp; sim
      </div>
      <div className="grid grid-cols-2 gap-2 mb-4">
        <Btn name="PING" pending={pending} onFire={(n) => void fire(n)} className="py-2.5">Ping</Btn>
        <Btn name="GET_STATUS" pending={pending} onFire={(n) => void fire(n)} className="py-2.5">Get status</Btn>
        <Btn name="FAKE" pending={pending} onFire={(n) => void fire(n)} className="py-2.5">Toggle sim</Btn>
        <Btn name="TAKE_PICTURE" pending={pending} onFire={(n) => void fire(n)} className="py-2.5">Take a picture</Btn>
      </div>

      <div
        className="rounded-xl p-3 mb-4"
        style={{ background: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.05)" }}
      >
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide" style={{ color: "rgba(215,210,203,0.75)" }}>
          Motor control
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Btn name="SPIN_CCW" pending={pending} onFire={(n) => void fire(n)} className="py-3 text-base">⟲</Btn>
          <Btn name="STOP" pending={pending} onFire={(n) => void fire(n)} className="py-3 font-bold bg-primary/25 ring-primary/50">STOP</Btn>
          <Btn name="SPIN_CW" pending={pending} onFire={(n) => void fire(n)} className="py-3 text-base">⟳</Btn>
        </div>
      </div>

      {error && <div className="text-xs text-destructive mb-3">{error}</div>}

      <div className="text-[11px] font-semibold uppercase tracking-wide mb-1" style={{ color: "rgba(215,210,203,0.75)" }}>
        Recent acks
      </div>
      <div className="space-y-1 max-h-32 overflow-y-auto font-mono text-[11px]">
        {acks.length === 0 && <div className="text-muted-foreground">No commands acknowledged yet.</div>}
        {acks.slice().reverse().map((a) => (
          <div key={`${a.commandId}-${a.at}`} className={a.ok === false ? "text-destructive" : "text-primary"}>
            {a.name} {a.ok === false ? "FAILED" : "OK"} {a.detail ? `— ${a.detail}` : ""}
          </div>
        ))}
      </div>
    </div>
  );
}
