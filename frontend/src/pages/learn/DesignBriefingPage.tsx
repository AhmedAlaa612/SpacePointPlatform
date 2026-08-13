/** Pre-design briefing (Design v2, 7D-4).
 *
 * A student used to land on a tab bar with no context: no statement of what
 * a CubeSat is, what a "budget" means, why the steps are in that order, or
 * what "done" looks like. This is the same surface the operate mission's
 * pre-flight briefing provides, and it exists for the same reason — the
 * mission has to say what it is before it asks you to do it.
 *
 * **No attempt row is created until "Begin design".** Reading the briefing,
 * or re-reading it, never burns a retry.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { isAxiosError } from "axios";
import { Boxes, ChevronRight, Gauge, Rocket, Target } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { startMissionAttempt } from "@/api/missions";
import { fetchDesignBriefing, type DesignBriefing } from "@/api/missionsDesign";

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail;
  return fallback;
}

export default function DesignBriefingPage() {
  const { missionId } = useParams({ strict: false }) as { missionId: string };
  const search = useSearch({ strict: false }) as { variant?: string; team?: string };
  const navigate = useNavigate();

  const [briefing, setBriefing] = useState<DesignBriefing | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");

  const load = useCallback(() => {
    fetchDesignBriefing(missionId, search.variant)
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
      navigate({ to: "/learn/missions/design/$attemptId", params: { attemptId: attempt.id } });
    } catch (err) {
      setStartError(errorDetail(err, "Couldn't start this design right now."));
      setStarting(false);
    }
  };

  if (error) {
    return <div className="mx-auto max-w-[1000px] px-5 py-10"><p className="text-sm text-destructive">{error}</p></div>;
  }
  if (!briefing) {
    return <div className="mx-auto max-w-[1000px] px-5 py-10"><p className="text-sm text-muted-foreground">Loading briefing...</p></div>;
  }

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
          <Rocket className="size-3" /> Design briefing · {briefing.variant_label} · {briefing.points} pts
        </div>
        <h1 className="font-display text-2xl sm:text-3xl font-extrabold tracking-tight">{briefing.mission_title}</h1>
        {briefing.mission_summary && (
          <p className="text-sm text-muted-foreground max-w-[70ch] leading-relaxed">{briefing.mission_summary}</p>
        )}
      </div>

      {/* --- the one paragraph that matters most ------------------------- */}
      <Card className="p-5 flex flex-col gap-2 ring-primary/25 bg-primary/5">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">What you're actually doing</p>
        <p className="text-sm leading-relaxed whitespace-pre-line">
          {briefing.what_is_a_budget.replace(/\*\*/g, "")}
        </p>
      </Card>

      {/* --- the steps, in order, with the dependency ------------------- */}
      <div className="flex flex-col gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
            <Boxes className="size-3.5" /> The steps
          </p>
          <p className="text-[11px] text-muted-foreground mt-1 max-w-[75ch] leading-relaxed">
            You can work in any order — but they are computed from each other, so the sequence is
            not arbitrary. Pay attention to CONOPS in particular: four separate budgets read it.
          </p>
        </div>
        <Card className="p-5 flex flex-col gap-3">
          {briefing.step_order.map((s, i) => (
            <div key={s.key} className="flex gap-3">
              <span className="shrink-0 size-6 rounded-full bg-muted text-[11px] font-mono flex items-center justify-center mt-0.5">
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">{s.label}</p>
                <p className="text-xs text-muted-foreground leading-relaxed mt-0.5 whitespace-pre-line">
                  {s.detail.replace(/\*\*/g, "")}
                </p>
                {s.depends_on.length > 0 && (
                  <p className="text-[10px] font-mono text-primary mt-1">
                    reads: {s.depends_on.map((d) => d.replace(/_/g, " ")).join(", ")}
                  </p>
                )}
              </div>
            </div>
          ))}
        </Card>
      </div>

      {/* --- what each budget checks ------------------------------------ */}
      <div className="flex flex-col gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
          <Target className="size-3.5" /> What gets checked
        </p>
        <div className="grid sm:grid-cols-2 gap-3">
          {briefing.budgets.map((b) => (
            <div key={b.key} className="rounded-xl ring-1 ring-border px-4 py-3 flex flex-col gap-1">
              <p className="text-sm font-semibold">{b.title}</p>
              <p className="text-xs">{b.checks}</p>
              <p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">{b.why_it_matters}</p>
            </div>
          ))}
        </div>
      </div>

      {/* --- your limits ------------------------------------------------ */}
      <div className="flex flex-col gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
            <Gauge className="size-3.5" /> Your limits on {briefing.variant_label}
          </p>
          <p className="text-[11px] text-muted-foreground mt-1">
            You are told these up front on purpose. Discovering a threshold on the report screen is
            not a design exercise.
          </p>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {briefing.limits.map((l) => (
            <div key={l.key} className="flex flex-col gap-1 px-4 py-3 rounded-xl ring-1 ring-border">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{l.label}</span>
              <span className="font-mono text-base font-semibold">{l.value}</span>
              <span className="text-[10px] text-muted-foreground leading-snug">{l.detail}</span>
            </div>
          ))}
        </div>
        <Card className="p-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            CubeSat sizes — the mass and volume limit you pick in Setup
          </p>
          <div className="grid grid-cols-4 gap-2">
            {briefing.cubesat_sizes.map((c) => (
              <div key={c.size} className="text-center px-2 py-2 rounded-lg ring-1 ring-border">
                <p className="font-mono text-sm font-semibold">{c.size}</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">{c.max_mass_kg} kg</p>
                <p className="text-[10px] text-muted-foreground">{c.available_volume_cm3.toLocaleString()} cm³</p>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* --- assumptions ------------------------------------------------ */}
      <Card className="p-5 flex flex-col gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          What this model simplifies
        </p>
        <ul className="flex flex-col gap-1.5">
          {briefing.assumptions.map((a) => (
            <li key={a} className="text-[11px] leading-relaxed flex gap-2 text-muted-foreground">
              <span className="shrink-0">·</span><span>{a}</span>
            </li>
          ))}
        </ul>
      </Card>

      {/* --- go --------------------------------------------------------- */}
      <div className="sticky bottom-4 flex flex-col gap-2">
        <Card className="p-4 flex flex-wrap items-center justify-between gap-3 shadow-lg">
          <div className="text-xs text-muted-foreground">
            There is no clock on this one — take as long as you need, and the Design Handbook stays
            open while you work.
          </div>
          <Button onClick={() => void handleBegin()} disabled={starting} size="lg">
            {starting ? "Starting..." : "Begin design"}
          </Button>
        </Card>
        {startError && <p className="text-xs text-destructive">{startError}</p>}
      </div>
    </div>
  );
}
