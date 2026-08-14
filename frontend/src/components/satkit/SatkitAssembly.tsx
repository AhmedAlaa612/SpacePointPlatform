import type * as React from "react";
import "./satkit-assembly.js";

/** Registers `<satkit-assembly>` (a plain custom element, no framework
 * dependency) and gives it a typed JSX wrapper. Assets live in
 * `public/assets/satkit/` (manifest.json + frames/), served as-is by Vite —
 * see that folder's README for attributes and how to change the cut.
 *
 * React 19's @types/react moved the JSX namespace under `React.JSX` —
 * augmenting the old bare global `JSX` namespace here silently doesn't
 * merge into what TSX actually resolves against, so this has to be a
 * module augmentation of "react" itself, not `declare global`. */
declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "satkit-assembly": React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
        base?: string;
        manifest?: string;
        fps?: string | number;
        hold?: string | number;
        height?: string | number;
        accent?: string;
        autoplay?: string | boolean;
        loop?: string | boolean;
        controls?: string | boolean;
        zoom?: string | number;
      };
    }
  }
}

export function SatkitAssembly(props: {
  className?: string;
  fps?: number;
  hold?: number;
  height?: number | string;
  loop?: boolean;
  /** Show the scrub rail. Off by default — this is a hero centerpiece, not
   * a video player. */
  controls?: boolean;
  /** Scale past the normal contain-fit size, cropping in from the edges
   * instead of leaving empty space around the subject. */
  zoom?: number;
}) {
  const { className, fps = 5, hold = 2000, height = "100%", loop = false, controls = false, zoom = 1 } = props;
  return (
    <satkit-assembly
      className={className}
      base="/assets/satkit"
      fps={fps}
      hold={hold}
      height={height}
      loop={String(loop)}
      controls={String(controls)}
      zoom={zoom}
    />
  );
}
