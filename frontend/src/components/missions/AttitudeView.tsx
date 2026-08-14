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
 * The materials deliberately match SatKit's `satellite-sandbox.html`: a
 * polished light chrome chassis, a gold nadir dish, and solar wings that are
 * gold *frames* around dark blue cells rather than blue slabs. Those three
 * choices are what made the original read as a spacecraft.
 *
 * Two things here that SatKit did **not** have:
 *
 * * **It actually travels the orbit.** SatKit's model only ever spun in
 *   place, which quietly taught that attitude and position are the same
 *   thing. They are not: pointing is what you control, position is what the
 *   orbit hands you, and a pass arrives on the orbit's schedule regardless
 *   of where you are looking. The satellite tracks `orbitFraction` across
 *   the limb, and the ground slides beneath it at orbit rate.
 * * **The pointing-error ring.** Attitude error decides whether the antenna
 *   can close the link, so it belongs on the picture of where the spacecraft
 *   is looking rather than buried in a list of numbers.
 */
import { useEffect, useMemo, useRef } from "react";
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
  /** 0..1 through the current orbit — drives the travel across the limb. */
  orbitFraction: number;
  orbitNumber: number;
}

const FACE = "absolute inset-0 border border-white/20";

export default function AttitudeView({
  pitch, roll, yaw, attitudeError, pointingLimit, sunlit, inPass, safeMode,
  orbitFraction, orbitNumber,
}: Props) {
  const lost = attitudeError >= pointingLimit * 2;
  const degraded = attitudeError >= pointingLimit;

  const f = Math.min(Math.max(orbitFraction, 0), 1);

  // Crossing from the end of one orbit to the start of the next is a jump in
  // screen position, not in physical position. Animating it would draw the
  // satellite flying backwards across the whole viewport once per orbit, so
  // the tween is suppressed for exactly that frame.
  const prev = useRef(f);
  const wrapped = f < prev.current - 0.5;
  useEffect(() => { prev.current = f; }, [f]);

  // A 3U bus is 10x10x30 cm. Drawn at 34x34x102 px so the proportions are
  // honest rather than a generic cube. SatKit used 1.2 x 2.2 x 1.2, which is
  // closer to a 2U — the real ratio reads better and costs nothing.
  const body = { w: 34, h: 102, d: 34 };

  const panels = useMemo(
    () => [-1, 1].map((side) => ({
      side,
      transform: `translateX(${side * (body.w / 2 + 30)}px) rotateY(90deg)`,
    })),
    [body.w],
  );

  // Travel: left to right across the visible limb, with a shallow arc so the
  // path reads as curved around a body rather than as a slide.
  const travelPct = 10 + f * 80;
  const arcLift = -Math.sin(Math.PI * f) * 16;
  // Fade at the very edges so the wrap is a horizon crossing, not a snap.
  const edgeFade = Math.min(1, Math.min(f, 1 - f) / 0.06);

  return (
    <div className="relative w-full h-[240px] rounded-xl overflow-hidden ring-1 ring-border bg-gradient-to-b from-[#04060a] via-[#0c1626] to-[#1b3255]">
      {/* Star field — pure CSS, no asset. */}
      <div
        className="absolute inset-0 opacity-60"
        style={{
          backgroundImage:
            "radial-gradient(1px 1px at 20% 30%, #fff, transparent), radial-gradient(1px 1px at 75% 18%, #cfe3ff, transparent), radial-gradient(1px 1px at 45% 72%, #fff, transparent), radial-gradient(1px 1px at 88% 62%, #bcd4ff, transparent), radial-gradient(1px 1px at 12% 85%, #fff, transparent), radial-gradient(1px 1px at 62% 45%, #e8f0ff, transparent)",
        }}
      />

      {/* Earth limb. The satellite is not floating in a void — it is falling
          around something, and the something has to be on screen for the
          travel to mean anything. */}
      <div
        className="absolute rounded-[50%] transition-colors duration-1000"
        style={{
          left: "-40%", right: "-40%", top: "78%", height: "340px",
          background: sunlit
            ? "radial-gradient(ellipse at 62% 8%, #4c9fe0 0%, #1d5a95 42%, #0b2b4d 100%)"
            : "radial-gradient(ellipse at 62% 8%, #14304d 0%, #0b1d33 45%, #050d18 100%)",
          boxShadow: sunlit
            ? "0 -18px 40px -10px rgba(90,170,255,0.45)"
            : "0 -18px 40px -14px rgba(60,110,180,0.18)",
        }}
      />
      {/* Ground sliding beneath at orbit rate — the motion cue that makes a
          static-looking frame read as 7.6 km/s. */}
      <div
        className="absolute opacity-30"
        style={{
          left: "-40%", right: "-40%", top: "78%", height: "340px",
          borderRadius: "50%",
          backgroundImage:
            "repeating-linear-gradient(90deg, rgba(255,255,255,0.10) 0 2px, transparent 2px 78px)",
          backgroundPositionX: `${-f * 156}px`,
        }}
      />

      {/* Sun / shadow cue, so eclipse is visible in the picture and not just
          in the power number. */}
      <div
        className="absolute inset-0 transition-opacity duration-1000"
        style={{
          background: sunlit
            ? "radial-gradient(circle at 78% 22%, rgba(255,236,180,0.20), transparent 55%)"
            : "linear-gradient(180deg, rgba(0,0,0,0.55), rgba(0,0,0,0.72))",
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
        <div className="text-[#8892b0]">
          ORBIT {orbitNumber} · {(f * 100).toFixed(0)}% AROUND
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

      {/* The travelling frame. Attitude rotation happens inside it, so the two
          motions stay separable: where it is, versus where it is looking. */}
      <div
        className="absolute top-0 bottom-0 flex items-center justify-center"
        style={{
          left: `${travelPct}%`,
          width: 0,
          opacity: edgeFade,
          transform: `translateY(${arcLift}px)`,
          transition: wrapped ? "none" : "left 1000ms linear, transform 1000ms linear, opacity 400ms linear",
          perspective: "760px",
        }}
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
          {/* Chassis — polished chrome, four long faces plus the two ends.
              The shading between faces is what sells a flat div as metal. */}
          <div className={`${FACE} bg-gradient-to-b from-[#f2f4f7] to-[#c3ccd8]`} style={{ transform: `translateZ(${body.d / 2}px)` }} />
          <div className={`${FACE} bg-gradient-to-b from-[#9aa6b5] to-[#76828f]`} style={{ transform: `rotateY(180deg) translateZ(${body.d / 2}px)` }} />
          <div
            className={`${FACE} bg-gradient-to-b from-[#dce2ea] to-[#a6b1bf]`}
            style={{ width: body.d, transform: `rotateY(90deg) translateZ(${body.w / 2}px)`, left: (body.w - body.d) / 2 }}
          />
          <div
            className={`${FACE} bg-gradient-to-b from-[#98a4b3] to-[#6f7a89]`}
            style={{ width: body.d, transform: `rotateY(-90deg) translateZ(${body.w / 2}px)`, left: (body.w - body.d) / 2 }}
          />
          <div
            className={`${FACE} bg-gradient-to-br from-[#e6ebf1] to-[#b4bfcc]`}
            style={{ height: body.d, transform: `rotateX(90deg) translateZ(${body.h / 2}px)`, top: (body.h - body.d) / 2 }}
          />
          <div
            className={`${FACE} bg-gradient-to-br from-[#8c98a7] to-[#666f7c]`}
            style={{ height: body.d, transform: `rotateX(-90deg) translateZ(${body.h / 2}px)`, top: (body.h - body.d) / 2 }}
          />

          {/* Gold nadir dish, sitting under the -Y end of the bus. */}
          <div
            className="absolute rounded-[50%]"
            style={{
              width: 26, height: 10,
              left: body.w / 2 - 13, top: body.h - 4,
              background: "linear-gradient(180deg, #f0d270, #b8952c)",
              boxShadow: "0 2px 6px rgba(0,0,0,0.45)",
            }}
          />

          {/* Deployed solar wings: a gold frame carrying dark blue cells,
              exactly as the original modelled them. They brighten in
              sunlight, which is the same fact the power balance reports
              numerically. */}
          {panels.map(({ side, transform }) => (
            <div
              key={side}
              className="absolute p-[3px] transition-colors duration-1000"
              style={{
                width: 60,
                height: body.h * 0.78,
                top: body.h * 0.11,
                left: body.w / 2 - 30,
                transform,
                background: "linear-gradient(160deg, #e3c463, #a4842a)",
                boxShadow: sunlit ? "0 0 14px -2px rgba(150,190,255,0.5)" : "none",
              }}
            >
              <div
                className="w-full h-full transition-colors duration-1000"
                style={{
                  background: sunlit
                    ? "repeating-linear-gradient(90deg, #10346e 0 7px, #061c42 7px 8px)"
                    : "repeating-linear-gradient(90deg, #0a1730 0 7px, #050c1c 7px 8px)",
                }}
              />
            </div>
          ))}

          {/* Antenna boom, pointing along -Z (nadir when we're behaving). */}
          <div
            className="absolute"
            style={{
              width: 3, height: 26, left: body.w / 2 - 1.5, top: body.h + 6,
              background: "linear-gradient(180deg, #e3c463, #8f7422)",
            }}
          />
        </div>
      </div>
    </div>
  );
}
