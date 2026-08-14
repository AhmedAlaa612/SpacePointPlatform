/** The flight console (Operate v2, Stage 7C-5/6).
 *
 * What v1 showed: eight numbers in a text grid, five one-word health lights
 * that named the failing subsystem, and a terminal. What it could not show,
 * structurally, was a *trend* — and since a trend is what a fault actually
 * looks like, the answer had to be printed on the light instead.
 *
 * This console is built around the three things an operator actually reads:
 *
 *   1. **Where am I in the orbit** — the flight strip and the timeline. Are
 *      you about to lose the Sun? Is the station in view? How long have you
 *      got? Almost every decision in this mission is really a timing
 *      decision.
 *   2. **What is the spacecraft doing** — subsystem cards with live values
 *      coloured against the flight rules, plus trend charts, plus the
 *      attitude viewport. No readout names its own fault.
 *   3. **What has happened** — two separate logs. The spacecraft's own
 *      event feed (AOS, eclipse entry, fault detections) is the alert
 *      channel; the terminal is the transcript of what *you* did. SatKit
 *      had both and v1 kept only the second.
 *
 * Polling stays at 2 s, unchanged from v1 — the backend recomputes the
 * whole flight from the command log on every read, so a poll is genuinely
 * just "ask again" and there is no client state that can drift from it.
 * The trend history is accumulated client-side from those polls, the same
 * way SatKit's `App.js` did it.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { isAxiosError } from "axios";
import {
  AlertTriangle, ChevronRight, Radio, Rocket, Satellite, Sun, SunDim, Target, Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAuth } from "@/context/AuthContext";
import AttitudeView from "@/components/missions/AttitudeView";
import OpsHandbook from "@/components/missions/OpsHandbook";
import OrbitTimeline from "@/components/missions/OrbitTimeline";
import TelemetryTrends, { type TrendPoint } from "@/components/missions/TelemetryTrends";
import OperateDebrief from "@/pages/learn/OperateDebriefPanel";
import {
  CREW_ROLES, CREW_ROLE_LABELS, countdown, fetchHandbook, fetchOperateState, finishOperation,
  flightClock, sendCommand, setCrewRole,
  type CrewRole, type Handbook, type OperateState, type SubsystemCard,
} from "@/api/missionsOperate";

const POINTING_LIMIT = 5.0;
const MAX_TREND_POINTS = 240;

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail;
  return fallback;
}

const ROW_TONE: Record<string, string> = {
  nominal: "",
  warn: "text-amber-500",
  alarm: "text-destructive",
};

const CARD_TONE: Record<string, string> = {
  nominal: "ring-border",
  off: "ring-border opacity-60",
  warning: "ring-amber-500/40 bg-amber-500/5",
  critical: "ring-destructive/50 bg-destructive/5",
};

function SubsystemPanel({ card }: { card: SubsystemCard }) {
  return (
    <div className={`rounded-xl ring-1 p-3.5 flex flex-col gap-2 ${CARD_TONE[card.status] ?? "ring-border"}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide">{card.subsystem}</span>
        <span
          className={`text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ${
            card.status === "critical"
              ? "bg-destructive/15 text-destructive"
              : card.status === "warning"
                ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
                : "bg-muted text-muted-foreground"
          }`}
        >
          {card.status}
        </span>
      </div>
      <div className="flex flex-col gap-1">
        {card.rows.map((row) => (
          <div key={row.key} className="flex items-baseline justify-between gap-2 text-[11px]">
            <span className="text-muted-foreground truncate">{row.label}</span>
            <span className={`font-mono shrink-0 ${ROW_TONE[row.status] ?? ""}`}>
              {typeof row.value === "number" ? row.value.toLocaleString() : row.value}
              {row.unit && <span className="text-muted-foreground ml-0.5">{row.unit}</span>}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

const LOG_TONE: Record<string, string> = {
  INFO: "text-[#8892b0]",
  WARNING: "text-amber-400",
  ERROR: "text-red-400",
};

/** Where you stand right now, in a sentence.
 *
 * The running score is honest but easy to misread while a flight is young:
 * protective objectives are scaled by how much of the session has actually
 * been flown, so a passing score at T+2 min means almost nothing. What a
 * student needs is not another number but the consequence — am I going to
 * pass if I keep doing this, and if not, which objective is the reason.
 *
 * Doing nothing is the case worth naming explicitly. A flight where no
 * command has been issued looks identical to a careful one from the outside
 * (nothing is on fire, telemetry is nominal) right up until the debrief
 * says zero science was collected.
 */
function MissionStanding({ state }: { state: OperateState }) {
  const remaining = Math.max(0, state.session_seconds - state.sim_t);
  const elapsedFrac = state.session_seconds ? state.sim_t / state.session_seconds : 0;
  const passing = state.score >= state.pass_threshold;
  const short = state.pass_threshold - state.score;

  // The unmet objective furthest from done — the one costing the most.
  const worst = state.objectives
    .filter((o) => !o.met)
    .sort((a, b) => a.fraction - b.fraction)[0];

  const idle = state.events.length === 0 && elapsedFrac > 0.08;

  let tone: string;
  let headline: string;
  let body: string;

  if (idle) {
    tone = "ring-destructive/40 bg-destructive/5 text-destructive";
    headline = "You haven't issued a command yet";
    body = `The satellite will keep flying whether you act or not, and none of the `
      + `objectives complete on their own. ${countdown(remaining)} left. Open the ops `
      + `handbook if you're not sure where to start — the first move is usually PAYLOAD_ON.`;
  } else if (passing) {
    tone = "ring-emerald-500/40 bg-emerald-500/5 text-emerald-600 dark:text-emerald-400";
    headline = `On course to pass — ${state.score.toFixed(0)}% against a ${state.pass_threshold}% bar`;
    body = worst
      ? `${countdown(remaining)} left. ${worst.label} is still the weakest at `
        + `${Math.round(worst.fraction * 100)}%, so that's where the remaining margin is.`
      : `${countdown(remaining)} left, and every objective is met. Keep the spacecraft healthy — `
        + `the protective objectives are scored over the whole session, not just this moment.`;
  } else {
    tone = "ring-amber-500/40 bg-amber-500/5 text-amber-600 dark:text-amber-500";
    headline = `Currently failing — ${short.toFixed(0)} points short of the ${state.pass_threshold}% bar`;
    body = worst
      ? `${countdown(remaining)} left. The biggest gap is "${worst.label}" at `
        + `${Math.round(worst.fraction * 100)}% — ${worst.detail}.`
      : `${countdown(remaining)} left. Penalties are what's holding the score down; `
        + `clear the open anomalies before they cost more.`;
  }

  return (
    <div className={`rounded-xl ring-1 px-4 py-2.5 flex flex-col gap-1 ${tone}`}>
      <p className="text-xs font-semibold">{headline}</p>
      <p className="text-[11px] leading-relaxed text-muted-foreground">{body}</p>
    </div>
  );
}

export default function OperateMissionPage() {
  const { attemptId } = useParams({ strict: false }) as { attemptId: string };
  const { currentUser } = useAuth();

  const [state, setState] = useState<OperateState | null>(null);
  const [handbook, setHandbook] = useState<Handbook | null>(null);
  const [error, setError] = useState("");
  const [command, setCommand] = useState("");
  const [sending, setSending] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const [finishError, setFinishError] = useState("");
  const [crewError, setCrewError] = useState("");
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [cmdHistory, setCmdHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const terminalEndRef = useRef<HTMLDivElement>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  // Every poll contributes one sample. This is what makes a *trend* visible
  // — the single most important thing v1's console could not do.
  const absorb = useCallback((next: OperateState) => {
    setState(next);
    const t = next.telemetry;
    setTrend((prev) => {
      const last = prev[prev.length - 1];
      if (last && Math.abs(last.t - next.sim_t) < 1) return prev;
      const point: TrendPoint = {
        t: next.sim_t,
        soc: Number(t.battery_soc ?? 0),
        wheel_rpm: Number(t.wheel_rpm ?? 0),
        payload_temp: Number(t.payload_temp_c ?? 0),
        signal: Number(t.signal_strength ?? -120),
        storage: Number(t.storage_used_mb ?? 0),
        downlinked: Number(t.downlinked_mb ?? 0),
      };
      return [...prev, point].slice(-MAX_TREND_POINTS);
    });
  }, []);

  const load = useCallback(() => {
    fetchOperateState(attemptId).then(absorb).catch(() => setError("Couldn't load this flight."));
  }, [attemptId, absorb]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    fetchHandbook(attemptId).then(setHandbook).catch(() => {});
  }, [attemptId]);

  useEffect(() => {
    if (state?.attempt_status !== "in_progress") return;
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, [state?.attempt_status, load]);

  useEffect(() => { terminalEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [state?.events.length]);
  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [state?.spacecraft_log.length]);

  const handleSend = async () => {
    if (!command.trim() || !state) return;
    const toSend = command.trim();
    setSending(true);
    setCommand("");
    setCmdHistory((h) => [...h, toSend].slice(-40));
    setHistoryIdx(-1);
    try {
      const result = await sendCommand(attemptId, toSend);
      absorb(result.state);
    } catch (err) {
      setFinishError(errorDetail(err, "Command failed to send."));
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

  const handleTakeRole = async (role: CrewRole | null) => {
    setCrewError("");
    try {
      absorb(await setCrewRole(attemptId, role));
    } catch (err) {
      setCrewError(errorDetail(err, "Couldn't update your seat right now."));
    }
  };

  // Up/down through your own command history — a terminal that doesn't do
  // this is a terminal people stop using.
  const handleKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
    if (cmdHistory.length === 0) return;
    e.preventDefault();
    const next = e.key === "ArrowUp"
      ? Math.min(cmdHistory.length - 1, historyIdx + 1)
      : Math.max(-1, historyIdx - 1);
    setHistoryIdx(next);
    setCommand(next === -1 ? "" : cmdHistory[cmdHistory.length - 1 - next]);
  };

  const bands = useMemo(() => {
    if (!state) return { passes: [], eclipses: [], saa: [] };
    const o = state.orbit;
    const period = o.period_minutes * 60;
    return {
      passes: Array.from({ length: o.orbits }, (_, i) => ({
        orbit: i + 1, start_t: i * period + 0.42 * period, end_t: i * period + 0.504 * period,
      })),
      eclipses: Array.from({ length: o.orbits }, (_, i) => ({
        orbit: i + 1, start_t: i * period + (1 - o.eclipse_fraction) * period, end_t: (i + 1) * period,
      })),
      saa: Array.from({ length: o.orbits }, (_, i) => ({
        orbit: i + 1, start_t: i * period + 0.2 * period, end_t: i * period + 0.263 * period,
      })),
    };
  }, [state]);

  if (error) {
    return <div className="mx-auto max-w-[1100px] px-5 py-10"><p className="text-sm text-destructive">{error}</p></div>;
  }
  if (!state) {
    return <div className="mx-auto max-w-[1100px] px-5 py-10"><p className="text-sm text-muted-foreground">Establishing uplink...</p></div>;
  }

  const decided = state.attempt_status === "passed" || state.attempt_status === "failed";
  if (decided) return <OperateDebrief attemptId={attemptId} missionId={state.mission_id} />;

  const t = state.telemetry;
  const phase = state.phase;
  const activeAnomalies = state.anomalies.filter((a) => a.cleared_t === null);

  return (
    <div className="mx-auto max-w-[1100px] px-4 sm:px-8 py-6 sm:py-8 flex flex-col gap-5">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Link to="/learn/missions" className="text-primary hover:opacity-80">Missions</Link>
        <ChevronRight className="size-3" />
        <span className="text-foreground">Flight Operations</span>
      </div>

      {/* --- flight status strip ------------------------------------------ */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-2">
          <div className="w-fit flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded-md bg-primary/10 text-primary">
            <Radio className="size-3" /> {state.variant_label} · {state.orbit.time_compression}× time
          </div>
          <h1 className="font-display text-xl sm:text-2xl font-extrabold tracking-tight">Ground Station Console</h1>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="font-mono text-lg font-semibold tabular-nums">{flightClock(state.sim_t)}</p>
            <p className="text-[10px] text-muted-foreground">
              orbit {phase.orbit_number} of {state.orbit.orbits}
            </p>
          </div>
          <Button onClick={() => void handleFinish()} disabled={finishing} variant={state.expired ? "default" : "outline"}>
            {finishing ? "Ending..." : state.expired ? "See debrief" : "End flight"}
          </Button>
        </div>
      </div>
      {finishError && <p className="text-xs text-destructive">{finishError}</p>}
      {state.expired && (
        <div className="rounded-xl ring-1 ring-primary/40 bg-primary/5 px-4 py-3 text-xs">
          The flight window has closed. End the flight to see your debrief.
        </div>
      )}

      {/* --- where am I --------------------------------------------------- */}
      <Card className="p-4 flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs">
          <span className="flex items-center gap-1.5 font-semibold">
            {phase.sunlit ? <Sun className="size-3.5 text-amber-500" /> : <SunDim className="size-3.5 text-slate-400" />}
            {phase.label}
          </span>
          {phase.in_pass ? (
            <span className="text-emerald-500 font-mono">
              LOS in {countdown(phase.seconds_to_los)} · elevation {phase.elevation_deg.toFixed(0)}°
            </span>
          ) : (
            <span className="text-muted-foreground font-mono">
              next pass in {countdown(phase.seconds_to_next_aos)}
            </span>
          )}
          <span className={`font-mono ${phase.sunlit && phase.seconds_to_eclipse < 300 ? "text-amber-500" : "text-muted-foreground"}`}>
            {phase.sunlit
              ? `eclipse in ${countdown(phase.seconds_to_eclipse)}`
              : `sunrise in ${countdown(phase.seconds_to_sunrise)}`}
          </span>
          {phase.in_saa && <span className="text-primary font-mono">in SAA — upset risk</span>}
        </div>
        <OrbitTimeline
          sessionSeconds={state.session_seconds}
          periodSeconds={state.orbit.period_minutes * 60}
          orbits={state.orbit.orbits}
          passes={bands.passes} eclipses={bands.eclipses} saa={bands.saa}
          currentT={state.sim_t}
        />
      </Card>

      {/* --- flying your own design (Stage 7C-9) --------------------------- */}
      {state.spacecraft_source.length > 0 && (
        <Card className="p-4 flex flex-col gap-1.5 ring-primary/30 bg-primary/5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-primary flex items-center gap-1.5">
            <Rocket className="size-3.5" /> You are flying the satellite you designed
          </p>
          <ul className="flex flex-col gap-0.5">
            {state.spacecraft_source.map((line) => (
              <li key={line} className="text-[11px] text-muted-foreground leading-relaxed">· {line}</li>
            ))}
          </ul>
        </Card>
      )}

      {/* --- active faults ------------------------------------------------ */}
      {activeAnomalies.length > 0 && (
        <div className="flex flex-col gap-2">
          {activeAnomalies.map((a) => (
            <div
              key={`${a.key}-${a.raised_t}`}
              className="flex items-start gap-2.5 rounded-xl ring-1 ring-destructive/40 bg-destructive/5 px-4 py-2.5"
            >
              <AlertTriangle className="size-4 text-destructive shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold">
                  {a.subsystem} · {a.title}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  raised at {flightClock(a.raised_t)} ·{" "}
                  {a.origin === "injected" ? "external event" : "caused by current configuration"} · check the Ops Handbook
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* --- objectives --------------------------------------------------- */}
      <Card className="p-4 flex flex-col gap-2.5">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
            <Target className="size-3.5" /> Mission objectives
          </p>
          <p className="text-xs font-mono">
            running score <span className="font-semibold">{state.score.toFixed(0)}%</span>
            <span className="text-muted-foreground"> / need {state.pass_threshold}%</span>
          </p>
        </div>
        {/* Say out loud what the bars only imply. A student who takes no
            action for ten minutes should not have to infer from five
            part-filled bars that they are on course to fail — the console
            has every number needed to tell them, and telling them is the
            difference between a simulator and a teaching tool. */}
        <MissionStanding state={state} />

        <div className="grid sm:grid-cols-2 gap-x-6 gap-y-2">
          {state.objectives.map((obj) => (
            <div key={obj.key} className="flex flex-col gap-1">
              <div className="flex items-baseline justify-between gap-2 text-[11px]">
                <span className={obj.met ? "text-emerald-500 font-medium" : ""}>{obj.label}</span>
                <span className="font-mono text-muted-foreground">{obj.detail}</span>
              </div>
              <div className="h-1 rounded-full bg-muted overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-700 ${obj.met ? "bg-emerald-500" : "bg-primary"}`}
                  style={{ width: `${Math.round(obj.fraction * 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* --- crew (team attempts) ----------------------------------------- */}
      {state.is_team && (
        <Card className="p-4 flex flex-col gap-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
            <Users className="size-3.5" /> Crew
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            {CREW_ROLES.map((role) => {
              const holder = state.roster.find((m) => m.role === role);
              const isMine = holder?.user_id === currentUser?.id;
              return (
                <div
                  key={role}
                  className={`flex flex-col gap-1 px-3 py-2 rounded-xl ring-1 ${isMine ? "ring-primary/40 bg-primary/10" : "ring-border"}`}
                >
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {CREW_ROLE_LABELS[role]}
                  </span>
                  <span className="text-xs truncate">{holder ? holder.name : "Open seat"}</span>
                  {(holder ? isMine : true) && (
                    <button
                      onClick={() => void handleTakeRole(isMine ? null : role)}
                      className="text-[10px] text-primary hover:opacity-80 text-left"
                    >
                      {isMine ? "Leave seat" : "Take seat"}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
          {crewError && <p className="text-xs text-destructive">{crewError}</p>}
        </Card>
      )}

      {/* --- attitude + subsystems ---------------------------------------- */}
      {/* The viewport spans the full width and the five subsystem cards sit
          in one even row beneath it. The previous two-column split put two
          cards under the viewport and three beside it, which left the cards
          different widths and a block of dead space at the bottom of the
          right column — and it squeezed the viewport into half the page,
          which the orbital travel needs. */}
      <div className="flex flex-col gap-3">
        <AttitudeView
          pitch={Number(t.pitch ?? 0)}
          roll={Number(t.roll ?? 0)}
          yaw={Number(t.yaw ?? 0)}
          attitudeError={Number(t.attitude_error_deg ?? 0)}
          pointingLimit={POINTING_LIMIT}
          sunlit={phase.sunlit}
          inPass={phase.in_pass}
          safeMode={t.mode === "SAFE"}
          orbitFraction={Number(phase.orbit_fraction ?? 0)}
          orbitNumber={Number(phase.orbit_number ?? 1)}
        />
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
          {state.subsystems.map((card) => <SubsystemPanel key={card.subsystem} card={card} />)}
        </div>
      </div>

      {/* --- trends ------------------------------------------------------- */}
      <div className="flex flex-col gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
          <Satellite className="size-3.5" /> Trends
          <span className="font-normal normal-case tracking-normal">
            — a value is a snapshot; the slope is the diagnosis
          </span>
        </p>
        <TelemetryTrends data={trend} passes={bands.passes} eclipses={bands.eclipses} />
      </div>

      {/* --- the two logs -------------------------------------------------- */}
      <div className="grid lg:grid-cols-2 gap-4">
        {/* Spacecraft event feed — what the vehicle is telling you. */}
        <div className="rounded-xl overflow-hidden ring-1 ring-border flex flex-col">
          <div className="px-4 py-2 bg-muted/50 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Spacecraft event log
          </div>
          <div className="bg-[#0a0d14] p-4 flex flex-col gap-1 h-[280px] overflow-y-auto font-mono text-[11px]">
            {state.spacecraft_log.map((entry, i) => (
              <div key={`${entry.t}-${i}`} className="flex gap-2 leading-relaxed">
                <span className="text-[#4a5568] shrink-0">{flightClock(entry.t).slice(2)}</span>
                <span className={`shrink-0 font-semibold ${LOG_TONE[entry.level]}`}>[{entry.level[0]}]</span>
                <span className={LOG_TONE[entry.level]}>{entry.message}</span>
              </div>
            ))}
            <div ref={logEndRef} />
          </div>
        </div>

        {/* Terminal — what you did about it. */}
        <div className="rounded-xl overflow-hidden ring-1 ring-border flex flex-col">
          <div className="px-4 py-2 bg-muted/50 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Uplink terminal
          </div>
          <div className="bg-[#0a0d14] p-4 flex flex-col gap-1.5 h-[280px] overflow-y-auto font-mono text-[11px]">
            <div className="text-[#64ffda]/85">SYSTEM: UPLINK ESTABLISHED // TYPE "HELP" FOR COMMANDS, "STATUS" FOR A SUMMARY.</div>
            {state.events.map((e) => (
              <div key={e.seq} className="flex flex-col gap-0.5">
                <div className="text-[#8892b0]">
                  operator@groundstation:~$ {e.command}{e.arg ? ` ${e.arg}` : ""}
                </div>
                <div className={e.success ? "text-emerald-400" : "text-red-400"}>{e.message}</div>
              </div>
            ))}
            <div ref={terminalEndRef} />
          </div>
          <form
            onSubmit={(ev) => { ev.preventDefault(); void handleSend(); }}
            className="flex items-center gap-2 px-4 py-3 bg-[#07090e] border-t border-border/40"
          >
            <span className="text-[#64ffda] font-mono font-bold">$</span>
            <input
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              onKeyDown={handleKey}
              disabled={sending || state.expired}
              placeholder={state.expired ? "Flight window closed" : "Type HELP or a telecommand..."}
              className="flex-1 bg-transparent border-none text-white font-mono text-xs outline-none placeholder:text-[#4a5568] disabled:opacity-50"
              autoFocus
            />
            <button
              type="submit"
              disabled={sending || state.expired || !command.trim()}
              className="text-[#64ffda] font-mono text-[10px] font-semibold uppercase tracking-wide disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Send
            </button>
          </form>
        </div>
      </div>

      <OpsHandbook handbook={handbook} />
    </div>
  );
}
