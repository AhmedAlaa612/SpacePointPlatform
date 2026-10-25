import React, { useEffect, useRef, useState } from "react";

// Hairline math & spring primitives
const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const r2 = (n: number) => Math.round(n * 100) / 100;

interface Spring {
  x: number;
  v: number;
  t: number;
  k: number;
  d: number;
}

function createSpring(init: number, stiffness = 170, damping = 22): Spring {
  return { x: init, v: 0, t: init, k: stiffness, d: damping };
}

function stepSpring(s: Spring, dt: number): boolean {
  const f = -s.k * (s.x - s.t) - s.d * s.v;
  s.v += f * dt;
  s.x += s.v * dt;
  if (Math.abs(s.x - s.t) < 0.001 && Math.abs(s.v) < 0.001) {
    s.x = s.t;
    s.v = 0;
    return false;
  }
  return true;
}

const SVG_NS = "http://www.w3.org/2000/svg";
function svgEl<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attrs: Record<string, string | number> = {},
  parent: SVGElement | null = null
): SVGElementTagNameMap[K] {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    el.setAttribute(k, String(v));
  }
  if (parent) parent.appendChild(el);
  return el;
}

export interface CubeSatButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
  variant?: "primary" | "secondary";
  showUnitBadge?: boolean;
  fixedUnits?: number;
  showDot?: boolean;
  onUnitsChange?: (units: number) => void;
}

/**
 * Auto-sizing 2.5D Rectangular CubeSat Button with spring physics:
 * - Text sits directly on the front face of the CubeSat chassis.
 * - ResizeObserver measures exact button dimensions and dynamically computes 1U..6U unit bays.
 * - On hover: spring deploys side solar wings (2 hinged panels per side) & 4 UHF whip antennas.
 * - On pointermove: 3D attitude tilt follows cursor.
 * - On pointerdown/click: physically depresses 3D chassis and emits telemetry pulse ring.
 */
export const CubeSatButton = React.forwardRef<HTMLButtonElement, CubeSatButtonProps>(
  (
    {
      children,
      variant = "primary",
      showUnitBadge = false,
      fixedUnits,
      showDot = false,
      onUnitsChange,
      className = "",
      style,
      onClick,
      ...props
    },
    forwardedRef
  ) => {
    const btnRef = useRef<HTMLButtonElement | null>(null);
    const initialUnits =
      fixedUnits ??
      (typeof children === "string" && children.trim().length <= 4 ? 1 : 2);
    const [units, setUnits] = useState<number>(initialUnits);

    useEffect(() => {
      const buttonEl = btnRef.current;
      if (!buttonEl) return;

      const PAD_X = 92;
      const PAD_Y = 44;

      // Clean up previous SVG if any
      const existing = buttonEl.querySelector("svg.cubesat-btn-svg");
      if (existing) existing.remove();

      const svg = svgEl("svg", {
        class: "hl-svg cubesat-btn-svg",
        "aria-hidden": "true",
        style: `position:absolute; left:-${PAD_X}px; top:-${PAD_Y}px; width:calc(100% + ${
          PAD_X * 2
        }px); height:calc(100% + ${PAD_Y * 2}px); pointer-events:none; overflow:visible; z-index:0;`,
      });
      buttonEl.insertBefore(svg, buttonEl.firstChild);

      // SVG Layers
      const gWings = svgEl("g", {}, svg);
      const gAntennas = svgEl("g", {}, svg);
      const gChassis3D = svgEl("g", {}, svg);
      const gFrontFace = svgEl("g", {}, svg);
      const gRails = svgEl("g", {}, svg);

      // Solar Wings (left & right)
      const leftYoke = svgEl("path", { class: "hl-mid" }, gWings);
      const leftWingInner = svgEl("path", { class: "hl-plate" }, gWings);
      const leftWingOuter = svgEl("path", { class: "hl-plate" }, gWings);
      const leftWingGrid = svgEl("path", { class: "hl-lo" }, gWings);

      const rightYoke = svgEl("path", { class: "hl-mid" }, gWings);
      const rightWingInner = svgEl("path", { class: "hl-plate" }, gWings);
      const rightWingOuter = svgEl("path", { class: "hl-plate" }, gWings);
      const rightWingGrid = svgEl("path", { class: "hl-lo" }, gWings);

      // 4 Corner UHF Antennas + Pulse Wave
      const whips = Array.from({ length: 4 }, () => ({
        line: svgEl("path", { class: "hl-hi" }, gAntennas),
        tip: svgEl("circle", { r: "1.8", class: "hl-dot" }, gAntennas),
      }));
      const pulseWave = svgEl("path", { class: "hl-hi" }, gAntennas);

      // 3D Top Deck & Right Wall
      const topDeckPlate = svgEl("path", { class: "hl-plate" }, gChassis3D);
      const topDeckSolarCells = svgEl("path", { class: "hl-lo" }, gChassis3D);
      const rightWallPlate = svgEl("path", { class: "hl-plate" }, gChassis3D);
      const rightWallVents = svgEl("path", { class: "hl-lo" }, gChassis3D);

      // Front Face
      const frontPlate = svgEl("path", { class: "hl-plate" }, gFrontFace);
      const frontInnerFrame = svgEl("path", { class: "hl-lo" }, gFrontFace);
      const unitBaySeams = svgEl("path", { class: "hl-lo" }, gFrontFace);

      // CalPoly Rails & Fasteners
      const cornerRailsPath = svgEl("path", { class: "hl-hi" }, gRails);
      const cornerFasteners = Array.from({ length: 8 }, () =>
        svgEl("circle", { r: "1.35", class: "hl-dot-m" }, gRails)
      );

      // Springs
      const spHover = createSpring(0, 190, 19);
      const spPress = createSpring(0, 280, 22);
      const spTiltX = createSpring(0, 170, 19);
      const spTiltY = createSpring(0, 170, 19);
      const spOuterWing = createSpring(0, 150, 17);

      let width = Math.max(88, buttonEl.offsetWidth || (initialUnits === 1 ? 96 : 180));
      let height = Math.max(38, buttonEl.offsetHeight || 44);
      let pulseT = 0;
      let pulseActive = false;
      let rafId: number | null = null;
      let lastT = performance.now();

      function computeUnits(w: number): number {
        if (fixedUnits && fixedUnits >= 1 && fixedUnits <= 6) return fixedUnits;
        return clamp(Math.round(w / 76), 1, 6);
      }

      function render() {
        const W = width;
        const H = height;
        const totalW = W + PAD_X * 2;
        const totalH = H + PAD_Y * 2;
        svg.setAttribute("viewBox", `0 0 ${totalW} ${totalH}`);

        const ox = PAD_X;
        const oy = PAD_Y;
        const currentUnits = computeUnits(W);

        const h = clamp(spHover.x, 0, 1.25);
        const hOuter = clamp(spOuterWing.x, 0, 1.25);
        const press = clamp(spPress.x, 0, 1.2);

        // Front face shifts back-right when pressed
        const baseDx = 10 + h * 2.5;
        const baseDy = -9 - h * 2.5;
        const pressShiftX = press * 6.5;
        const pressShiftY = -press * 6;

        const fx0 = r2(ox + pressShiftX + spTiltX.x * 2.2);
        const fy0 = r2(oy + pressShiftY + spTiltY.x * 2.2);
        const fx1 = r2(fx0 + W);
        const fy1 = r2(fy0 + H);

        const dx = r2(baseDx - press * 6 + spTiltX.x * 3);
        const dy = r2(baseDy + press * 5.5 + spTiltY.x * 2.5);

        // 1. Front Face Plate (chamfered)
        const ch = 4.5;
        const frontD = [
          `M ${fx0 + ch} ${fy0}`,
          `L ${fx1 - ch} ${fy0}`,
          `L ${fx1} ${fy0 + ch}`,
          `L ${fx1} ${fy1 - ch}`,
          `L ${fx1 - ch} ${fy1}`,
          `L ${fx0 + ch} ${fy1}`,
          `L ${fx0} ${fy1 - ch}`,
          `L ${fx0} ${fy0 + ch}`,
          "Z",
        ].join(" ");
        frontPlate.setAttribute("d", frontD);
        frontPlate.setAttribute("class", h > 0.25 ? "hl-plate hl-hi" : "hl-plate");

        // Inner bezel frame
        const ins = 3.5;
        frontInnerFrame.setAttribute(
          "d",
          `M ${fx0 + ins} ${fy0 + ins} L ${fx1 - ins} ${fy0 + ins} L ${fx1 - ins} ${fy1 - ins} L ${
            fx0 + ins
          } ${fy1 - ins} Z`
        );

        // 2. 3D Isometric Top Deck & Right Wall
        const topDeckD = [
          `M ${fx0 + ch} ${fy0}`,
          `L ${fx0 + ch + dx} ${fy0 + dy}`,
          `L ${fx1 - ch + dx} ${fy0 + dy}`,
          `L ${fx1 - ch} ${fy0}`,
          "Z",
        ].join(" ");
        topDeckPlate.setAttribute("d", topDeckD);
        topDeckPlate.setAttribute("class", h > 0.25 ? "hl-plate hl-hi" : "hl-plate");

        const rightWallD = [
          `M ${fx1} ${fy0 + ch}`,
          `L ${fx1 + dx} ${fy0 + ch + dy}`,
          `L ${fx1 + dx} ${fy1 - ch + dy}`,
          `L ${fx1} ${fy1 - ch}`,
          "Z",
        ].join(" ");
        rightWallPlate.setAttribute("d", rightWallD);
        rightWallPlate.setAttribute("class", h > 0.25 ? "hl-plate hl-hi" : "hl-plate");

        // 3. Unit Bay Seams & Top Deck Solar Cells
        const seamCmds: string[] = [];
        const solarCmds: string[] = [];
        const bayW = W / currentUnits;
        for (let i = 1; i < currentUnits; i++) {
          const bx = r2(fx0 + i * bayW);
          seamCmds.push(`M ${bx} ${fy0} L ${bx} ${fy0 + 5.5}`);
          seamCmds.push(`M ${bx} ${fy1 - 5.5} L ${bx} ${fy1}`);
          seamCmds.push(`M ${bx} ${fy0} L ${bx + dx} ${fy0 + dy}`);
        }
        unitBaySeams.setAttribute("d", seamCmds.join(" "));

        for (let i = 0; i < currentUnits; i++) {
          const sxA = r2(fx0 + i * bayW + 6);
          const sxB = r2(fx0 + (i + 1) * bayW - 6);
          if (sxB > sxA + 8) {
            solarCmds.push(
              `M ${r2(sxA + dx * 0.25)} ${r2(fy0 + dy * 0.25)} ` +
                `L ${r2(sxA + dx * 0.8)} ${r2(fy0 + dy * 0.8)} ` +
                `L ${r2(sxB + dx * 0.8)} ${r2(fy0 + dy * 0.8)} ` +
                `L ${r2(sxB + dx * 0.25)} ${r2(fy0 + dy * 0.25)} Z`
            );
          }
        }
        topDeckSolarCells.setAttribute("d", solarCmds.join(" "));

        // Right wall louvers
        const ventCmds: string[] = [];
        for (let k = 1; k <= 3; k++) {
          const vy = r2(fy0 + (H * k) / 4);
          ventCmds.push(
            `M ${r2(fx1 + dx * 0.25)} ${r2(vy + dy * 0.25)} L ${r2(fx1 + dx * 0.8)} ${r2(
              vy + dy * 0.8
            )}`
          );
        }
        rightWallVents.setAttribute("d", ventCmds.join(" "));

        // 4. Rails & Fastener Dots
        const rOut = 5.5;
        const rLen = 9;
        const railCmds = [
          `M ${fx0 - rOut} ${fy0 + rLen} L ${fx0 - rOut} ${fy0 - 2} L ${fx0 + rLen} ${fy0 - 2}`,
          `M ${fx0 - rOut} ${fy1 - rLen} L ${fx0 - rOut} ${fy1 + 2} L ${fx0 + rLen} ${fy1 + 2}`,
          `M ${fx1 - rLen + dx} ${fy0 + dy - 2} L ${fx1 + dx + rOut} ${fy0 + dy - 2} L ${
            fx1 + dx + rOut
          } ${fy0 + dy + rLen}`,
          `M ${fx1 + dx + rOut} ${fy1 + dy - rLen} L ${fx1 + dx + rOut} ${fy1 + dy + 2} L ${fx1} ${
            fy1 + 2
          }`,
        ];
        cornerRailsPath.setAttribute("d", railCmds.join(" "));

        const fastenerCoords = [
          [fx0 + 7, fy0 + 6],
          [fx0 + 7, fy1 - 6],
          [fx1 - 7, fy0 + 6],
          [fx1 - 7, fy1 - 6],
          [fx0 + W * 0.5, fy0 + 3.5],
          [fx0 + W * 0.5, fy1 - 3.5],
          [fx1 + dx * 0.55, fy0 + dy * 0.55 + 5],
          [fx1 + dx * 0.55, fy1 + dy * 0.55 - 5],
        ];
        fastenerCoords.forEach(([cx, cy], idx) => {
          cornerFasteners[idx].setAttribute("cx", String(r2(cx)));
          cornerFasteners[idx].setAttribute("cy", String(r2(cy)));
          cornerFasteners[idx].setAttribute("class", h > 0.4 && idx < 4 ? "hl-dot" : "hl-dot-m");
        });

        // 5. Unfolding Wings
        const wingSpan1 = r2(lerp(0, 34, h));
        const wingSpan2 = r2(lerp(0, 32, hOuter));
        const wingH = r2(H * 0.72);
        const wy0 = r2(fy0 + (H - wingH) / 2);
        const wy1 = r2(wy0 + wingH);
        const slant = r2(lerp(0, -6, h));

        if (wingSpan1 > 1.5) {
          const lx0 = fx0 - 5;
          const lx1 = r2(lx0 - wingSpan1);
          const lx2 = r2(lx1 - wingSpan2);
          leftYoke.setAttribute(
            "d",
            `M ${fx0} ${r2(wy0 + 6)} L ${lx0} ${r2(wy0 + 6)} M ${fx0} ${r2(wy1 - 6)} L ${lx0} ${r2(
              wy1 - 6
            )}`
          );
          leftWingInner.setAttribute(
            "d",
            `M ${lx0} ${wy0} L ${lx1} ${r2(wy0 + slant)} L ${lx1} ${r2(wy1 + slant)} L ${lx0} ${wy1} Z`
          );
          leftWingInner.setAttribute("class", "hl-plate hl-hi");

          if (wingSpan2 > 1.5) {
            leftWingOuter.setAttribute(
              "d",
              `M ${lx1 - 2} ${r2(wy0 + slant)} L ${lx2} ${r2(wy0 + slant * 1.8)} L ${lx2} ${r2(
                wy1 + slant * 1.8
              )} L ${lx1 - 2} ${r2(wy1 + slant)} Z`
            );
            leftWingOuter.setAttribute("class", "hl-plate hl-hi");
          } else {
            leftWingOuter.setAttribute("d", "");
          }

          const lMidY = r2((wy0 + wy1) / 2 + slant * 0.5);
          leftWingGrid.setAttribute(
            "d",
            `M ${lx0 - 3} ${lMidY} L ${lx2 + 3} ${r2(lMidY + slant * 0.6)}`
          );

          // Right wing
          const rx0 = r2(fx1 + dx + 5);
          const ry0 = r2(wy0 + dy * 0.6);
          const ry1 = r2(wy1 + dy * 0.6);
          const rx1 = r2(rx0 + wingSpan1);
          const rx2 = r2(rx1 + wingSpan2);

          rightYoke.setAttribute(
            "d",
            `M ${r2(fx1 + dx)} ${r2(ry0 + 6)} L ${rx0} ${r2(ry0 + 6)} M ${r2(fx1 + dx)} ${r2(
              ry1 - 6
            )} L ${rx0} ${r2(ry1 - 6)}`
          );
          rightWingInner.setAttribute(
            "d",
            `M ${rx0} ${ry0} L ${rx1} ${r2(ry0 - slant)} L ${rx1} ${r2(ry1 - slant)} L ${rx0} ${ry1} Z`
          );
          rightWingInner.setAttribute("class", "hl-plate hl-hi");

          if (wingSpan2 > 1.5) {
            rightWingOuter.setAttribute(
              "d",
              `M ${rx1 + 2} ${r2(ry0 - slant)} L ${rx2} ${r2(ry0 - slant * 1.8)} L ${rx2} ${r2(
                ry1 - slant * 1.8
              )} L ${rx1 + 2} ${r2(ry1 - slant)} Z`
            );
            rightWingOuter.setAttribute("class", "hl-plate hl-hi");
          } else {
            rightWingOuter.setAttribute("d", "");
          }

          const rMidY = r2((ry0 + ry1) / 2 - slant * 0.5);
          rightWingGrid.setAttribute(
            "d",
            `M ${rx0 + 3} ${rMidY} L ${rx2 - 3} ${r2(rMidY - slant * 0.6)}`
          );
        } else {
          leftYoke.setAttribute("d", "");
          leftWingInner.setAttribute("d", "");
          leftWingOuter.setAttribute("d", "");
          leftWingGrid.setAttribute("d", "");
          rightYoke.setAttribute("d", "");
          rightWingInner.setAttribute("d", "");
          rightWingOuter.setAttribute("d", "");
          rightWingGrid.setAttribute("d", "");
        }

        // 6. Corner UHF Antennas
        const whipLen = lerp(0, 22, h);
        const corners = [
          { x: fx0 + 4, y: fy0, vx: -0.75, vy: -0.9 },
          { x: fx1 + dx - 4, y: fy0 + dy, vx: 0.75, vy: -0.9 },
          { x: fx0 + 4, y: fy1, vx: -0.75, vy: 0.85 },
          { x: fx1 - 4, y: fy1, vx: 0.75, vy: 0.85 },
        ];
        corners.forEach((c, idx) => {
          if (whipLen > 1) {
            const tx = r2(c.x + c.vx * whipLen);
            const ty = r2(c.y + c.vy * whipLen);
            whips[idx].line.setAttribute("d", `M ${r2(c.x)} ${r2(c.y)} L ${tx} ${ty}`);
            whips[idx].tip.setAttribute("cx", String(tx));
            whips[idx].tip.setAttribute("cy", String(ty));
            whips[idx].tip.setAttribute("r", "1.7");
          } else {
            whips[idx].line.setAttribute("d", "");
            whips[idx].tip.setAttribute("r", "0");
          }
        });

        // 7. Click Pulse Ring
        if (pulseActive) {
          const padExpand = lerp(2, 26, pulseT);
          const px0 = r2(fx0 - padExpand);
          const py0 = r2(fy0 - padExpand * 0.65);
          const px1 = r2(fx1 + dx + padExpand);
          const py1 = r2(fy1 + padExpand * 0.65);
          pulseWave.setAttribute(
            "d",
            `M ${px0} ${py0} L ${px1} ${py0} L ${px1} ${py1} L ${px0} ${py1} Z`
          );
          pulseWave.setAttribute("class", pulseT < 0.5 ? "hl-hi" : "hl-mid");
        } else {
          pulseWave.setAttribute("d", "");
        }
      }

      function step(now: number) {
        const dt = Math.min((now - lastT) / 1000, 0.05);
        lastT = now;
        let moving = false;

        spOuterWing.t = spHover.x > 0.35 ? spHover.t : 0;

        if (stepSpring(spHover, dt)) moving = true;
        if (stepSpring(spOuterWing, dt)) moving = true;
        if (stepSpring(spPress, dt)) moving = true;
        if (stepSpring(spTiltX, dt)) moving = true;
        if (stepSpring(spTiltY, dt)) moving = true;

        if (pulseActive) {
          pulseT += dt * 2.1;
          if (pulseT >= 1) {
            pulseT = 0;
            pulseActive = false;
          } else {
            moving = true;
          }
        }

        render();
        rafId = moving ? requestAnimationFrame(step) : null;
      }

      function wake() {
        if (!rafId) {
          lastT = performance.now();
          rafId = requestAnimationFrame(step);
        }
      }

      function measureAndSync() {
        const rect = buttonEl.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          width = Math.round(rect.width);
          height = Math.round(rect.height);
        }
        const u = computeUnits(width);
        setUnits(u);
        onUnitsChange?.(u);
        render();
      }

      const ro = typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => measureAndSync())
        : null;
      if (ro) ro.observe(buttonEl);

      const onPointerEnter = () => {
        spHover.t = 1;
        wake();
      };
      const onPointerMove = (e: PointerEvent) => {
        const rect = buttonEl.getBoundingClientRect();
        spTiltX.t = clamp(((e.clientX - rect.left) / rect.width - 0.5) * 2, -1, 1);
        spTiltY.t = clamp(((e.clientY - rect.top) / rect.height - 0.5) * 2, -1, 1);
        spHover.t = 1;
        wake();
      };
      const onPointerLeave = () => {
        spHover.t = 0;
        spPress.t = 0;
        spTiltX.t = 0;
        spTiltY.t = 0;
        wake();
      };
      const onPointerDown = () => {
        spPress.t = 1;
        wake();
      };
      const onPointerUp = () => {
        spPress.t = 0;
        wake();
      };

      buttonEl.addEventListener("pointerenter", onPointerEnter);
      buttonEl.addEventListener("pointermove", onPointerMove);
      buttonEl.addEventListener("pointerleave", onPointerLeave);
      buttonEl.addEventListener("pointerdown", onPointerDown);
      buttonEl.addEventListener("pointerup", onPointerUp);

      measureAndSync();

      return () => {
        if (ro) ro.disconnect();
        if (rafId) cancelAnimationFrame(rafId);
        buttonEl.removeEventListener("pointerenter", onPointerEnter);
        buttonEl.removeEventListener("pointermove", onPointerMove);
        buttonEl.removeEventListener("pointerleave", onPointerLeave);
        buttonEl.removeEventListener("pointerdown", onPointerDown);
        buttonEl.removeEventListener("pointerup", onPointerUp);
        svg.remove();
      };
    }, [fixedUnits, onUnitsChange]);

    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
      onClick?.(e);
    };

    const variantClasses =
      variant === "primary" ? "cubesat-btn-primary" : "cubesat-btn-secondary";

    return (
      <button
        ref={(el) => {
          btnRef.current = el;
          if (typeof forwardedRef === "function") forwardedRef(el);
          else if (forwardedRef) forwardedRef.current = el;
        }}
        type="button"
        className={`cubesat-btn ${variantClasses} relative inline-flex items-center justify-center select-none cursor-pointer focus:outline-none group ${className}`}
        style={{
          background: "transparent",
          border: "none",
          padding: "13px 22px",
          ...style,
        }}
        onClick={handleClick}
        {...props}
      >
        <span className="relative z-10 inline-flex items-center gap-2 pointer-events-none whitespace-nowrap font-semibold text-xs sm:text-sm">
          {showDot && (
            <span
              className={`w-1.5 h-1.5 rounded-full transition-transform group-hover:scale-125 ${
                variant === "primary"
                  ? "bg-white"
                  : "bg-lms-cta dark:bg-lms-accent"
              }`}
            />
          )}
          {children}
          {showUnitBadge && (
            <span
              className={`font-mono text-[10px] tracking-wider px-1.5 py-0.5 rounded border transition-opacity ${
                variant === "primary"
                  ? "border-white/30 text-white/80"
                  : "border-lms-cta-border dark:border-lms-accent-border text-lms-cta dark:text-lms-accent"
              }`}
            >
              {units}U
            </span>
          )}
        </span>
      </button>
    );
  }
);

CubeSatButton.displayName = "CubeSatButton";
