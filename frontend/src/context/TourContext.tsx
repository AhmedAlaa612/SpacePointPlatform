import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useLocation, useNavigate } from "@tanstack/react-router";
import { EVENTS, STATUS, useJoyride, type EventData, type Step } from "react-joyride";
import { useAuth } from "@/context/AuthContext";
import { SpacePointTourCard } from "@/components/ui/SpacePointTourCard";
import {
  findVisibleTarget,
  resolveActionGuides,
  resolveCandidateSteps,
  waitForVisibleTarget,
  type TourActionGuide,
  type TourStepDef,
} from "@/lib/tours";

interface TourContextValue {
  /** Start or replay the full tutorial for the current role & surface. */
  startTour: () => void;
  /** Run any custom multi-page or in-page action walkthrough on demand. */
  startCustomTour: (customSteps: TourStepDef[]) => void;
  /** Return the live action guides available right now for the active role & surface. */
  getAvailableActions: () => TourActionGuide[];
  /** Whether a tour is currently running. */
  isRunning: boolean;
}

const TourContext = createContext<TourContextValue | undefined>(undefined);

const STORAGE_PREFIX = "sp_tour_seen_v1_";

function getSeenSteps(userId: string): Set<string> {
  try {
    const raw = localStorage.getItem(`${STORAGE_PREFIX}${userId}`);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? new Set<string>(parsed) : new Set();
  } catch {
    return new Set();
  }
}

function markStepsSeen(userId: string, stepIds: string[]): void {
  if (!stepIds.length) return;
  try {
    const existing = getSeenSteps(userId);
    stepIds.forEach((id) => existing.add(id));
    localStorage.setItem(`${STORAGE_PREFIX}${userId}`, JSON.stringify(Array.from(existing)));
  } catch {
    // Ignore storage quota errors
  }
}

export function TourProvider({
  surface,
  children,
}: {
  surface: "learn" | "applicant" | "portal";
  children: ReactNode;
}) {
  const { user, activeRole } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [activeDefs, setActiveDefs] = useState<TourStepDef[]>([]);
  const [run, setRun] = useState(false);
  const activeIdsRef = useRef<string[]>([]);

  const joyrideSteps: Step[] = useMemo(
    () =>
      activeDefs.map((def) => ({
        id: def.id,
        target: () => findVisibleTarget(def.selector) ?? document.body,
        title: def.title,
        content: def.content,
        placement: def.placement ?? "auto",
        skipBeacon: true,
        isFixed: true,
        blockTargetInteraction: def.allowInteraction === false,
        targetWaitTimeout: 3500,
        before: async () => {
          if (def.route && window.location.pathname !== def.route) {
            await navigate({ to: def.route as never });
          }
          if (def.beforeStep) {
            await def.beforeStep();
          }
          if (def.route || def.beforeStep) {
            await waitForVisibleTarget(def.selector, 3500);
          }
        },
      })),
    [activeDefs, navigate],
  );

  const handleEvent = useCallback(
    (data: EventData) => {
      const { status, type } = data;
      if (
        type === EVENTS.TOUR_END ||
        status === STATUS.FINISHED ||
        status === STATUS.SKIPPED
      ) {
        if (user?.id && activeIdsRef.current.length > 0) {
          markStepsSeen(user.id, activeIdsRef.current);
        }
        setRun(false);
      }
    },
    [user?.id],
  );

  const { controls, state, Tour } = useJoyride({
    steps: joyrideSteps,
    run,
    continuous: true,
    scrollToFirstStep: true,
    tooltipComponent: SpacePointTourCard,
    onEvent: handleEvent,
    options: {
      buttons: ["back", "close", "primary", "skip"],
      closeButtonAction: "skip",
      overlayClickAction: false,
      skipBeacon: true,
      primaryColor: "#38bdf8",
      overlayColor: "rgba(3, 7, 18, 0.72)",
      spotlightRadius: 12,
      spotlightPadding: 6,
      zIndex: 1000,
    },
  });

  // When a step has `advanceOnClick: true`, clicking the highlighted DOM element
  // performs its real click action AND automatically advances the tour to the next step!
  useEffect(() => {
    if (!run) return;
    const currentDef = activeDefs[state.index];
    if (!currentDef?.advanceOnClick) return;
    const targetEl = findVisibleTarget(currentDef.selector);
    if (!targetEl) return;

    const onTargetClick = () => {
      window.setTimeout(() => {
        controls.next();
      }, 150);
    };

    targetEl.addEventListener("click", onTargetClick, { once: true });
    return () => {
      targetEl.removeEventListener("click", onTargetClick);
    };
  }, [run, activeDefs, state.index, controls]);

  const getAvailableActions = useCallback(
    () => resolveActionGuides(surface, activeRole),
    [surface, activeRole],
  );

  // Start or replay the full tutorial manually when the user clicks "Tutorial"
  const startTour = useCallback(() => {
    const candidates = resolveCandidateSteps(surface, activeRole);
    if (candidates.length === 0) return;
    activeIdsRef.current = candidates.map((c) => c.id);
    setActiveDefs(candidates);
    setRun(true);
    setTimeout(() => {
      controls.reset(true);
    }, 50);
  }, [surface, activeRole, controls]);

  // Start any custom multi-page or in-page action tour
  const startCustomTour = useCallback(
    (customSteps: TourStepDef[]) => {
      if (customSteps.length === 0) return;
      activeIdsRef.current = customSteps.map((c) => c.id);
      setActiveDefs(customSteps);
      setRun(true);
      setTimeout(() => {
        controls.reset(true);
      }, 50);
    },
    [controls],
  );

  // Auto-start unseen steps (full onboarding on first visit, or mini-spotlight
  // when a previously hidden tab is unlocked for this user).
  useEffect(() => {
    if (!user?.id) return;
    // Don't auto-pop on full-screen player / live quiz gameplay routes
    if (
      pathname.startsWith("/learn/courses/") ||
      pathname.startsWith("/learn/games/") ||
      pathname.startsWith("/learn/login") ||
      pathname.startsWith("/learn/signup")
    ) {
      return;
    }

    const timer = window.setTimeout(() => {
      if (run) return;
      const candidates = resolveCandidateSteps(surface, activeRole);
      if (candidates.length === 0) return;

      const seen = getSeenSteps(user.id);
      const unseen = candidates.filter((c) => !seen.has(c.id));
      if (unseen.length === 0) return;

      // Avoid running a tour that ONLY consists of the generic welcome/replay buttons
      // if the user already completed the main tour previously.
      const hasSeenAny = seen.size > 0;
      const stepsToRun = hasSeenAny
        ? unseen.filter(
            (s) =>
              !s.id.endsWith("-welcome") &&
              !s.id.endsWith("-tutorial-btn") &&
              !s.id.endsWith("-replay-tutorial"),
          )
        : unseen;

      if (stepsToRun.length === 0) {
        markStepsSeen(
          user.id,
          unseen.map((u) => u.id),
        );
        return;
      }

      activeIdsRef.current = unseen.map((u) => u.id);
      setActiveDefs(stepsToRun);
      setRun(true);
    }, 700);

    return () => window.clearTimeout(timer);
  }, [user?.id, surface, activeRole, pathname, run]);

  const value = useMemo<TourContextValue>(
    () => ({
      startTour,
      startCustomTour,
      getAvailableActions,
      isRunning: run,
    }),
    [startTour, startCustomTour, getAvailableActions, run],
  );

  return (
    <TourContext.Provider value={value}>
      {children}
      {Tour}
    </TourContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTour(): TourContextValue {
  const ctx = useContext(TourContext);
  if (!ctx) {
    return {
      startTour: () => {},
      startCustomTour: () => {},
      getAvailableActions: () => [],
      isRunning: false,
    };
  }
  return ctx;
}
