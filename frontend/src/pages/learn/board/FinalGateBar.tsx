import { useCallback, useEffect, useRef, useState } from "react";
import { isAxiosError } from "axios";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Flag, Lock } from "lucide-react";
import { finalSubmitChecklist } from "@/api/lms";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import type { CheckpointGroup } from "./roadmap";

/** Same 2-line pattern every other student page in this app duplicates
 * locally (see TaskDrawer.tsx's own copy) — axios's `err.message` is a
 * generic "Request failed with status code 400", never the backend's
 * actual reason. */
function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail;
  return fallback;
}

function formatTimestamp(isoString: string): string {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "CONFIRMED";
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return "CONFIRMED";
  }
}

interface SmokePuff {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  growth: number;
  alpha: number;
  decay: number;
  r: number;
  g: number;
  b: number;
}

function SpaceFireworksOverlay({
  active,
  origin,
  onComplete,
}: {
  active: boolean;
  origin: { x: number; y: number } | null;
  onComplete: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (!active) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };
    window.addEventListener("resize", handleResize);

    const cx = origin?.x ?? width / 2;
    const cy = origin?.y ?? height / 2;

    const smokePuffs: SmokePuff[] = [];

    // SpaceX Night Launch Atmospheric Palette: obsidian black, midnight charcoal, and dark royal purple
    const smokeColors = [
      { r: 14, g: 11, b: 24 },   // Deep space obsidian
      { r: 22, g: 15, b: 36 },   // Midnight charcoal smoke
      { r: 42, g: 20, b: 72 },   // Dark nebula purple
      { r: 68, g: 32, b: 112 },  // Deep royal violet
      { r: 96, g: 50, b: 156 },  // Heliotrope plume ambient
    ];

    function spawnSmoke(
      x: number,
      y: number,
      vx: number,
      vy: number,
      initRadius: number,
      growth: number,
      maxAlpha = 0.55,
      decay = 0.005 + Math.random() * 0.005
    ) {
      const c = smokeColors[Math.floor(Math.random() * smokeColors.length)];
      smokePuffs.push({
        x,
        y,
        vx,
        vy,
        radius: initRadius,
        growth,
        alpha: maxAlpha,
        decay,
        r: c.r,
        g: c.g,
        b: c.b,
      });
    }

    // Spaceship Launch State
    const rocket = {
      x: cx,
      y: cy - 10,
      baseX: cx,
      vy: 0,
      ignitionFrames: 18,
      frame: 0,
      active: true,
      scale: 1.15,
    };

    function drawSpaceship(
      context: CanvasRenderingContext2D,
      x: number,
      y: number,
      scale: number,
      enginePower: number
    ) {
      context.save();
      context.translate(x, y);
      context.scale(scale, scale);

      // 1. Dynamic Plasma Thruster Flame (intense supersonic violet shock diamond)
      if (enginePower > 0) {
        context.save();
        context.globalCompositeOperation = "lighter";
        const flameLen = 16 + Math.random() * 12 * enginePower;

        // Violet outer plasma aura
        context.beginPath();
        context.moveTo(-5.5, 12);
        context.quadraticCurveTo(0, 12 + flameLen * 0.9, 0, 12 + flameLen);
        context.quadraticCurveTo(0, 12 + flameLen * 0.9, 5.5, 12);
        context.closePath();
        context.fillStyle = "rgba(168, 128, 255, 0.85)";
        context.fill();

        // White-hot core plume
        const coreLen = 8 + Math.random() * 6 * enginePower;
        context.beginPath();
        context.moveTo(-2.5, 12);
        context.quadraticCurveTo(0, 12 + coreLen * 0.85, 0, 12 + coreLen);
        context.quadraticCurveTo(0, 12 + coreLen * 0.85, 2.5, 12);
        context.closePath();
        context.fillStyle = "#ffffff";
        context.fill();
        context.restore();
      }

      // 2. Spaceship Fuselage (solid crisp rendering)
      context.beginPath();
      context.moveTo(0, -20);
      context.bezierCurveTo(5.5, -8, 6.5, 4, 5.5, 12);
      context.lineTo(-5.5, 12);
      context.bezierCurveTo(-6.5, 4, -5.5, -8, 0, -20);
      context.closePath();
      context.fillStyle = "#ffffff";
      context.fill();

      // 3. Delta Wings (brand purple)
      context.beginPath();
      context.moveTo(-5.5, 2);
      context.lineTo(-14, 13);
      context.lineTo(-5.5, 11);
      context.closePath();
      context.fillStyle = "#a880ff";
      context.fill();

      context.beginPath();
      context.moveTo(5.5, 2);
      context.lineTo(14, 13);
      context.lineTo(5.5, 11);
      context.closePath();
      context.fillStyle = "#a880ff";
      context.fill();

      // 4. Cockpit Canopy Glass (heliotrope tint)
      context.beginPath();
      context.ellipse(0, -5, 2.2, 4.5, 0, 0, Math.PI * 2);
      context.fillStyle = "#a880ff";
      context.fill();

      // 5. Thruster Nozzle
      context.beginPath();
      context.rect(-3.5, 11, 7, 2);
      context.fillStyle = "#6b5b95";
      context.fill();

      context.restore();
    }

    let animId: number;
    function render() {
      if (!ctx) return;
      ctx.clearRect(0, 0, width, height);

      // --- 1. BILLOWING SMOKE CLOUDS SIMULATION (SpaceX Atmospheric Plume) ---
      for (let i = smokePuffs.length - 1; i >= 0; i--) {
        const s = smokePuffs[i];
        s.x += s.vx;
        s.y += s.vy;
        s.vx *= 0.965; // lower lateral drag allows wide expansion
        s.vy *= 0.94;
        s.radius += s.growth;
        s.alpha -= s.decay;

        if (s.alpha <= 0) {
          smokePuffs.splice(i, 1);
          continue;
        }

        // Soft radial gradient creates smooth, billowy cloud edges
        const grad = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, s.radius);
        grad.addColorStop(0, `rgba(${s.r}, ${s.g}, ${s.b}, ${s.alpha})`);
        grad.addColorStop(0.55, `rgba(${s.r}, ${s.g}, ${s.b}, ${s.alpha * 0.6})`);
        grad.addColorStop(1, `rgba(${s.r}, ${s.g}, ${s.b}, 0)`);
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.radius, 0, Math.PI * 2);
        ctx.fill();
      }

      // --- 2. SPACESHIP PHYSICS & ENGINE EMISSION ---
      if (rocket.active) {
        rocket.frame++;
        let enginePower = 0.85;

        if (rocket.frame < rocket.ignitionFrames) {
          // Launch pad rumble vibration
          rocket.x = rocket.baseX + (Math.random() - 0.5) * 2.5;
          enginePower = 0.75 + (rocket.frame / rocket.ignitionFrames) * 0.45;

          // Pad deluge trench smoke billow (rolling wide sideways across the screen)
          for (let k = 0; k < 5; k++) {
            const angle = Math.PI * 0.06 + Math.random() * Math.PI * 0.42;
            const speed = 6 + Math.random() * 9.5;
            const dir = Math.random() > 0.5 ? 1 : -1;
            spawnSmoke(
              rocket.x + (Math.random() - 0.5) * 16,
              rocket.y + 12,
              dir * Math.cos(angle) * speed,
              Math.sin(angle) * (1.2 + Math.random() * 3),
              16 + Math.random() * 14,
              1.8 + Math.random() * 1.5,
              0.58,
              0.004 + Math.random() * 0.005
            );
          }
        } else {
          // Ascension acceleration into space
          rocket.vy -= 0.62;
          rocket.y += rocket.vy;
          rocket.x = rocket.baseX + Math.sin(rocket.frame * 0.16) * 1.5;
          enginePower = 1.35;

          // Wide supersonic atmospheric exhaust plume trailing behind rocket
          const lateralSpread = 8 + Math.min(22, Math.abs(rocket.vy) * 1.6);
          for (let k = 0; k < 6; k++) {
            spawnSmoke(
              rocket.x + (Math.random() - 0.5) * 10,
              rocket.y + 14,
              (Math.random() - 0.5) * lateralSpread,
              3 + Math.random() * 6,
              18 + Math.random() * 16,
              2.0 + Math.random() * 1.8,
              0.52,
              0.0045 + Math.random() * 0.0045
            );
          }

          // Ground pad smoke continues billowing sideways during early climb
          if (rocket.frame < 38) {
            for (let k = 0; k < 2; k++) {
              const angle = Math.PI * 0.05 + Math.random() * Math.PI * 0.35;
              const speed = 7 + Math.random() * 8.5;
              const dir = Math.random() > 0.5 ? 1 : -1;
              spawnSmoke(
                rocket.baseX + (Math.random() - 0.5) * 24,
                cy + 12,
                dir * Math.cos(angle) * speed,
                Math.sin(angle) * (1.2 + Math.random() * 2),
                22 + Math.random() * 16,
                2.2 + Math.random() * 1.6,
                0.46,
                0.004 + Math.random() * 0.004
              );
            }
          }

          if (rocket.y < -70) {
            rocket.active = false;
          }
        }

        // Render Spaceship on top of smoke
        drawSpaceship(ctx, rocket.x, rocket.y, rocket.scale, enginePower);
      }

      if (rocket.active || smokePuffs.length > 0) {
        animId = requestAnimationFrame(render);
      } else {
        onComplete();
      }
    }

    animId = requestAnimationFrame(render);

    return () => {
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animId);
    };
  }, [active, origin, onComplete]);

  if (!active) return null;

  return <canvas ref={canvasRef} className="pointer-events-none fixed inset-0 z-[70] h-full w-full overflow-hidden" />;
}

/** Design spec §"Final gate bar" — pinned to the bottom of the board
 * (`margin-top:auto` on desktop).
 *
 * Distinct 3-Stage Design in SpacePoint brand purple (#a880ff):
 * - State 1 (In Progress): Calm 9s walking light along the 2.5px border with gentle hover lift
 *   and clean inline text ("Complete remaining tasks to submit — X remaining").
 * - State 2 (Ready to Submit): Highly reactive card and CTA button matching the board's tiles
 *   (hover lift, shadow expansion, active scale) with the all-border beacon pulse.
 * - State 3 (Locked): Holographic foil card with lock icon; click anywhere to replay fireworks.
 */
export function FinalGateBar({
  groups,
  teamReady,
  locked,
  hasTeam,
  assignmentId,
  onFinalized,
  teamName,
  lockedAt,
  lockedByName,
  pct = 0,
  remainingCount,
}: {
  groups: CheckpointGroup[];
  teamReady: boolean;
  locked: boolean;
  hasTeam: boolean;
  assignmentId: string;
  onFinalized: () => void;
  teamName?: string | null;
  lockedAt?: string | null;
  lockedByName?: string | null;
  pct?: number;
  remainingCount: number;
}) {
  const toast = useToast();
  const cardRef = useRef<HTMLDivElement | null>(null);
  const [celebrating, setCelebrating] = useState(false);
  const [celebrationOrigin, setCelebrationOrigin] = useState<{ x: number; y: number } | null>(null);
  const [snapping, setSnapping] = useState(false);

  const triggerCelebration = useCallback(() => {
    if (cardRef.current) {
      const rect = cardRef.current.getBoundingClientRect();
      setCelebrationOrigin({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 });
    } else {
      setCelebrationOrigin(null);
    }
    setCelebrating(true);
  }, []);

  // Fireworks only fire once the lock is actually confirmed — celebrating
  // eagerly, before the request resolves, showed the "success" animation
  // in full even when the mutation then failed (found live, 2026-09-19:
  // an offline click, or a 409 from a teammate finalizing first, still
  // played the whole launch).
  const finalSubmitMutation = useMutation({
    mutationFn: () => finalSubmitChecklist(assignmentId),
    onSuccess: () => {
      toast.success("Final submission locked in!");
      triggerCelebration();
      onFinalized();
    },
    onError: (err) => toast.error(errorDetail(err, "Couldn't finalize your team's submission.")),
  });

  // Stable identity across re-renders — SpaceFireworksOverlay's effect
  // depends on this prop, and a fresh inline function every render (the
  // checklist refetch onFinalized() kicks off re-renders FinalGateBar
  // mid-celebration) restarted the whole launch animation from scratch
  // each time (found live, 2026-09-19).
  const handleCelebrationComplete = useCallback(() => setCelebrating(false), []);

  const handleLockClick = () => {
    setSnapping(true);
    setTimeout(() => setSnapping(false), 500);
    finalSubmitMutation.mutate();
  };

  if (groups.length === 0) return null;
  const last = groups[groups.length - 1];
  const eyebrow = last.label ? `FINAL GATE · ${last.label.toUpperCase()}` : "FINAL GATE";

  return (
    <>
      <style>{`
        @keyframes walking-beam {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        @keyframes legendary-beam {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        @keyframes beacon-pulse {
          0% {
            border-color: rgba(168, 128, 255, 0.35);
            box-shadow: 0 0 4px rgba(168, 128, 255, 0.15);
          }
          28% {
            border-color: #a880ff;
            box-shadow: 0 0 24px 3px rgba(168, 128, 255, 0.72), 0 0 6px 1px rgba(214, 199, 225, 0.45);
          }
          58% {
            border-color: rgba(168, 128, 255, 0.35);
            box-shadow: 0 0 4px rgba(168, 128, 255, 0.15);
          }
          100% {
            border-color: rgba(168, 128, 255, 0.35);
            box-shadow: 0 0 4px rgba(168, 128, 255, 0.15);
          }
        }
        @keyframes holo-sweep {
          0% { background-position: -300% 0; }
          100% { background-position: 300% 0; }
        }
        @keyframes trophy-entrance {
          0% {
            opacity: 0.6;
            transform: scale(0.98);
          }
          100% {
            opacity: 1;
            transform: scale(1);
          }
        }
        @keyframes lock-snap {
          0% { transform: scale(1); }
          30% { transform: scale(0.96); }
          70% { transform: scale(1.02); }
          100% { transform: scale(1); }
        }
        .gate-walking-beam {
          background: conic-gradient(
            from 0deg at 50% 50%,
            transparent 0deg,
            transparent 270deg,
            rgba(168, 128, 255, 0.35) 305deg,
            #a880ff 335deg,
            #ffffff 352deg,
            rgba(168, 128, 255, 0.6) 360deg
          );
          animation: walking-beam 9s linear infinite;
        }
        /* Legendary card beam: 18s slow orbit, soft non-glaring lavender purple (no harsh pure-white) */
        .gate-legendary-beam {
          background: conic-gradient(
            from 0deg at 50% 50%,
            transparent 0deg,
            transparent 280deg,
            rgba(168, 128, 255, 0.08) 310deg,
            rgba(168, 128, 255, 0.22) 335deg,
            rgba(186, 155, 255, 0.38) 350deg,
            rgba(168, 128, 255, 0.12) 360deg
          );
          animation: legendary-beam 18s linear infinite;
        }
        .gate-beacon-border {
          animation: beacon-pulse 2.2s cubic-bezier(0.4, 0, 0.2, 1) infinite;
        }
        .gate-holo-foil {
          background: linear-gradient(
            115deg,
            transparent 0%,
            rgba(168, 128, 255, 0.04) 25%,
            rgba(214, 199, 225, 0.07) 50%,
            rgba(168, 128, 255, 0.04) 75%,
            transparent 100%
          );
          background-size: 250% 100%;
          animation: holo-sweep 14s ease-in-out infinite;
        }
        .gate-trophy-entrance {
          animation: trophy-entrance 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        .gate-snap-action {
          animation: lock-snap 0.45s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
      `}</style>

      <SpaceFireworksOverlay
        active={celebrating}
        origin={celebrationOrigin}
        onComplete={handleCelebrationComplete}
      />

      {locked ? (
        /* STATE 3: LEGENDARY LOCKED CARD (Calm 18s beam, soft purple aura, click card to replay celebration) */
        <div
          ref={cardRef}
          className={cn(
            "relative mt-6 md:mt-auto rounded-2xl p-[2px] overflow-hidden shadow-lg transition-all duration-200 ease-in-out hover:-translate-y-1 hover:shadow-xl active:translate-y-0 active:scale-[0.995] gate-trophy-entrance",
            snapping && "gate-snap-action"
          )}
        >
          <div className="absolute -inset-[150%] gate-legendary-beam pointer-events-none" />
          <div className="absolute inset-0 bg-primary/10 rounded-2xl pointer-events-none" />

          <div
            onClick={triggerCelebration}
            title="Click to replay celebration"
            className="group relative z-10 rounded-[14px] bg-card/95 backdrop-blur-xl p-4 sm:px-5 sm:py-4 border border-primary/20 overflow-hidden cursor-pointer hover:bg-card"
          >
            <div className="absolute inset-0 gate-holo-foil pointer-events-none" />

            <div className="relative z-10 flex items-center gap-3.5 sm:gap-4">
              <div className="relative flex h-10 w-10 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 border border-primary/20 text-primary shadow-none transition-transform duration-200 group-hover:scale-105 group-active:scale-95">
                <Lock size={20} className="stroke-[2.2] sm:w-[22px] sm:h-[22px]" />
                <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-primary-foreground text-[10px] font-bold shadow-none">
                  ✓
                </span>
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-[10px] sm:text-[11px] font-bold uppercase tracking-[0.12em] text-primary flex items-center gap-1.5">
                    <CheckCircle2 size={13} className="text-emerald-400 inline shrink-0" />
                    FINAL GATE · LOCKED
                  </span>
                  {teamName && (
                    <span className="text-[10px] sm:text-[11px] font-mono text-muted-foreground border border-border px-2 py-0.5 rounded-full bg-muted/40 hidden sm:inline">
                      {teamName}
                    </span>
                  )}
                </div>
                <div className="font-display font-extrabold text-[16px] sm:text-xl text-foreground tracking-tight">
                  Final submission locked
                </div>
                <div className="text-xs sm:text-[13px] text-muted-foreground font-medium mt-0.5">
                  {lockedAt && lockedByName
                    ? `Locked in at ${formatTimestamp(lockedAt)} by ${lockedByName}`
                    : lockedAt
                    ? `Locked in at ${formatTimestamp(lockedAt)}`
                    : "All deliverables locked for review"}
                </div>
              </div>

              <div className="relative z-10 hidden sm:flex flex-col items-end shrink-0 text-right font-mono">
                <span className="text-[11px] text-primary font-semibold tracking-wider">LOCKED</span>
                <span className="text-[10px] text-muted-foreground">
                  {lockedAt ? formatTimestamp(lockedAt) : "COMPLETED"}
                  {lockedByName ? ` · by ${lockedByName}` : ""}
                </span>
              </div>
            </div>
          </div>
        </div>
      ) : teamReady && hasTeam ? (
        /* STATE 2: READY TO SUBMIT (HIGHLY REACTIVE CARD & BUTTON LIKE BOARD TILES) */
        <div
          ref={cardRef}
          className={cn(
            "group relative mt-6 md:mt-auto rounded-2xl p-4 sm:p-5 border-[2.5px] gate-beacon-border bg-card/95 backdrop-blur-xl transition-all duration-200 ease-in-out hover:-translate-y-1 hover:shadow-lg hover:shadow-primary/20 active:translate-y-0 active:scale-[0.995]",
            snapping && "gate-snap-action"
          )}
        >
          <div className="flex flex-col sm:flex-row sm:items-center gap-3.5 sm:gap-4">
            <div className="flex items-center gap-3.5 sm:gap-4 flex-1 min-w-0">
              <div className="flex h-10 w-10 sm:h-11 sm:w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground font-bold shadow-sm shadow-primary/20 transition-transform duration-200 group-hover:scale-105">
                <CheckCircle2 size={20} className="stroke-[2.5]" />
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-[11px] font-bold uppercase tracking-[0.1em] text-primary flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-primary animate-ping" />
                    ALL TASKS CLEAR
                  </span>
                </div>
                <div className="font-display font-bold text-[16px] sm:text-[18px] text-foreground tracking-tight">
                  Lock Final Submission
                </div>
              </div>
            </div>

            {/* Highly Reactive Primary CTA Button — full width on mobile, auto on desktop */}
            <button
              type="button"
              disabled={finalSubmitMutation.isPending}
              onClick={() => {
                if (confirm("Are you sure you want to submit team's work? You won't be able to make further edits.")) {
                  handleLockClick();
                }
              }}
              className="w-full sm:w-auto justify-center flex items-center gap-2 px-5 py-3 sm:py-2.5 rounded-xl bg-primary hover:bg-[#b895ff] text-primary-foreground font-extrabold text-sm tracking-wide shadow-md shadow-primary/25 hover:shadow-lg hover:shadow-primary/35 hover:scale-[1.03] hover:-translate-y-0.5 active:scale-95 active:translate-y-0 transition-all duration-150 ease-out shrink-0 cursor-pointer disabled:opacity-50 disabled:pointer-events-none"
            >
              <span>{finalSubmitMutation.isPending ? "Locking…" : "Lock & Submit"}</span>
              <ArrowRight size={16} className="stroke-[2.5] transition-transform duration-150 group-hover:translate-x-1" />
            </button>
          </div>
        </div>
      ) : (
        /* STATE 1: IN PROGRESS (CLEAN INLINE TEXT — MOBILE OPTIMIZED WITH PROGRESS BAR) */
        (() => {
          const remaining = remainingCount;
          const isUngatedDone = !hasTeam && pct === 100;

          if (isUngatedDone) {
            return (
              <div className="mt-6 md:mt-auto flex items-center gap-4 rounded-2xl bg-card p-4 sm:p-5 border border-border shadow-lg transition-all duration-200 hover:-translate-y-0.5">
                <div className="flex h-10 w-10 sm:h-11 sm:w-11 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
                  <CheckCircle2 size={20} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-[11px] font-bold uppercase tracking-[0.1em] text-primary">{eyebrow}</div>
                  <div className="font-display font-bold text-[16px] sm:text-[17px] text-foreground">All clear — nice work!</div>
                </div>
              </div>
            );
          }

          return (
            <div
              ref={cardRef}
              className="relative mt-6 md:mt-auto rounded-2xl p-[2.5px] overflow-hidden shadow-xl transition-all duration-200 hover:-translate-y-0.5 hover:shadow-2xl"
            >
              <div className="absolute -inset-[150%] gate-walking-beam pointer-events-none" />
              <div className="absolute inset-0 bg-primary/20 rounded-2xl pointer-events-none" />

              <div className="relative z-10 rounded-[14px] bg-card/95 backdrop-blur-xl p-4 sm:px-5 sm:py-4 border border-primary/20">
                <div className="flex items-center gap-3.5 sm:gap-4">
                  <div className="flex h-10 w-10 sm:h-11 sm:w-11 shrink-0 items-center justify-center rounded-xl bg-primary/15 border border-primary/25 text-primary">
                    <Flag size={18} className="stroke-[2] sm:w-5 sm:h-5" />
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2 mb-0.5">
                      <span className="text-[11px] font-bold uppercase tracking-[0.1em] text-primary">
                        {eyebrow}
                      </span>
                      {/* Mobile percentage indicator */}
                      <span className="text-[11px] font-bold font-mono text-primary sm:hidden">
                        {pct}% Complete
                      </span>
                    </div>

                    {/* Headline that wraps cleanly without truncation */}
                    <div className="font-display font-bold text-[15px] sm:text-[17px] text-foreground tracking-tight leading-snug">
                      {remaining > 0
                        ? "Complete remaining tasks to submit"
                        : "Review & submit deliverables"}
                    </div>

                    {/* Mobile sleek progress bar */}
                    <div className="mt-2.5 w-full h-1.5 bg-muted/60 rounded-full overflow-hidden sm:hidden">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-primary/60 to-primary shadow-[0_0_8px_rgba(168,128,255,0.7)] transition-all duration-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>

                  {/* Desktop progress bar column */}
                  <div className="hidden sm:flex flex-col items-end shrink-0 pl-3">
                    <div className="text-[11px] font-bold text-primary mb-1">
                      {pct}% Complete
                    </div>
                    <div className="w-28 h-2.5 bg-muted rounded-full p-0.5 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-primary/60 to-primary shadow-[0_0_10px_rgba(168,128,255,0.7)] transition-all duration-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })()
      )}
    </>
  );
}
