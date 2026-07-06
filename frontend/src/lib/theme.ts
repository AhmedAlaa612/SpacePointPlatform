import type { CSSProperties } from "react";

/** Shared glass-panel surface treatment used throughout the reference app's base.html. */
export const GLASS = "bg-[rgba(26,15,38,0.7)] backdrop-blur-xl border border-white/5";

/** base.html's global body styling: bg color + two radial glows + a tiled stardust texture.
 * Applies to every page rendered on top of the reference app's shared layout (public
 * marketing pages, the apply flow, and the authenticated applicant shell). */
export const BODY_BACKGROUND: CSSProperties = {
  backgroundColor: "#05030A",
  backgroundImage:
    "url('https://www.transparenttextures.com/patterns/stardust.png'), " +
    "radial-gradient(circle at 15% 50%, rgba(167,125,255,0.06) 0%, transparent 50%), " +
    "radial-gradient(circle at 85% 30%, rgba(35,17,52,0.4) 0%, transparent 50%)",
  color: "#E2E8F0",
};
