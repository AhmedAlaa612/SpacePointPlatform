import { useEffect } from "react";

import { useAuth } from "@/context/AuthContext";
import { boot, isFinEnabled, shutdown } from "@/lib/fin";

/**
 * Mounts the Fin (Intercom) support messenger. Renders nothing — the widget
 * is a floating launcher the third-party script injects into `<body>`, not
 * part of our tree.
 *
 * Mounted in `pages/learn/LearnShell.tsx`, deliberately **not** in `main.tsx`:
 * this is a student support assistant trained on the competition FAQ, and the
 * portal, judge and applicant surfaces have no business showing it. Phase 1
 * boots anonymously, so anyone on `/learn/*` — including staff taking LMS
 * courses, matching how `/lms/my-courses` is gated (see the student router's
 * docstring) — gets the same messenger.
 *
 * Keyed on the logged-in user id rather than booting once on mount: the
 * cleanup's `shutdown()` is what stops a signed-out student's conversation
 * carrying over to whoever signs in next on a shared machine. See
 * `lib/fin.ts::shutdown`.
 *
 * Renders as a no-op with no network calls when `VITE_INTERCOM_APP_ID` is
 * unset, which is how this ships until the Intercom workspace is configured.
 */
export function FinWidget() {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  useEffect(() => {
    if (!isFinEnabled()) return;
    boot();
    return () => shutdown();
  }, [userId]);

  return null;
}
