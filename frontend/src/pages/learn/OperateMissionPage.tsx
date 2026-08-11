import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, Link } from "@tanstack/react-router";
import { isAxiosError } from "axios";
import { AlertTriangle, CheckCircle2, ChevronRight, Radio, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { fetchOperateState, finishOperation, sendCommand, type OperateState } from "@/api/missionsOperate";

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail;
  return fallback;
}

const SUBSYSTEMS = ["EPS", "CDHS", "ADCS", "COMMS", "PAYLOAD"] as const;

function subsystemStatus(state: OperateState, subsystem: string): "nominal" | "critical" | "resolved" {
  const relevant = state.anomalies.filter((a) => a.subsystem === subsystem && a.triggered);
  if (relevant.length === 0) return "nominal";
  return relevant.every((a) => a.resolved) ? "resolved" : "critical";
}

/** The operate mission console (Phase 2B, Stage 7B-4) — live telemetry,
 * subsystem health lights, and a terminal, polling every 2s while the
 * attempt is in_progress (same polling-not-push transport this platform
 * already uses for other live surfaces). Telemetry and anomaly state are
 * both pure functions on the backend, so polling is just "ask again" —
 * there's no session state client and server could disagree about. */
export default function OperateMissionPage() {
  const { attemptId } = useParams({ strict: false }) as { attemptId: string };
  const [state, setState] = useState<OperateState | null>(null);
  const [error, setError] = useState("");
  const [command, setCommand] = useState("");
  const [sending, setSending] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const [finishError, setFinishError] = useState("");
  const terminalEndRef = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    fetchOperateState(attemptId).then(setState).catch(() => setError("Couldn't load this mission."));
  }, [attemptId]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (state?.attempt_status !== "in_progress") return;
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, [state?.attempt_status, load]);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [state?.events.length]);

  const handleSend = async () => {
    if (!command.trim() || !state) return;
    setSending(true);
    const toSend = command.trim();
    setCommand("");
    try {
      const result = await sendCommand(attemptId, toSend);
      setState(result.state);
    } catch (err) {
      setError(errorDetail(err, "Command failed to send."));
    } finally {
      setSending(false);
    }
  };

  const handleFinish = async () => {
    setFinishing(true);
    setFinishError("");
    try {
      const result = await finishOperation(attemptId);
      setState(result.state);
    } catch (err) {
      setFinishError(errorDetail(err, "Couldn't end the session right now."));
    } finally {
      setFinishing(false);
    }
  };

  if (error) return <div className="mx-auto max-w-[1000px] px-5 py-10"><p className="text-sm text-destructive">{error}</p></div>;
  if (!state) return <div className="mx-auto max-w-[1000px] px-5 py-10"><p className="text-sm text-muted-foreground">Establishing uplink...</p></div>;

  const decided = state.attempt_status === "passed" || state.attempt_status === "failed";
  const t = state.telemetry;

  return (
    <div className="mx-auto max-w-[1000px] px-5 sm:px-8 py-6 sm:py-8 flex flex-col gap-6">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Link to="/learn/missions" className="text-primary hover:opacity-80">Missions</Link>
        <ChevronRight className="size-3" />
        <span className="text-foreground">Operate Your Satellite</span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-2">
          <div className="w-fit flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded-md bg-primary/10 text-primary">
            <Radio className="size-3" /> Operate Mission &middot; {state.variant_label}
          </div>
          <h1 className="font-display text-2xl sm:text-3xl font-extrabold tracking-tight">Ground Station Console</h1>
        </div>
        {decided ? (
          <div className={`flex items-center gap-1.5 text-sm font-semibold ${state.attempt_status === "passed" ? "text-emerald-500" : "text-destructive"}`}>
            {state.attempt_status === "passed" ? <CheckCircle2 className="size-5" /> : <XCircle className="size-5" />}
            {state.attempt_status === "passed" ? "Mission Passed" : "Mission Failed"} &middot; {state.score}%
          </div>
        ) : (
          <Button onClick={() => void handleFinish()} disabled={finishing}>
            {finishing ? "Ending session..." : "End session"}
          </Button>
        )}
      </div>
      {finishError && <p className="text-xs text-destructive">{finishError}</p>}

      {/* Subsystem health lights */}
      <div className="grid grid-cols-5 gap-2">
        {SUBSYSTEMS.map((sub) => {
          const status = subsystemStatus(state, sub);
          const cls = status === "critical" ? "ring-destructive/40 bg-destructive/10 text-destructive"
            : status === "resolved" ? "ring-emerald-500/30 bg-emerald-500/10 text-emerald-500"
            : "ring-border text-muted-foreground";
          return (
            <div key={sub} className={`flex flex-col items-center gap-1 py-3 rounded-xl ring-1 ${cls}`}>
              {status === "critical" && <AlertTriangle className="size-4" />}
              <span className="text-[11px] font-semibold uppercase tracking-wide">{sub}</span>
              <span className="text-[10px] capitalize">{status}</span>
            </div>
          );
        })}
      </div>

      {/* Telemetry grid */}
      <Card className="p-5">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">Live Telemetry &middot; T+{state.elapsed_seconds.toFixed(0)}s</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
          <div><span className="text-muted-foreground">Battery</span><p className="font-mono">{t.battery_voltage.toFixed(2)}V / {t.battery_percentage}%</p></div>
          <div><span className="text-muted-foreground">Panel Temp</span><p className="font-mono">{t.panel_temp.toFixed(1)}&deg;C</p></div>
          <div><span className="text-muted-foreground">System Temp</span><p className="font-mono">{t.system_temp.toFixed(1)}&deg;C</p></div>
          <div><span className="text-muted-foreground">Signal</span><p className="font-mono">{t.signal_strength.toFixed(1)} dBm</p></div>
          <div><span className="text-muted-foreground">Pitch/Roll/Yaw</span><p className="font-mono">{t.pitch.toFixed(1)}&deg; / {t.roll.toFixed(1)}&deg; / {t.yaw.toFixed(1)}&deg;</p></div>
          <div><span className="text-muted-foreground">Reaction Wheel</span><p className="font-mono">{t.reaction_wheel_speed.toFixed(0)} RPM</p></div>
          <div><span className="text-muted-foreground">Solar Current</span><p className="font-mono">{t.solar_current.toFixed(2)}A</p></div>
          <div><span className="text-muted-foreground">Humidity/Light</span><p className="font-mono">{t.humidity.toFixed(1)}% / {t.light.toFixed(0)}lux</p></div>
        </div>
      </Card>

      {/* Score */}
      <Card className="p-4 flex items-center justify-between text-sm">
        <span className="text-muted-foreground">Anomalies resolved</span>
        <span className="font-semibold">{state.resolved_count} / {state.triggered_count} &middot; {state.score}% (need {state.pass_threshold}%)</span>
      </Card>

      {/* Terminal */}
      <div className="rounded-xl overflow-hidden ring-1 ring-border">
        <div className="bg-[#0a0d14] p-5 flex flex-col gap-1.5 max-h-[320px] overflow-y-auto font-mono text-[13px]">
          <div className="text-[#64ffda]/85">SYSTEM: GROUND STATION UPLINK ESTABLISHED // TYPE "HELP" FOR COMMANDS.</div>
          {state.events.map((e) => (
            <div key={e.seq} className="flex flex-col gap-0.5">
              <div className="text-[#8892b0]">operator@groundstation:~$ {e.command}</div>
              <div className={e.success ? "text-emerald-400" : "text-red-400"}>{e.message}</div>
            </div>
          ))}
          <div ref={terminalEndRef} />
        </div>
        <form
          onSubmit={(ev) => { ev.preventDefault(); void handleSend(); }}
          className="flex items-center gap-2 px-5 py-3 bg-[#07090e] border-t border-border/40"
        >
          <span className="text-[#64ffda] font-mono font-bold">$</span>
          <input
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            disabled={decided || sending}
            placeholder={decided ? "Session ended" : 'Type HELP or a telecommand...'}
            className="flex-1 bg-transparent border-none text-white font-mono text-sm outline-none placeholder:text-muted-foreground disabled:opacity-50"
            autoFocus
          />
          <button
            type="submit"
            disabled={decided || sending || !command.trim()}
            className="text-[#64ffda] font-mono text-xs font-semibold uppercase tracking-wide disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
