/** Minimal 3D attitude indicator — CSS 3D transforms, same call the
 * Operate mission's AttitudeView made (no three.js: this is six flat faces
 * rotating on three axes, which `transform-style: preserve-3d` does
 * natively). Unlike Operate's, this has no orbit/pass model to fake — it
 * just shows the ADCS board's live pitch/roll/yaw, exactly what the legacy
 * ground station displayed. */
interface Props {
  pitch: number;
  roll: number;
  yaw: number;
}

const FACE = "absolute inset-0 border border-white/20 bg-gradient-to-br from-slate-300 to-slate-500";

export default function AttitudeCube({ pitch, roll, yaw }: Props) {
  return (
    <div className="rounded-xl ring-1 ring-border p-4 bg-card">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-3">
        Attitude
      </div>
      <div style={{ perspective: 600 }} className="flex items-center justify-center py-6">
        <div
          style={{
            width: 72,
            height: 72,
            transformStyle: "preserve-3d",
            transform: `rotateX(${-pitch}deg) rotateY(${yaw}deg) rotateZ(${roll}deg)`,
            transition: "transform 0.3s ease-out",
          }}
          className="relative"
        >
          <div className={FACE} style={{ transform: "translateZ(36px)" }} />
          <div className={FACE} style={{ transform: "rotateY(180deg) translateZ(36px)" }} />
          <div className={FACE} style={{ transform: "rotateY(90deg) translateZ(36px)" }} />
          <div className={FACE} style={{ transform: "rotateY(-90deg) translateZ(36px)" }} />
          <div className={FACE} style={{ transform: "rotateX(90deg) translateZ(36px)" }} />
          <div className={FACE} style={{ transform: "rotateX(-90deg) translateZ(36px)" }} />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center font-mono text-xs">
        <div><div className="text-muted-foreground text-[10px]">PITCH</div>{pitch.toFixed(1)}°</div>
        <div><div className="text-muted-foreground text-[10px]">ROLL</div>{roll.toFixed(1)}°</div>
        <div><div className="text-muted-foreground text-[10px]">YAW</div>{yaw.toFixed(1)}°</div>
      </div>
    </div>
  );
}
