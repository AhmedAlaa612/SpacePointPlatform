import type { Role } from "@/types/shared";

export interface TourStepDef {
  /** Stable identifier persisted per-user in localStorage so seen steps are
   * remembered individually and newly unhidden tabs can trigger a spotlight. */
  id: string;
  /** CSS selector for the target element, or "body" for a centered intro card. */
  selector: string;
  /** Tooltip heading. */
  title: string;
  /** Tooltip body text. */
  content: string;
  /** Preferred tooltip placement relative to the target. */
  placement?: "top" | "bottom" | "left" | "right" | "center" | "auto";
  /** Optional route path (e.g. "/instructors/my-sessions"). If set, the tour
   * automatically navigates to this page before showing the step and waits for
   * `selector` to appear in the DOM. */
  route?: string;
  /** Optional async action to run before showing the step (e.g., opening a modal,
   * expanding an accordion, or switching an in-page tab). */
  beforeStep?: () => void | Promise<void>;
  /** Whether the user can click/interact with the highlighted element through
   * the spotlight cutout (default: true). */
  allowInteraction?: boolean;
  /** If true, clicking the highlighted target element automatically advances
   * the tour to the next step so the user can perform the action live. */
  advanceOnClick?: boolean;
}

export interface TourActionGuide {
  id: string;
  title: string;
  description: string;
  /** Optional selector that must be currently visible in the workspace for this
   * action guide to be offered (automatically hides guides for hidden tabs). */
  requiredSelector?: string;
  steps: TourStepDef[];
}

/** Wait up to `timeoutMs` for a visible element matching `selector` to mount
 * (used when a step navigates to another page or opens a tab/modal). */
export function waitForVisibleTarget(
  selector: string,
  timeoutMs = 3500,
): Promise<HTMLElement | null> {
  return new Promise((resolve) => {
    const immediate = findVisibleTarget(selector);
    if (immediate) {
      resolve(immediate);
      return;
    }
    const start = Date.now();
    const interval = window.setInterval(() => {
      const found = findVisibleTarget(selector);
      if (found) {
        window.clearInterval(interval);
        resolve(found);
      } else if (Date.now() - start >= timeoutMs) {
        window.clearInterval(interval);
        resolve(null);
      }
    }, 80);
  });
}

/** Convert any nav label into a deterministic data-tour slug. */
export function slugifyTourId(label: string): string {
  return label
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/** Find the first visible DOM element matching `selector` (supports comma-separated
 * priority fallback selectors, and ignores hidden desktop/mobile containers). */
export function findVisibleTarget(selector: string): HTMLElement | null {
  if (typeof document === "undefined") return null;
  if (selector === "body") return document.body;
  const parts = selector
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  for (const part of parts) {
    const elements = document.querySelectorAll<HTMLElement>(part);
    for (const el of elements) {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      if (
        rect.width > 0 &&
        rect.height > 0 &&
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        style.opacity !== "0"
      ) {
        return el;
      }
    }
  }
  return null;
}

/** Curated descriptions keyed by `data-tour` attribute value so any role or
 * domain showing that tab gets a clear explanation automatically. */
export const NAV_TAB_CATALOG: Record<string, { title: string; content: string }> = {
  // ── LMS (/learn/*) Navigation ─────────────────────────────────────────────
  "learn-nav-home": {
    title: "Home Base",
    content: "Your learning dashboard — resume your latest module, jump into your active cohort program, or explore new courses and learning paths.",
  },
  "learn-nav-my-courses": {
    title: "My Learning",
    content: "Access all courses and learning paths you are currently enrolled in and track your completion progress.",
  },
  "learn-nav-checklists": {
    title: "Programs & Checklists",
    content: "View your assigned program roadmap, complete required milestones, and track instructor verification.",
  },
  "learn-nav-missions": {
    title: "CubeSat & Flight Missions",
    content: "Design, configure, and operate virtual satellite missions and review telemetry engineering reports.",
  },
  "learn-nav-games": {
    title: "Live Quiz Arena",
    content: "Join real-time cohort quiz sessions and compete with your peers on space engineering challenges.",
  },
  "learn-nav-arcade": {
    title: "SpacePoint Mission Arcade",
    content: "Practice hands-on interactive engineering simulations across 8 satellite subsystems in Explorer and Engineer tracks.",
  },
  "learn-nav-leaderboard": {
    title: "Leaderboard",
    content: "See how you and your team rank across courses, quizzes, and program milestones.",
  },
  "learn-search-catalog": {
    title: "Course Catalog Search",
    content: "Browse and search the full library of SpacePoint courses and modules anytime.",
  },
  "learn-active-program": {
    title: "Active Program Shortcut",
    content: "Quickly jump back to your current cohort program board and see your live completion bar.",
  },
  "learn-back-to-portal": {
    title: "Return to Staff Portal",
    content: "Switch back from the student LMS view to your main SpacePoint Portal workspace.",
  },

  // ── Shared Portal Navigation Items ────────────────────────────────────────
  "portal-nav-dashboard": {
    title: "Dashboard Overview",
    content: "Your central command view with key metrics, recent activity, and quick actions for your role.",
  },
  "portal-nav-overview": {
    title: "Workspace Overview",
    content: "View your primary status summary, upcoming commitments, and key announcements.",
  },
  "portal-nav-learn": {
    title: "SpacePoint Learn (LMS)",
    content: "Open the student LMS experience to preview courses, missions, programs, and interactive simulations.",
  },
  "portal-nav-my-articles": {
    title: "My Articles",
    content: "Draft, submit, and manage contributor articles for the SpacePoint publication queue.",
  },
  "portal-nav-documents": {
    title: "Documents",
    content: "Access, sign, and download official agreements, letters, and role documentation.",
  },
  "portal-nav-personal-documents": {
    title: "Personal Documents",
    content: "View and manage your signed contracts, onboarding documents, and certificates.",
  },
  "portal-nav-settings": {
    title: "Settings",
    content: "Configure workspace preferences, system rules, and administrative options.",
  },
  "portal-nav-profile-and-settings": {
    title: "Profile & Settings",
    content: "Update your personal profile, contact details, password, and account preferences.",
  },

  // ── Admin Navigation ──────────────────────────────────────────────────────
  "portal-nav-user-management": {
    title: "User Management",
    content: "Search, create, and manage user accounts, assign roles, and synchronize contact emails across the platform.",
  },
  "portal-nav-applications": {
    title: "Applications Pipeline",
    content: "Review and approve incoming applicant submissions across programs and roles.",
  },
  "portal-nav-role-requests": {
    title: "Role Requests",
    content: "Approve or decline internal role requests and trigger automated internship letters.",
  },
  "portal-nav-birthdays": {
    title: "Team Birthdays",
    content: "Keep track of upcoming birthdays across the SpacePoint team and community.",
  },
  "portal-nav-operations": {
    title: "Operations Workspace",
    content: "Jump directly into the full Operations dashboard for cohorts, inventory, LMS, and website management.",
  },

  // ── Operations, COO & Storekeeper Navigation ──────────────────────────────
  "portal-nav-programs": {
    title: "Programs & Cohorts",
    content: "Manage educational programs, active cohorts, session reviews, and delivery settings.",
  },
  "portal-nav-lms": {
    title: "LMS Authoring & Student Hub",
    content: "Manage courses, learning paths, program checklists, missions, live quizzes, invite code grants, and student progress.",
  },
  "portal-nav-inventory": {
    title: "Inventory & Fulfilment",
    content: "Track kits, warehouse stock counts, fulfilment dispatches, item catalogues, and the SpacePoint e-commerce shop.",
  },
  "portal-nav-website": {
    title: "Website & Labs CMS",
    content: "Manage live content for spacepoint.ae and labs.spacepoint.ae — events, pricing, partners, press, newsletters, and R&D.",
  },
  "portal-nav-mentors": {
    title: "Space Mentors",
    content: "Manage the mentor roster, review mentor applications, and configure mentorship topics.",
  },
  "portal-nav-sessions-calendar": {
    title: "Sessions Calendar",
    content: "View and coordinate scheduled training sessions, staffing assignments, and delivery timelines.",
  },
  "portal-nav-ground-station-devices": {
    title: "Ground Station Devices",
    content: "Provision and monitor live CubeSat ground station hardware, telemetry streams, and alert thresholds.",
  },
  "portal-nav-test-accounts": {
    title: "Test & Sandbox Accounts",
    content: "Manage observer and test accounts for safely rehearsing courses, missions, and competition judging.",
  },

  // ── Instructors & Facilitators Navigation ─────────────────────────────────
  "portal-nav-sessions": {
    title: "Sessions",
    content: "View your assigned teaching or mentorship sessions, check attendance, and manage session logistics.",
  },
  "portal-nav-my-sessions": {
    title: "My Sessions",
    content: "View and manage your scheduled school and program sessions.",
  },
  "portal-nav-instructors": {
    title: "Instructor Resources & Reviews",
    content: "Access facilitator training, library resources, assessment banks, and instructor application reviews.",
  },
  "portal-nav-library-resources": {
    title: "Library Resources",
    content: "Download teaching slides, curriculum guides, and classroom reference materials.",
  },
  "portal-nav-satkit-training": {
    title: "SatKit Training",
    content: "Complete hands-on SatKit hardware and curriculum training modules.",
  },
  "portal-nav-payments": {
    title: "Payments & Invoices",
    content: "Track your session payouts, review payment summaries, and sign pending payment receipts.",
  },
  "portal-nav-students-progress": {
    title: "Students Progress",
    content: "Monitor your cohort students' checklist milestones, review submissions, and gate progress.",
  },
  "portal-nav-instructor-id-card": {
    title: "Instructor ID Card",
    content: "View and download your official digital SpacePoint Instructor ID badge.",
  },
  "portal-nav-facilitator-id": {
    title: "Facilitator ID Card",
    content: "View and download your official digital SpacePoint Facilitator ID badge.",
  },
  "portal-nav-my-kits-and-items": {
    title: "My Kits & Items",
    content: "See the SatKits and hardware equipment currently checked out under your custody.",
  },
  "portal-nav-applicants": {
    title: "Instructor Applicants",
    content: "Review applicant video summaries, research modules, presentations, and assessments.",
  },
  "portal-nav-invitation-codes": {
    title: "Invitation Codes",
    content: "Generate and track invitation codes for onboarding new applicants, students, and observers.",
  },
  "portal-nav-facilitators": {
    title: "Facilitators Roster",
    content: "Manage facilitator accounts, permissions, and assignments.",
  },
  "portal-nav-assessment-questions": {
    title: "Assessment Questions",
    content: "Create and curate technical assessment questions for instructor evaluation.",
  },
  "portal-nav-certificates": {
    title: "Certificates",
    content: "Issue and verify official completion and recognition certificates.",
  },

  // ── LMS Author Standalone Navigation ──────────────────────────────────────
  "portal-nav-courses": {
    title: "Courses Authoring",
    content: "Create and edit LMS courses, video lessons, quizzes, and module structures.",
  },
  "portal-nav-learning-paths": {
    title: "Learning Paths",
    content: "Bundle courses into structured multi-step learning paths for students.",
  },
  "portal-nav-invite-codes": {
    title: "Invite Codes & Grants",
    content: "Manage batch invite codes that automatically enroll students or observers into courses and cohorts.",
  },

  // ── Interns & Team Leaders Navigation ─────────────────────────────────────
  "portal-nav-board": {
    title: "Project Kanban Board",
    content: "Track active engineering tasks, move cards across stages, and collaborate with your intern team.",
  },
  "portal-nav-tracker": {
    title: "Progress Tracker",
    content: "Monitor project epics, deliverables, and individual intern contributions.",
  },
  "portal-nav-propose-a-mission": {
    title: "Propose a Mission",
    content: "Submit new project or mission proposals for review and approval.",
  },
  "portal-nav-manage-missions": {
    title: "Manage Missions",
    content: "Review, scope, and coordinate active intern missions and milestones.",
  },
  "portal-nav-team-management": {
    title: "Team Management",
    content: "Organize intern teams, assign team leaders, and manage project rosters.",
  },
  "portal-nav-id-card": {
    title: "Digital ID Card",
    content: "View and download your official SpacePoint digital ID card and QR pass.",
  },

  // ── Ambassadors & Teachers Navigation ─────────────────────────────────────
  "portal-nav-leads": {
    title: "School & Partner Leads",
    content: "Submit and track outreach leads as they progress through the partnership pipeline.",
  },
  "portal-nav-tasks": {
    title: "Assigned Tasks",
    content: "Complete outreach and community tasks to earn points, badges, and leaderboard ranks.",
  },
  "portal-nav-network": {
    title: "Ambassador Network",
    content: "Connect with fellow ambassadors and view community activity across regions.",
  },
  "portal-nav-materials": {
    title: "Outreach Materials",
    content: "Download official decks, brochures, and media kits for presentations and school visits.",
  },
  "portal-nav-leaderboard": {
    title: "Leaderboard",
    content: "Track points, titles, and achievements across the ambassador community.",
  },
  "portal-nav-titles": {
    title: "Ambassador Titles",
    content: "Configure rank thresholds and unlockable ambassador titles.",
  },
  "portal-nav-badges": {
    title: "Ambassador Badges",
    content: "Manage achievement badges awarded for special milestones.",
  },

  // ── Mentors & Organizations Navigation ────────────────────────────────────
  "portal-nav-availability": {
    title: "Mentor Availability",
    content: "Set your weekly time slots so students and teams can book mentorship sessions with you.",
  },
  "portal-nav-mentor-settings": {
    title: "Mentor Profile & Bio",
    content: "Configure your expertise tags, biography, and meeting preferences shown in the mentor directory.",
  },
  "portal-nav-directory": {
    title: "Mentor Directory",
    content: "Browse the SpacePoint mentor network by satellite subsystem and domain expertise.",
  },
  "portal-nav-my-events": {
    title: "Organization Events",
    content: "View and manage your organization's hosted SpacePoint events, cohorts, and participant rosters.",
  },

  // ── Competition Judges Navigation ─────────────────────────────────────────
  "portal-nav-teams": {
    title: "Competition Teams",
    content: "View assigned competition cohorts, inspect team submissions, and score teams using the official rubric.",
  },

  // ── Applicant Navigation ──────────────────────────────────────────────────
  "portal-nav-status": {
    title: "Application Status",
    content: "Track each phase of your instructor application and submit required deliverables.",
  },
  "portal-nav-videos": {
    title: "Video Summaries",
    content: "Watch training videos and submit your written summaries for Phase 1 review.",
  },
  "portal-nav-modules": {
    title: "Checklist Modules",
    content: "Upload your research PDFs for each required CubeSat training module.",
  },
};

/** Build the ordered candidate steps for the current surface ("learn" | "applicant" | "portal")
 * and role, automatically discovering any visible nav tabs even if they were
 * dynamically added or unhidden. */
export function resolveCandidateSteps(
  surface: "learn" | "applicant" | "portal",
  role: Role | null,
): TourStepDef[] {
  const steps: TourStepDef[] = [];

  if (surface === "learn") {
    steps.push({
      id: "learn-welcome",
      selector: '[data-tour="learn-brand"]',
      title: "Welcome to SpacePoint Learn",
      content:
        "This is your interactive learning and mission portal. Let's take a quick tour of the tools available to you.",
      placement: "bottom",
    });

    // Dynamically inspect all visible [data-tour^="learn-nav-"] items in DOM order.
    // If a tab is commented out or hidden for this user, it won't be in the DOM and is skipped.
    // If you unhide it later, it appears in the DOM and triggers a spotlight automatically!
    if (typeof document !== "undefined") {
      const seenNavIds = new Set<string>();
      const navElements = document.querySelectorAll<HTMLElement>('[data-tour^="learn-nav-"]');
      navElements.forEach((el) => {
        const attr = el.getAttribute("data-tour");
        if (!attr || seenNavIds.has(attr)) return;
        if (!findVisibleTarget(`[data-tour="${attr}"]`)) return;
        seenNavIds.add(attr);
        const meta = NAV_TAB_CATALOG[attr] ?? {
          title: el.textContent?.trim() || "Navigation Tab",
          content: `Open ${el.textContent?.trim() || "this section"} to explore its tools and activities.`,
        };
        steps.push({
          id: attr,
          selector: `[data-tour="${attr}"]`,
          title: meta.title,
          content: meta.content,
          placement: "right",
        });
      });
    }

    steps.push(
      {
        id: "learn-search-catalog",
        selector: '[data-tour="learn-search-catalog"]',
        title: NAV_TAB_CATALOG["learn-search-catalog"].title,
        content: NAV_TAB_CATALOG["learn-search-catalog"].content,
        placement: "bottom",
      },
      {
        id: "learn-active-program",
        selector: '[data-tour="learn-active-program"]',
        title: NAV_TAB_CATALOG["learn-active-program"].title,
        content: NAV_TAB_CATALOG["learn-active-program"].content,
        placement: "right",
      },
      {
        id: "learn-back-to-portal",
        selector: '[data-tour="learn-back-to-portal"]',
        title: NAV_TAB_CATALOG["learn-back-to-portal"].title,
        content: NAV_TAB_CATALOG["learn-back-to-portal"].content,
        placement: "top",
      },
      {
        id: "learn-replay-tutorial",
        selector: '[data-tour="learn-tutorial-btn"]',
        title: "Replay Tutorial Anytime",
        content: "Use this button whenever you want to replay this guide or check out newly unlocked features.",
        placement: "top",
      },
    );

    return steps.filter((s) => Boolean(s.route) || findVisibleTarget(s.selector) !== null);
  }

  if (surface === "applicant") {
    steps.push(
      {
        id: "applicant-welcome",
        selector: '[data-tour="applicant-brand"]',
        title: "Welcome to SpacePoint Instructor Onboarding",
        content:
          "Track your instructor application progress and complete each qualification stage right from this portal.",
        placement: "bottom",
      },
      {
        id: "applicant-step-videos",
        selector: '[data-tour="applicant-step-video-summaries"]',
        title: "Step 1: Video Summaries",
        content:
          "Start by watching the short orientation videos and submitting a 200+ word summary for each one.",
        placement: "bottom",
      },
      {
        id: "applicant-step-modules",
        selector: '[data-tour="applicant-step-checklist-modules"]',
        title: "Step 2: Checklist Modules",
        content:
          "Once your video summaries are complete, this section unlocks so you can upload your research PDFs.",
        placement: "bottom",
      },
      {
        id: "applicant-replay-tutorial",
        selector: '[data-tour="applicant-tutorial-btn"]',
        title: "Need a Refresher?",
        content: "Click Tutorial anytime to replay this walkthrough.",
        placement: "bottom",
      },
    );

    return steps.filter((s) => Boolean(s.route) || findVisibleTarget(s.selector) !== null);
  }

  // ── Portal Surface (`AppShell`) ───────────────────────────────────────────
  const rolePrefix = role ?? "portal";
  steps.push({
    id: `${rolePrefix}-welcome`,
    selector: '[data-tour="portal-brand"]',
    title: "Welcome to SpacePoint Portal",
    content:
      "Here is a quick walkthrough of the workspace tabs and tools available for your role.",
    placement: "right",
  });

  // Dynamically scan all currently visible `[data-tour^="portal-nav-"]` tabs in DOM order.
  // Because `getNavItems(pathname, activeRole)` renders only the tabs allowed for the active
  // role/domain, this automatically adapts when tabs are hidden, shown, or added!
  if (typeof document !== "undefined") {
    const seenNavIds = new Set<string>();
    const navElements = document.querySelectorAll<HTMLElement>('[data-tour^="portal-nav-"]');
    navElements.forEach((el) => {
      const attr = el.getAttribute("data-tour");
      if (!attr || seenNavIds.has(attr)) return;
      if (!findVisibleTarget(`[data-tour="${attr}"]`)) return;
      seenNavIds.add(attr);
      const meta = NAV_TAB_CATALOG[attr] ?? {
        title: el.textContent?.trim() || "Workspace Section",
        content: `Use ${el.textContent?.trim() || "this tab"} to manage its records and workflows.`,
      };
      steps.push({
        id: `${rolePrefix}:${attr}`,
        selector: `[data-tour="${attr}"]`,
        title: meta.title,
        content: meta.content,
        placement: "right",
      });
    });
  }

  // Judge-specific page toolbar spotlight if on /judge
  steps.push({
    id: `${rolePrefix}:judge-toolbar`,
    selector: '[data-tour="judge-toolbar"]',
    title: "Cohort & Team Filters",
    content:
      "Switch between competition cohorts, filter by locked submissions, or toggle between Students and Observers.",
    placement: "bottom",
  });

  // Shared top-bar controls (automatically skipped if not visible, e.g., RoleSwitcher for single-role users)
  steps.push(
    {
      id: `${rolePrefix}:portal-role-switcher`,
      selector: '[data-tour="portal-role-switcher"]',
      title: "Role Switcher",
      content:
        "Have multiple roles on SpacePoint? Switch between your workspaces anytime from this menu.",
      placement: "bottom",
    },
    {
      id: `${rolePrefix}:portal-notifications`,
      selector: '[data-tour="portal-notifications"]',
      title: "Notifications",
      content: "Stay updated on approvals, session updates, and platform alerts.",
      placement: "bottom",
    },
    {
      id: `${rolePrefix}:portal-profile-avatar`,
      selector: '[data-tour="portal-profile-avatar"]',
      title: "Your Profile",
      content: "Click your avatar to manage your profile details, photo, and account settings.",
      placement: "bottom",
    },
    {
      id: `${rolePrefix}:portal-tutorial-btn`,
      selector: '[data-tour="portal-tutorial-btn"]',
      title: "Replay Tutorial Anytime",
      content:
        "Click this Tutorial button whenever you want a refresher or when new tabs are unlocked for your account.",
      placement: "bottom",
    },
  );

  return steps.filter((s) => Boolean(s.route) || findVisibleTarget(s.selector) !== null);
}

/**
 * Live Action Guides ("What do you want to do?") per surface & role.
 * Selecting any action navigates to the target page and walks the user through
 * the live controls step-by-step (advancing when they click the highlighted
 * element or press Next). If a tab is hidden, its action guide is automatically
 * filtered out via `requiredSelector`.
 */
export function resolveActionGuides(
  surface: "learn" | "applicant" | "portal",
  role: Role | null,
): TourActionGuide[] {
  const guides: TourActionGuide[] = [];

  if (surface === "learn") {
    guides.push(
      {
        id: "action-learn-courses",
        title: "Start or Resume a Course",
        description: "Open your enrolled courses and continue your current video or module.",
        requiredSelector: '[data-tour="learn-nav-my-courses"]',
        steps: [
          {
            id: "act-learn-course-1",
            selector: '[data-tour="learn-nav-my-courses"]',
            title: "1. Open My Learning",
            content: "Click 'My Learning' (or press Next) to go to your enrolled courses.",
            placement: "right",
            advanceOnClick: true,
          },
          {
            id: "act-learn-course-2",
            route: "/learn/my-courses",
            selector: '[data-tour="page-workspace"]',
            title: "2. Pick a Course to Continue",
            content: "Select any course card here to launch the video player and module lessons.",
            placement: "top",
          },
        ],
      },
      {
        id: "action-learn-program",
        title: "Complete Program Milestones",
        description: "Check your assigned cohort program roadmap and required checklist items.",
        requiredSelector: '[data-tour="learn-nav-checklists"]',
        steps: [
          {
            id: "act-learn-prog-1",
            selector: '[data-tour="learn-nav-checklists"]',
            title: "1. Open Programs",
            content: "Click 'Programs' in the navigation bar to view your assigned checklists.",
            placement: "right",
            advanceOnClick: true,
          },
          {
            id: "act-learn-prog-2",
            route: "/learn/checklists",
            selector: '[data-tour="page-workspace"]',
            title: "2. Open Your Program Roadmap",
            content: "Click on your active cohort program to open the interactive milestone board.",
            placement: "top",
          },
        ],
      },
      {
        id: "action-learn-missions",
        title: "Run a CubeSat Mission",
        description: "Design a satellite configuration or run a flight operations simulation.",
        requiredSelector: '[data-tour="learn-nav-missions"]',
        steps: [
          {
            id: "act-learn-mission-1",
            selector: '[data-tour="learn-nav-missions"]',
            title: "1. Open Missions",
            content: "Click 'Missions' to view available CubeSat Design and Flight Operations missions.",
            placement: "right",
            advanceOnClick: true,
          },
          {
            id: "act-learn-mission-2",
            route: "/learn/missions",
            selector: '[data-tour="page-workspace"]',
            title: "2. Launch a Mission",
            content: "Pick a mission briefing to start configuring subsystems or operating a pass.",
            placement: "top",
          },
        ],
      },
      {
        id: "action-learn-arcade",
        title: "Practice in Mission Arcade",
        description: "Run interactive engineering simulations across 8 satellite subsystems.",
        requiredSelector: '[data-tour="learn-nav-arcade"]',
        steps: [
          {
            id: "act-learn-arcade-1",
            selector: '[data-tour="learn-nav-arcade"]',
            title: "1. Open Mission Arcade",
            content: "Click 'Arcade' to enter the SpacePoint simulation hub.",
            placement: "right",
            advanceOnClick: true,
          },
          {
            id: "act-learn-arcade-2",
            route: "/learn/arcade",
            selector: '[data-tour="page-workspace"]',
            title: "2. Choose Explorer or Engineer Track",
            content: "Filter by subsystem and launch any simulation to verify your engineering skills.",
            placement: "top",
          },
        ],
      },
      {
        id: "action-learn-catalog",
        title: "Browse & Search Course Catalog",
        description: "Explore all courses and learning paths available on SpacePoint.",
        requiredSelector: '[data-tour="learn-search-catalog"]',
        steps: [
          {
            id: "act-learn-cat-1",
            selector: '[data-tour="learn-search-catalog"]',
            title: "1. Click the Search Icon",
            content: "Click the search icon (or press Next) to open the full course catalog.",
            placement: "bottom",
            advanceOnClick: true,
          },
          {
            id: "act-learn-cat-2",
            route: "/learn/catalog",
            selector: '[data-tour="page-workspace"]',
            title: "2. Filter & Enroll",
            content: "Search by topic and click any course to view its syllabus and enroll.",
            placement: "top",
          },
        ],
      },
    );

    return guides.filter((g) => !g.requiredSelector || findVisibleTarget(g.requiredSelector) !== null);
  }

  if (surface === "applicant") {
    return [
      {
        id: "action-applicant-videos",
        title: "Submit Video Summaries",
        description: "Watch the orientation videos and submit your written summaries.",
        steps: [
          {
            id: "act-app-vid-1",
            route: "/instructors/status",
            selector: '[data-tour="applicant-step-video-summaries"], [data-tour="page-workspace"]',
            title: "1. Open Video Summaries",
            content: "Click the Video Summaries card (or press Next) to open the video list.",
            placement: "bottom",
            advanceOnClick: true,
          },
          {
            id: "act-app-vid-2",
            route: "/instructors/videos",
            selector: '[data-tour="page-workspace"]',
            title: "2. Watch & Write Summary",
            content: "Watch each training video and submit your 200+ word summary below it.",
            placement: "top",
          },
        ],
      },
    ];
  }

  // ── Portal Role Action Guides ─────────────────────────────────────────────
  if (role === "admin") {
    guides.push(
      {
        id: "action-admin-create-user",
        title: "Create or Manage a User Account",
        description: "Add a new staff/student account, assign roles, or update user details.",
        requiredSelector: '[data-tour="portal-nav-user-management"]',
        steps: [
          {
            id: "act-adm-user-1",
            selector: '[data-tour="portal-nav-user-management"]',
            title: "1. Open User Management",
            content: "Click 'User Management' in the sidebar (or press Next).",
            placement: "right",
            advanceOnClick: true,
          },
          {
            id: "act-adm-user-2",
            route: "/admin/users",
            selector: '[data-tour="admin-users-toolbar"], [data-tour="page-workspace"]',
            title: "2. Search or Filter by Role",
            content: "Filter between Staff, Students, and Organizations, or search by name/email.",
            placement: "bottom",
          },
          {
            id: "act-adm-user-3",
            route: "/admin/users",
            selector: '[data-tour="admin-new-user-btn"], [data-tour="page-workspace"]',
            title: "3. Click 'New user'",
            content: "Click 'New user' here to create an account and assign its SpacePoint roles.",
            placement: "left",
            advanceOnClick: true,
          },
        ],
      },
      {
        id: "action-admin-role-requests",
        title: "Approve Role Requests & Letters",
        description: "Review pending intern/staff role requests and issue signed letters.",
        requiredSelector: '[data-tour="portal-nav-role-requests"]',
        steps: [
          {
            id: "act-adm-rr-1",
            selector: '[data-tour="portal-nav-role-requests"]',
            title: "1. Open Role Requests",
            content: "Click 'Role Requests' in the sidebar to view pending approvals.",
            placement: "right",
            advanceOnClick: true,
          },
          {
            id: "act-adm-rr-2",
            route: "/admin/role-requests",
            selector: '[data-tour="page-workspace"]',
            title: "2. Review & Approve",
            content: "Approve or decline requests here and generate official internship letters.",
            placement: "top",
          },
        ],
      },
    );
  }

  if (role === "operations" || role === "admin" || role === "facilitator" || role === "lms_author") {
    guides.push(
      {
        id: "action-lms-invite-code",
        title: "Create an Invite Code & Auto-Grant Courses",
        description: "Generate a batch signup code and attach automatic course/cohort grants.",
        requiredSelector: '[data-tour="portal-nav-lms"], [data-tour="portal-nav-invite-codes"]',
        steps: [
          {
            id: "act-inv-1",
            selector: '[data-tour="portal-nav-invite-codes"], [data-tour="portal-nav-lms"]',
            title: "1. Open LMS Invite Codes",
            content: "Click 'LMS' / 'Invite Codes' in the sidebar (or press Next) to open the batch codes page.",
            placement: "right",
            advanceOnClick: true,
          },
          {
            id: "act-inv-2",
            route: "/lms-authoring/invite-codes",
            selector: '[data-tour="invite-new-code-btn"], [data-tour="page-workspace"]',
            title: "2. Click 'New code'",
            content: "Click 'New code' to create a student or observer signup code, then expand 'Grants' on the row to attach courses or cohorts.",
            placement: "left",
            advanceOnClick: true,
          },
        ],
      },
      {
        id: "action-lms-manage-student",
        title: "Search Students & Assign Courses",
        description: "Look up any student or observer, inspect their progress, and enroll/unenroll them.",
        requiredSelector: '[data-tour="portal-nav-lms"]',
        steps: [
          {
            id: "act-stu-1",
            selector: '[data-tour="portal-nav-lms"]',
            title: "1. Open LMS Section",
            content: "Open the LMS section in the sidebar (or press Next) to go to the Student Roster.",
            placement: "right",
            advanceOnClick: true,
          },
          {
            id: "act-stu-2",
            route: "/lms-authoring/students",
            selector: '[data-tour="students-filter-bar"], [data-tour="page-workspace"]',
            title: "2. Filter Students or Observers",
            content: "Toggle between Students and Observers, search by name/email, or filter by invite code batch, then click 'Manage' on any row.",
            placement: "bottom",
          },
        ],
      },
    );
  }

  if (role === "operations" || role === "coo" || role === "storekeeper") {
    guides.push({
      id: "action-ops-inventory",
      title: "Manage Kits & Warehouse Stock",
      description: "Inspect SatKit holdings, update warehouse stock counts, and manage fulfilment.",
      requiredSelector: '[data-tour="portal-nav-inventory"]',
      steps: [
        {
          id: "act-inv-stock-1",
          selector: '[data-tour="portal-nav-inventory"]',
          title: "1. Expand Inventory",
          content: "Click 'Inventory' in the sidebar to see Kits, Stock, Warehouses, and Fulfilment.",
          placement: "right",
          advanceOnClick: true,
        },
        {
          id: "act-inv-stock-2",
          route: "/operations/inventory/stock",
          selector: '[data-tour="page-workspace"]',
          title: "2. Review & Adjust Stock",
          content: "Record stock counts, restock items, and track kit allocations across warehouses.",
          placement: "top",
        },
      ],
    });
  }

  if (role === "operations") {
    guides.push({
      id: "action-ops-website",
      title: "Update Website & Labs Content",
      description: "Publish events, update pricing, manage partners, or edit SpacePoint Labs R&D.",
      requiredSelector: '[data-tour="portal-nav-website"]',
      steps: [
        {
          id: "act-web-1",
          selector: '[data-tour="portal-nav-website"]',
          title: "1. Expand Website CMS",
          content: "Click 'Website' in the sidebar to access all 10 public website management tabs.",
          placement: "right",
          advanceOnClick: true,
        },
        {
          id: "act-web-2",
          route: "/operations/website",
          selector: '[data-tour="page-workspace"]',
          title: "2. Edit & Publish Live",
          content: "Update general configuration, events, programs, or press items — changes hydrate spacepoint.ae and labs.spacepoint.ae immediately.",
          placement: "top",
        },
      ],
    });
  }

  if (role === "instructor" || role === "facilitator") {
    guides.push({
      id: "action-inst-sessions",
      title: "Check My Sessions & Attendance",
      description: "View your assigned sessions, schedules, and classroom attendance tools.",
      requiredSelector: '[data-tour="portal-nav-sessions"]',
      steps: [
        {
          id: "act-inst-sess-1",
          selector: '[data-tour="portal-nav-sessions"]',
          title: "1. Open Sessions",
          content: "Click 'Sessions' in the sidebar (or press Next).",
          placement: "right",
          advanceOnClick: true,
        },
        {
          id: "act-inst-sess-2",
          route: "/instructors/my-sessions",
          selector: '[data-tour="page-workspace"]',
          title: "2. Manage Your Assigned Sessions",
          content: "Review session dates, locations, and open any session to record attendance.",
          placement: "top",
        },
      ],
    });
  }

  if (role === "instructor") {
    guides.push(
      {
        id: "action-inst-payments",
        title: "Add Bank Details & Sign Payment Letters",
        description: "Enter your IBAN and sign pending facilitator payment letters.",
        requiredSelector: '[data-tour="portal-nav-payments"]',
        steps: [
          {
            id: "act-inst-pay-1",
            selector: '[data-tour="portal-nav-payments"]',
            title: "1. Open Payments",
            content: "Click 'Payments' in the sidebar to view your earnings and payment letters.",
            placement: "right",
            advanceOnClick: true,
          },
          {
            id: "act-inst-pay-2",
            route: "/instructors/payments",
            selector: '[data-tour="instructor-bank-card"], [data-tour="page-workspace"]',
            title: "2. Complete Bank Details & Sign",
            content: "Save your bank account details here first — once saved, the 'Sign' button unlocks on your payment letters below.",
            placement: "bottom",
          },
        ],
      },
      {
        id: "action-inst-training",
        title: "Complete SatKit Training",
        description: "Access your SatKit training modules and classroom preparation resources.",
        requiredSelector: '[data-tour="portal-nav-satkit-training"]',
        steps: [
          {
            id: "act-inst-trn-1",
            selector: '[data-tour="portal-nav-satkit-training"]',
            title: "1. Open SatKit Training",
            content: "Click 'SatKit Training' in the sidebar.",
            placement: "right",
            advanceOnClick: true,
          },
          {
            id: "act-inst-trn-2",
            route: "/instructors/training",
            selector: '[data-tour="page-workspace"]',
            title: "2. Work Through Training Modules",
            content: "Complete each module here to prepare for delivering hands-on SatKit sessions.",
            placement: "top",
          },
        ],
      },
    );
  }

  if (role === "intern" || role === "leader") {
    guides.push(
      {
        id: "action-intern-board",
        title: "Update Tasks on the Kanban Board",
        description: "View your assigned tasks and move cards across progress columns.",
        requiredSelector: '[data-tour="portal-nav-board"]',
        steps: [
          {
            id: "act-int-brd-1",
            selector: '[data-tour="portal-nav-board"]',
            title: "1. Open Kanban Board",
            content: "Click 'Board' in the sidebar to open your team's workspace.",
            placement: "right",
            advanceOnClick: true,
          },
          {
            id: "act-int-brd-2",
            route: "/interns",
            selector: '[data-tour="page-workspace"]',
            title: "2. Drag & Update Tasks",
            content: "Click any task card to inspect details or move it from To Do to In Progress / Done.",
            placement: "top",
          },
        ],
      },
      {
        id: "action-intern-propose",
        title: "Propose a New Mission",
        description: "Submit a new engineering mission proposal for review.",
        requiredSelector: '[data-tour="portal-nav-propose-a-mission"]',
        steps: [
          {
            id: "act-int-prop-1",
            selector: '[data-tour="portal-nav-propose-a-mission"]',
            title: "1. Click 'Propose a Mission'",
            content: "Select 'Propose a Mission' in the sidebar.",
            placement: "right",
            advanceOnClick: true,
          },
          {
            id: "act-int-prop-2",
            route: "/interns/propose-mission",
            selector: '[data-tour="page-workspace"]',
            title: "2. Fill Out Mission Objectives",
            content: "Define the mission scope, deliverables, and timeline, then submit it for approval.",
            placement: "top",
          },
        ],
      },
    );
  }

  if (role === "ambassador" || role === "teacher") {
    guides.push(
      {
        id: "action-amb-tasks",
        title: "Complete Outreach Tasks & Earn Points",
        description: "View active ambassador tasks and submit proof of completion.",
        requiredSelector: '[data-tour="portal-nav-tasks"]',
        steps: [
          {
            id: "act-amb-tsk-1",
            selector: '[data-tour="portal-nav-tasks"]',
            title: "1. Open Tasks",
            content: "Click 'Tasks' in the sidebar.",
            placement: "right",
            advanceOnClick: true,
          },
          {
            id: "act-amb-tsk-2",
            route: "/ambassadors/tasks",
            selector: '[data-tour="page-workspace"]',
            title: "2. Submit Task Completion",
            content: "Pick an available task, complete the outreach activity, and submit it for points.",
            placement: "top",
          },
        ],
      },
      {
        id: "action-amb-leads",
        title: "Submit a School or Partner Lead",
        description: "Add a new school or organization contact to the outreach pipeline.",
        requiredSelector: '[data-tour="portal-nav-leads"]',
        steps: [
          {
            id: "act-amb-ld-1",
            selector: '[data-tour="portal-nav-leads"]',
            title: "1. Open Leads",
            content: "Click 'Leads' in the sidebar.",
            placement: "right",
            advanceOnClick: true,
          },
          {
            id: "act-amb-ld-2",
            route: "/ambassadors/leads",
            selector: '[data-tour="page-workspace"]',
            title: "2. Add & Track Your Leads",
            content: "Log new school contacts here and track their status through the partnership pipeline.",
            placement: "top",
          },
        ],
      },
    );
  }

  if (role === "mentor") {
    guides.push(
      {
        id: "action-mentor-availability",
        title: "Set Weekly Mentorship Availability",
        description: "Configure the time slots when students and teams can book sessions with you.",
        requiredSelector: '[data-tour="portal-nav-availability"]',
        steps: [
          {
            id: "act-mnt-avail-1",
            selector: '[data-tour="portal-nav-availability"]',
            title: "1. Open Availability",
            content: "Click 'Availability' in the sidebar.",
            placement: "right",
            advanceOnClick: true,
          },
          {
            id: "act-mnt-avail-2",
            route: "/mentor/availability",
            selector: '[data-tour="page-workspace"]',
            title: "2. Add Your Time Slots",
            content: "Add or update your available weekly slots so mentees can schedule sessions.",
            placement: "top",
          },
        ],
      },
      {
        id: "action-mentor-sessions",
        title: "Manage Booked Mentorship Sessions",
        description: "View upcoming bookings, meeting links, and mark attendance.",
        requiredSelector: '[data-tour="portal-nav-sessions"]',
        steps: [
          {
            id: "act-mnt-sess-1",
            selector: '[data-tour="portal-nav-sessions"]',
            title: "1. Open Sessions",
            content: "Click 'Sessions' in the sidebar.",
            placement: "right",
            advanceOnClick: true,
          },
          {
            id: "act-mnt-sess-2",
            route: "/mentor/sessions",
            selector: '[data-tour="page-workspace"]',
            title: "2. Join Meet & Track Attendance",
            content: "Access the Google Meet link and record session attendance here.",
            placement: "top",
          },
        ],
      },
    );
  }

  if (role === "judge") {
    guides.push({
      id: "action-judge-score",
      title: "Filter & Score a Competition Team",
      description: "Filter teams by cohort or Student/Observer mode and submit rubric scores.",
      requiredSelector: '[data-tour="portal-nav-teams"]',
      steps: [
        {
          id: "act-jdg-1",
          route: "/judge",
          selector: '[data-tour="judge-toolbar"], [data-tour="page-workspace"]',
          title: "1. Filter Cohort & Mode",
          content: "Use this toolbar to toggle between Students and Observers or filter by Locked submissions.",
          placement: "bottom",
        },
        {
          id: "act-jdg-2",
          route: "/judge",
          selector: '[data-tour="page-workspace"]',
          title: "2. Select a Team Row to Score",
          content: "Click on any team in the list to inspect their CubeSat mission artifacts and enter your rubric scores.",
          placement: "top",
        },
      ],
    });
  }

  if (role === "organization") {
    guides.push({
      id: "action-org-events",
      title: "Manage Organization Events & Mentors",
      description: "View your hosted SpacePoint events and browse the Space Mentors directory.",
      requiredSelector: '[data-tour="portal-nav-my-events"]',
      steps: [
        {
          id: "act-org-1",
          selector: '[data-tour="portal-nav-my-events"]',
          title: "1. Open My Events",
          content: "Click 'My Events' in the sidebar to view your organization's events.",
          placement: "right",
          advanceOnClick: true,
        },
        {
          id: "act-org-2",
          route: "/organization/events",
          selector: '[data-tour="page-workspace"]',
          title: "2. Inspect Event Rosters",
          content: "Review event details, participant lists, and schedules here.",
          placement: "top",
        },
      ],
    });
  }

  return guides.filter((g) => !g.requiredSelector || findVisibleTarget(g.requiredSelector) !== null);
}
