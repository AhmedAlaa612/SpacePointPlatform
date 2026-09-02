import { useEffect, useState } from "react";
import type { LmsProgramChecklistItem } from "@/api/lms";
import { tileState } from "./roadmap";

/** The circuit-board "wires" between tiles — generated from measured tile
 * geometry every layout pass, never hard-coded coordinates (design spec
 * §"Traces (the wires)" / TRACES.md's own "generate, don't hard-code"
 * instruction). Colour = the state of the tile the run *leaves*; the run
 * entering the live tile is the live colour. Decoration only —
 * `aria-hidden`, `pointer-events:none`, behind the tiles. */

const TRACE_COLOR: Record<ReturnType<typeof tileState>, string> = {
  cleared: "var(--board-trace-cleared)", live: "var(--board-trace-live)", locked: "var(--board-trace-dim)",
};

interface Rect { left: number; top: number; right: number; bottom: number; centerX: number; centerY: number; height: number }
interface TraceRun { path: string; color: string; doubled: boolean; nodeAt: [number, number] }

function round(n: number) {
  return Math.round(n);
}

/** One 45°-dogleg run absorbing a small perpendicular offset, primary
 * axis horizontal (same-row / same-column connectors). */
function horizontalDogleg(x1: number, y1: number, x2: number, y2: number): string {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const adyStep = Math.min(Math.abs(dy), Math.abs(dx) / 2 || Math.abs(dy));
  const dirX = dx >= 0 ? 1 : -1;
  const remaining = dx - dirX * adyStep;
  const h1 = remaining / 2;
  const midX1 = x1 + h1;
  const midX2 = midX1 + dirX * adyStep;
  return `M${round(x1)},${round(y1)} H${round(midX1)} L${round(midX2)},${round(y2)} H${round(x2)}`;
}

/** The row-change / mobile connector — an S with two 45° steps, primary
 * axis vertical (TRACES.md's "run vertically past the row gap ... insert
 * two 45° steps"). */
function verticalS(x1: number, y1: number, x2: number, y2: number): string {
  const dy = y2 - y1;
  const dx = x2 - x1;
  const halfDx = dx / 2;
  const step = Math.min(Math.abs(halfDx), Math.abs(dy) / 3 || Math.abs(halfDx)) || 1;
  const dirY = dy >= 0 ? 1 : -1;
  const remaining = dy - 2 * dirY * step;
  const v1 = remaining / 3;
  const yA = y1 + v1;
  const xB = x1 + halfDx;
  const yB = yA + dirY * step;
  const yC = yB + v1;
  const yD = yC + dirY * step;
  return `M${round(x1)},${round(y1)} V${round(yA)} L${round(xB)},${round(yB)} V${round(yC)} L${round(x2)},${round(yD)} V${round(y2)}`;
}

function buildConnector(from: Rect, to: Rect): string {
  const dy = to.centerY - from.centerY;
  const sameRow = Math.abs(dy) < from.height * 0.6;
  if (sameRow) {
    const goingRight = to.centerX >= from.centerX;
    const x1 = goingRight ? from.right : from.left;
    const x2 = goingRight ? to.left : to.right;
    return horizontalDogleg(x1, from.centerY, x2, to.centerY);
  }
  return verticalS(from.centerX, from.bottom, to.centerX, to.top);
}

/** Measurement is an inherent side effect (real DOM geometry, not derived
 * from props/state), so it lives entirely inside a ResizeObserver-driven
 * effect that calls `setState` — never read from refs during render. */
export function TraceLayer({
  containerRef, tileRefs, items,
}: {
  containerRef: React.RefObject<HTMLDivElement | null>;
  tileRefs: React.RefObject<Map<string, HTMLDivElement>>;
  items: LmsProgramChecklistItem[];
}) {
  const [layout, setLayout] = useState<{ runs: TraceRun[]; viewBox: string }>({ runs: [], viewBox: "0 0 1 1" });

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const measure = () => {
      const containerRect = container.getBoundingClientRect();
      const rectOf = (el: HTMLElement): Rect => {
        const r = el.getBoundingClientRect();
        const left = r.left - containerRect.left;
        const top = r.top - containerRect.top;
        return { left, top, right: left + r.width, bottom: top + r.height, centerX: left + r.width / 2, centerY: top + r.height / 2, height: r.height };
      };

      const runsOut: TraceRun[] = [];
      for (let i = 0; i < items.length - 1; i++) {
        const fromEl = tileRefs.current?.get(items[i].id);
        const toEl = tileRefs.current?.get(items[i + 1].id);
        if (!fromEl || !toEl) continue;
        const fromRect = rectOf(fromEl);
        const toRect = rectOf(toEl);
        const path = buildConnector(fromRect, toRect);
        const doubled = Math.abs(toRect.centerY - fromRect.centerY) >= fromRect.height * 0.6; // row-change legs are the long ones
        const color = TRACE_COLOR[tileState(items[i])];
        const enterPoint: [number, number] = doubled
          ? [round(toRect.centerX), round(toRect.top)]
          : [round(toRect.centerX >= fromRect.centerX ? toRect.left : toRect.right), round(toRect.centerY)];
        runsOut.push({ path, color, doubled, nodeAt: enterPoint });
      }
      const h = Math.max(container.offsetHeight, 1);
      const w = Math.max(container.offsetWidth, 1);
      setLayout({ runs: runsOut, viewBox: `0 0 ${w} ${h}` });
    };

    const ro = new ResizeObserver(measure);
    ro.observe(container);
    for (const el of tileRefs.current?.values() ?? []) ro.observe(el);
    measure();

    let cancelled = false;
    document.fonts?.ready?.then(() => { if (!cancelled) measure(); });
    return () => { cancelled = true; ro.disconnect(); };
  }, [containerRef, tileRefs, items]);

  return (
    <svg
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 -z-[1] h-full w-full overflow-visible"
      viewBox={layout.viewBox}
      preserveAspectRatio="none"
    >
      {layout.runs.map((run, i) => (
        <g key={i}>
          <path d={run.path} fill="none" strokeWidth={2} strokeLinecap="square" style={{ stroke: run.color, transition: "stroke 300ms" }} />
          {run.doubled && (
            <path
              d={run.path}
              fill="none"
              strokeWidth={2}
              strokeLinecap="square"
              transform="translate(6 6)"
              style={{ stroke: run.color, opacity: 0.85, transition: "stroke 300ms" }}
            />
          )}
          <circle cx={run.nodeAt[0]} cy={run.nodeAt[1]} r={3} style={{ fill: run.color, transition: "fill 300ms" }} />
        </g>
      ))}
    </svg>
  );
}
