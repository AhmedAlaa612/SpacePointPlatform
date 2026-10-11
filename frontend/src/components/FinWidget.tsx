import { useEffect, useRef } from "react";

import { useParams } from "@tanstack/react-router";

import { fetchChatIdentity, fetchSupportConfig } from "@/api/lms";
import { useAuth } from "@/context/AuthContext";
import { boot, isFinEnabled, shutdown, update } from "@/lib/fin";

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
 *   `quiz/$itemId` child) the identity is fetched with that assignment, so
 *   `program`/`cohort`/`team` describe the board being viewed. Navigating
 *   between boards re-fetches and `update()`s — preserving the open
 *   conversation — while landing/catalog pages fall back to the latest
 *   assignment. An unknown or foreign assignment id is ignored server-side.
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
  // Present only on the checklist board + quiz routes; undefined everywhere
  // else (landing, catalog, courses, missions, …) — that is the fallback.
  const { assignmentId } = useParams({ strict: false }) as { assignmentId?: string };
  // Tracks whether this mount already booted, so board-to-board navigation
  // refreshes via `update()` (conversation preserved) instead of `boot()`.
  const bootedRef = useRef(false);

  useEffect(() => {
    if (!isFinEnabled()) return;
    // Don't boot until we know whether anyone is signed in.
    if (loading) return;

    let cancelled = false;

    async function start() {
      // Check admin toggle before booting Fin for students
      try {
        const config = await fetchSupportConfig();
        if (cancelled) return;
        if (!config.fin_enabled) {
          shutdown();
          bootedRef.current = false;
          return;
        }
      } catch {
        // If config endpoint blips, proceed to attempt boot
      }

      if (!userId) {
        boot();
        bootedRef.current = true;
        return;
      }
      try {
        const identity = await fetchChatIdentity(assignmentId);
        // The user navigated away (or we unmounted) while the request was
        // in flight — applying now would tag the wrong board.
        if (cancelled) return;
        // Only the token. The rest of the payload is already inside it as
        // signed claims, and sending unsigned copies alongside gets the
        // whole boot rejected — see `FinBootPayload`.
        const payload = { intercom_user_jwt: identity.intercom_user_jwt };
        if (bootedRef.current) {
          update(payload);
        } else {
          boot(payload);
          bootedRef.current = true;
        }
      } catch {
        if (cancelled) return;
        if (!bootedRef.current) {
          boot();
          bootedRef.current = true;
        }
      }
    }

    void start();

    return () => {
      cancelled = true;
    };
  }, [userId, loading, assignmentId]);

  // Full teardown on unmount / account switch only — not on board-to-board
  // navigation (that path uses `update()` above and must keep the chat).
  // `userId` in the deps remounts this cleanup when the account changes.
  useEffect(() => {
    return () => {
      bootedRef.current = false;
      shutdown();
    };
  }, [userId]);

  return null;
}
