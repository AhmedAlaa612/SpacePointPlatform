/** Live attitude viewport (Operate v2, Stage 7C-6).
 *
 * SatKit rendered a three.js CubeSat in a sandboxed iframe fed pitch/roll/yaw
 * over `postMessage`, and it was the most striking thing in the source. The
 * v1 port dropped it entirely.
 *
 * This rebuilds it with **CSS 3D transforms** rather than adding three.js.
 * That is a deliberate call, not a shortcut: three.js is ~600 KB, this
 * platform ships no CDN scripts, and the thing being drawn is six flat
 * faces and two panels rotating on three axes — which `transform-style:
 * preserve-3d` does natively, in about a hundred lines, with no new
 * dependency and no bundle cost. It also inherits the theme, which the
 * iframe version could not.
 *
 * The pointing-error ring is new. Attitude error is what decides whether
 * the antenna can close the link, so it belongs on the picture of where the
 * spacecraft is looking rather than buried in a list of numbers.
 */
import { useMemo } from "react";
import { AlertTriangle } from "lucide-react";

interface Props {
  pitch: number;
  roll: number;
  yaw: number;
  attitudeError: number;
  pointingLimit: number;
  sunlit: boolean;
  inPass: boolean;
  safeMode: boolean;
}

const FACE = "absolute inset-0 border border-white/25";

export default function AttitudeView({
  pitch, roll, yaw, attitudeError, pointingLimit, sunlit, inPass, safeMode,
}: Props) {
  const lost = attitudeError >= pointingLimit * 2;
  const degraded = attitudeError >= pointingLimit;

  // A 3U bus is 10x10x30 cm. Drawn at 34x34x102 px so the proportions are
  // honest rather than a generic cube.
  const body = { w: 34, h: 102, d: 34 };

  const panels = useMemo(
    () => [-1, 1].map((side) => ({
      side,
      transform: `translateX(${side * (body.w / 2 + 30)}px) rotateY(90deg)`,
    })),
    [body.w],
  );

  return (
    <div className="relative w-full h-[240px] rounded-xl overflow-hidden ring-1 ring-border bg-gradient-to-b from-[#070b16] to-[#0d1424]">
      {/* Star field — pure CSS, no asset. */}
      <div
        className="absolute inset-0 opacity-60"
        style={{
          backgroundImage:
            "radial-gradient(1px 1px at 20% 30%, #fff, transparent), radial-gradient(1px 1px at 75% 18%, #cfe3ff, transparent), radial-gradient(1px 1px at 45% 72%, #fff, transparent), radial-gradient(1px 1px at 88% 62%, #bcd4ff, transparent), radial-gradient(1px 1px at 12% 85%, #fff, transparent), radial-gradient(1px 1px at 62% 45%, #e8f0ff, transparent)",
        }}
      />

      {/* Sun / shadow cue, so eclipse is visible in the picture and not just
          in the power number. */}
      <div
        className="absolute inset-0 transition-opacity duration-1000"
        style={{
          background: sunlit
            ? "radial-gradient(circle at 78% 22%, rgba(255,236,180,0.22), transparent 55%)"
            : "linear-gradient(180deg, rgba(0,0,0,0.55), rgba(0,0,0,0.75))",
        }}
      />

      <div className="absolute top-3 left-3 z-10 font-mono text-[10px] leading-relaxed text-[#64ffda] pointer-events-none">
        <div>ATTITUDE DETERMINATION &amp; CONTROL</div>
        <div className="text-[#8892b0]">
          P {pitch.toFixed(1)}&deg; · R {roll.toFixed(1)}&deg; · Y {yaw.toFixed(1)}&deg;
        </div>
        <div className={degraded ? "text-amber-400" : "text-[#8892b0]"}>
          POINTING ERR {attitudeError.toFixed(2)}&deg; / {pointingLimit.toFixed(1)}&deg;
        </div>
      </div>

      {inPass && !degraded && (
        <div className="absolute top-3 right-3 z-10 font-mono text-[10px] text-emerald-400 pointer-events-none">
          ● ANTENNA ON TARGET
        </div>
      )}
      {lost && (
        <div className="absolute top-3 right-3 z-10 flex items-center gap-1 font-mono text-[10px] text-red-400 pointer-events-none">
          <AlertTriangle className="size-3" /> ATTITUDE LOST
        </div>
      )}
      {safeMode && !lost && (
        <div className="absolute top-3 right-3 z-10 font-mono text-[10px] text-amber-400 pointer-events-none">
          ☀ SUN-SAFE POINTING
        </div>
      )}

      <div
        className="absolute inset-0 flex items-center justify-center"
        style={{ perspective: "760px" }}
      >
        {/* Pointing-error ring: grows with error, turns red once the link
            can no longer close. */}
        <div
          className="absolute rounded-full border transition-all duration-700"
          style={{
            width: `${120 + Math.min(attitudeError, 25) * 5}px`,
            height: `${120 + Math.min(attitudeError, 25) * 5}px`,
            borderColor: lost
              ? "rgba(248,81,73,0.55)"
              : degraded
                ? "rgba(247,178,103,0.45)"
                : "rgba(100,255,218,0.28)",
            borderStyle: degraded ? "dashed" : "solid",
          }}
        />

        <div
          className="relative transition-transform duration-1000 ease-out"
          style={{
            transformStyle: "preserve-3d",
            width: body.w,
            height: body.h,
            transform: `rotateX(${pitch - 12}deg) rotateZ(${roll}deg) rotateY(${yaw}deg)`,
          }}
        >
          {/* Bus — four long faces plus the two ends. */}
          <div className={`${FACE} bg-[#c9d3e0]`} style={{ transform: `translateZ(${body.d / 2}px)` }} />
          <div className={`${FACE} bg-[#8e9bad]`} style={{ transform: `rotateY(180deg) translateZ(${body.d / 2}px)` }} />
          <div
            className={`${FACE} bg-[#aab6c6]`}
            style={{ width: body.d, transform: `rotateY(90deg) translateZ(${body.w / 2}px)`, left: (body.w - body.d) / 2 }}
          />
          <div
            className={`${FACE} bg-[#7f8b9c]`}
            style={{ width: body.d, transform: `rotateY(-90deg) translateZ(${body.w / 2}px)`, left: (body.w - body.d) / 2 }}
          />
          <div
            className={`${FACE} bg-[#d8b45a]`}
            style={{ height: body.d, transform: `rotateX(90deg) translateZ(${body.h / 2}px)`, top: (body.h - body.d) / 2 }}
          />
          <div
            className={`${FACE} bg-[#6f7a89]`}
            style={{ height: body.d, transform: `rotateX(-90deg) translateZ(${body.h / 2}px)`, top: (body.h - body.d) / 2 }}
          />

          {/* Deployed solar wings. They brighten in sunlight, which is the
              same fact the power balance is reporting numerically. */}
          {panels.map(({ side, transform }) => (
            <div
              key={side}
              className="absolute border transition-colors duration-1000"
              style={{
                width: 60,
                height: body.h * 0.78,
                top: body.h * 0.11,
                left: body.w / 2 - 30,
                transform,
                background: sunlit
                  ? "repeating-linear-gradient(90deg, #2f4f8f 0 6px, #1b3060 6px 7px)"
                  : "repeating-linear-gradient(90deg, #1b2740 0 6px, #131c2e 6px 7px)",
                borderColor: sunlit ? "rgba(120,170,255,0.5)" : "rgba(70,90,130,0.4)",
              }}
            />
          ))}

          {/* Antenna boom, pointing along -Z (nadir when we're behaving). */}
          <div
            className="absolute bg-[#d8b45a]"
            style={{ width: 3, height: 26, left: body.w / 2 - 1.5, top: body.h, transform: "rotateX(0deg)" }}
          />
        </div>
      </div>
    </div>
  );
}
