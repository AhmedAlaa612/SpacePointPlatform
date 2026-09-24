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

/** Cleanup callback returned by watchAndPositionLauncher. Null on desktop. */
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

/** Lifts the Intercom widget above the mobile tab bar.
 *
 *  Strategy: translate #intercom-container (shared parent of the launcher
 *  button AND the notification badge) so both move together.
 *
 *  Two known pitfalls addressed here:
 *
 *  1. z-index regression — applying `transform` creates a new stacking
 *     context on the container, which can cause Intercom's internal z-index
 *     to lose its fight against z-30 on the tab bar.  We stamp a very high
 *     z-index on the container at the same time as the transform so it
 *     always wins.
 *
 *  2. Not sticking — Intercom removes and re-inserts #intercom-container
 *     whenever a notification arrives.  The insertionObserver must stay
 *     connected (not disconnected on first find) and use element-identity
 *     tracking to re-attach to every new container instance.
 *
 *  3. Chat panel clipping — when the panel opens we remove the transform so
 *     the panel renders full-height from the viewport bottom, then restore it
 *     on close via Intercom's onShow / onHide events. */
function watchAndPositionLauncher(translateUpPx: number): () => void {
  // Intercom's own z-index is typically 2147483001 — we match it so the
  // launcher stays above the tab bar's z-30 after the transform creates a
  // new stacking context on the container.
  const INTERCOM_Z = "2147483001";

  let styleObserver: MutationObserver | null = null;
  let attachedEl: HTMLElement | null = null;
  let isOpen = false;

  function applyTransform(el: HTMLElement): void {
    if (isOpen) return;
    el.style.setProperty("transform", `translateY(-${translateUpPx}px)`, "important");
    el.style.setProperty("z-index", INTERCOM_Z, "important");
  }

  function clearTransform(el: HTMLElement): void {
    el.style.removeProperty("transform");
    // Keep z-index so the panel itself is still above the tab bar when open.
    el.style.setProperty("z-index", INTERCOM_Z, "important");
  }

  function attachTo(el: HTMLElement): void {
    // Detach from any previously watched container (Intercom re-inserted it).
    styleObserver?.disconnect();
    attachedEl = el;

    applyTransform(el);

    // Re-apply whenever Intercom rewrites the container's inline style.
    styleObserver = new MutationObserver(() => applyTransform(el));
    styleObserver.observe(el, { attributes: true, attributeFilter: ["style"] });

    // Remove transform when the chat panel opens so it renders at full height;
    // restore when it closes.
    window.Intercom?.("onShow", () => {
      isOpen = true;
      clearTransform(el);
    });
    window.Intercom?.("onHide", () => {
      isOpen = false;
      applyTransform(el);
    });
  }

  // Keep the observer connected — Intercom removes and re-inserts
  // #intercom-container on notification events, so we must detect every
  // new insertion, not just the first one.
  const insertionObserver = new MutationObserver(() => {
    const el = document.querySelector<HTMLElement>("#intercom-container");
    if (el && el !== attachedEl) attachTo(el);
  });
  insertionObserver.observe(document.body, { childList: true, subtree: true });

  // Handle the case where the container already exists when boot() runs.
  const existing = document.querySelector<HTMLElement>("#intercom-container");
  if (existing) attachTo(existing);

  return () => {
    insertionObserver.disconnect();
    styleObserver?.disconnect();
    styleObserver = null;
    attachedEl = null;
  };
}

/** Show the messenger. */
export function boot(payload: FinBootPayload = {}): void {
  if (!isFinEnabled()) return;
  ensureLoaded();

  cleanupLauncher?.();
  cleanupLauncher = null;

  const isMobile = window.innerWidth < 768;

  // Shutdown before every boot so Intercom starts from a clean state.
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
