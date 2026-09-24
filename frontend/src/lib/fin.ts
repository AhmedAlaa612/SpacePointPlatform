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
 */

const APP_ID: string = import.meta.env.VITE_INTERCOM_APP_ID ?? "";

const SCRIPT_ID = "intercom-widget";

/** Holds the MutationObserver that repositions the launcher on mobile,
 *  so we can disconnect it on shutdown and avoid a live observer after the
 *  widget is torn down. */
let launcherObserver: MutationObserver | null = null;


type IntercomCommand = "boot" | "update" | "shutdown" | "reattach_activator";

/** The messenger's global. Before the real script lands this is our own queue
 * stub; afterwards Intercom replaces it with the real implementation and
 * replays `q`. */
interface IntercomFn {
  (command: IntercomCommand, payload?: Record<string, unknown>): void;
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

/** Stamps `bottom` directly on whatever element Intercom injects for its
 *  launcher so it sits above the mobile tab bar.
 *
 *  Why not vertical_padding in boot(): Intercom's script sets
 *  `style="bottom:20px"` on the launcher iframe *after* the boot call
 *  resolves, overwriting the boot parameter every time.  CSS !important in
 *  our stylesheet also fails because Intercom's newer Fin builds use
 *  unpublished/hashed class names that differ between releases.
 *
 *  A MutationObserver fires *after* the element is inserted (and after
 *  Intercom has set its own inline style), so setProperty(…,'important')
 *  wins the race reliably.  The observer stays connected so it also catches
 *  Intercom re-stamping the style on messenger open/close cycles. */
function watchAndPositionLauncher(bottomPx: number): MutationObserver {
  // Every known selector Intercom has used for its launcher iframe across
  // messenger versions.  We try all of them on every mutation.
  const SELECTORS = [
    ".intercom-launcher-frame",
    ".intercom-lightweight-app-launcher",
    '[name="intercom-launcher-frame"]',
    "#intercom-container iframe",
  ];

  function stamp(): void {
    for (const sel of SELECTORS) {
      const el = document.querySelector<HTMLElement>(sel);
      if (el) {
        el.style.setProperty("bottom", `${bottomPx}px`, "important");
        return;
      }
    }
  }

  const observer = new MutationObserver(stamp);
  observer.observe(document.body, { childList: true, subtree: true });

  // Also try immediately in case the element already exists.
  stamp();

  return observer;
}

/** Show the messenger.
 *
 * On mobile the launcher is repositioned above the LearnMobileTabBar
 * (~112 px tall for staff + safe-area-inset-bottom on Face ID devices)
 * via a MutationObserver rather than vertical_padding — see
 * watchAndPositionLauncher above for why. */
export function boot(payload: FinBootPayload = {}): void {
  if (!isFinEnabled()) return;
  ensureLoaded();

  // Always disconnect any previous observer first — without this, an observer
  // started during a mobile boot can bleed into a desktop boot and move the
  // launcher on desktop too.
  launcherObserver?.disconnect();
  launcherObserver = null;

  // isMobile: the same md breakpoint the shell uses (768 px).
  const isMobile = window.innerWidth < 768;

  // Shutdown before every boot so Intercom starts from a clean state
  // rather than restoring a stale cached session from its cookie.
  window.Intercom?.("shutdown");

  window.Intercom?.("boot", {
    app_id: APP_ID,
    vertical_padding: isMobile ? 180 : 20, // belt
    ...payload,
  });

  // Suspenders — direct DOM override, mobile only.
  if (isMobile) {
    launcherObserver = watchAndPositionLauncher(160);
  }
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
  launcherObserver?.disconnect();
  launcherObserver = null;
  window.Intercom?.("shutdown");
}
