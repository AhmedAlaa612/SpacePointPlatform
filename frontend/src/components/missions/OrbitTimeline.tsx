/** The orbit timeline (Operate v2, Stage 7C-5).
 *
 * SatKit's "Team Progress" page had a six-step mission timeline — pre-launch,
 * launch, orbit insertion, data collection, deorbit, recovery — and every
 * one of those steps was a hardcoded string literal, including
 * "In progress · 34% complete". A page that looked like it tracked progress
 * tracked nothing.
 *
 * This is that idea made real. Every band is computed from the orbit model:
 * where the sunlight is, when the ground station comes into view, when the
 * spacecraft crosses the radiation belt. It is the flight plan, and the
 * marker is where you actually are in it.
 *
 * Doubles as the debrief's x-axis reference, which is why it takes explicit
 * windows rather than reading live state — the same component draws a live
 * flight and a finished one.
 */
interface Window {
  orbit: number;
  start_t: number;
  end_t: number;
}

interface Props {
  sessionSeconds: number;
  periodSeconds: number;
  orbits: number;
  passes: Window[];
  eclipses: Window[];
  saa?: Window[];
  /** Where the marker sits. Omit for a plain plan with no "you are here". */
  currentT?: number;
  /** Faults, shaded above the band — used by the debrief. */
  anomalies?: { start_t: number; end_t: number; outcome: string; title: string }[];
  compact?: boolean;
}

const pct = (v: number, total: number) => `${Math.max(0, Math.min(100, (v / total) * 100))}%`;

export default function OrbitTimeline({
  sessionSeconds, periodSeconds, orbits, passes, eclipses, saa = [],
  currentT, anomalies = [], compact = false,
}: Props) {
  const height = compact ? "h-8" : "h-11";

  return (
    <div className="flex flex-col gap-1.5">
      {anomalies.length > 0 && (
        <div className="relative h-3">
          {anomalies.map((a, i) => (
            <div
              key={`${a.title}-${i}`}
              title={`${a.title} — ${a.outcome}`}
              className={`absolute top-0 h-3 rounded-sm ${
                a.outcome === "resolved"
                  ? "bg-emerald-500/60"
                  : a.outcome === "late"
                    ? "bg-amber-500/60"
                    : "bg-destructive/70"
              }`}
              style={{
                left: pct(a.start_t, sessionSeconds),
                width: pct(Math.max(a.end_t - a.start_t, sessionSeconds * 0.004), sessionSeconds),
              }}
            />
          ))}
        </div>
      )}

      <div className={`relative ${height} rounded-lg overflow-hidden ring-1 ring-border bg-amber-200/25 dark:bg-amber-300/15`}>
        {/* Sunlit is the background; eclipse is drawn over it. */}
        {eclipses.map((e) => (
          <div
            key={`ecl-${e.orbit}`}
            className="absolute inset-y-0 bg-slate-900/70 dark:bg-slate-950/80"
            style={{ left: pct(e.start_t, sessionSeconds), width: pct(e.end_t - e.start_t, sessionSeconds) }}
            title={`Eclipse — orbit ${e.orbit}`}
          />
        ))}

        {saa.map((s) => (
          <div
            key={`saa-${s.orbit}`}
            className="absolute inset-y-0 opacity-70"
            style={{
              left: pct(s.start_t, sessionSeconds),
              width: pct(s.end_t - s.start_t, sessionSeconds),
              background: "repeating-linear-gradient(45deg, rgba(167,125,255,0.5) 0 4px, transparent 4px 8px)",
            }}
            title={`South Atlantic Anomaly — orbit ${s.orbit}`}
          />
        ))}

        {passes.map((p) => (
          <div
            key={`pass-${p.orbit}`}
            className="absolute inset-y-0 bg-emerald-500/70 border-x border-emerald-300/60"
            style={{ left: pct(p.start_t, sessionSeconds), width: pct(p.end_t - p.start_t, sessionSeconds) }}
            title={`Ground station pass — orbit ${p.orbit}`}
          />
        ))}

        {/* Orbit boundaries */}
        {Array.from({ length: Math.max(0, orbits - 1) }, (_, i) => (
          <div
            key={`b-${i}`}
            className="absolute inset-y-0 w-px bg-border"
            style={{ left: pct((i + 1) * periodSeconds, sessionSeconds) }}
          />
        ))}

        {currentT !== undefined && (
          <div
            className="absolute inset-y-0 w-0.5 bg-primary shadow-[0_0_8px_var(--color-primary,#A77DFF)] transition-[left] duration-1000 ease-linear"
            style={{ left: pct(currentT, sessionSeconds) }}
          />
        )}
      </div>

      {!compact && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-2.5 rounded-sm bg-amber-200/70 dark:bg-amber-300/40" /> Sunlit
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-2.5 rounded-sm bg-slate-900/70" /> Eclipse — no generation
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-2.5 rounded-sm bg-emerald-500/70" /> Pass — the only time you can downlink
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block w-3 h-2.5 rounded-sm"
              style={{ background: "repeating-linear-gradient(45deg, rgba(167,125,255,0.6) 0 3px, transparent 3px 6px)" }}
            />
            SAA — upset risk
          </span>
        </div>
      )}
    </div>
  );
}
