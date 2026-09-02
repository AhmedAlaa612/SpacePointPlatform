import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

/** Lets RoadmapBoard (mounted deep under the Outlet) publish "N of M traces
 * live" up to LearnSidebar's progress panel (design spec §"Sidebar", the
 * "Board power" row) without either importing the other or reaching into
 * routing state neither owns. `null` outside of a board — the panel hides
 * itself entirely rather than showing a stale/zero reading. */
interface BoardProgress {
  liveCount: number;
  total: number;
  checkpointLabel?: string;
}

const BoardProgressContext = createContext<{
  progress: BoardProgress | null;
  setProgress: (p: BoardProgress | null) => void;
} | null>(null);

export function BoardProgressProvider({ children }: { children: ReactNode }) {
  const [progress, setProgress] = useState<BoardProgress | null>(null);
  const value = useMemo(() => ({ progress, setProgress }), [progress]);
  return <BoardProgressContext.Provider value={value}>{children}</BoardProgressContext.Provider>;
}

export function useBoardProgress() {
  const ctx = useContext(BoardProgressContext);
  if (!ctx) throw new Error("useBoardProgress must be used within BoardProgressProvider");
  return ctx;
}
