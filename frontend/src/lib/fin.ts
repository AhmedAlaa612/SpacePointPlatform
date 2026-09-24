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

/** Cleanup callback returned by watchAndPositionLauncher — disconnects the
 *  MutationObserver.  Null when no observer is running (desktop / pre-boot). */
let cleanupLauncher: (() => void) | null = null;

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

/** Lifts the entire Intercom widget container above the mobile tab bar.
 *
 *  Why #intercom-container and not the launcher iframe:
 *  The notification badge (unread message count) is a *separate* element
 *  from the launcher iframe — targeting the iframe alone moved the button
 *  but left the badge at the original bottom position.  Translating the
 *  shared parent container moves both together.
 *
 *  Why onShow / onHide toggling:
 *  `transform` on the container creates a new stacking context.  When the
 *  chat panel is open it must render from the viewport bottom, not from
 *  the translated position.  Intercom's own `onShow` / `onHide` callbacks
 *  let us remove the transform the moment the panel opens and re-apply it
 *  the moment it closes — the launcher and badge stay raised whenever the
 *  chat is not in use. */
function watchAndPositionLauncher(translateUpPx: number): () => void {
  let styleObserver: MutationObserver | null = null;
  let isOpen = false;

  function applyTransform(el: HTMLElement): void {
    if (isOpen) return; // don't move while the chat panel is visible
    el.style.setProperty("transform", `translateY(-${translateUpPx}px)`, "important");
  }

  function clearTransform(el: HTMLElement): void {
    el.style.removeProperty("transform");
  }

  function attachTo(el: HTMLElement): void {
    applyTransform(el);

    // Re-apply whenever Intercom rewrites the container's inline style.
    styleObserver?.disconnect();
    styleObserver = new MutationObserver(() => applyTransform(el));
    styleObserver.observe(el, { attributes: true, attributeFilter: ["style"] });

    // Remove transform when chat opens so the panel renders at full height
    // from the viewport bottom; restore it when chat closes.
    window.Intercom?.("onShow", () => {
      isOpen = true;
      clearTransform(el);
    });
    window.Intercom?.("onHide", () => {
      isOpen = false;
      applyTransform(el);
    });
  }

  // Watch for #intercom-container being inserted into the DOM.
  const insertionObserver = new MutationObserver(() => {
    const el = document.querySelector<HTMLElement>("#intercom-container");
    if (el) {
      insertionObserver.disconnect(); // found it — no need to keep watching
      attachTo(el);
    }
  });
  insertionObserver.observe(document.body, { childList: true, subtree: true });

  // Try immediately in case the container already exists.
  const existing = document.querySelector<HTMLElement>("#intercom-container");
  if (existing) {
    insertionObserver.disconnect();
    attachTo(existing);
  }

  return () => {
    insertionObserver.disconnect();
    styleObserver?.disconnect();
    styleObserver = null;
  };
}

/** Show the messenger.
 *
 * On mobile the entire widget container is lifted above the LearnMobileTabBar
 * (~112 px for staff + safe-area-inset-bottom on Face ID devices) by
 * translating #intercom-container.  The transform is removed while the chat
 * panel is open (via onShow/onHide) so the panel always renders full-height
 * from the viewport bottom.  See watchAndPositionLauncher for full rationale. */
export function boot(payload: FinBootPayload = {}): void {
  if (!isFinEnabled()) return;
  ensureLoaded();

  // Always clean up any previous observer first so a mobile observer can
  // never bleed into a desktop boot.
  cleanupLauncher?.();
  cleanupLauncher = null;

  // isMobile: matches the shell's md breakpoint (768 px).
  const isMobile = window.innerWidth < 768;

  // Shutdown before every boot so Intercom starts from a clean state
  // rather than restoring a stale cached session from its cookie.
  window.Intercom?.("shutdown");

  window.Intercom?.("boot", {
    app_id: APP_ID,
    vertical_padding: isMobile ? 180 : 20,
    ...payload,
  });

  if (isMobile) {
    cleanupLauncher = watchAndPositionLauncher(120);
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
  cleanupLauncher?.();
  cleanupLauncher = null;
  window.Intercom?.("shutdown");
}
