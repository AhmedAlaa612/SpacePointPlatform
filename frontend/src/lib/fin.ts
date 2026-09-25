/** Fin (Intercom) messenger loader — the student support assistant on
 * `/learn/*` (see docs/HANDOFF_LMS.md for the student surface itself).
 *
 * Fin answers from content authored in the Intercom dashboard (Rayan's
 * competition FAQ), not from anything in this repo — so there is deliberately
 * no content, no prompt and no answer logic here. This file's whole job is
 * loading the third-party widget and telling it who (if anyone) is looking at
 * it. What it can answer is a dashboard concern, on purpose: ops re-author the
 * FAQ each round without a deploy.
 *
 * Everything here is a **no-op when `VITE_INTERCOM_APP_ID` is unset**, which
 * is the state the feature ships in — local dev, CI and any environment
 * without an App ID behave exactly as they did before this file existed.
 * Note the var is read at *build* time (Vite inlines it), so a new App ID
 * needs a frontend rebuild + `deploy-frontend.sh`, not an env edit on the
 * server — same constraint `VITE_API_URL` already has, see the README.
 *
 * This is the first third-party script in this frontend (there is no Stripe
 * JS, no analytics), so it sets the pattern rather than following one.
 *
 * LAUNCHER POSITION ON MOBILE
 * Intercom's mobile messenger defaults to `bottom: 20px` and ignores vertical
 * padding configured in the Intercom dashboard on mobile web. To clear the
 * fixed mobile tab bar (~112px tall + safe area), the launcher and notification
 * badge frames are shifted up via CSS in `frontend/src/index.css`
 * (`@media (max-width: 767px) { transform: translateY(-130px) !important }`).
 * Desktop uses the dashboard vertical padding setting untouched. */

const APP_ID: string = import.meta.env.VITE_INTERCOM_APP_ID ?? "";

const SCRIPT_ID = "intercom-widget";

type IntercomCommand =
  | "boot"
  | "update"
  | "shutdown"
  | "reattach_activator"
  | "onShow"
  | "onHide";

/** The messenger's global. Before the real script lands this is our own queue
 * stub; afterwards Intercom replaces it with the real implementation and
 * replays `q`. */
interface IntercomFn {
  (command: IntercomCommand, payload?: Record<string, unknown> | (() => void)): void;
  q?: unknown[][];
}

declare global {
  interface Window {
    Intercom?: IntercomFn;
  }
}

/** What the messenger is booted with.
 *
 * Deliberately **only** the token. Intercom reads identity from the JWT's
 * signed claims, and passing unsigned `user_id`/`name`/`email` alongside it
 * is precisely what Messenger Security rejects — it answers the boot ping
 * with a 403 and the widget never opens. Nothing is lost by omitting them:
 * the backend puts every attribute inside the token
 * (`services/lms/support.py::chat_identity`), so the contact record and the
 * Inbox still get the name, email, roles, team, cohort and card id.
 *
 * Omit it entirely to boot as an anonymous visitor.
 *
 * This type is narrow on purpose. An earlier version accepted the whole
 * identity object and the caller spread it in wholesale, which is how the
 * unsigned fields got sent in the first place. */
export interface FinBootPayload {
  intercom_user_jwt?: string;
}

/** Whether an App ID was baked into this build. Callers check this rather
 * than guessing from `window.Intercom`, which is also set by our own stub. */
export function isFinEnabled(): boolean {
  return APP_ID.length > 0;
}

/** Inject the widget script once. Idempotent: safe to call on every boot,
 * which matters because React re-runs effects (twice per mount under
 * StrictMode in dev) and the student shell mounts on every `/learn/*` route. */
function ensureLoaded(): void {
  if (document.getElementById(SCRIPT_ID)) return;

  // Queue stub — commands issued before the script finishes downloading are
  // pushed onto `q` and replayed by Intercom once it takes over the global.
  // Without this, the `boot` below is simply lost on a cold load.
  if (typeof window.Intercom !== "function") {
    const stub = ((...args: unknown[]) => {
      stub.q?.push(args);
    }) as IntercomFn;
    stub.q = [];
    window.Intercom = stub;
  }

  const script = document.createElement("script");
  script.id = SCRIPT_ID;
  script.async = true;
  script.src = `https://widget.intercom.io/widget/${APP_ID}`;
  document.head.appendChild(script);
}

/** Show the messenger. */
export function boot(payload: FinBootPayload = {}): void {
  if (!isFinEnabled()) return;
  ensureLoaded();

  // Shutdown before every boot so Intercom starts from a clean state
  // rather than restoring a stale cached session from its cookie.
  window.Intercom?.("shutdown");

  window.Intercom?.("boot", { app_id: APP_ID, ...payload });

  // Track chat open/close state on body so mobile styles can deactivate transforms while chatting
  window.Intercom?.("onShow", () => {
    document.body.classList.add("intercom-chat-open");
  });
  window.Intercom?.("onHide", () => {
    document.body.classList.remove("intercom-chat-open");
  });
}

/** Hide the messenger and **clear the local conversation**.
 *
 * This is why the caller tracks the logged-in user rather than booting once
 * and forgetting: Intercom keeps an anonymous visitor's conversation in a
 * cookie, so without a shutdown on logout the next person to sign in on the
 * same browser inherits the previous student's chat history. These run on
 * shared school and lab machines — that is a real leak, not a hypothetical. */
export function shutdown(): void {
  if (!isFinEnabled()) return;
  document.body.classList.remove("intercom-chat-open");
  window.Intercom?.("shutdown");
}
