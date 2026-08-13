/** Pre-flight briefing (Operate v2, Stage 7C-7).
 *
 * "Some instructions, some notes on common problems that might happen and
 * the right response to it, then you start the mission" — this is the
 * first two of those three, and it is the surface v1 had nothing of at
 * all: a student went straight from a variant picker into a live console
 * with no idea what the spacecraft was, what the objective was, or what
 * any readout meant.
 *
 * **No attempt row exists until "Begin flight".** Reading the briefing —
 * or re-reading it five times — never burns a retry, which is the whole
 * reason it lives on its own route rather than inside the console.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { isAxiosError } from "axios";
import {
  BatteryCharging, ChevronRight, Database, Gauge, Radio, Rocket, Satellite, Target, Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { HandbookBody } from "@/components/missions/OpsHandbook";
import OrbitTimeline from "@/components/missions/OrbitTimeline";
import { startMissionAttempt } from "@/api/missions";
import { fetchBriefing, type Briefing } from "@/api/missionsOperate";

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail;
  return fallback;
}

function Stat({ icon: Icon, label, value, sub }: {
  icon: typeof Gauge; label: string; value: string; sub?: string;
}) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3 rounded-xl ring-1 ring-border">
      <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        <Icon className="size-3" /> {label}
      </span>
      <span className="font-mono text-base font-semibold">{value}</span>
      {sub && <span className="text-[10px] text-muted-foreground">{sub}</span>}
    </div>
  );
}

export default function OperateBriefingPage() {
  const { missionId } = useParams({ strict: false }) as { missionId: string };
  const search = useSearch({ strict: false }) as { variant?: string; team?: string };
  const navigate = useNavigate();

  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");

  const load = useCallback(() => {
    fetchBriefing(missionId, search.variant)
      .then(setBriefing)
      .catch(() => setError("Couldn't load this mission briefing."));
  }, [missionId, search.variant]);

  useEffect(() => { load(); }, [load]);

  const handleBegin = async () => {
    if (!briefing) return;
    setStarting(true);
    setStartError("");
    try {
      const attempt = await startMissionAttempt(briefing.mission_id, briefing.variant_id, search.team);
      navigate({ to: "/learn/missions/operate/$attemptId", params: { attemptId: attempt.id } });
    } catch (err) {
      setStartError(errorDetail(err, "Couldn't start this flight right now."));
      setStarting(false);
    }
  };

  if (error) {
    return <div className="mx-auto max-w-[1000px] px-5 py-10"><p className="text-sm text-destructive">{error}</p></div>;
  }
  if (!briefing) {
    return <div className="mx-auto max-w-[1000px] px-5 py-10"><p className="text-sm text-muted-foreground">Loading briefing...</p></div>;
  }

  const o = briefing.orbit;
  const sc = briefing.spacecraft;
  // Bands for the flight-plan strip. Derived here from the same fractions
  // the backend uses, so the student sees the actual plan they'll fly.
  const period = (o.period_minutes * 60);
  const session = period * o.orbits;
  const passes = Array.from({ length: o.orbits }, (_, i) => ({
    orbit: i + 1, start_t: i * period + 0.42 * period, end_t: i * period + (0.42 + 0.084) * period,
  }));
  const eclipses = Array.from({ length: o.orbits }, (_, i) => ({
    orbit: i + 1, start_t: i * period + (1 - o.eclipse_fraction) * period, end_t: (i + 1) * period,
  }));
  const saa = Array.from({ length: o.orbits }, (_, i) => ({
    orbit: i + 1, start_t: i * period + 0.2 * period, end_t: i * period + 0.263 * period,
  }));

  return (
    <div className="mx-auto max-w-[1000px] px-5 sm:px-8 py-6 sm:py-8 flex flex-col gap-6">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Link to="/learn/missions" className="text-primary hover:opacity-80">Missions</Link>
        <ChevronRight className="size-3" />
        <Link to="/learn/missions/$missionId" params={{ missionId }} className="text-primary hover:opacity-80">
          {briefing.mission_title}
        </Link>
        <ChevronRight className="size-3" />
        <span className="text-foreground">Briefing</span>
      </div>

      <div className="flex flex-col gap-2">
        <div className="w-fit flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded-md bg-primary/10 text-primary">
          <Radio className="size-3" /> Pre-flight briefing · {briefing.variant_label} · {briefing.points} pts
        </div>
        <h1 className="font-display text-2xl sm:text-3xl font-extrabold tracking-tight">
          {briefing.mission_title}
        </h1>
        {briefing.mission_summary && (
          <p className="text-sm text-muted-foreground max-w-[70ch] leading-relaxed">{briefing.mission_summary}</p>
        )}
      </div>

      {/* --- the objective ------------------------------------------------ */}
      <Card className="p-5 flex flex-col gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
          <Target className="size-3.5" /> Your objective
        </p>
        <div className="grid sm:grid-cols-2 gap-3">
          {briefing.objectives.map((obj) => (
            <div key={obj.key} className="flex flex-col gap-0.5">
              <span className="text-sm font-semibold">{obj.label}</span>
              <span className="text-xs text-muted-foreground leading-relaxed">{obj.detail}</span>
            </div>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground border-t border-border/60 pt-3">
          Score is 60% objectives and 40% how you handled the faults, minus any penalties.
          You need <span className="font-semibold text-foreground">{briefing.pass_threshold}%</span> to pass.
        </p>
      </Card>

      {/* --- the orbit ---------------------------------------------------- */}
      <div className="flex flex-col gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
          <Satellite className="size-3.5" /> Your orbit
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat icon={Satellite} label="Altitude" value={`${o.altitude_km} km`} sub={`${o.inclination_deg}° sun-synchronous`} />
          <Stat icon={Gauge} label="Velocity" value={`${o.velocity_km_s} km/s`} sub={`one lap every ${o.period_minutes} min`} />
          <Stat icon={BatteryCharging} label="Eclipse" value={`${o.eclipse_minutes} min`} sub="per orbit with no generation" />
          <Stat icon={Radio} label="Pass window" value={`${o.pass_minutes} min`} sub={o.ground_station} />
        </div>
        <Card className="p-4 flex flex-col gap-3">
          <OrbitTimeline
            sessionSeconds={session} periodSeconds={period} orbits={o.orbits}
            passes={passes} eclipses={eclipses} saa={saa}
          />
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            You will fly <span className="font-semibold text-foreground">{o.orbits} orbits</span>, which takes about{" "}
            <span className="font-semibold text-foreground">{o.real_minutes} real minutes</span> at {o.time_compression}×
            time compression. The green bands are the only moments you can send data to the ground — about{" "}
            {o.pass_minutes} minutes each. Plan around them.
          </p>
        </Card>
      </div>

      {/* --- the spacecraft ----------------------------------------------- */}
      <div className="flex flex-col gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
          <Rocket className="size-3.5" /> Your spacecraft
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat icon={BatteryCharging} label="Battery" value={`${sc.battery_capacity_wh} Wh`} sub={`starting at ${sc.initial_soc_pct}%`} />
          <Stat icon={BatteryCharging} label="Solar array" value={`${sc.solar_array_w} W`} sub="sunlit, at nominal pointing" />
          <Stat icon={Database} label="Mass memory" value={`${sc.storage_capacity_mb} MB`} sub={`${sc.science_take_mb} MB per science take`} />
          <Stat icon={Radio} label="Downlink" value={`${sc.downlink_mbps} Mbps`} sub="transmitter only, during a pass" />
        </div>
        <Card className="p-4">
          <p className="text-xs leading-relaxed">
            <span className="font-semibold">The power budget is tight on purpose.</span> The bus draws{" "}
            <span className="font-mono">{sc.bus_idle_w} W</span> no matter what, the instrument adds{" "}
            <span className="font-mono">{sc.payload_active_w} W</span> while it's powered, and the transmitter adds{" "}
            <span className="font-mono">{sc.transmitter_w} W</span> while you're downlinking. In sunlight the array
            gives you <span className="font-mono">{sc.solar_array_w} W</span>. In eclipse it gives you nothing.
            Work out what that means before you fly it.
          </p>
        </Card>
      </div>

      {/* --- crew --------------------------------------------------------- */}
      {search.team && (
        <Card className="p-5 flex flex-col gap-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
            <Users className="size-3.5" /> Your crew
          </p>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Each officer owns one subsystem's commands. Seats are optional — an empty seat means anyone can act —
            so a crew of two works as well as a crew of five.
          </p>
          <div className="grid sm:grid-cols-5 gap-2">
            {briefing.crew_roles.map((r) => (
              <div key={r.role} className="flex flex-col gap-1 px-3 py-2 rounded-xl ring-1 ring-border">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{r.subsystem}</span>
                <span className="text-xs font-semibold">{r.label}</span>
                <span className="text-[10px] font-mono text-muted-foreground leading-snug">
                  {r.commands.slice(0, 3).join(", ")}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* --- the handbook ------------------------------------------------- */}
      <div className="flex flex-col gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            What can go wrong, and what to do about it
          </p>
          <p className="text-[11px] text-muted-foreground mt-1 max-w-[75ch] leading-relaxed">
            Read this now, and keep it open during the flight — the Ops Handbook button stays in the corner of the
            console. Some faults happen to you and some happen because of how you're flying; the handbook says which
            is which.
          </p>
        </div>
        <Card className="p-5">
          <HandbookBody
            handbook={{
              disclosure: (briefing.handbook[0]?.action ? "full" : briefing.handbook[0]?.meaning ? "symptoms" : "reference"),
              entries: briefing.handbook,
              commands: briefing.commands,
              flight_rules: briefing.flight_rules,
              crew_roles: briefing.crew_roles,
              assumptions: briefing.assumptions,
            }}
          />
        </Card>
      </div>

      {/* --- go ----------------------------------------------------------- */}
      <div className="sticky bottom-4 flex flex-col gap-2">
        <Card className="p-4 flex flex-wrap items-center justify-between gap-3 shadow-lg">
          <div className="text-xs text-muted-foreground">
            The clock starts the moment you begin, and it does not pause.
            <span className="block sm:inline sm:ml-1">You can retry as many times as you like.</span>
          </div>
          <Button onClick={() => void handleBegin()} disabled={starting} size="lg">
            {starting ? "Establishing uplink..." : "Begin flight"}
          </Button>
        </Card>
        {startError && <p className="text-xs text-destructive">{startError}</p>}
      </div>
    </div>
  );
}
