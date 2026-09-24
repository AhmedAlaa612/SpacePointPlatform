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

/** Cleanup for the padding watcher. Null when not running. */
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
    // Intercom reads this object at script load time before any boot() call.
    intercomSettings?: Record<string, unknown>;
  }
}

/** What the messenger is booted with. */
export interface FinBootPayload {
  intercom_user_jwt?: string;
}

/** Whether an App ID was baked into this build. */
export function isFinEnabled(): boolean {
  return APP_ID.length > 0;
}

/** Inject the widget script once. Sets window.intercomSettings first so
 *  Intercom reads vertical_padding during its own initialisation (before
 *  any boot/update call). */
function ensureLoaded(verticalPadding: number): void {
  if (document.getElementById(SCRIPT_ID)) return;

  // intercomSettings is read by Intercom's script at load time — more
  // reliable than boot/update which race against the script's own init.
  window.intercomSettings = {
    app_id: APP_ID,
    vertical_padding: verticalPadding,
  };

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

/** Ensures vertical_padding stays at our target value by calling
 *  Intercom('update') whenever:
 *  — the container first appears (covers normal boot)
 *  — the container is re-inserted (notification badge swap)
 *  — the launcher iframe's style attribute is changed (Intercom re-stamp)
 *  — 500 ms and 1500 ms after boot (catches delayed initialisation resets)
 *
 *  A debounce prevents rapid-fire update loops when the style observer and
 *  Intercom's own code fire in quick succession. */
function watchAndApplyPadding(padding: number): () => void {
  const LAUNCHER_SELECTORS = [
    ".intercom-launcher-frame",
    ".intercom-lightweight-app-launcher",
    '[name="intercom-launcher-frame"]',
  ];

  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let styleObserver: MutationObserver | null = null;
  let lastContainer: Element | null = null;
  const timers: ReturnType<typeof setTimeout>[] = [];

  function scheduleUpdate(): void {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      window.Intercom?.("update", { vertical_padding: padding });
    }, 80);
  }

  function attachStyleWatcher(container: Element): void {
    styleObserver?.disconnect();

    // Find the launcher iframe inside the container and watch its style —
    // Intercom re-stamps bottom: 20px on it after insertion.
    for (const sel of LAUNCHER_SELECTORS) {
      const el = container.querySelector<HTMLElement>(sel);
      if (el) {
        styleObserver = new MutationObserver(scheduleUpdate);
        styleObserver.observe(el, { attributes: true, attributeFilter: ["style"] });
        return;
      }
    }

    // Launcher not yet inside the container — watch for it to appear.
    const inner = new MutationObserver(() => {
      for (const sel of LAUNCHER_SELECTORS) {
        const el = container.querySelector<HTMLElement>(sel);
        if (el) {
          inner.disconnect();
          styleObserver?.disconnect();
          styleObserver = new MutationObserver(scheduleUpdate);
          styleObserver.observe(el, { attributes: true, attributeFilter: ["style"] });
          return;
        }
      }
    });
    inner.observe(container, { childList: true, subtree: true });
    styleObserver = inner;
  }

  const containerObserver = new MutationObserver(() => {
    const el = document.querySelector("#intercom-container");
    if (el && el !== lastContainer) {
      lastContainer = el;
      attachStyleWatcher(el);
      scheduleUpdate();
    }
  });
  containerObserver.observe(document.body, { childList: true, subtree: true });

  // Handle container already in DOM.
  const existing = document.querySelector("#intercom-container");
  if (existing) {
    lastContainer = existing;
    attachStyleWatcher(existing);
    scheduleUpdate();
  }

  // Catch delayed resets — Intercom sometimes re-stamps 500–1500 ms after boot.
  timers.push(setTimeout(scheduleUpdate, 500));
  timers.push(setTimeout(scheduleUpdate, 1500));

  return () => {
    containerObserver.disconnect();
    styleObserver?.disconnect();
    if (debounceTimer) clearTimeout(debounceTimer);
    timers.forEach(clearTimeout);
    lastContainer = null;
  };
}

/** Show the messenger. */
export function boot(payload: FinBootPayload = {}): void {
  if (!isFinEnabled()) return;

  cleanupLauncher?.();
  cleanupLauncher = null;

  const isMobile = window.innerWidth < 768;
  const verticalPadding = isMobile ? 150 : 20;

  ensureLoaded(verticalPadding);

  // Shutdown before every boot so Intercom starts from a clean state.
  window.Intercom?.("shutdown");

  window.Intercom?.("boot", {
    app_id: APP_ID,
    vertical_padding: verticalPadding,
    ...payload,
  });

  if (isMobile) {
    cleanupLauncher = watchAndApplyPadding(verticalPadding);
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
