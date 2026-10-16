import { useEffect, useRef } from "react";

import { useParams, useSearch } from "@tanstack/react-router";

import { fetchChatIdentity, fetchSupportConfig } from "@/api/lms";
import { useAuth } from "@/context/AuthContext";
import { boot, isFinEnabled, shutdown, update } from "@/lib/fin";

// Refresh the signed Intercom JWT every 45 minutes (and on tab wakeup after
// 15+ minutes) so long study sessions or sleeping laptops never hit an
// expired token on Intercom re-pings.
const JWT_REFRESH_INTERVAL_MS = 45 * 60 * 1000;
const VISIBILITY_REFRESH_THRESHOLD_MS = 15 * 60 * 1000;

/**
 * Mounts the Fin (Intercom) support messenger. Renders nothing — the widget
 * is a floating launcher the third-party script injects into `<body>`, not
 * part of our tree.
 *
 * Mounted in `pages/learn/LearnShell.tsx`, deliberately **not** in `main.tsx`:
 * this is a student support assistant trained on the competition FAQ, and the
 * portal, judge and applicant surfaces have no business showing it. Open to
 * any authenticated account on `/learn/*`, including staff taking LMS
 * courses, matching how `/lms/my-courses` is gated (see the student router's
 * docstring).
 *
 * Boots with a verified identity when there is one, anonymously otherwise.
 * Four things that look incidental and are not:
 *
 * - **Waits for `loading`.** `AuthContext` resolves the user asynchronously,
 *   so booting on mount would open an anonymous conversation and then throw
 *   it away a moment later when the user arrives — a launcher that flickers
 *   and a stray contact in Intercom for every page load.
 * - **Falls back to an anonymous boot if the identity call fails.** A 503
 *   (no `INTERCOM_IDENTITY_SECRET` configured) or a network blip degrades to
 *   exactly the pre-identity behaviour rather than costing the student their
 *   support channel.
 * - **Cohort-page awareness.** On `/learn/checklists/$assignmentId` (and its
 *   `quiz/$itemId` child), or when following a board tile into a course or
 *   design mission (`?program=<assignmentId>`), the identity is fetched with
 *   that assignment, so `program`/`cohort`/`team` describe the board being
 *   viewed. Navigating between boards re-fetches and `update()`s — preserving
 *   the open conversation — while landing/catalog pages fall back to the
 *   latest assignment. An unknown or foreign assignment id is ignored
 *   server-side.
 * - **`shutdown()` on cleanup.** Intercom keeps a conversation in a cookie,
 *   so without this the next person to sign in on a shared school machine
 *   inherits the previous student's chat history. See `lib/fin.ts::shutdown`.
 *
 * Renders as a no-op with no network calls when `VITE_INTERCOM_APP_ID` is
 * unset, or when disabled by an administrator via system settings.
 */
export function FinWidget() {
  const { user, loading } = useAuth();
  const userId = user?.id ?? null;
  // Present on the checklist board + quiz routes, or carried via `?program=`
  // when a student opens a course or design mission from their board.
  const { assignmentId } = useParams({ strict: false }) as { assignmentId?: string };
  const { program: searchProgram } = useSearch({ strict: false }) as { program?: string };
  const effectiveAssignmentId = assignmentId || searchProgram || undefined;

  // Tracks whether this mount already booted, so board-to-board navigation
  // refreshes via `update()` (conversation preserved) instead of `boot()`.
  const bootedRef = useRef(false);
  const lastFetchedAtRef = useRef(0);
  const prevUserIdRef = useRef<string | null>(userId);

  // Only tear down the session when a previously logged-in user logs out or
  // switches to a different account — NEVER on the initial `null -> userId`
  // transition when `AuthContext` finishes resolving `/auth/me` on page load.
  useEffect(() => {
    const prevUserId = prevUserIdRef.current;
    prevUserIdRef.current = userId;
    if (prevUserId !== null && prevUserId !== userId) {
      bootedRef.current = false;
      shutdown();
    }
  }, [userId]);

  useEffect(() => {
    if (!isFinEnabled()) return;

    let cancelled = false;
    let loadingFallbackTimer: number | undefined;

    // If `AuthContext` is still resolving `/auth/me`, wait briefly so we don't
    // double-boot unnecessarily; but if `/auth/me` takes >2s on a slow
    // connection, boot anonymously right away so the launcher is never hidden.
    if (loading) {
      loadingFallbackTimer = window.setTimeout(() => {
        if (!cancelled && !bootedRef.current) {
          boot();
          bootedRef.current = true;
        }
      }, 2000);
      return () => {
        cancelled = true;
        if (loadingFallbackTimer !== undefined) {
          window.clearTimeout(loadingFallbackTimer);
        }
      };
    }

    async function syncIdentity() {
      const [configResult, identityResult] = await Promise.allSettled([
        fetchSupportConfig(),
        userId ? fetchChatIdentity(effectiveAssignmentId) : Promise.resolve(null),
      ]);

      if (cancelled) return;

      // Check admin toggle before booting Fin for students
      if (configResult.status === "fulfilled" && !configResult.value.fin_enabled) {
        shutdown();
        bootedRef.current = false;
        return;
      }

      if (!userId) {
        if (bootedRef.current) {
          update();
        } else {
          boot();
          bootedRef.current = true;
        }
        lastFetchedAtRef.current = Date.now();
        return;
      }

      if (identityResult.status === "fulfilled" && identityResult.value?.intercom_user_jwt) {
        // Only the token. The rest of the payload is already inside it as
        // signed claims, and sending unsigned copies alongside gets the
        // whole boot rejected — see `FinBootPayload`.
        const payload = { intercom_user_jwt: identityResult.value.intercom_user_jwt };
        if (bootedRef.current) {
          update(payload);
        } else {
          boot(payload);
          bootedRef.current = true;
        }
        lastFetchedAtRef.current = Date.now();
      } else {
        // Degrade gracefully to anonymous boot if `/lms/support/chat-identity`
        // fails (503, network blip, expired token) so Fin stays visible.
        if (!bootedRef.current) {
          boot();
          bootedRef.current = true;
        }
      }
    }

    void syncIdentity();

    const intervalId = userId
      ? window.setInterval(() => {
          void syncIdentity();
        }, JWT_REFRESH_INTERVAL_MS)
      : undefined;

    function handleVisibilityChange() {
      if (
        document.visibilityState === "visible" &&
        Date.now() - lastFetchedAtRef.current >= VISIBILITY_REFRESH_THRESHOLD_MS
      ) {
        void syncIdentity();
      }
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      cancelled = true;
      if (loadingFallbackTimer !== undefined) window.clearTimeout(loadingFallbackTimer);
      if (intervalId !== undefined) window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [userId, loading, effectiveAssignmentId]);

  // Full teardown when leaving the `/learn/*` surface entirely. Navigating to
  // `/learn/login` or `/learn/signup` keeps the launcher alive.
  useEffect(() => {
    return () => {
      if (!window.location.pathname.startsWith("/learn")) {
        bootedRef.current = false;
        shutdown();
      }
    };
  }, []);

  return null;
}
