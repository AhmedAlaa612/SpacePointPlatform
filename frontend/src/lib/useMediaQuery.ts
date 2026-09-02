import { useEffect, useState } from "react";

/** SSR-safe `matchMedia` subscription. Used by the Roadmap board to pick
 * between its desktop (serpentine grid) and mobile (alternating column)
 * tile-field layouts — those are structurally different DOM shapes per
 * the design spec, not a single reflowing flex container, so the board
 * renders one or the other rather than both at once. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => (typeof window !== "undefined" ? window.matchMedia(query).matches : false));

  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}
