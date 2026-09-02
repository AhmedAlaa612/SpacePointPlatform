import { useEffect, useState } from "react";
import type { LmsProgramChecklistItem } from "@/api/lms";
import { tileState } from "./roadmap";

/** The circuit-board "wires" between tiles — generated from measured tile
 * geometry every layout pass, never hard-coded coordinates (design spec
 * §"Traces (the wires)" / TRACES.md's own "generate, don't hard-code"
 * instruction). Colour = the state of the tile the run *leaves*; the run
 * entering the live tile is the live colour. Decoration only —
 * `aria-hidden`, `pointer-events:none`, behind the tiles.
 *
 * Two distinct connector shapes, per TRACES.md's own authored examples:
 * - same-row (desktop): one 45° dogleg, H-L-H (`horizontalDogleg`).
 * - row-change (desktop) and every mobile connector (always a "row
 *   change" there, one tile per row): a two-kick S — desktop's is
 *   vertical-dominant (V-L-V-L, `verticalS`), mobile's is V-L-H-L
 *   (`mobileZigzag`) per TRACES.md's own "leave the bottom edge → short
 *   vertical → 45° step → short horizontal → 45° step into the top edge."
 *
 * Stroke count (single/double/triple) is tiered by the run's own length —
 * "long legs doubled, short legs single" (README) — not by state or
 * surface, so most runs on a normal board end up doubled with only the
 * shortest single and the longest (row-change) triple. */

const TRACE_COLOR: Record<ReturnType<typeof tileState>, string> = {
  cleared: "var(--board-trace-cleared)", live: "var(--board-trace-live)", locked: "var(--board-trace-dim)",
};

interface Rect { left: number; top: number; right: number; bottom: number; centerX: number; centerY: number; width: number; height: number }
interface TraceRun { path: string; color: string; strokes: number; axis: "x" | "y"; nodeAt: [number, number] }

function round(n: number) {
  return Math.round(n);
}

/** Same-row connector — exit the left/right edge, one 45° dogleg absorbs
 * the small vertical stagger between adjacent tiles, enter the other
 * tile's edge. TRACES.md: `M158,90 H192 L208,106 H246`. */
function horizontalDogleg(x1: number, y1: number, x2: number, y2: number): string {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const kick = Math.min(Math.abs(dy), Math.abs(dx) / 2 || Math.abs(dy)) || 1;
  const dirX = dx >= 0 ? 1 : -1;
  const remaining = dx - dirX * kick;
  const h1 = remaining / 2;
  const midX1 = x1 + h1;
  const midX2 = midX1 + dirX * kick;
  return `M${round(x1)},${round(y1)} H${round(midX1)} L${round(midX2)},${round(y2)} H${round(x2)}`;
}

/** Desktop row-change connector — exit the bottom edge, an S made of two
 * fixed-size 45° kicks (never degenerating to a bare straight line even
 * when the two tiles share a column — TRACES.md's own same-column wrap
 * example, `M817,174 V186 L803,200 V208 L817,222`, still zigzags: kick
 * out ~14px, then back). */
function verticalS(x1: number, y1: number, x2: number, y2: number): string {
  const dyTotal = y2 - y1;
  const dxTotal = x2 - x1;
  const KICK = 14;
  // Same-column wrap (row-change tiles happen to line up): still kick out
  // and back rather than drawing a bare straight line — TRACES.md's own
  // same-column example (`M817,174 V186 L803,200 V208 L817,222`) zigzags
  // with zero net horizontal drift. Otherwise split the real dx in half
  // across the two 45° kicks so each is a true 45° (dx magnitude ==
  // dy magnitude == kick).
  const aligned = Math.abs(dxTotal) < KICK * 1.5;
  const kick = aligned ? KICK : Math.min(Math.abs(dxTotal) / 2, KICK * 1.6);
  const dir1 = aligned ? 1 : Math.sign(dxTotal || 1);
  // Total dy = v1 (first vertical) + kick (first diagonal) + v2 (middle
  // vertical) + kick (second diagonal) — no trailing vertical segment,
  // the second diagonal lands exactly on (x2, y2).
  const vRemaining = Math.max(dyTotal - 2 * kick, kick * 0.5);
  const v1 = vRemaining * 0.4;
  const v2 = vRemaining - v1;
  const yA = y1 + v1;
  const xB = x1 + dir1 * kick;
  const yB = yA + kick;
  const yC = yB + v2;
  return `M${round(x1)},${round(y1)} V${round(yA)} L${round(xB)},${round(yB)} V${round(yC)} L${round(x2)},${round(y2)}`;
}

/** Mobile connector — the alternating-column layout's own shape, always
 * V-L-H-L per TRACES.md: `M170,104 V116 L182,128 H198 L210,140`. */
function mobileZigzag(x1: number, y1: number, x2: number, y2: number): string {
  const dyTotal = y2 - y1;
  const dxTotal = x2 - x1;
  const dirX = dxTotal >= 0 ? 1 : -1;
  // Both diagonal kicks the same size (TRACES.md's own numbers: a 12px
  // drop, two 12px 45° kicks, a 16px horizontal run between them) — first
  // vertical absorbs whatever's left of dyTotal so the second kick still
  // lands exactly on (x2, y2), no trailing vertical segment needed.
  const s = Math.min(14, Math.max(8, Math.abs(dyTotal) / 3), Math.abs(dxTotal) / 2 || 14);
  const v0 = Math.max(dyTotal - 2 * s, s);
  const yA = y1 + v0;
  const xB = x1 + dirX * s;
  const yB = yA + s;
  const hRemaining = dxTotal - 2 * dirX * s;
  const xC = xB + hRemaining;
  return `M${round(x1)},${round(y1)} V${round(yA)} L${round(xB)},${round(yB)} H${round(xC)} L${round(x2)},${round(y2)}`;
}

function buildConnector(from: Rect, to: Rect, isMobile: boolean): { path: string; axis: "x" | "y" } {
  const dy = to.centerY - from.centerY;
  const sameRow = !isMobile && Math.abs(dy) < from.height * 0.6;
  if (sameRow) {
    const goingRight = to.centerX >= from.centerX;
    const x1 = goingRight ? from.right : from.left;
    const x2 = goingRight ? to.left : to.right;
    return { path: horizontalDogleg(x1, from.centerY, x2, to.centerY), axis: "x" };
  }
  if (isMobile) {
    return { path: mobileZigzag(from.centerX, from.bottom, to.centerX, to.top), axis: "y" };
  }
  return { path: verticalS(from.centerX, from.bottom, to.centerX, to.top), axis: "y" };
}

/** "Long legs doubled, short legs single" — tiered by the run's rough
 * manhattan length, plus a triple tier for the longest (row-change) legs,
 * matching the design's own mostly-double-some-triple-some-single mix. */
function strokeCountFor(from: Rect, to: Rect): number {
  const length = Math.abs(to.centerX - from.centerX) + Math.abs(to.centerY - from.centerY);
  if (length < 70) return 1;
  if (length < 220) return 2;
  return 3;
}

/** Measurement is an inherent side effect (real DOM geometry, not derived
 * from props/state), so it lives entirely inside a ResizeObserver-driven
 * effect that calls `setState` — never read from refs during render. */
export function TraceLayer({
  containerRef, tileRefs, items, isMobile,
}: {
  containerRef: React.RefObject<HTMLDivElement | null>;
  tileRefs: React.RefObject<Map<string, HTMLDivElement>>;
  items: LmsProgramChecklistItem[];
  isMobile: boolean;
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
        return {
          left, top, right: left + r.width, bottom: top + r.height,
          centerX: left + r.width / 2, centerY: top + r.height / 2, width: r.width, height: r.height,
        };
      };

      const runsOut: TraceRun[] = [];
      for (let i = 0; i < items.length - 1; i++) {
        const fromEl = tileRefs.current?.get(items[i].id);
        const toEl = tileRefs.current?.get(items[i + 1].id);
        if (!fromEl || !toEl) continue;
        const fromRect = rectOf(fromEl);
        const toRect = rectOf(toEl);
        const { path, axis } = buildConnector(fromRect, toRect, isMobile);
        const strokes = strokeCountFor(fromRect, toRect);
        const color = TRACE_COLOR[tileState(items[i])];
        const sameRow = !isMobile && Math.abs(toRect.centerY - fromRect.centerY) < fromRect.height * 0.6;
        const nodeAt: [number, number] = sameRow
          ? [round(toRect.centerX >= fromRect.centerX ? toRect.left : toRect.right), round(toRect.centerY)]
          : [round(toRect.centerX), round(toRect.top)];
        runsOut.push({ path, color, strokes, axis, nodeAt });
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
  }, [containerRef, tileRefs, items, isMobile]);

  return (
    <svg
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 -z-[1] h-full w-full overflow-visible"
      viewBox={layout.viewBox}
      preserveAspectRatio="none"
    >
      {layout.runs.map((run, i) => {
        // Perpendicular-to-the-run offsets for the doubled/tripled
        // companions — a horizontal-dominant run doubles vertically, a
        // vertical-dominant run doubles horizontally, so the copies read
        // as parallel PCB traces rather than a diagonal smear.
        const offsets: [number, number][] =
          run.strokes === 1 ? [[0, 0]]
          : run.strokes === 2 ? (run.axis === "x" ? [[0, 0], [0, 7]] : [[0, 0], [7, 0]])
          : (run.axis === "x" ? [[0, -7], [0, 0], [0, 7]] : [[-7, 0], [0, 0], [7, 0]]);
        return (
          <g key={i}>
            {offsets.map(([ox, oy], j) => (
              <path
                key={j} d={run.path} fill="none" strokeWidth={2} strokeLinecap="square"
                transform={ox || oy ? `translate(${ox} ${oy})` : undefined}
                style={{ stroke: run.color, opacity: j === Math.floor(offsets.length / 2) ? 1 : 0.85, transition: "stroke 300ms" }}
              />
            ))}
            <circle cx={run.nodeAt[0]} cy={run.nodeAt[1]} r={3} style={{ fill: run.color, transition: "fill 300ms" }} />
          </g>
        );
      })}
    </svg>
  );
}
