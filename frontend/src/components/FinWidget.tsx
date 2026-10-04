import { useEffect } from "react";

import { fetchChatIdentity, fetchSupportConfig } from "@/api/lms";
import { useAuth } from "@/context/AuthContext";
import { boot, isFinEnabled, shutdown } from "@/lib/fin";

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
 * Three things that look incidental and are not:
 *
 * - **Waits for `loading`.** `AuthContext` resolves the user asynchronously,
 *   so booting on mount would open an anonymous conversation and then throw
 *   it away a moment later when the user arrives — a launcher that flickers
 *   and a stray contact in Intercom for every page load.
 * - **Falls back to an anonymous boot if the identity call fails.** A 503
 *   (no `INTERCOM_IDENTITY_SECRET` configured) or a network blip degrades to
 *   exactly the pre-identity behaviour rather than costing the student their
 *   support channel.
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
          return;
        }
      } catch {
        // If config endpoint blips, proceed to attempt boot
      }

      if (!userId) {
        boot();
        return;
      }
      try {
        const identity = await fetchChatIdentity();
        // The user changed (or we unmounted) while the request was in
        // flight — booting now would identify the wrong person.
        if (cancelled) return;
        // Only the token. The rest of the payload is already inside it as
        // signed claims, and sending unsigned copies alongside gets the
        // whole boot rejected — see `FinBootPayload`.
        boot({ intercom_user_jwt: identity.intercom_user_jwt });
      } catch {
        if (cancelled) return;
        boot();
      }
    }

    void start();

    return () => {
      cancelled = true;
      shutdown();
    };
  }, [userId, loading]);

  return null;
}
