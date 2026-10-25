# SpacePoint Unified — Tutorials & Live Action Guides Handoff (`react-joyride` v3)

**Entry point for any agent or developer modifying, extending, or reusing the interactive onboarding tours and live "How do I..." action guides across the Portal and LMS.**

**Last verified against the code: 2026-10-25**

---

## 1. Architecture in One Table

| Layer | File | Responsibility |
|---|---|---|
| **Step & Action Catalog** | `frontend/src/lib/tours/index.ts` | Defines `TourStepDef`, `TourActionGuide`, `NAV_TAB_CATALOG` (descriptions for every sidebar tab), `findVisibleTarget` (DOM visibility & priority selector resolver), `resolveCandidateSteps` (full workspace tour), and `resolveActionGuides` ("How do I..." live workflows). |
| **Global Tour Engine** | `frontend/src/context/TourContext.tsx` | Wraps each layout shell (`<TourProvider surface="portal" \| "applicant" \| "learn">`). Manages `useJoyride` (v3), per-step `localStorage` persistence (`sp_tour_seen_v1_${user.id}`), cross-page route transitions, and live click-to-advance (`advanceOnClick`). |
| **Tooltip & Launcher UI** | `frontend/src/components/ui/SpacePointTourCard.tsx` | Renders `SpacePointTourCard` (custom Joyride tooltip) and `TutorialLauncherMenu` (the popover menu offering **Full Workspace Tour** + role-specific **How do I...** guides). Lives in `components/ui/` so both Portal and `/learn/**` can import it legally. |
| **Portal & Applicant Shells** | `frontend/src/components/layout/Sidebar.tsx` | Mounts `<TourProvider surface="portal">` on `AppShell` and `<TourProvider surface="applicant">` on `ApplicantShell`. Automatically tags every `NavLinkItem` with `data-tour="portal-nav-<slug>"`. |
| **LMS Student Shell** | `frontend/src/pages/learn/LearnShell.tsx`<br/>`frontend/src/pages/learn/LearnSidebar.tsx`<br/>`frontend/src/pages/learn/nav/LearnMobileTabBar.tsx`<br/>`frontend/src/pages/learn/nav/LearnNavShared.tsx` | Mounts `<TourProvider surface="learn">` on `LearnShell`. Automatically tags every `NAV_ITEMS` link with `data-tour="learn-nav-${item.key}"` on both desktop sidebar and mobile bottom tab bar. |

---

## 2. How Dynamic Tab Filtering & "New Feature" Spotlights Work

Tabs in SpacePoint are frequently hidden, shown, or added per role (for example, commenting/uncommenting `missions`, `games`, or `arcade` in `frontend/src/pages/learn/nav/navItems.ts`, or conditional role branches in `Sidebar.tsx`).

The tutorial engine handles this **automatically with zero manual sync**:

1. **Deterministic `data-tour` Tagging:**
   - **Portal (`Sidebar.tsx`):** Every item created with `mk(label, to)` or `mkGroup(label, to, children)` automatically receives `data-tour="portal-nav-${slugifyTourId(label)}"` (and child items receive `data-tour="portal-nav-${parentSlug}-${childSlug}"`).
   - **LMS (`LearnSidebar.tsx` & `LearnMobileTabBar.tsx`):** Every entry in `NAV_ITEMS` automatically receives `data-tour="learn-nav-${item.key}"`.
2. **Real DOM Visibility Pre-Filtering (`findVisibleTarget`):**
   - Before starting a tour, `resolveCandidateSteps` scans the DOM for `[data-tour^="portal-nav-"]` (or `[data-tour^="learn-nav-"]`) and checks `findVisibleTarget(selector)` (`rect.width > 0 && rect.height > 0 && display !== "none"`).
   - If a tab is commented out, hidden for a role, or inside an inactive mobile/desktop container, it is skipped automatically.
3. **Per-Step Seen Tracking (`sp_tour_seen_v1_${user.id}`):**
   - Instead of storing a single `tour_done = true` flag, `TourContext.tsx` records an array of seen **step IDs** per user ID in `localStorage`.
   - **First visit:** All visible steps are unseen -> runs the full onboarding tour.
   - **When a hidden tab is later unlocked:** Returning users already have the old step IDs in their seen set, so `TourContext` detects *only* the newly unlocked tab's step ID and automatically runs a 1-step spotlight on that new tab.

---

## 3. Recipes: How to Reuse & Extend

### Recipe A: Add or Customize a Sidebar Tab Description
When you add a new sidebar item in `Sidebar.tsx` (e.g. `mk("Telemetry Console", "/operations/telemetry")`), it automatically gets `data-tour="portal-nav-telemetry-console"` and a fallback description.

To give it a curated title and description, add an entry to `NAV_TAB_CATALOG` in `frontend/src/lib/tours/index.ts`:

```ts
// frontend/src/lib/tours/index.ts -> NAV_TAB_CATALOG
"portal-nav-telemetry-console": {
  title: "Telemetry Console",
  content: "Monitor live satellite packets, downlink health, and ground station pass logs.",
},
```

---

### Recipe B: Add a Live "How do I..." Action Guide (`resolveActionGuides`)
Action guides appear inside the **Tutorial** menu under **"How do I..."**. When selected, they can navigate across routes and advance automatically when the user clicks the highlighted element.

1. **(Optional) Tag a specific button/toolbar on the target page with `data-tour`:**
   ```tsx
   <button data-tour="my-action-btn" onClick={handleAction}>
     Create Cohort
   </button>
   ```
2. **Add the `TourActionGuide` in `resolveActionGuides` (`frontend/src/lib/tours/index.ts`):**
   ```ts
   {
     id: "action-ops-create-cohort",
     title: "Create a New Cohort",
     description: "Open the cohorts page and launch the cohort creation modal.",
     // If this sidebar tab is hidden for the user, this guide is automatically hidden too:
     requiredSelector: '[data-tour="portal-nav-programs"]',
     steps: [
       {
         id: "act-cohort-1",
         selector: '[data-tour="portal-nav-programs"]',
         title: "1. Open Programs & Cohorts",
         content: "Click 'Programs' in the sidebar (or press Next).",
         placement: "right",
         advanceOnClick: true, // Clicking the real sidebar item advances to Step 2 automatically
       },
       {
         id: "act-cohort-2",
         route: "/operations/cohorts", // Automatically navigates if not already on /operations/cohorts
         // Comma-separated priority selectors: tries the button first, falls back to the page header
         selector: '[data-tour="my-action-btn"], [data-tour="page-workspace"]',
         title: "2. Click 'Create Cohort'",
         content: "Click this button to configure dates, program checklists, and staffing.",
         placement: "bottom",
         advanceOnClick: true,
       },
     ],
   }
   ```

---

### Recipe C: Trigger a Custom Tour From Any Button on a Page (`useTour`)
Any component inside the Portal, Applicant, or LMS shells can trigger a custom walkthrough on demand using `useTour()`:

```tsx
import { useTour } from "@/context/TourContext";

export function MyPageHelpButton() {
  const { startCustomTour } = useTour();

  return (
    <button
      type="button"
      onClick={() =>
        startCustomTour([
          {
            id: "custom-step-1",
            selector: '[data-tour="step-1-box"]',
            title: "Step 1: Select Subsystem",
            content: "Pick the satellite subsystem you want to configure.",
            placement: "bottom",
            advanceOnClick: true,
          },
          {
            id: "custom-step-2",
            selector: '[data-tour="step-2-run-btn"]',
            title: "Step 2: Run Simulation",
            content: "Click Run to validate power and mass budgets.",
            placement: "left",
          },
        ])
      }
    >
      How this page works
    </button>
  );
}
```

---

## 4. Critical Invariants & Pitfalls (Read Before Editing!)

1. **UI Rule — Never Use the `Sparkles` Icon:**
   Per operator directive, **never** use the `Sparkles` icon in `SpacePointTourCard.tsx` or any tutorial badge/button. Keep step badges (`STEP X OF Y`) as clean text only.
2. **Never Put `navigate` in `joyrideSteps`'s `useMemo` Dependencies (`TourContext.tsx`):**
   In `@tanstack/react-router`, `useNavigate()` returns a new function reference when the route changes. In `react-joyride` v3, if the `steps` array reference changes while a step transition is in flight, `usePropSync` resets the store and aborts `useLifecycleEffect`'s internal `AbortController`, freezing the dark overlay on screen with no modal.
   - **Rule:** Keep `joyrideSteps` memoized **only** on `[activeDefs]`, store `navigate` in `navigateRef`, and perform route navigation inside a `useEffect` watching `[run, activeDefs, state.index]`.
3. **Route-Transition Target Guard:**
   When a step defines `route: "/some/path"`, `step.target()` must return `null` while `window.location.pathname !== def.route`. Otherwise, generic selectors like `[data-tour="page-workspace"]` will match the *old* page before the route finishes changing. Returning `null` until the pathname matches lets Joyride's built-in 100ms poller (`targetWaitTimeout: 3000`) wait cleanly for the new page to mount.
4. **Never Anchor a Tooltip Directly to the Full-Height `<main>` Element:**
   `<main>` spans the full document height (`2000px+`). Anchoring Floating UI to `<main>` pushes the tooltip all the way to the bottom of the page. Always use `[data-tour="page-workspace"]` with `placement: "bottom"` — `findVisibleTarget` automatically expands `[data-tour="page-workspace"]` to target the compact top header/tablist inside `<main>` (`main [role="tablist"]`, `main h1`, `main h2`, `main > div > :first-child`) so the modal stays at the top of the viewport with zero scrolling.
5. **Mobile Viewport Positioning:**
   - In `TutorialLauncherMenu` (`SpacePointTourCard.tsx`), keep `fixed inset-x-3` on mobile (`< 640px`) and `sm:absolute sm:w-80` on desktop so the popover never clips off the left/right edges when triggered from `LearnMobileTabBar`.
   - Steps targeting `learn-nav-*` automatically switch to `placement: "top"` on viewports `< 768px` (where nav is a bottom tab bar) and `placement: "right"` on desktop (where nav is a left sidebar).
6. **LMS Import Discipline (`LearnShell.tsx`):**
   Files under `frontend/src/pages/learn/**` must **never** import from `frontend/src/components/layout/Sidebar.tsx`. All shared tour components must stay in `frontend/src/context/TourContext.tsx`, `frontend/src/lib/tours/`, and `frontend/src/components/ui/SpacePointTourCard.tsx`.
